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
from wqb_agent.discovery import FieldDiscovery
from wqb_agent.memory import ExperienceMemory
from wqb_agent.proposal_contract import validate_proposal, validate_vector_inputs
from wqb_agent.reflection import Reflector
from wqb_agent.simulator import Simulator
from wqb_agent.state import Experiment, Trajectory
from wqb_agent.submission import SubmissionPool, self_correlation_evidence

FAKE_FIELDS = {
    "pv1": [
        {"id": "close", "name": "Close price", "description": "daily close price of the stock"},
        {"id": "returns", "name": "Returns", "description": "daily simple returns"},
        {"id": "volume", "name": "Volume", "description": "daily trading volume"},
        {"id": "adv20", "name": "Average daily volume 20d", "description": "20 day average trading volume"},
        {"id": "high", "name": "High price", "description": "daily high price"},
        {"id": "low", "name": "Low price", "description": "daily low price"},
        {"id": "open", "name": "Open price", "description": "daily open price"},
        {"id": "vwap", "name": "VWAP", "description": "volume weighted average price"},
    ],
    "pv13": [
        {"id": "sector", "name": "Sector", "description": "sector classification"},
        {"id": "market_cap", "name": "Market cap", "description": "market capitalization"},
        {"id": "spread", "name": "Bid-ask spread", "description": "liquidity spread"},
    ],
    "analyst4": [
        {"id": "target_price", "name": "Analyst target price", "description": "consensus analyst target price"},
        {"id": "recommendation", "name": "Recommendation", "description": "analyst recommendation rating"},
        {"id": "eps_estimate", "name": "EPS estimate", "description": "analyst eps estimate"},
        {"id": "num_analysts", "name": "Number of analysts", "description": "analyst coverage count"},
    ],
    "option8": [
        {"id": "implied_vol", "name": "Implied volatility", "description": "option implied volatility"},
        {"id": "put_call_ratio", "name": "Put call ratio", "description": "option put call volume ratio"},
        {"id": "iv_skew", "name": "IV skew", "description": "implied volatility skew"},
        {"id": "option_volume", "name": "Option volume", "description": "total option trading volume"},
    ],
    "model16": [
        {"id": "risk_score", "name": "Model risk score", "description": "composite model risk score"},
        {"id": "model_factor", "name": "Model factor", "description": "model factor loading"},
        {"id": "pred_ret", "name": "Predicted return", "description": "model predicted return"},
    ],
    "news12": [
        {"id": "news_sentiment", "name": "News sentiment", "description": "news sentiment score"},
        {"id": "news_count", "name": "News count", "description": "number of news articles"},
        {"id": "headline_buzz", "name": "Headline buzz", "description": "headline attention score"},
    ],
}
def _fake_metrics(expression):
    sharpe = 0.1
    turnover = 1.8
    if "ts_mean" in expression:
        sharpe += 1.0
        turnover = 0.4
    if "ts_rank" in expression:
        sharpe += 0.3
    if "group_neutralize" in expression:
        sharpe += 0.2
    if "zscore" in expression:
        sharpe -= 0.1
    if expression.startswith("rank(close") or expression.startswith("-rank(close"):
        sharpe = -0.3
    if "badfield" in expression:
        return {
            "sharpe": 0.0,
            "fitness": 0.0,
            "turnover": 0.5,
            "margin": 0.0,
            "returns": 0.0,
            "drawdown": 0.0,
            "checks": [{"name": "syntax", "pass": False}],
        }
    return {
        "sharpe": sharpe,
        "fitness": sharpe,
        "turnover": turnover,
        "margin": sharpe * 0.1,
        "returns": sharpe * 0.05,
        "drawdown": 0.1,
        "checks": [{"name": "limitations", "pass": True}],
    }
BASE_CONFIG = {
    "simulation": {
        "instrumentType": "EQUITY",
        "region": "USA",
        "universe": "TOP3000",
        "delay": 1,
        "decay": 0,
        "neutralization": "SUBINDUSTRY",
        "truncation": 0.08,
        "pasteurization": "ON",
        "unitHandling": "VERIFY",
        "nanHandling": "ON",
    },
    "agent": {
        "max_rounds": 2,
        "candidates_per_round": 6,
        "max_concurrent_sims": 3,
        "fields_per_discovery": 6,
        "pagination_limit": 50,
        "max_pagination_pages": 20,
        "state_dir": None,
        "poll_timeout_sec": 30,
    },
}
def make_agent(tmpdir, rounds=2):
    config = json.loads(json.dumps(BASE_CONFIG))
    config["agent"]["state_dir"] = str(tmpdir)
    config["agent"]["max_rounds"] = rounds
    client = FakeClient()
    return Agent(client, config), client

class TmpStateMixin:
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="wqb_test_")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestReflection(TmpStateMixin, unittest.TestCase):
    def test_failed_high_score_does_not_replace_best(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        good = Experiment(1, "h", "rank(good)", {}, ["good"])
        good.metrics = {
            "sharpe": 1.1, "fitness": 1.1, "turnover": 0.2,
            "returns": 0.1, "drawdown": 0.1, "margin": 0.01,
            "checks": [{"name": "LIMITS", "pass": True}],
            "passed": True,
        }
        good.status = "DONE"
        bad = Experiment(1, "h", "rank(noise)", {}, ["noise"])
        bad.metrics = {
            "sharpe": 9.0, "fitness": 20.0, "turnover": 0.1,
            "returns": 0.5, "drawdown": 0.1, "margin": 0.02,
            "checks": [{"name": "LIMITS", "pass": True}],
            "passed": True,
        }
        bad.status = "DONE"
        bad.health = {"ok": False, "reasons": ["CONCENTRATED_WEIGHT=FAIL"]}
        reflector.reflect(1, {"id": "h", "direction": "long"}, [good, bad])
        self.assertIsNone(memory.current_best)

    def test_sub_universe_health_failure_keeps_its_real_diagnosis(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        exp = Experiment(1, "h", "rank(x)", {}, ["x"])
        exp.status = "DONE"
        exp.metrics = {
            "sharpe": -1.0, "fitness": -0.4, "turnover": 0.2,
            "returns": -0.03, "drawdown": 0.16, "margin": -0.0003,
            "checks": [{"name": "LOW_SUB_UNIVERSE_SHARPE", "pass": False}],
            "passed": False,
        }
        exp.health = {"ok": False, "reasons": ["LOW_SUB_UNIVERSE_SHARPE=FAIL v=-1.12"]}
        verdict = reflector._classify(exp)
        self.assertIn("sub_universe", verdict["diagnosis"])
        self.assertNotIn("weight_concentration", verdict["diagnosis"])

    def test_suspicious_high_signal_is_not_promoted(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        exp = Experiment(1, "h", "rank(x)", {}, ["x"])
        exp.status = "DONE"
        exp.metrics = {
            "sharpe": 3.2, "fitness": 8.1, "turnover": 0.2,
            "returns": 0.2, "drawdown": 0.1, "margin": 0.01,
            "checks": [{"name": "LIMITS", "pass": True}], "passed": True,
        }
        exp.health = {"ok": True, "reasons": []}
        summary = reflector.reflect(1, {"id": "h", "direction": "long"}, [exp])
        self.assertEqual(summary["verdicts"]["SUSPICIOUS_HIGH_SIGNAL"], 1)
        self.assertIsNone(memory.current_best)
        self.assertEqual(memory.lessons, [])
        self.assertTrue(memory.next_with_fields()["idea"].startswith("Validate suspicious"))

    def test_unverified_checks_and_missing_metrics_cannot_succeed(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        exp = Experiment(1, "h", "rank(x)", {}, ["x"])
        exp.status = "DONE"
        exp.metrics = {
            "sharpe": 2.0, "fitness": None, "turnover": 0.2,
            "returns": 0.1, "drawdown": 0.1, "margin": 0.01,
            "checks": [], "passed": None,
        }
        verdict = reflector._classify(exp)
        self.assertNotEqual(verdict["label"], "SUCCESS")
        self.assertIn("missing_metrics", verdict["diagnosis"])

    def test_result_only_checks_are_accepted_when_resolved(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        exp = Experiment(1, "h", "rank(x)", {}, ["x"])
        exp.status = "DONE"
        exp.metrics = {
            "sharpe": 1.1, "fitness": 0.8, "turnover": 0.2,
            "returns": 0.1, "drawdown": 0.1, "margin": 0.01,
            "checks": [{"name": "LIMITS", "result": "PASS"}],
            "passed": True,
        }
        verdict = reflector._classify(exp)
        self.assertNotEqual(verdict["label"], "RECONCILE")

    def test_single_success_is_observation_not_best_or_lesson(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        exps = []
        for _, expr in enumerate(
            ["rank(close)", "rank(ts_mean(returns, 5))", "rank(ts_rank(returns, 20))"]
        ):
            e = Experiment(1, "h", expr, {}, ["returns"])
            e.metrics = _fake_metrics(expr)
            e.status = "DONE"
            exps.append(e)
        summary = reflector.reflect(1, {"tags": ["return"], "direction": "long"}, exps)
        self.assertIsNone(memory.current_best)
        self.assertEqual(memory.lessons, [])
        self.assertTrue(any(x["kind"] == "observation" for x in memory.short_term))
        self.assertIn("SUCCESS", summary["verdicts"])

    def test_fail_diagnosis_adds_avoid(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        e = Experiment(1, "h", "rank(close)", {}, ["close"])
        e.status = "FAILED"
        e.error = "Simulation rejected (422): syntax error"
        reflector.reflect(1, {"tags": ["price"], "direction": "long"}, [e])
        self.assertEqual(len(memory.avoid), 1)
        self.assertIn("syntax", memory.avoid[0]["reason"])

    def test_marks_hypothesis_outcome(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        e = Experiment(1, "h-1", "rank(ts_mean(returns, 5))", {}, ["returns"])
        e.metrics = _fake_metrics(e.expression)
        e.status = "DONE"
        hypothesis = {"id": "h-1", "tags": ["return"], "direction": "long", "_round": 1}
        memory.register_hypothesis(hypothesis)
        reflector.reflect(1, hypothesis, [e])
        active = {h["id"]: h for h in memory.active_hypotheses}
        self.assertEqual(active["h-1"]["status"], "success")

    def test_promising_next_carries_fields_and_datasets(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        e = Experiment(1, "h", "rank(returns)", {}, ["returns"], ["pv1"])
        e.metrics = {
            "sharpe": 0.8, "fitness": 0.6, "turnover": 0.2,
            "returns": 0.03, "drawdown": 0.1, "margin": 0.003,
            "checks": [{"name": "LIMITS", "pass": True}], "passed": True,
        }
        e.status = "DONE"
        reflector.reflect(1, {"tags": ["return"], "direction": "long"}, [e])
        top = memory.next_with_fields()
        self.assertIsNotNone(top)
        self.assertIn("returns", top.get("fields", []))
        self.assertIn("pv1", top.get("datasets", []))

    # ---- six-metric comprehensive gate --------------------------------

    @staticmethod
    def _done_experiment(expression, metrics):
        e = Experiment(1, "h", expression, {}, ["f"])
        e.metrics = metrics
        e.status = "DONE"
        return e

    def test_gate_promising_on_deep_drawdown(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        exp = self._done_experiment(
            "rank(f)",
            {"sharpe": 1.5, "fitness": 1.5, "turnover": 0.4, "margin": 0.15,
             "returns": 0.1, "drawdown": 0.8,
             "checks": [{"name": "limitations", "pass": True}]},
        )
        result = reflector._classify(exp)
        self.assertEqual(result["label"], "PROMISING")
        self.assertIn("drawdown", result["diagnosis"])

    def test_gate_promising_on_nonpositive_margin(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        exp = self._done_experiment(
            "rank(f)",
            {"sharpe": 1.5, "fitness": 1.5, "turnover": 0.4, "margin": -0.01,
             "returns": 0.1, "drawdown": 0.1,
             "checks": [{"name": "limitations", "pass": True}]},
        )
        result = reflector._classify(exp)
        self.assertEqual(result["label"], "PROMISING")
        self.assertIn("margin", result["diagnosis"])

    def test_gate_fail_on_low_sharpe_plus_deep_drawdown(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        exp = self._done_experiment(
            "rank(f)",
            {"sharpe": 0.3, "fitness": 0.3, "turnover": 0.4, "margin": 0.03,
             "returns": 0.02, "drawdown": 0.8,
             "checks": [{"name": "limitations", "pass": True}]},
        )
        result = reflector._classify(exp)
        self.assertEqual(result["label"], "FAIL")
        self.assertIn("drawdown", result["diagnosis"])

    def test_gate_soft_low_turnover_still_success(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        exp = self._done_experiment(
            "rank(f)",
            {"sharpe": 1.5, "fitness": 1.5, "turnover": 0.005, "margin": 0.15,
             "returns": 0.1, "drawdown": 0.1,
             "checks": [{"name": "limitations", "pass": True}]},
        )
        result = reflector._classify(exp)
        self.assertEqual(result["label"], "SUCCESS")
        self.assertTrue(any("turnover" in note for note in result["notes"]))

    def test_unknown_not_learned_or_avoided(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        e = Experiment(1, "h", "rank(returns)", {}, ["returns"])
        e.status = "UNKNOWN"
        e.error = "UNKNOWN_LOCAL ConnectionError: proxy down"
        hypothesis = {"tags": ["return"], "direction": "long", "id": "h", "_round": 1}
        memory.register_hypothesis(hypothesis)
        reflector.reflect(1, hypothesis, [e])
        self.assertEqual(len(memory.avoid), 0)
        self.assertEqual(len(memory.lessons), 0)
        active = {h["id"]: h for h in memory.active_hypotheses}
        self.assertEqual(active["h"]["status"], "active")

    def test_unknown_and_system_failure_are_removed_from_persisted_dedupe(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(memory)
        unknown = Experiment(1, "h", "rank(unknown_field)", {}, ["unknown_field"])
        unknown.status = "UNKNOWN"
        unknown.error = "UNKNOWN_LOCAL ConnectionError: proxy down"
        failed = Experiment(1, "h", "rank(rate_limited)", {}, ["rate_limited"])
        failed.status = "FAILED"
        failed.error = "WQBRateLimitError: 429"
        memory.remember_expression(unknown.expression)
        memory.remember_expression(failed.expression)
        hypothesis = {"id": "h", "direction": "long", "_round": 1}
        memory.register_hypothesis(hypothesis)
        reflector.reflect(1, hypothesis, [unknown, failed])
        loaded = ExperienceMemory(state_dir=self._tmp).load()
        self.assertNotIn(unknown.expression, loaded.seen_expressions)
        self.assertNotIn(failed.expression, loaded.seen_expressions)



if __name__ == "__main__":
    unittest.main()
