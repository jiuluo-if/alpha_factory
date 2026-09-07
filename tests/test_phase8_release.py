import json
import io
import os
import contextlib
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from wqb_agent.config import parse_config
from wqb_agent.schema import CURRENT_SCHEMA_VERSION, migrate_artifact, ARTIFACT_SCHEMAS
from wqb_agent.doctor import run_doctor
from wqb_agent.audit import audit_state
from wqb_agent.agent import Agent
from wqb_agent.incremental_policy import IncrementalValuePolicy
from wqb_agent.state import Experiment
from wqb_agent.diagnostics import DiagnosticEvent
from wqb_agent.trial_ledger import TrialLedger
from wqb_agent.behavior import extract_behavior_series
import main as main_entry


class Phase8ReleaseTests(unittest.TestCase):
    def test_invalid_config_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_config({"simulation": {}, "agent": {"incremental_value": {"mode": "unknown"}}})

    def test_discovery_plus_validation_budget_cannot_exceed_factory_cap(self):
        with self.assertRaises(ValueError):
            parse_config({"simulation": {}, "agent": {
                "factory": {"max_simulations": 5},
                "search_policy": {"max_simulations": 4, "validation_max_simulations": 2},
            }})

    def test_research_allocation_is_typed(self):
        config = parse_config({"simulation": {}, "agent": {
            "research_allocation": {
                "max_simulations": 8,
                "maximum": {"EXPLOIT": 2, "VALIDATION": 3},
            },
            "search_policy": {"max_simulations": 8},
            "factory": {"max_simulations": 10},
        }})
        self.assertEqual(config.research_allocation.max_simulations, 8)
        self.assertEqual(config.research_allocation.maximum["VALIDATION"], 3)

    def test_schema_migration_is_idempotent(self):
        legacy = {"schema_version": 1, "candidates": []}
        once = migrate_artifact("submission_pool", legacy)
        twice = migrate_artifact("submission_pool", once)
        self.assertEqual(once, twice)
        self.assertEqual(once["schema_version"], CURRENT_SCHEMA_VERSION)
        self.assertIn("created_by_version", once)

    def test_registry_covers_persistent_artifacts(self):
        for name in ("trajectory", "trial_ledger", "checkpoint", "validation",
                     "submission_pool", "fields_cache", "evidence_cache", "active_snapshot",
                     "simulation_results", "memory", "search_snapshot", "validation_plan"):
            self.assertIn(name, ARTIFACT_SCHEMAS)

    def test_platform_fixtures_are_small_anonymous_and_not_live_capability(self):
        fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures", "brain")
        expected = {
            "authentication.json", "simulation_progress.json", "alpha.json",
            "aggregates.json", "alpha_check.json", "pnl.json",
            "data_fields.json", "data_sets.json", "operators.json",
            "self_correlation.json",
        }
        actual = {name for name in os.listdir(fixture_dir) if name.endswith(".json")}
        self.assertEqual(actual, expected)
        forbidden_keys = {"password", "secret", "authorization", "cookie"}

        def walk(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    self.assertNotIn(str(key).lower(), forbidden_keys)
                    yield from walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    yield from walk(nested)

        for name in sorted(expected):
            with open(os.path.join(fixture_dir, name), encoding="utf-8") as handle:
                payload = json.load(handle)
            list(walk(payload))
        with open(os.path.join(fixture_dir, "pnl.json"), encoding="utf-8") as handle:
            pnl_payload = json.load(handle)
        self.assertEqual(
            extract_behavior_series({"pnl": pnl_payload["pnl"]})["availability"],
            "UNAVAILABLE",
        )

    def test_legacy_v2_and_current_migrations_are_idempotent(self):
        for payload in ({"schema_version": 2}, {"schema_version": CURRENT_SCHEMA_VERSION,
                                                  "created_by_version": "alpha-factory"}):
            migrated = migrate_artifact("checkpoint", payload)
            self.assertEqual(migrated, migrate_artifact("checkpoint", migrated))

    def test_doctor_is_local_and_reports_capability_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_doctor({"simulation": {}, "agent": {"state_dir": tmp}}, offline=True)
            self.assertTrue(result["config_valid"])
            self.assertFalse(result["ledger_readable"])
            self.assertEqual(result["ledger_status"], "MISSING")
            self.assertEqual(result["pnl_capability"], "UNAVAILABLE")
            self.assertEqual(result["incremental_capability"], "UNAVAILABLE")

    def test_doctor_and_audit_are_network_free(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "requests.Session", side_effect=AssertionError("网络调用不应发生")
        ):
            result = run_doctor({"simulation": {}, "agent": {"state_dir": tmp}}, offline=True)
            self.assertTrue(result["config_valid"])
            self.assertTrue(audit_state(tmp)["ok"])

    def test_doctor_uses_example_config_on_fresh_checkout(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "sys.argv", ["main.py", "--doctor", "--offline",
                          "--config", os.path.join(tmp, "missing.json"),
                          "--state-dir", tmp]
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                main_entry.main()
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["config_valid"])
            self.assertEqual(payload["state_dir"], tmp)

    def test_offline_flag_cannot_enter_production_path(self):
        with patch("sys.argv", ["main.py", "--offline", "--run-proposals"]), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main_entry.main()
        self.assertEqual(raised.exception.code, 2)

    def test_audit_detects_orphan_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "submission_pool.json"), "w", encoding="utf-8") as handle:
                json.dump({"candidates": [{"alpha_id": "orphan"}]}, handle)
            result = audit_state(tmp)
            self.assertFalse(result["ok"])
            self.assertIn("orphan_submission", result["errors"])

    def test_audit_detects_duplicate_settlement_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                row = {"phase": "research_outcome_settled", "proposal_id": "p",
                       "settlement": {"settlement_id": "same"}}
                handle.write(json.dumps(row) + "\n")
                handle.write(json.dumps(row) + "\n")
            result = audit_state(tmp)
            self.assertFalse(result["ok"])
            self.assertIn("duplicate_settlement", result["errors"])

    def test_audit_detects_phantom_checkpoint_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "round_1.checkpoint.json"), "w", encoding="utf-8") as handle:
                json.dump({"complete": False, "experiments": [{"status": "PENDING"}]}, handle)
            result = audit_state(tmp)
            self.assertFalse(result["ok"])
            self.assertIn("phantom_reservation", result["errors"])

    def test_audit_detects_invalid_lifecycle_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"phase": "simulation_submitted", "proposal_id": "p"}) + "\n")
            result = audit_state(tmp)
            self.assertFalse(result["ok"])
            self.assertIn("lifecycle_order", result["errors"])

    def test_audit_detects_checkpoint_ledger_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "round_1.checkpoint.json"), "w", encoding="utf-8") as handle:
                json.dump({"complete": True, "experiments": [{
                    "status": "DONE", "proposal_id": "p"
                }]}, handle)
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "phase": "simulation_committed", "proposal_id": "p"
                }) + "\n")
            result = audit_state(tmp)
            self.assertFalse(result["ok"])
            self.assertIn("checkpoint_ledger_mismatch", result["errors"])

    def test_audit_reports_missing_ledger_for_terminal_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "round_1.checkpoint.json"), "w", encoding="utf-8") as handle:
                json.dump({"complete": True, "experiments": [{
                    "status": "DONE", "proposal_id": "p"
                }]}, handle)
            result = audit_state(tmp)
            self.assertFalse(result["ok"])
            self.assertIn("ledger_missing", result["errors"])
            self.assertIn("checkpoint_ledger_mismatch", result["errors"])

    def test_audit_detects_orphan_validation_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "validation_reports.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"parent_id": "missing", "plan_id": "p",
                                         "report": {"plan_id": "p"}}) + "\n")
            result = audit_state(tmp)
            self.assertFalse(result["ok"])
            self.assertIn("orphan_validation_parent", result["errors"])

    def test_audit_detects_unknown_job_released_from_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "round_1.checkpoint.json"), "w", encoding="utf-8") as handle:
                json.dump({"complete": False, "experiments": [{
                    "status": "SUBMIT_UNKNOWN", "proposal_id": "p", "budget_held": False
                }]}, handle)
            result = audit_state(tmp)
            self.assertFalse(result["ok"])
            self.assertIn("unknown_not_budget_held", result["errors"])

    def test_audit_detects_terminal_reserved_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "round_1.checkpoint.json"), "w", encoding="utf-8") as handle:
                json.dump({"complete": True, "experiments": [{
                    "status": "DONE", "proposal_id": "p", "reserved": True
                }]}, handle)
            result = audit_state(tmp)
            self.assertFalse(result["ok"])
            self.assertIn("terminal_occupies_arm", result["errors"])

    def test_agent_production_settlement_records_missing_pnl(self):
        agent = Agent.__new__(Agent)
        agent.trajectory = type("Trajectory", (), {"experiments": []})()
        agent.incremental_policy = IncrementalValuePolicy()
        exp = Experiment(1, "h", "rank(x)", {}, ["x"])
        exp.status = "DONE"
        evidence = agent._settle_incremental_evidence(exp)
        self.assertEqual(evidence["availability"], "UNAVAILABLE")
        self.assertEqual(exp.incremental_evidence["decision"], "INCONCLUSIVE")

    def test_final_settlement_persists_research_evidence_bundle(self):
        from wqb_agent.agent import Agent
        agent = Agent.__new__(Agent)
        agent.trajectory = type("Trajectory", (), {"experiments": []})()
        agent.incremental_policy = IncrementalValuePolicy()
        exp = Experiment(1, "h", "rank(x)", {}, ["x"])
        exp.status = "DONE"
        exp.provisional_outcome = {
            "proposal_id": "p", "evaluated": True, "base_quality": "PROMISING",
            "reward": 0.5,
        }
        exp.validation_report = {"status": "FAIL", "statistical_evidence": {}}
        # Build the production evidence stage directly; no client or POST is involved.
        incremental = agent._settle_incremental_evidence(exp)
        self.assertEqual(incremental["decision"], "INCONCLUSIVE")

    def test_diagnostic_event_is_structured_and_bounded(self):
        event = DiagnosticEvent("CONFIG_INVALID", "ERROR", "config", message="bad")
        self.assertEqual(event.as_dict()["severity"], "ERROR")
        with self.assertRaises(ValueError):
            DiagnosticEvent("X", "DEBUG", "config")

    def test_trial_ledger_summary_cache_is_rebuildable(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = os.path.join(tmp, "trial_ledger.jsonl")
            cache_path = os.path.join(tmp, "trial_ledger.summary.json")
            ledger = TrialLedger(ledger_path)
            first = ledger.summarize_cached(cache_path)
            second = ledger.summarize_cached(cache_path)
            self.assertEqual(first, second)
            self.assertTrue(os.path.exists(cache_path))
