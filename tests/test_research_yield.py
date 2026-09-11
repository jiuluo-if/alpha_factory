"""Contract tests for derived mechanism-family research yield.

ResearchYield is derived control-plane research evidence: it aggregates
existing SearchOutcome / experiment / optimizer handoff / incremental
evidence per semantic mechanism family.  These tests cover conversions with
explicit denominators, evidence-quality separation, infra-vs-research
failure separation, identity reuse, the five family outcomes, bounded
continuation, and the read-only campaign replay classification rules.
"""

import ast
import os
import unittest
from pathlib import Path

from wqb_agent.research_yield import (
    BLOCKED,
    EXHAUSTED,
    FINAL_EVIDENCE,
    INCONCLUSIVE,
    INFRASTRUCTURE_BLOCKED,
    LEGACY_APPROXIMATE,
    LOW_INFORMATION,
    LOW_RESEARCH_YIELD,
    MECHANISM_FAMILY_EXHAUSTED,
    NO_INCREMENTAL_CHILD_EVIDENCE,
    PROMISING,
    PROVISIONAL_EVIDENCE,
    build_research_yield,
    child_generation_bound,
    continuation_decision,
    conversion,
    evidence_quality,
    failure_class,
    family_state,
    incremental_stop_reason,
    merge_evidence,
    research_outcome_summary,
    session_control_metadata,
)

PACKAGE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wqb_agent"
)


def evidence(identity, *, family="m:a:b", status="DONE", quality=None,
             lineage=None, child=False, incremental=None, admission=None,
             feasible=False, expression=None, round_no=1, error=None,
             reason_code=None):
    row = {
        "id": f"exp-{identity}",
        "expression": expression or f"rank(field_{identity})",
        "template_family": "template_a",
        "semantic_mechanism_family": family,
        "status": status,
        "round": round_no,
    }
    if lineage is not None:
        row["lineage_id"] = lineage
    if child:
        row["parent_expression"] = f"rank(field_parent_{identity})"
        row["experiment_stage"] = "EXPLOIT"
    if incremental is not None:
        row["incremental_decision"] = incremental
    if admission is not None:
        row["semantic_admission"] = admission
    if feasible:
        row["feasible"] = True
    if error is not None:
        row["error"] = error
    if reason_code is not None:
        row["reason_code"] = reason_code
    if quality == "FINAL":
        row["outcome_kind"] = "FINAL"
        row["reward_quality"] = "FINAL_EVIDENCE"
    elif quality == "PROVISIONAL":
        row["outcome_kind"] = "PROVISIONAL"
        row["reward_quality"] = "PROVISIONAL_EVIDENCE"
    elif quality == "LEGACY":
        row["outcome_kind"] = "LEGACY"
        row["reward_quality"] = "LEGACY_APPROXIMATE"
    return row


def rejected_eligibility(identities, *, reasons=("PARENT_INCREMENTAL_EVIDENCE_INSUFFICIENT",)):
    return {
        f"exp-{identity}": {"eligible": False, "reasons": list(reasons)}
        for identity in identities
    }


class TestConversion(unittest.TestCase):
    def test_zero_denominator_is_none_not_zero(self):
        self.assertEqual(conversion(0, 0), {"value": None, "reason": "NO_DENOMINATOR"})
        self.assertEqual(conversion(3, 0), {"value": None, "reason": "NO_DENOMINATOR"})

    def test_occurred_but_zero_percent_is_explicit_zero(self):
        self.assertEqual(conversion(0, 10), {"value": 0.0, "reason": "OK"})

    def test_unavailable_denominator_is_none(self):
        self.assertEqual(
            conversion(5, None), {"value": None, "reason": "DENOMINATOR_UNAVAILABLE"}
        )

    def test_funnel_conversions_use_explicit_denominators(self):
        records = []
        for index in range(20):
            records.append(evidence(f"p-{index}", admission="ALLOW", status=None))
        for index in range(60):
            records.append(evidence(f"b-{index}", admission="ALLOW"))
        for index in range(4):
            records.append(evidence(
                f"c-{index}", admission="ALLOW", child=True,
                incremental="PASS" if index < 2 else "FAIL",
            ))
        eligibility_map = {}
        for index in range(60):
            if index < 12:
                eligibility_map[f"exp-b-{index}"] = {"eligible": True, "reasons": []}
            else:
                eligibility_map[f"exp-b-{index}"] = {
                    "eligible": False,
                    "reasons": ["PARENT_INCREMENTAL_EVIDENCE_INSUFFICIENT"],
                }
        funnel = build_research_yield(records, eligibility=eligibility_map)["m:a:b"]
        self.assertEqual(funnel.assembled_proposals, 84)
        self.assertEqual(funnel.simulations_dispatched, 64)
        self.assertEqual(funnel.simulations_done, 64)
        self.assertEqual(funnel.optimizer_eligible_parents, 12)
        self.assertEqual(funnel.children_generated, 4)
        self.assertEqual(funnel.children_done, 4)
        self.assertEqual(funnel.incremental_pass, 2)
        conversions = funnel.conversions()
        self.assertAlmostEqual(conversions["proposal_to_simulation"]["value"], 64 / 84)
        self.assertEqual(conversions["simulation_to_done"]["value"], 1.0)
        self.assertAlmostEqual(conversions["done_to_optimizer_parent"]["value"], 12 / 64)
        self.assertAlmostEqual(conversions["parent_to_child"]["value"], 4 / 12)
        self.assertEqual(conversions["child_to_incremental"]["value"], 0.5)

    def test_unavailable_optimizer_stage_reports_unavailable_conversion(self):
        records = [evidence(f"b-{index}", admission="ALLOW") for index in range(60)]
        funnel = build_research_yield(records)["m:a:b"]
        conversions = funnel.conversions()
        self.assertEqual(
            conversions["done_to_optimizer_parent"],
            {"value": None, "reason": "DENOMINATOR_UNAVAILABLE"},
        )
        self.assertEqual(
            conversions["parent_to_child"],
            {"value": None, "reason": "DENOMINATOR_UNAVAILABLE"},
        )

    def test_no_done_means_no_optimizer_conversion(self):
        records = [evidence(f"p-{index}", status=None) for index in range(10)]
        funnel = build_research_yield(records, eligibility={})["m:a:b"]
        conversions = funnel.conversions()
        self.assertEqual(conversions["done_to_optimizer_parent"]["reason"], "NO_DENOMINATOR")
        self.assertIsNone(conversions["done_to_optimizer_parent"]["value"])
        self.assertEqual(conversions["child_to_incremental"]["reason"], "NO_DENOMINATOR")

class TestEvidenceQuality(unittest.TestCase):
    def test_final_evidence_can_drive_a_decision(self):
        records = [evidence(index, quality="FINAL") for index in range(60)]
        eligibility_map = {
            f"exp-{index}": {"eligible": index == 0, "reasons": []}
            for index in range(60)
        }
        funnel = build_research_yield(records, eligibility=eligibility_map)["m:a:b"]
        self.assertEqual(funnel.final_evidence_count, 60)
        self.assertEqual(funnel.optimizer_eligible_parents, 1)
        self.assertEqual(family_state(funnel)["state"], PROMISING)

    def test_legacy_only_evidence_caps_at_inconclusive(self):
        records = [evidence(index, quality="LEGACY") for index in range(60)]
        funnel = build_research_yield(
            records, eligibility=rejected_eligibility(range(60))
        )["m:a:b"]
        decision = family_state(funnel)
        self.assertEqual(decision["state"], INCONCLUSIVE)
        self.assertIn("LEGACY_ONLY_EVIDENCE", decision["reasons"])
        self.assertNotEqual(continuation_decision(decision["state"])["decision"], "STOP")

    def test_provisional_only_evidence_cannot_hard_stop(self):
        records = [evidence(index, quality="PROVISIONAL") for index in range(60)]
        funnel = build_research_yield(
            records, eligibility=rejected_eligibility(range(60))
        )["m:a:b"]
        decision = family_state(funnel)
        self.assertEqual(decision["state"], INCONCLUSIVE)
        self.assertIn("FINAL_EVIDENCE_INSUFFICIENT", decision["reasons"])
        self.assertEqual(continuation_decision(decision["state"])["decision"], "OBSERVE")

    def test_infrastructure_failure_is_not_research_failure(self):
        records = [
            evidence("a", status="FAILED", reason_code="AUTH"),
            evidence("b", status="FAILED", error="rate limit"),
            evidence("c", status="FAILED", reason_code="INVALID_EXPRESSION"),
            evidence("d", status="SUBMIT_UNKNOWN"),
            evidence("e", status="SKIPPED_STALE"),
        ]
        funnel = build_research_yield(records)["m:a:b"]
        self.assertEqual(funnel.infrastructure_failure_count, 4)
        self.assertEqual(funnel.research_failure_count, 1)
        self.assertEqual(funnel.simulations_failed, 3)

    def test_unknown_evidence_never_becomes_low_information(self):
        records = [evidence(index, status="UNKNOWN") for index in range(60)]
        funnel = build_research_yield(records)["m:a:b"]
        self.assertEqual(funnel.infrastructure_failure_count, 60)
        self.assertEqual(family_state(funnel)["state"], BLOCKED)

    def test_quality_bucket_helpers_match_searchoutcome_semantics(self):
        self.assertEqual(evidence_quality(evidence("x", quality="FINAL")), FINAL_EVIDENCE)
        self.assertEqual(
            evidence_quality(evidence("x", quality="PROVISIONAL")), PROVISIONAL_EVIDENCE
        )
        self.assertEqual(evidence_quality(evidence("x", quality="LEGACY")), LEGACY_APPROXIMATE)
        self.assertIsNone(evidence_quality(evidence("x")))
        self.assertEqual(failure_class(evidence("x", status="SUBMIT_UNKNOWN")), "INFRA")
        self.assertEqual(
            failure_class(evidence("x", status="FAILED", reason_code="RATE_LIMIT")), "INFRA"
        )
        self.assertEqual(
            failure_class(evidence("x", status="FAILED", reason_code="REJECTED")), "RESEARCH"
        )


class TestIdentity(unittest.TestCase):
    def test_same_semantic_mechanism_different_expressions_form_one_family(self):
        records = [
            evidence("a", family="vol:level:signed", expression="rank(ts_zscore(vol, 20))"),
            evidence("b", family="vol:level:signed", expression="rank(ts_zscore(vol, 60))"),
            evidence("c", family="vol:level:signed", expression="reverse(rank(ts_zscore(vol, 20)))"),
        ]
        funnels = build_research_yield(records)
        self.assertEqual(set(funnels), {"vol:level:signed"})
        self.assertEqual(funnels["vol:level:signed"].assembled_proposals, 3)

    def test_parameter_variants_stay_in_one_family(self):
        records = [
            evidence("a", family="m:level:signed", expression="rank(ts_zscore(ts_delta(f, 5), 20))"),
            evidence("b", family="m:level:signed", expression="rank(ts_zscore(ts_delta(f, 20), 60))"),
        ]
        self.assertEqual(len(build_research_yield(records)), 1)

    def test_same_parent_children_count_as_one_independent_lineage(self):
        records = [
            evidence("p", lineage="L1"),
            evidence("c1", lineage="L1", child=True),
            evidence("c2", lineage="L1", child=True),
            evidence("c3", lineage="L1", child=True),
        ]
        funnel = build_research_yield(records)["m:a:b"]
        self.assertEqual(funnel.independent_lineage_count, 1)

    def test_real_independent_mechanisms_stay_separate(self):
        records = [
            evidence("a", family="vol:dispersion:signed"),
            evidence("b", family="earnings:level:slow_moving"),
        ]
        funnels = build_research_yield(records)
        self.assertEqual(
            set(funnels), {"vol:dispersion:signed", "earnings:level:slow_moving"}
        )


class TestState(unittest.TestCase):
    def test_below_minimum_sample_is_inconclusive(self):
        records = [evidence(index, quality="FINAL") for index in range(5)]
        decision = family_state(build_research_yield(records)["m:a:b"])
        self.assertEqual(decision["state"], INCONCLUSIVE)
        self.assertIn("SAMPLE_INSUFFICIENT", decision["reasons"])

    def test_enough_final_done_with_zero_downstream_is_low_information(self):
        records = [evidence(index, quality="FINAL") for index in range(100)]
        funnel = build_research_yield(
            records, eligibility=rejected_eligibility(range(100))
        )["m:a:b"]
        decision = family_state(funnel, novelty_flat=True)
        self.assertEqual(decision["state"], LOW_INFORMATION)
        self.assertIn("NOVELTY_FLAT", decision["reasons"])

    def test_incremental_pass_is_promising(self):
        # PROMISING still requires the minimum sample guard: enough FINAL
        # evidence plus real downstream progress (eligible parent + PASS child).
        records = [evidence(index, quality="FINAL") for index in range(40)]
        records.append(evidence("p", quality="FINAL"))
        records.append(evidence("c", child=True, incremental="PASS", lineage="L1"))
        eligibility = rejected_eligibility(range(40))
        eligibility["exp-p"] = True
        funnel = build_research_yield(records, eligibility=eligibility)["m:a:b"]
        self.assertEqual(funnel.final_evidence_count, 41)
        self.assertEqual(funnel.optimizer_eligible_parents, 1)
        self.assertEqual(funnel.incremental_pass, 1)
        self.assertEqual(family_state(funnel)["state"], PROMISING)

    def test_infra_dominated_family_is_blocked(self):
        records = [evidence(f"d-{index}") for index in range(50)]
        records += [evidence(f"f-{index}", status="FAILED", reason_code="TIMEOUT")
                    for index in range(50)]
        funnel = build_research_yield(records)["m:a:b"]
        decision = family_state(funnel)
        self.assertEqual(decision["state"], BLOCKED)
        self.assertIn(INFRASTRUCTURE_BLOCKED, decision["reasons"])

    def test_semantic_route_exhausted_is_exhausted(self):
        records = [evidence(index, quality="FINAL") for index in range(60)]
        funnel = build_research_yield(records)["m:a:b"]
        decision = family_state(funnel, exhaustion_evidence=["m:a:b"])
        self.assertEqual(decision["state"], EXHAUSTED)
        self.assertEqual(decision["stop_reason"], MECHANISM_FAMILY_EXHAUSTED)


class TestContinuation(unittest.TestCase):
    def test_low_information_maps_to_bounded_reroute(self):
        decision = continuation_decision(LOW_INFORMATION)
        self.assertEqual(decision["decision"], "REROUTE")
        self.assertIsNone(decision["stop_reason"])
        self.assertTrue(decision["consumes_quota"])

    def test_repeated_low_information_stops_low_research_yield(self):
        decision = continuation_decision(
            LOW_INFORMATION, no_gain_count=2, max_no_gain_attempts=2
        )
        self.assertEqual(decision["decision"], "STOP")
        self.assertEqual(decision["stop_reason"], LOW_RESEARCH_YIELD)
        self.assertFalse(decision["consumes_quota"])

    def test_one_bad_simulation_cannot_stop(self):
        records = [evidence(index, quality="FINAL") for index in range(40)]
        records.append(
            evidence("bad", status="FAILED", reason_code="INVALID_EXPRESSION")
        )
        funnel = build_research_yield(
            records, eligibility=rejected_eligibility(range(40))
        )["m:a:b"]
        decision = family_state(funnel)
        self.assertEqual(decision["state"], LOW_INFORMATION)
        self.assertIsNone(decision["stop_reason"])
        self.assertEqual(
            continuation_decision(decision["state"])["decision"], "REROUTE"
        )

    def test_blocked_does_not_consume_quota(self):
        decision = continuation_decision(BLOCKED)
        self.assertEqual(decision["decision"], "WAIT")
        self.assertEqual(decision["stop_reason"], INFRASTRUCTURE_BLOCKED)
        self.assertFalse(decision["consumes_quota"])


class TestSafety(unittest.TestCase):
    def _module_path(self):
        return Path(PACKAGE_ROOT) / "research_yield.py"

    def test_submit_unknown_never_becomes_done_or_promising(self):
        records = [evidence(index, status="SUBMIT_UNKNOWN") for index in range(5)]
        funnel = build_research_yield(records)["m:a:b"]
        self.assertEqual(funnel.simulations_done, 0)
        self.assertEqual(funnel.infrastructure_failure_count, 5)
        self.assertEqual(funnel.research_failure_count, 0)
        decision = family_state(funnel)
        self.assertEqual(decision["state"], BLOCKED)
        self.assertEqual(decision["stop_reason"], INFRASTRUCTURE_BLOCKED)

    def test_no_second_simulation_path(self):
        source = self._module_path().read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        blocked = {
            "wqb_agent.client",
            "wqb_agent.simulator",
            "wqb_agent.state",
            "wqb_agent.alpha_feed_workflow",
            "wqb_agent.proposal_execution",
            "wqb_agent.agent",
        }
        self.assertTrue(imported.isdisjoint(blocked))
        self.assertNotIn("submit_simulation(", source)
        self.assertNotIn("run_proposals", source)
        self.assertNotIn("settle_search_outcome(", source)

    def test_no_metrics_reconstruction_in_funnel_payload(self):
        records = [evidence(index, quality="FINAL") for index in range(5)]
        funnel = build_research_yield(records)["m:a:b"]
        payload = funnel.as_dict()
        banned = ("sharpe", "turnover", "returns", "drawdown", "checks", "fitness")
        for key in payload:
            lowered = key.lower()
            for token in banned:
                self.assertNotIn(token, lowered)

    def test_alpha_feed_metadata_cannot_become_yield_evidence(self):
        feed_rows = [
            {"id": f"alpha-{i}", "status": "DONE", "updated_at": "2026-09-11T00:00:00Z"}
            for i in range(10)
        ]
        funnels = build_research_yield(feed_rows)
        self.assertEqual(funnels, {})
        merged = merge_evidence(feed_rows)
        # metadata survives merge but is filtered at funnel construction.
        self.assertEqual(len(merged), 10)

    def test_legacy_metrics_snapshot_without_expression_is_ignored(self):
        rows = [
            {"id": f"r{i}", "status": "DONE", "sharpe": 1.2, "turnover": 0.3}
            for i in range(10)
        ]
        self.assertEqual(build_research_yield(rows), {})


class TestMergeEvidence(unittest.TestCase):
    def test_merge_joins_proposal_with_checkpoint_by_expression(self):
        proposal = {
            "id": "p-1",
            "round": 13,
            "expression": "rank(ts_zscore(f1, 20))",
            "semantic_mechanism_key": "vol:level:signed",
            "template_family": "t",
        }
        checkpoint = {
            "id": "e-1",
            "proposal_id": "p-1",
            "round": 13,
            "expression": "rank(ts_zscore(f1, 20))",
            "status": "DONE",
            "progress_url": "https://example.invalid/progress",
        }
        merged = merge_evidence([proposal], [checkpoint])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["status"], "DONE")
        self.assertEqual(merged[0]["semantic_mechanism_key"], "vol:level:signed")
        self.assertEqual(merged[0]["progress_url"], "https://example.invalid/progress")

    def test_shared_lineage_does_not_collapse_distinct_expressions(self):
        # Real campaign data: many distinct experiments share one lineage_id.
        # Lineage is an aggregation axis, not a merge identity key.
        records = [
            {
                "id": f"r{i}",
                "round": 13,
                "lineage_id": "L1",
                "expression": f"rank(f{i})",
                "template_family": "t",
                "status": "DONE",
            }
            for i in range(3)
        ]
        merged = merge_evidence(records)
        self.assertEqual(len(merged), 3)
        funnels = build_research_yield(
            records, mechanism_key_fn=lambda _row: "m:a:b"
        )
        self.assertEqual(funnels["m:a:b"].assembled_proposals, 3)
        self.assertEqual(funnels["m:a:b"].independent_lineage_count, 1)


class TestIncrementalStopReason(unittest.TestCase):
    def _funnel(self, rows):
        return build_research_yield(rows)["m:a:b"]

    def test_no_child_opportunity_never_stops(self):
        funnel = self._funnel([evidence("a", status="DONE")])
        self.assertIsNone(incremental_stop_reason(funnel))

    def test_child_not_done_is_not_settled(self):
        child = evidence("c", child=True, incremental="PASS", lineage="L1", status="RUNNING")
        funnel = self._funnel([evidence("p", status="DONE"), child])
        self.assertIsNone(incremental_stop_reason(funnel))

    def test_done_child_without_settled_verdict_is_not_settled(self):
        child = evidence("c", child=True, lineage="L1", status="DONE")
        funnel = self._funnel([evidence("p", status="DONE"), child])
        self.assertIsNone(incremental_stop_reason(funnel))

    def test_settled_pass_is_not_a_stop(self):
        child = evidence("c", child=True, incremental="PASS", lineage="L1", status="DONE")
        funnel = self._funnel([evidence("p", status="DONE"), child])
        self.assertIsNone(incremental_stop_reason(funnel))

    def test_settled_children_without_pass_is_no_incremental_child_evidence(self):
        child = evidence("c", child=True, incremental="FAIL", lineage="L1", status="DONE")
        funnel = self._funnel([evidence("p", status="DONE"), child])
        self.assertEqual(
            incremental_stop_reason(funnel), NO_INCREMENTAL_CHILD_EVIDENCE
        )


class TestChildGenerationBound(unittest.TestCase):
    """One bounded generation when incremental value cannot be verified."""

    def _funnel(self, rows):
        return build_research_yield(rows)["m:a:b"]

    def test_no_completed_child_does_not_bound_the_chain(self):
        funnel = self._funnel([evidence("p", status="DONE")])
        bound = child_generation_bound(funnel)
        self.assertTrue(bound["allowed"])
        self.assertIsNone(bound["stop_reason"])
        self.assertEqual(bound["max_generations"], 1)

    def test_verified_incremental_pass_keeps_the_chain_open(self):
        child = evidence("c", child=True, incremental="PASS", lineage="L1", status="DONE")
        funnel = self._funnel([evidence("p", status="DONE"), child])
        bound = child_generation_bound(funnel)
        self.assertTrue(bound["allowed"])
        self.assertIsNone(bound["stop_reason"])

    def test_unavailable_incremental_evidence_blocks_the_next_generation(self):
        child = evidence("c", child=True, lineage="L1", status="DONE")
        funnel = self._funnel([evidence("p", status="DONE"), child])
        bound = child_generation_bound(funnel)
        self.assertFalse(bound["allowed"])
        self.assertEqual(bound["state"], BLOCKED)
        self.assertEqual(bound["stop_reason"], NO_INCREMENTAL_CHILD_EVIDENCE)
        self.assertEqual(bound["generations"], 1)

    def test_settled_children_without_pass_close_the_chain(self):
        child = evidence("c", child=True, incremental="FAIL", lineage="L1", status="DONE")
        funnel = self._funnel([evidence("p", status="DONE"), child])
        bound = child_generation_bound(funnel)
        self.assertFalse(bound["allowed"])
        self.assertEqual(bound["state"], INCONCLUSIVE)
        self.assertEqual(bound["stop_reason"], NO_INCREMENTAL_CHILD_EVIDENCE)

    def test_explicit_bound_keeps_the_first_generation_available(self):
        child = evidence("c", child=True, lineage="L1", status="DONE")
        funnel = self._funnel([evidence("p", status="DONE"), child])
        bound = child_generation_bound(funnel, max_generations=2)
        self.assertTrue(bound["allowed"])
        self.assertEqual(bound["max_generations"], 2)


class TestControlMetadata(unittest.TestCase):
    def test_session_control_metadata_is_minimal_and_metrics_free(self):
        records = [evidence(i, quality="FINAL") for i in range(45)]
        funnels = build_research_yield(
            records, eligibility=rejected_eligibility(range(45))
        )
        rows = session_control_metadata(funnels)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(
            set(row),
            {"mechanism_family", "evaluated_count", "outcome_state", "stop_reason"},
        )
        self.assertEqual(row["mechanism_family"], "m:a:b")
        self.assertEqual(row["evaluated_count"], 45)
        self.assertIn(row["outcome_state"], {INCONCLUSIVE, LOW_INFORMATION})

    def test_research_outcome_summary_is_count_aggregate_only(self):
        records = [evidence(i, quality="FINAL") for i in range(45)]
        funnels = build_research_yield(
            records, eligibility=rejected_eligibility(range(45))
        )
        summary = research_outcome_summary(funnels)
        self.assertEqual(summary["mechanism_families"], 1)
        self.assertEqual(summary["evaluated"], 45)
        self.assertEqual(summary["optimizer_eligible_parents"], 0)
        self.assertEqual(summary["children_generated"], 0)
        self.assertEqual(summary["incremental_pass"], 0)
        self.assertEqual(summary["outcome_states"][LOW_INFORMATION], 1)
        banned = ("sharpe", "turnover", "returns", "drawdown", "checks", "fitness")
        for key in summary:
            lowered = key.lower()
            for token in banned:
                self.assertNotIn(token, lowered)
