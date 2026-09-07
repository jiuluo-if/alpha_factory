import json
import os
import tempfile
import unittest

from wqb_agent.research_api import (
    ExperimentSpec,
    compare_experiments,
    discover_fields,
    get_operator_reference,
    inspect_state,
    reconcile,
    run_experiment,
)


class _Discovery:
    fields_per_discovery = 3

    def discover(self, query, target_count):
        return [{"id": "close", "type": "MATRIX"}][:target_count]

    def source_provenance(self):
        return {"kind": "brain_api", "snapshot_date": None}


class _FakeAgent:
    state_dir = None
    fields_per_discovery = 3
    discovery = _Discovery()

    def __init__(self, state_dir):
        self.state_dir = state_dir
        self.received = None

    def next_round_no(self):
        return 7

    def run_proposals(self, path):
        with open(path, encoding="utf-8") as handle:
            self.received = json.load(handle)
        return {"accepted": 1, "status": "DONE"}


class _FakeClient:
    def __init__(self):
        self.urls = []

    def get_progress_snapshot(self, url, timeout=60):
        self.urls.append((url, timeout))
        return {"url": url, "status": "RUNNING"}


class TestResearchApi(unittest.TestCase):
    def test_experiment_spec_is_lightweight_and_adapts_to_existing_contract(self):
        spec = ExperimentSpec(
            hypothesis="short-term reversal",
            expression="rank(returns)",
            fields=("returns",),
            settings={"decay": 2},
            rationale="test a falsifiable reversal mechanism",
        )
        proposal = spec.to_proposal(round_no=4)
        self.assertEqual(proposal["round"], 4)
        self.assertEqual(proposal["fields"], ["returns"])
        self.assertEqual(proposal["experiment_stage"], "BASELINE")
        self.assertEqual(proposal["research_role"], "EXPLORE")

    def test_discovery_facade_uses_existing_discovery_component(self):
        result = discover_fields("price reversal", agent=_FakeAgent(tempfile.gettempdir()))
        self.assertEqual(result["fields"][0]["id"], "close")
        self.assertEqual(result["field_source"]["kind"], "brain_api")

    def test_run_experiment_delegates_to_guarded_agent_path(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = _FakeAgent(directory)
            result = run_experiment(
                {"hypothesis": "test", "expression": "rank(close)", "fields": ["close"]},
                agent=agent,
            )
            self.assertEqual(result["status"], "DONE")
            self.assertEqual(agent.received["round_no"], 7)
            self.assertEqual(agent.received["proposals"][0]["expression"], "rank(close)")
            self.assertEqual(os.listdir(directory), [])

    def test_reconcile_only_polls_the_known_url(self):
        client = _FakeClient()
        result = reconcile("https://brain.example/progress/1", client=client, timeout=12)
        self.assertEqual(result["status"], "RUNNING")
        self.assertEqual(client.urls, [("https://brain.example/progress/1", 12)])

    def test_operator_reference_is_read_from_the_checked_in_table(self):
        reference = get_operator_reference()
        self.assertTrue(reference["sha256"])
        self.assertIn("rank", reference["operators"])

    def test_state_queries_are_small_and_composable(self):
        with tempfile.TemporaryDirectory() as directory:
            result = inspect_state(state_dir=directory, limit=2)
            self.assertEqual(result["experiment_count"], 0)
            self.assertEqual(result["recent_experiments"], [])
            self.assertEqual(compare_experiments(["missing"], state_dir=directory)["missing"], ["missing"])


if __name__ == "__main__":
    unittest.main()
