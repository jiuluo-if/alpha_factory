"""Phase V pre-correlation admission + metric-aware optimization context.

The gate that decides whether a DONE Alpha may be queried for the asynchronous
SELF_CORRELATION endpoint must be a single pure policy shared by the Agent and
``scripts/refresh_self_correlation.py``.  Missing evidence stays UNKNOWN and
never becomes a PASS.
"""

import tempfile
import unittest

from scripts.refresh_self_correlation import (
    load_trajectory_rows,
    pre_correlation_selection,
    select_alpha_ids,
)
from tests.test_agent_flow import make_agent
from wqb_agent.optimization_decision import (
    OptimizationDecision,
    summarize_parent,
    validation_candidate_values,
    validation_rejections,
)
from wqb_agent.pre_correlation import (
    DELAY_THRESHOLDS,
    TURNOVER_FITNESS_FLOOR,
    metric_optimization_context,
    pre_self_correlation_eligibility,
    turnover_bounds,
)
from wqb_agent.state import Experiment

QUALITY = {
    "min_turnover": 0.01,
    "max_turnover": 0.70,
    "max_drawdown": 0.5,
}

PASSING_CHECKS = [
    {"name": "LOW_SHARPE", "pass": True},
    {"name": "LOW_SUB_UNIVERSE_SHARPE", "pass": True},
    {"name": "CONCENTRATED_WEIGHT", "pass": True},
    {"name": "SELF_CORRELATION", "pass": None, "result": "PENDING"},
]

PARENT = {
    "id": "p1",
    "status": "DONE",
    "expression": "rank(field_a)",
    "settings": {"delay": 1, "decay": 4, "truncation": 0.08},
    "health": {"ok": True},
}


def synthetic_metrics(**overrides):
    base = {
        "sharpe": 1.60,
        "fitness": 1.30,
        "returns": 0.05,
        "turnover": 0.25,
        "drawdown": 0.05,
        "margin": 0.0012,
        "checks": [dict(check) for check in PASSING_CHECKS],
    }
    checks = overrides.pop("checks", None)
    base.update(overrides)
    if checks is not None:
        base["checks"] = checks
    return base


def report(**overrides):
    return pre_self_correlation_eligibility(
        synthetic_metrics(**overrides), delay=1, quality_policy=QUALITY,
        health={"ok": True},
    )


def validate_decision(parent_id="p1", **overrides):
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


class TestPreCorrelationEligibility(unittest.TestCase):
    def test_turnover_bounds_are_the_single_shared_source(self):
        self.assertEqual(turnover_bounds(None), (0.01, 0.70))
        self.assertEqual(
            turnover_bounds({"min_turnover": 0.05, "max_turnover": 0.4}),
            (0.05, 0.4),
        )
        within = pre_self_correlation_eligibility(
            synthetic_metrics(turnover=0.05), delay=1,
            quality_policy={"min_turnover": 0.05, "max_turnover": 0.4},
            health={"ok": True},
        )
        self.assertTrue(within["turnover_valid"])
        outside = pre_self_correlation_eligibility(
            synthetic_metrics(turnover=0.05), delay=1,
            quality_policy={"min_turnover": 0.2, "max_turnover": 0.4},
            health={"ok": True},
        )
        self.assertFalse(outside["turnover_valid"])
        self.assertIn("TURNOVER_OUT_OF_RANGE", outside["reasons"])

    def test_delay_one_metric_line_is_strictly_greater(self):
        self.assertTrue(report(sharpe=1.26, fitness=1.01)["eligible"])
        edge = report(sharpe=1.25, fitness=1.0)
        self.assertFalse(edge["eligible"])
        self.assertIn("SHARPE_BELOW_THRESHOLD", edge["reasons"])
        self.assertIn("FITNESS_BELOW_THRESHOLD", edge["reasons"])

    def test_delay_zero_requires_higher_thresholds(self):
        self.assertEqual(DELAY_THRESHOLDS[0]["sharpe"], 2.0)
        self.assertEqual(DELAY_THRESHOLDS[0]["fitness"], 1.5)
        delay_zero = pre_self_correlation_eligibility(
            synthetic_metrics(sharpe=1.60, fitness=1.30), delay=0,
            quality_policy=QUALITY, health={"ok": True},
        )
        self.assertFalse(delay_zero["eligible"])
        self.assertIn("SHARPE_BELOW_THRESHOLD", delay_zero["reasons"])
        passing = pre_self_correlation_eligibility(
            synthetic_metrics(sharpe=2.01, fitness=1.51), delay=0,
            quality_policy=QUALITY, health={"ok": True},
        )
        self.assertTrue(passing["eligible"])

    def test_unknown_delay_is_fail_closed(self):
        for delay in (None, 2, "delay-1", True, 1.5):
            outcome = pre_self_correlation_eligibility(
                synthetic_metrics(), delay=delay, quality_policy=QUALITY,
                health={"ok": True},
            )
            self.assertFalse(outcome["eligible"], delay)
            self.assertIn("DELAY_UNKNOWN", outcome["reasons"])

    def test_non_positive_returns_block_query(self):
        for returns in (0.0, -0.05):
            outcome = report(returns=returns)
            self.assertFalse(outcome["eligible"])
            self.assertIn("RETURNS_NOT_POSITIVE", outcome["reasons"])
        self.assertTrue(report(returns=1e-9)["returns_positive"])

    def test_turnover_and_drawdown_bounds_block_query(self):
        for turnover in (0.005, 0.75):
            outcome = report(turnover=turnover)
            self.assertFalse(outcome["eligible"], turnover)
            self.assertIn("TURNOVER_OUT_OF_RANGE", outcome["reasons"])
        failing_drawdown = report(drawdown=0.6)
        self.assertFalse(failing_drawdown["eligible"])
        self.assertIn("DRAWDOWN_EXCEEDS_LIMIT", failing_drawdown["reasons"])

    def test_health_and_non_correlation_checks_stay_fail_closed(self):
        unhealthy = pre_self_correlation_eligibility(
            synthetic_metrics(), delay=1, quality_policy=QUALITY,
            health={"ok": False},
        )
        self.assertFalse(unhealthy["eligible"])
        self.assertIn("HEALTH_NOT_OK", unhealthy["reasons"])
        unknown_health = pre_self_correlation_eligibility(
            synthetic_metrics(), delay=1, quality_policy=QUALITY, health=None,
        )
        self.assertIn("HEALTH_UNKNOWN", unknown_health["reasons"])
        failing_check = report(checks=[
            {"name": "CONCENTRATED_WEIGHT", "pass": False},
            {"name": "SELF_CORRELATION", "pass": None, "result": "PENDING"},
        ])
        self.assertFalse(failing_check["eligible"])
        self.assertIn("NON_CORRELATION_CHECKS_NOT_PASS", failing_check["reasons"])
        pending_other = report(checks=[
            {"name": "LOW_SHARPE", "pass": None, "result": "PENDING"},
            {"name": "SELF_CORRELATION", "pass": None, "result": "PENDING"},
        ])
        self.assertFalse(pending_other["eligible"])

    def test_low_sub_universe_sharpe_blocks_the_query(self):
        outcome = report(checks=[
            {"name": "LOW_SUB_UNIVERSE_SHARPE", "pass": False},
            {"name": "SELF_CORRELATION", "pass": None, "result": "PENDING"},
        ])
        self.assertFalse(outcome["eligible"])
        self.assertIn("NON_CORRELATION_CHECKS_NOT_PASS", outcome["reasons"])

    def test_missing_metrics_stay_unknown_not_pass(self):
        outcome = pre_self_correlation_eligibility(
            {}, delay=1, quality_policy=QUALITY, health={"ok": True},
        )
        self.assertFalse(outcome["eligible"])
        for reason in ("SHARPE_MISSING", "FITNESS_MISSING", "RETURNS_MISSING",
                       "TURNOVER_MISSING", "DRAWDOWN_MISSING"):
            self.assertIn(reason, outcome["reasons"])

    def test_pending_self_correlation_is_the_reason_to_query(self):
        outcome = report()
        self.assertTrue(outcome["eligible"])
        self.assertTrue(outcome["non_correlation_checks_pass"])


class TestMetricOptimizationContext(unittest.TestCase):
    def test_concentrated_weight_parent_requires_structural_repair(self):
        context = metric_optimization_context(
            synthetic_metrics(checks=[
                {"name": "CONCENTRATED_WEIGHT", "pass": False},
                {"name": "SELF_CORRELATION", "pass": None, "result": "PENDING"},
            ]),
            delay=1, quality_policy=QUALITY, health={"ok": True},
        )
        self.assertFalse(context["pre_correlation_eligible"])
        self.assertEqual(context["readiness"], "STRUCTURAL_REPAIR_REQUIRED")
        self.assertEqual(context["structural_blockers"], ["CONCENTRATED_WEIGHT"])
        self.assertIn("CONCENTRATION_REPAIR", context["opportunities"])

    def test_low_sub_universe_sharpe_needs_structure_not_a_query(self):
        context = metric_optimization_context(
            synthetic_metrics(sharpe=1.50, fitness=1.20, checks=[
                {"name": "LOW_SUB_UNIVERSE_SHARPE", "pass": False},
                {"name": "SELF_CORRELATION", "pass": None, "result": "PENDING"},
            ]),
            delay=1, quality_policy=QUALITY, health={"ok": True},
        )
        self.assertFalse(context["pre_correlation_eligible"])
        self.assertEqual(context["readiness"], "STRUCTURAL_REPAIR_REQUIRED")
        self.assertEqual(
            context["structural_blockers"], ["LOW_SUB_UNIVERSE_SHARPE"]
        )
        self.assertIn("SUB_UNIVERSE_REPAIR", context["opportunities"])

    def test_repaired_parent_is_ready_for_self_correlation(self):
        context = metric_optimization_context(
            synthetic_metrics(sharpe=1.50, fitness=1.20, turnover=0.18),
            delay=1, quality_policy=QUALITY, health={"ok": True},
        )
        self.assertTrue(context["pre_correlation_eligible"])
        self.assertEqual(context["readiness"], "PRE_CORRELATION_READY")
        self.assertEqual(context["blocking_checks"], [])

    def test_turnover_efficiency_hint_tracks_the_0_125_floor(self):
        self.assertEqual(TURNOVER_FITNESS_FLOOR, 0.125)
        penalized = metric_optimization_context(
            synthetic_metrics(sharpe=1.60, fitness=0.98, turnover=0.40),
            delay=1, quality_policy=QUALITY, health={"ok": True},
        )
        self.assertTrue(penalized["turnover_penalty_active"])
        self.assertTrue(penalized["fitness_turnover_efficiency_hint"])
        self.assertIn("TURNOVER_EFFICIENCY", penalized["opportunities"])
        self.assertAlmostEqual(penalized["turnover_distance_to_0_125"], 0.275)

        cheap = metric_optimization_context(
            synthetic_metrics(sharpe=1.60, fitness=0.98, turnover=0.10),
            delay=1, quality_policy=QUALITY, health={"ok": True},
        )
        self.assertFalse(cheap["turnover_penalty_active"])
        self.assertFalse(cheap["fitness_turnover_efficiency_hint"])
        self.assertNotIn("TURNOVER_EFFICIENCY", cheap["opportunities"])
        self.assertLess(cheap["turnover_distance_to_0_125"], 0)

    def test_numeric_validation_candidate_band(self):
        context = metric_optimization_context(
            synthetic_metrics(sharpe=1.60, fitness=0.90, turnover=0.40),
            delay=1, quality_policy=QUALITY, health={"ok": True},
        )
        self.assertEqual(context["readiness"], "NUMERIC_VALIDATION_CANDIDATE")

    def test_drawdown_headroom_is_derived_not_recomputed(self):
        context = metric_optimization_context(
            synthetic_metrics(drawdown=0.20), delay=1,
            quality_policy=QUALITY, health={"ok": True},
        )
        self.assertAlmostEqual(context["drawdown_headroom"], 0.30)
        self.assertEqual(context["drawdown"], 0.20)


class TestAgentAndScriptSelectorAgreement(unittest.TestCase):
    def test_agent_and_script_selector_agree_on_settled_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent, _client = make_agent(tmpdir, rounds=1)
            canonical = Experiment(
                round=1, hypothesis_id="h-1", expression="rank(field_a)",
                settings={"delay": 1}, fields_used=["field_a"],
                status="DONE", alpha_id="alpha-settled",
                metrics={"checks": [{"name": "SELF_CORRELATION", "pass": None}]},
            )
            agent.trajectory.add(canonical)
            self.assertEqual(len(agent.trajectory.experiments), 1)
            # Production aggregates the settled evidence onto the same
            # Experiment instance, then persists one RESEARCH_SETTLED revision.
            canonical.metrics = synthetic_metrics()
            canonical.health = {"ok": True}
            self.assertTrue(agent.trajectory.settle(canonical))

            ineligible = Experiment(
                round=1, hypothesis_id="h-2", expression="rank(field_b)",
                settings={"delay": 1}, fields_used=["field_b"],
                status="DONE", alpha_id="alpha-negative-returns",
                metrics=synthetic_metrics(returns=-0.01),
                health={"ok": True},
            )
            agent.trajectory.add(ineligible)

            agent_ids = agent._pre_correlation_candidates()
            rows = load_trajectory_rows(tmpdir, window=agent.trajectory.max_len)
            script_ids = select_alpha_ids(
                rows, 0, 10 ** 12, delay=1, quality_policy=agent.quality_policy
            )
            selection = pre_correlation_selection(
                rows, 0, 10 ** 12, delay=1, quality_policy=agent.quality_policy
            )
        self.assertEqual(agent_ids, script_ids)
        self.assertEqual(agent_ids, ["alpha-settled"])
        self.assertEqual(selection["eligible"], 1)
        self.assertEqual(selection["reason_counts"], {"RETURNS_NOT_POSITIVE": 1})
        self.assertEqual(selection["alpha_ids"], ["alpha-settled"])


class TestValidationContract(unittest.TestCase):
    def setUp(self):
        self.parent = dict(PARENT)
        self.parent["metrics"] = synthetic_metrics()

    def test_single_variable_decay_validation_is_accepted(self):
        decision = validate_decision()
        self.assertEqual(
            validation_rejections(
                decision, self.parent,
                allowed_values=validation_candidate_values("decay", current=4),
            ),
            [],
        )

    def test_decay_and_truncation_together_are_rejected(self):
        decision = validate_decision(new_value={"decay": 5, "truncation": 0.10})
        self.assertIn(
            "VALIDATION_MULTIPLE_VARIABLES",
            validation_rejections(decision, self.parent),
        )

    def test_out_of_pool_or_unknown_variable_is_rejected(self):
        out_of_pool = validate_decision(new_value=73)
        self.assertIn(
            "VALIDATION_NEW_VALUE_OUT_OF_POOL",
            validation_rejections(
                out_of_pool, self.parent,
                allowed_values=validation_candidate_values("decay", current=4),
            ),
        )
        unknown = validate_decision(validation_variable="window_size")
        self.assertIn("VALIDATION_VARIABLE_UNKNOWN",
                      validation_rejections(unknown, self.parent))
        missing = validate_decision(reason="")
        self.assertIn("VALIDATION_FIELDS_MISSING",
                      validation_rejections(missing, self.parent))

    def test_universe_validation_needs_an_explicit_justification(self):
        decision = validate_decision(
            validation_variable="universe", old_value="TOP3000",
            new_value="TOP1000",
        )
        self.assertIn("VALIDATION_UNIVERSE_NOT_JUSTIFIED",
                      validation_rejections(decision, self.parent))
        self.assertEqual(
            validation_rejections(decision, self.parent, allow_universe=True,
                                  allowed_values=("TOP1000",)),
            [],
        )

    def test_bounded_candidate_pools_are_single_step(self):
        self.assertEqual(validation_candidate_values("decay", current=4), (3, 5))
        self.assertEqual(validation_candidate_values("decay", current=0), (1,))
        self.assertEqual(validation_candidate_values("decay", current=10), (9,))
        self.assertEqual(
            validation_candidate_values("truncation", current=0.08), (0.06, 0.10)
        )
        self.assertEqual(validation_candidate_values("universe", current="TOP3000"), ())
        self.assertEqual(validation_candidate_values("decay", current=None), ())

    def test_truncation_outside_the_whitelist_is_rejected(self):
        decision = validate_decision(
            validation_variable="truncation", old_value=0.08, new_value=0.09
        )
        self.assertIn(
            "VALIDATION_NEW_VALUE_OUT_OF_POOL",
            validation_rejections(
                decision, self.parent,
                allowed_values=validation_candidate_values("truncation", current=0.08),
            ),
        )

    def test_decision_identity_is_checked_before_pool_membership(self):
        decision = validate_decision(parent_id="other")
        self.assertIn("PARENT_IDENTITY_MISMATCH",
                      validation_rejections(decision, self.parent))

    def test_summarize_parent_carries_metric_optimization_context(self):
        summary = summarize_parent(self.parent, delay=1, quality_policy=QUALITY)
        context = summary["metric_optimization_context"]
        self.assertEqual(context["readiness"], "PRE_CORRELATION_READY")
        self.assertEqual(context["delay"], 1)
        self.assertTrue(context["pre_correlation_eligible"])
