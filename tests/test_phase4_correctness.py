import os
import tempfile
import unittest

from wqb_agent.pnl import correlation_evidence
from wqb_agent.search_policy import BudgetAllocator
from wqb_agent.search_snapshot import SearchSnapshot
from wqb_agent.state import Experiment
from wqb_agent.trial_ledger import TrialLedger
from wqb_agent.validation_report import (
    build_validation_report,
    default_validation_plan,
    deflated_sharpe_ratio,
    pbo_proxy,
    probabilistic_sharpe_ratio,
    validate_plan,
)


def metrics():
    return {"sharpe": 1.2, "fitness": 1.0, "turnover": .2, "margin": .01,
            "drawdown": .1, "checks": [{"name": "ALL", "pass": True}]}


class TestAllocatorLifecycle(unittest.TestCase):
    def proposal(self, name="p1"):
        return {"proposal_id": name, "datasets": ["pv1"], "template_family": "trend"}

    def test_failed_releases_slot_and_unknown_does_not(self):
        allocator = BudgetAllocator(total_budget=3, max_pending_per_arm=1)
        first = self.proposal()
        self.assertTrue(allocator.reserve(first))
        allocator.mark_running(first)
        allocator.mark_failed(first)
        self.assertTrue(allocator.reserve(self.proposal("p2")))
        allocator.mark_unknown(self.proposal("p2"))
        self.assertFalse(allocator.reserve(self.proposal("p3")))

    def test_done_and_unknown_batch_only_unknown_occupies_slot(self):
        allocator = BudgetAllocator(total_budget=4, max_pending_per_arm=1)
        done = self.proposal("done")
        unknown = self.proposal("unknown")
        self.assertTrue(allocator.reserve(done))
        self.assertTrue(allocator.reserve({"proposal_id": "other", "datasets": ["pv2"], "template_family": "trend"}))
        allocator.complete(done)
        allocator.mark_unknown({"proposal_id": "other", "datasets": ["pv2"], "template_family": "trend"})
        self.assertTrue(allocator.reserve(self.proposal("new")))
        self.assertFalse(allocator.reserve({"proposal_id": "other2", "datasets": ["pv2"], "template_family": "trend"}))

    def test_replayed_transition_is_idempotent_and_budget_is_hard(self):
        allocator = BudgetAllocator(total_budget=1)
        proposal = self.proposal()
        self.assertTrue(allocator.reserve(proposal))
        allocator.mark_pending(proposal)
        allocator.mark_pending(proposal)
        allocator.complete(proposal, reward=.5)
        allocator.complete(proposal, reward=.5)
        self.assertEqual(allocator.snapshot()["arms"]["pv1::trend"]["completed"], 1)
        self.assertEqual(allocator.snapshot()["arms"]["pv1::trend"]["reward"], .5)
        self.assertFalse(allocator.reserve(self.proposal("second")))

    def test_restart_snapshot_rebuild_is_equivalent(self):
        first = Experiment(1, "h", "rank(close)", {}, ["close"], ["pv1"])
        first.template_family = "trend"
        first.status = "DONE"
        first.metrics = {"fitness": .4}
        second = Experiment(1, "h", "rank(volume)", {}, ["volume"], ["pv1"])
        second.template_family = "trend"
        second.status = "UNKNOWN"
        one = SearchSnapshot.from_sources([first, second])
        two = SearchSnapshot.from_sources([first, second])
        self.assertEqual(one.allocator_state(10), two.allocator_state(10))


class TestPhase4Evidence(unittest.TestCase):
    def test_rejected_candidates_are_ledger_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = TrialLedger(os.path.join(tmp, "trials.jsonl"))
            proposal = {"proposal_id": "reject-1", "expression": "rank(x)", "fields_used": ["x"]}
            ledger.record(proposal, "candidate_generated", outcome="CONSIDERED")
            ledger.record(proposal, "candidate_rejected", outcome="REJECTED", reason="重复结构")
            summary = ledger.summarize()
            self.assertEqual(summary["candidate_count"], 1)
            self.assertEqual(summary["rejected_candidate_count"], 1)

    def test_plan_hash_changes_when_content_changes(self):
        parent = {"expression": "rank(close)", "submission_fingerprint": "fp", "settings": {"decay": 4}}
        left = default_validation_plan(parent, timestamp=1.0)
        right = default_validation_plan(parent, timestamp=2.0, budget=6)
        self.assertNotEqual(left["plan_id"], right["plan_id"])
        self.assertTrue(validate_plan(left)[0])

    def test_not_applicable_window_is_not_a_failure_dimension(self):
        parent = Experiment(1, "h", "rank(close)", {}, ["close"])
        parent.status = "DONE"
        parent.metrics = metrics()
        plan = default_validation_plan(parent)
        self.assertEqual(next(row for row in plan["variables"] if row["variable"] == "window_locality")["requirement"], "NOT_APPLICABLE")
        self.assertTrue(validate_plan(plan)[0])

    def test_unavailable_dsr_is_not_pass(self):
        result = deflated_sharpe_ratio([], observed_sharpe=1.0)
        self.assertEqual(result["evidence_status"], "UNAVAILABLE")
        self.assertNotEqual(result["status"], "PASS")

    def test_reference_psr_and_proxy_labels_are_stable(self):
        values = [-.01, .02, .01, .03, -.02, .01, .015, -.005, .01, .02]
        result = probabilistic_sharpe_ratio(values, observed_sharpe=1.2)
        self.assertAlmostEqual(result["psr"], .9937524253, places=8)
        proxy = pbo_proxy([[1, 2, 3, 4, 5, 6, 7, 8], [0, 1, 2, 3, 4, 5, 6, 7]])
        self.assertEqual(proxy["method"], "pbo_proxy")
        self.assertEqual(proxy["evidence_status"], "APPROXIMATE")

    def test_date_aligned_correlation_uses_inner_join(self):
        result = correlation_evidence({"2024-01-02": 1, "2024-01-03": 2, "2024-01-04": 3},
                                       {"2024-01-01": 9, "2024-01-02": 2, "2024-01-03": 4, "2024-01-04": 6})
        self.assertEqual(result["overlap_count"], 3)
        self.assertEqual(result["signed_corr"], 1.0)
        self.assertEqual(result["abs_corr"], 1.0)


if __name__ == "__main__":
    unittest.main()
