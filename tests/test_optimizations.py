"""Tests for failures / diversity / validation / metrics tri-state.

Covers the optimizations absorbed from the remote Self-Evolution-wqb
reference implementation:
- failures.classify_error / is_research_relevant (system failures must not
  pollute research memory)
- diversity.extract_fields (precise field extraction, no prefix false
  positives), is_redundant, deduplicate
- _extract_metrics tri-state passed (empty checks != PASS)
- HighSignalValidator decide() logic (no network)
"""

import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
from collections import defaultdict
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wqb_agent.diversity import (
    deduplicate,
    extract_fields,
    field_similarity,
    is_redundant,
)
from wqb_agent.failures import (
    FailureKind,
    classify_error,
    is_research_relevant,
)
from wqb_agent.memory import ExperienceMemory
from wqb_agent.agent import (
    Agent,
    MAX_PROPOSALS_PER_ROUND,
    proposal_budget_cap,
    proposal_priority,
    validate_proposal,
    validate_vector_inputs,
)
from wqb_agent.alpha_factory import AlphaFactory
from wqb_agent.artifacts import (
    atomic_write_json_if_changed,
    atomic_write_jsonl_if_changed,
    append_jsonl_if_unique,
    iter_jsonl_objects,
)
from wqb_agent.expression import canonical_expression, submission_fingerprint
from wqb_agent.factory_runner import AIFactoryRunner
from wqb_agent.locking import acquire_os_owner_lock, release_os_owner_lock
from wqb_agent.metrics import checks_passed, num, score_of
from wqb_agent.research_guard import ResearchLoopGuard
from wqb_agent.state import Experiment, Trajectory
from wqb_agent.simulator import _check_pass, _extract_metrics
from wqb_agent.validation import HighSignalValidator
from wqb_agent.reflection import Reflector

from scripts.reconcile_pending import append_unique_history, collect
from scripts.maintain_memory import compact_only
from scripts import generate_report
from scripts.generate_report import (
    _load_json_object,
    _safe_text,
    iter_trajectory,
    state_snapshot_time,
)
from scripts.curate_data import (
    build_lineages,
    detect_duplicates,
    normalize_simulation,
    normalize_round,
    iter_trajectory,
    run_integrity_checks,
    write_jsonl_if_changed,
)
from scripts.validate_integrity import duplicate_groups, iter_jsonl, load_jsonl, round_key
from scripts.validate_integrity import _prefix
from scripts.archive_completed_rounds import ensure_archive_dir_safe
from scripts.generate_complete_report import (
    heuristic_sim_status,
    heuristic_status,
    source_snapshot_time as complete_report_snapshot,
    summarize_simulations as summarize_complete_simulations,
)
from scripts.generate_final_report import (
    _metric_text as final_metric_text,
    source_snapshot_time as final_report_snapshot,
    summarize_simulations,
)
from scripts.generate_ledger import _aggregate
from scripts.enhance_simulations import check_health as enhance_check_health, enhance_rows
from scripts.refactor_memory import build_evidence
from scripts.analyze_bulk import pass_correlation_ids
from scripts.validate_high_signal import apply_validation_rows
from scripts.validate_high_signal import (
    MAX_VALIDATION_REPORT_RESULTS,
    _retain_validation_result,
    _metric_text,
    _short_text,
    generate_perturbations,
    heuristic_validate,
)
from scripts.query_ledger import iter_simulations, query_by_round, query_top_performers
from scripts.enhance_schema import enhanced_rows
from scripts.execute_validation import build_jobs
from scripts.check_correlation import configured_threshold, numeric_correlations, parse_records
from scripts.refresh_evidence import fetch_settled, pending_check_names
from scripts import audit_high_signal


class TestFailureClassification(unittest.TestCase):
    def test_status_code_mapping(self):
        self.assertEqual(classify_error("", 401), FailureKind.AUTH)
        self.assertEqual(classify_error("", 429), FailureKind.RATE_LIMIT)
        self.assertEqual(classify_error("", 422), FailureKind.SYNTAX)
        self.assertEqual(classify_error("", 404), FailureKind.DATA)
        self.assertEqual(classify_error("", 500), FailureKind.INFRA)

    def test_text_mapping(self):
        self.assertEqual(classify_error("timed out after 900s"), FailureKind.TIMEOUT)
        self.assertEqual(classify_error("Simulation rejected (422): bad expr"),
                         FailureKind.SYNTAX)
        self.assertEqual(classify_error("field not found"), FailureKind.DATA)
        self.assertEqual(classify_error("connection refused"), FailureKind.INFRA)
        self.assertEqual(classify_error("authentication failed"), FailureKind.AUTH)
        self.assertEqual(classify_error("rate limit exceeded"), FailureKind.RATE_LIMIT)

    def test_default_research(self):
        self.assertEqual(classify_error("random research error"), FailureKind.RESEARCH)

    def test_malformed_error_shape_does_not_break_classification(self):
        self.assertEqual(classify_error({"message": "connection refused"}), FailureKind.INFRA)

    def test_research_relevant_subset(self):
        self.assertTrue(is_research_relevant(FailureKind.RESEARCH))
        self.assertTrue(is_research_relevant(FailureKind.SYNTAX))
        self.assertTrue(is_research_relevant(FailureKind.DATA))
        self.assertFalse(is_research_relevant(FailureKind.AUTH))
        self.assertFalse(is_research_relevant(FailureKind.RATE_LIMIT))
        self.assertFalse(is_research_relevant(FailureKind.TIMEOUT))
        self.assertFalse(is_research_relevant(FailureKind.INFRA))


class TestExtractFields(unittest.TestCase):
    def test_no_prefix_false_positive(self):
        # returns_5d must not be matched by a search for returns
        known = ["returns", "returns_5d", "close"]
        found = extract_fields("rank(returns_5d) + close", known)
        self.assertIn("returns_5d", found)
        self.assertIn("close", found)
        self.assertNotIn("returns", found)

    def test_longest_id_preferred(self):
        known = ["anl4_adjusted_netincome_ft", "anl4_adjusted_netincome"]
        found = extract_fields("rank(anl4_adjusted_netincome_ft)", known)
        self.assertIn("anl4_adjusted_netincome_ft", found)
        self.assertNotIn("anl4_adjusted_netincome", found)

    def test_empty_expression(self):
        self.assertEqual(extract_fields("", ["returns"]), [])
        self.assertEqual(extract_fields(None, ["returns"]), [])

    def test_repeated_field_bundle_uses_cached_matching_helpers(self):
        from wqb_agent import diversity

        diversity._field_boundary_pattern.cache_clear()
        diversity._sorted_field_ids.cache_clear()
        known = ("returns", "returns_5d", "close")
        extract_fields("rank(returns_5d) + close", known)
        extract_fields("rank(returns_5d) + close", known)
        self.assertEqual(diversity._sorted_field_ids.cache_info().hits, 1)
        self.assertEqual(
            diversity._field_boundary_pattern.cache_info().hits,
            3,
        )


class TestMemoryTokenization(unittest.TestCase):
    def test_repeated_similarity_reuses_token_cache(self):
        ExperienceMemory._tokens.cache_clear()
        ExperienceMemory._similar("daily return quality", "return quality")
        before = ExperienceMemory._tokens.cache_info().hits
        ExperienceMemory._similar("daily return quality", "return quality")
        self.assertGreaterEqual(ExperienceMemory._tokens.cache_info().hits, before + 2)

    def test_expression_identity_is_shared_and_whitespace_insensitive(self):
        self.assertEqual(canonical_expression(" Rank( Signal ) "), "rank(signal)")
        self.assertEqual(
            submission_fingerprint("rank(signal)", {"decay": 4}),
            submission_fingerprint(" RANK( signal ) ", {"decay": 4}),
        )

    def test_memory_dedupe_uses_canonical_expression_identity(self):
        memory = ExperienceMemory()
        memory.remember_expression(" Rank( Signal ) ")
        self.assertTrue(memory.is_seen("rank(signal)"))

    def test_lineage_decision_index_is_bounded_and_keeps_recent_rounds(self):
        memory = ExperienceMemory(max_lineages=2)
        memory.lineages = {
            "old": {"last_round": 1, "decision": "KILL"},
            "newer": {"last_round": 9, "decision": "CONTINUE"},
            "newest": {"last_round": 10, "decision": "STOP"},
        }
        memory.compress()
        self.assertEqual(set(memory.lineages), {"newer", "newest"})

    def test_memory_drops_reconstructable_dynamic_hypothesis_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ExperienceMemory(tmp)
            memory.used_hypotheses.update({
                "h-1", "h-next-r12", "h-iter-r13", "h-seed-value",
                "h-rb41g-child-old", "rb489-hypothesis",
            })
            memory.save()
            loaded = ExperienceMemory(tmp).load()
            self.assertEqual(loaded.used_hypotheses, {"h-1", "h-seed-value"})

    def test_memory_drops_malformed_rows_and_legacy_seen_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "experience.json"), "w", encoding="utf-8") as handle:
                json.dump({
                    "lessons": [{"claim": None}],
                    "avoid": [{"direction": 3}],
                    "next": [{"idea": 8}],
                    "active_hypotheses": [{"id": None}],
                    "short_term": [{"text": None}],
                    "seen_expressions": "rank(close)",
                    "updated_round": "not-a-round",
                    "lineages": {"bad": "not-a-lineage"},
                }, handle)
            memory = ExperienceMemory(tmp).load()
            self.assertEqual(memory.seen_expressions, set())
            self.assertEqual(memory.updated_round, 0)
            self.assertEqual(memory.lineages, {})
            memory.save()
            self.assertEqual(memory.lessons, [])
            self.assertEqual(memory.avoid, [])
            self.assertEqual(memory.next, [])
            self.assertEqual(memory.short_term, [])

    def test_corrupt_memory_keeps_one_stable_diagnostic_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "experience.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{broken")
            ExperienceMemory(tmp).load()
            backup = path + ".corrupt"
            self.assertTrue(os.path.exists(backup))
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{broken-again")
            ExperienceMemory(tmp).load()
            self.assertEqual(
                sorted(os.listdir(tmp)), ["experience.json", "experience.json.corrupt"]
            )


class TestTrajectoryIdentity(unittest.TestCase):
    def test_iter_rows_skips_malformed_lines_without_materializing_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("not-json\n")
                handle.write(json.dumps({"id": "a", "status": "DONE"}) + "\n")
                handle.write(json.dumps(["not", "a", "row"]) + "\n")
                handle.write(json.dumps({"id": "b", "status": "PENDING"}) + "\n")
            rows = list(Trajectory(path=path).iter_rows())
            self.assertEqual([row["id"] for row in rows], ["a", "b"])

    def test_settings_fingerprint_is_rebuilt_and_removed_by_later_pending_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            trajectory = Trajectory(max_len=1, path=path)
            done = Experiment(1, "h-1", "rank(a)", {"decay": 4}, ["a"])
            done.status = "DONE"
            # Simulate an older row written before the fingerprint field was
            # mandatory; identity recovery must derive it from settings.
            trajectory.add(done)
            agent = object.__new__(Agent)
            agent.memory = ExperienceMemory(tmp)
            agent.trajectory = Trajectory(max_len=1, path=path).load()
            expressions, fingerprints = Agent._terminal_identities(agent)
            expected = "settings::" + submission_fingerprint(
                "rank(a)", {"decay": 4}
            )
            self.assertIn("rank(a)", expressions)
            self.assertIn(expected, fingerprints)

            pending = Experiment(1, "h-1", "rank(a)", {"decay": 4}, ["a"])
            pending.status = "PENDING"
            trajectory.add(pending)
            agent.trajectory = Trajectory(max_len=1, path=path).load()
            expressions, fingerprints = Agent._terminal_identities(agent)
            self.assertNotIn("rank(a)", expressions)
            self.assertNotIn(expected, fingerprints)

    def test_trajectory_does_not_reappend_id_that_left_recent_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            first = Experiment(1, "h", "rank(a)", {}, ["a"])
            second = Experiment(1, "h", "rank(b)", {}, ["b"])
            trajectory = Trajectory(max_len=1, path=path)
            trajectory.add(first)
            trajectory.add(second)
            restarted = Trajectory(max_len=1, path=path).load()
            restarted.add(first)
            with open(path, encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
            self.assertEqual([row["id"] for row in rows], [first.id, second.id])

    def test_trajectory_batch_reconciles_history_once_for_realtime_callbacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            old = Experiment(1, "h", "rank(old)", {}, ["old"])
            first = Experiment(1, "h", "rank(a)", {}, ["a"])
            second = Experiment(1, "h", "rank(b)", {}, ["b"])
            trajectory = Trajectory(max_len=1, path=path)
            trajectory.add(old)
            trajectory.load()
            with mock.patch.object(
                trajectory, "contains_ids", wraps=trajectory.contains_ids
            ) as contains:
                trajectory.begin_append_batch([first, second])
                trajectory.add(first)
                trajectory.add(second)
                trajectory.end_append_batch()
            self.assertEqual(contains.call_count, 1)


class TestCorrelationDiagnostic(unittest.TestCase):
    def test_malformed_or_missing_correlation_is_not_a_pass(self):
        payload = {
            "schema": {"properties": [{"name": "alpha"},
                                        {"name": "correlation"}]},
            "records": [["a", "bad"], ["b", None]],
        }
        props, rows = parse_records(payload)
        key, values = numeric_correlations(payload, props, rows)
        self.assertEqual(key, "correlation")
        self.assertEqual(values, [])

    def test_histogram_max_is_normalized_as_absolute_value(self):
        payload = {"max": "-0.42", "records": []}
        props, rows = parse_records(payload)
        key, values = numeric_correlations(payload, props, rows)
        self.assertIsNone(key)
        self.assertEqual(values, [0.42])

    def test_curator_uses_production_expression_identity(self):
        duplicates = detect_duplicates([
            {"experiment_id": "a", "expression": " Rank( x ) "},
            {"experiment_id": "b", "expression": "rank(x)"},
        ])
        self.assertEqual(duplicates["by_expression"], {"rank(x)": ["a", "b"]})

    def test_refresh_script_reuses_canonical_evidence_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            from wqb_agent.evidence import save_evidence_cache
            save_evidence_cache(tmp, {
                "alpha": {
                    "checks": [{"name": "SELF_CORRELATION", "pass": True,
                                "result": "PASS", "value": 0.2}],
                    "passed": True,
                }
            })

            class Client:
                def get_alpha(self, alpha_id):
                    return {"alpha_id": alpha_id}

            metrics = {
                "checks": [
                    {"name": "LOW_SHARPE", "pass": True, "result": "PASS"},
                    {"name": "SELF_CORRELATION", "pass": None,
                     "result": "PENDING"},
                ],
                "passed": None,
            }
            with mock.patch("scripts.refresh_evidence._extract_metrics",
                            return_value=metrics):
                settled = fetch_settled(Client(), tmp, "alpha")
            self.assertIsNotNone(settled)
            self.assertTrue(settled["passed"])

    def test_refresh_script_accepts_shared_cache_without_reloading_per_alpha(self):
        with tempfile.TemporaryDirectory() as tmp:
            class Client:
                def get_alpha(self, alpha_id):
                    return {"alpha_id": alpha_id}

            metrics = {
                "checks": [{"name": "SELF_CORRELATION", "pass": None,
                             "result": "PENDING"}],
                "passed": None,
            }
            with mock.patch("scripts.refresh_evidence._extract_metrics",
                            return_value=metrics), \
                 mock.patch("scripts.refresh_evidence.load_evidence_cache",
                            side_effect=AssertionError("cache reloaded")):
                settled = fetch_settled(
                    Client(), tmp, "alpha", cache={"alpha": {"checks": []}}
                )
            self.assertIsNone(settled)

    def test_refresh_pending_filter_accepts_resolved_result_only_check(self):
        self.assertEqual(
            pending_check_names({"checks": [{"name": "SELF_CORRELATION", "result": "PASS"}]}),
            [],
        )


class TestProposalBudget(unittest.TestCase):
    def test_production_cap_is_never_above_contract_limit(self):
        self.assertEqual(MAX_PROPOSALS_PER_ROUND, 18)
        self.assertEqual(proposal_budget_cap(40, 40), 18)
        self.assertEqual(proposal_budget_cap(6, 40), 6)
        self.assertEqual(proposal_budget_cap(40, 7), 7)


class TestAlphaFactory(unittest.TestCase):
    def test_pure_factory_import_does_not_load_production_chain(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import wqb_agent.alpha_factory; "
                "print('agent=' + str('wqb_agent.agent' in sys.modules)); "
                "print('client=' + str('wqb_agent.client' in sys.modules)); "
                "print('state=' + str('wqb_agent.state' in sys.modules))",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("agent=False", result.stdout)
        self.assertIn("client=False", result.stdout)
        self.assertIn("state=False", result.stdout)

    def test_template_first_instantiation_keeps_traceability(self):
        factory = AlphaFactory("SUBINDUSTRY")
        candidates = factory.generate(
            {"template_ids": ["reversal_zscore_20"]},
            [{"id": "returns"}, {"id": "volume"}],
            count=2,
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["template_id"], "reversal_zscore_20")
        self.assertEqual(candidate["template_family"], "reversal")
        self.assertEqual(candidate["fields_used"], ["returns"])
        self.assertEqual(candidate["template_ref"]["source"], "newwqb_builtin")
        self.assertEqual(
            candidate["template_slots"],
            {"p": "returns", "g": "subindustry", "s": "volume"},
        )
        self.assertEqual(len(candidate["template_ref"]["skeleton_fingerprint"]), 16)

    def test_two_field_template_requires_a_secondary_slot(self):
        factory = AlphaFactory()
        self.assertEqual(
            factory.generate({"template_ids": ["spread_rank"]}, [{"id": "a"}]),
            [],
        )

    def test_unknown_explicit_template_fails_closed(self):
        factory = AlphaFactory()
        self.assertEqual(
            factory.generate({"template_ids": ["typo_template"]}, [{"id": "a"}]),
            [],
        )
        self.assertEqual(
            factory.generate(
                {"template_ids": ["rank_level", "typo_template"]},
                [{"id": "a"}],
            ),
            [],
        )
        self.assertEqual(
            factory.generate(
                {"template_family": "typo_family", "direction": "long"},
                [{"id": "a"}],
            ),
            [],
        )

    def test_malformed_template_request_fails_closed(self):
        factory = AlphaFactory()
        self.assertEqual(
            factory.generate({"template_ids": {"rank_level": True}}, [{"id": "a"}]),
            [],
        )
        self.assertEqual(
            factory.generate({"template_ref": "rank_level"}, [{"id": "a"}]),
            [],
        )
        self.assertEqual(factory.generate([], [{"id": "a"}]), [])

    def test_candidate_builder_can_opt_into_template_mode(self):
        from wqb_agent.candidate import CandidateBuilder

        candidates = CandidateBuilder().build(
            {"template_family": "momentum", "direction": "long"},
            [{"id": "signal"}],
            None,
            count=1,
        )
        self.assertEqual(candidates[0]["template_family"], "momentum")
        self.assertTrue(candidates[0]["expression"].startswith("rank(ts_mean("))

    def test_assemble_proposals_is_auditable_and_type_aware(self):
        factory = AlphaFactory()
        proposals = factory.assemble_proposals(
            {"id": "h-factory", "statement": "test", "datasets": ["pv1"]},
            [{
                "id": "close",
                "description": "verified close field",
                "type": "MATRIX",
                "coverage": 0.99,
                "frequency": "daily",
                "semantic_status": "KNOWN",
                "dataset": "pv1",
                "field_source": {"kind": "local_catalog", "snapshot_date": "20260906"},
            }],
            {"sha256": "operator-sha", "operators": ["rank"]},
            max_candidates=1,
        )
        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        self.assertEqual(proposal["experiment_stage"], "BASELINE")
        self.assertEqual(proposal["research_role"], "EXPLORE")
        self.assertEqual(proposal["field_hypothesis_basis"]["close"]["description"],
                         "verified close field")
        self.assertEqual(proposal["operator_evidence"]["sha256"], "operator-sha")

    def test_vector_factory_uses_verified_vector_aggregation(self):
        proposals = AlphaFactory().assemble_proposals(
            {"id": "h-vector", "statement": "test", "datasets": ["x"]},
            [{"id": "vec", "description": "verified vector", "type": "VECTOR",
              "semantic_status": "KNOWN", "dataset": "x"}],
            {"sha256": "s", "operators": ["rank", "vec_avg"]},
            max_candidates=1,
        )
        self.assertEqual(proposals[0]["expression"], "rank(vec_avg(vec))")

    def test_assemble_caps_repeated_template_family(self):
        proposals = AlphaFactory().assemble_proposals(
            {"id": "h", "statement": "test", "datasets": ["pv1"]},
            [{"id": f"f{i}", "description": "verified", "type": "MATRIX",
              "semantic_status": "KNOWN", "dataset": "pv1"} for i in range(4)],
            {"sha256": "s", "operators": ["rank"]},
            max_candidates=4,
        )
        self.assertEqual(len(proposals), 2)
        self.assertEqual(
            {proposal["template_family"] for proposal in proposals},
            {"cross_sectional_rank"},
        )

    def test_economic_templates_have_bounded_operator_complexity(self):
        factory = AlphaFactory()
        templates = factory.registry.economic_templates()
        self.assertGreaterEqual(len(templates), 18)
        self.assertTrue(all(3 <= item.operator_count <= 8 for item in templates))
        self.assertTrue(all(item.catalog_entry()["economic"] for item in templates))

    def test_economic_mode_uses_auditable_multi_operator_template(self):
        factory = AlphaFactory()
        operators = {
            "rank", "ts_decay_linear", "ts_delta", "ts_zscore", "ts_mean",
            "reverse", "divide", "add", "ts_std_dev", "hump", "normalize",
            "winsorize", "quantile", "group_neutralize", "group_zscore",
            "group_backfill", "group_rank", "vec_avg", "vec_sum", "subtract",
            "ts_covariance", "ts_corr", "abs", "trade_when", "ts_rank",
        }
        proposals = factory.assemble_proposals(
            {"id": "h-economic", "datasets": ["x"], "template_mode": "economic"},
            [{"id": "signal", "description": "verified signal", "type": "MATRIX",
              "semantic_status": "KNOWN", "dataset": "x",
              "field_source": {"kind": "local_catalog", "snapshot_date": "20260907"}}],
            {"sha256": "operator-sha", "operators": sorted(operators)},
            max_candidates=2,
        )
        self.assertTrue(proposals)
        self.assertTrue(all(p["experiment_stage"] == "BASELINE" for p in proposals))
        self.assertTrue(all(p["template_family"] not in {"cross_sectional_rank", "momentum"}
                            for p in proposals))
        self.assertTrue(all(len(p["operator_evidence"]["operators"]) >= 3 for p in proposals))

    def test_economic_mode_routes_vector_fields_to_vector_template(self):
        factory = AlphaFactory()
        operators = {"rank", "vec_avg", "ts_mean", "ts_zscore"}
        proposals = factory.assemble_proposals(
            {"id": "h-vector-economic", "datasets": ["x"],
             "template_mode": "economic"},
            [{"id": "vector_signal", "description": "verified vector", "type": "VECTOR",
              "semantic_status": "KNOWN", "dataset": "x",
              "field_source": {"kind": "local_catalog", "snapshot_date": "20260907"}}],
            {"sha256": "operator-sha", "operators": sorted(operators)},
            max_candidates=1,
        )
        self.assertEqual(proposals[0]["template_id"], "vector_persistent_signal")
        self.assertIn("vec_avg", proposals[0]["operator_evidence"]["operators"])

    def test_autonomous_optimizer_only_mutates_completed_signal(self):
        factory = AlphaFactory()
        parent = {
            "status": "DONE", "expression": "rank(ts_delta(signal, 5))",
            "metrics": {"sharpe": 1.0, "fitness": 0.7, "turnover": 0.2},
            "health": {"ok": True}, "fields_used": ["signal"],
            "datasets": ["x"], "field_understanding": {"signal": "verified"},
            "field_analysis": {"signal": {"semantic": "verified", "coverage": 1,
                                             "frequency": "daily", "data_type": "MATRIX"}},
            "field_source": {"kind": "local_catalog", "snapshot_date": "20260907"},
            "field_hypothesis_basis": {"signal": {"description": "verified",
                                                     "mechanism": "change",}},
            "lineage_id": "lineage-signal", "hypothesis_id": "h-signal",
            "direction": "long",
        }
        proposals = factory.optimize_signal_proposals(
            [parent],
            {"sha256": "operator-sha", "operators": [
                "rank", "ts_delta", "hump", "ts_decay_linear"
            ]},
            max_candidates=2,
        )
        self.assertEqual(len(proposals), 2)
        self.assertTrue(all(p["experiment_stage"] == "CHILD" for p in proposals))
        self.assertTrue(all(p["research_role"] == "EXPLOIT" for p in proposals))
        self.assertTrue(all(p["parent_expression"] == parent["expression"] for p in proposals))


class TestProposalInputGuards(unittest.TestCase):
    def test_public_proposal_helpers_fail_closed_on_wrong_shapes(self):
        ok, problems = validate_proposal(None)
        self.assertFalse(ok)
        self.assertIn("proposal 必须是对象", problems)
        ok, problems = validate_vector_inputs([], {})
        self.assertFalse(ok)
        self.assertIn("proposal 必须是对象", problems)
        ok, problems = validate_vector_inputs({}, [])
        self.assertFalse(ok)
        self.assertIn("field_types 必须是对象", problems)
        self.assertEqual(proposal_priority(None), 0.0)


class TestIdempotentArtifacts(unittest.TestCase):
    def test_shared_jsonl_reader_skips_bad_and_non_object_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "derived.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("broken\n[]\n")
                handle.write(json.dumps({"id": "ok"}) + "\n")
            self.assertEqual(list(iter_jsonl_objects(path)), [{"id": "ok"}])

    def test_json_write_is_noop_for_same_logical_payload_and_volatile_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            self.assertTrue(atomic_write_json_if_changed(
                path, {"value": 1, "updated_at": 1}
            ))
            first = os.stat(path).st_mtime_ns
            self.assertFalse(atomic_write_json_if_changed(
                path, {"value": 1, "updated_at": 2},
                ignored_keys=("updated_at",),
            ))
            self.assertEqual(os.stat(path).st_mtime_ns, first)

    def test_jsonl_derived_write_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "derived.jsonl")
            rows = [{"id": "a"}, {"id": "b"}]
            self.assertTrue(atomic_write_jsonl_if_changed(path, rows))
            first = os.stat(path).st_mtime_ns
            self.assertFalse(atomic_write_jsonl_if_changed(path, rows))
            self.assertEqual(os.stat(path).st_mtime_ns, first)

    def test_jsonl_derived_write_accepts_stream_without_building_joined_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "derived.jsonl")

            def rows():
                for index in range(3):
                    yield {"id": str(index)}

            self.assertTrue(atomic_write_jsonl_if_changed(path, rows()))
            with open(path, encoding="utf-8") as handle:
                self.assertEqual([json.loads(line)["id"] for line in handle], ["0", "1", "2"])

    def test_memory_persists_seen_expressions_compressed_without_losing_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ExperienceMemory(tmp)
            expressions = {f"rank(field_{i})" for i in range(200)}
            for expression in expressions:
                memory.remember_expression(expression)
            memory.save()
            with open(os.path.join(tmp, "experience.json"), encoding="utf-8") as handle:
                raw = handle.read()
            self.assertIn("seen_expressions_blob", raw)
            self.assertLess(len(raw), sum(len(x) for x in expressions) + 3000)
            restored = ExperienceMemory(tmp).load()
            self.assertEqual(restored.seen_expressions, expressions)

    def test_seen_expression_cache_is_bounded(self):
        memory = ExperienceMemory(max_seen_expressions=2)
        for index in range(10):
            memory.remember_expression(f"rank(field_{index})")
        self.assertEqual(len(memory.seen_expressions), 2)

    def test_used_hypothesis_cache_is_bounded(self):
        memory = ExperienceMemory(max_used_hypotheses=2)
        for index in range(10):
            memory.register_hypothesis({"id": f"external-{index}"})
        self.assertEqual(len(memory.used_hypotheses), 2)

    def test_used_hypothesis_cache_normalizes_numeric_ids(self):
        memory = ExperienceMemory(max_used_hypotheses=2)
        memory.register_hypothesis({"id": 7})
        memory.register_hypothesis({"id": "8"})
        self.assertEqual(memory.used_hypotheses, {"7", "8"})

    def test_terminal_dedupe_prefers_trajectory_over_stale_memory_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            current = Experiment(1, "h", "rank(current)", {}, ["current"])
            current.status = "DONE"
            Trajectory(path=path).add(current)
            agent = object.__new__(Agent)
            agent.memory = ExperienceMemory(max_seen_expressions=2)
            agent.memory.remember_expression("rank(stale)")
            agent.trajectory = Trajectory(max_len=1, path=path).load()
            expressions, _ = Agent._terminal_identities(agent)
            self.assertIn("rank(current)", expressions)
            self.assertNotIn("rank(stale)", expressions)

    def test_terminal_dedupe_can_scope_history_scan_to_current_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            trajectory = Trajectory(path=path)
            for index in range(20):
                item = Experiment(1, "h", f"rank(old_{index})", {}, [f"old_{index}"])
                item.status = "DONE"
                trajectory.add(item)
            current = Experiment(1, "h", "rank(current)", {}, ["current"])
            current.status = "DONE"
            trajectory.add(current)
            agent = object.__new__(Agent)
            agent.memory = ExperienceMemory()
            agent.trajectory = Trajectory(max_len=1, path=path).load()
            expressions, _ = Agent._terminal_identities(agent, ["rank(current)"])
            self.assertEqual(expressions, {"rank(current)"})


class TestStreamingReportInputs(unittest.TestCase):
    def test_report_helpers_degrade_bad_memory_and_non_string_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "experience.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("broken")
            value, error = _load_json_object(path)
            self.assertEqual(value, {})
            self.assertTrue(error)
        self.assertEqual(_safe_text(None, 10), "")
        self.assertEqual(_safe_text(12345, 3), "123")

    def test_report_source_normalizes_display_ids_before_alpha_mapping(self):
        source = Path(generate_report.__file__).read_text(encoding="utf-8")
        self.assertIn("local_id = _safe_text(e.get(\"id\"))", source)
        self.assertIn("if isinstance(best, dict) and best", source)
        self.assertIn("isinstance(e.get(\"metrics\"), dict)", source)

    def test_report_uses_shared_jsonl_reader_and_bounded_hypothesis_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"id": "a", "hypothesis_id": "h1"}) + "\n")
                handle.write("broken\n")
            self.assertEqual(list(generate_report.iter_trajectory(path))[0]["id"], "a")
        source = Path(generate_report.__file__).read_text(encoding="utf-8")
        self.assertIn("iter_jsonl_objects", source)
        self.assertNotIn("json.loads(line)", source)
        self.assertIn("display_hypothesis_ids", source)

    def test_curator_trajectory_iterator_preserves_source_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("not-json\n")
                handle.write('{"id": "a"}\n')
            rows = list(iter_trajectory(path))
            self.assertEqual(rows, [{"id": "a", "_source_line": 2}])

    def test_report_reader_skips_bad_rows_and_snapshot_time_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"id": "a", "status": "DONE"}\n')
                handle.write("not-json\n")
                handle.write("[]\n")
                handle.write('{"id": "b", "status": "FAILED"}\n')
            self.assertEqual([row["id"] for row in iter_trajectory(path)], ["a", "b"])
            first = state_snapshot_time((path,))
            second = state_snapshot_time((path,))
            self.assertEqual(first, second)

    def test_curated_jsonl_write_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "derived.jsonl")
            rows = [{"round": 1, "status": "DONE"}]
            self.assertTrue(write_jsonl_if_changed(path, rows))
            first = os.stat(path).st_mtime_ns
            self.assertFalse(write_jsonl_if_changed(path, rows))
            self.assertEqual(os.stat(path).st_mtime_ns, first)

    def test_audit_jsonl_append_is_idempotent_by_stable_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.jsonl")
            row = {"round_no": 4, "experiment_id": "e1", "reason": "manual"}
            self.assertTrue(append_jsonl_if_unique(
                path, dict(row, timestamp="first"),
                ("round_no", "experiment_id", "reason"),
            ))
            self.assertFalse(append_jsonl_if_unique(
                path, dict(row, timestamp="second"),
                ("round_no", "experiment_id", "reason"),
            ))
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(len(handle.readlines()), 1)


class TestFactoryRunner(unittest.TestCase):
    def test_completed_checkpoint_cache_rechecks_changed_file(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            path = os.path.join(tmp, "round_1.checkpoint.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"round_no": 1, "complete": True}, handle)
            runner = AIFactoryRunner(FakeAgent())
            self.assertIsNone(runner._unfinished_checkpoint())
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"round_no": 1, "complete": False}, handle)
            self.assertEqual(runner._unfinished_checkpoint(), path)

    def test_factory_stops_deterministic_error_instead_of_retrying(self):
        class BadAgent:
            def __init__(self, state_dir):
                self.state_dir = state_dir
                self.alpha_factory = AlphaFactory()
                self.calls = 0

            def next_round_no(self):
                return 1

            def run_suggestion_round(self, _round_no):
                self.calls += 1
                raise ValueError("malformed canonical state")

        with tempfile.TemporaryDirectory() as tmp:
            agent = BadAgent(tmp)
            session = AIFactoryRunner(agent).run(
                duration_sec=10, idle_sleep_sec=1, max_simulations=2
            )
            self.assertEqual(session["status"], "RECONCILE_REQUIRED")
            self.assertEqual(agent.calls, 1)
    def test_completed_checkpoints_are_scanned_once_per_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            for round_no in (1, 2):
                with open(os.path.join(tmp, f"round_{round_no}.checkpoint.json"), "w",
                          encoding="utf-8") as handle:
                    json.dump({"round_no": round_no, "complete": True}, handle)
            agent = type("Agent", (), {"state_dir": tmp, "alpha_factory": None})()
            runner = AIFactoryRunner(agent)
            with mock.patch("builtins.open", wraps=open) as opened:
                self.assertIsNone(runner._unfinished_checkpoint())
                first_count = opened.call_count
                self.assertIsNone(runner._unfinished_checkpoint())
                self.assertEqual(opened.call_count, first_count)

    def test_completed_checkpoint_signature_cache_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            for round_no in range(520):
                with open(os.path.join(tmp, f"round_{round_no}.checkpoint.json"), "w",
                          encoding="utf-8") as handle:
                    json.dump({"round_no": round_no, "complete": True}, handle)
            agent = type("Agent", (), {"state_dir": tmp, "alpha_factory": None})()
            runner = AIFactoryRunner(agent)
            self.assertIsNone(runner._unfinished_checkpoint())
            self.assertLessEqual(
                len(runner._complete_checkpoint_signatures),
                runner.CHECKPOINT_CACHE_MAX,
            )

    def test_factory_stop_updates_only_canonical_session(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            runner = AIFactoryRunner(FakeAgent())
            runner._save_session({
                "schema_version": 1, "session_id": "session-1", "started_at": 1,
                "deadline": 100, "status": "RUNNING", "rounds_completed": 0,
                "simulations_reserved": 0, "simulation_cap": 10,
            })
            stopped = AIFactoryRunner.request_stop(tmp)
            self.assertTrue(stopped["stop_requested"])
            self.assertEqual(stopped["last_action"], "STOP_REQUESTED")
            self.assertEqual(sorted(os.listdir(tmp)), ["factory_session.json"])

    def test_factory_stop_is_idempotent(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            AIFactoryRunner(FakeAgent())._save_session({
                "schema_version": 1, "session_id": "session-1", "started_at": 1,
                "deadline": 100, "status": "RUNNING", "rounds_completed": 0,
                "simulations_reserved": 0, "simulation_cap": 10,
            })
            first = AIFactoryRunner.request_stop(tmp)
            second = AIFactoryRunner.request_stop(tmp)
            self.assertEqual(first["session_id"], second["session_id"])
            self.assertEqual(first["stop_requested"], second["stop_requested"])

    def test_factory_does_not_reset_reconcile_session_into_a_new_post_window(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

            def next_round_no(self):
                raise AssertionError("对账阻断期间不得开启新轮")

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            runner = AIFactoryRunner(FakeAgent())
            existing = {
                "schema_version": 1, "session_id": "reconcile-1",
                "started_at": 1, "deadline": 9999999999,
                "status": "RECONCILE_REQUIRED", "rounds_completed": 1,
                "simulations_reserved": 1, "simulation_cap": 10,
                "last_action": "EXECUTION_RECONCILE_REQUIRED",
            }
            runner._save_session(existing)

            returned = runner.run(duration_sec=2, max_simulations=10)

            self.assertEqual(returned["session_id"], "reconcile-1")
            self.assertEqual(returned["status"], "RECONCILE_REQUIRED")
            self.assertEqual(AIFactoryRunner.read_session(tmp)["session_id"], "reconcile-1")

    def test_factory_does_not_overwrite_corrupt_session_envelope(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

            def next_round_no(self):
                raise AssertionError("损坏控制面不得进入 discovery")

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            path = os.path.join(tmp, "factory_session.json")
            raw = "{not-json"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(raw)

            returned = AIFactoryRunner(FakeAgent()).run(duration_sec=2)

            self.assertEqual(returned["status"], "RECONCILE_REQUIRED")
            self.assertEqual(returned["last_action"], "INVALID_SESSION")
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), raw)
            self.assertEqual(AIFactoryRunner.status_view(tmp)["last_action"], "INVALID_SESSION")

    def test_factory_keeps_reservation_when_normal_execution_leaves_checkpoint(self):
        class FakeAgent:
            def __init__(self, state_dir):
                self.state_dir = state_dir
                self.alpha_factory = AlphaFactory()
                self.candidates_per_round = 2
                self.last_run_stats = {"accepted": 2}
                self.calls = 0

            def next_round_no(self):
                return 1

            def run_suggestion_round(self, round_no):
                return {
                    "epoch_label": "rb-test",
                    "research_space": {"id": "h", "statement": "test", "datasets": ["pv1"]},
                    "field_source": {"kind": "local_catalog", "snapshot_date": "20260906"},
                    "operator_reference": {"sha256": "s", "operators": ["rank"]},
                    "fields": [{
                        "id": "close", "description": "verified", "type": "MATRIX",
                        "semantic_status": "KNOWN", "dataset": "pv1",
                        "field_source": {"kind": "local_catalog", "snapshot_date": "20260906"},
                    }],
                }

            def run_proposals(self, path):
                self.calls += 1
                checkpoint = os.path.join(self.state_dir, "round_1.checkpoint.json")
                if self.calls == 1:
                    with open(checkpoint, "w", encoding="utf-8") as handle:
                        json.dump({"round_no": 1, "complete": False, "experiments": [{"id": "a"}, {"id": "b"}]}, handle)
                    return None
                os.unlink(checkpoint)
                return {"round": 1, "verdicts": {"FAIL": 2}}

        with tempfile.TemporaryDirectory() as tmp:
            agent = FakeAgent(tmp)
            session = AIFactoryRunner(agent).run(
                duration_sec=2, max_rounds=1, idle_sleep_sec=1, max_simulations=2
            )
            self.assertEqual(agent.calls, 2)
            self.assertEqual(session["status"], "ROUND_CAP")
            self.assertEqual(session["rounds_completed"], 1)
            self.assertEqual(session["simulations_reserved"], 1)

    def test_factory_does_not_recover_mismatched_proposals(self):
        class FakeAgent:
            def __init__(self, state_dir):
                self.state_dir = state_dir
                self.alpha_factory = AlphaFactory()
                self.candidates_per_round = 1
                self.recovered = False

            def next_round_no(self):
                raise AssertionError("错轮次提案不能进入新一轮 discovery")

            def run_proposals(self, path):
                self.recovered = True

        with tempfile.TemporaryDirectory() as tmp:
            agent = FakeAgent(tmp)
            with open(os.path.join(tmp, "round_9.checkpoint.json"), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 9, "complete": False}, handle)
            with open(os.path.join(tmp, "proposals.json"), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 8, "proposals": []}, handle)
            session = AIFactoryRunner(agent).run(duration_sec=2, idle_sleep_sec=1)
            self.assertEqual(session["status"], "RECONCILE_REQUIRED")
            self.assertFalse(agent.recovered)

    def test_factory_runner_preserves_concurrent_stop_request(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            runner = AIFactoryRunner(FakeAgent())
            session = {
                "schema_version": 1, "session_id": "session-1", "started_at": 1,
                "deadline": 100, "status": "RUNNING", "rounds_completed": 0,
                "simulations_reserved": 0, "simulation_cap": 10,
            }
            runner._save_session(session)
            session["stop_requested"] = False
            current = AIFactoryRunner.request_stop(tmp)
            self.assertTrue(current["stop_requested"])
            runner._save_session(session)
            persisted = AIFactoryRunner.read_session(tmp)
            self.assertTrue(persisted["stop_requested"])

    def test_factory_releases_preflight_rejections_from_budget(self):
        class FakeAgent:
            def __init__(self, state_dir):
                self.state_dir = state_dir
                self.alpha_factory = AlphaFactory()
                self.candidates_per_round = 2
                self.last_run_stats = {"accepted": 0}
                self.calls = 0

            def next_round_no(self):
                return 1

            def run_suggestion_round(self, round_no):
                return {
                    "epoch_label": "rb-test",
                    "research_space": {"id": "h", "statement": "test", "datasets": ["pv1"]},
                    "field_source": {"kind": "local_catalog", "snapshot_date": "20260906"},
                    "operator_reference": {"sha256": "s", "operators": ["rank"]},
                    "fields": [{
                        "id": "close", "description": "verified", "type": "MATRIX",
                        "semantic_status": "KNOWN", "dataset": "pv1",
                        "field_source": {"kind": "local_catalog", "snapshot_date": "20260906"},
                    }],
                }

            def run_proposals(self, path):
                self.calls += 1
                self.last_run_stats = {"accepted": 0, "rejected": 2, "skipped": 0}
                return None

        with tempfile.TemporaryDirectory() as tmp:
            agent = FakeAgent(tmp)
            session = AIFactoryRunner(agent).run(
                duration_sec=2, max_rounds=1, idle_sleep_sec=1
            )
            self.assertEqual(session["simulations_reserved"], 0)

    def test_factory_excludes_known_expression_before_writing_inbox(self):
        factory = AlphaFactory()
        fields = [{
            "id": "close", "description": "verified", "type": "MATRIX",
            "semantic_status": "KNOWN", "dataset": "pv1",
        }]
        reference = {"sha256": "s", "operators": ["rank"]}
        first = factory.assemble_proposals(
            {"id": "h", "statement": "test", "datasets": ["pv1"]},
            fields, reference, max_candidates=1,
        )
        second = factory.assemble_proposals(
            {"id": "h", "statement": "test", "datasets": ["pv1"]},
            fields, reference, max_candidates=1,
            excluded_expressions=[first[0]["expression"]],
        )
        self.assertEqual(second, [])

    def test_factory_rotates_to_new_template_after_exact_dedupe(self):
        factory = AlphaFactory()
        fields = [{
            "id": "close", "description": "verified", "type": "MATRIX",
            "semantic_status": "KNOWN", "dataset": "pv1",
        }]
        reference = {
            "sha256": "s", "operators": ["rank", "ts_zscore"]
        }
        first = factory.assemble_proposals(
            {"id": "h", "statement": "test", "datasets": ["pv1"]},
            fields, reference, max_candidates=1,
        )
        second = factory.assemble_proposals(
            {"id": "h", "statement": "test", "datasets": ["pv1"]},
            fields, reference, max_candidates=1,
            excluded_expressions=[first[0]["expression"]],
        )
        self.assertEqual(len(second), 1)
        self.assertNotEqual(second[0]["expression"], first[0]["expression"])


class TestFactoryRunnerContinuation(unittest.TestCase):
    def test_factory_zero_duration_does_not_overwrite_live_session(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            runner = AIFactoryRunner(FakeAgent())
            runner._save_session({
                "schema_version": 1, "session_id": "live", "started_at": 1,
                "deadline": 100, "status": "RUNNING", "rounds_completed": 2,
                "simulations_reserved": 3, "simulation_cap": 10,
            })
            session = runner.run(duration_sec=0)
            self.assertEqual(session["session_id"], "live")
            self.assertEqual(session["status"], "RUNNING")

    def test_factory_quiet_call_does_not_emit_per_round_report(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            runner = AIFactoryRunner(FakeAgent())
            output = io.StringIO()
            with redirect_stdout(output):
                runner._call(lambda: print("internal round report"))
            self.assertEqual(output.getvalue(), "")
            source = Path(__import__(
                "wqb_agent.factory_runner", fromlist=["AIFactoryRunner"]
            ).__file__).read_text(encoding="utf-8")
            self.assertNotIn("io.StringIO", source)
            self.assertIn("_DISCARD_STDOUT", source)

    def test_factory_reconciles_template_contract_error_without_retry_loop(self):
        class Clock:
            def __init__(self):
                self.now = 0

            def __call__(self):
                return self.now

            def sleep(self, seconds):
                self.now += seconds

        class FailingFactory:
            def assemble_proposals(self, *args, **kwargs):
                raise ValueError("template contract failure")

        class FakeAgent:
            def __init__(self, state_dir):
                self.state_dir = state_dir
                self.alpha_factory = FailingFactory()
                self.candidates_per_round = 1

            def next_round_no(self):
                return 1

            def run_suggestion_round(self, round_no):
                return {"research_space": {"id": "h", "datasets": ["pv1"]}, "fields": []}

        with tempfile.TemporaryDirectory() as tmp:
            clock = Clock()
            session = AIFactoryRunner(
                FakeAgent(tmp), clock=clock, sleeper=clock.sleep
            ).run(duration_sec=2, idle_sleep_sec=1)
            self.assertEqual(session["status"], "RECONCILE_REQUIRED")
            self.assertEqual(session["last_action"], "ASSEMBLE_RECONCILE_REQUIRED")
            self.assertFalse(os.path.exists(os.path.join(tmp, "proposals.json")))

    def test_factory_recovers_orphaned_canonical_proposals_before_new_discovery(self):
        class FakeAgent:
            def __init__(self, state_dir):
                self.state_dir = state_dir
                self.alpha_factory = AlphaFactory()
                self.candidates_per_round = 1
                self.last_run_stats = {"accepted": 1}
                self.recovery_calls = 0

            def next_round_no(self):
                raise AssertionError("孤儿提案恢复完成前不得进入新 discovery")

            def run_proposals(self, path):
                self.recovery_calls += 1
                return {"round": 3, "verdicts": {"FAIL": 1}}

        with tempfile.TemporaryDirectory() as tmp:
            agent = FakeAgent(tmp)
            runner = AIFactoryRunner(agent)
            runner._save_session({
                "schema_version": 1, "session_id": "s", "started_at": 1,
                "deadline": 9999999999, "status": "RUNNING", "rounds_completed": 0,
                "simulations_reserved": 1, "simulation_cap": 1,
                "last_round": 3, "last_action": "RUN_PROPOSALS",
                "last_result": None,
            })
            with open(os.path.join(tmp, "proposals.json"), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 3, "factory_session_id": "s",
                           "proposals": [{"expression": "rank(close)"}]}, handle)
            self.assertEqual(
                len(runner._orphaned_canonical_proposals(runner.read_session(tmp))), 1
            )
            session = runner.run(duration_sec=2, max_rounds=1, idle_sleep_sec=1)
            self.assertEqual(agent.recovery_calls, 1)
            self.assertEqual(session["status"], "ROUND_CAP")
            self.assertEqual(session["last_result"]["round_no"], 3)
            self.assertEqual(session["simulations_reserved"], 1)

    def test_factory_stops_after_canonical_proposal_write_error(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()
            candidates_per_round = 1

            def next_round_no(self):
                return 1

            def run_suggestion_round(self, round_no):
                return {"research_space": {"id": "h", "datasets": ["pv1"]}, "fields": []}

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            runner = AIFactoryRunner(FakeAgent())

            def fail_only_proposals(path, payload, **kwargs):
                if os.path.basename(path) == "proposals.json":
                    raise OSError("disk full")
                return atomic_write_json_if_changed(path, payload, **kwargs)

            with mock.patch(
                "wqb_agent.factory_runner.atomic_write_json_if_changed",
                side_effect=fail_only_proposals,
            ):
                session = runner.run(duration_sec=2, idle_sleep_sec=1)
            self.assertEqual(session["status"], "RECONCILE_REQUIRED")
            self.assertEqual(session["last_action"], "STORAGE_RECONCILE_REQUIRED")

    def test_factory_retries_discovery_exception_without_creating_artifact(self):
        class FakeAgent:
            def __init__(self, state_dir):
                self.state_dir = state_dir
                self.alpha_factory = AlphaFactory()
                self.candidates_per_round = 1

            def next_round_no(self):
                return 1

            def run_suggestion_round(self, round_no):
                raise OSError("temporary discovery failure")

        with tempfile.TemporaryDirectory() as tmp:
            session = AIFactoryRunner(FakeAgent(tmp)).run(
                duration_sec=2, idle_sleep_sec=1
            )
            self.assertEqual(session["status"], "DEADLINE")
            self.assertEqual(session["last_action"], "SUGGEST_ERROR")
            self.assertGreaterEqual(session["retry_count"], 1)
            self.assertEqual(sorted(os.listdir(tmp)), ["factory_session.json"])

    def test_factory_execution_exception_keeps_budget_reserved_for_recovery(self):
        class FakeAgent:
            def __init__(self, state_dir):
                self.state_dir = state_dir
                self.alpha_factory = AlphaFactory()
                self.candidates_per_round = 1
                self.last_run_stats = {"accepted": 1}

            def next_round_no(self):
                return 1

            def run_suggestion_round(self, round_no):
                return {
                    "epoch_label": "rb-test",
                    "research_space": {"id": "h", "statement": "test", "datasets": ["pv1"]},
                    "field_source": {"kind": "local_catalog", "snapshot_date": "20260906"},
                    "operator_reference": {"sha256": "s", "operators": ["rank"]},
                    "fields": [{
                        "id": "close", "description": "verified", "type": "MATRIX",
                        "semantic_status": "KNOWN", "dataset": "pv1",
                        "field_source": {"kind": "local_catalog", "snapshot_date": "20260906"},
                    }],
                }

            def run_proposals(self, path):
                raise RuntimeError("execution interrupted after durable submission")

        with tempfile.TemporaryDirectory() as tmp:
            session = AIFactoryRunner(FakeAgent(tmp)).run(
                duration_sec=2, max_rounds=1, idle_sleep_sec=1,
                max_simulations=1,
            )
            self.assertEqual(session["status"], "RECONCILE_REQUIRED")
            self.assertEqual(session["simulations_reserved"], 1)
            self.assertEqual(session["last_action"], "EXECUTION_RECONCILE_REQUIRED")
            self.assertEqual(session["last_result"]["error_type"], "RuntimeError")

    def test_factory_recovers_checkpoint_exceptions_without_crashing_or_new_round(self):
        class FakeAgent:
            def __init__(self, state_dir):
                self.state_dir = state_dir
                self.alpha_factory = AlphaFactory()
                self.recovery_calls = 0

            def next_round_no(self):
                raise AssertionError("恢复失败期间不得创建新轮次")

            def run_proposals(self, path):
                self.recovery_calls += 1
                raise RuntimeError("recovery interrupted")

        with tempfile.TemporaryDirectory() as tmp:
            agent = FakeAgent(tmp)
            with open(os.path.join(tmp, "round_9.checkpoint.json"), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 9, "complete": False}, handle)
            with open(os.path.join(tmp, "proposals.json"), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 9, "proposals": []}, handle)
            session = AIFactoryRunner(agent).run(
                duration_sec=2, idle_sleep_sec=1, max_simulations=1
            )
            self.assertEqual(session["status"], "DEADLINE")
            self.assertGreaterEqual(agent.recovery_calls, 1)
            persisted = AIFactoryRunner.read_session(tmp)
            self.assertEqual(persisted["last_action"], "RECOVER_CHECKPOINT_ERROR")

    def test_factory_reserves_and_accounts_for_legacy_checkpoint_recovery(self):
        class FakeAgent:
            def __init__(self, state_dir):
                self.state_dir = state_dir
                self.alpha_factory = AlphaFactory()
                self.candidates_per_round = 1
                self.recovery_calls = 0

            def next_round_no(self):
                raise AssertionError("恢复完成后达到轮次上限，不应创建新轮")

            def run_proposals(self, path):
                self.recovery_calls += 1
                checkpoint_path = os.path.join(self.state_dir, "round_4.checkpoint.json")
                with open(checkpoint_path, "w", encoding="utf-8") as handle:
                    json.dump({"round_no": 4, "complete": True, "experiments": [{"id": "e1"}]}, handle)
                return {"round": 4, "verdicts": {"FAIL": 1}}

        with tempfile.TemporaryDirectory() as tmp:
            agent = FakeAgent(tmp)
            with open(os.path.join(tmp, "round_4.checkpoint.json"), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 4, "complete": False, "experiments": [{"id": "e1"}]}, handle)
            with open(os.path.join(tmp, "proposals.json"), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 4, "proposals": []}, handle)
            session = AIFactoryRunner(agent).run(
                duration_sec=2, max_rounds=1, idle_sleep_sec=1, max_simulations=1
            )
            self.assertEqual(agent.recovery_calls, 1)
            self.assertEqual(session["status"], "ROUND_CAP")
            self.assertEqual(session["rounds_completed"], 1)
            self.assertEqual(session["simulations_reserved"], 1)
            self.assertEqual(session["last_action"], "ROUND_CAP")

    def test_factory_blocks_oversized_checkpoint_before_recovery(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

            def next_round_no(self):
                raise AssertionError("预算不足时不得开启新 discovery")

            def run_proposals(self, path):
                raise AssertionError("预算不足时不得恢复 checkpoint")

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            with open(os.path.join(tmp, "round_2.checkpoint.json"), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 2, "complete": False, "experiments": [{"id": "a"}, {"id": "b"}]}, handle)
            with open(os.path.join(tmp, "proposals.json"), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 2, "proposals": []}, handle)
            session = AIFactoryRunner(FakeAgent()).run(
                duration_sec=2, idle_sleep_sec=1, max_simulations=1
            )
            self.assertEqual(session["status"], "SIMULATION_BUDGET_CAP")
            self.assertEqual(session["last_action"], "RECOVERY_BUDGET_BLOCKED")
            self.assertEqual(session["simulations_reserved"], 0)

    def test_factory_rotates_discovery_probe_without_changing_simulation_round(self):
        class FakeAgent:
            def __init__(self, state_dir):
                self.state_dir = state_dir
                self.alpha_factory = AlphaFactory()
                self.candidates_per_round = 1
                self.probe_rounds = []

            def next_round_no(self):
                return 7

            def run_suggestion_round(self, round_no):
                self.probe_rounds.append(round_no)
                return {
                    "research_space": {"id": "h", "statement": "test", "datasets": ["pv1"]},
                    "field_source": {"kind": "local_catalog", "snapshot_date": "20260906"},
                    "operator_reference": {"sha256": "s", "operators": ["rank"]},
                    "fields": [],
                }

        with tempfile.TemporaryDirectory() as tmp:
            agent = FakeAgent(tmp)
            session = AIFactoryRunner(agent).run(
                duration_sec=2, idle_sleep_sec=1, max_simulations=2
            )
            self.assertGreaterEqual(len(agent.probe_rounds), 2)
            self.assertEqual(agent.probe_rounds[:2], [7, 8])
            self.assertEqual(session["rounds_completed"], 0)
            self.assertEqual(session["last_round"], 7)

    def test_factory_restart_reuses_deadline_and_budget(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

            def next_round_no(self):
                raise AssertionError("已耗尽预算时不应重新 discovery")

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            runner = AIFactoryRunner(FakeAgent())
            runner._save_session({
                "schema_version": 1, "session_id": "existing", "started_at": 1,
                "deadline": 9999999999, "status": "RUNNING",
                "rounds_completed": 4, "simulations_reserved": 2,
                "simulation_cap": 2,
            })
            session = runner.run(duration_sec=86400, max_simulations=240)
            self.assertEqual(session["session_id"], "existing")
            self.assertEqual(session["deadline"], 9999999999.0)
            self.assertEqual(session["status"], "SIMULATION_BUDGET_CAP")

    def test_factory_stop_does_not_mutate_finished_session(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            runner = AIFactoryRunner(FakeAgent())
            runner._save_session({
                "schema_version": 1, "session_id": "finished", "started_at": 1,
                "deadline": 2, "status": "DEADLINE", "rounds_completed": 1,
                "simulations_reserved": 1, "simulation_cap": 2,
            })
            self.assertIsNone(AIFactoryRunner.request_stop(tmp))
            self.assertFalse(AIFactoryRunner.read_session(tmp).get("stop_requested", False))

    def test_zero_duration_only_writes_one_session_envelope(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            session = AIFactoryRunner(FakeAgent()).run(duration_sec=0)
            self.assertEqual(session["status"], "STOPPED")
            self.assertTrue(os.path.exists(os.path.join(tmp, "factory_session.json")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "round_1.json")))

    def test_session_budget_blocks_before_discovery(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()
            candidates_per_round = 18

            def next_round_no(self):
                raise AssertionError("预算为零时不应进入 discovery")

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            session = AIFactoryRunner(FakeAgent()).run(
                duration_sec=10, max_simulations=0
            )
            self.assertEqual(session["status"], "SIMULATION_BUDGET_CAP")

    def test_one_round_reuses_canonical_proposals_inbox(self):
        class FakeAgent:
            def __init__(self, state_dir):
                self.state_dir = state_dir
                self.alpha_factory = AlphaFactory()
                self.candidates_per_round = 1
                self.calls = 0

            def next_round_no(self):
                return self.calls + 1

            def run_suggestion_round(self, round_no):
                return {
                    "round_no": round_no,
                    "epoch_label": "rb-test",
                    "research_space": {"id": "h", "statement": "test", "datasets": ["pv1"]},
                    "field_source": {"kind": "local_catalog", "snapshot_date": "20260906"},
                    "operator_reference": {"sha256": "s", "operators": ["rank"]},
                    "fields": [{
                        "id": "close", "description": "verified", "type": "MATRIX",
                        "semantic_status": "KNOWN", "dataset": "pv1",
                        "field_source": {"kind": "local_catalog", "snapshot_date": "20260906"},
                    }],
                }

            def run_proposals(self, path):
                self.calls += 1
                return {"round": self.calls, "verdicts": {"FAIL": 1}}

        with tempfile.TemporaryDirectory() as tmp:
            agent = FakeAgent(tmp)
            session = AIFactoryRunner(agent).run(
                duration_sec=10, max_rounds=1, idle_sleep_sec=1
            )
            self.assertEqual(session["rounds_completed"], 1)
            self.assertTrue(os.path.exists(os.path.join(tmp, "proposals.json")))
            self.assertEqual(len(os.listdir(tmp)), 2)


class TestReconcileHistory(unittest.TestCase):
    def test_empty_reconciliation_does_not_create_audit_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "reconcile_history.jsonl")
            self.assertEqual(append_unique_history(path, []), 0)
            self.assertFalse(os.path.exists(path))

    def test_collect_skips_unhashable_or_invalid_active_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            rows = [
                {"status": "RUNNING", "round": {"bad": 1},
                 "expression": "rank(bad)", "progress_url": "/sim/bad"},
                {"status": "RUNNING", "round": 1,
                 "expression": ["bad"], "progress_url": "/sim/bad2"},
                {"status": "RUNNING", "round": 1,
                 "expression": "rank(ok)", "progress_url": "/sim/ok"},
                {"status": "RUNNING", "round": 1,
                 "expression": "rank(no-url)", "progress_url": ["/sim/no"]},
            ]
            with open(path, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
            targets = collect(tmp)
            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0]["progress_url"], "/sim/ok")

    def test_repolling_same_state_does_not_grow_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "reconcile_history.jsonl")
            row = {"simulation_id": "sim-1", "outcome": "STALE", "alpha_id": None}
            self.assertEqual(append_unique_history(path, [row]), 1)
            self.assertEqual(append_unique_history(path, [dict(row, reconciled_at="later")]), 0)
            self.assertEqual(append_unique_history(path, [dict(row, outcome="COMPLETE", alpha_id="a1")]), 1)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(len(handle.readlines()), 2)

    def test_invalid_reconciliation_rows_do_not_create_a_shared_duplicate_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "reconcile_history.jsonl")
            self.assertEqual(
                append_unique_history(path, [{"reconciled_at": "noise"}]), 0
            )
            self.assertFalse(os.path.exists(path))

    def test_unhashable_reconciliation_identity_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "reconcile_history.jsonl")
            self.assertEqual(
                append_unique_history(path, [{"simulation_id": ["sim-1"], "outcome": "STALE"}]),
                0,
            )
            self.assertFalse(os.path.exists(path))

    def test_duplicate_only_batch_does_not_create_history_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "reconcile_history.jsonl")
            row = {"simulation_id": "sim-1", "outcome": "STALE", "alpha_id": None}
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
            before = os.path.getsize(path)
            self.assertEqual(append_unique_history(path, [dict(row, reconciled_at="later")]), 0)
            self.assertEqual(os.path.getsize(path), before)

    def test_history_append_refuses_active_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "reconcile_history.jsonl")
            lock_path = os.path.join(tmp, "run.lock")
            owner = acquire_os_owner_lock(lock_path)
            self.assertIsNotNone(owner)
            try:
                with self.assertRaises(RuntimeError):
                    append_unique_history(
                        path,
                        [{"simulation_id": "sim-1", "outcome": "STALE"}],
                    )
            finally:
                release_os_owner_lock(owner)
            self.assertFalse(os.path.exists(path))


class TestMemoryMaintenance(unittest.TestCase):
    def test_compact_only_dry_run_does_not_write_state_or_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ExperienceMemory(tmp)
            memory.seen_expressions = {"rank(close)"}
            memory.save()
            memory_path = os.path.join(tmp, "experience.json")
            with open(memory_path, "rb") as handle:
                before = handle.read()

            report = compact_only(tmp, apply=False)

            self.assertIn("dry-run, not saved", report)
            with open(memory_path, "rb") as handle:
                self.assertEqual(handle.read(), before)
            self.assertFalse(os.path.exists(os.path.join(tmp, "context.md")))

    def test_compact_only_apply_refreshes_canonical_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ExperienceMemory(tmp)
            memory.seen_expressions = {"rank(close)"}
            memory.save()

            report = compact_only(tmp, apply=True)

            self.assertIn("applied", report)
            self.assertTrue(os.path.exists(os.path.join(tmp, "context.md")))


class TestRoundArchivePath(unittest.TestCase):
    def test_archive_default_is_relative_to_state_project_not_process_cwd(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(root, "scripts", "archive_completed_rounds.py")
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, ".wqb_state")
            os.makedirs(state_dir)
            with open(os.path.join(state_dir, "round_1.json"), "w", encoding="utf-8") as handle:
                json.dump({"round_no": 1}, handle)
            result = subprocess.run(
                [sys.executable, script, "--state-dir", state_dir, "--keep", "0"],
                cwd=root, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn(os.path.join(tmp, "docs", "archive"), result.stdout)
            self.assertFalse(os.path.exists(os.path.join(root, "docs", "archive", "rounds", "round_1.json")))

    def test_archive_target_inside_live_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = os.path.join(tmp, ".wqb_state")
            os.makedirs(state_dir)
            with self.assertRaises(ValueError):
                ensure_archive_dir_safe(
                    Path(state_dir), Path(state_dir) / "nested-archive"
                )


class TestIntegrityAuditHelpers(unittest.TestCase):
    def test_jsonl_iterator_is_streaming_compatibility_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "derived.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"experiment_id": "a"}) + "\n")
                handle.write(json.dumps({"experiment_id": "b"}) + "\n")
            iterator = iter_jsonl(path)
            try:
                self.assertEqual(next(iterator)["experiment_id"], "a")
                self.assertEqual(next(iterator)["experiment_id"], "b")
            finally:
                iterator.close()

    def test_integrity_main_does_not_materialize_jsonl_ledgers(self):
        source = Path(__import__("scripts.validate_integrity", fromlist=["main"]).__file__).read_text(
            encoding="utf-8"
        )
        self.assertIn("for sim in iter_jsonl(simulations_path)", source)
        self.assertNotIn("simulations = load_jsonl(", source)
        self.assertNotIn("experiments = load_jsonl(", source)
        self.assertNotIn("lineages = load_jsonl(", source)
        self.assertIn("from wqb_agent.metrics import num", source)
        self.assertNotIn("garbage = load_json_object", source)

    def test_jsonl_loader_ignores_non_object_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "derived.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("[]\n")
                handle.write(json.dumps({"experiment_id": "ok"}) + "\n")
                handle.write("broken\n")
            self.assertEqual(load_jsonl(path), [{"experiment_id": "ok"}])

    def test_duplicate_groups_use_canonical_expression_identity(self):
        records = [
            {"experiment_id": "a", "expression": " Rank( x ) "},
            {"experiment_id": "b", "expression": "rank(x)"},
            {"experiment_id": "c", "expression": "rank(y)"},
        ]
        self.assertEqual(
            duplicate_groups(records, "expression", canonicalize=True),
            {"rank(x)": ["a", "b"]},
        )

    def test_report_snapshot_excludes_its_own_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "input.json")
            output = os.path.join(tmp, "FINAL.md")
            with open(source, "w", encoding="utf-8") as handle:
                handle.write("{}")
            source_time = os.path.getmtime(source)
            with open(output, "w", encoding="utf-8") as handle:
                handle.write("old report")
            os.utime(output, (source_time + 1000, source_time + 1000))
            self.assertEqual(complete_report_snapshot(tmp, "FINAL.md"), source_time)
            self.assertEqual(final_report_snapshot(tmp, "FINAL.md"), source_time)

    def test_validation_job_builder_skips_malformed_plan_rows(self):
        self.assertEqual(
            build_jobs({
                "plans": [
                    None,
                    {"experiment_id": "p", "perturbations": [
                        {"expression": "rank(a)", "label": "x"},
                        {"label": "missing-expression"},
                    ]},
                ]
            }),
            [{"parent_id": "p", "parent_round": None,
              "expression": "rank(a)", "label": "x", "type": None}],
        )


class TestTrajectoryIdStreaming(unittest.TestCase):
    def test_batch_append_uses_one_jsonl_open_for_multiple_new_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            trajectory = Trajectory(max_len=10, path=path)
            experiments = [
                Experiment(1, "h", "rank(a)", {}, ["a"]),
                Experiment(1, "h", "rank(b)", {}, ["b"]),
            ]
            with mock.patch.object(
                trajectory, "_append_jsonl_many", wraps=trajectory._append_jsonl_many
            ) as append:
                added = trajectory.add_many(experiments)
            self.assertEqual(len(added), 2)
            append.assert_called_once_with(experiments)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(len(handle.readlines()), 2)

    def test_live_result_persists_correlation_before_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = object.__new__(Agent)
            agent.trajectory = Trajectory(
                max_len=10, path=os.path.join(tmp, "trajectory.jsonl")
            )
            agent.reflector = Reflector(ExperienceMemory(tmp))
            agent.quality_policy = {}
            exp = Experiment(
                1, "h", "rank(a)", {}, ["a"], datasets=["pv1"]
            )
            exp.status = "DONE"
            exp.alpha_id = "alpha-1"
            exp.metrics = {
                "sharpe": 1.0, "fitness": 1.1, "turnover": 0.2,
                "returns": 0.1, "drawdown": 0.1, "margin": 0.001,
                "checks": [{"name": "SELF_CORRELATION", "pass": True,
                            "result": "PASS", "value": 0.1}],
                "passed": True,
            }
            with redirect_stdout(io.StringIO()):
                agent._record_live_result(exp)
            with open(os.path.join(tmp, "trajectory.jsonl"), encoding="utf-8") as handle:
                row = json.loads(handle.readline())
            self.assertEqual(row["self_correlation"]["status"], "PASS")
    def test_iter_ids_does_not_require_experiment_materialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trajectory.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"id": "a", "status": "DONE"}) + "\n")
                handle.write("not-json\n")
                handle.write(json.dumps({"id": "b", "status": "FAILED"}) + "\n")
            self.assertEqual(set(Trajectory(path=path).iter_ids()), {"a", "b"})


class TestLockBoundary(unittest.TestCase):
    def test_maintenance_lock_has_no_metadata_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "run.lock")
            handle = acquire_os_owner_lock(lock_path)
            self.assertIsNotNone(handle)
            try:
                self.assertFalse(os.path.exists(lock_path))
            finally:
                release_os_owner_lock(handle)

    def test_factory_status_does_not_require_client_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = os.path.join(tmp, "config.json")
            with open(config, "w", encoding="utf-8") as handle:
                json.dump({"agent": {"state_dir": tmp}}, handle)
            result = subprocess.run(
                [sys.executable, "main.py", "--config", config, "--factory-status"],
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("NOT_STARTED", result.stdout)

    def test_factory_status_view_drops_unknown_session_payload(self):
        class FakeAgent:
            state_dir = None
            alpha_factory = AlphaFactory()

        with tempfile.TemporaryDirectory() as tmp:
            FakeAgent.state_dir = tmp
            AIFactoryRunner(FakeAgent())._save_session({
                "schema_version": 1, "session_id": "s", "deadline": 100,
                "status": "RUNNING", "rounds_completed": 2,
                "simulations_reserved": 3, "simulation_cap": 10,
                "private_debug_dump": "must-not-leak",
            })
            view = AIFactoryRunner.status_view(tmp)
            self.assertNotIn("private_debug_dump", view)
            self.assertEqual(view["simulations_reserved"], 3)


class TestResearchLoopGuard(unittest.TestCase):
    @staticmethod
    def _done(expression, change_type="window_change", fitness=1.0):
        exp = Experiment(1, "h1", expression, {}, ["signal"])
        exp.status = "DONE"
        exp.lineage_id = "lineage-1"
        exp.change_type = change_type
        exp.template_family = "momentum"
        exp.metrics = {"fitness": fitness, "sharpe": fitness}
        return exp

    def test_same_change_type_stagnation_requires_a_new_variable(self):
        guard = ResearchLoopGuard([
            self._done("rank(ts_mean(signal, 20))", fitness=1.0),
            self._done("rank(ts_mean(signal, 60))", fitness=1.01),
        ])
        blocked, reason = guard.check({
            "expression": "rank(ts_mean(signal, 84))",
            "fields": ["signal"],
            "lineage_id": "lineage-1",
            "template_family": "momentum",
            "change_type": "window_change",
        })
        self.assertFalse(blocked)
        self.assertIn("切换", reason)
        allowed, reason = guard.check({
            "expression": "group_neutralize(rank(ts_mean(signal, 20)), subindustry)",
            "fields": ["signal"],
            "lineage_id": "lineage-1",
            "template_family": "momentum",
            "change_type": "neutralization",
        })
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_unresolved_experiment_does_not_close_a_lineage(self):
        pending = self._done("rank(ts_mean(signal, 20))")
        pending.status = "UNKNOWN"
        guard = ResearchLoopGuard([pending])
        allowed, reason = guard.check({
            "expression": "rank(ts_mean(signal, 60))",
            "fields": ["signal"],
            "lineage_id": "lineage-1",
            "change_type": "window_change",
        })
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_whitespace_equivalent_action_is_blocked(self):
        guard = ResearchLoopGuard([self._done("rank( signal )")])
        allowed, reason = guard.check({
            "expression": "rank(signal)",
            "fields": ["signal"],
            "lineage_id": "lineage-1",
            "template_family": "momentum",
            "change_type": "window_change",
        })
        self.assertFalse(allowed)
        self.assertIn("同一谱系", reason)


class TestTemplateStateRoundTrip(unittest.TestCase):
    def test_template_metadata_is_durable_without_changing_state_machine(self):
        exp = Experiment(1, "h", "rank(signal)", {}, ["signal"])
        exp.template_id = "rank_level"
        exp.template_family = "cross_sectional_rank"
        exp.template_stage_path = "L0:raw -> L1:cross_sectional -> L2:none"
        exp.template_ref = {"skeleton_fingerprint": "abc123"}
        exp.template_slots = {"p": "signal", "g": "subindustry"}
        restored = Experiment.from_dict(exp.to_dict())
        self.assertEqual(restored.status, "PENDING")
        self.assertEqual(restored.template_id, "rank_level")
        self.assertEqual(restored.template_slots["p"], "signal")


class TestRedundancy(unittest.TestCase):
    def test_field_similarity(self):
        self.assertEqual(field_similarity(["a", "b"], ["a", "b"]), 1.0)
        self.assertEqual(field_similarity(["a"], ["b"]), 0.0)
        self.assertEqual(field_similarity([], ["a"]), 0.0)

    def test_is_redundant_detects_same_family(self):
        rec = {
            "expression": "rank(ts_mean(returns, 5))",
            "fields_used": ["returns"],
        }
        pool = [
            {
                "expression": "rank(ts_mean(returns, 10))",
                "fields_used": ["returns"],
            }
        ]
        redundant, keeper = is_redundant(rec, pool)
        self.assertTrue(redundant)
        self.assertEqual(keeper["expression"], "rank(ts_mean(returns, 10))")

    def test_deduplicate_keeps_best(self):
        pool = [
            {"expression": "rank(a)", "fields_used": ["a"],
             "metrics": {"fitness": 1.0, "sharpe": 1.0}},
            {"expression": "rank(a) + 1", "fields_used": ["a"],
             "metrics": {"fitness": 2.0, "sharpe": 2.0}},
            {"expression": "rank(b)", "fields_used": ["b"],
             "metrics": {"fitness": 1.5, "sharpe": 1.5}},
        ]
        kept, dropped = deduplicate(pool)
        self.assertEqual(len(kept), 2)
        self.assertEqual(kept[0]["metrics"]["fitness"], 2.0)
        self.assertIn("rank(b)", [k["expression"] for k in kept])

    def test_redundancy_result_is_stable_for_incremental_prefix(self):
        """The incremental accepted-record path preserves prefix semantics."""
        accepted = []
        for expression, fields in (
            ("rank(a)", ["a"]),
            ("rank(ts_mean(b, 5))", ["b"]),
        ):
            record = {"expression": expression, "fields_used": fields}
            redundant, _ = is_redundant(record, accepted)
            self.assertFalse(redundant)
            accepted.append(record)
        redundant, keeper = is_redundant(
            {"expression": "rank(ts_mean(b, 10))", "fields_used": ["b"]},
            accepted,
        )
        self.assertTrue(redundant)
        self.assertEqual(keeper["expression"], "rank(ts_mean(b, 5))")


class TestMetricsTriState(unittest.TestCase):
    def test_non_finite_numbers_fail_closed(self):
        self.assertIsNone(num("nan"))
        self.assertIsNone(num("Infinity"))
        self.assertIsNone(_check_pass({"pass": float("nan")}))
        self.assertIsNone(checks_passed({"checks": [{"pass": float("inf")}]}))

    def test_unknown_check_result_stays_unresolved(self):
        self.assertIsNone(_check_pass({"result": "platform_pending_variant"}))

    def test_malformed_platform_shape_is_missing_evidence(self):
        from wqb_agent.metrics import check_health, extract_metrics

        metrics = extract_metrics({"is": ["bad"]})
        self.assertIsNone(metrics["sharpe"])
        self.assertEqual(metrics["checks"], [])
        self.assertIsNone(metrics["passed"])
        self.assertTrue(check_health({"is": ["bad"]})["ok"])

    def test_checks_passed_is_the_shared_tri_state_aggregator(self):
        self.assertIs(checks_passed({"checks": [{"result": "PASS"}]}), True)
        self.assertIsNone(checks_passed({"checks": [{"result": "PENDING"}]}))
        self.assertIsNone(checks_passed({"checks": []}))

    def test_result_string_checks_are_normalized(self):
        self.assertTrue(_check_pass({"name": "x", "result": "PASS"}))
        self.assertFalse(_check_pass({"name": "x", "result": "FAIL"}))

    def test_empty_checks_is_not_pass(self):
        m = _extract_metrics({"is": {"sharpe": 1.0, "checks": []}})
        self.assertIsNone(m["passed"])

    def test_all_checks_pass(self):
        m = _extract_metrics({
            "is": {
                "sharpe": 1.0,
                "checks": [{"name": "a", "pass": True}, {"name": "b", "pass": True}],
            }
        })
        self.assertIs(m["passed"], True)

    def test_any_check_fails(self):
        m = _extract_metrics({
            "is": {
                "sharpe": 1.0,
                "checks": [{"name": "a", "pass": True}, {"name": "b", "pass": False}],
            }
        })
        self.assertIs(m["passed"], False)

    def test_pending_check_is_validation_incomplete(self):
        m = _extract_metrics({
            "is": {
                "sharpe": 1.0,
                "checks": [
                    {"name": "LOW_SHARPE", "result": "PASS"},
                    {"name": "SELF_CORRELATION", "result": "PENDING"},
                ],
            }
        })
        self.assertIsNone(m["passed"])
        self.assertIsNone(m["checks"][1]["pass"])


class TestValidatorDecide(unittest.TestCase):
    def test_score_of_normalizes_legacy_string_metrics(self):
        self.assertEqual(score_of({"fitness": "1.25", "sharpe": "2.0"}), 1.25)
        self.assertEqual(score_of({"fitness": "0", "sharpe": "2.0"}), 2.0)

    def test_majority_pass_required(self):
        validator = HighSignalValidator(None, {}, min_valid_fitness=1.0,
                                        majority_ratio=0.6, min_pass=2)
        record = {"expression": "rank(a)", "metrics": {"fitness": 2.0, "sharpe": 2.0}}
        results = [
            {"expression": "p1", "score": 1.2, "checks_passed": True},
            {"expression": "p2", "score": 0.5, "checks_passed": True},
            {"expression": "p3", "score": 1.1, "checks_passed": True},
        ]
        stable, _ = validator.decide(record, results)
        self.assertTrue(stable)

    def test_insufficient_pass_fails(self):
        validator = HighSignalValidator(None, {}, min_valid_fitness=1.0,
                                        majority_ratio=0.6, min_pass=2)
        record = {"expression": "rank(a)", "metrics": {"fitness": 2.0, "sharpe": 2.0}}
        results = [
            {"expression": "p1", "score": 1.2, "checks_passed": True},
            {"expression": "p2", "score": 0.5, "checks_passed": False},
        ]
        stable, _ = validator.decide(record, results)
        self.assertFalse(stable)

    def test_validator_decide_handles_legacy_string_and_missing_scores(self):
        validator = HighSignalValidator(None, {}, min_valid_fitness=1.0,
                                        majority_ratio=0.5, min_pass=1)
        record = {"expression": "rank(a)", "metrics": {"fitness": 2.0}}
        results = [
            {"expression": "p1", "score": "1.2", "checks_passed": True},
            {"expression": "p2", "checks_passed": True},
        ]
        stable, detail = validator.decide(record, results)
        self.assertTrue(stable)
        self.assertEqual(detail[0]["score"], "1.2")

    def test_empty_results_fails(self):
        validator = HighSignalValidator(None, {})
        stable, _ = validator.decide({"expression": "x"}, [])
        self.assertFalse(stable)

    def test_validate_requires_outer_production_runner(self):
        validator = HighSignalValidator(None, {})
        stable, detail = validator.validate(
            {"expression": "rank(ts_mean(a, 10))", "fields_used": ["a"]}
        )
        self.assertFalse(stable)
        self.assertEqual(detail["reason"], "simulation_runner_required")

    def test_validator_perturbation_uses_actual_swapped_field(self):
        validator = HighSignalValidator(None, {})
        jobs, _ = validator.build_perturbation_jobs(
            {"expression": "rank(a)", "fields_used": ["a"]},
            alt_fields=[{"id": "b", "dataset": "pv1"}],
        )
        swapped = [job for job in jobs if "b" in job.expression]
        self.assertEqual(len(swapped), 1)
        self.assertEqual(swapped[0].fields_used, ["b"])


class TestHighSignalAuditMemory(unittest.TestCase):
    def test_audit_keeps_bounded_compact_evidence(self):
        record = audit_high_signal._compact_record({
            "experiment_id": "exp-1",
            "alpha_id": "alpha-1",
            "expression": "rank(signal)",
            "health": {"ok": True},
        })
        self.assertEqual(record["id"], "exp-1")
        self.assertEqual(record["alpha_id"], "alpha-1")
        self.assertNotIn("checks", record)

    def test_audit_has_stream_and_retention_cap(self):
        source = Path(audit_high_signal.__file__).read_text(encoding="utf-8")
        self.assertIn("bounded high-signal evidence", source)
        self.assertIn("second bounded", source)
        self.assertIn("TOP_AUDIT_LIMIT = 50", source)
        self.assertNotIn("sims = []", source)
        self.assertNotIn("high_signal = []", source)
        self.assertNotIn("expression_first = {}", source)


class TestStreamingLedgerAggregation(unittest.TestCase):
    def test_ledger_skips_unhashable_grouping_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "simulations_enhanced.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "hypothesis_id": ["bad"], "status": {"bad": True},
                    "round": [1], "dataset": {"bad": True},
                    "mutation_type": ["bad"], "expression": {"bad": True},
                }) + "\n")
            aggregate = _aggregate(path)
            self.assertEqual(aggregate["total"], 1)
            self.assertEqual(len(aggregate["datasets"]), 1)

    def test_ledger_aggregates_without_retaining_source_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "simulations_enhanced.jsonl")
            rows = [
                {"hypothesis_id": "h1", "status": "DONE", "round": 1,
                 "dataset": "pv1", "expression": " Rank(a) ",
                 "sharpe": "1.0", "fitness": "2.0",
                 "suspicious_high_signal": True},
                {"hypothesis_id": "h1", "status": "DONE", "round": 1,
                 "dataset": "pv1", "expression": "rank(a)",
                 "sharpe": 2.0, "fitness": 3.0,
                 "mutation_type": "window"},
                {"hypothesis_id": "h2", "status": "FAILED", "round": 2,
                 "dataset": "news", "failure_class": "SYNTAX"},
            ]
            with open(path, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
                handle.write("not-json\n")
            aggregate = _aggregate(path)
            self.assertEqual(aggregate["total"], 3)
            self.assertEqual(aggregate["valid_evidence"], 2)
            lineage = aggregate["lineage_stats"][0]
            self.assertEqual(lineage["hypothesis_id"], "h1")
            self.assertEqual(lineage["unique_expressions"], 1)
            self.assertEqual(lineage["duplicate_expressions"], 1)
            self.assertEqual(aggregate["research_failures"], 1)
            self.assertEqual(aggregate["datasets"]["pv1"]["done"], 2)

    def test_ledger_source_is_streamed_once(self):
        source = Path(__import__("scripts.generate_ledger", fromlist=["main"]).__file__).read_text(
            encoding="utf-8"
        )
        self.assertIn("for sim in iter_jsonl(path)", source)
        self.assertNotIn("sims = []", source)


class TestStreamingFinalReportSummary(unittest.TestCase):
    def test_final_report_does_not_turn_missing_metrics_into_zero(self):
        self.assertEqual(final_metric_text(None), "?")
        self.assertEqual(final_metric_text("1.25"), "1.25")
        self.assertEqual(final_metric_text("0", digits=3), "0.000")

    def test_final_report_summary_keeps_only_top_signal_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "simulations.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                for fitness in range(20):
                    handle.write(json.dumps({
                        "status": "DONE", "fitness": fitness,
                        "suspicious_high_signal": True,
                    }) + "\n")
            summary = summarize_simulations(path)
            self.assertEqual(summary["total"], 20)
            self.assertEqual(summary["high_signal"], 20)
            self.assertEqual(len(summary["top_high_signal"]), 10)
            self.assertEqual(summary["top_high_signal"][0]["fitness"], 19)

    def test_final_report_summary_normalizes_mixed_fitness_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "simulations.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "status": "DONE", "fitness": "2.5",
                    "suspicious_high_signal": True,
                }) + "\n")
                handle.write(json.dumps({
                    "status": "DONE", "fitness": "not-a-number",
                    "suspicious_high_signal": True,
                }) + "\n")
            summary = summarize_simulations(path)
            self.assertEqual(summary["top_high_signal"][0]["fitness"], "2.5")

    def test_final_report_source_does_not_materialize_sims(self):
        source = Path(__import__("scripts.generate_final_report", fromlist=["main"]).__file__).read_text(
            encoding="utf-8"
        )
        self.assertIn("summarize_simulations(", source)
        self.assertNotIn("sims = [json.loads", source)
        self.assertIn('failure_counts = simulation_summary["failure_counts"]', source)
        self.assertIn("from wqb_agent.metrics import num", source)


class TestStreamingCompleteReportSummary(unittest.TestCase):
    def test_heuristic_readers_never_fall_back_to_production_status(self):
        row = {"validation_status": "NOISE_TRAP"}
        self.assertIsNone(heuristic_status(row))
        self.assertIsNone(heuristic_sim_status(row))

    def test_complete_report_summary_handles_malformed_numeric_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "simulations_final.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "status": "DONE", "sharpe": "bad", "fitness": "2",
                    "hypothesis_id": "h1", "dataset": "pv1",
                    "lineage_depth": 0,
                }) + "\n")
                handle.write("broken\n")
            summary = summarize_complete_simulations(path)
            self.assertEqual(summary["total"], 1)
            self.assertEqual(summary["done"], 1)
            self.assertEqual(summary["sharpe_present"], 0)
            self.assertEqual(summary["datasets"]["pv1"]["total_sharpe"], 0.0)

    def test_complete_report_summary_skips_unhashable_grouping_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "simulations_final.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "status": {"bad": True}, "hypothesis_id": ["bad"],
                    "dataset": ["bad"],
                }) + "\n")
            summary = summarize_complete_simulations(path)
            self.assertEqual(summary["total"], 1)
            self.assertEqual(summary["hypotheses"], set())
            self.assertIn("unknown", summary["datasets"])

    def test_complete_report_source_does_not_materialize_sims(self):
        source = Path(__import__("scripts.generate_complete_report", fromlist=["main"]).__file__).read_text(
            encoding="utf-8"
        )
        self.assertIn("summarize_simulations(", source)
        self.assertNotIn("sims = []", source)


class TestHealthDiagnosticBoundary(unittest.TestCase):
    def test_standalone_health_diagnostic_reuses_pure_metric_helper(self):
        source = Path(__import__("scripts.check_health", fromlist=["check"]).__file__).read_text(
            encoding="utf-8"
        )
        self.assertIn("from wqb_agent.metrics import check_health as evaluate_health, num", source)
        self.assertNotIn("conc.get(\"result\")", source)


class TestStreamingSimulationEnhancement(unittest.TestCase):
    def test_health_adapter_uses_pure_metric_function_without_recursion(self):
        self.assertFalse(enhance_check_health([
            {"name": "CONCENTRATED_WEIGHT", "result": "FAIL"}
        ][0:1])["ok"])

    def test_enhancement_yields_rows_and_updates_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "simulations.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "status": "DONE", "sharpe": 4.0, "fitness": 9.0,
                    "expression": "rank(a)", "mutation_type": "baseline",
                    "checks": [],
                }) + "\n")
            counters = {
                "enhanced_count": 0, "validation_role_updates": 0,
                "health_checks_added": 0, "noise_traps_detected": 0,
                "role_counts": defaultdict(int),
                "suspicious_counts": defaultdict(int),
            }
            rows = list(enhance_rows(path, counters))
            self.assertEqual(len(rows), 1)
            self.assertEqual(counters["enhanced_count"], 1)
            self.assertTrue(rows[0]["suspicious_high_signal"])


class TestStreamingMemoryEvidence(unittest.TestCase):
    def test_memory_refactor_evidence_is_aggregated_as_a_stream(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "simulations_final.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"status": "DONE", "round": "3"}) + "\n")
                handle.write(json.dumps({
                    "status": "FAILED", "round": 4,
                    "heuristic_status": "SUSPICIOUS",
                }) + "\n")
            self.assertEqual(build_evidence(tmp), {
                "total": 2, "done": 1, "noise": 1, "source_round": 4,
            })


class TestStreamingHighSignalValidation(unittest.TestCase):
    def test_validation_report_formatters_handle_legacy_and_missing_values(self):
        self.assertEqual(_metric_text("2.5"), "2.50")
        self.assertEqual(_metric_text(None), "?")
        self.assertEqual(_short_text(None), "?")
        self.assertEqual(_short_text("a\nb", 8), "a b")

    def test_heuristic_validator_degrades_malformed_optional_shapes(self):
        result = heuristic_validate({
            "expression": 123,
            "health": "bad",
            "sharpe": "1.0",
            "fitness": "0.8",
            "turnover": "0.2",
        })
        self.assertEqual(result["status"], "PROMISING")
        self.assertEqual(generate_perturbations(123, "field"), [])

    def test_validation_rewrites_source_in_one_stream_by_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "simulations.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"experiment_id": "e1", "status": "DONE"}) + "\n")
                handle.write(json.dumps({"experiment_id": "e2", "status": "DONE"}) + "\n")
            result = list(apply_validation_rows(path, {
                "e2": {
                    "heuristic_status": "SUSPICIOUS", "confidence": 0.7,
                    "noise_indicators": [], "recommendation": "review",
                    "perturbations": [],
                }
            }))
            self.assertNotIn("heuristic_validation_status", result[0])
            self.assertEqual(result[1]["heuristic_validation_status"], "SUSPICIOUS")

    def test_validation_source_has_no_full_sims_list(self):
        source = Path(__import__("scripts.validate_high_signal", fromlist=["main"]).__file__).read_text(
            encoding="utf-8"
        )
        self.assertIn("apply_validation_rows", source)
        self.assertNotIn("sims = []", source)
        self.assertNotIn("high_signal = [", source)

    def test_validation_report_retention_is_bounded(self):
        retained = []
        for index in range(MAX_VALIDATION_REPORT_RESULTS + 40):
            _retain_validation_result(retained, {
                "heuristic_status": "PROMISING",
                "confidence": 0.5,
                "id": index,
            })
        self.assertEqual(len(retained), MAX_VALIDATION_REPORT_RESULTS)

    def test_integrity_text_prefix_handles_non_string_memory_values(self):
        self.assertEqual(_prefix(12345, 3), "123")
        self.assertEqual(_prefix(None, 3), "")


class TestStreamingLedgerQuery(unittest.TestCase):
    def test_top_query_keeps_only_requested_rows(self):
        rows = ({"status": "DONE", "fitness": value} for value in range(100))
        top = query_top_performers(rows, n=3)
        self.assertEqual([row["fitness"] for row in top], [99, 98, 97])

    def test_top_query_normalizes_legacy_string_scores_and_skips_missing(self):
        rows = [
            {"status": "DONE", "fitness": "2.5"},
            {"status": "DONE", "fitness": None},
            {"status": "DONE", "fitness": "bad"},
            {"status": "DONE", "fitness": "1.5"},
        ]
        self.assertEqual(
            [row["fitness"] for row in query_top_performers(rows, n=2)],
            ["2.5", "1.5"],
        )

    def test_round_query_accepts_legacy_string_rounds(self):
        self.assertEqual(
            query_by_round([{"round": "7"}, {"round": 8}], 7),
            [{"round": "7"}],
        )

    def test_integrity_round_key_matches_numeric_and_string_values(self):
        self.assertEqual(round_key("7"), round_key(7))

    def test_bulk_analysis_accepts_result_only_self_correlation_checks(self):
        cache = {
            "a1": {"checks": [{"name": "SELF_CORRELATION", "result": "PASS", "value": "0.2"}]},
            "a2": {"checks": [{"name": "SELF_CORRELATION", "result": "FAIL", "value": 0.1}]},
        }
        self.assertEqual(pass_correlation_ids(cache), {"a1": 0.2})

    def test_query_reader_is_shared_streaming_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "simulations_final.jsonl"), "w", encoding="utf-8") as handle:
                handle.write("broken\n" + json.dumps({"id": "ok"}) + "\n")
            self.assertEqual(list(iter_simulations(tmp)), [{"id": "ok"}])


class TestStreamingSchemaEnhancement(unittest.TestCase):
    def test_schema_metadata_writer_streams_source_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "validated.jsonl")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"experiment_id": "e1"}) + "\n")
            rows = list(enhanced_rows(path, {"e1": None}, {"e1": ["e2"]}, {"e1": 0}))
            self.assertEqual(rows[0]["validation_children"], ["e2"])
            self.assertEqual(rows[0]["lineage_depth"], 0)

    def test_schema_source_does_not_create_second_full_list(self):
        source = Path(__import__("scripts.enhance_schema", fromlist=["main"]).__file__).read_text(
            encoding="utf-8"
        )
        self.assertIn("enhanced_rows(", source)
        self.assertNotIn("sims = []", source)


class TestCurateNormalization(unittest.TestCase):
    def test_legacy_metric_strings_and_bad_timestamp_are_safe(self):
        record = normalize_simulation({
            "id": "e1",
            "round": 1,
            "hypothesis_id": "h1",
            "status": "DONE",
            "created_at": "not-a-timestamp",
            "metrics": {
                "sharpe": "1.2", "fitness": "0.8", "turnover": "0.2",
                "returns": "0.1", "drawdown": "0.05", "margin": "0.01",
                "checks": [],
            },
            "datasets": ["pv1"],
        }, "trajectory.jsonl", 1)
        self.assertEqual(record["sharpe"], 1.2)
        self.assertEqual(record["fitness"], 0.8)
        self.assertEqual(normalize_round("7"), 7)
        self.assertIsNone(record["created_at"])

    def test_malformed_optional_shapes_fail_closed_during_normalization(self):
        record = normalize_simulation({
            "id": "e2", "hypothesis_id": 42, "mutation": 7,
            "rationale": 9, "metrics": [], "settings": "bad",
            "fields_used": "field", "datasets": "pv1",
            "expression": 123, "round": "2",
        }, "trajectory.jsonl", 2)
        self.assertEqual(record["hypothesis_id"], "42")
        self.assertEqual(record["round"], 2)
        self.assertEqual(record["fields_used"], [])
        self.assertIsNone(record["dataset"])
        self.assertEqual(record["expression"], "123")


class TestCurateLineageEfficiency(unittest.TestCase):
    def test_lineage_links_previous_experiment_without_quadratic_scan(self):
        simulations = [
            {
                "experiment_id": "e1", "hypothesis_id": "h1",
                "mutation_type": "baseline", "expression": "rank(close)",
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "experiment_id": "e2", "hypothesis_id": "h1",
                "mutation_type": "window-tweak", "expression": "ts_mean(close, 5)",
                "created_at": "2026-01-01T00:01:00Z",
            },
        ]
        lineages = build_lineages(simulations)
        self.assertEqual(len(lineages), 1)
        self.assertEqual(lineages[0]["experiment_count"], 2)
        self.assertEqual(lineages[0]["depth"], 1)
        self.assertEqual(lineages[0]["parent_expression"], "rank(close)")
        self.assertEqual(lineages[0]["child_expression"], "ts_mean(close, 5)")

        source = Path("scripts/curate_data.py").read_text(encoding="utf-8")
        self.assertNotIn("sims_sorted.index(", source)
        self.assertIn("children_by_parent", source)

    def test_high_signal_parent_check_uses_bounded_index(self):
        simulations = [
            {"experiment_id": "e1", "status": "DONE", "sharpe": 4.0,
             "fitness": 1.0, "parent_id": None},
            {"experiment_id": "e2", "status": "FAILED", "sharpe": None,
             "fitness": None, "parent_id": "e1"},
        ]
        checks = run_integrity_checks(simulations, {})
        self.assertEqual(checks["suspicious_high_unverified"], [])


class TestCorrelationThresholdSource(unittest.TestCase):
    def test_manual_diagnostic_reads_quality_threshold_from_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"agent": {"quality": {"max_self_correlation": 0.37}}}, handle)
            self.assertEqual(configured_threshold(path), 0.37)

    def test_invalid_threshold_config_falls_back_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("not-json")
            self.assertEqual(configured_threshold(path), 0.5)


if __name__ == "__main__":
    unittest.main()
