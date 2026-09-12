"""Batch trajectory read contracts.

``Trajectory.find_rows()`` and ``research_api.compare_experiments()`` resolve
several identities with one canonical streaming pass.  They must keep the
single-id ``find_row`` semantics exactly: the latest legal revision wins, a row
whose execution identity contradicts the first legal match is ignored, and a
missing identity stays missing instead of being fabricated.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from wqb_agent.research_api import compare_experiments, get_experiment
from wqb_agent.state import RESEARCH_SETTLED_REVISION, Experiment, Trajectory


def _experiment(identity, *, expression="rank(field_a)", status="DONE"):
    experiment = Experiment(1, "h-1", expression, {"decay": 4}, ["field_a"], ["pv1"])
    experiment.id = identity
    experiment.proposal_id = f"proposal-{identity}"
    experiment.status = status
    experiment.metrics = {"sharpe": 1.0} if status == "DONE" else None
    return experiment


def _write(path, experiments, revision=None):
    with open(path, "w", encoding="utf-8") as handle:
        for experiment in experiments:
            row = experiment.to_dict()
            if revision:
                row["trajectory_revision"] = revision
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class TestFindRowsBatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wqb_batch_reads_")
        self.path = os.path.join(self.tmp, "trajectory.jsonl")

    def _trajectory(self):
        return Trajectory(path=self.path, persist=True)

    def test_batch_matches_single_id_reads(self):
        _write(self.path, [_experiment("e0"), _experiment("e1"), _experiment("e2")])
        trajectory = self._trajectory()
        found = trajectory.find_rows(["e0", "e1", "e2"])
        self.assertEqual(set(found), {"e0", "e1", "e2"})
        for identity in ("e0", "e1", "e2"):
            self.assertEqual(found[identity], trajectory.find_row(identity))

    def test_batch_resolves_proposal_identity(self):
        _write(self.path, [_experiment("e0")])
        found = self._trajectory().find_rows(["proposal-e0"])
        self.assertEqual(found["proposal-e0"]["id"], "e0")

    def test_batch_keeps_latest_settlement_revision(self):
        _write(self.path, [_experiment("e0")])
        trajectory = self._trajectory()
        trajectory.load()
        settled = _experiment("e0")
        settled.final_outcome = {"reward": 2.0, "reward_quality": "FINAL_EVIDENCE"}
        settled.research_classification = {"label": "PROMISING"}
        trajectory.settle(settled)
        found = self._trajectory().find_rows(["e0"])
        self.assertEqual(found["e0"]["final_outcome"]["reward"], 2.0)
        self.assertEqual(found["e0"], self._trajectory().find_row("e0"))

    def test_batch_ignores_identity_conflicting_revision(self):
        early = _experiment("e0")
        conflicting = _experiment("e0", expression="rank(field_b)")
        _write(self.path, [early, conflicting], revision=RESEARCH_SETTLED_REVISION)
        found = self._trajectory().find_rows(["e0"])
        self.assertEqual(found["e0"]["expression"], "rank(field_a)")

    def test_batch_finds_identities_that_need_escaping(self):
        identity = 'e"0\\中'
        _write(self.path, [_experiment(identity)])
        trajectory = self._trajectory()
        found = trajectory.find_rows([identity])
        self.assertEqual(found[identity], trajectory.find_row(identity))
        self.assertIsNotNone(found[identity])

    def test_missing_identity_stays_missing(self):
        _write(self.path, [_experiment("e0")])
        found = self._trajectory().find_rows(["e0", "missing"])
        self.assertIsNone(found["missing"])
        self.assertIsNotNone(found["e0"])

    def test_empty_or_unpersisted_reads_are_empty(self):
        self.assertEqual(self._trajectory().find_rows([]), {})
        self.assertEqual(self._trajectory().find_rows(None), {})
        self.assertEqual(
            Trajectory(path=self.path, persist=False).find_rows(["e0"]), {}
        )

    def test_iter_rows_prefilter_never_hides_matching_rows(self):
        _write(self.path, [_experiment("e0"), _experiment("e1")])
        trajectory = self._trajectory()
        self.assertEqual(
            {row["id"] for row in trajectory.iter_rows()}, {"e0", "e1"}
        )
        self.assertEqual(
            {row["id"] for row in trajectory.iter_rows(prefilter="e1")}, {"e1"}
        )
        self.assertEqual(
            {
                row["id"]
                for row in trajectory.iter_rows(prefilter=("e0", "e1"))
            },
            {"e0", "e1"},
        )


class TestCompareExperimentsBatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wqb_compare_")
        self.path = os.path.join(self.tmp, "trajectory.jsonl")

    def test_compare_reads_append_only_history_once(self):
        _write(self.path, [_experiment("e0"), _experiment("e1"), _experiment("e2")])
        original = Trajectory.iter_rows
        calls = []

        def counting(self, **kwargs):
            calls.append(kwargs)
            yield from original(self, **kwargs)

        with mock.patch.object(Trajectory, "iter_rows", counting):
            result = compare_experiments(["e0", "e1", "e2"], state_dir=self.tmp)
        self.assertEqual(len(calls), 1)
        self.assertEqual([row["id"] for row in result["experiments"]], ["e0", "e1", "e2"])
        self.assertEqual(result["missing"], [])

    def test_compare_reports_missing_and_keeps_request_order(self):
        _write(self.path, [_experiment("e0")])
        result = compare_experiments(["e0", "missing"], state_dir=self.tmp)
        self.assertEqual([row["id"] for row in result["experiments"]], ["e0"])
        self.assertEqual(result["missing"], ["missing"])

    def test_single_id_read_matches_batch_read(self):
        _write(self.path, [_experiment("e0")])
        self.assertEqual(
            get_experiment("e0", state_dir=self.tmp),
            compare_experiments(["e0"], state_dir=self.tmp)["experiments"][0],
        )
