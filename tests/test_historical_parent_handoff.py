"""Cross-process optimizer parent evidence handoff contracts.

These tests prove the P0 handoff fix: canonical completed Experiment evidence
persists through the existing Trajectory owner and is rehydrated read-only in
a fresh process, without a second trajectory, checkpoint owner or metrics
store.  No Simulation runs here.
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from wqb_agent.config import normalize_config
from wqb_agent.expression import canonical_expression
from wqb_agent.state import Experiment, Trajectory


def _config(state_dir):
    return {
        "simulation": {"neutralization": "SUBINDUSTRY"},
        "agent": {
            "state_dir": state_dir,
            "max_rounds": 3,
            "candidates_per_round": 5,
            "max_proposals_per_round": 12,
            "research_integrity": True,
            "fields_per_discovery": 4,
            "context_experiments": 7,
            "factory": {
                "max_simulations": 100,
                "max_runtime_sec": 3600,
                "daily_simulation_cap": 80,
                "weekly_simulation_cap": 100,
            },
            "field_selection": {
                "dataset_pool": ["pv1", "fundamental6"],
                "min_datasets": 2,
                "min_cross_dataset_pairs": 1,
                "require_platform_alpha_count": True,
            },
        },
    }


def completed_parent(expression="rank(field_a)", *, round_no=1, metrics=None):
    """Build one canonical completed parent Experiment with full evidence."""
    parent = Experiment(
        round_no, "h-parent", expression, {"decay": 4}, ["field_a"], ["pv1"]
    )
    parent.status = "DONE"
    parent.metrics = metrics or {
        "sharpe": 1.2,
        "fitness": 1.1,
        "turnover": 0.2,
        "checks": [{"name": "LOW_TURNOVER", "pass": True}],
    }
    parent.field_source = {"kind": "local_catalog", "snapshot_date": "2026-09-11"}
    parent.field_understanding = {"field_a": {"type": "MATRIX"}}
    parent.field_analysis = {"field_a": {"semantic_traits": {"status": "KNOWN"}}}
    parent.field_hypothesis_basis = {"field_a": {"concept": "level"}}
    parent.economic_mechanism = "level signal on a fundamental field"
    parent.direction = "higher value predicts higher forward return"
    parent.validation_plan = {"robustness": "aggregate"}
    return parent


class TmpStateMixin:
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="wqb_handoff_")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestRuntimeTrajectoryPersistence(unittest.TestCase):
    def test_runtime_components_enable_persistent_trajectory(self):
        # The architecture declares trajectory.jsonl as immutable evidence and
        # states that restarts recover optimizer evidence from the persisted
        # trajectory owner.  A fresh runtime must therefore persist.
        with tempfile.TemporaryDirectory(prefix="wqb_handoff_") as state_dir:
            config = normalize_config(_config(state_dir))
            from wqb_agent.runtime_components import build_runtime_components

            components = build_runtime_components(mock.MagicMock(), config)
            self.assertTrue(getattr(components.trajectory, "persist", False))
            self.assertEqual(
                os.path.basename(components.trajectory.path), "trajectory.jsonl"
            )
            self.assertEqual(
                os.path.dirname(components.trajectory.path),
                os.path.abspath(state_dir),
            )


class TestCanonicalEvidenceRestart(TmpStateMixin, unittest.TestCase):
    def test_case_a_completed_parent_survives_restart(self):
        path = os.path.join(self._tmp, "trajectory.jsonl")
        writer = Trajectory(max_len=25, path=path)
        parent = completed_parent()
        writer.add(parent)

        reader = Trajectory(max_len=25, path=path).load()
        restored = reader.find_completed_expression("rank( field_a )")
        self.assertIsNotNone(restored)
        self.assertEqual(restored.id, parent.id)
        self.assertEqual(restored.metrics["sharpe"], 1.2)
        self.assertEqual(restored.economic_mechanism, parent.economic_mechanism)
        self.assertEqual(restored.field_analysis, parent.field_analysis)

    def test_duplicate_append_is_not_persisted_twice(self):
        path = os.path.join(self._tmp, "trajectory.jsonl")
        first = Trajectory(max_len=25, path=path)
        parent = completed_parent()
        first.add(parent)

        second = Trajectory(max_len=25, path=path).load()
        second.add(parent)
        with open(path, encoding="utf-8") as handle:
            rows = [line for line in handle if line.strip()]
        self.assertEqual(len(rows), 1)

    def test_corrupt_row_is_skipped_without_fabrication(self):
        path = os.path.join(self._tmp, "trajectory.jsonl")
        writer = Trajectory(max_len=25, path=path)
        good = completed_parent()
        writer.add(good)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("{ this is not json\n")
            handle.write('{"expression": "rank(broken)"}\n')

        reader = Trajectory(max_len=25, path=path).load()
        self.assertEqual([exp.id for exp in reader.experiments], [good.id])
        self.assertIsNone(reader.find_completed_expression("rank(broken)"))


class FakeTrajectory:
    """Minimal trajectory double for the optimizer gate (read-only)."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.experiments = list(rows)

    def recent(self, limit):
        return self.rows[-limit:]


class FakeCache:
    def __init__(self, payload):
        self.payload = payload

    def load(self):
        return self.payload


class RecordingFactory:
    def screen_optimization_parents(self, parents, **kwargs):
        return list(parents)

    def optimize_signal_proposals(self, parents, operator_reference, **kwargs):
        return ["factory-result"]


def _optimizer_workflow(trajectory, cache=None):
    from wqb_agent.optimizer_workflow import OptimizerHooks, OptimizerWorkflow

    return OptimizerWorkflow(
        trajectory=trajectory,
        alpha_feed_cache=cache or FakeCache({}),
        alpha_factory=RecordingFactory(),
        quality_policy={},
        operator_reference={"operators": ["rank", "group_neutralize"]},
        hooks=OptimizerHooks(
            ensure_loaded=lambda: None,
            terminal_expressions=lambda: set(),
        ),
    )


def checkpoint_style_row(expression="rank(field_a)", *, row_id="exp-cp-1"):
    """A checkpoint experiment row: execution facts only, no result evidence."""
    return {
        "schema_version": 1,
        "created_by_version": "alpha-factory",
        "round": 1,
        "hypothesis_id": "h-cp",
        "expression": expression,
        "settings": {"decay": 4},
        "fields_used": ["field_a"],
        "id": row_id,
        "proposal_id": "p-" + row_id,
        "submission_fingerprint": "fp-" + row_id,
        "status": "DONE",
        "lineage_id": "lineage-cp",
        "template_family": "template_a",
    }


class TestRestartContractCases(TmpStateMixin, unittest.TestCase):
    def test_case_b_checkpoint_status_only_is_not_a_legal_parent(self):
        # A completed checkpoint row has DONE + execution facts but no
        # metrics/checks/field evidence.  It must stay BLOCKED, never relaxed.
        workflow = _optimizer_workflow(FakeTrajectory([]))
        report = workflow.gate_report([checkpoint_style_row()])
        self.assertEqual(report["ready_parent_count"], 0)
        self.assertGreater(report["blocked_reasons"].get("PARENT_METRICS_MISSING", 0), 0)
        self.assertGreater(
            report["blocked_reasons"].get("PARENT_FIELD_EVIDENCE_MISSING", 0), 0
        )
        self.assertEqual(workflow.optimizable_signal_records(), [])

    def test_case_c_cloud_metadata_alone_cannot_create_a_parent(self):
        cache = FakeCache({
            "days": {"2026-09-11": {"simulations": [
                {"alpha_id": "cloud-only-alpha"},
            ], "submitted_alphas": []}},
        })
        workflow = _optimizer_workflow(FakeTrajectory([]), cache=cache)
        self.assertEqual(workflow.optimizable_signal_records(), [])
        report = workflow.gate_report([])
        self.assertEqual(report["ready_parent_count"], 0)

    def test_case_d_child_and_incremental_verdict_survive_restart(self):
        path = os.path.join(self._tmp, "trajectory.jsonl")
        writer = Trajectory(max_len=25, path=path)
        parent = completed_parent()
        writer.add(parent)
        child = Experiment(
            2, "h-child", "rank(group_neutralize(field_a, industry))",
            {"decay": 4}, ["field_a"], ["pv1"],
        )
        child.status = "DONE"
        child.metrics = {"sharpe": 1.35, "fitness": 1.2,
                         "checks": [{"name": "LOW_TURNOVER", "pass": True}]}
        child.parent_expression = parent.expression
        child.lineage_id = "lineage-1"
        child.experiment_stage = "EXPLOIT"
        child.change_type = "group_neutralization"
        child.incremental_evidence = {
            "availability": "AVAILABLE", "quality": "VERIFIED",
            "decision": "PASS", "max_abs_corr": 0.2,
        }
        writer.add(child)

        reader = Trajectory(max_len=25, path=path).load()
        restored = reader.find_completed_expression(child.expression)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.parent_expression, parent.expression)
        self.assertEqual(restored.incremental_evidence["decision"], "PASS")
        resolved = reader.find_completed_expressions([restored.parent_expression])
        self.assertEqual(
            resolved[canonical_expression(parent.expression)].id, parent.id
        )

    def test_case_e_multi_generation_lineage_identity_survives_restart(self):
        path = os.path.join(self._tmp, "trajectory.jsonl")
        writer = Trajectory(max_len=25, path=path)
        parent = completed_parent("rank(field_a)")
        parent.lineage_id = "lineage-root"
        writer.add(parent)
        first = Experiment(
            2, "h-1", "rank(group_neutralize(field_a, industry))",
            {"decay": 4}, ["field_a"], ["pv1"],
        )
        first.status = "DONE"
        first.metrics = {"sharpe": 1.3, "fitness": 1.1,
                         "checks": [{"name": "LOW_TURNOVER", "pass": True}]}
        first.parent_expression = parent.expression
        first.lineage_id = "lineage-root"
        first.experiment_stage = "EXPLOIT"
        writer.add(first)
        second = Experiment(
            3, "h-2", "rank(group_neutralize(field_a, subindustry))",
            {"decay": 4}, ["field_a"], ["pv1"],
        )
        second.status = "DONE"
        second.metrics = {"sharpe": 1.4, "fitness": 1.2,
                          "checks": [{"name": "LOW_TURNOVER", "pass": True}]}
        second.parent_expression = first.expression
        second.lineage_id = "lineage-root"
        second.experiment_stage = "EXPLOIT"
        writer.add(second)

        reader = Trajectory(max_len=25, path=path).load()
        resolved = reader.find_completed_expressions(
            [parent.expression, first.expression, second.expression]
        )
        self.assertEqual(len(resolved), 3)
        restored_second = resolved[canonical_expression(second.expression)]
        self.assertEqual(
            canonical_expression(restored_second.parent_expression),
            canonical_expression(first.expression),
        )
        restored_first = resolved[canonical_expression(first.expression)]
        self.assertEqual(
            canonical_expression(restored_first.parent_expression),
            canonical_expression(parent.expression),
        )
        self.assertEqual(
            {restored_first.lineage_id, restored_second.lineage_id},
            {"lineage-root"},
        )


if __name__ == "__main__":
    unittest.main()
