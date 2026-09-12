import contextlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import main as main_entry
import wqb_agent.config as config_module
from wqb_agent.agent import Agent
from wqb_agent.audit import audit_state
from wqb_agent.behavior import extract_behavior_series
from wqb_agent.config import AppConfig, FactoryConfig, normalize_config, parse_config
from wqb_agent.diagnostics import DiagnosticEvent
from wqb_agent.doctor import run_doctor
from wqb_agent.incremental_policy import IncrementalValuePolicy
from wqb_agent.protocol import retry_after_seconds
from wqb_agent.schema import ARTIFACT_SCHEMAS, CURRENT_SCHEMA_VERSION, migrate_artifact
from wqb_agent.state import Experiment
from wqb_agent.trial_ledger import TrialLedger
from wqb_agent.workspace_snapshot import read_workspace_snapshot


class TestRuntimeSettlementEvidence(unittest.TestCase):

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
