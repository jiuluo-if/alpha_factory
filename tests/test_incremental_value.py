import json
import os
import tempfile
import unittest

from wqb_agent.incremental_value import (
    build_incremental_value,
    select_trusted_pool,
    behavior_clusters,
)
from wqb_agent.alpha_pool import build_pool_snapshot
from wqb_agent.incremental_policy import incremental_gate
from wqb_agent.behavior import extract_behavior_series
from wqb_agent.research_evidence import ResearchEvidenceBundle, classify_research
from wqb_agent.robustness import evaluate_robustness, retention
from wqb_agent.search_calibration import SearchPolicyReplay, reward_v2, build_search_calibration
from wqb_agent.search_outcome import SearchOutcome, extract_statistical_decision, reward_v1, resolve_reward
from wqb_agent.search_policy import SearchPolicy
from wqb_agent.submission import SubmissionPool, submission_eligibility
from wqb_agent.state import Experiment
from wqb_agent.trial_ledger import TrialLedger
from wqb_agent.validation_report import build_validation_report, default_validation_plan
from wqb_agent.yearly import build_yearly_evidence


class TestIncrementalValue(unittest.TestCase):
    def test_reward_recovery_precedence_is_explicit(self):
        self.assertEqual(resolve_reward({"reward": 1.0}, {"reward": 0.2}, 0.1)["quality"], "FINAL_EVIDENCE")
        self.assertEqual(resolve_reward(None, {"reward": 0.2}, 0.1)["quality"], "PROVISIONAL_EVIDENCE")
        self.assertEqual(resolve_reward(None, None, 0.1)["quality"], "LEGACY_APPROXIMATE")
    def test_calibration_does_not_report_zero_behavior_clusters(self):
        report = build_search_calibration({"submitted_count": 1}, outcomes=[{"proposal_id": "p"}])
        self.assertNotIn("behavior_cluster_count", report)
        self.assertNotIn("mean_cluster_size", report)
    def test_incremental_policy_gate_has_explicit_modes(self):
        evidence = {"availability": "AVAILABLE", "decision": "FAIL"}
        self.assertFalse(incremental_gate(evidence, "required_when_available")["eligible"])
        self.assertTrue(incremental_gate(evidence, "advisory")["eligible"])
        self.assertFalse(incremental_gate({"availability": "UNAVAILABLE", "decision": "UNAVAILABLE"}, "required")["eligible"])

    def test_behavior_series_missing_pnl_is_unavailable(self):
        result = extract_behavior_series({"metrics": {"returns": 0.2}, "yearly_evidence": {}})
        self.assertEqual(result["availability"], "UNAVAILABLE")
        self.assertIsNone(result["series"])

    def test_behavior_series_accepts_live_verified_pnl_only(self):
        result = extract_behavior_series({
            "pnl": {"status": "LIVE_VERIFIED", "series": {"2024-01-01": 0.1}},
        })
        self.assertEqual(result["availability"], "AVAILABLE")
        self.assertEqual(result["source"], "LIVE_VERIFIED_PNL")

    def test_pool_snapshot_as_of_excludes_unknown_and_future_members(self):
        snapshot = build_pool_snapshot([
            {"alpha_id": "known", "status": "DONE", "checks_passed": True,
             "identity": "id-1", "behavior_series": {"a": 1}, "pool_entered_at": 5},
            {"alpha_id": "missing-time", "status": "DONE", "checks_passed": True,
             "identity": "id-2", "behavior_series": {"a": 1}},
            {"alpha_id": "future", "status": "DONE", "checks_passed": True,
             "identity": "id-3", "behavior_series": {"a": 1}, "pool_entered_at": 20},
        ], as_of=10, snapshot_id="snap-1")
        self.assertEqual(snapshot.snapshot_id, "snap-1")
        self.assertEqual([row["alpha_id"] for row in snapshot.members], ["known"])

    def test_trusted_pool_as_of_excludes_unknown_timestamp(self):
        rows = select_trusted_pool([
            {"alpha_id": "unknown", "status": "DONE", "checks_passed": True,
             "identity": "i", "series": {"a": 1}},
        ], as_of=10)
        self.assertEqual(rows, [])

    def test_submission_eligibility_exposes_incremental_reason(self):
        result = submission_eligibility(
            platform_pass=True, health=True, validation=True, yearly=True,
            incremental={"availability": "AVAILABLE", "decision": "FAIL"},
            incremental_mode="required_when_available",
        )
        self.assertFalse(result["eligible"])
        self.assertIn("incremental_value:FAIL", result["reasons"])

    def test_advisory_incremental_fail_is_allowed_with_reason(self):
        result = submission_eligibility(
            platform_pass=True, health=True, validation=True, yearly=True,
            incremental={"availability": "AVAILABLE", "decision": "FAIL"},
            incremental_mode="advisory",
        )
        self.assertTrue(result["eligible"])
        self.assertIn("incremental_value:FAIL", result["reasons"])

    def test_semantic_identical_settlement_ignores_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = TrialLedger(os.path.join(tmp, "ledger.jsonl"))
            trial = Experiment(1, "h", "rank(x)", {}, ["x"])
            trial.proposal_id = "p1"
            ledger.record_outcome_settled(trial, reward=0.8, timestamp=1,
                                          incremental_decision="PASS")
            ledger.record_outcome_settled(trial, reward=0.8, timestamp=2,
                                          incremental_decision="PASS")
            with open(ledger.path, encoding="utf-8") as handle:
                self.assertEqual(len(handle.readlines()), 1)

    def test_legacy_fitness_reward_is_marked_approximate(self):
        exp = Experiment(1, "h", "rank(x)", {}, ["x"])
        exp.status = "DONE"
        exp.metrics = {"fitness": 0.4, "sharpe": 0.4}
        outcome = SearchOutcome.from_experiment(exp)
        self.assertEqual(outcome.as_dict()["reward_quality"], "LEGACY_APPROXIMATE")

    def test_round_one_replay_cannot_select_round_two_candidate(self):
        replay = SearchPolicyReplay([
            {"proposal_id": "r2", "round": 2, "candidate_available_at": 2,
             "novelty": 100, "reward": 1.0},
            {"proposal_id": "r1", "round": 1, "candidate_available_at": 1,
             "novelty": 0, "reward": 0.1},
        ])
        result = replay.run(checkpoints=(1,))
        self.assertEqual(result["selected_proposal_ids"][0], "r1")

    def test_reward_is_observed_only_after_settlement(self):
        replay = SearchPolicyReplay([
            {"proposal_id": "a", "candidate_available_at": 1,
             "outcome_observed_at": 2, "reward": 1.0},
            {"proposal_id": "b", "candidate_available_at": 2,
             "outcome_observed_at": 2, "reward": 0.0},
        ])
        result = replay.run(checkpoints=(1, 2))
        self.assertEqual(result["observed_history_at_checkpoints"]["1"], {})
        self.assertEqual(result["observed_history_at_checkpoints"]["2"]["unknown"], [1.0])

    def test_nested_statistical_decision_is_extracted(self):
        report = {"statistical_evidence": {"statistical_decision": "PASS"}}
        self.assertEqual(extract_statistical_decision(report), "PASS")

    def test_stable_and_statistical_pass_get_full_reward(self):
        self.assertEqual(reward_v1(status="DONE", infrastructure_failure=False,
                                   base_quality="STABLE", robustness="PASS",
                                   statistical_decision="PASS"), 1.0)

    def test_provisional_settlement_replaces_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = TrialLedger(os.path.join(tmp, "ledger.jsonl"))
            trial = {"proposal_id": "p1", "candidate_id": "c1", "expression": "x",
                     "status": "DONE", "metrics": {"fitness": 1}}
            ledger.record(trial, "simulation_settled", outcome="DONE", timestamp=1,
                          reason="provisional", reason_code="PROVISIONAL")
            ledger.record_outcome_settled(trial, reward=0.85, base_quality="STABLE",
                                          robustness="PASS", statistical_decision="PASS",
                                          incremental_decision="PASS", timestamp=2)
            ledger.record_outcome_settled(trial, reward=1.0, base_quality="STABLE",
                                          robustness="PASS", statistical_decision="PASS",
                                          incremental_decision="PASS", timestamp=3)
            summary = ledger.summarize()
            self.assertEqual(summary["settled_observation_count"], 1)
            self.assertEqual(summary["settled_rewards"]["p1"], 1.0)

    def test_low_sharpe_retention_fails_even_when_checks_pass(self):
        evidence = evaluate_robustness("window", {"sharpe": 1.0, "fitness": .8,
            "turnover": .2, "drawdown": .2}, {"sharpe": .4, "fitness": .8,
            "turnover": .2, "drawdown": .2}, {"min_sharpe_retention": .7,
            "min_fitness_retention": .6, "max_turnover_multiple": 1.5,
            "max_drawdown_multiple": 1.5, "require_checks_passed": True}, True)
        self.assertEqual(evidence.decision, "FAIL")

    def test_retention_criteria_pass(self):
        evidence = evaluate_robustness("window", {"sharpe": 1.0, "fitness": .8,
            "turnover": .2, "drawdown": .2}, {"sharpe": .8, "fitness": .7,
            "turnover": .25, "drawdown": .25}, {"min_sharpe_retention": .7,
            "min_fitness_retention": .6, "max_turnover_multiple": 1.5,
            "max_drawdown_multiple": 1.5, "require_checks_passed": True}, True)
        self.assertEqual(evidence.decision, "PASS")

    def test_missing_parent_metric_is_unavailable(self):
        self.assertIsNone(retention(None, 1.0, direction="up"))

    def test_negative_parent_uses_absolute_delta_not_ratio(self):
        self.assertIsNone(retention(-1.0, -2.0, direction="up"))

    def test_acceptance_criteria_change_changes_plan_id(self):
        parent = {"expression": "x", "settings": {}, "fields_used": []}
        first = default_validation_plan(parent, robustness_policy={"min_sharpe_retention": .7})
        second = default_validation_plan(parent, robustness_policy={"min_sharpe_retention": .8})
        self.assertNotEqual(first["plan_id"], second["plan_id"])

    def test_date_overlap_short_is_unavailable(self):
        evidence = build_incremental_value("candidate", {"2024-01-01": 1}, [], min_overlap=2)
        self.assertEqual(evidence.availability, "UNAVAILABLE")

    def test_high_abs_correlation_fails_incremental(self):
        series = {str(i): float(i) for i in range(4)}
        pool = [{"alpha_id": "old", "series": {str(i): float(i) for i in range(4)}}]
        evidence = build_incremental_value("new", series, pool, min_overlap=4,
                                           max_abs_correlation=.7)
        self.assertEqual(evidence.decision, "FAIL")

    def test_negative_high_correlation_uses_absolute_value(self):
        series = {str(i): float(i) for i in range(4)}
        pool = [{"alpha_id": "old", "series": {str(i): float(3-i) for i in range(4)}}]
        evidence = build_incremental_value("new", series, pool, min_overlap=4,
                                           max_abs_correlation=.7)
        self.assertEqual(evidence.decision, "FAIL")

    def test_low_correlation_passes_incremental(self):
        evidence = build_incremental_value("new", {"a": 1, "b": 0, "c": 1, "d": 0},
            [{"alpha_id": "old", "series": {"a": 0, "b": 1, "c": 2, "d": 3}}],
            min_overlap=4, max_abs_correlation=.7)
        self.assertEqual(evidence.decision, "PASS")

    def test_failed_alpha_not_in_trusted_pool(self):
        pool = select_trusted_pool([{"alpha_id": "bad", "status": "FAILED",
                                     "metrics": {}, "series": {}}])
        self.assertEqual(pool, [])

    def test_future_alpha_not_in_pool_snapshot(self):
        pool = select_trusted_pool([{"alpha_id": "future", "status": "DONE",
                                     "checks_passed": True, "identity": "x",
                                     "pool_entered_at": 10}], as_of=5)
        self.assertEqual(pool, [])

    def test_structural_novelty_does_not_create_behavioral_pass(self):
        evidence = build_incremental_value("new", {}, [], min_overlap=1)
        self.assertEqual(evidence.decision, "INCONCLUSIVE")

    def test_behavior_cluster_is_deterministic(self):
        clusters = behavior_clusters([("b", "a", .9), ("c", "b", .9)], threshold=.7)
        self.assertEqual(clusters["a"], clusters["c"])

    def test_effective_trial_proxy_is_explicit(self):
        bundle = ResearchEvidenceBundle.from_parts({"raw_trial_count": 8}, {}, {}, {}, {}, {})
        self.assertEqual(bundle.as_dict()["effective_trial_count"]["quality"], "APPROXIMATE")

    def test_one_year_is_not_cross_year_verified(self):
        evidence = build_yearly_evidence({"is": {"yearlyData": [{"year": 2024,
            "sharpe": 1, "fitness": 1, "turnover": .2}]}}, min_years=2)
        self.assertNotEqual(evidence["coverage_status"], "VERIFIED")

    def test_reward_v2_is_offline_only(self):
        self.assertGreater(reward_v2(reward=0.5, incremental_decision="PASS"), .5)
        self.assertNotEqual(reward_v2(reward=0.5, incremental_decision="FAIL"), 0.0)

    def test_reward_v1_and_v2_replay_can_be_compared(self):
        replay = SearchPolicyReplay([{"proposal_id": "a", "candidate_available_at": 1,
            "reward": .5, "reward_v2": .8}])
        result = replay.compare_rewards()
        self.assertEqual(result["reward_v1"], .5)
        self.assertEqual(result["reward_v2"], .8)

    def test_bundle_has_no_decision_logic(self):
        bundle = ResearchEvidenceBundle.from_parts({}, {}, {}, {}, {}, {})
        self.assertFalse(hasattr(bundle, "decide"))

    def test_classification_requires_independent_dimensions(self):
        self.assertEqual(classify_research("PROMISING", "PASS", "PASS", "PASS", "PASS"),
                         "PORTFOLIO_CANDIDATE")
        self.assertNotEqual(classify_research("STABLE", "PASS", "FAIL", "PASS", "PASS"),
                            "PORTFOLIO_CANDIDATE")

    def test_replay_rejects_future_observation_timestamp(self):
        replay = SearchPolicyReplay([{"proposal_id": "a", "candidate_available_at": 1,
            "outcome_observed_at": 5, "decision_timestamp": 2, "reward": 1}])
        with self.assertRaises(ValueError):
            replay.run()

    def test_replay_pool_snapshot_excludes_future_alpha(self):
        replay = SearchPolicyReplay(
            [{"proposal_id": "a", "candidate_available_at": 1, "reward": 0}],
            pool=[{"alpha_id": "old", "pool_entered_at": 1},
                  {"alpha_id": "future", "pool_entered_at": 2}],
        )
        result = replay.run(checkpoints=(1,))
        self.assertEqual(result["pool_snapshot_at_checkpoints"]["1"], ["old"])

    def test_validation_report_requires_retention_not_only_checks(self):
        parent = {"expression": "rank(ts_mean(x, 5))", "status": "DONE",
                  "metrics": {"sharpe": 1.0, "fitness": 1.0,
                               "turnover": .2, "drawdown": .2,
                               "checks": [{"name": "ALL", "pass": True}]}}
        plan = default_validation_plan(parent)
        child = {"status": "DONE", "changed_variable": "window_locality",
                 "metrics": {"sharpe": .2, "fitness": .8,
                             "turnover": .2, "drawdown": .2,
                             "checks": [{"name": "ALL", "pass": True}]}}
        report = build_validation_report(parent, [child], plan,
                                         yearly_evidence={"status": "VERIFIED", "stable": True},
                                         platform_evidence={})
        self.assertEqual(report["dimensions"]["window_locality"]["status"], "FAIL")

    def test_allocator_replaces_final_reward_without_new_observation(self):
        policy = SearchPolicy({"enabled": True, "max_simulations": 2,
                               "max_pending_per_arm": 2})
        proposal = {"proposal_id": "p", "datasets": ["pv1"], "template_family": "trend"}
        self.assertTrue(policy.accept(proposal))
        self.assertTrue(policy.commit(proposal))
        policy.release(proposal, status="DONE", reward=.5)
        self.assertTrue(policy.replace_reward(proposal, .85))
        state = policy.snapshot()["arms"]["pv1::trend"]
        self.assertEqual(state["reward_count"], 1)
        self.assertEqual(state["reward_sum"], .85)

    def test_submission_record_exposes_unknown_incremental_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            exp = Experiment(1, "h", "rank(x)", {}, ["x"])
            exp.status, exp.alpha_id, exp.proposal_id = "DONE", "alpha", "proposal"
            exp.metrics = {"sharpe": 2, "fitness": 2, "turnover": .1, "margin": .1}
            exp.research_classification = "STABLE"
            pool = SubmissionPool(tmp)
            pool.upsert_many([(exp, "EXCELLENT", {"status": "PASS"}, None)])
            with open(os.path.join(tmp, "submission_pool.json"), encoding="utf-8") as handle:
                record = json.load(handle)["candidates"][0]
            self.assertEqual(record["incremental_status"], "UNKNOWN")
            self.assertEqual(record["submission"], "MANUAL_REQUIRED")


if __name__ == "__main__":
    unittest.main()
