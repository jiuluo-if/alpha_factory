import json
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace

from wqb_agent.alpha_colors import (
    classify_alpha_color,
    has_research_signal,
    sync_alpha_colors,
)
from wqb_agent.client import WQBClient


def _experiment(*, quality="SUCCESS", self_result=True, self_value=0.2,
                classification="PROMISING", eligible=False,
                incremental=None, validation_status=None,
                validation_report=None, yearly=None, mechanism=True,
                status="DONE", error=None, skip_record=None):
    checks = [
        {"name": "LOW_SHARPE", "pass": True, "result": "PASS"},
        {"name": "LOW_FITNESS", "pass": True, "result": "PASS"},
        {"name": "SELF_CORRELATION", "pass": self_result,
         "result": self_result, "value": self_value},
    ]
    exp = SimpleNamespace(
        alpha_id="alpha-1",
        status=status,
        error=error,
        skip_record=skip_record,
        expression="rank(ts_delta(cashflow_op, 5))",
        metrics={
            "sharpe": 1.5, "fitness": 1.4, "turnover": 0.2,
            "returns": 0.08, "drawdown": 0.12, "margin": 0.03,
            "checks": checks,
        },
        health={"ok": True, "reasons": []},
        economic_mechanism=(
            "经营现金流改善代表盈利质量改善，检验未来收益增量。"
            if mechanism else None
        ),
        direction="long",
        falsification="若独立样本与健康证据不支持则停止。",
        research_classification=classification,
        search_outcome={"base_quality": quality},
        provisional_outcome={"base_quality": quality},
        final_outcome=None,
        submission_eligibility={"eligible": eligible, "reasons": []},
        validation_status=validation_status,
        validation_report=validation_report,
        yearly_evidence=yearly,
        incremental_evidence=incremental,
        self_correlation={
            "status": "PASS" if self_result is True else
            "FAIL" if self_result is False else "PENDING",
            "source": "BRAIN alpha payload",
            "check": {"name": "SELF_CORRELATION", "pass": self_result,
                      "result": self_result, "value": self_value},
        },
    )
    return exp


class FakeColorClient:
    def __init__(self, color=None):
        self.color = color
        self.get_calls = []
        self.patch_calls = []
        self.submit_calls = []

    def get_alpha(self, alpha_id):
        self.get_calls.append(alpha_id)
        return {"id": alpha_id, "color": self.color}

    def set_alpha_color(self, alpha_id, color, verify=True):
        self.patch_calls.append((alpha_id, color, verify))
        self.color = color
        return {"id": alpha_id, "color": color}

    def submit_alpha(self, *args, **kwargs):
        self.submit_calls.append((args, kwargs))
        raise AssertionError("颜色同步不得调用 Alpha submit")


class TestAlphaColorClassification(unittest.TestCase):
    def test_submit_ready_is_green(self):
        exp = _experiment(
            quality="STABLE", classification="STABLE", eligible=True,
            validation_status="STABLE",
            validation_report={"status": "PASS", "candidate": "parent"},
            yearly={"status": "VERIFIED", "stable": True},
        )
        self.assertTrue(has_research_signal(exp))
        self.assertEqual(classify_alpha_color(exp), "GREEN")

    def test_submit_ready_with_verified_incremental_value_is_purple(self):
        exp = _experiment(
            quality="STABLE", classification="PORTFOLIO_CANDIDATE", eligible=True,
            validation_status="STABLE",
            validation_report={"status": "PASS", "candidate": "parent"},
            yearly={"status": "VERIFIED", "stable": True},
            incremental={"decision": "PASS", "availability": "AVAILABLE",
                          "quality": "VERIFIED", "max_abs_corr": 0.18,
                          "nearest_alpha_id": "alpha-2", "cluster_id": None},
        )
        self.assertEqual(classify_alpha_color(exp), "PURPLE")

    def test_strong_signal_pending_is_blue(self):
        exp = _experiment(quality="SUCCESS", classification="PROMISING",
                          self_result=None, self_value=None)
        self.assertEqual(classify_alpha_color(exp), "BLUE")

    def test_promising_signal_is_yellow(self):
        exp = _experiment(quality="PROMISING", classification="PROMISING",
                          self_result=True, self_value=0.2)
        self.assertEqual(classify_alpha_color(exp), "YELLOW")

    def test_signal_with_self_correlation_fail_is_red(self):
        exp = _experiment(quality="SUCCESS", classification="SUCCESS",
                          self_result=False, self_value=0.76)
        self.assertEqual(classify_alpha_color(exp), "RED")

    def test_other_correlation_blocker_is_red(self):
        exp = _experiment(quality="SUCCESS", classification="SUCCESS",
                          self_result=True, self_value=0.2)
        exp.metrics["checks"].append({
            "name": "PROD_CORRELATION", "pass": False,
            "result": "FAIL", "value": 0.91,
        })
        self.assertEqual(classify_alpha_color(exp), "RED")

    def test_no_signal_has_no_color(self):
        self.assertIsNone(classify_alpha_color(
            _experiment(quality="FAILED", classification="REJECTED",
                        mechanism=False, self_result=True)
        ))

    def test_reconcile_label_overrides_stale_positive_label(self):
        exp = _experiment(quality="SUCCESS", classification="RECONCILE",
                          self_result=True)
        self.assertIsNone(classify_alpha_color(exp))

    def test_infrastructure_failure_has_no_color(self):
        self.assertIsNone(classify_alpha_color(
            _experiment(status="FAILED", error="WQBTimeoutError: timed out")
        ))

    def test_duplicate_has_no_color(self):
        self.assertIsNone(classify_alpha_color(
            _experiment(skip_record={"reason_code": "DUPLICATE_LOCAL"})
        ))

    def test_unknown_cannot_be_green_or_purple(self):
        exp = _experiment(quality="STABLE", classification="STABLE",
                          eligible=True, self_result=None, self_value=None,
                          validation_status="STABLE",
                          validation_report={"status": "PASS", "candidate": "parent"},
                          yearly={"status": "VERIFIED", "stable": True},
                          incremental={"decision": "PASS", "availability": "AVAILABLE",
                                        "quality": "VERIFIED", "max_abs_corr": 0.1})
        self.assertNotIn(classify_alpha_color(exp), {"GREEN", "PURPLE"})


class TestAlphaColorSync(unittest.TestCase):
    def test_same_color_is_idempotent(self):
        exp = _experiment(quality="PROMISING", self_result=True)
        client = FakeColorClient(color="YELLOW")
        with tempfile.TemporaryDirectory() as tmp:
            rows = sync_alpha_colors([exp], client, tmp, dry_run=False)
        self.assertEqual(client.patch_calls, [])
        self.assertEqual(rows[0]["old_color"], "YELLOW")
        self.assertEqual(rows[0]["new_color"], "YELLOW")

    def test_dry_run_never_patches(self):
        exp = _experiment(quality="PROMISING", self_result=True)
        client = FakeColorClient(color=None)
        with tempfile.TemporaryDirectory() as tmp:
            rows = sync_alpha_colors([exp], client, tmp, dry_run=True)
        self.assertEqual(client.patch_calls, [])
        self.assertEqual(rows[0]["new_color"], "YELLOW")
        self.assertFalse(os.path.exists(os.path.join(tmp, "alpha_color_evidence.json")))

    def test_existing_user_color_is_not_overwritten(self):
        exp = _experiment(quality="PROMISING", self_result=True)
        client = FakeColorClient(color="GREEN")
        with tempfile.TemporaryDirectory() as tmp:
            rows = sync_alpha_colors([exp], client, tmp, dry_run=False)
        self.assertEqual(client.patch_calls, [])
        self.assertEqual(rows[0]["action"], "OWNERSHIP_CONFLICT")

    def test_sync_never_calls_submit_endpoint(self):
        exp = _experiment(quality="PROMISING", self_result=True)
        client = FakeColorClient(color=None)
        with tempfile.TemporaryDirectory() as tmp:
            sync_alpha_colors([exp], client, tmp, dry_run=False)
        self.assertEqual(client.submit_calls, [])


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.headers = {}
        self.text = json.dumps(payload or {})
        self._payload = payload or {}

    def json(self):
        return self._payload


class RecordingSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class TestAlphaColorClient(unittest.TestCase):
    def test_metadata_patch_uses_request_and_verifies_without_submit(self):
        client = WQBClient.__new__(WQBClient)
        client._local = threading.local()
        client._local.authenticated = True
        client.base_url = "https://api.worldquantbrain.com"
        client.max_retries = 1
        client._rate_limit_until = 0.0
        client._rate_limit_lock = threading.Lock()
        client._local.session = RecordingSession([
            FakeResponse(200, {"id": "a1", "color": "RED"}),
            FakeResponse(200, {"id": "a1", "color": "RED"}),
        ])
        result = client.set_alpha_color("a1", "RED", verify=True)
        self.assertEqual(result["color"], "RED")
        session_calls = client._local.session.calls
        self.assertEqual([call[0] for call in session_calls], ["PATCH", "GET"])
        self.assertEqual(session_calls[0][2]["json"], {"color": "RED"})
        self.assertNotIn("/submit", session_calls[0][1])

    def test_client_rejects_unsupported_color(self):
        client = WQBClient.__new__(WQBClient)
        with self.assertRaises(ValueError):
            client.set_alpha_color("a1", "ORANGE")


if __name__ == "__main__":
    unittest.main()
