import tempfile
import unittest

from wqb_agent.optimization_decision import OptimizationDecision
from wqb_agent.trial_ledger import SIMULATION_LIFECYCLE_PHASES, TrialLedger


class TestOptimizationSelectionAccounting(unittest.TestCase):
    def test_final_decisions_count_once_and_are_idempotent(self):
        ledger = TrialLedger(None, persist=False)
        stop = OptimizationDecision(parent_id="p-stop", decision="STOP", reason="falsified")
        reroute = OptimizationDecision(parent_id="p-reroute", decision="REROUTE", reason="reroute")

        self.assertTrue(ledger.record_optimization_selection(stop))
        self.assertTrue(ledger.record_optimization_selection(reroute))
        self.assertFalse(ledger.record_optimization_selection(stop))
        summary = ledger.summarize()

        self.assertEqual(summary["selection_trial_count"], 2)
        self.assertEqual(summary["candidate_count"], 0)
        self.assertEqual(summary["trial_count"], 0)

    def test_rejected_and_pruned_decisions_count_without_changing_lifecycle(self):
        ledger = TrialLedger(None, persist=False)
        for decision, outcome in (("CHILD", "REJECTED"), ("VALIDATE", "PRUNED")):
            item = OptimizationDecision(parent_id=f"p-{decision}", decision=decision)
            self.assertTrue(ledger.record_optimization_selection(item, outcome=outcome))

        ledger.record({"candidate_id": "c1", "expression": "rank(x)"}, "generated")
        summary = ledger.summarize()
        self.assertEqual(summary["selection_trial_count"], 2)
        self.assertEqual(summary["candidate_count"], 1)
        self.assertEqual(SIMULATION_LIFECYCLE_PHASES, (
            "simulation_committed", "simulation_submitted",
            "simulation_settled", "research_outcome_settled",
        ))

    def test_persisted_selection_is_deduplicated_by_semantics_not_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = TrialLedger(f"{tmp}/ledger.jsonl")
            decision = OptimizationDecision(parent_id="p1", decision="STOP", reason="no gain")
            self.assertTrue(ledger.record_optimization_selection(decision, timestamp=1))
            self.assertFalse(ledger.record_optimization_selection(decision, timestamp=2))
            self.assertEqual(ledger.summarize()["selection_trial_count"], 1)
