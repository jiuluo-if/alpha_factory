import os
import tempfile
import unittest

from wqb_agent.evidence_status import annotate_evidence
from wqb_agent.identity import candidate_identity
from wqb_agent.search_policy import BudgetAllocator, SearchPolicy
from wqb_agent.search_snapshot import SearchSnapshot
from wqb_agent.state import Experiment
from wqb_agent.trial_ledger import TrialLedger
from wqb_agent.validation_report import (
    build_validation_report,
    default_validation_plan,
    migrate_validation_plan,
    validate_plan,
)


class TestExperimentIdentity(unittest.TestCase):
    def test_candidate_identity_includes_settings(self):
        left = {"round": 1, "expression": "rank(close)", "fields": ["close"], "settings": {"decay": 2}}
        right = dict(left, settings={"decay": 4})
        self.assertNotEqual(candidate_identity(left), candidate_identity(right))

    def test_one_hundred_generated_candidates_are_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = TrialLedger(os.path.join(tmp, "ledger.jsonl"))
            for index in range(100):
                candidate = {"round": 1, "expression": f"rank(field_{index})", "fields": [f"field_{index}"]}
                candidate["candidate_id"] = candidate_identity(candidate)
                ledger.record(candidate, "candidate_generated", outcome="CONSIDERED")
            summary = ledger.summarize()
            self.assertEqual(summary["candidate_generated_count"], 100)
            self.assertEqual(summary["candidate_count"], 100)
            self.assertEqual(summary["unique_candidate_count"], 100)

    def test_rejected_candidates_do_not_collide_without_proposal_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = TrialLedger(os.path.join(tmp, "ledger.jsonl"))
            for decay in (2, 4):
                candidate = {"round": 1, "expression": "rank(close)", "fields": ["close"], "settings": {"decay": decay}}
                candidate["candidate_id"] = candidate_identity(candidate)
                ledger.record(candidate, "candidate_generated", outcome="CONSIDERED")
                ledger.record(candidate, "candidate_rejected", outcome="REJECTED", reason_code="DUPLICATE_LOCAL", reason="duplicate")
            summary = ledger.summarize()
            self.assertEqual(summary["candidate_count"], 2)
            self.assertEqual(summary["candidate_rejected_count"], 2)


class TestBudgetAndRecovery(unittest.TestCase):
    def proposal(self, key="p1"):
        return {"proposal_id": key, "datasets": ["pv1"], "template_family": "trend"}

    def test_local_skip_does_not_consume_simulation_budget(self):
        policy = SearchPolicy({"enabled": True, "max_simulations": 2, "max_pending_per_arm": 10})
        first, second = self.proposal(), self.proposal("p2")
        self.assertTrue(policy.accept(first))
        self.assertTrue(policy.accept(second))
        self.assertTrue(policy.commit(first))
        policy.release(second, status="SKIPPED_LOCAL")
        self.assertEqual(policy.allocator.consumed_budget, 1)
        self.assertEqual(policy.allocator.arms["pv1::trend"]["skipped_local"], 1)

    def test_unknown_remains_committed_and_infra_failure_has_no_reward(self):
        allocator = BudgetAllocator(total_budget=3, max_pending_per_arm=10)
        unknown = self.proposal("unknown")
        self.assertTrue(allocator.reserve(unknown))
        allocator.mark_unknown(unknown)
        self.assertEqual(allocator.consumed_budget, 1)
        failed = self.proposal("infra")
        self.assertTrue(allocator.reserve(failed))
        allocator.mark_failed(failed, outcome="INFRA")
        state = allocator.arms["pv1::trend"]
        self.assertEqual(state["reward_count"], 0)
        self.assertEqual(state["failed_infra"], 1)
        self.assertEqual(allocator.arms["pv1::trend"]["reward_count"], 0)

    def test_restart_restores_family_penalty_and_committed_budget(self):
        policy = SearchPolicy({"enabled": True, "max_simulations": 5, "max_pending_per_arm": 10})
        proposal = self.proposal()
        self.assertTrue(policy.accept(proposal))
        self.assertTrue(policy.commit(proposal))
        snapshot = policy.snapshot()
        restored = SearchPolicy({"enabled": True, "max_simulations": 5, "max_pending_per_arm": 10})
        restored.restore(snapshot)
        self.assertEqual(restored.family_counts, policy.family_counts)
        self.assertEqual(restored.allocator.consumed_budget, 1)

    def test_snapshot_uses_ledger_candidate_count_and_deduplicates_rows(self):
        exp = Experiment(1, "h", "rank(close)", {}, ["close"], ["pv1"])
        exp.candidate_id = "c-1"
        exp.proposal_id = "p-1"
        exp.status = "DONE"
        exp.metrics = {"fitness": .2}
        summary = {"candidate_count": 7, "submitted_count": 1, "family_counts": {"trend": 1}}
        snapshot = SearchSnapshot.from_sources([exp], summary, [exp])
        self.assertEqual(snapshot["candidate_count"], 7)
        self.assertEqual(len(snapshot["proposals"]), 1)


class TestEvidenceAndValidationPlan(unittest.TestCase):
    def test_available_is_not_automatically_pass(self):
        result = annotate_evidence({"status": "AVAILABLE", "value": .62}, status="INCONCLUSIVE")
        self.assertEqual(result["availability"], "AVAILABLE")
        self.assertEqual(result["decision"], "INCONCLUSIVE")
        self.assertNotEqual(result["evidence_status"], "PASS")

    def test_statistical_policy_can_fail_available_evidence(self):
        parent = {"expression": "rank(close)", "status": "DONE", "metrics": {"checks": [{"pass": True}]}}
        plan = default_validation_plan(parent, statistical_policy={"mode": "required_when_available", "min_psr": .999, "min_dsr": .999})
        report = build_validation_report(parent, [], plan, return_series=[-.02, -.01, -.01, -.02, -.01, -.02], trial_summary={"candidate_count": 5, "trial_sharpes": [0.1, 0.2]})
        self.assertEqual(report["statistical_evidence"]["statistical_decision"], "FAIL")
        self.assertNotEqual(report["statistical_evidence"]["statistical_status"], "PASS")

    def test_calculation_without_policy_threshold_is_inconclusive(self):
        parent = {"expression": "rank(close)", "status": "DONE", "metrics": {"checks": [{"pass": True}]}}
        plan = default_validation_plan(parent)
        report = build_validation_report(parent, [], plan, return_series=[.01, .02, .01, .02, .01, .02], trial_summary={"candidate_count": 2, "trial_sharpes": [0.1, 0.2]})
        self.assertEqual(report["statistical_evidence"]["statistical_status"], "INCONCLUSIVE")

    def test_legacy_plan_migrates_to_v3_without_fake_dimension(self):
        legacy = default_validation_plan({"expression": "rank(close)", "settings": {}}, timestamp=1)
        legacy["schema_version"] = 2
        legacy["variables"].append({"variable": "decay_truncation", "reason": "legacy", "budget": 1,
                                     "falsification": "legacy", "stopping_rule": "legacy", "requirement": "REQUIRED"})
        migrated = migrate_validation_plan(legacy)
        self.assertEqual(migrated["schema_version"], 3)
        self.assertNotIn("decay_truncation", {item["variable"] for item in migrated["variables"]})
        self.assertTrue(validate_plan(migrated)[0])


if __name__ == "__main__":
    unittest.main()
