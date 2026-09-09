import datetime as dt
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from wqb_agent.daily_cache import DailyResearchCache
from wqb_agent.alpha_factory import (
    AlphaFactory,
    AlphaTemplate,
    AlphaTemplateRegistry,
)
from wqb_agent.research_guard import parameter_only_change_reason
from wqb_agent.agent import Agent
from wqb_agent.state import Experiment
from wqb_agent.checkpoints import CheckpointStore
from wqb_agent.proposal_contract import factory_batch_stats, validate_factory_batch
from wqb_agent.factory_runner import AIFactoryRunner
from wqb_agent.weekly_quota import QuotaExceeded, WeeklySimulationQuota


def _utc_timestamp(value):
    return value.replace(tzinfo=dt.timezone.utc).timestamp()


class TestDailyResearchCache(unittest.TestCase):
    def test_uses_new_york_calendar_day_and_drops_previous_bucket(self):
        now = [_utc_timestamp(dt.datetime(2026, 9, 9, 3, 59))]
        cache = DailyResearchCache(clock=lambda: now[0])

        cache.put_simulations([{"alpha_id": "a1", "sharpe": 1.2}])
        self.assertEqual(cache.local_date, "2026-09-08")
        self.assertEqual(cache.simulations(), [{"alpha_id": "a1", "sharpe": 1.2}])

        # 04:00 UTC is midnight in New York after the DST transition period.
        now[0] = _utc_timestamp(dt.datetime(2026, 9, 9, 4, 0))
        self.assertEqual(cache.local_date, "2026-09-09")
        self.assertEqual(cache.simulations(), [])
        self.assertEqual(cache.submitted_alphas(), [])
        self.assertEqual(cache.colors(), [])

    def test_cache_is_memory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DailyResearchCache(clock=lambda: _utc_timestamp(
                dt.datetime(2026, 9, 9, 12, 0)
            ))
            cache.put_submitted_alphas([{"alpha_id": "a1"}])
            cache.put_colors([{"alpha_id": "a1", "classification": "BLUE"}])
            self.assertFalse(os.listdir(tmp))
            self.assertEqual(cache.snapshot()["local_date"], "2026-09-09")

    def test_same_day_batches_accumulate_without_duplicate_alpha_ids(self):
        cache = DailyResearchCache(clock=lambda: _utc_timestamp(
            dt.datetime(2026, 9, 9, 12, 0)
        ))
        cache.put_simulations([{"alpha_id": "a1", "sharpe": 1.0}])
        cache.put_simulations([
            {"alpha_id": "a1", "sharpe": 1.1},
            {"alpha_id": "a2", "sharpe": 0.8},
        ])
        self.assertEqual(cache.simulations(), [
            {"alpha_id": "a1", "sharpe": 1.1},
            {"alpha_id": "a2", "sharpe": 0.8},
        ])


class TestWeeklySimulationQuota(unittest.TestCase):
    def test_daily_refresh_preserves_weekly_usage(self):
        now = [_utc_timestamp(dt.datetime(2026, 9, 8, 12, 0))]
        quota = WeeklySimulationQuota(
            weekly_cap=11200, daily_cap=1600, clock=lambda: now[0]
        )
        state = quota.initial_state()
        state = quota.reserve(state, 1600)
        self.assertEqual(quota.remaining(state), 0)
        with self.assertRaises(QuotaExceeded):
            quota.reserve(state, 1)

        now[0] = _utc_timestamp(dt.datetime(2026, 9, 9, 12, 0))
        state = quota.normalize_state(state)
        self.assertEqual(state["daily_reserved"], 0)
        self.assertEqual(state["weekly_reserved"], 1600)
        self.assertEqual(quota.remaining(state), 1600)

    def test_week_refresh_clears_weekly_and_daily_usage(self):
        now = [_utc_timestamp(dt.datetime(2026, 9, 13, 12, 0))]
        quota = WeeklySimulationQuota(
            weekly_cap=11200, daily_cap=1600, clock=lambda: now[0]
        )
        state = quota.reserve(quota.initial_state(), 1600)
        now[0] = _utc_timestamp(dt.datetime(2026, 9, 14, 12, 0))
        state = quota.normalize_state(state)
        self.assertEqual(state["daily_reserved"], 0)
        self.assertEqual(state["weekly_reserved"], 0)
        self.assertEqual(quota.remaining(state), 1600)

    def test_malformed_state_fails_closed(self):
        quota = WeeklySimulationQuota(weekly_cap=11200, daily_cap=1600)
        with self.assertRaises(ValueError):
            quota.normalize_state({"daily_reserved": "not-a-number"})

    def test_state_contains_only_quota_metadata(self):
        quota = WeeklySimulationQuota(weekly_cap=11200, daily_cap=1600)
        state = quota.initial_state()
        self.assertEqual(
            set(state),
            {
                "schema_version", "timezone", "local_date", "week_start",
                "daily_cap", "weekly_cap", "daily_reserved", "weekly_reserved",
            },
        )


class TestAgentColorAndOptimizerTriggers(unittest.TestCase):
    def test_remote_alpha_feed_refreshes_submitted_and_today_simulations_together(self):
        class FeedClient:
            def __init__(self):
                self.calls = []

            def get_user_alphas(self, *, status, limit, offset):
                self.calls.append((status, limit, offset))
                if status == "SUBMITTED":
                    return {"results": [{
                        "id": "submitted-1",
                        "status": "SUBMITTED",
                        "dateSubmitted": "2026-09-08T20:00:00-04:00",
                    }]}
                return {"results": [
                    {
                        "id": "today-1",
                        "status": "UNSUBMITTED",
                        "dateCreated": "2026-09-09T08:00:00-04:00",
                    },
                    {
                        "id": "old-1",
                        "status": "UNSUBMITTED",
                        "dateCreated": "2026-09-08T08:00:00-04:00",
                    },
                ]}

        agent = Agent.__new__(Agent)
        agent.client = FeedClient()
        agent.daily_cache = DailyResearchCache(clock=lambda: _utc_timestamp(
            dt.datetime(2026, 9, 9, 12, 0)
        ))
        snapshot = agent.refresh_remote_alpha_feed(limit=20)

        self.assertEqual(snapshot["submitted_count"], 1)
        self.assertEqual(snapshot["today_simulated_count"], 1)
        self.assertEqual(agent.daily_cache.submitted_alphas()[0]["alpha_id"], "submitted-1")
        self.assertEqual(agent.daily_cache.simulations()[0]["alpha_id"], "today-1")
        self.assertEqual(agent.client.calls, [
            ("SUBMITTED", 20, 0), ("UNSUBMITTED", 20, 0),
        ])

    def test_settled_result_updates_color_cache_immediately(self):
        agent = Agent.__new__(Agent)
        agent.daily_cache = DailyResearchCache(clock=lambda: _utc_timestamp(
            dt.datetime(2026, 9, 9, 12, 0)
        ))
        experiment = {
            "alpha_id": "alpha-1",
            "status": "DONE",
            "economic_mechanism": "已验证的事件后价格漂移机制",
            "falsification": "若跨年份稳定性失败则停止该方向",
            "health": {"ok": True},
            "quality_label": "SUCCESS",
            "metrics": {
                "sharpe": 1.1, "fitness": 0.8, "turnover": 0.2,
                "returns": 0.1, "drawdown": 0.05, "margin": 0.03,
                "checks": [],
            },
        }
        agent._cache_color_result(experiment)
        self.assertEqual(agent.daily_cache.colors(), [{
            "alpha_id": "alpha-1", "classification": "BLUE",
        }])

    def test_optimizer_gate_reports_missing_agent_child_hypothesis(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(object(), {"simulation": {}, "agent": {"state_dir": tmp}})
            parent = {
                "status": "DONE",
                "expression": "rank(field)",
                "fields_used": ["field"],
                "datasets": ["fundamental6"],
                "metrics": {"sharpe": 1.1, "fitness": 0.8, "turnover": 0.2},
                "health": {"ok": True},
                "field_understanding": {"field": "已核验字段"},
                "field_analysis": {"field": {"data_type": "MATRIX"}},
                "field_source": {"kind": "brain_api"},
                "field_hypothesis_basis": {"field": {"mechanism": "质量变化"}},
            }
            report = agent.optimizer_gate_report([parent])
        self.assertEqual(report["done_parent_count"], 1)
        self.assertEqual(report["ready_parent_count"], 0)
        self.assertEqual(report["blocked_reasons"]["missing_child_economic_hypothesis"], 1)


class TestFactoryBatchContract(unittest.TestCase):
    def _proposal(self, index, origin="factory"):
        return {
            "expression": f"rank(field_{index})",
            "proposal_origin": origin,
            "fields": [f"field_{index}"],
        }

    def test_factory_batch_requires_exactly_one_hundred_unique_proposals(self):
        ok, errors = validate_factory_batch(
            [self._proposal(index) for index in range(100)]
        )
        self.assertTrue(ok, errors)

        ok, errors = validate_factory_batch(
            [self._proposal(index) for index in range(99)]
        )
        self.assertFalse(ok)
        self.assertIn("100", " ".join(errors))

    def test_factory_batch_rejects_duplicate_and_unowned_candidates(self):
        proposals = [self._proposal(index) for index in range(99)]
        proposals.append(self._proposal(0))
        ok, errors = validate_factory_batch(proposals)
        self.assertFalse(ok)
        self.assertTrue(any("重复" in error for error in errors))

        proposals = [self._proposal(index) for index in range(99)]
        proposals.append(self._proposal(99, origin="legacy_agent"))
        ok, errors = validate_factory_batch(proposals)
        self.assertFalse(ok)
        self.assertTrue(any("来源" in error for error in errors))

    def test_factory_batch_can_require_real_multi_dataset_coverage(self):
        single_dataset = [
            {
                **self._proposal(index),
                "datasets": ["pv1"],
            }
            for index in range(100)
        ]
        ok, errors = validate_factory_batch(single_dataset, min_datasets=2)
        self.assertFalse(ok)
        self.assertTrue(any("dataset" in error for error in errors))

        multi_dataset = []
        for index in range(100):
            dataset = "pv1" if index % 2 else "option8"
            multi_dataset.append({
                **self._proposal(index),
                "datasets": [dataset],
                "field_refs": [{"dataset": dataset, "id": f"field_{index}"}],
            })
        ok, errors = validate_factory_batch(
            multi_dataset,
            min_datasets=2,
            require_cross_dataset_pairs=True,
        )
        self.assertFalse(ok)
        self.assertTrue(any("跨 dataset" in error for error in errors))
        stats = factory_batch_stats(multi_dataset)
        self.assertEqual(stats["dataset_counts"], {"pv1": 50, "option8": 50})
        self.assertEqual(stats["cross_dataset_pair_count"], 0)

    def test_factory_generates_a_full_batch_from_mechanism_templates(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference

        reference = _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )
        fields = [
            {"id": f"field_{index}", "description": "已核验经济字段", "type": "MATRIX",
             "semantic_status": "KNOWN", "dataset": "fundamental6"}
            for index in range(10)
        ]
        proposals = AlphaFactory().generate_factory_batch(
            {"id": "factory", "datasets": ["fundamental6"]},
            fields, reference, target=100,
        )
        self.assertEqual(len(proposals), 100)
        self.assertTrue(all(isinstance(item, dict) for item in proposals))
        self.assertTrue(all(item["proposal_origin"] == "factory" for item in proposals))
        self.assertTrue(all(item["expression"] for item in proposals))
        ok, errors = validate_factory_batch(proposals)
        self.assertTrue(ok, errors)

    def test_factory_batch_prefers_cross_dataset_companions_and_reports_stats(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference

        reference = _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )
        datasets = ["pv1", "pv13", "option8"]
        fields = [
            {
                "id": f"field_{index}", "description": f"verified field {index}",
                "type": "MATRIX", "semantic_status": "KNOWN",
                "dataset": datasets[index % len(datasets)],
            }
            for index in range(30)
        ]
        proposals = AlphaFactory().generate_factory_batch(
            {"id": "factory", "datasets": datasets}, fields, reference, target=100
        )
        stats = factory_batch_stats(proposals)
        ok, errors = validate_factory_batch(
            proposals, target=100, min_datasets=3,
            require_cross_dataset_pairs=True,
        )
        self.assertTrue(ok, errors)
        self.assertGreater(stats["dual_or_multi_field_count"], 0)
        self.assertGreater(stats["cross_dataset_pair_count"], 0)
        self.assertIn("generic_pair_spread_change", stats["template_counts"])

    def test_generic_data_field_template_supports_multiple_slots_and_field_refs(self):
        registry = AlphaTemplateRegistry([
            AlphaTemplate(
                "generic_triple_confirmation",
                "generic_multi_field_confirmation",
                "rank(add(ts_zscore({data_field}, 20), add(ts_zscore({s}, 20), ts_zscore({t}, 20))))",
                required_slots=("data_field", "s", "t"),
                economic=False,
            ),
        ])
        fields = [
            {"id": "low", "dataset": "pv1"},
            {"id": "implied_vol", "dataset": "option8"},
            {"id": "target_price", "dataset": "analyst4"},
        ]
        candidates = AlphaFactory(registry=registry).generate(
            {"template_ids": ["generic_triple_confirmation"]}, fields, count=1
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertIn("low", candidate["expression"])
        self.assertIn("implied_vol", candidate["expression"])
        self.assertIn("target_price", candidate["expression"])
        self.assertEqual(candidate["template_slots"]["data_field"], "low")
        self.assertEqual(candidate["template_slots"]["s"], "implied_vol")
        self.assertEqual(candidate["template_slots"]["t"], "target_price")
        self.assertEqual(
            [(item["dataset"], item["id"]) for item in candidate["field_refs"]],
            [("pv1", "low"), ("option8", "implied_vol"), ("analyst4", "target_price")],
        )

    def test_assemble_connects_dual_field_template_across_datasets(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference

        reference = _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )
        fields = [
            {
                "id": "low", "dataset": "pv1", "type": "MATRIX",
                "description": "daily low price", "semantic_status": "KNOWN",
            },
            {
                "id": "implied_vol", "dataset": "option8", "type": "MATRIX",
                "description": "option implied volatility", "semantic_status": "KNOWN",
            },
        ]
        proposals = AlphaFactory().assemble_proposals(
            {
                "id": "pair", "datasets": ["pv1", "option8"],
                "template_ids": ["relative_spread_change"],
            },
            fields,
            reference,
            max_candidates=1,
        )
        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        self.assertEqual(proposal["fields"], ["low", "implied_vol"])
        self.assertEqual(proposal["datasets"], ["pv1", "option8"])
        self.assertEqual(
            [(item["dataset"], item["id"]) for item in proposal["field_refs"]],
            [("pv1", "low"), ("option8", "implied_vol")],
        )
        self.assertEqual(proposal["template_slots"]["p"], "low")
        self.assertEqual(proposal["template_slots"]["s"], "implied_vol")

    def test_assemble_connects_generic_triple_template_and_records_all_slots(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference

        reference = _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )
        fields = [
            {"id": "low", "dataset": "pv1", "type": "MATRIX",
             "description": "daily low price", "semantic_status": "KNOWN"},
            {"id": "implied_vol", "dataset": "option8", "type": "MATRIX",
             "description": "option implied volatility", "semantic_status": "KNOWN"},
            {"id": "target_price", "dataset": "analyst4", "type": "MATRIX",
             "description": "analyst target price", "semantic_status": "KNOWN"},
        ]
        proposals = AlphaFactory().assemble_proposals(
            {
                "id": "triple", "datasets": ["pv1", "option8", "analyst4"],
                "template_ids": ["generic_triple_confirmation"],
            },
            fields,
            reference,
            max_candidates=1,
        )
        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        self.assertEqual(proposal["fields"], ["low", "implied_vol", "target_price"])
        self.assertEqual(
            {item["dataset"] for item in proposal["field_refs"]},
            {"pv1", "option8", "analyst4"},
        )
        self.assertEqual(proposal["template_slots"]["data_field"], "low")
        self.assertEqual(proposal["template_slots"]["t"], "target_price")

    def test_agent_runtime_keeps_results_and_trajectory_out_of_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(object(), {"simulation": {}, "agent": {"state_dir": tmp}})
            experiment = Experiment(1, "h", "rank(field)", {}, ["field"])
            experiment.status = "DONE"
            experiment.metrics = {"sharpe": 1.0}
            agent.trajectory.add(experiment)
            agent._record_trial_phase(experiment, "completed", outcome="DONE")
            agent._write_sims_results(1, [experiment])
            agent.memory.save()
            self.assertEqual(os.listdir(tmp), [])
            self.assertEqual(len(agent.daily_cache.simulations()), 1)

    def test_nonpersistent_runtime_does_not_resurrect_old_trajectory_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            trajectory_path = os.path.join(tmp, "trajectory.jsonl")
            old = Experiment(7, "old", "rank(old_field)", {}, ["old_field"])
            old.status = "DONE"
            old.metrics = {"sharpe": 99.0}
            with open(trajectory_path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(old.to_dict()) + "\n")
            agent = Agent(object(), {"simulation": {}, "agent": {"state_dir": tmp}})
            agent._ensure_loaded()
            self.assertEqual(agent.trajectory.experiments, [])
            self.assertEqual(agent._terminal_expressions(), set())

    def test_nested_platform_dataset_id_is_normalized_for_alpha_count_overlay(self):
        agent = Agent(object(), {"simulation": {}, "agent": {"state_dir": tempfile.mkdtemp()}})
        agent.discovery._using_catalog = True
        agent.discovery._disk_cache = {
            "news18": [{
                "id": "news_field",
                "description": "news semantic field",
                "type": "MATRIX",
                "dataset": {"id": "news18", "name": "News"},
                "alphaCount": 7,
            }]
        }
        _types, profiles = agent._read_field_cache()
        self.assertEqual(profiles["news_field"]["dataset"], "news18")

    def test_numeric_window_change_is_not_a_new_mechanism(self):
        self.assertIsNotNone(parameter_only_change_reason(
            "rank(ts_zscore(field, 20))",
            "rank(ts_zscore(field, 60))",
        ))
        self.assertIsNone(parameter_only_change_reason(
            "rank(field)", "group_neutralize(rank(field), SUBINDUSTRY)"
        ))

    def test_factory_execution_blocks_partial_batch_before_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(object(), {"simulation": {}, "agent": {"state_dir": tmp}})
            path = os.path.join(tmp, "proposals.json")
            with open(path, "w", encoding="utf-8") as handle:
                import json
                json.dump({
                    "round_no": 1,
                    "batch_type": "factory_100",
                    "proposals": [self._proposal(index) for index in range(99)],
                }, handle)
            self.assertIsNone(agent.run_proposals(path))
            self.assertFalse(os.path.exists(os.path.join(tmp, "round_1.checkpoint.json")))

    def test_factory_batch_passes_normal_preflight_as_one_hundred_atomic_jobs(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference

        reference = _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )
        fields = [
            {"id": f"field_{index}", "description": "已核验经济字段", "type": "MATRIX",
             "semantic_status": "KNOWN", "dataset": "fundamental6"}
            for index in range(10)
        ]
        proposals = AlphaFactory().generate_factory_batch(
            {"id": "factory", "datasets": ["fundamental6"]},
            fields, reference, target=100,
        )
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(object(), {"simulation": {}, "agent": {"state_dir": tmp}})
            agent.simulator.run = Mock()
            path = os.path.join(tmp, "proposals.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({
                    "round_no": 1,
                    "batch_type": "factory_100",
                    "hypothesis": {
                        "id": "factory", "statement": "检验已核验字段的经济机制",
                        "datasets": ["fundamental6"], "direction": "long",
                    },
                    "fields": fields,
                    "proposals": proposals,
                }, handle)
            agent.run_proposals(path)
            self.assertEqual(agent.last_run_stats.get("accepted"), 100)
            agent.simulator.run.assert_called_once()
            self.assertEqual(len(agent.simulator.run.call_args.args[0]), 100)
            self.assertTrue(os.path.exists(os.path.join(tmp, "round_1.checkpoint.json")))

    def test_agent_optimizer_requires_explicit_non_parameter_mechanism(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference
        reference = _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )
        parent = {
            "status": "DONE",
            "expression": "rank(ts_zscore(field, 20))",
            "fields_used": ["field"],
            "datasets": ["fundamental6"],
            "metrics": {"sharpe": 1.1, "fitness": 0.8, "turnover": 0.2},
            "health": {"ok": True},
            "field_understanding": {"field": "已核验字段"},
            "field_analysis": {"field": {"data_type": "MATRIX"}},
            "field_source": {"kind": "brain_api", "snapshot_date": "2026-09-08"},
            "field_hypothesis_basis": {"field": {"mechanism": "质量变化"}},
            "hypothesis_id": "h1",
            "child_economic_hypothesis": {
                "expression": "rank(ts_zscore(field, 60))",
                "economic_mechanism": "长期标准化不能单独构成新机制",
                "change_type": "window_change",
            },
        }
        self.assertEqual(AlphaFactory().optimize_signal_proposals(
            [parent], reference, max_candidates=4
        ), [])

    def test_completed_checkpoint_is_not_a_result_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Experiment(1, "h", "rank(field)", {}, ["field"])
            experiment.status = "DONE"
            experiment.alpha_id = "alpha-secret-result-id"
            experiment.metrics = {"sharpe": 9.9, "checks": [{"name": "SELF_CORRELATION"}]}
            CheckpointStore(tmp).write(1, {"id": "h"}, [experiment], complete=True)
            with open(os.path.join(tmp, "round_1.checkpoint.json"), encoding="utf-8") as handle:
                payload = handle.read()
            self.assertNotIn("alpha-secret-result-id", payload)
            self.assertNotIn("sharpe", payload)
            self.assertNotIn("SELF_CORRELATION", payload)

    def test_unfinished_checkpoint_keeps_recovery_identity_but_not_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Experiment(1, "h", "rank(field)", {}, ["field"])
            experiment.status = "UNKNOWN"
            experiment.progress_url = "https://api.worldquantbrain.com/simulations/known"
            experiment.alpha_id = "alpha-secret-result-id"
            experiment.metrics = {"sharpe": 9.9}
            CheckpointStore(tmp).write(1, {"id": "h"}, [experiment], complete=False)
            with open(os.path.join(tmp, "round_1.checkpoint.json"), encoding="utf-8") as handle:
                payload = handle.read()
            self.assertIn("known", payload)
            self.assertNotIn("alpha-secret-result-id", payload)
            self.assertNotIn("sharpe", payload)

    def test_checkpoint_identity_prevents_cross_process_resubmission(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Experiment(1, "h", "rank(field)", {}, ["field"])
            experiment.status = "DONE"
            CheckpointStore(tmp).write(1, {"id": "h"}, [experiment], complete=True)
            agent = Agent(object(), {"simulation": {}, "agent": {"state_dir": tmp}})
            self.assertEqual(agent.next_round_no(), 2)
            terminal, _fingerprints = agent._terminal_identities(["rank(field)"])
            self.assertIn("rank(field)", terminal)


class TestFactoryRunnerAccounting(unittest.TestCase):
    def test_known_expressions_include_completed_checkpoint_identities(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Experiment(1, "h", "rank(old_field)", {}, ["old_field"])
            experiment.status = "DONE"
            CheckpointStore(tmp).write(1, {"id": "h"}, [experiment], complete=True)
            agent = SimpleNamespace(
                state_dir=tmp,
                memory=SimpleNamespace(seen_expressions=set()),
                trajectory=SimpleNamespace(experiments=[]),
                checkpoints=CheckpointStore(tmp),
            )
            known = AIFactoryRunner(agent, factory=Mock())._known_expressions()
        self.assertIn("rank(old_field)", known)

    def test_none_without_checkpoint_is_not_counted_as_completed_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [0.0]

            def sleep(seconds):
                now[0] += seconds

            proposals = [
                {
                    "expression": f"rank(field_{index})",
                    "proposal_origin": "factory",
                    "datasets": ["d1"],
                }
                for index in range(100)
            ]
            agent = SimpleNamespace(
                state_dir=tmp,
                alpha_factory=Mock(),
                factory_config={},
                min_factory_datasets=1,
                min_cross_dataset_pairs=0,
                next_round_no=lambda: 1,
                run_suggestion_round=Mock(return_value={
                    "research_space": {
                        "id": "h1", "statement": "test", "datasets": ["d1"]
                    },
                    "fields": [],
                    "operator_reference": {},
                    "field_source": {"kind": "brain_api", "snapshot_date": "today"},
                }),
                run_proposals=Mock(return_value=None),
                last_run_stats={
                    "accepted": 0, "rejected": 100, "skipped": 0,
                    "status": "PREFLIGHT_BLOCKED",
                },
                checkpoints=SimpleNamespace(
                    unfinished_except=lambda _round: None,
                    scan=lambda: [],
                ),
                memory=SimpleNamespace(seen_expressions=set()),
                trajectory=SimpleNamespace(experiments=[]),
            )
            agent.alpha_factory.generate_factory_batch.return_value = proposals
            result = AIFactoryRunner(
                agent, factory=agent.alpha_factory, quiet=True,
                clock=lambda: now[0], sleeper=sleep,
            ).run(
                duration_sec=1, idle_sleep_sec=1, max_simulations=11200,
                daily_simulation_cap=1600, weekly_simulation_cap=11200,
            )

        self.assertEqual(result["rounds_completed"], 0)
        self.assertEqual(result["simulations_reserved"], 0)
        self.assertEqual(result["last_action"], "WAIT_RUN_PROPOSALS")
        self.assertEqual(result["last_result"]["status"], "RUN_PROPOSALS_NOT_EXECUTED")
        self.assertEqual(result["last_result"]["agent_status"], "PREFLIGHT_BLOCKED")
        self.assertEqual(result["quota"]["daily_cap"], 1600)
        self.assertEqual(result["quota"]["weekly_cap"], 11200)
        agent.run_proposals.assert_called_once()

    def test_checkpoint_recovery_records_the_checkpoint_round_in_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [0.0]
            experiment = Experiment(7, "h", "rank(field)", {}, ["field"])
            experiment.status = "UNKNOWN"
            experiment.progress_url = "https://api.worldquantbrain.com/simulations/known"
            CheckpointStore(tmp).write(
                7, {"id": "h", "_round": 7}, [experiment], complete=False
            )
            with open(os.path.join(tmp, "proposals.json"), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 7}, handle)

            def recover(_path):
                now[0] = 2.0
                return None

            agent = SimpleNamespace(
                state_dir=tmp,
                alpha_factory=Mock(),
                checkpoints=CheckpointStore(tmp),
                run_proposals=recover,
            )
            result = AIFactoryRunner(
                agent, factory=agent.alpha_factory,
                clock=lambda: now[0], sleeper=lambda _seconds: None,
            ).run(duration_sec=1, max_simulations=10)

        self.assertEqual(result["last_round"], 7)
        self.assertEqual(result["last_action"], "CHECKPOINT_BLOCKED")

    def test_daily_quota_blocks_batch_before_production_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [0.0]
            proposals = [
                {
                    "expression": f"rank(field_{index})",
                    "proposal_origin": "factory",
                    "datasets": ["d1"],
                }
                for index in range(100)
            ]
            agent = SimpleNamespace(
                state_dir=tmp,
                alpha_factory=Mock(),
                factory_config={},
                min_factory_datasets=1,
                min_cross_dataset_pairs=0,
                next_round_no=lambda: 1,
                run_suggestion_round=Mock(return_value={
                    "research_space": {
                        "id": "h1", "statement": "test", "datasets": ["d1"]
                    },
                    "fields": [],
                    "operator_reference": {},
                    "field_source": {"kind": "brain_api", "snapshot_date": "today"},
                }),
                run_proposals=Mock(),
                checkpoints=SimpleNamespace(
                    unfinished_except=lambda _round: None,
                    scan=lambda: [],
                ),
                memory=SimpleNamespace(seen_expressions=set()),
                trajectory=SimpleNamespace(experiments=[]),
            )
            agent.alpha_factory.generate_factory_batch.return_value = proposals
            result = AIFactoryRunner(
                agent, factory=agent.alpha_factory, quiet=True,
                clock=lambda: now[0],
                sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
            ).run(
                duration_sec=1, idle_sleep_sec=1, max_simulations=11200,
                daily_simulation_cap=50, weekly_simulation_cap=11200,
            )

        self.assertEqual(result["status"], "SIMULATION_BUDGET_CAP")
        self.assertEqual(result["last_action"], "FACTORY_BATCH_BUDGET_BLOCKED")
        self.assertEqual(result["quota"]["daily_reserved"], 0)
        agent.run_proposals.assert_not_called()


if __name__ == "__main__":
    unittest.main()
