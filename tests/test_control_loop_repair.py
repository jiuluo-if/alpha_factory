"""Phase VI 控制链修复的 offline 验收测试（无真实 Simulation、无状态写入）。"""

import dataclasses
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from scripts.refresh_self_correlation import (
    load_trajectory_rows,
    pre_correlation_selection,
)
from tests.test_agent_flow import make_agent
from tests.test_optimization_decision import (
    FakeTrajectory,
    child_decision,
    parent_record,
    validate_decision,
)
from tests.test_pre_correlation import synthetic_metrics
from wqb_agent import research_api
from wqb_agent.alpha_factory import AlphaFactory
from wqb_agent.checkpoints import CheckpointStore
from wqb_agent.factory_runner import AIFactoryRunner
from wqb_agent.optimizer_workflow import OptimizerHooks, OptimizerWorkflow
from wqb_agent.proposal_contract import (
    TARGETED_BATCH_TYPE,
    targeted_batch_state,
)
from wqb_agent.state import Experiment, Trajectory


class _Cache:
    def load(self):
        return {}


class _Factory:
    registry = None

    def screen_optimization_parents(self, parents, **kwargs):
        return list(parents)


def _child(*, stage="CHILD", decision=None, status="DONE", alpha_id=None):
    return Experiment(
        round=1,
        hypothesis_id="h1",
        expression="group_neutralize(rank(field_a), SUBINDUSTRY)",
        settings={"delay": 1},
        fields_used=["field_a"],
        datasets=["fundamental6"],
        experiment_stage=stage,
        status=status,
        alpha_id=alpha_id,
        incremental_evidence=({"decision": decision} if decision else None),
    )


def _workflow(trajectory):
    return OptimizerWorkflow(
        trajectory=trajectory,
        alpha_feed_cache=_Cache(),
        alpha_factory=_Factory(),
        quality_policy={},
        operator_reference={"operators": []},
        hooks=OptimizerHooks(
            ensure_loaded=lambda: None,
            terminal_expressions=lambda: set(),
        ),
    )


class TestGenerationBoundUsesRealChildHistory(unittest.TestCase):
    """P0-B：多代边界必须来自 canonical trajectory 的真实 CHILD 证据。"""

    def _restarted(self, path):
        trajectory = Trajectory(path=path, max_len=64, persist=True)
        trajectory.load()
        return trajectory

    def test_child_done_without_incremental_evidence_blocks_the_next_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            first = Trajectory(path=path, max_len=64, persist=True)
            first.add(_child(decision="UNAVAILABLE"))
            bound = _workflow(self._restarted(path)).optimizer_context()[
                "generation_bound"
            ]
            self.assertEqual(bound["children_generated"], 1)
            self.assertEqual(bound["children_done"], 1)
            self.assertFalse(bound["allowed"])
            self.assertEqual(bound["stop_reason"], "NO_INCREMENTAL_CHILD_EVIDENCE")

    def test_incremental_pass_allows_the_next_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            first = Trajectory(path=path, max_len=64, persist=True)
            first.add(_child(decision="PASS"))
            bound = _workflow(self._restarted(path)).optimizer_context()[
                "generation_bound"
            ]
            self.assertEqual(bound["incremental_pass"], 1)
            self.assertTrue(bound["allowed"])
            self.assertIsNone(bound["stop_reason"])

    def test_robustness_records_are_not_a_new_child_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            first = Trajectory(path=path, max_len=64, persist=True)
            first.add(_child(stage="ROBUSTNESS", decision="UNAVAILABLE"))
            bound = _workflow(self._restarted(path)).optimizer_context()[
                "generation_bound"
            ]
            self.assertEqual(bound["children_generated"], 0)
            self.assertTrue(bound["allowed"])


class _CorrelationClient:
    def __init__(self, payload):
        self._session = object()
        self.payload = payload
        self.calls = []

    def get_self_correlation(self, alpha_id, timeout_sec=20):
        self.calls.append(str(alpha_id))
        return dict(self.payload)


def _correlation_parent(alpha_id="alpha-corr"):
    return Experiment(
        round=1,
        hypothesis_id="h1",
        expression="rank(field_a)",
        settings={"delay": 1},
        fields_used=["field_a"],
        datasets=["fundamental6"],
        field_understanding={"field_a": "已核验字段"},
        field_analysis={"field_a": {"data_type": "MATRIX"}},
        field_source={"kind": "brain_api"},
        field_hypothesis_basis={"field_a": {"mechanism": "质量变化"}},
        economic_mechanism="质量变化驱动的相对定价差异",
        status="DONE",
        alpha_id=alpha_id,
        health={"ok": True},
        metrics={
            "sharpe": 1.6,
            "fitness": 1.3,
            "turnover": 0.25,
            "returns": 0.05,
            "drawdown": 0.05,
            "checks": [
                {"name": "CONCENTRATED_WEIGHT", "pass": True},
                {"name": "SELF_CORRELATION", "pass": None, "result": "PENDING"},
            ],
        },
    )


class TestResolvedCorrelationFeedsTheNextDecision(unittest.TestCase):
    """P0-C：同进程只 GET 一次，且已结算结果进入 optimizer context。"""

    def test_resolved_failure_is_reused_and_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent, _client = make_agent(tmp, rounds=1)
            parent = _correlation_parent()
            agent.trajectory.add(parent)
            agent.reflector.evidence_cache = {}
            client = _CorrelationClient({"correlation": 0.9})
            agent.client = client
            agent._refresh_self_correlation_evidence([parent])
            self.assertEqual(client.calls, ["alpha-corr"])
            agent._refresh_self_correlation_evidence([parent])
            self.assertEqual(client.calls, ["alpha-corr"])
            context = agent.optimizer_context()
            summary = context["eligible_parents"][0]
            self.assertEqual(summary["self_correlation_status"], "FAIL")
            self.assertEqual(summary["next_action"], "CONSIDER_CORRELATION_REPAIR")
            self.assertEqual(
                summary["metric_optimization_context"]["readiness"],
                "STRUCTURAL_REPAIR_REQUIRED",
            )
            self.assertFalse(
                summary["metric_optimization_context"]["pre_correlation_eligible"]
            )
            self.assertIn(
                "SELF_CORRELATION_REPAIR",
                summary["metric_optimization_context"]["opportunities"],
            )
            self.assertEqual(context["next_action"], "CONSIDER_CORRELATION_REPAIR")

    def test_resolved_pass_advances_instead_of_rechecking(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent, _client = make_agent(tmp, rounds=1)
            parent = _correlation_parent()
            agent.trajectory.add(parent)
            agent.reflector.evidence_cache = {}
            agent.client = _CorrelationClient({"correlation": 0.1})
            agent._refresh_self_correlation_evidence([parent])
            summary = agent.optimizer_context()["eligible_parents"][0]
            self.assertEqual(summary["self_correlation_status"], "PASS")
            self.assertEqual(summary["next_action"], "READY_TO_ADVANCE")


class TestResearchApiCanonicalReads(unittest.TestCase):
    """P0-D：一个 experiment identity 只暴露一条 canonical Agent 记录。"""

    def test_settled_revision_wins_in_every_research_api_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            trajectory = Trajectory(path=path, max_len=64, persist=True)
            early = Experiment(
                round=1, hypothesis_id="h1", expression="rank(field_a)",
                settings={"delay": 1}, fields_used=["field_a"],
                status="DONE", alpha_id="alpha-1",
            )
            trajectory.add(early)
            settled = dataclasses.replace(
                early, final_outcome={"evidence_quality": "FINAL"},
            )
            trajectory.settle(settled)
            record = research_api.get_experiment(early.id, state_dir=tmp)
            self.assertEqual(
                record.get("final_outcome"), {"evidence_quality": "FINAL"}
            )
            rows = research_api.search_history(early.id, state_dir=tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].get("final_outcome"), {"evidence_quality": "FINAL"})
            compared = research_api.compare_experiments([early.id], state_dir=tmp)
            self.assertEqual(len(compared["experiments"]), 1)
            self.assertEqual(compared["missing"], [])


class TestBoundedValidationStaysBounded(unittest.TestCase):
    """P1-A：VALIDATE 只能取 Python 解析的有界池，旧值必须来自 parent 自身。"""

    def _parent(self, **overrides):
        overrides.setdefault(
            "metrics",
            {
                "sharpe": 1.1,
                "fitness": 0.8,
                "turnover": 0.2,
                "checks": [
                    {"name": "LOW_SUB_UNIVERSE_SHARPE", "pass": False,
                     "result": "FAIL"},
                    {"name": "SELF_CORRELATION", "pass": None,
                     "result": "PENDING"},
                ],
            },
        )
        overrides.setdefault(
            "settings",
            {"delay": 1, "decay": 4, "truncation": 0.08, "universe": "TOP3000"},
        )
        overrides.setdefault("self_correlation", {"status": "PENDING"})
        return parent_record("p-universe", **overrides)

    def _flow(self, parents, *, universes=None):
        return OptimizerWorkflow(
            trajectory=FakeTrajectory(parents),
            alpha_feed_cache=_Cache(),
            alpha_factory=AlphaFactory(),
            quality_policy={},
            operator_reference={"operators": ["rank", "group_neutralize"]},
            hooks=OptimizerHooks(
                ensure_loaded=lambda: None,
                terminal_expressions=lambda: set(),
                allowed_universes=(
                    (lambda: tuple(universes)) if universes is not None else None
                ),
            ),
        )

    def test_universe_validate_without_a_pool_is_denied(self):
        flow = self._flow([self._parent()])
        result = flow.generate_from_decisions([
            validate_decision(
                "p-universe", validation_variable="universe",
                old_value="TOP3000", new_value="TOP1234",
            )
        ])
        self.assertEqual(result["proposals"], [])
        self.assertIn(
            "VALIDATION_UNIVERSE_POOL_UNAVAILABLE",
            result["rejected"][0]["reasons"],
        )

    def test_universe_validate_only_accepts_pooled_values(self):
        flow = self._flow([self._parent()], universes=["TOP1000", "TOP500"])
        out_of_pool = flow.generate_from_decisions([
            validate_decision(
                "p-universe", validation_variable="universe",
                old_value="TOP3000", new_value="TOP1234",
            )
        ])
        self.assertEqual(out_of_pool["proposals"], [])
        self.assertIn(
            "VALIDATION_NEW_VALUE_OUT_OF_POOL",
            out_of_pool["rejected"][0]["reasons"],
        )
        pooled = flow.generate_from_decisions([
            validate_decision(
                "p-universe", validation_variable="universe",
                old_value="TOP3000", new_value="TOP1000",
            )
        ])
        self.assertEqual(len(pooled["proposals"]), 1)
        proposal = pooled["proposals"][0]
        self.assertEqual(proposal["settings"], {"universe": "TOP1000"})
        self.assertEqual(proposal["experiment_stage"], "ROBUSTNESS")
        self.assertEqual(
            proposal["settings_variant"]["parent_default_value"], "TOP3000"
        )

    def test_agent_reported_old_value_never_becomes_provenance(self):
        flow = self._flow([self._parent()])
        lied = flow.generate_from_decisions([
            validate_decision("p-universe", old_value=7, new_value=5),
        ])
        self.assertEqual(lied["proposals"], [])
        self.assertIn(
            "VALIDATION_OLD_VALUE_MISMATCH", lied["rejected"][0]["reasons"]
        )
        honest = flow.generate_from_decisions([
            validate_decision("p-universe", old_value=4, new_value=5),
        ])
        self.assertEqual(len(honest["proposals"]), 1)
        self.assertEqual(
            honest["proposals"][0]["settings_variant"]["parent_default_value"], 4
        )


class TestHistoricalCorrelationBackfill(unittest.TestCase):
    """P1-B：脚本选择必须覆盖 trajectory_window 之外的 canonical 历史。"""

    def test_selection_reaches_beyond_the_in_memory_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            trajectory = Trajectory(path=path, max_len=512, persist=True)
            base = 1_700_000_000.0
            oldest = None
            for index in range(600):
                experiment = Experiment(
                    round=1, hypothesis_id=f"h-{index}",
                    expression=f"rank(field_{index})",
                    settings={"delay": 1}, fields_used=["field_a"],
                    status="DONE", alpha_id=f"alpha-{index}",
                    created_at=base + index,
                    metrics=synthetic_metrics(), health={"ok": True},
                )
                if index == 0:
                    oldest = experiment
                trajectory.add(experiment)
            self.assertNotIn(oldest.id, {item.id for item in trajectory.experiments})
            trajectory.settle(dataclasses.replace(
                oldest, final_outcome={"evidence_quality": "FINAL"},
            ))
            rows = load_trajectory_rows(
                tmp, window=64, since=base, until=base + 0.5
            )
            self.assertEqual([row["id"] for row in rows], [oldest.id])
            self.assertEqual(
                rows[0]["final_outcome"], {"evidence_quality": "FINAL"}
            )
            selection = pre_correlation_selection(
                rows, base, base + 0.5, None, delay=1, quality_policy={},
            )
            self.assertEqual(selection["alpha_ids"], ["alpha-0"])


def _targeted_proposal(index, *, stage="CHILD"):
    return {
        "expression": f"group_neutralize(rank(field_{index}), SUBINDUSTRY)",
        "proposal_origin": "agent_optimizer",
        "experiment_stage": stage,
        "settings": {"delay": 1, "decay": 4 + index},
        "datasets": ["fundamental6"],
        "fields": ["field_a"],
    }


def _factory_proposals():
    return [
        {
            "expression": f"rank(field_{index})",
            "proposal_origin": "factory",
            "datasets": ["d1"],
        }
        for index in range(100)
    ]


def _factory_agent(tmp):
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
        last_run_stats={"accepted": 0, "rejected": 0, "skipped": 0},
        checkpoints=CheckpointStore(tmp),
        memory=SimpleNamespace(seen_expressions=set()),
        trajectory=SimpleNamespace(experiments=[]),
    )
    agent.alpha_factory.generate_factory_batch.return_value = _factory_proposals()
    return agent


def _run_factory(agent, now):
    return AIFactoryRunner(
        agent, factory=agent.alpha_factory, quiet=True,
        clock=lambda: now[0],
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    ).run(
        duration_sec=1, idle_sleep_sec=1, max_simulations=11200,
        daily_simulation_cap=1600, weekly_simulation_cap=11200,
    )


class TestFactoryNeverOverwritesTargetedBatch(unittest.TestCase):
    """P1-C：Agent targeted batch 存在时工厂不得静默覆盖为 exploration 100。"""

    def _write(self, tmp, *, created_at, expires_at):
        payload = {
            "batch_type": TARGETED_BATCH_TYPE,
            "source": "agent_optimizer",
            "round_no": 7,
            "created_at": created_at,
            "expires_at": expires_at,
            "proposals": [
                _targeted_proposal(0),
                _targeted_proposal(1),
                _targeted_proposal(2, stage="ROBUSTNESS"),
            ],
        }
        path = os.path.join(tmp, "proposals.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return payload, path

    def test_pending_targeted_batch_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [0.0]
            payload, path = self._write(tmp, created_at=0.0, expires_at=3600.0)
            agent = _factory_agent(tmp)
            result = _run_factory(agent, now)
            with open(path, encoding="utf-8") as handle:
                after = json.load(handle)

        self.assertEqual(after, payload)
        self.assertEqual(result["last_action"], "WAIT_AGENT_DECISION")
        self.assertEqual(
            result["last_result"]["status"], "TARGETED_OPTIMIZATION_PENDING"
        )
        self.assertEqual(result["simulations_reserved"], 0)
        agent.run_suggestion_round.assert_not_called()
        agent.run_proposals.assert_not_called()
        agent.alpha_factory.generate_factory_batch.assert_not_called()

    def test_invalid_targeted_envelope_still_blocks_the_inbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [0.0]
            payload, path = self._write(tmp, created_at=0.0, expires_at=3600.0)
            payload["proposals"] = [_targeted_proposal(index) for index in range(5)]
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            agent = _factory_agent(tmp)
            result = _run_factory(agent, now)
            with open(path, encoding="utf-8") as handle:
                after = json.load(handle)

        self.assertEqual(after, payload)
        self.assertEqual(result["last_action"], "WAIT_AGENT_DECISION")
        self.assertEqual(result["last_result"]["status"], "TARGETED_BATCH_INVALID")
        self.assertTrue(result["last_result"]["errors"])
        agent.alpha_factory.generate_factory_batch.assert_not_called()

    def test_expired_targeted_batch_releases_the_inbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [10_000.0]
            _payload, path = self._write(tmp, created_at=0.0, expires_at=1.0)
            agent = _factory_agent(tmp)
            result = _run_factory(agent, now)
            with open(path, encoding="utf-8") as handle:
                after = json.load(handle)

        self.assertEqual(after["batch_type"], "factory_100")
        self.assertEqual(len(after["proposals"]), 100)
        self.assertEqual(result["last_action"], "WAIT_RUN_PROPOSALS")
        agent.alpha_factory.generate_factory_batch.assert_called_once()


class TestTargetedBatchMaterialization(unittest.TestCase):
    """P1-C：Agent 决策必须能落到唯一 proposals.json 的 targeted envelope。"""

    def _runtime(self, tmp, proposals, *, round_no=42):
        return SimpleNamespace(
            state_dir=tmp,
            next_round_no=lambda: round_no,
            propose_optimization=lambda decisions, max_candidates=4: {
                "proposals": list(proposals), "rejected": [],
            },
        )

    def test_materialize_writes_one_bounded_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            proposals = (
                [_targeted_proposal(index) for index in range(4)]
                + [
                    _targeted_proposal(index + 10, stage="ROBUSTNESS")
                    for index in range(4)
                ]
            )
            result = research_api.materialize_targeted_batch(
                [], agent=self._runtime(tmp, proposals), state_dir=tmp,
            )
            with open(os.path.join(tmp, "proposals.json"), encoding="utf-8") as handle:
                payload = json.load(handle)
            state = targeted_batch_state(payload, now=payload["created_at"])

        self.assertTrue(result["written"])
        self.assertEqual(result["status"], "TARGETED_BATCH_WRITTEN")
        self.assertEqual(payload["batch_type"], TARGETED_BATCH_TYPE)
        self.assertEqual(payload["round_no"], 42)
        self.assertEqual(len(payload["proposals"]), 8)
        self.assertTrue(state["valid"])
        self.assertTrue(state["blocking"])
        self.assertGreater(payload["expires_at"], payload["created_at"])

    def test_out_of_contract_batch_is_refused_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            proposals = [_targeted_proposal(index) for index in range(5)]
            result = research_api.materialize_targeted_batch(
                [], agent=self._runtime(tmp, proposals), state_dir=tmp,
            )
            exists = os.path.exists(os.path.join(tmp, "proposals.json"))

        self.assertFalse(result["written"])
        self.assertEqual(result["status"], "TARGETED_BATCH_REJECTED")
        self.assertTrue(result["errors"])
        self.assertFalse(exists)

    def test_no_decision_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = research_api.materialize_targeted_batch(
                [], agent=self._runtime(tmp, []), state_dir=tmp,
            )
            exists = os.path.exists(os.path.join(tmp, "proposals.json"))

        self.assertFalse(result["written"])
        self.assertEqual(result["status"], "NO_TARGETED_PROPOSAL")
        self.assertFalse(exists)


class TestFactoryNeverInventsAgentDecisions(unittest.TestCase):
    """P1-D：Python 不得替 Agent 伪造 CHILD decision。"""

    def _parent(self):
        field_profile = {
            "id": "field_a", "dataset": "fundamental6", "type": "MATRIX",
            "description": "已核验字段", "semantic_status": "KNOWN",
        }
        parent = parent_record(
            "p-repair",
            health={"ok": False, "reasons": ["CONCENTRATED_WEIGHT=FAIL v=0.9"]},
            metrics={
                "sharpe": 1.1, "fitness": 0.8, "turnover": 0.2,
                "checks": [
                    {"name": "CONCENTRATED_WEIGHT", "pass": False,
                     "result": "FAIL"},
                    {"name": "SELF_CORRELATION", "pass": None,
                     "result": "PENDING"},
                ],
            },
            field_analysis={"field_a": {
                "semantic": "已核验字段", "coverage": None,
                "frequency": None, "data_type": "MATRIX",
            }},
        )
        return parent, field_profile

    def test_structural_repair_parent_needs_an_agent_decision(self):
        parent, _profile = self._parent()
        flow = OptimizerWorkflow(
            trajectory=FakeTrajectory([parent]),
            alpha_feed_cache=_Cache(),
            alpha_factory=AlphaFactory(),
            quality_policy={},
            operator_reference={"operators": ["rank", "group_neutralize"]},
            hooks=OptimizerHooks(
                ensure_loaded=lambda: None,
                terminal_expressions=lambda: set(),
            ),
        )
        silent = flow.generate([parent], max_candidates=2)
        self.assertEqual(silent, [])
        self.assertEqual(flow.last_handoff_report["child_generated"], 0)
        self.assertEqual(flow.last_handoff_report["optimizer_rejected"], 1)
        authored = flow.generate_from_decisions(
            [child_decision("p-repair")], max_candidates=2,
        )
        self.assertEqual(len(authored["proposals"]), 1)


if __name__ == "__main__":
    unittest.main()
