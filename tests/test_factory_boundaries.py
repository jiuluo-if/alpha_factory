import datetime as dt
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from wqb_agent.agent import Agent
from wqb_agent.alpha_factory import (
    AlphaFactory,
    AlphaTemplate,
    AlphaTemplateRegistry,
)
from wqb_agent.alpha_feed_cache import WeeklyAlphaFeedCache
from wqb_agent.alpha_feed_workflow import AlphaFeedWorkflow
from wqb_agent.checkpoints import CheckpointStore
from wqb_agent.client import WQBQueryTooBroadError
from wqb_agent.daily_cache import DailyResearchCache
from wqb_agent.diversity import (
    derive_budget_priority,
    diversity_audit,
    select_budget_candidates,
    semantic_mechanism_key,
)
from wqb_agent.factory_runner import AIFactoryRunner
from wqb_agent.proposal_contract import factory_batch_stats, validate_factory_batch
from wqb_agent.research_guard import parameter_only_change_reason
from wqb_agent.state import Experiment
from wqb_agent.weekly_quota import QuotaExceeded, WeeklySimulationQuota


def _utc_timestamp(value):
    return value.replace(tzinfo=dt.UTC).timestamp()


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


class TestWeeklyAlphaFeedCache(unittest.TestCase):
    def test_persists_time_buckets_and_prunes_oldest_simulations(self):
        now = [_utc_timestamp(dt.datetime(2026, 9, 9, 12, 0))]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "weekly.json")
            cache = WeeklyAlphaFeedCache(
                path, clock=lambda: now[0], weekly_simulation_cap=3
            )
            result = cache.refresh({
                "2026-09-07": {
                    "simulations": [{"alpha_id": "old-1"}],
                    "submitted_alphas": [],
                },
                "2026-09-08": {
                    "simulations": [{"alpha_id": "old-2"}],
                    "submitted_alphas": [{"alpha_id": "submitted-1"}],
                },
                "2026-09-09": {
                    "simulations": [
                        {"alpha_id": "today-1"},
                        {"alpha_id": "today-2"},
                    ],
                    "submitted_alphas": [],
                },
            })

            self.assertEqual(result["simulation_count"], 3)
            self.assertEqual(result["pruned_simulation_count"], 1)
            self.assertEqual(result["local_date"], "2026-09-09")
            self.assertTrue(result["updated_at"])
            self.assertTrue(result["expires_at"])
            payload = cache.load()
            self.assertEqual(
                set(payload["days"]), {"2026-09-08", "2026-09-09"}
            )
            self.assertEqual(
                [row["alpha_id"] for row in payload["days"]["2026-09-09"]["simulations"]],
                ["today-1", "today-2"],
            )

    def test_cross_week_load_removes_expired_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "weekly.json")
            first = WeeklyAlphaFeedCache(
                path,
                clock=lambda: _utc_timestamp(dt.datetime(2026, 9, 9, 12, 0)),
            )
            first.refresh({"2026-09-09": {"simulations": [], "submitted_alphas": []}})
            next_week = WeeklyAlphaFeedCache(
                path,
                clock=lambda: _utc_timestamp(dt.datetime(2026, 9, 14, 12, 0)),
            )

            self.assertIsNone(next_week.load())
            self.assertFalse(os.path.exists(path))


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
    def test_remote_alpha_feed_refreshes_week_buckets_and_today_count_together(self):
        class FeedClient:
            def __init__(self):
                self.calls = []

            def get_all_user_alphas(
                self, *, status, limit, max_pages=None, max_results=1000, **kwargs
            ):
                self.calls.append((status, limit, max_pages))
                if status == "SUBMITTED":
                    return [{
                        "id": "submitted-1",
                        "status": "SUBMITTED",
                        "dateSubmitted": "2026-09-08T20:00:00-04:00",
                    }]
                return [
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
                ]

        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent.__new__(Agent)
            agent.client = FeedClient()
            agent.daily_cache = DailyResearchCache(clock=lambda: _utc_timestamp(
                dt.datetime(2026, 9, 9, 12, 0)
            ))
            agent.alpha_feed_cache = WeeklyAlphaFeedCache(
                os.path.join(tmp, "weekly.json"),
                clock=lambda: _utc_timestamp(dt.datetime(2026, 9, 9, 12, 0)),
            )
            agent.alpha_feed_workflow = AlphaFeedWorkflow(
                alpha_reader=agent.client.get_all_user_alphas,
                daily_cache=agent.daily_cache,
                weekly_cache=agent.alpha_feed_cache,
            )
            snapshot = agent.refresh_remote_alpha_feed(limit=20)

            self.assertEqual(snapshot["submitted_count"], 1)
            self.assertEqual(snapshot["today_simulated_count"], 1)
            self.assertEqual(snapshot["weekly_simulated_count"], 2)
            self.assertEqual(
                agent.daily_cache.submitted_alphas()[0]["alpha_id"],
                "submitted-1",
            )
            self.assertEqual(agent.daily_cache.simulations()[0]["alpha_id"], "today-1")
            self.assertEqual(agent.client.calls, [
                ("SUBMITTED", 20, None), ("UNSUBMITTED", 20, None),
            ])
            self.assertEqual(
                agent.alpha_feed_cache.load()["days"]["2026-09-09"]["simulations"][0]["alpha_id"],
                "today-1",
            )

    def test_remote_alpha_feed_splits_a_platform_broad_window(self):
        class BroadClient:
            def __init__(self):
                self.calls = []
                self.broad = {"SUBMITTED": True, "UNSUBMITTED": True}

            def get_all_user_alphas(self, **kwargs):
                self.calls.append(kwargs)
                status = kwargs["status"]
                if self.broad[status]:
                    self.broad[status] = False
                    raise WQBQueryTooBroadError("too broad")
                if status == "SUBMITTED":
                    return [{
                        "id": "submitted-1",
                        "status": status,
                        "dateSubmitted": "2026-09-09T08:00:00-04:00",
                    }]
                return [{
                    "id": "today-1",
                    "status": status,
                    "dateCreated": "2026-09-09T08:00:00-04:00",
                }]

        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent.__new__(Agent)
            agent.client = BroadClient()
            agent.daily_cache = DailyResearchCache(clock=lambda: _utc_timestamp(
                dt.datetime(2026, 9, 9, 12, 0)
            ))
            agent.alpha_feed_cache = WeeklyAlphaFeedCache(
                os.path.join(tmp, "weekly.json"),
                clock=lambda: _utc_timestamp(dt.datetime(2026, 9, 9, 12, 0)),
            )
            agent.alpha_feed_workflow = AlphaFeedWorkflow(
                alpha_reader=agent.client.get_all_user_alphas,
                daily_cache=agent.daily_cache,
                weekly_cache=agent.alpha_feed_cache,
            )

            snapshot = agent.refresh_remote_alpha_feed(limit=100)

            self.assertEqual(snapshot["today_simulated_count"], 1)
            self.assertEqual(len(agent.client.calls), 6)
            self.assertTrue(all(call["max_results"] == 1000 for call in agent.client.calls))

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
        self.assertEqual(report["blocked_reasons"]["PARENT_INCREMENTAL_EVIDENCE_INSUFFICIENT"], 1)


class TestFactoryBatchContract(unittest.TestCase):
    @staticmethod
    def _diversity_proposal(expression, *, concept="fundamental", measurement="level",
                            behavior="slow_moving", template_family="persistent_level",
                            dataset="fundamental6", lineage_id=None, layer="exploration",
                            relationship_type=None):
        traits = {
            "concept": concept, "measurement": measurement, "behavior": behavior,
            "status": "KNOWN" if concept != "unknown" else "UNKNOWN",
        }
        item = {
            "expression": expression,
            "template_family": template_family,
            "research_layer": layer,
            "field_analysis": {"field": {"semantic_traits": traits}},
            "field_refs": [{"id": "field", "dataset": dataset}],
            "datasets": [dataset],
        }
        if lineage_id is not None:
            item["lineage_id"] = lineage_id
        if relationship_type is not None:
            item["relationship_audit"] = {"relationship_type": relationship_type}
        return item

    def test_semantic_key_ignores_field_id_and_uses_derived_traits(self):
        first = self._diversity_proposal("rank(field_a)")
        second = self._diversity_proposal("rank(field_b)")
        self.assertEqual(semantic_mechanism_key(first), semantic_mechanism_key(second))
        self.assertNotIn("field_a", semantic_mechanism_key(first))

    def test_diversity_audit_separates_expression_structure_and_semantics(self):
        proposals = [
            self._diversity_proposal(f"rank(field_{i})", dataset=f"d{i}")
            for i in range(10)
        ]
        stats = diversity_audit(proposals)
        self.assertEqual(stats["expression"]["unique_count"], 10)
        self.assertEqual(stats["structure"]["unique_family_count"], 1)
        self.assertEqual(stats["semantic"]["known_mechanism_count"], 1)
        self.assertEqual(stats["datasets"]["unique_count"], 10)

    def test_same_structure_different_concepts_increase_semantic_only(self):
        proposals = [
            self._diversity_proposal("persistent_level(a)", concept="analyst_revision",
                                     measurement="change", behavior="event_driven"),
            self._diversity_proposal("persistent_level(b)", concept="liquidity",
                                     measurement="level", behavior="signed"),
        ]
        stats = diversity_audit(proposals)
        self.assertEqual(stats["structure"]["unique_family_count"], 1)
        self.assertEqual(stats["semantic"]["known_mechanism_count"], 2)

    def test_different_structures_same_mechanism_increase_structure_only(self):
        proposals = [
            self._diversity_proposal("rank(a)", template_family="rank_level"),
            self._diversity_proposal("zscore(b)", template_family="zscore_level"),
        ]
        stats = diversity_audit(proposals)
        self.assertEqual(stats["structure"]["unique_family_count"], 2)
        self.assertEqual(stats["semantic"]["known_mechanism_count"], 1)

    def test_unknown_semantics_and_child_count_do_not_create_diversity(self):
        proposals = [
            self._diversity_proposal(f"rank(unknown_{i})", concept="unknown",
                                     dataset=f"unknown_d{i}", lineage_id="parent-a")
            for i in range(20)
        ]
        stats = diversity_audit(proposals)
        self.assertEqual(stats["semantic"]["known_mechanism_count"], 0)
        self.assertEqual(stats["semantic"]["unknown_mechanism_count"], 20)
        self.assertEqual(stats["lineages"]["unique_independent_count"], 1)
        self.assertEqual(stats["lineages"]["unknown_count"], 0)

    def test_batch_stats_contains_diversity_audit_and_layer_counts(self):
        proposals = [
            self._diversity_proposal("rank(a)", layer="optimization", lineage_id="p"),
            self._diversity_proposal("rank(b)", layer="exploration", lineage_id="e"),
        ]
        stats = factory_batch_stats(proposals)
        self.assertEqual(stats["diversity_layers"]["optimization"]["count"], 1)
        self.assertEqual(stats["diversity_layers"]["exploration"]["mechanism_count"], 1)

    def test_route_ignores_expression_only_change_but_accepts_semantic_or_relationship_change(self):
        base = {
            "candidate_expression_fingerprints": ["a"],
            "relationship_fingerprints": ["r"],
            "semantic_mechanism_fingerprints": ["fundamental:level:persistent_level"],
            "structural_family_fingerprints": ["persistent_level"],
            "dataset_route": ["d1"],
        }
        expression_only = dict(base, candidate_expression_fingerprints=["b"])
        decision = AIFactoryRunner.route_decision(
            base, expression_only, route_attempt=0, no_gain_attempts=1,
            max_no_gain_attempts=2,
        )
        self.assertFalse(decision["information_gain"])
        self.assertEqual(decision["change_type"], "candidate_change_only")
        semantic_change = dict(expression_only,
                                semantic_mechanism_fingerprints=["liquidity:level:rank_level"])
        decision = AIFactoryRunner.route_decision(
            base, semantic_change, route_attempt=0, no_gain_attempts=1,
            max_no_gain_attempts=2,
        )
        self.assertTrue(decision["information_gain"])
        self.assertIn("semantic_change", decision["information_changes"])

    def test_route_accepts_new_relationship_family_as_information_gain(self):
        previous = {
            "semantic_mechanism_fingerprints": ["fundamental:level:slow_moving"],
            "relationship_fingerprints": ["pair:co_movement"],
            "dataset_route": ["d1", "d2"],
        }
        current = dict(previous, relationship_fingerprints=["pair:relative_spread"])
        decision = AIFactoryRunner.route_decision(
            previous, current, route_attempt=1, no_gain_attempts=1,
        )
        self.assertTrue(decision["information_gain"])
        self.assertEqual(decision["change_type"], "research_information_change")

    def test_diversity_audit_is_deterministic_for_fixed_input(self):
        proposals = [
            self._diversity_proposal("rank(b)", dataset="d2", lineage_id="l2"),
            self._diversity_proposal("rank(a)", dataset="d1", lineage_id="l1"),
        ]
        self.assertEqual(diversity_audit(proposals), diversity_audit(list(proposals)))

    def test_budget_selection_interleaves_mechanisms_after_hard_gates(self):
        candidates = [
            self._diversity_proposal(f"rank(a{i})", dataset="d1")
            for i in range(8)
        ] + [
            self._diversity_proposal("rank(b)", concept="liquidity",
                                     behavior="signed", dataset="d2"),
            self._diversity_proposal("rank(c)", concept="analyst_revision",
                                     measurement="change", behavior="event_driven",
                                     dataset="d3"),
        ]
        selected, audit = select_budget_candidates([], candidates, target=10)
        keys = [semantic_mechanism_key(item) for item in selected]
        self.assertGreaterEqual(len(set(keys[:3])), 3)
        self.assertEqual(audit["selected_count"], 10)
        self.assertEqual(audit["priority_counts"]["normal"], 10)

    def test_same_parent_optimization_children_are_interleaved_by_lineage(self):
        optimization = [
            self._diversity_proposal(f"rank(child_a{i})", lineage_id="parent-a",
                                     layer="optimization")
            for i in range(4)
        ] + [
            self._diversity_proposal("rank(child_b)", lineage_id="parent-b",
                                     layer="optimization"),
            self._diversity_proposal("rank(child_c)", lineage_id="parent-c",
                                     layer="optimization"),
        ]
        selected, audit = select_budget_candidates(
            optimization, [], target=4, optimization_cap=4,
        )
        self.assertEqual(audit["optimization"]["selected"], 4)
        self.assertGreaterEqual(len({item["lineage_id"] for item in selected}), 3)

    def test_question_and_outcome_context_drive_ordinal_priority(self):
        context = {
            "unresolved_questions": ["does normalization preserve the effect?"],
            "next_discriminating_questions": [],
        }
        high = self._diversity_proposal("rank(high)")
        high["experiment_question"] = "Does normalization preserve the effect?"
        inconclusive = self._diversity_proposal("rank(inconclusive)")
        inconclusive["hypothesis_outcome"] = "INCONCLUSIVE"
        supported = self._diversity_proposal("rank(supported)")
        supported.update({"hypothesis_outcome": "SUPPORTED",
                          "confirmation_status": "INDEPENDENT_CONFIRMED"})
        self.assertEqual(derive_budget_priority(high, context=context)["bucket"], "HIGH")
        self.assertEqual(derive_budget_priority(inconclusive, context=context)["bucket"], "HIGH")
        self.assertEqual(derive_budget_priority(supported, context=context)["bucket"], "LOW")

    def test_unknown_semantics_cannot_receive_novelty_priority(self):
        unknown = self._diversity_proposal("rank(unknown)", concept="unknown")
        unknown["semantic_status"] = "UNKNOWN"
        unknown["semantic_novelty"] = True
        priority = derive_budget_priority(unknown, context={})
        self.assertEqual(priority["bucket"], "LOW")
        self.assertIn("UNKNOWN", priority["priority_reason"])

    def test_explicit_unknown_candidates_are_not_selected_to_fill_budget(self):
        unknown = self._diversity_proposal("rank(unknown)", concept="fundamental")
        unknown["semantic_status"] = "UNKNOWN"
        selected, audit = select_budget_candidates([], [unknown], target=1)
        self.assertEqual(selected, [])
        self.assertEqual(audit["shortage_reason"], "SEMANTIC_GATE_SCARCITY")
        self.assertEqual(audit["unknown_rejected"], 1)

    def test_historical_exhaustion_is_mechanism_family_exhausted(self):
        factory = AlphaFactory()
        fields = [
            {"id": "put_iv", "dataset": "pv1", "type": "MATRIX",
             "description": "put option implied volatility", "frequency": "daily",
             "category": "options", "semantic_status": "KNOWN"},
            {"id": "call_iv", "dataset": "option8", "type": "MATRIX",
             "description": "call option implied volatility", "frequency": "daily",
             "category": "options", "semantic_status": "KNOWN"},
        ]
        baseline = factory.assess_feasibility(
            {"id": "probe", "datasets": ["pv1", "option8"]}, fields, {},
            excluded_expressions=[],
        )
        probe = factory.assess_feasibility(
            {"id": "probe", "datasets": ["pv1", "option8"]}, fields, {},
            excluded_expressions=baseline["candidate_expression_fingerprints"],
        )
        self.assertEqual(probe["failure_taxonomy"], "MECHANISM_FAMILY_EXHAUSTED")

    def test_route_decision_stops_after_bounded_no_gain(self):
        decision = AIFactoryRunner.route_decision(
            {"failure_taxonomy": "CROSS_DATASET_FEASIBILITY_ZERO",
             "candidate_expression_fingerprints": ["a"],
             "relationship_fingerprints": ["r"],
             "mechanism_family": "relationship",
             "dataset_route": ["d1", "d2"]},
            {"failure_taxonomy": "CROSS_DATASET_FEASIBILITY_ZERO",
             "candidate_expression_fingerprints": ["a"],
             "relationship_fingerprints": ["r"],
             "mechanism_family": "relationship",
             "dataset_route": ["d1", "d2"]},
            route_attempt=2, no_gain_attempts=1, max_route_attempts=3,
            max_no_gain_attempts=1,
        )
        self.assertFalse(decision["information_gain"])
        self.assertEqual(decision["action"], "STOP")
        self.assertEqual(decision["reason"], "NO_INFORMATION_GAIN")
    def test_factory_stats_retains_feasibility_probe_without_result_payload(self):
        stats = factory_batch_stats([], {
            "probe_id": "p1",
            "failure_taxonomy": "RELATIONSHIP_REVIEW",
            "batch_gate": {"feasible": False},
        })

        self.assertEqual(
            stats["feasibility_probe"]["failure_taxonomy"],
            "RELATIONSHIP_REVIEW",
        )
        self.assertNotIn("metrics", stats["feasibility_probe"])

    def test_feasibility_probe_exposes_separate_semantic_and_structural_fingerprints(self):
        fields = [
            {"id": "eps_revision", "dataset": "analyst4", "type": "MATRIX",
             "description": "analyst EPS estimate revision", "frequency": "daily",
             "category": "analyst", "semantic_status": "KNOWN"},
            {"id": "book_value", "dataset": "fundamental6", "type": "MATRIX",
             "description": "fundamental book value", "frequency": "quarterly",
             "category": "fundamental", "semantic_status": "KNOWN"},
        ]
        probe = AlphaFactory().assess_feasibility(
            {"id": "fingerprints"}, fields, {}, max_combinations=32,
        )
        self.assertIn("semantic_mechanism_fingerprints", probe)
        self.assertIn("structural_family_fingerprints", probe)
        self.assertIn("field_concept_fingerprints", probe)

    def test_feasibility_probe_reports_bounded_cross_dataset_diagnosis(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference

        reference = _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )
        fields = [
            {"id": "put_iv", "dataset": "pv1", "type": "MATRIX",
             "description": "put option implied volatility", "frequency": "daily",
             "category": "options", "semantic_status": "KNOWN"},
            {"id": "call_iv", "dataset": "option8", "type": "MATRIX",
             "description": "call option implied volatility", "frequency": "daily",
             "category": "options", "semantic_status": "KNOWN"},
        ]
        probe = AlphaFactory().assess_feasibility(
            {"id": "probe", "datasets": ["pv1", "option8"]},
            fields,
            reference,
            excluded_expressions=[],
        )

        self.assertEqual(probe["probe_id"], "probe")
        self.assertEqual(probe["explicit_frequency_count"], 2)
        self.assertEqual(probe["inferred_frequency_count"], 0)
        self.assertGreaterEqual(probe["pair_examined"], 1)
        self.assertGreaterEqual(probe["relationship_allow"], 1)
        self.assertGreaterEqual(probe["novel_cross_dataset_relationship_count"], 1)
        self.assertTrue(probe["batch_gate"]["feasible"])
        self.assertIn("failure_taxonomy", probe)
    def _proposal(self, index, origin="factory"):
        return {
            "expression": f"rank(field_{index})",
            "proposal_origin": origin,
            "fields": [f"field_{index}"],
        }

    def _operator_reference(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference

        return _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )

    @staticmethod
    def _semantic_field(field_id, description, *, dataset="research1",
                        frequency="daily", category=None):
        return {
            "id": field_id,
            "name": description,
            "description": description,
            "dataset": dataset,
            "type": "MATRIX",
            "frequency": frequency,
            "category": category or "market",
            "coverage": 0.9,
            "semantic_status": "KNOWN",
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

    def test_factory_exploration_is_seeded_and_marked_as_signal_discovery(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference

        reference = _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )
        fields = [
            {
                "id": f"field_{index}", "description": f"verified field {index}",
                "type": "MATRIX", "semantic_status": "KNOWN",
                "dataset": "fundamental6",
            }
            for index in range(30)
        ]
        hypothesis = {"id": "factory-seeded", "datasets": ["fundamental6"]}
        first = AlphaFactory().generate_factory_batch(
            hypothesis, fields, reference, target=100, seed="round-a"
        )
        repeat = AlphaFactory().generate_factory_batch(
            hypothesis, fields, reference, target=100, seed="round-a"
        )
        other = AlphaFactory().generate_factory_batch(
            hypothesis, fields, reference, target=100, seed="round-b"
        )
        self.assertEqual(
            [item["expression"] for item in first],
            [item["expression"] for item in repeat],
        )
        self.assertNotEqual(
            [item["expression"] for item in first[:8]],
            [item["expression"] for item in other[:8]],
        )
        self.assertTrue(all(item["research_role"] == "EXPLORE" for item in first))
        self.assertTrue(all(item["experiment_stage"] == "BASELINE" for item in first))
        self.assertTrue(
            all(item["research_layer"] == "exploration" for item in first)
        )
        self.assertTrue(
            all(item["exploration_objective"] == "signal_discovery" for item in first)
        )

    def test_analyst_revision_traits_prioritize_update_mechanisms(self):
        factory = AlphaFactory()
        profile = {
            "id": "eps_revision",
            "name": "Analyst EPS estimate revision",
            "description": "analyst consensus EPS estimate revision",
            "dataset": "analyst4",
            "type": "MATRIX",
            "frequency": "daily",
            "category": "analyst",
            "coverage": 0.95,
            "semantic_status": "KNOWN",
        }

        traits = factory.derive_field_semantic_traits(profile)
        self.assertEqual(traits["concept"], "analyst_revision")
        self.assertEqual(traits["measurement"], "change")
        self.assertEqual(traits["update_style"], "event_driven")
        self.assertEqual(traits["frequency"], "daily")
        self.assertEqual(traits["sign_semantics"], "signed_change")

        ranked = factory.rank_compatible_templates(profile)
        self.assertTrue({
            "change", "persistent_level", "innovation_surprise",
            "delayed_confirmation", "accumulated_change", "quality_change",
        }.issuperset(item["template"].family for item in ranked[:4]))

        proposals = factory.generate_factory_batch(
            {"id": "revision-semantics"}, [profile],
            self._operator_reference(), target=4, seed="revision-semantics",
        )
        families = {item["template_family"] for item in proposals}
        self.assertTrue(
            families.intersection({
                "quality_change", "persistent_level", "change",
                "innovation_surprise", "delayed_confirmation",
            })
        )
        self.assertNotIn("data_quality_penalty", {
            item["template_id"] for item in proposals
        })
        mechanism = proposals[0]["field_hypothesis_basis"]["eps_revision"]["mechanism"]
        self.assertIn("analyst_revision", mechanism)
        self.assertNotEqual(mechanism, proposals[0]["rationale"])

    def test_analyst_category_fallback_does_not_invent_revision(self):
        factory = AlphaFactory()
        estimate = {
            "id": "eps_estimate",
            "name": "Analyst EPS estimate",
            "description": "analyst consensus EPS estimate",
            "dataset": "analyst4",
            "type": "MATRIX",
            "category": "analyst",
            "semantic_status": "KNOWN",
        }
        target_price = {
            "id": "target_price",
            "name": "Analyst target price",
            "description": "consensus analyst target price",
            "dataset": "analyst4",
            "type": "MATRIX",
            "category": "analyst",
            "semantic_status": "KNOWN",
        }
        broad = {
            "id": "analyst_misc",
            "name": "Analyst data",
            "description": "analyst data point",
            "dataset": "analyst4",
            "type": "MATRIX",
            "category": "analyst",
            "semantic_status": "KNOWN",
        }

        estimate_traits = factory.derive_field_semantic_traits(estimate)
        target_traits = factory.derive_field_semantic_traits(target_price)
        broad_traits = factory.derive_field_semantic_traits(broad)
        self.assertNotEqual(estimate_traits["concept"], "analyst_revision")
        self.assertEqual(estimate_traits["measurement"], "level")
        self.assertNotEqual(target_traits["concept"], "analyst_revision")
        self.assertEqual(target_traits["measurement"], "level")
        self.assertEqual(broad_traits["concept"], "analyst")
        self.assertEqual(broad_traits["semantic_admission"], "REVIEW")
        self.assertNotEqual(broad_traits["confidence"], "HIGH")

        category_only = {
            "id": "misc_field",
            "name": "misc field",
            "description": "generic numeric field",
            "dataset": "fundamental6",
            "type": "MATRIX",
            "category": "fundamental",
            "semantic_status": "KNOWN",
        }
        category_traits = factory.derive_field_semantic_traits(category_only)
        self.assertEqual(category_traits["concept"], "fundamental")
        self.assertEqual(category_traits["semantic_admission"], "REVIEW")
        self.assertNotEqual(category_traits["confidence"], "HIGH")

    def test_slow_moving_fundamental_is_not_event_triggered_by_default(self):
        profile = {
            "id": "total_assets",
            "name": "Total assets",
            "description": "quarterly total assets on the balance sheet",
            "dataset": "fundamental6",
            "type": "MATRIX",
            "frequency": "quarterly",
            "category": "fundamental",
            "coverage": 0.98,
            "semantic_status": "KNOWN",
        }
        proposals = AlphaFactory().generate_factory_batch(
            {"id": "fundamental-semantics"}, [profile],
            self._operator_reference(), target=8, seed="fundamental-semantics",
        )
        traits = AlphaFactory().derive_field_semantic_traits(profile)
        self.assertEqual(traits["frequency"], "quarterly")
        self.assertEqual(traits["sign_semantics"], "nonnegative_level")
        self.assertEqual(traits["behavior"], "slow_moving")
        self.assertTrue(proposals)
        self.assertNotIn(
            "event_trigger",
            {item["template_family"] for item in proposals},
        )

    def test_option_volatility_prefers_risk_regime_or_relative_families(self):
        profile = {
            "id": "implied_vol",
            "name": "Option implied volatility",
            "description": "option implied volatility",
            "dataset": "option8",
            "type": "MATRIX",
            "frequency": "daily",
            "category": "options",
            "coverage": 0.91,
            "semantic_status": "KNOWN",
        }
        proposals = AlphaFactory().generate_factory_batch(
            {"id": "option-semantics"}, [profile],
            self._operator_reference(), target=4, seed="option-semantics",
        )
        traits = AlphaFactory().derive_field_semantic_traits(profile)
        self.assertEqual(traits["sign_semantics"], "nonnegative_level")
        self.assertTrue(proposals)
        self.assertTrue({
            "risk_adjusted_reversal", "downside_risk", "distribution_regime",
            "relative_spread_change", "relative_ratio", "relative_covariance",
            "relative_correlation",
        }.intersection(item["template_family"] for item in proposals))
        self.assertNotIn("data_quality_penalty", {
            item["template_id"] for item in proposals
        })

    def test_option_activity_and_skew_are_not_collapsed_into_plain_volatility(self):
        factory = AlphaFactory()
        open_interest = {
            "id": "open_interest",
            "name": "Option open interest",
            "description": "option open interest",
            "dataset": "option8",
            "type": "MATRIX",
            "category": "options",
            "semantic_status": "KNOWN",
        }
        put_call_skew = {
            "id": "put_call_skew",
            "name": "Put-call skew",
            "description": "put-call implied volatility skew",
            "dataset": "option8",
            "type": "MATRIX",
            "category": "options",
            "semantic_status": "KNOWN",
        }
        open_traits = factory.derive_field_semantic_traits(open_interest)
        skew_traits = factory.derive_field_semantic_traits(put_call_skew)
        self.assertEqual(open_traits["concept"], "liquidity")
        self.assertNotEqual(open_traits["concept"], "volatility")
        self.assertEqual(skew_traits["concept"], "option_relative")
        self.assertEqual(skew_traits["measurement"], "dispersion")
        self.assertNotEqual(skew_traits["concept"], "volatility")

        generic_skew = {
            "id": "generic_skew",
            "name": "Generic skew",
            "description": "generic distribution skew",
            "dataset": "research1",
            "type": "MATRIX",
            "category": "fundamental",
            "semantic_status": "KNOWN",
        }
        generic_traits = factory.derive_field_semantic_traits(generic_skew)
        self.assertNotEqual(generic_traits["concept"], "option_relative")

    def test_pair_relationship_gate_rejects_social_count_and_total_assets(self):
        fields = [
            {
                "id": "social_count",
                "name": "Social mention count",
                "description": "daily social media mention count",
                "dataset": "news18",
                "type": "MATRIX",
                "frequency": "daily",
                "category": "social",
                "coverage": 0.8,
                "semantic_status": "KNOWN",
            },
            {
                "id": "total_assets",
                "name": "Total assets",
                "description": "quarterly total assets on the balance sheet",
                "dataset": "fundamental6",
                "type": "MATRIX",
                "frequency": "quarterly",
                "category": "fundamental",
                "coverage": 0.98,
                "semantic_status": "KNOWN",
            },
        ]
        proposals = AlphaFactory().assemble_proposals(
            {"id": "invalid-pair", "template_ids": [
                "relative_ratio_extreme", "relative_spread_change",
            ]},
            fields, self._operator_reference(), max_candidates=2,
        )
        self.assertEqual(proposals, [])

    def test_relationship_decision_reports_symmetric_slots_and_frequency(self):
        factory = AlphaFactory()
        put_iv = self._semantic_field(
            "put_iv", "put option implied volatility", category="options"
        )
        call_iv = self._semantic_field(
            "call_iv", "call option implied volatility", category="options"
        )
        decision = factory._relationship_gate(
            [put_iv, call_iv], factory.registry.get("relative_spread_change")
        )
        self.assertEqual(decision["admission"], "ALLOW")
        self.assertEqual(decision["relationship_type"], "option_pair")
        self.assertTrue(decision["symmetric"])
        self.assertEqual(
            decision["preferred_slot_assignment"], {"p": "EITHER", "s": "EITHER"}
        )
        self.assertEqual(
            decision["frequency_compatibility"]["status"], "COMPATIBLE"
        )
        self.assertTrue(any("frequency" in reason for reason in decision["reasons"]))

    def test_ratio_requires_directional_earnings_over_assets_assignment(self):
        factory = AlphaFactory()
        earnings = self._semantic_field(
            "earnings", "quarterly earnings per share",
            dataset="fundamental6", frequency="quarterly", category="fundamental",
        )
        assets = self._semantic_field(
            "assets", "quarterly total assets balance sheet",
            dataset="fundamental6", frequency="quarterly", category="fundamental",
        )
        template = factory.registry.get("relative_ratio_extreme")
        forward = factory._relationship_gate([earnings, assets], template)
        reverse = factory._relationship_gate([assets, earnings], template)
        self.assertEqual(forward["admission"], "ALLOW")
        self.assertEqual(
            forward["preferred_slot_assignment"],
            {"p": "numerator", "s": "denominator"},
        )
        self.assertFalse(forward["symmetric"])
        self.assertNotEqual(reverse["admission"], "ALLOW")

    def test_option_pair_does_not_admit_unrelated_open_interest_and_greek(self):
        factory = AlphaFactory()
        open_interest = self._semantic_field(
            "open_interest", "option open interest", category="options"
        )
        greek = self._semantic_field(
            "iv_delta", "option implied volatility delta greek", category="options"
        )
        for template_id in (
            "relative_spread_change", "relative_ratio_extreme",
            "relative_covariance", "relative_correlation_regime",
        ):
            decision = factory._relationship_gate(
                [open_interest, greek], factory.registry.get(template_id)
            )
            self.assertNotEqual(decision["admission"], "ALLOW", template_id)

    def test_frequency_mismatch_is_incompatible_for_direct_correlation(self):
        factory = AlphaFactory()
        daily = self._semantic_field("daily_close", "daily close price")
        annual = self._semantic_field(
            "annual_close", "annual close price", frequency="annual"
        )
        decision = factory._relationship_gate(
            [daily, annual], factory.registry.get("relative_correlation_regime")
        )
        self.assertEqual(
            decision["frequency_compatibility"]["status"], "INCOMPATIBLE"
        )
        self.assertEqual(decision["admission"], "REJECT")

    def test_frequency_review_pair_is_not_auto_generated(self):
        fields = [
            self._semantic_field("daily_close", "daily close price", dataset="pv1"),
            self._semantic_field(
                "weekly_close", "weekly close price", dataset="pv13",
                frequency="weekly",
            ),
        ]
        factory = AlphaFactory()
        decision = factory._relationship_gate(
            fields, factory.registry.get("relative_spread_change")
        )
        self.assertEqual(decision["frequency_compatibility"]["status"], "REVIEW")
        self.assertEqual(decision["admission"], "REVIEW")
        self.assertEqual(
            factory.generate(
                {"template_ids": ["relative_spread_change"]}, fields, count=1
            ),
            [],
        )
        self.assertEqual(
            factory.assemble_proposals(
                {"template_ids": ["relative_spread_change"]},
                fields, self._operator_reference(), max_candidates=1,
            ),
            [],
        )
        self.assertEqual(
            factory.generate(
                {"template_family": "relative_spread_change"}, fields, count=1
            ),
            [],
        )
        batch = factory.generate_factory_batch(
            {"id": "frequency-review"}, fields, self._operator_reference(),
            target=8, seed="frequency-review",
        )
        self.assertFalse(any(len(item.get("fields", [])) > 1 for item in batch))

    def test_analyst_triple_requires_one_confirmation_mechanism(self):
        fields = [
            self._semantic_field(
                "revision", "analyst EPS estimate revision", category="analyst"
            ),
            self._semantic_field(
                "dispersion", "analyst EPS estimate dispersion", category="analyst"
            ),
            self._semantic_field(
                "recommendation", "analyst recommendation change", category="analyst"
            ),
        ]
        decision = AlphaFactory()._relationship_gate(
            fields, AlphaFactory().registry.get("generic_triple_confirmation")
        )
        self.assertEqual(decision["admission"], "ALLOW")
        self.assertEqual(
            decision["confirmation_mechanism"], "analyst_expectation_update"
        )

    def test_triple_with_two_unified_pair_edges_is_not_confirmation(self):
        fields = [
            self._semantic_field("price", "daily close price"),
            self._semantic_field(
                "iv", "daily option implied volatility", category="options"
            ),
            self._semantic_field(
                "open_interest", "daily option open interest", category="options"
            ),
        ]
        decision = AlphaFactory()._relationship_gate(
            fields, AlphaFactory().registry.get("generic_triple_confirmation")
        )
        self.assertNotEqual(decision["admission"], "ALLOW")

    def test_same_concept_with_level_change_mismatch_is_not_spread(self):
        factory = AlphaFactory()
        level = self._semantic_field("price_level", "daily close price")
        change = self._semantic_field("price_return", "daily close price return")
        decision = factory._relationship_gate(
            [level, change], factory.registry.get("relative_spread_change")
        )
        self.assertNotEqual(decision["admission"], "ALLOW")

    def test_multi_field_proposal_contains_relationship_audit_metadata(self):
        fields = [
            self._semantic_field(
                "put_iv", "put option implied volatility", dataset="option8",
                category="options",
            ),
            self._semantic_field(
                "call_iv", "call option implied volatility", dataset="option8",
                category="options",
            ),
        ]
        proposals = AlphaFactory().assemble_proposals(
            {"template_ids": ["relative_spread_change"]},
            fields, self._operator_reference(), max_candidates=1,
        )
        self.assertEqual(len(proposals), 1)
        audit = proposals[0]["relationship_audit"]
        self.assertEqual(audit["relationship_type"], "option_pair")
        self.assertEqual(audit["relationship_admission"], "ALLOW")
        self.assertEqual(audit["slot_assignment"], {
            "p": "put_iv", "s": "call_iv",
        })
        self.assertEqual(audit["frequency_compatibility"]["status"], "COMPATIBLE")

    def test_factory_drops_review_multi_field_optimized_prefix(self):
        optimized = [{
            "expression": "rank(a - b)",
            "fields": ["a", "b"],
            "proposal_origin": "agent_optimizer",
            "relationship_audit": {
                "relationship_admission": "REVIEW",
            },
        }]
        batch = AlphaFactory().generate_factory_batch(
            {"id": "optimized-review"}, [], {}, target=1, optimized=optimized,
        )
        self.assertEqual(batch, [])

    def test_unknown_semantics_are_review_only_and_do_not_claim_template_mechanism(self):
        profile = {
            "id": "mystery_signal",
            "name": "Mystery signal",
            "description": "verified proprietary signal",
            "dataset": "model16",
            "type": "MATRIX",
            "frequency": "daily",
            "category": "model",
            "coverage": 0.9,
            "semantic_status": "KNOWN",
        }
        proposals = AlphaFactory().assemble_proposals(
            {"id": "unknown-semantics", "template_ids": [
                "event_triggered_signal",
            ]},
            [profile], self._operator_reference(), max_candidates=1,
        )
        self.assertEqual(proposals, [])

    def test_derived_unknown_semantics_never_admit_a_strong_economic_mechanism(self):
        profile = {
            "id": "opaque_signal",
            "name": "Opaque signal",
            "description": "verified proprietary signal",
            "dataset": "model16",
            "type": "MATRIX",
            "frequency": "daily",
            "category": "model",
            "coverage": 0.9,
            "semantic_status": "KNOWN",
        }
        factory = AlphaFactory()
        ranked = factory.rank_compatible_templates(profile)
        self.assertTrue(ranked)
        self.assertTrue(all(item["admission"] != "ALLOW" for item in ranked))
        candidate = factory.generate(
            {"template_ids": ["persistent_level"]}, [profile], count=1
        )[0]
        self.assertIn("UNKNOWN", candidate["economic_mechanism"])
        self.assertNotIn("平滑后的相对高低", candidate["economic_mechanism"])

    def test_factory_coverage_forms_have_identical_sparse_semantics(self):
        factory = AlphaFactory()
        base = {
            "id": "opaque_signal",
            "name": "Opaque signal",
            "description": "verified proprietary signal",
            "dataset": "model16",
            "type": "MATRIX",
            "semantic_status": "KNOWN",
        }
        fractional = factory.derive_field_semantic_traits(
            {**base, "coverage": 0.95}
        )
        percentage = factory.derive_field_semantic_traits(
            {**base, "coveragePercentage": 95}
        )
        invalid = factory.derive_field_semantic_traits(
            {**base, "coverage": float("nan")}
        )
        self.assertEqual(fractional["behavior"], percentage["behavior"])
        self.assertEqual(fractional["semantic_admission"], "UNKNOWN")
        self.assertEqual(percentage["semantic_admission"], "UNKNOWN")
        self.assertEqual(invalid["semantic_admission"], "UNKNOWN")

    def test_semantic_matching_is_deterministic_for_a_fixed_seed(self):
        fields = [
            {
                "id": "revision_a", "name": "EPS revision",
                "description": "analyst EPS estimate revision", "dataset": "analyst4",
                "type": "MATRIX", "frequency": "daily", "category": "analyst",
                "coverage": 0.9, "semantic_status": "KNOWN",
            },
            {
                "id": "iv_a", "name": "Implied volatility",
                "description": "option implied volatility", "dataset": "option8",
                "type": "MATRIX", "frequency": "daily", "category": "options",
                "coverage": 0.9, "semantic_status": "KNOWN",
            },
        ]
        factory = AlphaFactory()
        first = factory.generate_factory_batch(
            {"id": "semantic-seed"}, fields, self._operator_reference(),
            target=8, seed="fixed-seed",
        )
        repeat = factory.generate_factory_batch(
            {"id": "semantic-seed"}, fields, self._operator_reference(),
            target=8, seed="fixed-seed",
        )
        self.assertEqual(
            [(item["expression"], item["template_id"]) for item in first],
            [(item["expression"], item["template_id"]) for item in repeat],
        )

    def test_code_screen_precedes_agent_economic_gate(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference

        reference = _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )
        complete_parent = {
            "status": "DONE",
            "expression": "rank(field)",
            "fields_used": ["field"],
            "datasets": ["fundamental6"],
            "metrics": {"sharpe": 1.1, "fitness": 0.8, "turnover": 0.2},
            "health": {"ok": True},
            "field_understanding": {"field": "已核验字段"},
            "field_analysis": {"field": {"data_type": "MATRIX"}},
            "field_source": {"kind": "brain_api", "snapshot_date": "2026-09-08"},
            "field_hypothesis_basis": {"field": {"mechanism": "质量变化"}},
        }
        weak_parent = dict(complete_parent, metrics={"sharpe": 0.1, "fitness": 0.1, "turnover": 0.2})
        screened = AlphaFactory().screen_optimization_parents(
            [weak_parent, complete_parent], min_sharpe=0.9, min_fitness=0.6
        )
        self.assertEqual([item["expression"] for item in screened], ["rank(field)"])
        self.assertEqual(
            AlphaFactory().screen_optimization_parents(
                [dict(complete_parent, metrics={
                    "sharpe": float("nan"), "fitness": 0.8, "turnover": 0.2,
                })]
            ),
            [],
        )

        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(object(), {"simulation": {}, "agent": {"state_dir": tmp}})
            self.assertEqual(
                agent.generate_optimized_proposals(screened, max_candidates=4), []
            )
        self.assertEqual(
            AlphaFactory().optimize_signal_proposals(
                screened, reference, max_candidates=4
            ), []
        )

    def test_cloud_alpha_metadata_prioritizes_matching_evidence_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(object(), {"simulation": {}, "agent": {"state_dir": tmp}})
            cloud_parent = Experiment(1, "h", "rank(cloud_field)", {}, ["cloud_field"])
            cloud_parent.datasets = ["fundamental6"]
            cloud_parent.status = "DONE"
            cloud_parent.alpha_id = "cloud-alpha"
            cloud_parent.metrics = {"sharpe": 1.0}
            cloud_parent.metrics["checks"] = [{"name": "SELF_CORRELATION", "status": "UNKNOWN"}]
            cloud_parent.field_understanding = {"cloud_field": "verified"}
            cloud_parent.field_analysis = {"cloud_field": {"data_type": "MATRIX"}}
            cloud_parent.field_source = {"kind": "brain_api"}
            cloud_parent.field_hypothesis_basis = {"cloud_field": {"mechanism": "变化"}}
            cloud_parent.economic_mechanism = "信息变化导致相对定价差异"
            cloud_parent.hypothesis_id = "h-cloud"
            current_parent = Experiment(2, "h", "rank(current_field)", {}, ["current_field"])
            current_parent.datasets = ["fundamental6"]
            current_parent.status = "DONE"
            current_parent.alpha_id = "current-alpha"
            current_parent.metrics = {"sharpe": 1.0}
            current_parent.metrics["checks"] = [{"name": "SELF_CORRELATION", "status": "UNKNOWN"}]
            current_parent.field_understanding = {"current_field": "verified"}
            current_parent.field_analysis = {"current_field": {"data_type": "MATRIX"}}
            current_parent.field_source = {"kind": "brain_api"}
            current_parent.field_hypothesis_basis = {"current_field": {"mechanism": "变化"}}
            current_parent.economic_mechanism = "信息变化导致相对定价差异"
            current_parent.hypothesis_id = "h-current"
            agent.trajectory.experiments = [current_parent, cloud_parent]
            today = agent.alpha_feed_cache.local_date
            agent.alpha_feed_cache.refresh({
                today: {
                    "simulations": [{"alpha_id": "cloud-alpha", "status": "SIMULATED"}],
                    "submitted_alphas": [],
                }
            })
            records = agent.optimizable_signal_records()

        self.assertEqual(
            [item["alpha_id"] for item in records], ["cloud-alpha", "current-alpha"]
        )
        self.assertEqual(records[0]["optimization_source"], "cloud")
        self.assertEqual(records[1]["optimization_source"], "current_run")

    def test_factory_batch_stats_separate_layers_and_sources(self):
        stats = factory_batch_stats([
            {
                "expression": "rank(cloud_field)",
                "research_layer": "optimization",
                "optimization_source": "cloud",
            },
            {
                "expression": "rank(new_field)",
                "research_layer": "exploration",
                "exploration_objective": "signal_discovery",
            },
        ])
        self.assertEqual(stats["layer_counts"], {
            "optimization": 1, "exploration": 1, "unknown": 0,
        })
        self.assertEqual(stats["optimization_source_counts"]["cloud"], 1)
        self.assertEqual(stats["exploration_objective_counts"], {
            "signal_discovery": 1,
        })

    def test_factory_batch_prefers_cross_dataset_companions_and_reports_stats(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference

        reference = _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )
        datasets = ["pv1", "pv13", "option8"]
        fields = [
            {
                "id": f"field_{index}", "description": "daily close price",
                "type": "MATRIX", "semantic_status": "KNOWN",
                "frequency": "daily", "category": "market",
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
            {"id": "revision", "dataset": "analyst4", "type": "MATRIX",
             "description": "analyst EPS estimate revision", "frequency": "daily",
             "category": "analyst", "semantic_status": "KNOWN"},
            {"id": "dispersion", "dataset": "analyst4", "type": "MATRIX",
             "description": "analyst EPS estimate dispersion", "frequency": "daily",
             "category": "analyst", "semantic_status": "KNOWN"},
            {"id": "recommendation", "dataset": "analyst4", "type": "MATRIX",
             "description": "analyst recommendation change", "frequency": "daily",
             "category": "analyst", "semantic_status": "KNOWN"},
        ]
        candidates = AlphaFactory(registry=registry).generate(
            {"template_ids": ["generic_triple_confirmation"]}, fields, count=1
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertIn("revision", candidate["expression"])
        self.assertIn("dispersion", candidate["expression"])
        self.assertIn("recommendation", candidate["expression"])
        self.assertEqual(candidate["template_slots"]["data_field"], "revision")
        self.assertEqual(candidate["template_slots"]["s"], "dispersion")
        self.assertEqual(candidate["template_slots"]["t"], "recommendation")
        self.assertEqual(
            [(item["dataset"], item["id"]) for item in candidate["field_refs"]],
            [("analyst4", "revision"), ("analyst4", "dispersion"),
             ("analyst4", "recommendation")],
        )

    def test_assemble_connects_dual_field_template_across_datasets(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference

        reference = _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )
        fields = [
            {
                "id": "put_iv", "dataset": "pv1", "type": "MATRIX",
                "description": "put option implied volatility", "frequency": "daily",
                "category": "options", "semantic_status": "KNOWN",
            },
            {
                "id": "call_iv", "dataset": "option8", "type": "MATRIX",
                "description": "call option implied volatility", "frequency": "daily",
                "category": "options", "semantic_status": "KNOWN",
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
        self.assertEqual(proposal["fields"], ["put_iv", "call_iv"])
        self.assertEqual(proposal["datasets"], ["pv1", "option8"])
        self.assertEqual(
            [(item["dataset"], item["id"]) for item in proposal["field_refs"]],
            [("pv1", "put_iv"), ("option8", "call_iv")],
        )
        self.assertEqual(proposal["template_slots"]["p"], "put_iv")
        self.assertEqual(proposal["template_slots"]["s"], "call_iv")

    def test_assemble_connects_generic_triple_template_and_records_all_slots(self):
        root = os.path.dirname(os.path.dirname(__file__))
        from wqb_agent.proposal_contract import _operator_reference

        reference = _operator_reference(
            os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
        )
        fields = [
            {"id": "revision", "dataset": "pv1", "type": "MATRIX",
             "description": "analyst EPS estimate revision", "frequency": "daily",
             "category": "analyst", "semantic_status": "KNOWN"},
            {"id": "dispersion", "dataset": "option8", "type": "MATRIX",
             "description": "analyst EPS estimate dispersion", "frequency": "daily",
             "category": "analyst", "semantic_status": "KNOWN"},
            {"id": "recommendation", "dataset": "analyst4", "type": "MATRIX",
             "description": "analyst recommendation change", "frequency": "daily",
             "category": "analyst", "semantic_status": "KNOWN"},
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
        self.assertEqual(
            proposal["fields"], ["revision", "dispersion", "recommendation"]
        )
        self.assertEqual(
            {item["dataset"] for item in proposal["field_refs"]},
            {"pv1", "option8", "analyst4"},
        )
        self.assertEqual(proposal["template_slots"]["data_field"], "revision")
        self.assertEqual(proposal["template_slots"]["t"], "recommendation")

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


class TestTemplateLiveOperatorEvidence(unittest.TestCase):
    """2026-09-11 平台实测回归：模板不得使用 live 平台确定性拒绝的算子用法。

    证据（USA/EQUITY/TOP3000/Delay1，rounds 1-4 真实 Simulation）：
    - 三参 `normalize(x, true, 0.0)` → `Invalid number of inputs : 2,
      should be exactly 1 input(s)`；
    - 裸位置参数 `gaussian` 驱动（`quantile`/`ts_quantile`）→
      `Attempted to use unknown variable "gaussian"`；
    - `group_rank(rank(group_backfill(...)))` 嵌套 → `Invalid number of
      inputs : 3, should be exactly 2 input(s)`；
    - 双参 `winsorize(x, 4)` / `hump(x, 0.01)` → `Invalid number of inputs
      : 2, should be exactly 1 input(s)`（round_4 实测：此 region 下
      normalize/winsorize/hump 均仅 1 输入）；
    - `ts_regression(..., 20, 0)` 的 lookback=0 → `Got invalid value "0"
      for attribute "lookback"`（round_4 实测，改省略该参数）。
    rounds 1-3 的 63 项 FAILED 与 round 4 的 15 项 FAILED 全部归因于
    上述用法。修复后的 7 个模板必须只使用本平台已实证算子。
    """

    # 156 条 DONE 表达式 + 项目历史 trajectory 使用统计中已被平台接受的算子。
    # winsorize/hump：2026-09-11 平台实测双参形式被拒（exactly 1 input），
    # 单参 winsorize(x)/hump(x) 为平台明确要求的合法形式。
    # ts_regression/ts_step：平台按名接受（round_4 的拒绝发生在属性值层：
    # lookback=0 非法），省略 lookback 的 3 参形式为当前模板用法。
    LIVE_ACCEPTED_OPERATORS = {
        "rank", "winsorize", "hump", "ts_zscore", "ts_delta", "ts_rank",
        "subtract", "ts_backfill", "group_mean", "ts_regression", "ts_step",
    }
    REJECTED_SNIPPETS = (
        "gaussian", "group_rank(", "group_backfill(",
        # 2026-09-11 round_4：ts_regression 的 lookback=0 被平台拒绝
        "ts_step(1), 20, 0",
        # 2026-09-11 round_9：2 参 group_mean(X, G) 被平台拒绝（exactly 3 inputs），
        # 仅 3 参形式 group_mean(X, 1, G) 有 38 次 DONE 实证（r1-r7 group_scaled_mean）
        "group_mean(ts_backfill({p}, 20), {g}))",
    )
    REPAIRED_TEMPLATE_IDS = (
        "robust_cross_section",
        "distributional_change",
        "distribution_regime",
        "group_filled_rank",
        "turnover_controlled_change",
        "trend_residual",
    )

    def _template_by_id(self, template_id):
        from wqb_agent.alpha_factory import ECONOMIC_TEMPLATES
        for template in ECONOMIC_TEMPLATES:
            if template.template_id == template_id:
                return template
        self.fail(f"template {template_id!r} missing from ECONOMIC_TEMPLATES")

    def _concrete(self, expression):
        return (
            expression
            .replace("{p}", "cashflow_fin")
            .replace("{s}", "cashflow_op")
            .replace("{t}", "cashflow_invst")
            .replace("{g}", "subindustry")
        )

    def test_repaired_templates_use_only_live_accepted_operators(self):
        from wqb_agent.expression import analyze_expression

        for template_id in self.REPAIRED_TEMPLATE_IDS:
            expression = self._concrete(self._template_by_id(template_id).expression)
            parsed = analyze_expression(expression)
            operators = set(parsed.operators)
            rejected = operators - self.LIVE_ACCEPTED_OPERATORS
            self.assertEqual(
                rejected, set(),
                f"{template_id} uses platform-unproven operators "
                f"{sorted(rejected)}: {expression}",
            )

    def test_repaired_templates_avoid_rejected_syntax(self):
        for template_id in self.REPAIRED_TEMPLATE_IDS:
            expression = self._template_by_id(template_id).expression
            for snippet in self.REJECTED_SNIPPETS:
                self.assertNotIn(
                    snippet, expression,
                    f"{template_id} still contains live-rejected usage "
                    f"{snippet!r}: {expression}",
                )
            # 多参 normalize(x, ...) 从未在本平台实证，禁止任何参数形式。
            self.assertNotIn(
                "normalize(", expression,
                f"{template_id} uses unverified normalize: {expression}",
            )

    def _top_level_arity(self, expression, call_name):
        """各 call_name 调用的顶层实参数（深度感知，避免嵌套调用误报）。"""
        arities = []
        needle = f"{call_name}("
        idx = 0
        while True:
            start = expression.find(needle, idx)
            if start == -1:
                break
            depth = 0
            args = 1
            i = start + len(needle) - 1
            while i < len(expression):
                char = expression[i]
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        break
                elif char == "," and depth == 1:
                    args += 1
                i += 1
            arities.append(args)
            idx = start + len(needle)
        return arities

    def test_registry_wide_guard_against_rejected_drivers(self):
        from wqb_agent.alpha_factory import ECONOMIC_TEMPLATES

        for template in ECONOMIC_TEMPLATES:
            expression = template.expression
            for snippet in self.REJECTED_SNIPPETS:
                self.assertNotIn(
                    snippet, expression,
                    f"{template.template_id} reintroduced live-rejected "
                    f"usage {snippet!r}",
                )
            # 2026-09-11 平台实测：此 region 下 normalize、winsorize、hump
            # 均只接受恰好 1 个输入；多参形式一律拒绝（嵌套调用合法）。
            for call in ("normalize", "winsorize", "hump"):
                for arity in self._top_level_arity(expression, call):
                    self.assertEqual(
                        arity, 1,
                        f"{template.template_id} uses multi-arg {call} "
                        f"({arity} inputs): {expression}",
                    )
            # 2026-09-11 round_9 平台实测：此 region 下 group_mean 只接受恰好 3 个
            # 顶层输入（group_mean(X, 1, G)）；2 参形式被拒绝，3 参形式 r1-r7 共 38 次 DONE。
            for arity in self._top_level_arity(expression, "group_mean"):
                self.assertEqual(
                    arity, 3,
                    f"{template.template_id} uses non-3-arg group_mean "
                    f"({arity} inputs): {expression}",
                )


if __name__ == "__main__":
    unittest.main()
