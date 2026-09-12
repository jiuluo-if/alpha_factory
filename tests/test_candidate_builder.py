"""Candidate builder from-scratch and single-variable mutation tests."""

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.agent import (
    SEED_HYPOTHESES,
    Agent,
)
from wqb_agent.artifacts import atomic_write_json_if_changed
from wqb_agent.candidate import CandidateBuilder
from wqb_agent.discovery import (
    FieldDiscovery,
    frequency_evidence,
    normalize_coverage,
    normalize_frequency,
)
from wqb_agent.memory import ExperienceMemory
from wqb_agent.proposal_contract import validate_proposal, validate_vector_inputs
from wqb_agent.reflection import Reflector
from wqb_agent.simulator import Simulator
from wqb_agent.state import Experiment, Trajectory
from wqb_agent.submission import SubmissionPool, self_correlation_evidence


class TestCandidateBuilder(unittest.TestCase):
    def test_from_scratch_excludes_direction_only_candidate(self):
        builder = CandidateBuilder(neutralization="subindustry")
        fields = [{"id": "returns"}, {"id": "volume"}]
        hypothesis = {"direction": "reversal", "tags": ["return"]}
        candidates = builder.build(hypothesis, fields, None, count=9)
        # 纯 sign-flip 不是新的经济假设，候选生成器必须将其排除。
        self.assertEqual(len(candidates), 2)
        self.assertTrue(all("returns" in c["expression"] for c in candidates))
        self.assertTrue(candidates[0]["expression"].startswith("-rank"))

    def test_from_scratch_long_direction_positive(self):
        builder = CandidateBuilder()
        fields = [{"id": "returns"}]
        candidates = builder.build({"direction": "long"}, fields, None, count=3)
        self.assertTrue(candidates[0]["expression"].startswith("rank"))

    def test_reversal_flips_sign(self):
        builder = CandidateBuilder()
        fields = [{"id": "returns"}]
        candidates = builder.build(
            {"direction": "reversal"}, fields, None, count=2
        )
        self.assertTrue(candidates[0]["expression"].startswith("-rank"))

    def test_mutates_best_single_variable(self):
        builder = CandidateBuilder()
        fields = [{"id": "returns"}, {"id": "volume"}]
        best = {
            "id": "b1",
            "expression": "rank(returns)",
            "fields_used": ["returns"],
            "metrics": {"sharpe": 0.6, "fitness": 0.6},
        }
        candidates = builder.build({}, fields, best, count=6)
        exprs = [c["expression"] for c in candidates]
        self.assertNotIn("rank(returns)", exprs)
        self.assertEqual(len(exprs), 6)
        self.assertTrue(all(c["parent"] == "b1" for c in candidates))

    def test_sibling_zscore_combination(self):
        builder = CandidateBuilder()
        fields = [{"id": "f1"}, {"id": "f2"}]
        best = {
            "id": "b1",
            "expression": "rank(ts_zscore(f1, 63))",
            "fields_used": ["f1"],
            "metrics": {"sharpe": 3.0, "fitness": 10.0},
        }
        candidates = builder.build({}, fields, best, count=6)
        exprs = [c["expression"] for c in candidates]
        self.assertIn("rank(ts_zscore(f1, 63) + ts_zscore(f2, 63))", exprs)

    def test_window_step_on_ts_zscore(self):
        builder = CandidateBuilder()
        fields = [{"id": "f1"}]
        best = {
            "id": "b1",
            "expression": "rank(ts_zscore(f1, 63))",
            "fields_used": ["f1"],
            "metrics": {"sharpe": 3.0, "fitness": 10.0},
        }
        candidates = builder.build({}, fields, best, count=6)
        exprs = [c["expression"] for c in candidates]
        # 63 的下一步是 84（r229 实证的甜点窗口），不是跳 126
        self.assertIn("rank(ts_zscore(f1, 84))", exprs)

    def test_window_step_reaches_252_and_ts_av_diff(self):
        """2026-08-19 修复回归：WINDOW_STEPS 含 252；ts_av_diff 可步进。"""
        from wqb_agent.candidate import _window_change

        self.assertEqual(_window_change("rank(ts_zscore(f1, 126))", +1),
                         "rank(ts_zscore(f1, 252))")
        self.assertEqual(_window_change("rank(ts_av_diff(f1, 63))", +1),
                         "rank(ts_av_diff(f1, 84))")
        self.assertEqual(_window_change("rank(ts_av_diff(f1, 84))", -1),
                         "rank(ts_av_diff(f1, 63))")
