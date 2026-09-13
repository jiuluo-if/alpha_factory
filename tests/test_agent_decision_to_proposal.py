"""Agent decision to CHILD proposal tests."""

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
        self.assertEqual(result["decision_results"][0]["outcome"], "GENERATED")
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
            expression="-rank(ts_zscore(field_a, 5))",
            template_id="toy_control_zscore",
            field_analysis={"field_a": {
                "semantic": "已核验字段", "coverage": None,
                "frequency": None, "data_type": "MATRIX",
            }},
        )
        flow = workflow(
            FakeTrajectory([parent]), factory=AlphaFactory(),
            operators=["rank", "ts_zscore", "group_neutralize"],
        )
        shifted = "-rank(ts_zscore(field_a, 22))"
        result = flow.generate_from_decisions([
            validate_decision(
                "p-window", validation_variable="template_window",
                old_value=5, new_value=22,
            )
        ], max_candidates=2)
        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["expression"], shifted)
        self.assertEqual(proposal["change_type"], "window_change")
        self.assertEqual(proposal["experiment_stage"], "ROBUSTNESS")
        self.assertEqual(proposal["numeric_variant"]["slot"], "horizon")
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

    def test_structural_repair_parent_reaches_a_valid_child_proposal(self):
        """P0-A：可修结构 health 失败不得被代码初筛杀死。"""
        field_profile = {
            "id": "field_a", "dataset": "fundamental6", "type": "MATRIX",
            "description": "已核验字段", "semantic_status": "KNOWN",
        }
        for check in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
            health = {"ok": False, "reasons": [f"{check}=FAIL v=0.9"]}
            parent = parent_record(
                "p-repair",
                health=health,
                metrics={
                    "sharpe": 1.1, "fitness": 0.8, "turnover": 0.2,
                    "checks": [
                        {"name": check, "pass": False, "result": "FAIL"},
                        {"name": "SELF_CORRELATION", "pass": None,
                         "result": "PENDING"},
                    ],
                },
                field_analysis={"field_a": {
                    "semantic": "已核验字段", "coverage": None,
                    "frequency": None, "data_type": "MATRIX",
                }},
            )
            admission = optimization_parent_admission(parent)
            self.assertTrue(admission["admitted"], check)
            self.assertEqual(admission["repairable_health_failures"], [check])
            self.assertFalse(admission["submission_health_ok"])
            flow = workflow(
                FakeTrajectory([parent]), factory=AlphaFactory(),
                operators=["rank", "group_neutralize"],
            )
            result = flow.generate_from_decisions(
                [child_decision("p-repair")], max_candidates=1
            )
            self.assertEqual(len(result["proposals"]), 1, check)
            ok, problems = validate_proposal(
                result["proposals"][0],
                discovered_fields=[field_profile],
                strict_experiment=True,
                operator_reference={"operators": ["rank", "group_neutralize"],
                                    "sha256": "sha"},
                require_economic_integrity=True,
            )
            self.assertEqual(problems, [], check)
            self.assertTrue(ok)
            # 能修 ≠ 能提交：同一 parent 仍不满足 SELF_CORRELATION 查询门槛。
            self.assertFalse(pre_self_correlation_eligibility(
                parent["metrics"], delay=1, quality_policy={}, health=health,
            )["eligible"])

    def test_unknown_health_failure_stays_fail_closed(self):
        unknown = parent_record(
            "p-unknown",
            health={"ok": False, "reasons": ["SOME_NEW_FAILURE=FAIL"]},
        )
        admission = optimization_parent_admission(unknown)
        self.assertFalse(admission["admitted"])
        self.assertIn(
            "PARENT_HEALTH_FAILURE_NOT_REPAIRABLE", admission["reasons"]
        )
        undecided = parent_record("p-undecided", health={"ok": None})
        self.assertIn(
            "PARENT_HEALTH_UNKNOWN",
            optimization_parent_admission(undecided)["reasons"],
        )
        self.assertEqual(
            AlphaFactory().screen_optimization_parents([unknown, undecided]), []
        )

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
        template = factory.registry.get("toy_scale_surprise")
        self.assertEqual(
            template.research_slot_names, ("fast_horizon", "slow_horizon")
        )
        variants = template.numeric_variants(max_variants=3)
        self.assertEqual(len(variants), 3)
        for variant in variants:
            self.assertEqual(variant["change_count"], 1)
            self.assertEqual(variant["source_template"], "toy_scale_surprise")
            # 未声明的 divide epsilon 0.001 永远保持字面量。
            self.assertIn("0.001", variant["expression"])
            self.assertNotEqual(variant["expression"], template.expression)
        changed = {
            (variant["slot"], str(variant["candidate_value"]))
            for variant in variants
        }
        self.assertNotIn(("fast_horizon", "5"), changed)
        self.assertNotIn(("slow_horizon", "20"), changed)

    def test_numeric_variants_never_form_a_cartesian_product(self):
        template = AlphaFactory().registry.get("toy_confirmation")
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
        template = AlphaFactory().registry.get("toy_control_rank")
        self.assertIsNone(template.numeric_slot("epsilon"))
        with self.assertRaises(KeyError):
            template.render_numeric_variant("epsilon", 0.002)
        with self.assertRaises(KeyError):
            template.render_numeric_variant("horizon", 17)

    def test_every_template_numeric_literal_is_explicitly_classified(self):
        """P2：固定数字必须显式分类，只有 RESEARCH_SLOT 可轮换。"""
        audit = template_numeric_audit()
        self.assertEqual(audit["problems"], [])
        self.assertTrue(audit["ok"])
        declared = {
            (template.template_id, slot.name)
            for template in DEFAULT_TEMPLATES + ECONOMIC_TEMPLATES
            for slot in template.numeric_slots
        }
        rotatable = {
            (row["template_id"], row["name"]) for row in audit["rotatable"]
        }
        self.assertEqual(rotatable, declared)
        for row in audit["rotatable"]:
            self.assertTrue(row["allowed_values"], row)
            self.assertNotEqual(row["token"], "0.001")
        epsilon_classes = {
            row["class"] for row in audit["rows"] if row["token"] == "0.001"
        }
        self.assertEqual(epsilon_classes, {"SAFETY_CONSTANT"})
