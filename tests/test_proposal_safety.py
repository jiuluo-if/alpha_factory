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


class TmpStateMixin:
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="wqb_test_")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestAgentLoop(TmpStateMixin, unittest.TestCase):
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
