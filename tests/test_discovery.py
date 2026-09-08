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
    Agent,
    SEED_HYPOTHESES,
    validate_proposal,
    validate_vector_inputs,
)
from wqb_agent.artifacts import atomic_write_json_if_changed
from wqb_agent.candidate import CandidateBuilder
from wqb_agent.discovery import FieldDiscovery
from wqb_agent.memory import ExperienceMemory
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

class FakeClient:
    def __init__(self, latency=0.01):
        self.counter = 0
        self.latency = latency
        self._expr_by_url = {}
        self._alpha_expr = {}
        self.sim_calls = []
        self.max_active = 0
        self._active = 0
        self._lock = threading.Lock()
        self.datafield_calls = []

    def get_datafields(self, dataset_id, limit=50, offset=0, field_type=None):
        self.datafield_calls.append((dataset_id, limit, offset))
        all_fields = FAKE_FIELDS.get(dataset_id, [])
        return all_fields[offset : offset + limit], len(all_fields)

    def submit_simulation(self, expression, settings, alpha_type="REGULAR"):
        self.counter += 1
        url = f"progress-{self.counter}"
        self._expr_by_url[url] = expression
        self.sim_calls.append(expression)
        return url

    def poll_progress(self, progress_url, timeout_sec=900):
        expression = self._expr_by_url[progress_url]
        alpha_id = f"alpha-{abs(hash(progress_url))}"
        self._alpha_expr[alpha_id] = expression
        return alpha_id

    def get_alpha(self, alpha_id):
        expression = self._alpha_expr.get(alpha_id, "")
        return {"is": _fake_metrics(expression), "regular": expression}


class TmpStateMixin:
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="wqb_test_")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestFieldDiscovery(TmpStateMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.client = FakeClient()
        self.discovery = FieldDiscovery(self.client, pagination_limit=2, max_pages=20)

    def test_selects_relevant_dataset_and_fields(self):
        hypothesis = {
            "statement": "Stocks with high trading volume predict returns.",
            "tags": ["volume", "return"],
            "direction": "long",
        }
        fields = self.discovery.discover(hypothesis, target_count=4)
        ids = [f["id"] for f in fields]
        self.assertTrue(any("volume" in f for f in ids))
        self.assertTrue(any("return" in f for f in ids))
        self.assertLessEqual(len(fields), 4)
        calls = self.client.datafield_calls
        self.assertTrue(all(c[1] == 2 for c in calls))

    def test_malformed_field_page_is_ignored_without_crashing(self):
        class MalformedClient:
            def get_datafields(self, *args, **kwargs):
                return {"not": "a field list"}, None

        discovery = FieldDiscovery(MalformedClient(), pagination_limit=2, max_pages=2)
        self.assertEqual(discovery._fields_for("pv1"), [])

    def test_malformed_hypothesis_and_field_metadata_degrade_safely(self):
        class MalformedClient:
            def get_datafields(self, *args, **kwargs):
                return [
                    {"id": ["bad"], "name": {"bad": True}},
                    {"id": 7, "name": 8, "description": "volume"},
                ], 2

        discovery = FieldDiscovery(MalformedClient(), pagination_limit=10, max_pages=2)
        self.assertEqual(
            discovery.categorize_hypothesis({"statement": "trading volume", "tags": "bad"}),
            ["price_volume"],
        )
        fields = discovery.discover(
            {"statement": "volume", "tags": [123], "datasets": [{"id": "pv1"}]}, 2
        )
        self.assertEqual([field["id"] for field in fields], ["7"])

    def test_stops_when_enough_fields(self):
        hypothesis = {
            "statement": "reversal on price.",
            "tags": ["reversal", "price"],
            "direction": "reversal",
        }
        fields = self.discovery.discover(hypothesis, target_count=2)
        self.assertLessEqual(len(fields), 2)

    def test_complete_local_catalog_is_preferred_and_has_provenance(self):
        catalog = os.path.join(self._tmp, "platform_field_catalog_20260822")
        os.makedirs(catalog)
        with open(os.path.join(catalog, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"fetched_at": "2026-08-22T00:00:00+0800", "datasets": {
                "pv1": {"file": "pv1.json"}
            }}, f)
        with open(os.path.join(catalog, "pv1.json"), "w", encoding="utf-8") as f:
            json.dump({"fields": [{"id": "local_volume", "description": "local volume", "type": "MATRIX"}]}, f)
        discovery = FieldDiscovery(
            self.client, cache_path=os.path.join(self._tmp, "fields_cache.json")
        )
        fields = discovery.discover(
            {"statement": "volume effect", "tags": ["volume"], "datasets": ["pv1"]}, 1
        )
        self.assertEqual(fields[0]["id"], "local_volume")
        self.assertEqual(fields[0]["field_source"]["kind"], "local_catalog")
        self.assertEqual(self.client.datafield_calls, [])

    def test_malformed_catalog_manifest_fails_closed_to_discovery(self):
        catalog = os.path.join(self._tmp, "platform_field_catalog_20260906")
        os.makedirs(catalog)
        with open(os.path.join(catalog, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"datasets": {"pv1": "not-an-object"}}, f)
        discovery = FieldDiscovery(self.client, cache_path=os.path.join(self._tmp, "fields_cache.json"))
        fields = discovery._fields_for("pv1")
        self.assertEqual(discovery.source_provenance()["kind"], "brain_api")
        self.assertTrue(fields)
        self.assertTrue(self.client.datafield_calls)

    def test_newer_corrupt_catalog_does_not_hide_older_complete_catalog(self):
        older = os.path.join(self._tmp, "platform_field_catalog_20260901")
        newer = os.path.join(self._tmp, "platform_field_catalog_20260907")
        for catalog in (older, newer):
            os.makedirs(catalog)
            with open(os.path.join(catalog, "manifest.json"), "w", encoding="utf-8") as handle:
                json.dump({"fetched_at": catalog[-8:], "datasets": {
                    "pv1": {"file": "pv1.json"}
                }}, handle)
        with open(os.path.join(older, "pv1.json"), "w", encoding="utf-8") as handle:
            json.dump({"fields": [{"id": "older_valid", "description": "valid", "type": "MATRIX"}]}, handle)
        with open(os.path.join(newer, "pv1.json"), "w", encoding="utf-8") as handle:
            json.dump({"fields": "corrupt"}, handle)
        discovery = FieldDiscovery(self.client, cache_path=os.path.join(self._tmp, "fields_cache.json"))
        fields = discovery._fields_for("pv1")
        self.assertEqual([field["id"] for field in fields], ["older_valid"])
        self.assertEqual(discovery.source_provenance()["path"], os.path.abspath(older))
        self.assertEqual(self.client.datafield_calls, [])

    def test_malformed_catalog_and_disk_cache_shapes_fail_closed(self):
        catalog = os.path.join(self._tmp, "platform_field_catalog_20260907")
        os.makedirs(catalog)
        with open(os.path.join(catalog, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump([], f)
        cache_path = os.path.join(self._tmp, "fields_cache.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        discovery = FieldDiscovery(self.client, cache_path=cache_path)
        self.assertEqual(discovery.source_provenance()["kind"], "brain_api")
        self.assertEqual(discovery._disk_cache, {})

    def test_complete_local_catalog_does_not_create_legacy_disk_cache(self):
        catalog = os.path.join(self._tmp, "platform_field_catalog_20260906")
        os.makedirs(catalog)
        with open(os.path.join(catalog, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"fetched_at": "2026-09-06T00:00:00+0800", "datasets": {
                "pv1": {"file": "pv1.json"}
            }}, f)
        with open(os.path.join(catalog, "pv1.json"), "w", encoding="utf-8") as f:
            json.dump({"fields": [{"id": "local_price", "description": "local price",
                                    "type": "MATRIX"}]}, f)
        cache_path = os.path.join(self._tmp, "fields_cache.json")
        discovery = FieldDiscovery(self.client, cache_path=cache_path)
        discovery._fields_for("pv1")
        discovery._save_disk_cache()
        self.assertFalse(os.path.exists(cache_path))

    def test_agent_preflight_reuses_complete_catalog_without_legacy_cache(self):
        catalog = os.path.join(self._tmp, "platform_field_catalog_20260906")
        os.makedirs(catalog)
        with open(os.path.join(catalog, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"fetched_at": "2026-09-06T00:00:00+0800", "datasets": {
                "pv1": {"file": "pv1.json"}
            }}, f)
        with open(os.path.join(catalog, "pv1.json"), "w", encoding="utf-8") as f:
            json.dump({"fields": [{"id": "catalog_vector", "description": "catalog vector",
                                    "type": "VECTOR"}]}, f)
        agent, _ = make_agent(self._tmp)
        types, profiles = agent._read_field_cache()
        self.assertEqual(types["catalog_vector"], "VECTOR")
        self.assertEqual(profiles["catalog_vector"]["dataset"], "pv1")
        self.assertFalse(os.path.exists(os.path.join(self._tmp, "fields_cache.json")))

    def test_high_alpha_count_field_is_excluded_before_selection(self):
        discovery = FieldDiscovery(self.client, max_alpha_count=10)
        discovery._cache["pv1"] = [
            {"id": "overused_volume", "description": "volume", "type": "MATRIX", "alphaCount": 99},
            {"id": "fresh_volume", "description": "volume", "type": "MATRIX", "alphaCount": 2},
        ]
        fields = discovery.discover(
            {"statement": "volume", "tags": ["volume"], "datasets": ["pv1"]}, 2
        )
        self.assertEqual([field["id"] for field in fields], ["fresh_volume"])
        self.assertEqual(discovery.last_excluded_high_usage[0]["id"], "overused_volume")

    def test_no_fake_fields(self):
        hypothesis = {
            "statement": "option volatility.",
            "tags": ["option", "volatility"],
            "direction": "reversal",
        }
        fields = self.discovery.discover(hypothesis, target_count=6)
        known = {f["id"] for f in sum(FAKE_FIELDS.values(), [])}
        self.assertTrue(all(f["id"] in known for f in fields))

    def test_preferred_datasets_used_first(self):
        hypothesis = {
            "statement": "guidance target revision predicts returns.",
            "tags": ["analyst", "eps", "target", "revision"],
            "direction": "long",
            "datasets": ["analyst4"],
        }
        fields = self.discovery.discover(hypothesis, target_count=3)
        self.assertGreaterEqual(len(fields), 3)
        self.assertTrue(all(f["dataset"] == "analyst4" for f in fields))
        # analyst4 must be queried before any fallback dataset
        first_dataset = self.client.datafield_calls[0][0]
        self.assertEqual(first_dataset, "analyst4")


class TestCandidateBuilder(unittest.TestCase):
    def test_from_scratch_excludes_direction_only_candidate(self):
        builder = CandidateBuilder(neutralization="subindustry")
        fields = [{"id": "returns"}, {"id": "volume"}]
        hypothesis = {"direction": "reversal", "tags": ["return"]}
        candidates = builder.build(hypothesis, fields, None, count=9)
        # 纯 sign-flip 不是新的经济假设，候选生成器必须将其排除。
        self.assertEqual(len(candidates), 8)
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



if __name__ == "__main__":
    unittest.main()
