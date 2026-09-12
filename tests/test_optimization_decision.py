"""Phase III optimization decision contract + optimizer funnel tests.

The Agent owns the economic judgement (why change, what changes, what effect is
expected, how it can be falsified).  Python only verifies the deterministic
gates: field completeness, parent identity, one-change rule, parameter/direction
rejection, overfit rejection, operator legality and the existing
self-correlation admission contract.
"""

import unittest
from dataclasses import replace
from pathlib import Path

from wqb_agent.alpha_factory import AlphaFactory
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
from wqb_agent.pre_correlation import READINESS_BANDS
from wqb_agent.proposal_contract import validate_proposal
from wqb_agent.research_yield import build_research_yield

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "wqb_agent"

MECHANISM = "质量变化驱动的相对定价差异"
IMPACT = {
    "expected_effect": "LOWER",
    "basis": "子域中性化降低与现有族的相关暴露",
    "rationale": "同一字段、同一机制，仅改变可比组",
    "admission": "ALLOW",
}
CHILD_EXPRESSION = "group_neutralize(rank(field_a), SUBINDUSTRY)"
PARENT_EXPRESSION = "rank(field_a)"


def parent_record(pid, expression=PARENT_EXPRESSION, **overrides):
    record = {
        "id": pid,
        "proposal_id": pid,
        "status": "DONE",
        "round": 1,
        "expression": expression,
        "fields_used": ["field_a"],
        "datasets": ["fundamental6"],
        "field_understanding": {"field_a": "已核验字段"},
        "field_analysis": {"field_a": {"data_type": "MATRIX"}},
        "field_source": {"kind": "brain_api"},
        "field_hypothesis_basis": {"field_a": {"mechanism": MECHANISM}},
        "hypothesis_id": "h-1",
        "economic_mechanism": MECHANISM,
        "semantic_mechanism_family": "m:quality:diffusion",
        "metrics": {
            "sharpe": 1.1,
            "fitness": 0.8,
            "turnover": 0.2,
            "checks": [{"name": "SELF_CORRELATION", "status": "UNKNOWN"}],
        },
        "self_correlation": {"status": "PASS"},
        "validation_status": "STABLE",
    }
    record.update(overrides)
    return record


def child_decision(parent_id, *, expression=CHILD_EXPRESSION, **overrides):
    payload = {
        "parent_id": parent_id,
        "decision": "CHILD",
        "observed_evidence": "父代子域内表现弱于整体",
        "economic_mechanism": MECHANISM,
        "change_type": "neutralization",
        "changed_variable": "neut",
        "expression": expression,
        "expected_effect": "lower sub-universe gap",
        "falsification": "若子域检查转差则机制不成立",
        "direction": "long",
        "direction_transform": {
            "applied": False,
            "reason": "沿用 parent 方向，不把方向翻转当作新机制",
        },
        "self_correlation_impact": IMPACT,
        "why_not_parameter_tuning": "改变可比组而非窗口/权重",
    }
    payload.update(overrides)
    return OptimizationDecision(**payload)


def validate_decision(parent_id, **overrides):
    payload = {
        "parent_id": parent_id,
        "decision": "VALIDATE",
        "validation_variable": "decay",
        "old_value": 4,
        "new_value": 5,
        "expected_effect": "验证 decay 邻域内换手与稳定性是否单调",
        "falsification": "若邻域内 Sharpe 反向恶化则稳定性假设不成立",
        "reason": "Fitness 未过线且 turnover 进入分母",
    }
    payload.update(overrides)
    return OptimizationDecision(**payload)


class FakeTrajectory:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def recent(self, limit):
        return self.rows[-limit:]


class FakeCache:
    def load(self):
        return {}


class RecordingFactory:
    def __init__(self):
        self.screen_calls = []
        self.optimize_calls = []

    def screen_optimization_parents(self, parents, **kwargs):
        self.screen_calls.append((list(parents), kwargs))
        return list(parents)

    def optimize_signal_proposals(self, parents, operator_reference, **kwargs):
        self.optimize_calls.append((list(parents), operator_reference, kwargs))
        return ["factory-result"]


def workflow(trajectory=None, factory=None, operators=None):
    return OptimizerWorkflow(
        trajectory=trajectory or FakeTrajectory(),
        alpha_feed_cache=FakeCache(),
        alpha_factory=factory or RecordingFactory(),
        quality_policy={},
        operator_reference={
            "operators": list(operators or ["rank", "group_neutralize"])
        },
        hooks=OptimizerHooks(
            ensure_loaded=lambda: None,
            terminal_expressions=lambda: set(),
        ),
    )


class TestOptimizationDecisionContract(unittest.TestCase):
    def setUp(self):
        self.parent = parent_record("p1")

    def test_decision_vocabulary_and_required_child_fields_are_explicit(self):
        self.assertEqual(set(VALID_DECISIONS), {"CHILD", "VALIDATE", "REROUTE", "STOP"})
        self.assertIn("economic_mechanism", CHILD_REQUIRED_TEXT_FIELDS)
        self.assertIn("falsification", CHILD_REQUIRED_TEXT_FIELDS)
        self.assertIn("parent_id", CHILD_REQUIRED_TEXT_FIELDS)

    def test_unknown_decision_and_empty_parent_are_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            OptimizationDecision(parent_id="p1", decision="MAYBE")
        with self.assertRaises(ValueError):
            OptimizationDecision(parent_id="   ", decision="STOP")

    def test_legal_child_decision_passes_every_deterministic_gate(self):
        decision = child_decision("p1")
        self.assertTrue(decision.is_child)
        self.assertEqual(decision.missing_fields(), [])
        self.assertEqual(decision_rejections(decision, self.parent), [])

    def test_missing_parent_is_rejected(self):
        decision = child_decision("p1")
        self.assertEqual(decision_rejections(decision, None), ["PARENT_INVALID"])
        self.assertEqual(
            decision_rejections(decision, parent_record("p2")),
            ["PARENT_IDENTITY_MISMATCH"],
        )

    def test_missing_economic_mechanism_or_falsification_is_rejected(self):
        for field in ("economic_mechanism", "falsification", "why_not_parameter_tuning"):
            decision = child_decision("p1", **{field: "  "})
            self.assertEqual(
                decision_rejections(decision, self.parent),
                ["DECISION_FIELDS_MISSING"],
                field,
            )

    def test_parameter_only_change_is_rejected(self):
        tuned_parent = parent_record(
            "p1", expression="ts_decay_linear(rank(field_a), 5)"
        )
        decision = child_decision(
            "p1", expression="ts_decay_linear(rank(field_a), 10)"
        )
        self.assertIn(
            "PARAMETER_ONLY_CHANGE", decision_rejections(decision, tuned_parent)
        )

    def test_direction_only_change_is_rejected(self):
        decision = child_decision("p1", expression="-rank(field_a)")
        self.assertEqual(
            decision_rejections(decision, self.parent), ["DIRECTION_ONLY_CHANGE"]
        )

    def test_disguised_multi_change_is_rejected(self):
        decision = child_decision("p1", expression="rank(field_b)")
        self.assertIn(
            "DECLARED_CHANGE_MULTIPLE_FIELDS",
            decision_rejections(decision, self.parent),
        )
        tuned_parent = parent_record(
            "p1", expression="ts_decay_linear(rank(field_a), 5)"
        )
        disguised = child_decision(
            "p1", expression="ts_decay_linear(rank(field_b), 10)"
        )
        reasons = decision_rejections(disguised, tuned_parent)
        self.assertIn("DECLARED_CHANGE_FIELD_AND_PARAMETER", reasons)

    def test_change_type_and_direction_transform_must_match_the_proposal_contract(self):
        """决策层必须复用既有 proposal contract，而不是自创同义取值。"""
        wrong_vocabulary = child_decision("p1", change_type="neutralization_change")
        self.assertEqual(
            decision_rejections(wrong_vocabulary, self.parent),
            ["CHANGE_TYPE_NOT_IN_PROPOSAL_CONTRACT"],
        )
        bad_transform = child_decision("p1", direction_transform="same")
        self.assertEqual(
            decision_rejections(bad_transform, self.parent),
            ["DIRECTION_TRANSFORM_INVALID"],
        )

    def test_illegal_operator_and_invalid_self_correlation_are_rejected(self):
        decision = child_decision("p1")
        reasons = decision_rejections(
            decision, self.parent, allowed_operators={"rank"}
        )
        self.assertEqual(reasons, ["OPERATOR_ILLEGAL"])
        bad_impact = child_decision(
            "p1",
            self_correlation_impact={
                "expected_effect": "SIMILAR",
                "basis": "b",
                "rationale": "r",
                "admission": "ALLOW",
            },
        )
        self.assertIn(
            "SELF_CORRELATION_IMPACT_INVALID",
            decision_rejections(bad_impact, self.parent),
        )

    def test_non_child_decisions_carry_no_child_discovery_claim(self):
        for decision_name in ("VALIDATE", "REROUTE", "STOP"):
            decision = OptimizationDecision(
                parent_id="p1", decision=decision_name
            )
            self.assertFalse(decision.is_child)
            self.assertEqual(decision.missing_fields(), [])
            self.assertEqual(decision_rejections(decision, self.parent), [])
        validate = OptimizationDecision(
            parent_id="p1",
            decision="VALIDATE",
            expression=CHILD_EXPRESSION,
            economic_mechanism=MECHANISM,
        )
        # A VALIDATE decision never becomes a CHILD claim even if fields exist.
        self.assertFalse(validate.is_child)
        self.assertEqual(validate.to_child_hypothesis()["expression"], CHILD_EXPRESSION)

    def test_from_child_hypothesis_round_trips_the_legacy_dict(self):
        legacy = child_decision("p1").to_child_hypothesis()
        restored = OptimizationDecision.from_child_hypothesis("p1", legacy)
        self.assertTrue(restored.is_child)
        self.assertEqual(restored.to_child_hypothesis(), legacy)
        self.assertEqual(restored.parent_id, "p1")

    def test_from_mapping_requires_an_object(self):
        with self.assertRaises(TypeError):
            OptimizationDecision.from_mapping(["not", "a", "mapping"])

    def test_parent_opportunity_and_summary_stay_evidence_derived(self):
        self.assertIn(parent_opportunity(self.parent), OPPORTUNITY_CATEGORIES)
        self.assertEqual(
            parent_opportunity(parent_record("p", self_correlation={"status": "FAIL"})),
            "SELF_CORRELATION_REPAIR",
        )
        self.assertEqual(
            parent_opportunity(
                parent_record(
                    "p",
                    metrics={"sharpe": 1.0, "checks": [
                        {"name": "CONCENTRATED_WEIGHT", "pass": False}
                    ]},
                )
            ),
            "CONCENTRATION_REPAIR",
        )
        summary = summarize_parent(self.parent)
        self.assertEqual(summary["parent_id"], "p1")
        self.assertEqual(summary["opportunity"], "NO_CLEAR_OPPORTUNITY")
        self.assertEqual(summary["mechanism_state"], "UNKNOWN")
        self.assertEqual(
            set(summary["metrics"]),
            {"sharpe", "fitness", "turnover", "margin", "returns"},
        )
        # Missing evidence stays UNKNOWN instead of being guessed.
        self.assertEqual(summarize_parent({})["self_correlation_status"], "UNKNOWN")


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


class TestAgentDecisionToProposal(unittest.TestCase):
    def test_child_decision_generates_through_the_single_workflow_path(self):
        factory = RecordingFactory()
        parent = parent_record("p1")
        flow = workflow(FakeTrajectory([parent]), factory=factory)
        result = flow.generate_from_decisions([child_decision("p1")], max_candidates=2)
        self.assertEqual(result["proposals"], ["factory-result"])
        self.assertEqual(result["decision_report"], {
            "reviewed": 1, "accepted": 1, "rejected": 0, "child_generated": 1,
            "validation_requests": 0, "validation_generated": 0,
        })
        self.assertEqual(len(factory.optimize_calls), 1)
        optimized, reference, kwargs = factory.optimize_calls[0]
        self.assertEqual(optimized[0]["optimization_decision"]["decision"], "CHILD")
        self.assertEqual(
            optimized[0]["child_economic_hypothesis"]["expression"], CHILD_EXPRESSION
        )
        self.assertEqual(reference, {"operators": ["rank", "group_neutralize"]})
        self.assertEqual(kwargs["max_candidates"], 2)

    def test_real_factory_child_proposal_keeps_parent_provenance(self):
        """真实 AlphaFactory 组装必须能追回 parent，且不复制 parent metrics。"""
        field_profile = {
            "id": "field_a",
            "dataset": "fundamental6",
            "type": "MATRIX",
            "description": "已核验字段",
            "semantic_status": "KNOWN",
        }
        parent = parent_record(
            "p-parent",
            field_analysis={"field_a": {
                "semantic": "已核验字段", "coverage": None,
                "frequency": None, "data_type": "MATRIX",
            }},
        )
        flow = workflow(FakeTrajectory([parent]), factory=AlphaFactory())
        result = flow.generate_from_decisions(
            [child_decision("p-parent")], max_candidates=1
        )

        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["parent_id"], "p-parent")
        self.assertEqual(proposal["parent_expression"], PARENT_EXPRESSION)
        self.assertEqual(proposal["lineage_id"], "h-1")
        self.assertEqual(proposal["economic_mechanism"], MECHANISM)
        self.assertEqual(proposal["change_type"], "neutralization")
        self.assertEqual(proposal["changed_variable"], "neut")
        self.assertTrue(proposal["falsification"].strip())
        self.assertEqual(proposal["optimization_decision"]["decision"], "CHILD")
        self.assertEqual(proposal["optimization_decision"]["parent_id"], "p-parent")
        for copied in ("metrics", "checks", "self_correlation", "status", "round"):
            self.assertNotIn(copied, proposal)

        ok, problems = validate_proposal(
            proposal,
            discovered_fields=[field_profile],
            strict_experiment=True,
            operator_reference={"operators": ["rank", "group_neutralize"]},
            require_economic_integrity=True,
        )
        self.assertEqual(problems, [])
        self.assertTrue(ok)

    def test_legacy_child_hypothesis_still_carries_parent_identity(self):
        """无正式 decision 时也必须保留 parent 身份与新机制。"""
        parent = parent_record("p-legacy", child_economic_hypothesis={
            "expression": CHILD_EXPRESSION,
            "economic_mechanism": MECHANISM,
            "change_type": "neutralization",
        })
        flow = workflow(FakeTrajectory([parent]), factory=AlphaFactory())
        proposals = flow.generate([parent], max_candidates=1)

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["parent_id"], "p-legacy")
        self.assertEqual(proposals[0]["economic_mechanism"], MECHANISM)
        self.assertNotIn("optimization_decision", proposals[0])
        self.assertNotIn("metrics", proposals[0])

    def test_valid_reroute_and_stop_decisions_generate_no_child(self):
        parent = parent_record("p1")
        factory = RecordingFactory()
        flow = workflow(FakeTrajectory([parent]), factory=factory)
        result = flow.generate_from_decisions([
            OptimizationDecision(parent_id="p1", decision="REROUTE"),
            OptimizationDecision(parent_id="p1", decision="STOP"),
        ])
        self.assertEqual(result["proposals"], [])
        self.assertEqual(factory.optimize_calls, [])
        self.assertEqual(result["decision_report"]["child_generated"], 0)
        for entry in result["rejected"]:
            self.assertIn("NOT_A_CHILD_DECISION", entry["reasons"])

    def test_incomplete_validate_decision_is_rejected_without_proposal(self):
        """VALIDATE 缺单变量 contract 时必须 fail-closed，不猜参数。"""
        parent = parent_record("p1")
        factory = RecordingFactory()
        flow = workflow(FakeTrajectory([parent]), factory=factory)
        result = flow.generate_from_decisions([
            OptimizationDecision(parent_id="p1", decision="VALIDATE"),
        ])
        self.assertEqual(result["proposals"], [])
        self.assertEqual(factory.optimize_calls, [])
        self.assertIn(
            "VALIDATION_FIELDS_MISSING", result["rejected"][0]["reasons"]
        )

    def test_invalid_or_unknown_parent_decisions_are_rejected(self):
        flow = workflow(FakeTrajectory([parent_record("p1")]))
        result = flow.generate_from_decisions([
            "not-a-decision",
            child_decision("missing-parent"),
        ])
        self.assertEqual(result["proposals"], [])
        reasons = [entry["reasons"] for entry in result["rejected"]]
        self.assertIn(["DECISION_INVALID"], reasons)
        self.assertIn(["PARENT_NOT_FOUND"], reasons)

    def test_inspect_view_is_bounded_and_opportunity_ranked(self):
        rows = [
            parent_record("p1"),
            parent_record("p2", self_correlation={"status": "FAIL"}),
            parent_record("p3", field_source={}),
        ]
        flow = workflow(FakeTrajectory(rows))
        summaries = flow.inspect_optimizer_parents(limit=1)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["parent_id"], "p2")
        self.assertEqual(summaries[0]["opportunity"], "SELF_CORRELATION_REPAIR")

    def test_decision_module_has_no_transport_or_state_ownership(self):
        source = (PACKAGE_ROOT / "optimization_decision.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "WQBClient", "Simulator", "submit_simulation(", "requests.",
            "CheckpointStore", "Trajectory(", "alpha_feed", "alpha_colors",
        ):
            self.assertNotIn(forbidden, source)


    def test_single_variable_decay_validation_emits_robustness_proposal(self):
        field_profile = {
            "id": "field_a",
            "dataset": "fundamental6",
            "type": "MATRIX",
            "description": "已核验字段",
            "semantic_status": "KNOWN",
        }
        parent = parent_record(
            "p-decay",
            settings={"delay": 1, "decay": 4, "truncation": 0.08,
                      "universe": "TOP3000"},
            field_analysis={"field_a": {
                "semantic": "已核验字段", "coverage": None,
                "frequency": None, "data_type": "MATRIX",
            }},
        )
        flow = workflow(FakeTrajectory([parent]), factory=AlphaFactory())
        result = flow.generate_from_decisions(
            [validate_decision("p-decay")], max_candidates=2
        )
        self.assertEqual(result["decision_report"]["validation_requests"], 1)
        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["experiment_stage"], "ROBUSTNESS")
        self.assertEqual(proposal["change_type"], "decay")
        self.assertEqual(proposal["changed_variable"], "decay")
        self.assertEqual(proposal["settings"], {"decay": 5})
        self.assertEqual(proposal["parent_id"], "p-decay")
        self.assertEqual(proposal["settings_variant"]["change_count"], 1)
        self.assertEqual(proposal["settings_variant"]["candidate_value"], 5)
        ok, problems = validate_proposal(
            proposal,
            discovered_fields=[field_profile],
            strict_experiment=True,
            operator_reference={"operators": ["rank", "group_neutralize"],
                                "sha256": "sha"},
            require_economic_integrity=True,
        )
        self.assertEqual(problems, [])
        self.assertTrue(ok)

    def test_window_validation_is_robustness_not_child(self):
        field_profile = {
            "id": "field_a",
            "dataset": "fundamental6",
            "type": "MATRIX",
            "description": "已核验字段",
            "semantic_status": "KNOWN",
        }
        parent = parent_record(
            "p-window",
            expression="-rank(ts_zscore(field_a, 20))",
            template_id="reversal_zscore_20",
            field_analysis={"field_a": {
                "semantic": "已核验字段", "coverage": None,
                "frequency": None, "data_type": "MATRIX",
            }},
        )
        flow = workflow(
            FakeTrajectory([parent]), factory=AlphaFactory(),
            operators=["rank", "ts_zscore", "group_neutralize"],
        )
        shifted = "-rank(ts_zscore(field_a, 60))"
        result = flow.generate_from_decisions([
            validate_decision(
                "p-window", validation_variable="template_window",
                old_value=20, new_value=60,
            )
        ], max_candidates=2)
        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["expression"], shifted)
        self.assertEqual(proposal["change_type"], "window_change")
        self.assertEqual(proposal["experiment_stage"], "ROBUSTNESS")
        self.assertEqual(proposal["numeric_variant"]["slot"], "short_window")
        self.assertEqual(proposal["numeric_variant"]["change_count"], 1)
        # 同样的窗口变化若声明为 CHILD，必须被参数化检查拒绝。
        self.assertIn(
            "PARAMETER_ONLY_CHANGE",
            decision_rejections(
                child_decision("p-window", expression=shifted), parent
            ),
        )
        ok, problems = validate_proposal(
            proposal,
            discovered_fields=[field_profile],
            strict_experiment=True,
            operator_reference={"operators": ["rank", "ts_zscore",
                                              "group_neutralize"],
                                "sha256": "sha"},
            require_economic_integrity=True,
        )
        self.assertEqual(problems, [])
        self.assertTrue(ok)

    def test_decay_and_truncation_in_one_validate_decision_is_rejected(self):
        parent = parent_record("p1")
        flow = workflow(FakeTrajectory([parent]), factory=RecordingFactory())
        result = flow.generate_from_decisions([
            validate_decision(
                "p1", new_value={"decay": 5, "truncation": 0.10}
            ),
        ])
        self.assertEqual(result["proposals"], [])
        self.assertIn(
            "VALIDATION_MULTIPLE_VARIABLES", result["rejected"][0]["reasons"]
        )

    def test_numeric_slots_declare_research_numbers_not_safety_constants(self):
        factory = AlphaFactory()
        template = factory.registry.get("reversal_vol_adjusted")
        self.assertEqual(
            template.research_slot_names, ("delta_window", "vol_window")
        )
        variants = template.numeric_variants(max_variants=3)
        self.assertEqual(len(variants), 3)
        for variant in variants:
            self.assertEqual(variant["change_count"], 1)
            self.assertEqual(variant["source_template"], "reversal_vol_adjusted")
            # 未声明的 divide epsilon 0.001 永远保持字面量。
            self.assertIn("0.001", variant["expression"])
            self.assertNotEqual(variant["expression"], template.expression)
        changed = {
            (variant["slot"], str(variant["candidate_value"]))
            for variant in variants
        }
        self.assertNotIn(("delta_window", "5"), changed)
        self.assertNotIn(("vol_window", "20"), changed)

    def test_numeric_variants_never_form_a_cartesian_product(self):
        template = AlphaFactory().registry.get("quality_smooth_change")
        variants = template.numeric_variants(max_variants=8)
        self.assertEqual(len(variants), 4)
        for variant in variants:
            others = {
                slot.name: slot.default for slot in template.numeric_slots
            }
            others.pop(variant["slot"], None)
            for name, value in others.items():
                self.assertIn(str(value), variant["expression"], name)
            self.assertNotEqual(variant["expression"], template.expression)

    def test_undeclared_numeric_slot_cannot_be_rendered(self):
        template = AlphaFactory().registry.get("reversal_zscore_20")
        self.assertIsNone(template.numeric_slot("epsilon"))
        with self.assertRaises(KeyError):
            template.render_numeric_variant("epsilon", 0.002)
        with self.assertRaises(ValueError):
            template.render_numeric_variant("short_window", 17)


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


class TestNumericVariantIdentityAndDedupe(unittest.TestCase):
    """§24-§32/§49/§55：参数变化不制造机制多样性，并复用现有去重与预算。"""

    @staticmethod
    def window_parent():
        return parent_record(
            "p-window", expression="-rank(ts_zscore(field_a, 20))",
            template_id="reversal_zscore_20",
        )

    @staticmethod
    def window_request(value, *, expression):
        return {
            "parent": TestNumericVariantIdentityAndDedupe.window_parent(),
            "variable": "template_window",
            "old_value": 20,
            "new_value": value,
            "expected_effect": "检验短期反转窗口是否稳定",
            "falsification": "窗口变化后 Sharpe 反向恶化则稳定性假设不成立",
            "reason": "检验短期反转窗口稳定性",
            "expression": expression,
            "settings_override": {},
            "numeric_variant": {
                "source_template": "reversal_zscore_20",
                "slot": "short_window",
                "parent_default_value": 20,
                "candidate_value": value,
                "change_count": 1,
                "reason": "检验短期反转窗口稳定性",
            },
        }

    def test_variant_keeps_the_parent_semantic_mechanism_family(self):
        template = AlphaFactory().registry.get("reversal_zscore_20")
        variants = template.numeric_variants(max_variants=3)
        self.assertTrue(variants)
        parent_proposal = {
            "semantic_mechanism_family": template.family,
            "template_family": template.family,
        }
        for variant in variants:
            self.assertEqual(
                variant["semantic_mechanism_family"], template.family
            )
            family = str(variant["semantic_mechanism_family"]).lower()
            for token in ("5", "20", "60", "window", "decay", "truncation",
                          "threshold"):
                self.assertNotIn(token, family)
            self.assertEqual(
                semantic_mechanism_key({
                    "semantic_mechanism_family": variant["semantic_mechanism_family"],
                    "template_family": template.family,
                    "template_variant_id": variant["template_variant_id"],
                }),
                semantic_mechanism_key(parent_proposal),
            )
        identities = {variant["template_variant_id"] for variant in variants}
        self.assertEqual(len(identities), len(variants))

    def test_validation_proposals_dedupe_identical_expressions(self):
        factory = AlphaFactory()
        template = factory.registry.get("reversal_zscore_20")
        request = self.window_request(
            60,
            expression=template.numeric_slot("short_window").render(
                "-rank(ts_zscore(field_a, 20))", 60
            ),
        )
        proposals = factory.validation_proposals(
            [dict(request), dict(request)],
            {"operators": ["rank", "ts_zscore"], "sha256": "sha"},
            max_candidates=4,
        )
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["expression"], "-rank(ts_zscore(field_a, 60))")

    def test_validation_proposals_are_role_capped_and_bounded(self):
        factory = AlphaFactory()
        template = factory.registry.get("reversal_zscore_20")
        requests = [
            self.window_request(
                value,
                expression=template.numeric_slot("short_window").render(
                    "-rank(ts_zscore(field_a, 20))", value
                ),
            )
            for value in (5, 60)
        ]
        proposals = factory.validation_proposals(
            requests,
            {"operators": ["rank", "ts_zscore"], "sha256": "sha"},
            max_candidates=1,
        )
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["research_role"], "VALIDATION")
        self.assertEqual(proposals[0]["experiment_stage"], "ROBUSTNESS")


if __name__ == "__main__":
    unittest.main()
