"""Tests for artifact append semantics."""

import json
import os
import tempfile
import threading
import unittest

from wqb_agent.artifacts import append_jsonl_if_unique


class TestAppendJsonlSemantics(unittest.TestCase):
    def test_owning_lock_makes_duplicate_check_atomic_for_concurrent_callers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.jsonl")
            owner_lock = threading.Lock()
            barrier = threading.Barrier(2)
            results = []

            def append_once():
                barrier.wait()
                try:
                    result = append_jsonl_if_unique(
                        path, {"event_id": "same"}, ("event_id",),
                        lock=owner_lock,
                    )
                except Exception as exc:  # assert the failure at the caller
                    result = exc
                results.append(result)

            workers = [threading.Thread(target=append_once) for _ in range(2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(1.0)

            self.assertTrue(all(not worker.is_alive() for worker in workers))
            self.assertEqual(sorted(results, key=repr), [False, True])
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(len([json.loads(line) for line in handle]), 1)


if __name__ == "__main__":
    unittest.main()
