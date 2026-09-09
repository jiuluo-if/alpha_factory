import json
import io
import os
import contextlib
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import wqb_agent.config as config_module
from wqb_agent.config import AppConfig, FactoryConfig, normalize_config, parse_config
from wqb_agent.schema import CURRENT_SCHEMA_VERSION, migrate_artifact, ARTIFACT_SCHEMAS
from wqb_agent.doctor import run_doctor
from wqb_agent.audit import audit_state
from wqb_agent.agent import Agent
from wqb_agent.incremental_policy import IncrementalValuePolicy
from wqb_agent.state import Experiment
from wqb_agent.diagnostics import DiagnosticEvent
from wqb_agent.trial_ledger import TrialLedger
from wqb_agent.behavior import extract_behavior_series
from wqb_agent.workspace_snapshot import read_workspace_snapshot
from wqb_agent.protocol import retry_after_seconds
import main as main_entry


class TestRuntimeSafety(unittest.TestCase):
    def test_normalize_config_is_the_only_raw_config_boundary(self):
        raw = {"simulation": {}, "agent": {"max_rounds": 3}}
        typed = normalize_config(raw)
        self.assertIsInstance(typed, AppConfig)
        self.assertIs(normalize_config(typed), typed)

    def test_main_state_dir_override_reports_config_error_before_agent_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "invalid.json")
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump({"simulation": {}}, handle)
            output = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "main.py", "--doctor", "--offline",
                    "--config", config_path, "--state-dir", tmp,
                ],
            ), redirect_stdout(output):
                with self.assertRaises(SystemExit) as raised:
                    main_entry.main()
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("config.agent", output.getvalue())

    def test_cli_state_dir_override_is_typed_and_does_not_mutate_original(self):
        typed = normalize_config({
            "simulation": {},
            "agent": {"state_dir": "original-state"},
        })
        apply_override = getattr(config_module, "apply_cli_overrides", None)
        self.assertIsNotNone(apply_override)
        overridden = apply_override(typed, state_dir="override-state")
        self.assertIsInstance(overridden, AppConfig)
        self.assertEqual(overridden.runtime.state_dir, "override-state")
        self.assertEqual(typed.runtime.state_dir, "original-state")
        self.assertEqual(typed.agent["state_dir"], "original-state")

    def test_runtime_scalar_max_concurrent_sims_must_be_positive(self):
        with self.assertRaisesRegex(
            ValueError, "config.agent.max_concurrent_sims"
        ):
            parse_config({
                "simulation": {},
                "agent": {"max_concurrent_sims": 0},
            })

    def test_runtime_scalar_poll_timeout_rejects_negative_values(self):
        with self.assertRaisesRegex(
            ValueError, "config.agent.poll_timeout_sec"
        ):
            parse_config({
                "simulation": {},
                "agent": {"poll_timeout_sec": -1},
            })

    def test_runtime_scalar_poll_timeout_rejects_nan(self):
        with self.assertRaisesRegex(
            ValueError, "config.agent.poll_timeout_sec"
        ):
            parse_config({
                "simulation": {},
                "agent": {"poll_timeout_sec": float("nan")},
            })

    def test_max_proposals_per_round_rejects_values_above_hard_limit(self):
        with self.assertRaisesRegex(
            ValueError, "config.agent.max_proposals_per_round"
        ):
            parse_config({
                "simulation": {},
                "agent": {"max_proposals_per_round": 101},
            })

    def test_config_example_remains_valid_with_factory_quotas(self):
        with open("config.example.json", encoding="utf-8") as handle:
            config = normalize_config(json.load(handle))
        self.assertEqual(config.factory.daily_simulation_cap, 1600)
        self.assertEqual(config.factory.weekly_simulation_cap, 11200)
        self.assertEqual(config.runtime.max_proposals_per_round, 100)

    def test_default_typed_config_is_runtime_ready(self):
        typed = normalize_config(AppConfig())
        self.assertEqual(typed.simulation_config.settings["neutralization"], "SUBINDUSTRY")
        self.assertEqual(typed.runtime.memory["max_lineages"], 256)
        self.assertEqual(typed.runtime.field_selection["mode"], "semantic_random")
        self.assertEqual(typed.runtime.search_policy["max_pending_per_arm"], 1)
        self.assertEqual(typed.runtime.quality["promising_sharpe"], 0.9)
        self.assertEqual(typed.runtime.yearly_policy["min_years"], 2)

    def test_config_boolean_strings_are_strict_and_fail_closed(self):
        config = parse_config({
            "simulation": {},
            "agent": {
                "research_integrity": "false",
                "search_policy": {"enabled": "false"},
            },
        })
        self.assertFalse(config.runtime.research_integrity)
        self.assertFalse(config.search.enabled)
        with self.assertRaises(ValueError):
            parse_config({
                "simulation": {},
                "agent": {"research_integrity": "maybe"},
            })

    def test_parse_config_keeps_typed_factory_and_nested_runtime_models(self):
        config = parse_config({"simulation": {}, "agent": {
            "factory": {"max_simulations": 12, "max_runtime_sec": 99},
            "search_policy": {"max_simulations": 12},
            "max_rounds": 8,
        }})
        self.assertIsInstance(config, AppConfig)
        self.assertIsInstance(config.factory, FactoryConfig)
        self.assertEqual(config.factory.max_simulations, 12)
        self.assertEqual(config.factory.max_runtime_sec, 99)
        self.assertEqual(config.factory.daily_simulation_cap, 12)
        self.assertEqual(config.factory.weekly_simulation_cap, 12)
        self.assertEqual(config.runtime.max_rounds, 8)

    def test_factory_weekly_and_daily_caps_are_typed_and_validated(self):
        config = parse_config({"simulation": {}, "agent": {
            "factory": {
                "max_simulations": 300,
                "daily_simulation_cap": 1600,
                "weekly_simulation_cap": 11200,
            },
            "search_policy": {"max_simulations": 100},
        }})
        self.assertEqual(config.factory.max_simulations, 11200)
        self.assertEqual(config.factory.daily_simulation_cap, 1600)
        self.assertEqual(config.factory.weekly_simulation_cap, 11200)
        self.assertEqual(config.runtime.factory["max_simulations"], 300)
        with self.assertRaises(ValueError):
            parse_config({"simulation": {}, "agent": {
                "factory": {
                    "daily_simulation_cap": 1601,
                    "weekly_simulation_cap": 1600,
                },
            }})

    def test_agent_typed_config_does_not_round_trip_through_legacy_dict(self):
        typed = parse_config({"simulation": {"neutralization": "SUBINDUSTRY"}, "agent": {}})
        agent = Agent(object(), typed)
        self.assertEqual(agent.simulation_settings["neutralization"], "SUBINDUSTRY")

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

    def test_agent_runtime_values_are_typed_once_and_consumed_by_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = {
                "simulation": {"neutralization": "SUBINDUSTRY"},
                "agent": {
                    "state_dir": tmp,
                    "max_rounds": 7,
                    "candidates_per_round": 11,
                    "max_concurrent_sims": 2,
                    "poll_timeout_sec": 123,
                    "trajectory_window": 17,
                    "fields_cache_ttl_sec": 456,
                },
            }
            typed = parse_config(raw)
            self.assertEqual(typed.runtime.state_dir, tmp)
            self.assertEqual(typed.runtime.max_rounds, 7)
            self.assertEqual(typed.runtime.poll_timeout_sec, 123)
            agent = Agent(object(), typed)
            self.assertEqual(agent.state_dir, tmp)
            self.assertEqual(agent.max_rounds, 7)
            self.assertEqual(agent.candidates_per_round, 11)
            self.assertEqual(agent.simulator.poll_timeout_sec, 123)
            self.assertEqual(agent.trajectory.max_len, 17)

    def test_runtime_component_defaults_are_resolved_at_config_boundary(self):
        config = normalize_config({"simulation": {}, "agent": {}})
        runtime = config.runtime
        self.assertEqual(config.simulation_config.settings["neutralization"], "SUBINDUSTRY")
        self.assertEqual(
            {key: runtime.memory[key] for key in (
                "max_lessons", "max_avoid", "max_next", "max_hypotheses",
                "max_short_term", "short_term_window", "promote_hits",
                "max_garbage", "garbage_max_age_rounds", "next_max_age_rounds",
                "max_lineages", "max_seen_expressions", "max_used_hypotheses",
            )},
            {
                "max_lessons": 20, "max_avoid": 30, "max_next": 15,
                "max_hypotheses": 12, "max_short_term": 30,
                "short_term_window": 5, "promote_hits": 2,
                "max_garbage": 200, "garbage_max_age_rounds": 60,
                "next_max_age_rounds": 20, "max_lineages": 256,
                "max_seen_expressions": 4096, "max_used_hypotheses": 256,
            },
        )
        self.assertEqual(
            {key: runtime.field_selection[key] for key in (
                "mode", "random_fraction", "random_seed",
            )},
            {"mode": "semantic_random", "random_fraction": 0.35, "random_seed": "newwqb"},
        )
        self.assertEqual(runtime.search_policy["max_pending_per_arm"], 1)
        self.assertEqual(runtime.search_policy["ucb_exploration"], 1.0)
        self.assertEqual(runtime.quality["promising_sharpe"], 0.9)
        self.assertEqual(runtime.quality["promising_fitness"], 0.6)
        self.assertEqual(runtime.yearly_policy["min_years"], 2)

    def test_snapshot_exposes_ledger_lifecycle_evidence_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"proposal_id": "p1", "phase": "simulation_committed"}) + "\n")
                handle.write(json.dumps({"proposal_id": "p1", "phase": "simulation_submitted"}) + "\n")
                handle.write(json.dumps({"proposal_id": "p1", "phase": "simulation_settled"}) + "\n")
            snapshot = read_workspace_snapshot(tmp)
        self.assertIn("p1", snapshot.ledger.committed)
        self.assertIn("p1", snapshot.ledger.submitted)
        self.assertIn("p1", snapshot.ledger.simulation_settled)

    def test_audit_reports_trajectory_lifecycle_without_ledger_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trajectory.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "proposal_id": "p", "phase": "simulation_committed",
                }) + "\n")
            result = audit_state(tmp)
        self.assertFalse(result["ok"])
        self.assertIn("trajectory_lifecycle_missing_ledger", result["errors"])
        self.assertNotIn("ledger_lifecycle_missing_trajectory", result["errors"])
        self.assertEqual(result["committed"], 0)
        self.assertEqual(result["trajectory_observed_committed"], 1)

    def test_audit_reports_ledger_lifecycle_without_trajectory_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "proposal_id": "p", "phase": "simulation_committed",
                }) + "\n")
            result = audit_state(tmp)
        self.assertFalse(result["ok"])
        self.assertIn("ledger_lifecycle_missing_trajectory", result["errors"])
        self.assertNotIn("trajectory_lifecycle_missing_ledger", result["errors"])
        self.assertEqual(result["committed"], 1)
        self.assertEqual(result["trajectory_observed_committed"], 0)

    def test_audit_findings_identify_lifecycle_phase_source_and_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trajectory.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "proposal_id": "p", "phase": "simulation_submitted",
                }) + "\n")
            result = audit_state(tmp)
        finding = next(item for item in result["findings"]
                       if item["code"] == "trajectory_lifecycle_missing_ledger")
        self.assertTrue(result["blocking"])
        self.assertEqual(finding["source"], "trajectory→trial_ledger")
        self.assertEqual(finding["phase"], "simulation_submitted")
        self.assertEqual(finding["proposal_ids"], ["p"])

    def test_audit_compares_ledger_phase_to_same_trajectory_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trajectory.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"id": "trial-1", "proposal_id": "p"}) + "\n")
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                for phase in ("simulation_committed", "simulation_submitted"):
                    handle.write(json.dumps({"proposal_id": "p", "phase": phase}) + "\n")
            result = audit_state(tmp)
        findings = [item for item in result["findings"]
                    if item["code"] == "ledger_lifecycle_missing_trajectory"]
        self.assertEqual(
            [(item["phase"], item["proposal_ids"]) for item in findings],
            [("simulation_committed", ["p"]), ("simulation_submitted", ["p"])],
        )

    def test_audit_requires_exact_phase_continuity(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "proposal_id": "p", "phase": "simulation_settled",
                }) + "\n")
            result = audit_state(tmp)
        self.assertIn("lifecycle_order", result["errors"])

    def test_audit_findings_have_one_canonical_order_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "proposal_id": "p", "phase": "simulation_submitted",
                }) + "\n")
            result = audit_state(tmp)
        codes = [item["code"] for item in result["findings"]]
        self.assertEqual(codes.count("ledger_lifecycle_order"), 1)
        self.assertNotIn("lifecycle_order", codes)

    def test_audit_findings_sort_proposal_ids_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "validation_reports.jsonl"), "w", encoding="utf-8") as handle:
                for proposal_id in ("p2", "p1"):
                    handle.write(json.dumps({"parent_id": proposal_id}) + "\n")
            result = audit_state(tmp)
        findings = [item for item in result["findings"]
                    if item["code"] == "orphan_validation_parent"]
        self.assertEqual([item["proposal_ids"] for item in findings], [["p1"], ["p2"]])

    def test_audit_and_doctor_surface_malformed_jsonl_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                handle.write("not json\n")
            result = audit_state(tmp)
            doctor = run_doctor({"simulation": {}, "agent": {"state_dir": tmp}}, offline=True)
        self.assertIn("malformed_ledger_evidence", result["errors"])
        self.assertTrue(any(
            item["code"] == "LEDGER_EVIDENCE_DEGRADED"
            for item in doctor["diagnostics"]
        ))

    def test_malformed_validation_is_degraded_warning_not_lifecycle_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "validation_reports.jsonl"), "w", encoding="utf-8") as handle:
                handle.write("not json\n")
            result = audit_state(tmp)
        self.assertTrue(result["ok"])
        self.assertNotIn("malformed_validation_evidence", result["errors"])
        finding = next(item for item in result["findings"]
                       if item["code"] == "malformed_validation_evidence")
        self.assertEqual(finding["severity"], "WARN")
        self.assertIn("malformed_validation_evidence", result["warnings"])

    def test_unknown_ledger_schema_is_distinguished_from_unknown_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "schema_version": 99,
                    "proposal_id": "p",
                    "phase": "future_phase",
                }) + "\n")
            result = audit_state(tmp)
        self.assertIn("unsupported_schema", result["errors"])
        self.assertIn("unknown_ledger_phase", result["errors"])
        finding = next(item for item in result["findings"]
                       if item["code"] == "unsupported_schema")
        self.assertEqual(finding["source"], "trial_ledger")
        self.assertEqual(finding["rows"], 1)

    def test_known_result_records_ledger_before_trajectory(self):
        """已知结果必须先写生命周期证据，再落 append-only trajectory。"""
        events = []
        agent = Agent.__new__(Agent)
        agent.trajectory = SimpleNamespace(
            experiments=[],
            add=lambda experiment: events.append("trajectory"),
        )
        agent.reflector = SimpleNamespace(
            _classify=lambda experiment: {"label": "BASELINE", "reason": "test"},
        )
        agent.quality_policy = {}
        agent._record_trial_phase = lambda experiment, phase, **kwargs: events.append(
            f"ledger:{phase}"
        )
        agent._update_search_lifecycle = lambda experiment, outcome=None: None
        agent._print_experiment = lambda experiment: None
        exp = Experiment(1, "h", "rank(field)", {}, [])
        exp.status = "DONE"
        exp.metrics = {"checks": []}
        exp.health = None
        exp.error = None
        agent._record_live_result(exp)
        self.assertLess(
            events.index("ledger:simulation_settled"),
            events.index("trajectory"),
        )

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
            "self_correlation.json", "retry_after.json",
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
        with open(os.path.join(fixture_dir, "retry_after.json"), encoding="utf-8") as handle:
            retry_payload = json.load(handle)
        self.assertEqual(retry_after_seconds(retry_payload["headers"]), 2.0)

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

    def test_audit_does_not_match_alpha_id_to_proposal_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trajectory.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"id": "trial-1", "proposal_id": "p1"}) + "\n")
            with open(os.path.join(tmp, "submission_pool.json"), "w", encoding="utf-8") as handle:
                json.dump({"candidates": [{"alpha_id": "p1"}]}, handle)
            result = audit_state(tmp)
        self.assertFalse(result["ok"])
        self.assertIn("orphan_submission", result["errors"])

    def test_trial_ledger_summary_separates_exact_and_cumulative_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                for phase in ("simulation_submitted", "simulation_settled"):
                    handle.write(json.dumps({"proposal_id": "p", "phase": phase}) + "\n")
            snapshot = read_workspace_snapshot(tmp)
        self.assertEqual(snapshot.ledger.simulation_submitted, frozenset({"p"}))
        self.assertEqual(snapshot.ledger.submitted, frozenset({"p"}))

    def test_valid_non_simulation_ledger_phases_are_not_lifecycle_degraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                for phase in (
                    "candidate_generated", "candidate_rejected",
                    "preflight_accepted", "candidate_admitted",
                ):
                    handle.write(json.dumps({"candidate_id": "c", "phase": phase}) + "\n")
            snapshot = read_workspace_snapshot(tmp)
        self.assertEqual(snapshot.ledger.unknown_phase_rows, 0)
        self.assertEqual(snapshot.ledger.incomplete_rows, 0)

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

    def test_audit_accepts_same_settlement_in_ledger_and_trajectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "trajectory.jsonl"), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "proposal_id": "p", "phase": "simulation_committed",
                }) + "\n")
                handle.write(json.dumps({
                    "proposal_id": "p", "phase": "simulation_submitted",
                }) + "\n")
                handle.write(json.dumps({
                    "proposal_id": "p", "phase": "simulation_settled",
                }) + "\n")
                handle.write(json.dumps({
                    "proposal_id": "p", "phase": "research_outcome_settled",
                    "settlement": {"settlement_id": "same"},
                }) + "\n")
            with open(os.path.join(tmp, "trial_ledger.jsonl"), "w", encoding="utf-8") as handle:
                for phase in ("simulation_committed", "simulation_submitted", "simulation_settled"):
                    handle.write(json.dumps({"proposal_id": "p", "phase": phase}) + "\n")
                handle.write(json.dumps({
                    "proposal_id": "p", "phase": "research_outcome_settled",
                    "settlement": {"settlement_id": "same"},
                }) + "\n")
            result = audit_state(tmp)
        self.assertTrue(result["ok"], result["errors"])

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
                json.dump({"schema_version": 1, "round_no": 1,
                           "hypothesis": {}, "complete": True, "experiments": [{
                    "id": "e1", "round": 1, "hypothesis_id": "h",
                    "expression": "rank(low)", "settings": {},
                    "fields_used": ["low"], "status": "DONE", "proposal_id": "p"
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

    def test_audit_allows_ephemeral_lifecycle_without_local_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "round_1.checkpoint.json"), "w", encoding="utf-8") as handle:
                json.dump({"schema_version": 1, "round_no": 1,
                           "hypothesis": {}, "complete": True, "experiments": [{
                    "id": "e1", "round": 1, "hypothesis_id": "h",
                    "expression": "rank(low)", "settings": {},
                    "fields_used": ["low"], "status": "DONE", "proposal_id": "p"
                }]}, handle)
            result = audit_state(tmp, lifecycle_persistent=False)
            self.assertTrue(result["ok"])
            self.assertNotIn("ledger_missing", result["errors"])
            self.assertNotIn("checkpoint_ledger_mismatch", result["errors"])

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
