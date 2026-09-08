import json
import tempfile
import unittest
from types import SimpleNamespace

from wqb_agent.checkpoints import CheckpointStore


class TestCheckpointStore(unittest.TestCase):
    def test_write_and_load_preserve_checkpoint_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(f"{tmp}/new-state")
            experiment = SimpleNamespace(to_dict=lambda: {
                "id": "e1", "round": 4, "hypothesis_id": "h1",
                "expression": "rank(close)", "settings": {},
                "fields_used": ["close"], "status": "SUBMIT_UNKNOWN",
            })
            self.assertTrue(store.write(4, {"id": "h1"}, [experiment], complete=False))
            loaded = store.load(4)
            self.assertEqual(loaded["round_no"], 4)
            self.assertFalse(loaded["complete"])
            self.assertEqual(loaded["experiments"][0]["status"], "SUBMIT_UNKNOWN")

    def test_malformed_or_mismatched_checkpoint_is_not_treated_as_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(tmp)
            with open(store.path(4), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 3, "experiments": []}, handle)
            self.assertIsNone(store.load(4))
            self.assertIsNone(store.unfinished_except(4))
            with open(store.path(5), "w", encoding="utf-8") as handle:
                handle.write("not json")
            self.assertEqual(store.unfinished_except(4), store.path(5))

    def test_unfinished_except_returns_lowest_blocking_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(tmp)
            for round_no in (6, 8):
                with open(store.path(round_no), "w", encoding="utf-8") as handle:
                    json.dump({"round_no": round_no, "complete": False,
                               "hypothesis": {}, "experiments": []}, handle)
            with open(store.path(7), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 7, "complete": True,
                           "hypothesis": {}, "experiments": []}, handle)
            self.assertEqual(store.unfinished_except(9), store.path(6))
            self.assertEqual(store.unfinished_except(6), store.path(8))

    def test_scan_is_authoritative_for_valid_and_malformed_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(tmp)
            with open(store.path(4), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 4, "complete": False, "hypothesis": {}, "experiments": []}, handle)
            with open(store.path(5), "w", encoding="utf-8") as handle:
                handle.write("not json")
            records = store.scan()
            self.assertEqual([record["round_no"] for record in records], [4, 5])
            self.assertFalse(records[0]["malformed"])
            self.assertTrue(records[1]["malformed"])
            self.assertEqual(store.unfinished_except(9), records[0]["path"])


if __name__ == "__main__":
    unittest.main()
