"""Optimizer funnel and metric-context tests."""

import unittest
from dataclasses import replace
from pathlib import Path

from tests.optimizer_helpers import (
    CHILD_EXPRESSION,
    IMPACT,
    MECHANISM,
    PACKAGE_ROOT,
    PARENT_EXPRESSION,
    FakeCache,
    FakeTrajectory,
    RecordingFactory,
    child_decision,
    parent_record,
    validate_decision,
    workflow,
)
from wqb_agent.alpha_factory import (
    DEFAULT_TEMPLATES,
    ECONOMIC_TEMPLATES,
    AlphaFactory,
    template_numeric_audit,
)
from wqb_agent.diversity import semantic_mechanism_key
from wqb_agent.optimization_decision import (
    CHILD_REQUIRED_TEXT_FIELDS,
    OPPORTUNITY_CATEGORIES,
    VALID_DECISIONS,
    VALIDATION_VARIABLES,
    OptimizationDecision,
    decision_rejections,
    parent_opportunity,
    summarize_parent,
)
from wqb_agent.optimizer_workflow import (
    OptimizerHooks,
    OptimizerWorkflow,
    optimization_eligibility_map,
    optimizer_conversions,
)
from wqb_agent.pre_correlation import (
    READINESS_BANDS,
    optimization_parent_admission,
    pre_self_correlation_eligibility,
)
from wqb_agent.proposal_contract import validate_proposal
from wqb_agent.research_yield import build_research_yield


class TestOptimizerFunnel(unittest.TestCase):
    """DONE -> evidence eligible -> agent reviewed -> decision -> child -> done."""

    def build(self):
        parents = [
            parent_record(f"p{i}", expression=f"rank(field_a_{i})")
            for i in range(10)
        ]
        # Two parents fail the Python evidence gate (missing field evidence).
        parents[8]["field_source"] = {}
        parents[9]["field_analysis"] = {}
        decisions = (
            ["CHILD"] * 3 + ["VALIDATE", "STOP", "REROUTE"]
        )
        for parent, name in zip(parents[:6], decisions):
            if name == "CHILD":
                payload = child_decision(parent["id"]).as_dict()
            else:
                payload = OptimizationDecision(
                    parent_id=parent["id"], decision=name
                ).as_dict()
            parent["optimization_decision"] = payload
        children = [
            {"id": "c1", "status": "DONE", "incremental_evidence": {"decision": "PASS"}},
            {"id": "c2", "status": "DONE", "incremental_evidence": {"decision": "UNAVAILABLE"}},
            {"id": "c3", "status": "FAILED"},
        ]
        return parents, children

    def test_funnel_separates_evidence_eligibility_from_agent_decision(self):
        parents, children = self.build()
        report = workflow().gate_report(parents, children=children)
        self.assertEqual(report["parent_count"], 10)
        self.assertEqual(report["done_parent_count"], 10)
        self.assertEqual(report["evidence_eligible_parent_count"], 8)
        self.assertEqual(report["evidence_rejected_parent_count"], 2)
        self.assertEqual(report["agent_reviewed_parent_count"], 6)
        self.assertEqual(report["agent_decision_child_count"], 3)
        self.assertEqual(report["agent_decision_validate_count"], 1)
        self.assertEqual(report["agent_decision_stop_count"], 1)
        self.assertEqual(report["agent_decision_reroute_count"], 1)
        self.assertEqual(report["child_generated_count"], 3)
        self.assertEqual(report["child_done_count"], 2)
        self.assertEqual(report["incremental_pass_count"], 1)
        self.assertEqual(report["incremental_fail_count"], 0)
        self.assertEqual(report["incremental_unknown_count"], 1)
        # The legacy ready count still means evidence + Agent hypothesis.
        self.assertEqual(report["ready_parent_count"], 3)

    def test_agent_optimization_yield_conversions(self):
        parents, children = self.build()
        report = workflow().gate_report(parents, children=children)
        ratios = optimizer_conversions(report)
        self.assertAlmostEqual(ratios["done_to_evidence_parent"], 0.8)
        self.assertAlmostEqual(ratios["evidence_parent_to_agent_review"], 0.75)
        self.assertAlmostEqual(ratios["agent_review_to_child_decision"], 0.5)
        self.assertAlmostEqual(ratios["child_decision_to_child_generated"], 1.0)
        self.assertAlmostEqual(ratios["child_to_done"], 2 / 3)
        self.assertAlmostEqual(ratios["child_to_incremental_pass"], 0.5)

    def test_zero_denominator_is_none_never_zero(self):
        report = workflow().gate_report([], children=[])
        self.assertEqual(report["done_parent_count"], 0)
        ratios = optimizer_conversions(report)
        self.assertEqual(set(ratios.values()), {None})
        for name, value in ratios.items():
            self.assertIsNone(value, name)

    def test_research_yield_funnel_distinguishes_the_two_optimizer_stages(self):
        parents, _ = self.build()
        eligibility = optimization_eligibility_map(parents)
        self.assertEqual(len(eligibility), 10)
        self.assertFalse(eligibility["p8"]["eligible"])
        self.assertTrue(eligibility["p1"]["eligible"])
        self.assertTrue(eligibility["p1"]["reviewed"])
        self.assertEqual(eligibility["p1"]["decision"], "CHILD")

        funnels = build_research_yield(parents, eligibility=eligibility)
        self.assertEqual(list(funnels), ["m:quality:diffusion"])
        funnel = funnels["m:quality:diffusion"]
        self.assertEqual(funnel.simulations_done, 10)
        self.assertEqual(funnel.optimizer_eligible_parents, 8)
        self.assertTrue(funnel.agent_review_stage_available)
        self.assertEqual(funnel.agent_reviewed_parents, 6)
        self.assertEqual(funnel.agent_child_decisions, 3)
        conversions = funnel.conversions()
        self.assertAlmostEqual(
            conversions["done_to_optimizer_parent"]["value"], 0.8
        )
        self.assertAlmostEqual(
            conversions["evidence_parent_to_agent_review"]["value"], 0.75
        )
        self.assertAlmostEqual(
            conversions["agent_review_to_child_decision"]["value"], 0.5
        )

    def test_unknown_agent_stage_is_none_not_zero_percent(self):
        parents = [parent_record("p1")]
        # This eligibility view carries no Agent-review information at all.
        funnel = build_research_yield(parents, eligibility={"p1": True})[
            "m:quality:diffusion"
        ]
        self.assertFalse(funnel.agent_review_stage_available)
        self.assertIsNone(funnel.agent_reviewed_parents)
        conversions = funnel.conversions()
        self.assertIsNone(conversions["evidence_parent_to_agent_review"]["value"])
        self.assertEqual(
            conversions["evidence_parent_to_agent_review"]["reason"],
            "DENOMINATOR_UNAVAILABLE",
        )
        self.assertIsNone(conversions["agent_review_to_child_decision"]["value"])

    def test_eligible_but_unreviewed_parent_reports_a_real_zero(self):
        parents = [parent_record("p1")]
        funnel = build_research_yield(
            parents, eligibility=optimization_eligibility_map(parents)
        )["m:quality:diffusion"]
        self.assertTrue(funnel.agent_review_stage_available)
        self.assertEqual(funnel.agent_reviewed_parents, 0)
        conversions = funnel.conversions()
        self.assertEqual(
            conversions["evidence_parent_to_agent_review"]["value"], 0.0
        )
        self.assertIsNone(conversions["agent_review_to_child_decision"]["value"])

class TestOptimizerMetricContext(unittest.TestCase):
    """§39-§54：metric-aware、bounded 的 optimizer context（只读派生）。"""

    @staticmethod
    def blocked_metrics(**overrides):
        metrics = {
            "sharpe": 1.6,
            "fitness": 1.3,
            "turnover": 0.25,
            "returns": 0.12,
            "drawdown": 0.05,
            "checks": [
                {"name": "CONCENTRATED_WEIGHT", "result": "FAIL"},
                {"name": "SELF_CORRELATION", "result": "PENDING"},
            ],
        }
        metrics.update(overrides)
        return metrics

    @staticmethod
    def eligible_metrics(**overrides):
        metrics = {
            "sharpe": 1.5,
            "fitness": 1.2,
            "turnover": 0.18,
            "returns": 0.12,
            "drawdown": 0.05,
            "checks": [{"name": "SELF_CORRELATION", "result": "PENDING"}],
        }
        metrics.update(overrides)
        return metrics

    def test_context_is_bounded_and_exposes_the_decision_contract(self):
        rows = [
            parent_record(
                f"p{index}", settings={"delay": 1},
                health={"ok": True},
                self_correlation={"status": "PENDING"},
                metrics=self.blocked_metrics(),
            )
            for index in range(3)
        ]
        context = workflow(FakeTrajectory(rows)).optimizer_context(limit=2)

        self.assertEqual(context["parent_limit"], 2)
        self.assertEqual(context["parent_count"], 2)
        self.assertLessEqual(len(context["eligible_parents"]), 2)
        self.assertEqual(
            context["failure_blocker_summary"], {"CONCENTRATED_WEIGHT": 2}
        )
        self.assertEqual(
            context["readiness_counts"]["STRUCTURAL_REPAIR_REQUIRED"], 2
        )
        self.assertEqual(context["self_correlation_counts"], {"PENDING": 2})
        contract = context["decision_contract"]
        self.assertEqual(set(contract["decisions"]), set(VALID_DECISIONS))
        self.assertEqual(
            set(contract["validation_variables"]), set(VALIDATION_VARIABLES)
        )
        self.assertEqual(set(contract["readiness_bands"]), set(READINESS_BANDS))
        self.assertIn("blocked_reasons", context)
        self.assertIn("generation_bound", context)
        self.assertIn("ranking", context)

    def test_blocked_parent_needs_structural_repair_before_correlation(self):
        row = parent_record(
            "p-blocked", settings={"delay": 1}, health={"ok": True},
            metrics=self.blocked_metrics(),
        )
        context = workflow(FakeTrajectory([row])).optimizer_context(limit=4)

        entry = context["pre_correlation_eligibility"][0]
        self.assertEqual(entry["parent_id"], "p-blocked")
        self.assertFalse(entry["eligible"])
        self.assertEqual(entry["readiness"], "STRUCTURAL_REPAIR_REQUIRED")
        self.assertIn("CONCENTRATION_REPAIR", entry["opportunities"])
        self.assertIn("NON_CORRELATION_CHECKS_NOT_PASS", entry["reasons"])
        metric_context = context["eligible_parents"][0]["metric_optimization_context"]
        self.assertFalse(metric_context["pre_correlation_eligible"])
        self.assertEqual(metric_context["structural_blockers"], ["CONCENTRATED_WEIGHT"])
        self.assertEqual(metric_context["blocking_checks"], ["CONCENTRATED_WEIGHT"])

    def test_repaired_parent_moves_to_ready_for_correlation(self):
        row = parent_record(
            "p-ready", settings={"delay": 1}, health={"ok": True},
            metrics=self.eligible_metrics(),
        )
        context = workflow(FakeTrajectory([row])).optimizer_context(limit=4)

        entry = context["pre_correlation_eligibility"][0]
        self.assertTrue(entry["eligible"])
        self.assertEqual(entry["readiness"], "PRE_CORRELATION_READY")
        self.assertEqual(context["readiness_counts"]["PRE_CORRELATION_READY"], 1)
        self.assertEqual(context["failure_blocker_summary"], {})

    def test_ranking_is_readiness_first_not_sharpe_only(self):
        rows = [
            parent_record(
                "p-higher-sharpe", settings={"delay": 1}, health={"ok": True},
                metrics=self.eligible_metrics(sharpe=0.9, fitness=0.4, turnover=0.35),
            ),
            parent_record(
                "p-structural", settings={"delay": 1}, health={"ok": True},
                metrics=self.blocked_metrics(sharpe=0.5, fitness=0.4, turnover=0.25),
            ),
        ]
        context = workflow(FakeTrajectory(rows)).optimizer_context(limit=4)

        self.assertEqual(
            [summary["parent_id"] for summary in context["eligible_parents"]],
            ["p-structural", "p-higher-sharpe"],
        )
        self.assertEqual(context["readiness_counts"]["LOW_INFORMATION"], 1)

    def test_delay_hook_controls_the_metric_line(self):
        row = parent_record(
            "p-delay", settings={"delay": 1},
            health={"ok": True},
            metrics=self.eligible_metrics(sharpe=1.6),
        )
        flow = workflow(FakeTrajectory([row]))
        flow.hooks = replace(flow.hooks, simulation_delay=lambda: 0)

        entry = flow.optimizer_context(limit=4)["pre_correlation_eligibility"][0]
        self.assertFalse(entry["eligible"])
        self.assertEqual(entry["readiness"], "LOW_INFORMATION")
        self.assertIn("SHARPE_BELOW_THRESHOLD", entry["reasons"])
        self.assertIn("FITNESS_BELOW_THRESHOLD", entry["reasons"])

    def test_declared_numeric_slots_and_settings_pools_are_bounded(self):
        row = parent_record(
            "p-numeric", template_id="reversal_zscore_20",
            settings={"delay": 1, "decay": 4, "truncation": 0.08},
            metrics=self.eligible_metrics(),
        )
        context = workflow(
            FakeTrajectory([row]), factory=AlphaFactory()
        ).optimizer_context(limit=4)

        variants = context["numeric_variants_available"]
        self.assertEqual(len(variants), 1)
        entry = variants[0]
        self.assertEqual(entry["template_id"], "reversal_zscore_20")
        self.assertEqual(
            [(slot["slot"], slot["default"]) for slot in entry["template_slots"]],
            [("short_window", 20)],
        )
        self.assertEqual(entry["settings_pools"]["decay"], [3, 5])
        self.assertEqual(entry["settings_pools"]["truncation"], [0.06, 0.1])
        self.assertEqual(entry["settings_pools"]["universe"], [])
