import json
import os
import tempfile
import unittest

from wqb_agent.workspace_snapshot import read_workspace_snapshot


class TestWorkspaceSnapshotBoundaries(unittest.TestCase):
    def test_malformed_checkpoint_and_json_remain_visible_as_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "round_1.checkpoint.json"), "w", encoding="utf-8") as handle:
                handle.write("not json")
            with open(os.path.join(tmp, "proposals.json"), "w", encoding="utf-8") as handle:
                handle.write("{")
            snapshot = read_workspace_snapshot(tmp)
        self.assertTrue(snapshot.checkpoint_records[0]["malformed"])
        self.assertEqual(
            snapshot.inventory.info("round_1.checkpoint.json").schema_version,
            "UNREADABLE",
        )
        proposals = snapshot.inventory.info("proposals.json")
        self.assertTrue(proposals.exists)
        self.assertTrue(proposals.readable)
        self.assertEqual(proposals.schema_version, "UNREADABLE")
        self.assertIsNone(snapshot.proposal_round)
        self.assertEqual(snapshot.proposal_count, 0)

    def test_directory_named_json_is_not_reported_as_readable_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.mkdir(os.path.join(tmp, "proposals.json"))
            snapshot = read_workspace_snapshot(tmp)
        info = snapshot.inventory.info("proposals.json")
        self.assertTrue(info.exists)
        self.assertFalse(info.readable)
        self.assertEqual(info.kind, "json")
        self.assertIsNone(snapshot.proposal_round)

    def test_invalid_jsonl_row_is_skipped_without_mutating_append_only_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trial_ledger.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("not json\n")
                handle.write(json.dumps({
                    "proposal_id": "p1", "phase": "simulation_committed",
                }) + "\n")
            with open(path, "rb") as handle:
                before = handle.read()
            snapshot = read_workspace_snapshot(tmp)
            with open(path, "rb") as handle:
                after = handle.read()
        self.assertEqual(before, after)
        self.assertIn("p1", snapshot.ledger.committed)

    def test_unexpected_json_is_inventory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "notes.json"), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 999, "proposals": [{"id": "unexpected"}]}, handle)
            snapshot = read_workspace_snapshot(tmp)
        info = snapshot.inventory.info("notes.json")
        self.assertEqual(info.schema_version, "PRESENT")
        self.assertIsNone(snapshot.proposal_round)
        self.assertEqual(snapshot.proposal_count, 0)

    def test_empty_state_is_a_valid_empty_read_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = read_workspace_snapshot(tmp)
        self.assertEqual(snapshot.checkpoint_records, ())
        self.assertEqual(snapshot.trajectory.records, 0)
        self.assertEqual(snapshot.ledger.committed, frozenset())

    def test_large_trajectory_uses_bounded_summary_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                for index in range(2000):
                    handle.write(json.dumps({
                        "id": f"e{index}", "round": index,
                        "status": "UNKNOWN" if index % 2 else "DONE",
                    }) + "\n")
            snapshot = read_workspace_snapshot(tmp)
        self.assertEqual(snapshot.trajectory.records, 2000)
        self.assertEqual(snapshot.trajectory.latest_round, 1999)
        self.assertEqual(snapshot.trajectory.submit_unknown_count, 0)


if __name__ == "__main__":
    unittest.main()
