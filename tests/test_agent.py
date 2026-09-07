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
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        time.sleep(self.latency)
        with self._lock:
            self._active -= 1
        self.counter += 1
        url = f"progress-{self.counter}"
        self._expr_by_url[url] = expression
        self.sim_calls.append(expression)
        return url

    def poll_progress(self, progress_url, timeout_sec=900):
        time.sleep(self.latency)
        expression = self._expr_by_url[progress_url]
        alpha_id = f"alpha-{abs(hash(progress_url))}"
        self._alpha_expr[alpha_id] = expression
        return alpha_id

    def get_alpha(self, alpha_id):
        expression = self._alpha_expr.get(alpha_id, "")
        return {"is": _fake_metrics(expression), "regular": expression}


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
    def test_from_scratch_returns_nine(self):
        builder = CandidateBuilder(neutralization="subindustry")
        fields = [{"id": "returns"}, {"id": "volume"}]
        hypothesis = {"direction": "reversal", "tags": ["return"]}
        candidates = builder.build(hypothesis, fields, None, count=9)
        self.assertEqual(len(candidates), 9)
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


class TestSimulator(unittest.TestCase):
    def test_concurrency_limited(self):
        client = FakeClient(latency=0.05)
        sim = Simulator(client, max_concurrent=3, poll_timeout_sec=30)
        exps = [Experiment(1, "h", f"rank(field{i})", {}, []) for i in range(7)]
        sim.run(exps)
        self.assertEqual(len(exps), 7)
        self.assertTrue(all(e.status == "DONE" for e in exps))
        self.assertLessEqual(client.max_active, 3)
        self.assertEqual(len(client.sim_calls), 7)

    def test_failure_recorded(self):
        class FailingClient(FakeClient):
            def submit_simulation(self, expression, settings, alpha_type="REGULAR"):
                raise Exception("Simulation rejected (422): bad expression")

        sim = Simulator(FailingClient(), max_concurrent=3, poll_timeout_sec=5)
        exp = Experiment(1, "h", "badfield(x)", {}, [])
        sim.run([exp])
        self.assertEqual(exp.status, "FAILED")
        self.assertIn("Simulation rejected", exp.error)

    def test_extracts_drawdown_and_six_metrics(self):
        client = FakeClient()
        sim = Simulator(client, max_concurrent=1, poll_timeout_sec=30)
        exp = Experiment(1, "h", "rank(ts_mean(returns, 5))", {}, ["returns"])
        sim.run([exp])
        m = exp.metrics
        for key in ("sharpe", "fitness", "turnover", "margin", "returns", "drawdown"):
            self.assertIsNotNone(m.get(key), f"missing metric {key}")
        self.assertEqual(m["drawdown"], 0.1)
        self.assertIn("value", m["checks"][0])
        self.assertIn("limit", m["checks"][0])
        self.assertIn("result", m["checks"][0])

    def test_unknown_pauses_dispatch(self):
        class NetworkFailingClient(FakeClient):
            def submit_simulation(self, expression, settings, alpha_type="REGULAR"):
                import requests
                raise requests.exceptions.ConnectionError("proxy down")

        client = NetworkFailingClient(latency=0.01)
        sim = Simulator(client, max_concurrent=3, poll_timeout_sec=30)
        exps = [Experiment(1, "h", f"rank(field{i})", {}, []) for i in range(6)]
        sim.run(exps)
        # 请求在传输层失败时无法证明 BRAIN 没有接收 POST；按 exactly-once
        # 语义保留为 SUBMIT_UNKNOWN，禁止下一轮自动重发。
        self.assertEqual(exps[0].status, "SUBMIT_UNKNOWN")
        self.assertTrue(sim.paused_reason)
        self.assertEqual(len(client.sim_calls), 0)  # 连接层失败未发出任何 POST
        # 3 个已 in-flight 的不回收；暂停后其余 3 个未派发
        self.assertEqual(
            sum(1 for e in exps if e.status == "PENDING"), 3
        )

    def test_ambiguous_submit_is_never_reposted(self):
        """丢失 POST 响应必须保留 SUBMIT_UNKNOWN，而非重复烧预算。"""
        from wqb_agent.client import WQBSubmitUnknownError

        class AmbiguousClient(FakeClient):
            def submit_simulation(self, expression, settings, alpha_type="REGULAR"):
                self.sim_calls.append(expression)  # BRAIN may already have accepted it
                raise WQBSubmitUnknownError("response lost after POST")

        client = AmbiguousClient()
        checkpoints = []
        exp = Experiment(1, "h", "rank(field)", {}, [])
        Simulator(client, max_concurrent=1, poll_timeout_sec=30).run(
            [exp], on_update=lambda item: checkpoints.append(item.status)
        )
        self.assertEqual(exp.status, "SUBMIT_UNKNOWN")
        self.assertEqual(len(client.sim_calls), 1)
        self.assertEqual(checkpoints, ["SUBMITTING", "SUBMIT_UNKNOWN"])

    def test_rolling_window_stays_full(self):
        client = FakeClient(latency=0.05)
        sim = Simulator(client, max_concurrent=3, poll_timeout_sec=30)
        exps = [Experiment(1, "h", f"rank(field{i})", {}, []) for i in range(9)]
        sim.run(exps)
        self.assertEqual(len(exps), 9)
        self.assertTrue(all(e.status == "DONE" for e in exps))
        self.assertLessEqual(client.max_active, 3)
        self.assertEqual(len(client.sim_calls), 9)

    def test_rate_limit_without_contract_is_submit_unknown(self):
        """没有 API 明确写入保证的 429 不能自动重发。"""
        from wqb_agent.client import WQBRateLimitError

        class FlakyClient(FakeClient):
            def __init__(self, failures=2):
                super().__init__(latency=0.01)
                self.failures = failures

            def submit_simulation(self, expression, settings, alpha_type="REGULAR"):
                if self.failures > 0:
                    self.failures -= 1
                    raise WQBRateLimitError("rate-limited after 5 attempts (429).")
                return super().submit_simulation(expression, settings, alpha_type)

        client = FlakyClient(failures=2)
        sim = Simulator(client, max_concurrent=1, poll_timeout_sec=30,
                        replace_attempts=3, replace_backoff_sec=0)
        exp = Experiment(1, "h", "rank(ts_mean(returns, 5))", {}, [])
        sim.run([exp])
        self.assertEqual(exp.status, "SUBMIT_UNKNOWN", exp.error)
        self.assertEqual(len(client.sim_calls), 0)
        self.assertTrue(sim.paused_reason)
        self.assertIsNotNone(exp.elapsed_sec)
        self.assertGreaterEqual(exp.elapsed_sec, 0.0)

    def test_rate_limit_never_marks_failed_without_write_contract(self):
        """429 没有幂等/拒绝契约时保留对账状态和预算槽。"""
        from wqb_agent.client import WQBRateLimitError

        class AlwaysLimitedClient(FakeClient):
            def submit_simulation(self, expression, settings, alpha_type="REGULAR"):
                raise WQBRateLimitError("rate-limited after 5 attempts (429).")

        client = AlwaysLimitedClient()
        sim = Simulator(client, max_concurrent=1, poll_timeout_sec=30,
                        replace_attempts=3, replace_backoff_sec=0)
        exp = Experiment(1, "h", "rank(ts_mean(returns, 5))", {}, [])
        sim.run([exp])
        self.assertEqual(exp.status, "SUBMIT_UNKNOWN")
        self.assertIn("WQBRateLimitError", exp.error)
        self.assertTrue(sim.paused_reason)
        self.assertIsNotNone(exp.elapsed_sec)

    def test_poll_timeout_reuses_known_progress_url(self):
        """轮询超时只重试同一 BRAIN job，不可重复提交。"""
        from wqb_agent.client import WQBTimeoutError

        class TimeoutOnceClient(FakeClient):
            def __init__(self):
                super().__init__(latency=0.01)
                self._once = True

            def poll_progress(self, progress_url, timeout_sec=900,
                              progress_callback=None):
                if self._once:
                    self._once = False
                    raise WQBTimeoutError("Simulation polling timed out.")
                return super().poll_progress(progress_url, timeout_sec)

        client = TimeoutOnceClient()
        sim = Simulator(client, max_concurrent=1, poll_timeout_sec=30,
                        replace_attempts=3, replace_backoff_sec=0)
        exp = Experiment(1, "h", "rank(ts_mean(returns, 5))", {}, [])
        sim.run([exp])
        self.assertEqual(exp.status, "DONE", exp.error)
        self.assertEqual(len(client.sim_calls), 1)


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
        for i, expr in enumerate(
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


class TestSubmissionPool(TmpStateMixin, unittest.TestCase):
    def test_pool_records_only_platform_self_correlation_evidence(self):
        exp = Experiment(1, "h", "rank(field)", {}, ["field"])
        exp.alpha_id = "alpha-1"
        exp.proposal_id = "p-1"
        exp.metrics = {
            "sharpe": 2.0, "fitness": 2.0, "turnover": 0.1, "margin": 0.01,
            "checks": [{"name": "SELF_CORRELATION", "pass": True}], "passed": True,
        }
        exp.health = {"ok": True}
        exp.validation_status = "STABLE"
        evidence = self_correlation_evidence(exp.metrics)
        self.assertEqual(evidence["status"], "PASS")
        pool = SubmissionPool(self._tmp)
        pool.upsert(exp, "EXCELLENT", evidence, {"total": 1})
        with open(os.path.join(self._tmp, "submission_pool.json"), encoding="utf-8") as f:
            entry = json.load(f)["candidates"][0]
        self.assertEqual(entry["submission"], "MANUAL_REQUIRED")
        self.assertEqual(entry["self_correlation"]["status"], "PASS")

    def test_batch_upsert_writes_review_queue_once(self):
        pool = SubmissionPool(self._tmp)
        experiments = []
        for index in range(2):
            exp = Experiment(1, "h", f"rank(field_{index})", {}, [f"field_{index}"])
            exp.alpha_id = f"alpha-{index}"
            exp.proposal_id = f"proposal-{index}"
            exp.metrics = {"sharpe": 2.0}
            exp.health = {"ok": True}
            exp.validation_status = "STABLE"
            experiments.append((exp, "EXCELLENT", {"status": "PASS"}, None))
        with mock.patch("wqb_agent.submission.atomic_write_json_if_changed", wraps=atomic_write_json_if_changed) as writer:
            records = pool.upsert_many(experiments)
        self.assertEqual(len(records), 2)
        self.assertEqual(writer.call_count, 1)

    def test_pool_recovers_from_malformed_candidates_shape(self):
        path = os.path.join(self._tmp, "submission_pool.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"schema_version": 1, "candidates": ["bad", 3, {"alpha_id": "old"}]}, handle)
        exp = Experiment(1, "h", "rank(field)", {}, ["field"])
        exp.alpha_id = "new"
        exp.metrics = {"sharpe": 2.0}
        record = SubmissionPool(self._tmp).upsert(
            exp, "EXCELLENT", {"status": "PASS"}, None
        )
        self.assertEqual(record["alpha_id"], "new")
        with open(path, encoding="utf-8") as handle:
            self.assertEqual([item["alpha_id"] for item in json.load(handle)["candidates"]], ["old", "new"])

    def test_pending_self_correlation_is_not_failure(self):
        metrics = {
            "checks": [{
                "name": "SELF_CORRELATION",
                "pass": None,
                "result": "PENDING",
            }]
        }
        self.assertEqual(self_correlation_evidence(metrics)["status"], "PENDING")

    def test_result_only_self_correlation_is_normalized(self):
        metrics = {
            "checks": [{
                "name": "SELF_CORRELATION",
                "result": "PASS",
                "value": 0.2,
            }]
        }
        self.assertEqual(self_correlation_evidence(metrics)["status"], "PASS")


class TestMemory(TmpStateMixin, unittest.TestCase):
    def test_persistence_roundtrip(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        memory.add_lesson("Smoothing lowers turnover", 1, evidence=2)
        memory.add_avoid("rank(close)", "low sharpe", 1)
        memory.remember_expression("rank(close)")
        memory.save()
        loaded = ExperienceMemory(state_dir=self._tmp).load()
        self.assertEqual(len(loaded.lessons), 1)
        self.assertEqual(loaded.avoid[0]["direction"], "rank(close)")
        self.assertIn("rank(close)", loaded.seen_expressions)

    def test_reconcile_avoid_merges_truncated_and_full_keys(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        expression = "x" * 100
        memory.add_avoid(expression[:80], "wrong diagnosis", 1)
        memory.add_avoid(expression, "duplicate", 1)
        memory.reconcile_avoid(expression, "correct diagnosis", 2)
        self.assertEqual(len(memory.avoid), 1)
        self.assertEqual(memory.avoid[0]["direction"], expression[:80])
        self.assertEqual(memory.avoid[0]["reason"], "correct diagnosis")

    def test_compress_dedupes_lessons(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        memory.add_lesson("Rank fields on returns is weak", 1, evidence=2)
        memory.add_lesson("Rank fields on returns is weak", 2, evidence=1)
        memory.compress()
        self.assertEqual(len(memory.lessons), 1)

    def test_context_shape(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        memory.add_lesson("Some lesson", 1, evidence=1)
        ctx = memory.context(recent_experiments=[{"expression": "rank(x)"}])
        for key in (
            "current_best",
            "active_hypotheses",
            "recent_key_experiments",
            "lessons",
            "avoid",
            "next",
        ):
            self.assertIn(key, ctx)

    def test_used_hypotheses_persisted(self):
        memory = ExperienceMemory(state_dir=self._tmp)
        memory.register_hypothesis({"id": "h-1", "statement": "s", "_round": 1})
        memory.save()
        loaded = ExperienceMemory(state_dir=self._tmp).load()
        self.assertIn("h-1", loaded.used_hypotheses)


class TestTrajectory(TmpStateMixin, unittest.TestCase):
    def test_datasets_dict_entries_normalized(self):
        """proposal datasets 允许 {"id":...} 字典形态；Experiment 入口必须
        归一化为字符串 id，保证 trajectory/ResearchState 聚合可哈希。"""
        from wqb_agent.state import Experiment as Exp, dataset_ref
        exp = Exp(1, "h", "rank(x)", {}, ["x"],
                  datasets=[{"id": "pv1", "name": "Price Volume"},
                            "option8", {"name": "news18"}, None])
        self.assertEqual(exp.datasets, ["pv1", "option8", "news18"])
        self.assertEqual(dataset_ref({"id": "f2"}), "f2")
        self.assertIsNone(dataset_ref(None))
        # 聚合场景不再触发 unhashable dict
        pooled = sorted({d for d in exp.datasets})
        self.assertEqual(pooled, ["news18", "option8", "pv1"])

    def test_jsonl_append_only(self):
        path = os.path.join(self._tmp, "trajectory.jsonl")
        traj = Trajectory(max_len=100, path=path)
        e1 = Experiment(1, "h", "rank(a)", {}, ["a"])
        e1.status = "DONE"
        traj.add(e1)
        e2 = Experiment(2, "h", "rank(b)", {}, ["b"])
        e2.status = "DONE"
        traj.add(e2)
        with open(path, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        self.assertEqual(len(lines), 2)

        traj2 = Trajectory(max_len=100, path=path).load()
        self.assertEqual(len(traj2.experiments), 2)
        self.assertEqual(traj2.experiments[1].expression, "rank(b)")
        self.assertTrue(traj2.contains_id(e1.id))
        self.assertFalse(traj2.contains_id("missing-id"))

    def test_old_completed_parent_is_streamed_without_large_memory_window(self):
        path = os.path.join(self._tmp, "trajectory.jsonl")
        traj = Trajectory(max_len=10, path=path)
        old = Experiment(1, "h", "rank(old_signal)", {}, ["old_signal"])
        old.status = "DONE"
        old.metrics = {"sharpe": 1.0, "fitness": 1.0}
        recent = Experiment(2, "h", "rank(recent_signal)", {}, ["recent_signal"])
        recent.status = "DONE"
        recent.metrics = {"sharpe": 0.5, "fitness": 0.5}
        traj.add(old)
        traj.add(recent)

        bounded = Trajectory(max_len=1, path=path).load()

        self.assertEqual(len(bounded.experiments), 1)
        restored = bounded.find_completed_expression("rank( old_signal )")
        self.assertIsNotNone(restored)
        self.assertEqual(restored.id, old.id)
        self.assertIs(restored, bounded.find_completed_expression("rank(old_signal)"))

    def test_multiple_old_parents_share_one_streaming_lookup(self):
        path = os.path.join(self._tmp, "trajectory.jsonl")
        traj = Trajectory(max_len=1, path=path)
        expected_ids = set()
        for number, expression in ((1, "rank(old_a)"), (2, "rank(old_b)")):
            exp = Experiment(number, "h", expression, {}, [expression])
            exp.status = "DONE"
            exp.metrics = {"sharpe": 1.0, "fitness": 1.0}
            traj.add(exp)
            expected_ids.add(exp.id)

        with mock.patch("builtins.open", wraps=open) as opened:
            resolved = traj.find_completed_expressions(
                ["rank(old_a)", "rank( old_b )"]
            )
        self.assertEqual({item.id for item in resolved.values()}, expected_ids)
        trajectory_reads = [
            call for call in opened.call_args_list
            if str(call.args[0]).endswith("trajectory.jsonl")
        ]
        self.assertEqual(len(trajectory_reads), 1)

    def test_completed_parent_cache_is_bounded(self):
        traj = Trajectory(max_len=1)
        traj.find_completed_expressions(
            [f"rank(cache_{index})" for index in range(600)]
        )
        self.assertLessEqual(
            len(traj._completed_expression_cache),
            Trajectory.COMPLETED_EXPRESSION_CACHE_MAX,
        )


class TestAgentLoop(TmpStateMixin, unittest.TestCase):
    def test_current_discovery_type_overlays_cached_type(self):
        agent, _ = make_agent(self._tmp, rounds=1)
        result = agent._known_field_types(
            {"fields": [{"id": "shared", "type": "VECTOR"}]},
            cached_field_types={"shared": "MATRIX", "cached_only": "MATRIX"},
        )
        self.assertEqual(result["shared"], "VECTOR")
        self.assertEqual(result["cached_only"], "MATRIX")

    def test_malformed_numeric_metrics_fail_closed(self):
        agent, _ = make_agent(self._tmp, rounds=1)
        self.assertEqual(
            agent._alpha_rating({
                "sharpe": "not-a-number", "fitness": 2,
                "turnover": 0.1, "margin": 0.01,
            }),
            "UNRATED",
        )

    def test_legacy_automatic_loop_is_blocked(self):
        agent, client = make_agent(self._tmp, rounds=2)
        with self.assertRaises(RuntimeError):
            agent.run()
        self.assertEqual(client.sim_calls, [])

    def test_legacy_single_round_is_blocked(self):
        agent, client = make_agent(self._tmp, rounds=2)
        with self.assertRaises(RuntimeError):
            agent.run_one_round(1)
        self.assertEqual(client.sim_calls, [])

    def test_legacy_path_cannot_resimulate_seen_expressions(self):
        agent, client = make_agent(self._tmp, rounds=1)
        with self.assertRaises(RuntimeError):
            agent.run()
        self.assertEqual(client.sim_calls, [])

    def test_legacy_path_does_not_write_research_state(self):
        agent, client = make_agent(self._tmp, rounds=1)
        with self.assertRaises(RuntimeError):
            agent.run_one_round(1)
        self.assertFalse(os.path.exists(os.path.join(self._tmp, "context.md")))

    def test_suggestion_exports_real_fields_bundle(self):
        agent, client = make_agent(self._tmp, rounds=1)
        agent.run_suggestion_round(round_no=1)
        path = os.path.join(self._tmp, "suggestions.json")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            bundle = json.load(f)
        self.assertEqual(bundle["round_no"], 1)
        self.assertGreater(len(bundle["fields"]), 0)
        self.assertIn("context", bundle)
        self.assertIn("current_best", bundle["context"])
        self.assertGreaterEqual(len(bundle["alpha_templates"]), 6)
        self.assertIn("research_guard", bundle)
        self.assertEqual(bundle["research_guard"]["policy"], "same_change_type_no_gain_guard")

    def test_stalled_dataset_rotates_to_an_unseen_family(self):
        agent, _ = make_agent(self._tmp, rounds=1)
        for index in range(12):
            experiment = Experiment(
                10 + index, "h-analyst", f"rank(field_{index})", {},
                [f"field_{index}"], ["analyst4"],
            )
            experiment.status = "DONE"
            agent.trajectory.add(experiment)

        rotated = agent._rotate_stalled_research_space(
            {"id": "analyst", "statement": "test", "datasets": ["analyst4"]},
            round_no=11,
        )

        self.assertNotIn("analyst4", rotated["datasets"])
        self.assertTrue(rotated.get("rotation_reason"))

    def test_suggestion_falls_back_after_empty_discovery(self):
        agent, client = make_agent(self._tmp, rounds=1)
        calls = []

        def discover(space, target_count):
            calls.append(space["datasets"])
            if len(calls) == 1:
                return []
            return [{
                "id": "cashflow_op",
                "name": "Operating cash flow",
                "description": "Operating cash flow generated by the business",
                "dataset": "fundamental6",
                "type": "MATRIX",
                "coverage": 0.9,
                "frequency": None,
                "alpha_count": 1,
                "semantic_status": "KNOWN",
                "field_source": agent.discovery.source_provenance(),
            }]

        agent.discovery.discover = discover
        bundle = agent.run_suggestion_round(round_no=1)

        self.assertEqual(len(calls), 2)
        self.assertEqual(bundle["research_space"]["datasets"], ["fundamental6", "fundamental2"])
        self.assertEqual(bundle["fields"][0]["id"], "cashflow_op")

    def test_suggestion_keeps_previous_bundle_fields(self):
        """2026-08-22 政策：字段级全量排除已删除，上轮字段可再次进入 discovery；
        重复防护收敛到 run_proposals 的表达式级去重。"""
        agent, client = make_agent(self._tmp, rounds=1)
        previous = os.path.join(self._tmp, "suggestions.json")
        with open(previous, "w", encoding="utf-8") as f:
            json.dump({"round_no": 0, "fields": [{"id": "old_field"}]}, f)

        def discover(space, target_count):
            return [
                {"id": "old_field", "description": "old", "type": "MATRIX"},
                {"id": "new_field", "description": "new", "type": "MATRIX"},
            ]

        agent.discovery.discover = discover
        bundle = agent.run_suggestion_round(round_no=1)

        self.assertEqual(
            [field["id"] for field in bundle["fields"]], ["old_field", "new_field"]
        )

    def test_suggestion_keeps_fields_outside_trajectory_window(self):
        """2026-08-22 政策：trajectory 历史字段不再被 discovery 排除。"""
        agent, client = make_agent(self._tmp, rounds=1)
        with open(agent.trajectory.path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"round": 1, "fields_used": ["old_field"]}) + "\n")

        def discover(space, target_count):
            return [
                {"id": "old_field", "description": "old", "type": "MATRIX"},
                {"id": "new_field", "description": "new", "type": "MATRIX"},
            ]

        agent.discovery.discover = discover
        bundle = agent.run_suggestion_round(round_no=1)

        self.assertEqual(
            [field["id"] for field in bundle["fields"]], ["old_field", "new_field"]
        )

    def test_epoch_label_hex(self):
        """rb 纪元标签：r619->rb0, r620->rb1, r634->rbf, r635->rb10。"""
        agent, _ = make_agent(self._tmp, rounds=1)
        self.assertEqual(agent.epoch_label(619), "rb0")
        self.assertEqual(agent.epoch_label(620), "rb1")
        self.assertEqual(agent.epoch_label(634), "rbf")
        self.assertEqual(agent.epoch_label(635), "rb10")

    def test_run_proposals_executes_llm_candidates(self):
        agent, client = make_agent(self._tmp, rounds=1)
        proposals = {
            "round_no": 1,
            "hypothesis": {
                "id": "h-llm-1",
                "statement": "LLM proposed reversal with ts_zscore smoothing.",
                "tags": ["llm"],
                "direction": "long",
            },
            "fields": [
                {"id": "returns", "dataset": "pv1", "type": "MATRIX", "description": "daily simple returns", "semantic_status": "KNOWN"},
                {"id": "volume", "dataset": "pv1", "type": "MATRIX", "description": "daily trading volume", "semantic_status": "KNOWN"},
            ],
            "proposals": [
                {
                    "expression": "-rank(ts_zscore(returns, 20))",
                    "hypothesis": "短期收益反转：5 日大涨后均值回归。",
                    "rationale": "r84 后反转信号在短窗有效（记忆证据）。",
                    "direction": "reversal",
                    "expected_horizon": "20 天 z-score 反转，短窗生效（63 内）",
                    "falsification": "S<0.5 或方向反号即放弃",
                    "fields": ["returns"],
                    "datasets": ["pv1"],
                    "field_understanding": {"returns": "每日简单收益率，代表近期价格变化。"},
                    "operator_mapping": "ts_zscore 衡量异常涨跌，rank 形成横截面对比。",
                    "experiment_question": "异常短期收益是否会在随后一个月反转？",
                    "field_analysis": {"returns": {"semantic": "daily simple returns", "coverage": None, "frequency": None, "data_type": "MATRIX"}},
                    "expected_failure_modes": ["sharpe", "turnover"],
                    "tuning_risk": False,
                    "experiment_stage": "BASELINE",
                },
                {
                    "expression": "-rank(ts_zscore(returns, 20))",
                    "hypothesis": "duplicate of above.",
                },
                {
                    "expression": "rank(ts_mean(volume, 5))",
                    "hypothesis": "成交量 5 日均值：放量预示持续关注。",
                    "rationale": "second structure",
                    "direction": "long",
                    "expected_horizon": "5 天均值，短期",
                    "falsification": "S<0.5 即放弃",
                    "fields": ["volume"],
                    "datasets": ["pv1"],
                    "field_understanding": {"volume": "每日成交量，代表市场注意力与交易参与。"},
                    "operator_mapping": "短期均值降低单日成交量噪声，rank 比较相对注意力。",
                    "experiment_question": "持续放量是否对应后续收益延续？",
                    "field_analysis": {"volume": {"semantic": "daily trading volume", "coverage": None, "frequency": None, "data_type": "MATRIX"}},
                    "expected_failure_modes": ["sharpe"],
                    "tuning_risk": False,
                    "experiment_stage": "BASELINE",
                },
            ],
        }
        with open(os.path.join(self._tmp, "proposals.json"), "w", encoding="utf-8") as f:
            json.dump(proposals, f, ensure_ascii=False)
        summary = agent.run_proposals(os.path.join(self._tmp, "proposals.json"))
        self.assertIsNotNone(summary)
        # 重复提案被去重：只模拟 2 个
        self.assertEqual(len(client.sim_calls), 2)
        self.assertEqual(summary["experiment_count"], 2)
        self.assertIsNone(agent.memory.current_best)
        self.assertTrue(any(x["kind"] == "observation" for x in agent.memory.short_term))
        # trajectory 完整记录
        self.assertEqual(len(agent.trajectory.experiments), 2)
        for exp in agent.trajectory.experiments:
            self.assertTrue(exp.proposal_id.startswith("p-"))
            self.assertEqual(len(exp.submission_fingerprint), 64)
            self.assertIsNotNone(exp.submission_started_at)

    def test_run_proposals_caps_same_structural_family_without_template_metadata(self):
        """Sibling fields must not multiply one operator/window skeleton."""
        agent, client = make_agent(self._tmp, rounds=1)
        field_rows = [
            {
                "id": f"analyst_field_{i}",
                "dataset": "analyst4",
                "type": "MATRIX",
                "description": f"verified analyst field {i}",
                "semantic_status": "KNOWN",
            }
            for i in range(4)
        ]
        proposals = {
            "round_no": 1,
            "hypothesis": {"id": "h-structural", "statement": "same skeleton"},
            "fields": field_rows,
            "proposals": [
                {
                    "expression": f"rank(ts_delta(analyst_field_{i}, 5))",
                    "fields": [f"analyst_field_{i}"],
                    "datasets": ["analyst4"],
                    "field_understanding": {
                        f"analyst_field_{i}": "verified analyst signal",
                    },
                    "field_analysis": {
                        f"analyst_field_{i}": {
                            "semantic": "verified analyst signal",
                            "coverage": None,
                            "frequency": None,
                            "data_type": "MATRIX",
                        },
                    },
                    "operator_mapping": "ts_delta measures the field change; rank compares it cross-sectionally",
                    "experiment_question": "Does the five-day field change carry information?",
                    "expected_failure_modes": ["weak signal"],
                    "tuning_risk": False,
                    "experiment_stage": "BASELINE",
                }
                for i in range(4)
            ],
        }
        path = os.path.join(self._tmp, "proposals.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(proposals, handle, ensure_ascii=False)

        summary = agent.run_proposals(path)

        self.assertIsNotNone(summary)
        self.assertEqual(len(client.sim_calls), 2)
        self.assertEqual(summary["experiment_count"], 2)

    def test_validate_proposal_allows_retired_question_fields_to_be_omitted(self):
        """旧的解释性字段不再是生产预检条件。"""
        ok, problems = validate_proposal(
            {
                "expression": "-rank(ts_zscore(returns, 20))",
                "fields": ["returns"],
            }
        )
        self.assertTrue(ok, problems)

    def test_run_proposals_accepts_traceable_proposal_without_retired_fields(self):
        agent, client = make_agent(self._tmp, rounds=1)
        field = {
            "id": "returns", "dataset": "pv1", "type": "MATRIX",
            "description": "daily returns", "semantic_status": "KNOWN",
            "coverage": None, "frequency": None,
        }
        proposal = {
            "expression": "rank(returns)",
            "fields": ["returns"], "datasets": ["pv1"],
            "field_understanding": {"returns": "daily stock returns"},
            "field_analysis": {"returns": {
                "semantic": "daily returns", "coverage": None,
                "frequency": None, "data_type": "MATRIX",
            }},
            "field_source": {
                "kind": "local_catalog", "path": "snapshot",
                "snapshot_date": "2026-09-03",
            },
            "field_hypothesis_basis": {"returns": {
                "description": "daily returns",
                "mechanism": "Tests cross-sectional return strength.",
            }},
            "operator_mapping": "rank compares cross-sectional return strength",
            "operator_evidence": {
                "sha256": agent.operator_reference["sha256"],
                "operators": ["rank"], "rationale": "rank is documented",
            },
            "experiment_question": "Does return strength carry information?",
            "expected_failure_modes": ["weak sharpe"], "tuning_risk": False,
            "experiment_stage": "BASELINE", "research_role": "EXPLORE",
        }
        path = os.path.join(self._tmp, "proposals.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "round_no": 1,
                "hypothesis": {"id": "h-preflight", "statement": "traceable proposal"},
                "fields": [field], "proposals": [proposal],
            }, f, ensure_ascii=False)
        summary = agent.run_proposals(path)
        self.assertIsNotNone(summary)
        self.assertEqual(client.sim_calls, ["rank(returns)"])

    def test_vec_operators_require_vector_input(self):
        proposal = {"expression": "rank(vec_avg(news_vector))"}
        ok, problems = validate_vector_inputs(
            proposal, {"news_vector": "VECTOR"}
        )
        self.assertTrue(ok, problems)

        ok, problems = validate_vector_inputs(
            proposal, {"news_vector": "MATRIX"}
        )
        self.assertFalse(ok)
        self.assertTrue(any("只能作用于 VECTOR" in p for p in problems))

        ok, problems = validate_vector_inputs(proposal, {})
        self.assertFalse(ok)
        self.assertTrue(any("类型未知" in p for p in problems))

        # direction 现在只是可选元数据，不参与生产预检。
        ok, problems = validate_proposal(
            {
                "expression": "rank(x)",
                "hypothesis": "h",
                "rationale": "r",
                "direction": "sideways",
                "expected_horizon": "63",
                "falsification": "S<1",
                "fields": ["x"],
            }
        )
        self.assertTrue(ok, problems)

        # 同一表达式带旧元数据时仍兼容。
        ok, problems = validate_proposal(
            {
                "expression": "rank(x)",
                "hypothesis": "h",
                "rationale": "r",
                "direction": "long",
                "expected_horizon": "63",
                "falsification": "S<1",
                "fields": ["x"],
            }
        )
        self.assertTrue(ok, problems)

        # 集成：结构性证据缺失时仍不发起模拟。
        agent, client = make_agent(self._tmp, rounds=1)
        proposals = {
            "round_no": 1,
            "hypothesis": {
                "id": "h-llm-1",
                "statement": "incomplete-preflight",
                "tags": ["llm"],
                "direction": "long",
            },
            "proposals": [
                {"expression": "-rank(ts_zscore(returns, 20))", "hypothesis": "x"},
            ],
        }
        with open(os.path.join(self._tmp, "proposals.json"), "w", encoding="utf-8") as f:
            json.dump(proposals, f, ensure_ascii=False)
        summary = agent.run_proposals(os.path.join(self._tmp, "proposals.json"))
        self.assertIsNone(summary)
        self.assertEqual(len(client.sim_calls), 0)
        self.assertEqual(len(agent.trajectory.experiments), 0)

    def test_proposal_settings_merge_defaults_and_reject_unknown(self):
        agent, _client = make_agent(self._tmp, rounds=1)
        merged = agent._proposal_settings({"decay": 7})
        self.assertEqual(merged["decay"], 7)
        self.assertEqual(merged["region"], "USA")
        self.assertEqual(merged["neutralization"], "SUBINDUSTRY")
        with self.assertRaises(ValueError):
            agent._proposal_settings({"region": "EUROPE"})
        with self.assertRaises(ValueError):
            agent._proposal_settings({"decay": 11})

    def test_run_proposals_blocks_vector_input_type_mismatch(self):
        agent, client = make_agent(self._tmp, rounds=1)
        # Seed a real-looking discovery bundle so the preflight can resolve
        # the field type without contacting the platform.
        proposals = {
            "round_no": 1,
            "hypothesis": {"id": "h-vector", "statement": "vector to matrix", "direction": "long"},
            "fields": [{"id": "news_vector", "type": "MATRIX", "dataset": "news18"}],
            "proposals": [{
                "expression": "rank(vec_avg(news_vector))",
                "hypothesis": "vector input test",
                "rationale": "type gate test",
                "direction": "long",
                "expected_horizon": "63 days",
                "falsification": "S<1",
                "fields": ["news_vector"],
            }],
        }
        path = os.path.join(self._tmp, "proposals.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(proposals, f, ensure_ascii=False)
        self.assertIsNone(agent.run_proposals(path))
        self.assertEqual(len(client.sim_calls), 0)

    def test_validate_proposal_requires_declared_field_in_expression(self):
        from wqb_agent.agent import validate_proposal

        ok, problems = validate_proposal({
            "expression": "rank(returns)",
            "hypothesis": "h",
            "rationale": "evidence",
            "direction": "long",
            "expected_horizon": "63 days",
            "falsification": "sharpe < 1",
            "fields": ["close"],
        })
        self.assertFalse(ok)
        self.assertTrue(any("expression" in p for p in problems))
        ok, problems = validate_proposal({
            "expression": "rank(returns)", "hypothesis": "h",
            "rationale": "evidence", "direction": "long",
            "expected_horizon": "63 days", "falsification": "sharpe < 1",
            "fields": "returns",
        })
        self.assertFalse(ok)
        self.assertTrue(any("非空数组" in p for p in problems))

    def test_expression_identifier_allowlist_covers_cheatsheet_operators(self):
        """2026-08-22 算子放开政策：cheatsheet 收录的算子（hump/ts_corr 等）
        与常用命名参数不得被当作未知字段拦截。回归：r622 hump 误拦。"""
        from wqb_agent.agent import validate_proposal

        base = {
            "hypothesis": "h", "rationale": "e", "direction": "reversal",
            "expected_horizon": "5 days", "falsification": "S<1",
        }
        for expr in (
            "-rank(hump(ts_mean(vec_avg(two_hour_price_change_percent),5),hump=0.005))",
            "quantile(-rank(ts_av_diff(doubtful_accounts_write_offs,4)),driver=gaussian)",
            "quantile(-rank(ts_av_diff(doubtful_accounts_write_offs,4)),driver=cauchy,sigma=1)",
            "kth_element(doubtful_accounts_write_offs,10,1)",
            "trade_when(ts_rank(vec_avg(volume_at_open),63)>0.5,-rank(ts_mean(vec_avg(two_hour_price_change_percent),5)),-1)",
            "-rank(days_from_last_change(anl4_ffo_flag))",
            "-rank(last_diff_value(anl4_netdebt_flag,20))",
        ):
            ok, problems = validate_proposal({
                "expression": expr,
                "fields": ["two_hour_price_change_percent", "volume_at_open",
                            "doubtful_accounts_write_offs", "anl4_ffo_flag",
                            "anl4_netdebt_flag"],
                **base,
            })
            self.assertTrue(
                ok, f"expression blocked: {expr} -> {problems}"
            )
        # 真正的未知字段仍必须被拦截
        ok, problems = validate_proposal({
            "expression": "rank(fabricated_field_xyz)", "fields": ["close"], **base,
        })
        self.assertFalse(ok)


    def test_strict_proposal_rejects_undiscovered_or_unexplained_field(self):
        proposal = {
            "expression": "rank(returns)",
            "hypothesis": "h", "rationale": "e", "direction": "long",
            "expected_horizon": "63 days", "falsification": "S<1",
            "fields": ["returns"], "datasets": ["pv1"],
            "operator_mapping": "rank compares cross-sectional strength",
            "experiment_question": "does the effect predict returns?",
            "field_understanding": {},
        }
        ok, problems = validate_proposal(
            proposal,
            discovered_fields=[
                {"id": "returns", "description": "daily returns",
                 "semantic_status": "KNOWN", "dataset": "pv1"},
            ],
            strict_experiment=True,
        )
        self.assertFalse(ok)
        self.assertTrue(any("field_understanding" in p for p in problems))
        proposal["field_understanding"] = {"returns": "daily stock return"}
        ok, problems = validate_proposal(
            proposal,
            discovered_fields=[],
            strict_experiment=True,
        )
        self.assertFalse(ok)
        self.assertTrue(any("discovery" in p for p in problems))

        proposal["expression"] = "rank(returns + fabricated_field)"
        ok, problems = validate_proposal(
            proposal,
            discovered_fields=[
                {"id": "returns", "description": "daily returns",
                 "semantic_status": "KNOWN", "dataset": "pv1"},
            ],
            strict_experiment=True,
        )
        self.assertFalse(ok)
        self.assertTrue(any("fabricated_field" in p for p in problems))

    def test_other_unfinished_checkpoint_blocks_new_round(self):
        agent, client = make_agent(self._tmp, rounds=1)
        checkpoint = {
            "round_no": 7,
            "complete": False,
            "experiments": [],
            "hypothesis": {"id": "h-7"},
        }
        with open(os.path.join(self._tmp, "round_7.checkpoint.json"), "w",
                  encoding="utf-8") as f:
            json.dump(checkpoint, f)
        payload = {"round_no": 8, "proposals": []}
        path = os.path.join(self._tmp, "proposals.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        self.assertIsNone(agent.run_proposals(path))
        self.assertEqual(client.sim_calls, [])

    def test_malformed_checkpoint_fails_closed_before_resume(self):
        agent, client = make_agent(self._tmp, rounds=1)
        checkpoint_path = os.path.join(self._tmp, "round_1.checkpoint.json")
        with open(checkpoint_path, "w", encoding="utf-8") as handle:
            json.dump({
                "round_no": 1,
                "complete": False,
                "hypothesis": {"id": "h-1"},
                "experiments": [{"id": "only-partial-row"}],
            }, handle)
        proposals_path = os.path.join(self._tmp, "proposals.json")
        with open(proposals_path, "w", encoding="utf-8") as handle:
            json.dump({"round_no": 1, "proposals": []}, handle)
        self.assertIsNone(agent.run_proposals(proposals_path))
        self.assertEqual(client.sim_calls, [])
        with open(checkpoint_path, encoding="utf-8") as handle:
            self.assertFalse(json.load(handle)["complete"])

    def test_skip_stale_requires_three_reconciliations_and_records_terminal_state(self):
        agent, client = make_agent(self._tmp, rounds=1)
        exp = Experiment(1797, "h-1797", "rank(put_iv)", BASE_CONFIG["simulation"], ["put_iv"], ["option8"])
        exp.status = "UNKNOWN"
        exp.progress_url = "https://api.worldquantbrain.com/simulations/remote-1797"
        agent._write_proposal_checkpoint(1797, {"id": "h-1797"}, [exp], complete=False)
        history_path = os.path.join(self._tmp, "reconcile_history.jsonl")
        rows = [{"simulation_id": "remote-1797", "outcome": "STALE", "reconciled_at": str(i)}
                for i in range(2)]
        with open(history_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        with self.assertRaises(ValueError):
            agent.skip_stale_reconciled(1797, "remote-1797")
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"simulation_id": "remote-1797", "outcome": "STALE",
                                "reconciled_at": "2"}) + "\n")
        skipped = agent.skip_stale_reconciled(1797, "remote-1797")
        self.assertEqual(skipped.status, "SKIPPED_STALE")
        self.assertEqual(skipped.skip_record["attempts"], 3)
        with open(os.path.join(self._tmp, "round_1797.checkpoint.json"), encoding="utf-8") as f:
            self.assertTrue(json.load(f)["complete"])
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "stale_skip_log.jsonl")))
        self.assertEqual(client.sim_calls, [])

    def test_explicit_force_new_round_preserves_old_checkpoint(self):
        agent, client = make_agent(self._tmp, rounds=1)
        checkpoint = {
            "round_no": 7,
            "complete": False,
            "experiments": [],
            "hypothesis": {"id": "h-7"},
        }
        with open(os.path.join(self._tmp, "round_7.checkpoint.json"), "w",
                  encoding="utf-8") as f:
            json.dump(checkpoint, f)
        payload = {"round_no": 8, "fields": [{
            "id": "returns", "dataset": "pv1", "type": "MATRIX",
            "description": "daily return", "semantic_status": "KNOWN",
        }], "proposals": [{
            "expression": "rank(returns)", "hypothesis": "return signal",
            "rationale": "explicit user-authorized new round", "direction": "long",
            "expected_horizon": "63 days", "falsification": "S<1",
            "fields": ["returns"], "datasets": ["pv1"],
            "field_understanding": {"returns": "daily return"},
            "field_hypothesis_basis": {"returns": {
                "description": "daily return", "mechanism": "return signal",
            }},
            "operator_mapping": "rank creates a cross-section",
            "operator_evidence": {
                "sha256": agent.operator_reference["sha256"],
                "operators": ["rank"], "rationale": "documented rank",
            },
            "experiment_question": "does return predict future return?",
            "field_analysis": {"returns": {"semantic": "daily return",
                "coverage": None, "frequency": None, "data_type": "MATRIX"}},
            "expected_failure_modes": ["sharpe"], "tuning_risk": False,
            "experiment_stage": "BASELINE",
        }]}
        path = os.path.join(self._tmp, "proposals.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        agent.run_proposals(path, allow_unresolved_checkpoint=True)
        self.assertEqual(client.sim_calls, ["rank(returns)"])
        with open(os.path.join(self._tmp, "round_7.checkpoint.json"),
                  encoding="utf-8") as f:
            self.assertFalse(json.load(f)["complete"])

    def test_proposal_priority_cap_never_spends_over_budget(self):
        agent, client = make_agent(self._tmp, rounds=1)
        agent.candidates_per_round = 1
        fields = [
            {"id": f, "dataset": "pv1", "type": "MATRIX", "description": f"{f} profile",
             "semantic_status": "KNOWN"}
            for f in ("returns", "close", "volume")
        ]
        proposals = []
        for field, quality in (("returns", 1), ("close", 3), ("volume", 2)):
            proposals.append({
                "expression": f"rank({field})", "hypothesis": f"{field} effect",
                "rationale": "test evidence", "direction": "long",
                "expected_horizon": "63 days", "falsification": "S<1",
                "fields": [field], "datasets": ["pv1"],
                "field_understanding": {field: f"{field} meaning"},
                "operator_mapping": "rank converts the field to a cross-section",
                "experiment_question": f"does {field} predict returns?",
                "field_analysis": {field: {"semantic": f"{field} profile", "coverage": None, "frequency": None, "data_type": "MATRIX"}},
                "expected_failure_modes": ["sharpe"],
                "tuning_risk": False,
                "experiment_stage": "BASELINE",
                "expected_quality": quality,
            })
        path = os.path.join(self._tmp, "proposals.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"round_no": 1, "fields": fields, "proposals": proposals}, f)
        agent.run_proposals(path)
        self.assertEqual(client.sim_calls, ["rank(close)"])

    def test_research_allocation_allows_cold_start_explore(self):
        agent, client = make_agent(self._tmp, rounds=1)
        agent.candidates_per_round = 18
        agent.research_allocation = {
            "max_simulations": 18,
            "maximum": {"EXPLOIT": 4, "VALIDATION": 4},
        }
        proposal = {
            "expression": "rank(returns)", "hypothesis": "one candidate",
            "rationale": "single candidate test", "direction": "long",
            "expected_horizon": "63 days", "falsification": "S<1",
            "fields": ["returns"], "datasets": ["pv1"],
            "field_understanding": {"returns": "daily return"},
            "operator_mapping": "rank creates a cross-section",
            "field_hypothesis_basis": {"returns": {
                "description": "daily return", "mechanism": "cross-sectional return contains the tested signal",
            }},
            "operator_evidence": {
                "sha256": agent.operator_reference["sha256"], "operators": ["rank"],
                "rationale": "rank is documented for cross-sectional comparison",
            },
            "experiment_question": "does return predict future return?",
            "field_analysis": {"returns": {"semantic": "daily return",
                "coverage": None, "frequency": None, "data_type": "MATRIX"}},
            "expected_failure_modes": ["sharpe"], "tuning_risk": False,
            "experiment_stage": "BASELINE", "research_role": "EXPLORE",
            "field_source": {"kind": "local_catalog", "path": "snapshot", "snapshot_date": "2026-08-22"},
        }
        path = os.path.join(self._tmp, "proposals.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"round_no": 1,
                       "fields": [{"id": "returns", "dataset": "pv1",
                                   "type": "MATRIX", "description": "daily return",
                                   "semantic_status": "KNOWN"}],
                       "proposals": [proposal]}, f)
        self.assertIsNotNone(agent.run_proposals(path))
        self.assertEqual(client.sim_calls, ["rank(returns)"])

    def test_production_contract_requires_description_and_operator_evidence(self):
        fields = [{"id": "returns", "type": "MATRIX", "description": "daily return",
                   "semantic_status": "KNOWN", "alpha_count": 2}]
        proposal = {
            "expression": "rank(returns)", "hypothesis": "return effect", "rationale": "test",
            "direction": "long", "expected_horizon": "20d", "falsification": "S<1",
            "fields": ["returns"], "datasets": ["pv1"],
            "field_understanding": {"returns": "daily return"},
            "field_analysis": {"returns": {"semantic": "daily return", "coverage": 1,
                "frequency": None, "data_type": "MATRIX"}},
            "operator_mapping": "rank compares stocks", "experiment_question": "does it work?",
            "expected_failure_modes": ["sharpe"], "tuning_risk": False,
            "experiment_stage": "BASELINE",
        }
        agent, _ = make_agent(self._tmp, rounds=1)
        ok, problems = validate_proposal(
            proposal, discovered_fields=fields, strict_experiment=True,
            operator_reference=agent.operator_reference, require_research_evidence=True,
            max_alpha_count=10,
        )
        self.assertFalse(ok)
        self.assertTrue(any("field_hypothesis_basis" in problem for problem in problems))
        self.assertTrue(any("operator_evidence" in problem for problem in problems))

    def test_verified_field_profiles_supplement_current_discovery(self):
        agent, _ = make_agent(self._tmp, rounds=1)
        cache = {
            "schema": 2,
            "saved_at": time.time(),
            "datasets": {
                "option9": [{
                    "id": "verified_option_field",
                    "description": "verified option metadata",
                    "type": "MATRIX",
                    "coverage": 0.91,
                }],
            },
        }
        with open(os.path.join(self._tmp, "fields_cache.json"), "w",
                  encoding="utf-8") as f:
            json.dump(cache, f)
        profiles = agent._verified_field_profiles()
        self.assertEqual(profiles["verified_option_field"]["dataset"], "option9")
        self.assertEqual(profiles["verified_option_field"]["semantic_status"], "KNOWN")

    def test_field_cache_reader_returns_types_and_profiles_together(self):
        agent, _ = make_agent(self._tmp, rounds=1)
        cache = {
            "schema": 2,
            "saved_at": time.time(),
            "datasets": {
                "pv1": [
                    {"id": "typed_only", "type": "MATRIX"},
                    {"id": "verified", "type": "VECTOR", "description": "vector field"},
                ]
            },
        }
        with open(os.path.join(self._tmp, "fields_cache.json"), "w", encoding="utf-8") as f:
            json.dump(cache, f)
        types, profiles = agent._read_field_cache()
        self.assertEqual(types["typed_only"], "MATRIX")
        self.assertEqual(types["verified"], "VECTOR")
        self.assertEqual(profiles["verified"]["dataset"], "pv1")
        self.assertNotIn("typed_only", profiles)

    def test_proposal_requires_field_analysis_and_one_variable_child_contract(self):
        from wqb_agent.agent import validate_proposal

        proposal = {
            "expression": "rank(returns)", "hypothesis": "return effect",
            "rationale": "test", "direction": "long", "expected_horizon": "63d",
            "falsification": "S<1", "fields": ["returns"], "datasets": ["pv1"],
            "field_understanding": {"returns": "daily return"},
            "operator_mapping": "rank creates a cross-section",
            "experiment_question": "does return predict future return?",
            "expected_failure_modes": ["sharpe"], "tuning_risk": False,
            "experiment_stage": "CHILD", "change_type": "window_change",
            "parent_expression": "rank(ts_mean(returns, 20))",
        }
        fields = [{"id": "returns", "dataset": "pv1", "type": "MATRIX",
                   "description": "daily return", "semantic_status": "KNOWN"}]
        ok, problems = validate_proposal(proposal, discovered_fields=fields,
                                         strict_experiment=True)
        self.assertFalse(ok)
        self.assertTrue(any("changed_variable" in p for p in problems))
        proposal["changed_variable"] = "window: 20 -> raw"
        proposal["field_analysis"] = {"returns": {
            "semantic": "daily return", "coverage": None, "frequency": None,
            "data_type": "MATRIX",
        }}
        ok, problems = validate_proposal(proposal, discovered_fields=fields,
                                         strict_experiment=True)
        self.assertTrue(ok, problems)

    def test_documented_ts_arg_min_is_not_treated_as_unknown_field(self):
        from wqb_agent.agent import validate_proposal

        proposal = {
            "expression": "-rank(ts_zscore(close, 7))+0.2*rank(ts_arg_min(close, 30))",
            "hypothesis": "price reversal", "rationale": "documented operator",
            "direction": "reversal", "expected_horizon": "7-30d",
            "falsification": "Sharpe<0.8", "fields": ["close"],
            "datasets": ["pv1"], "field_understanding": {"close": "daily close"},
            "field_analysis": {"close": {"semantic": "Daily close price",
                "coverage": 1.0, "frequency": None, "data_type": "MATRIX"}},
            "operator_mapping": "ts_arg_min locates the recent low",
            "experiment_question": "does price location add information?",
            "expected_failure_modes": ["sharpe"], "tuning_risk": False,
            "experiment_stage": "BASELINE",
        }
        fields = [{"id": "close", "dataset": "pv1", "type": "MATRIX",
                   "description": "Daily close price", "semantic_status": "KNOWN"}]
        ok, problems = validate_proposal(proposal, discovered_fields=fields,
                                         strict_experiment=True)
        self.assertTrue(ok, problems)

    def test_documented_ts_arg_max_is_not_treated_as_unknown_field(self):
        from wqb_agent.agent import validate_proposal

        proposal = {
            "expression": "rank(ts_zscore(close, 7))+0.2*rank(ts_arg_max(close, 30))",
            "hypothesis": "price location", "rationale": "documented operator",
            "direction": "long", "expected_horizon": "7-30d",
            "falsification": "Sharpe<0.8", "fields": ["close"],
            "datasets": ["pv1"], "field_understanding": {"close": "daily close"},
            "field_analysis": {"close": {"semantic": "Daily close price",
                "coverage": 1.0, "frequency": None, "data_type": "MATRIX"}},
            "operator_mapping": "ts_arg_max locates the recent high",
            "experiment_question": "does price location add information?",
            "expected_failure_modes": ["sharpe"], "tuning_risk": False,
            "experiment_stage": "BASELINE",
        }
        fields = [{"id": "close", "dataset": "pv1", "type": "MATRIX",
                   "description": "Daily close price", "semantic_status": "KNOWN"}]
        ok, problems = validate_proposal(proposal, discovered_fields=fields,
                                         strict_experiment=True)
        self.assertTrue(ok, problems)

    def test_documented_ts_decay_linear_is_not_treated_as_unknown_field(self):
        from wqb_agent.agent import validate_proposal

        proposal = {
            "expression": "rank(ts_decay_linear(ts_zscore(close, 20), 5))",
            "hypothesis": "smoothed price effect", "rationale": "documented operator",
            "direction": "long", "expected_horizon": "20d",
            "falsification": "Sharpe<0.8", "fields": ["close"],
            "datasets": ["pv1"], "field_understanding": {"close": "daily close"},
            "field_analysis": {"close": {"semantic": "Daily close price",
                "coverage": 1.0, "frequency": None, "data_type": "MATRIX"}},
            "operator_mapping": "decay linear smooths the signal",
            "experiment_question": "does smoothing add information?",
            "expected_failure_modes": ["sharpe"], "tuning_risk": False,
            "experiment_stage": "BASELINE",
        }
        fields = [{"id": "close", "dataset": "pv1", "type": "MATRIX",
                   "description": "Daily close price", "semantic_status": "KNOWN"}]
        ok, problems = validate_proposal(proposal, discovered_fields=fields,
                                         strict_experiment=True)
        self.assertTrue(ok, problems)

    def test_stopped_lineage_cannot_spend_more_budget(self):
        agent, client = make_agent(self._tmp, rounds=1)
        for score in (1.0, 0.9, 0.8):
            agent.memory.record_lineage_result("lineage-a", score, "FAIL", 1)
        self.assertEqual(agent.memory.lineage_decision("lineage-a"), "STOP")
        proposal = {
            "expression": "rank(returns)", "hypothesis": "return effect",
            "rationale": "last permitted variant already failed", "direction": "long",
            "expected_horizon": "63d", "falsification": "S<1",
            "fields": ["returns"], "datasets": ["pv1"],
            "field_understanding": {"returns": "daily return"},
            "field_analysis": {"returns": {"semantic": "daily return",
                "coverage": None, "frequency": None, "data_type": "MATRIX"}},
            "operator_mapping": "rank creates a cross-section",
            "experiment_question": "does a final window change help?",
            "expected_failure_modes": ["sharpe"], "tuning_risk": False,
            "experiment_stage": "CHILD", "change_type": "window_change",
            "parent_expression": "rank(ts_mean(returns, 20))",
            "changed_variable": "window: 20 -> raw", "lineage_id": "lineage-a",
        }
        path = os.path.join(self._tmp, "proposals.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"round_no": 1, "fields": [{"id": "returns", "dataset": "pv1",
                "type": "MATRIX", "description": "daily return", "semantic_status": "KNOWN"}],
                       "proposals": [proposal]}, f)
        self.assertIsNone(agent.run_proposals(path))
        self.assertEqual(client.sim_calls, [])


if __name__ == "__main__":
    unittest.main()
