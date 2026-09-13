import unittest
from unittest.mock import Mock

from wqb_agent.agent import Agent
from wqb_agent.optimization_decision import OptimizationDecision


class TestAgentOptimizationSelectionBridge(unittest.TestCase):
    def test_bridge_accounts_finalized_decisions_once(self):
        agent = object.__new__(Agent)
        agent.trial_ledger = Mock()
        agent.memory = Mock()
        agent.optimizer_workflow = Mock()
        agent.optimizer_workflow.generate_from_decisions.return_value = {
            "accepted": [{"parent_id": "p-child"}],
            "rejected": [
                {"parent_id": "p-stop", "reasons": ["NOT_A_CHILD_DECISION"]},
                {"parent_id": "p-pruned", "reasons": ["PRUNED_BY_GATE"]},
            ],
            "decision_results": [
                {"parent_id": "p-child", "decision": "CHILD", "outcome": "GENERATED"},
                {"parent_id": "p-stop", "decision": "STOP", "outcome": "STOP"},
                {"parent_id": "p-pruned", "decision": "VALIDATE", "outcome": "PRUNED"},
            ],
        }
        decisions = [
            OptimizationDecision(parent_id="p-child", decision="CHILD"),
            OptimizationDecision(parent_id="p-stop", decision="STOP"),
            OptimizationDecision(parent_id="p-pruned", decision="VALIDATE"),
        ]

        Agent.propose_optimization(agent, decisions)

        outcomes = [call.kwargs["outcome"] for call in agent.trial_ledger.record_optimization_selection.call_args_list]
        self.assertEqual(outcomes, ["GENERATED", "STOP", "PRUNED"])

    def test_bridge_uses_generated_validate_result_instead_of_accepted_list(self):
        agent = object.__new__(Agent)
        agent.trial_ledger = Mock()
        agent.memory = Mock()
        agent.optimizer_workflow = Mock()
        agent.optimizer_workflow.generate_from_decisions.return_value = {
            "accepted": [], "rejected": [],
            "decision_results": [{
                "parent_id": "p-validate", "decision": "VALIDATE", "outcome": "GENERATED",
            }],
        }
        decision = OptimizationDecision(parent_id="p-validate", decision="VALIDATE",
                                        validation_variable="decay", expected_effect="stable",
                                        falsification="fails", reason="check")

        Agent.propose_optimization(agent, [decision])

        self.assertEqual(
            agent.trial_ledger.record_optimization_selection.call_args.kwargs["outcome"],
            "GENERATED",
        )

    def test_memory_projection_failure_does_not_erase_ledger_fact(self):
        agent = object.__new__(Agent)
        agent.trial_ledger = Mock()
        agent.memory = Mock()
        agent.memory.add_short_term.side_effect = RuntimeError("projection unavailable")
        agent.optimizer_workflow = Mock()
        agent.optimizer_workflow.generate_from_decisions.return_value = {
            "accepted": [], "rejected": [{"parent_id": "p1", "reasons": ["NO_CANDIDATE"]}],
        }

        Agent.propose_optimization(agent, [OptimizationDecision(parent_id="p1", decision="STOP")])

        agent.trial_ledger.record_optimization_selection.assert_called_once()
