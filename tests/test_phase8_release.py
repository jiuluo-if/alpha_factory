import json
import os
import tempfile
import unittest

from wqb_agent.config import parse_config
from wqb_agent.schema import CURRENT_SCHEMA_VERSION, migrate_artifact
from wqb_agent.doctor import run_doctor
from wqb_agent.audit import audit_state
from wqb_agent.agent import Agent
from wqb_agent.incremental_policy import IncrementalValuePolicy
from wqb_agent.state import Experiment
from wqb_agent.diagnostics import DiagnosticEvent


class Phase8ReleaseTests(unittest.TestCase):
    def test_invalid_config_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_config({"simulation": {}, "agent": {"incremental_value": {"mode": "unknown"}}})

    def test_schema_migration_is_idempotent(self):
        legacy = {"schema_version": 1, "candidates": []}
        once = migrate_artifact("submission_pool", legacy)
        twice = migrate_artifact("submission_pool", once)
        self.assertEqual(once, twice)
        self.assertEqual(once["schema_version"], CURRENT_SCHEMA_VERSION)
        self.assertIn("created_by_version", once)

    def test_doctor_is_local_and_reports_capability_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_doctor({"simulation": {}, "agent": {"state_dir": tmp}}, offline=True)
            self.assertTrue(result["config_valid"])
            self.assertEqual(result["pnl_capability"], "UNAVAILABLE")
            self.assertEqual(result["incremental_capability"], "UNAVAILABLE")

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

    def test_agent_production_settlement_records_missing_pnl(self):
        agent = Agent.__new__(Agent)
        agent.trajectory = type("Trajectory", (), {"experiments": []})()
        agent.incremental_policy = IncrementalValuePolicy()
        exp = Experiment(1, "h", "rank(x)", {}, ["x"])
        exp.status = "DONE"
        evidence = agent._settle_incremental_evidence(exp)
        self.assertEqual(evidence["availability"], "UNAVAILABLE")
        self.assertEqual(exp.incremental_evidence["decision"], "INCONCLUSIVE")

    def test_diagnostic_event_is_structured_and_bounded(self):
        event = DiagnosticEvent("CONFIG_INVALID", "ERROR", "config", message="bad")
        self.assertEqual(event.as_dict()["severity"], "ERROR")
        with self.assertRaises(ValueError):
            DiagnosticEvent("X", "DEBUG", "config")
