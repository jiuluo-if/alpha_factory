"""ROLE: INTERNAL
AGENT_RELEVANCE: LOW
PURPOSE: Derive mechanism-family research yield from existing evidence.
READ WHEN: analyzing whether a semantic research route advanced research.
DO NOT USE FOR: platform truth, metrics storage, checkpoint/trajectory owner,
Simulation scheduling, reward replacement, or any remote write.

Derived control-plane research evidence.

ResearchYield aggregates existing SearchOutcome / experiment / optimizer
handoff / incremental evidence into a per-semantic-mechanism funnel.  It
separates execution completion from research progress, keeps FINAL /
PROVISIONAL / LEGACY evidence quality apart, and classifies infrastructure
failure separately from research failure.  It is a deterministic in-memory /
report projection: no new files, no second reward engine, no scheduler and
no research-state owner.

Mechanism identity reuses :func:`wqb_agent.diversity.semantic_mechanism_key`;
lineage uses the existing lineage identity; evidence-quality buckets mirror
SearchOutcome ``reward_quality`` values.  This module never imports Client,
Simulator or state, and never performs a POST.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .diversity import semantic_mechanism_key as _default_mechanism_key

# Evidence quality buckets (mirror SearchOutcome.reward_quality).
FINAL_EVIDENCE = "FINAL_EVIDENCE"
PROVISIONAL_EVIDENCE = "PROVISIONAL_EVIDENCE"
LEGACY_APPROXIMATE = "LEGACY_APPROXIMATE"

# Mechanism-family outcomes.
INCONCLUSIVE = "INCONCLUSIVE"
PROMISING = "PROMISING"
LOW_INFORMATION = "LOW_INFORMATION"
EXHAUSTED = "EXHAUSTED"
BLOCKED = "BLOCKED"

# STOP taxonomy (reuses existing route vocabulary where possible).
ROUTE_ATTEMPTS_EXHAUSTED = "ROUTE_ATTEMPTS_EXHAUSTED"
NO_INFORMATION_GAIN = "NO_INFORMATION_GAIN"
MECHANISM_FAMILY_EXHAUSTED = "MECHANISM_FAMILY_EXHAUSTED"
LOW_RESEARCH_YIELD = "LOW_RESEARCH_YIELD"
NO_INCREMENTAL_CHILD_EVIDENCE = "NO_INCREMENTAL_CHILD_EVIDENCE"
INFRASTRUCTURE_BLOCKED = "INFRASTRUCTURE_BLOCKED"

STOP_REASONS = frozenset({
    ROUTE_ATTEMPTS_EXHAUSTED,
    NO_INFORMATION_GAIN,
    MECHANISM_FAMILY_EXHAUSTED,
    LOW_RESEARCH_YIELD,
    NO_INCREMENTAL_CHILD_EVIDENCE,
    INFRASTRUCTURE_BLOCKED,
})

# Execution status partition (mirrors state.py frozen status contract).
_ACTIVE_UNRESOLVED = frozenset({"PENDING", "RUNNING", "SUBMITTING"})
_TERMINAL_DONE = frozenset({"DONE"})
_TERMINAL_FAILED = frozenset({"FAILED"})
_UNKNOWN_BOUNDARY = frozenset({"UNKNOWN", "SUBMIT_UNKNOWN"})
_SKIPPED_INFRA = frozenset({"SKIPPED_STALE", "SKIPPED_UNKNOWN"})
_SKIPPED_LOCAL = frozenset({"SKIPPED", "SKIPPED_LOCAL"})

_SIMULATION_STATUSES = (
    _ACTIVE_UNRESOLVED | _TERMINAL_DONE | _TERMINAL_FAILED
    | _UNKNOWN_BOUNDARY | _SKIPPED_INFRA | _SKIPPED_LOCAL
)

_INFRA_TOKENS = (
    "AUTH", "RATE_LIMIT", "TIMEOUT", "INFRA", "NETWORK", "HTTP",
    "TRANSPORT", "PLATFORM_UNAVAILABLE", "STALE",
)

# Optimizer gate rejection reasons that mean evidence is missing, not that
# the parent failed research-side (mirrors OptimizerWorkflow._parent_rejections).
_EVIDENCE_GAP_REASONS = frozenset({
    "PARENT_METRICS_MISSING",
    "PARENT_CHECKS_INCOMPLETE",
    "PARENT_FIELD_EVIDENCE_MISSING",
})


def _upper(value):
    return str(value or "").upper()


@dataclass(frozen=True)
class ResearchYieldPolicy:
    """Conservative, typed sample guards for derived family outcomes.

    Only two new knobs are introduced (``min_evaluated`` / ``window``);
    everything else reuses existing route / budget / SearchPolicy semantics.
    """

    min_evaluated: int = 40
    window: int = 200
    min_final_evidence: int = 1
    infra_domination_ratio: float = 0.5
    unresolved_domination_ratio: float = 0.5

    def __post_init__(self):
        if int(self.min_evaluated) <= 0:
            raise ValueError("research_yield.min_evaluated 必须为正整数")
        if int(self.window) <= 0:
            raise ValueError("research_yield.window 必须为正整数")
        if int(self.min_final_evidence) <= 0:
            raise ValueError("research_yield.min_final_evidence 必须为正整数")
        for name in ("infra_domination_ratio", "unresolved_domination_ratio"):
            value = float(getattr(self, name))
            if not (0.0 < value <= 1.0):
                raise ValueError(f"research_yield.{name} 必须在 (0, 1] 内")

def conversion(numerator, denominator):
    """Ratio with an explicit None for a zero or unavailable denominator.

    ``denominator == 0`` means the stage had no opportunity to occur
    (``NO_DENOMINATOR``); ``denominator is None`` means the evidence needed
    to compute the stage is unavailable (``DENOMINATOR_UNAVAILABLE``).
    Neither is ever reported as 0.0.
    """
    if denominator is None:
        return {"value": None, "reason": "DENOMINATOR_UNAVAILABLE"}
    try:
        num = int(numerator)
        den = int(denominator)
    except (TypeError, ValueError):
        return {"value": None, "reason": "DENOMINATOR_UNAVAILABLE"}
    if den <= 0:
        return {"value": None, "reason": "NO_DENOMINATOR"}
    return {"value": num / den, "reason": "OK"}


@dataclass(frozen=True)
class ResearchYieldFunnel:
    """One mechanism family's derived research-yield funnel (counts only)."""

    mechanism_key: str
    feasible_candidates: int = 0
    assembled_proposals: int = 0
    simulations_dispatched: int = 0
    simulations_done: int = 0
    simulations_failed: int = 0
    simulations_unresolved: int = 0
    simulations_skipped: int = 0
    quality_evaluated: int = 0
    final_evidence_count: int = 0
    provisional_evidence_count: int = 0
    legacy_evidence_count: int = 0
    infrastructure_failure_count: int = 0
    research_failure_count: int = 0
    optimizer_eligible_parents: int | None = None
    optimizer_rejected_parents: int | None = None
    optimizer_eligible_available: bool = False
    optimizer_rejection_reasons: tuple[tuple[str, int], ...] = ()
    children_generated: int = 0
    children_done: int = 0
    incremental_pass: int = 0
    incremental_fail: int = 0
    incremental_unknown: int = 0
    incremental_available: bool = False
    independent_lineage_count: int = 0
    novelty_gain: bool = False

    def conversions(self):
        """Five conversions; denominator rules are explicit, never 0.0."""
        eligible = self.optimizer_eligible_parents
        if not self.optimizer_eligible_available:
            done_to_parent = {"value": None, "reason": "DENOMINATOR_UNAVAILABLE"}
            parent_to_child = {"value": None, "reason": "DENOMINATOR_UNAVAILABLE"}
        else:
            done_to_parent = conversion(eligible, self.simulations_done)
            parent_to_child = conversion(self.children_generated, eligible)
        if self.children_done <= 0:
            child_to_incremental = {"value": None, "reason": "NO_DENOMINATOR"}
        elif not self.incremental_available:
            child_to_incremental = {"value": None, "reason": "DENOMINATOR_UNAVAILABLE"}
        else:
            child_to_incremental = conversion(self.incremental_pass, self.children_done)
        return {
            "proposal_to_simulation": conversion(self.simulations_dispatched, self.assembled_proposals),
            "simulation_to_done": conversion(self.simulations_done, self.simulations_dispatched),
            "done_to_optimizer_parent": done_to_parent,
            "parent_to_child": parent_to_child,
            "child_to_incremental": child_to_incremental,
        }

    def as_dict(self):
        return {
            "mechanism_key": self.mechanism_key,
            "feasible_candidates": self.feasible_candidates,
            "assembled_proposals": self.assembled_proposals,
            "simulations_dispatched": self.simulations_dispatched,
            "simulations_done": self.simulations_done,
            "simulations_failed": self.simulations_failed,
            "simulations_unresolved": self.simulations_unresolved,
            "simulations_skipped": self.simulations_skipped,
            "quality_evaluated": self.quality_evaluated,
            "final_evidence_count": self.final_evidence_count,
            "provisional_evidence_count": self.provisional_evidence_count,
            "legacy_evidence_count": self.legacy_evidence_count,
            "infrastructure_failure_count": self.infrastructure_failure_count,
            "research_failure_count": self.research_failure_count,
            "optimizer_eligible_parents": self.optimizer_eligible_parents,
            "optimizer_rejected_parents": self.optimizer_rejected_parents,
            "optimizer_eligible_available": self.optimizer_eligible_available,
            "optimizer_rejection_reasons": dict(self.optimizer_rejection_reasons),
            "children_generated": self.children_generated,
            "children_done": self.children_done,
            "incremental_pass": self.incremental_pass,
            "incremental_fail": self.incremental_fail,
            "incremental_unknown": self.incremental_unknown,
            "incremental_available": self.incremental_available,
            "independent_lineage_count": self.independent_lineage_count,
            "novelty_gain": self.novelty_gain,
            "conversions": self.conversions(),
        }


def failure_class(record):
    """Return ``INFRA``, ``RESEARCH`` or None for one record's failure lens."""
    status = _upper(record.get("status"))
    if status in _UNKNOWN_BOUNDARY or status in _SKIPPED_INFRA:
        return "INFRA"
    if status not in _TERMINAL_FAILED:
        return None
    reason = " ".join(
        str(record.get(key) or "") for key in
        ("reason_code", "reason", "error", "failure_class")
    )
    # Normalize punctuation so natural text like "rate limit" or
    # "RATE_LIMIT" matches the same infra token.
    normalized = reason.replace("_", " ").replace("-", " ").upper()
    tokens = {
        token.replace("_", " ").replace("-", " ").upper()
        for token in _INFRA_TOKENS
    }
    if "SUBMIT UNKNOWN" in normalized or any(
        token in normalized for token in tokens
    ):
        return "INFRA"
    return "RESEARCH"


def evidence_quality(record):
    """FINAL / PROVISIONAL / LEGACY bucket for one record, or None."""
    quality = _upper(record.get("reward_quality"))
    kind = _upper(record.get("outcome_kind"))
    if record.get("final_outcome") is not None or kind == "FINAL" or quality == FINAL_EVIDENCE:
        return FINAL_EVIDENCE
    if record.get("provisional_outcome") is not None or kind == "PROVISIONAL" or quality == PROVISIONAL_EVIDENCE:
        return PROVISIONAL_EVIDENCE
    if kind == "LEGACY" or quality == LEGACY_APPROXIMATE:
        return LEGACY_APPROXIMATE
    return None


def is_child(record):
    """Whether a record represents a derived child experiment."""
    if record.get("parent_expression") or record.get("child_economic_hypothesis"):
        return True
    return _upper(record.get("experiment_stage")) not in {"", "BASELINE"}


def incremental_verdict(record):
    """Settled incremental verdict PASS/FAIL/UNKNOWN, or None when unsettled."""
    value = record.get("incremental_decision")
    if value is None:
        outcome = record.get("final_outcome") or record.get("search_outcome")
        if isinstance(outcome, dict):
            value = outcome.get("incremental_decision")
    if value is None:
        return None
    text = _upper(value)
    if text in {"PASS", "FAIL", "UNKNOWN"}:
        return text
    if text in {"UNAVAILABLE", "NOT_APPLICABLE", "INCONCLUSIVE"}:
        return "UNKNOWN"
    return None


def lineage_root(record):
    """Existing lineage identity for independent-lineage counting."""
    for key in ("lineage_id", "parent_id", "hypothesis_id"):
        value = record.get(key)
        if value not in (None, ""):
            return f"{key}:{value}"
    if record.get("proposal_id") is not None:
        return f"proposal:{record['proposal_id']}"
    if record.get("id") is not None:
        return f"experiment:{record['id']}"
    return None


def _record_key(record):
    for key in ("id", "proposal_id", "submission_fingerprint"):
        value = record.get(key)
        if value not in (None, ""):
            return ("global", key, str(value))
    round_no = record.get("round")
    for key in ("lineage_id", "expression"):
        value = record.get(key)
        if value not in (None, ""):
            return (round_no, key, str(value))
    return None

def merge_evidence(*streams):
    """Merge record streams by any shared identity key (id / lineage / expression).

    Later streams fill gaps without duplicating the same underlying record.
    Identity keys are scoped: id/proposal_id/submission_fingerprint are global;
    expression merges only within the same round.  lineage_id is deliberately
    not an identity key: a lineage is an aggregation axis shared by many
    distinct experiments, so it must not collapse them into one slot.
    """
    slots: list[dict[str, Any]] = []

    def find_slot(record):
        keys = _identity_keys(record)
        for slot in slots:
            if _identity_keys(slot) & keys:
                return slot
        return None

    for stream in streams:
        for record in stream or ():
            if not isinstance(record, dict) or not record:
                continue
            slot = find_slot(record)
            if slot is None:
                slot = {}
                slots.append(slot)
            slot.update(record)
    return slots


def _identity_keys(record):
    """Unique-record identity; lineage is an aggregation axis, not identity."""
    keys = set()
    for key in ("id", "proposal_id", "submission_fingerprint"):
        value = record.get(key)
        if value not in (None, ""):
            keys.add(("global", key, str(value)))
    round_no = record.get("round")
    expression = record.get("expression")
    if expression not in (None, ""):
        keys.add((round_no, "expression", str(expression)))
    return keys


def _eligibility_key(record):
    for key in ("proposal_id", "id", "submission_fingerprint"):
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _build_funnel(family, records, *, eligibility):
    feasible = assembled = dispatched = 0
    done = failed = unresolved = skipped = 0
    quality_evaluated = final_count = provisional_count = legacy_count = 0
    infra_failures = research_failures = 0
    children = children_done = 0
    inc_pass = inc_fail = inc_unknown = 0
    inc_available = False
    lineages = set()
    eligible_count = None
    rejected_count = None
    rejection_reasons = Counter()
    eligible_available = eligibility is not None
    if eligible_available:
        eligible_count = 0
        rejected_count = 0
    for record in records:
        if _is_proposal_or_experiment(record):
            assembled += 1
        if _upper(record.get("semantic_admission")) == "ALLOW" or record.get("feasible") is True:
            feasible += 1
        status = _upper(record.get("status"))
        submitted = bool(
            status in _SIMULATION_STATUSES
            or record.get("submission_started_at")
            or record.get("progress_url")
        )
        if submitted:
            dispatched += 1
        if status in _TERMINAL_DONE:
            done += 1
        elif status in _TERMINAL_FAILED:
            failed += 1
            if failure_class(record) == "INFRA":
                infra_failures += 1
            else:
                research_failures += 1
        elif status in _ACTIVE_UNRESOLVED:
            unresolved += 1
        elif status in _UNKNOWN_BOUNDARY:
            infra_failures += 1
        elif status in _SKIPPED_INFRA:
            skipped += 1
            infra_failures += 1
        elif status in _SKIPPED_LOCAL:
            skipped += 1
        quality = evidence_quality(record)
        if quality == FINAL_EVIDENCE:
            final_count += 1
            quality_evaluated += 1
        elif quality == PROVISIONAL_EVIDENCE:
            provisional_count += 1
            quality_evaluated += 1
        elif quality == LEGACY_APPROXIMATE:
            legacy_count += 1
        if is_child(record):
            children += 1
            if status in _TERMINAL_DONE:
                children_done += 1
        verdict = incremental_verdict(record)
        if verdict is not None:
            inc_available = True
            if verdict == "PASS":
                inc_pass += 1
            elif verdict == "FAIL":
                inc_fail += 1
            else:
                inc_unknown += 1
        root = lineage_root(record)
        if root is not None:
            lineages.add(root)
        if eligible_available:
            key = _eligibility_key(record)
            decision = eligibility.get(key) if key is not None else None
            if decision is not None:
                if isinstance(decision, Mapping):
                    ok = bool(decision.get("eligible"))
                    reasons = decision.get("reasons") or ()
                else:
                    ok = bool(decision)
                    reasons = ()
                if ok:
                    eligible_count += 1
                else:
                    rejected_count += 1
                    for reason in reasons:
                        rejection_reasons[str(reason)] += 1
    return ResearchYieldFunnel(
        mechanism_key=family,
        feasible_candidates=feasible,
        assembled_proposals=assembled,
        simulations_dispatched=dispatched,
        simulations_done=done,
        simulations_failed=failed,
        simulations_unresolved=unresolved,
        simulations_skipped=skipped,
        quality_evaluated=quality_evaluated,
        final_evidence_count=final_count,
        provisional_evidence_count=provisional_count,
        legacy_evidence_count=legacy_count,
        infrastructure_failure_count=infra_failures,
        research_failure_count=research_failures,
        optimizer_eligible_parents=eligible_count,
        optimizer_rejected_parents=rejected_count,
        optimizer_eligible_available=eligible_available,
        optimizer_rejection_reasons=tuple(sorted(rejection_reasons.items())),
        children_generated=children,
        children_done=children_done,
        incremental_pass=inc_pass,
        incremental_fail=inc_fail,
        incremental_unknown=inc_unknown,
        incremental_available=inc_available,
        independent_lineage_count=len(lineages),
    )


def _is_proposal_or_experiment(record):
    if not isinstance(record, dict) or not str(record.get("expression") or "").strip():
        return False
    return bool(
        record.get("template_family") or record.get("template_id")
        or record.get("fields_used") or record.get("fields")
        or record.get("status")
    )


def build_research_yield(
    *streams,
    eligibility: Mapping[str, Any] | None = None,
    mechanism_key_fn: Callable[[Mapping[str, Any]], str] | None = None,
    window: int | None = None,
):
    """Aggregate merged evidence into per-semantic-mechanism funnels.

    ``eligibility`` is the optional optimizer gate output mapping a record key
    (proposal_id / id / submission_fingerprint) to ``bool`` or
    ``{"eligible": bool, "reasons": [...]}``.  When omitted, the optimizer
    stage stays unavailable: DONE alone must never fabricate parent
    eligibility (frozen #14 handoff rule).
    """
    key_fn = mechanism_key_fn or _default_mechanism_key
    merged = merge_evidence(*streams)
    by_family: dict[str, list] = defaultdict(list)
    for record in merged:
        # Only real experiment/proposal evidence enters the funnel; lightweight
        # cloud metadata (e.g. Alpha Feed rows without expression/template/
        # fields) must never become yield evidence.
        if not _is_proposal_or_experiment(record):
            continue
        family = str(key_fn(record) or "UNKNOWN").strip().lower()
        by_family[family].append(record)
    funnels = {}
    for family, records in by_family.items():
        if window is not None:
            records = records[-int(window):]
        funnels[family] = _build_funnel(family, records, eligibility=eligibility)
    return funnels

def family_state(
    funnel,
    *,
    policy: ResearchYieldPolicy | None = None,
    exhaustion_evidence: Iterable[str] = (),
    novelty_flat: bool = False,
):
    """Deterministic family outcome decision table (5 states, first match wins).

    Order: EXHAUSTED (explicit route/semantic closure) -> BLOCKED (infra
    dominated) -> INCONCLUSIVE (unresolved share) -> INCONCLUSIVE (sample) ->
    BLOCKED (handoff/evidence gap) -> INCONCLUSIVE (legacy/provisional only) ->
    PROMISING (downstream progress) -> LOW_INFORMATION (ample evidence, zero
    downstream) -> INCONCLUSIVE fallback.
    """
    policy = policy or ResearchYieldPolicy()
    exhaustion = {str(item).strip().lower() for item in exhaustion_evidence}
    if funnel.mechanism_key in exhaustion:
        return {
            "state": EXHAUSTED,
            "reasons": [MECHANISM_FAMILY_EXHAUSTED],
            "stop_reason": MECHANISM_FAMILY_EXHAUSTED,
        }
    terminal = (
        funnel.simulations_done
        + funnel.research_failure_count
        + funnel.infrastructure_failure_count
    )
    if terminal > 0 and (
        funnel.infrastructure_failure_count >= policy.infra_domination_ratio * terminal
    ):
        return {
            "state": BLOCKED,
            "reasons": [INFRASTRUCTURE_BLOCKED],
            "stop_reason": INFRASTRUCTURE_BLOCKED,
        }
    if funnel.simulations_dispatched > 0 and (
        funnel.simulations_unresolved
        >= policy.unresolved_domination_ratio * funnel.simulations_dispatched
    ):
        return {
            "state": INCONCLUSIVE,
            "reasons": ["SIMULATIONS_UNRESOLVED"],
            "stop_reason": None,
        }
    if _evidence_records(funnel) < policy.min_evaluated:
        return {
            "state": INCONCLUSIVE,
            "reasons": ["SAMPLE_INSUFFICIENT"],
            "stop_reason": None,
        }
    if (
        funnel.simulations_done >= policy.min_evaluated
        and not funnel.optimizer_eligible_available
    ):
        return {
            "state": BLOCKED,
            "reasons": ["HANDOFF_EVIDENCE_BLOCKED"],
            "stop_reason": INFRASTRUCTURE_BLOCKED,
        }
    rejected = funnel.optimizer_rejected_parents or 0
    if funnel.optimizer_eligible_available and rejected > 0:
        evidence_rejections = sum(
            count for reason, count in funnel.optimizer_rejection_reasons
            if reason in _EVIDENCE_GAP_REASONS
        )
        if evidence_rejections >= policy.infra_domination_ratio * rejected:
            return {
                "state": BLOCKED,
                "reasons": ["HANDOFF_EVIDENCE_BLOCKED", "EVIDENCE_GAP_REJECTIONS"],
                "stop_reason": INFRASTRUCTURE_BLOCKED,
            }
    if (
        funnel.legacy_evidence_count > 0
        and funnel.final_evidence_count == 0
        and funnel.provisional_evidence_count == 0
    ):
        return {
            "state": INCONCLUSIVE,
            "reasons": ["LEGACY_ONLY_EVIDENCE"],
            "stop_reason": None,
        }
    if funnel.final_evidence_count < policy.min_final_evidence:
        return {
            "state": INCONCLUSIVE,
            "reasons": ["FINAL_EVIDENCE_INSUFFICIENT"],
            "stop_reason": None,
        }
    downstream = (
        funnel.optimizer_eligible_available
        and (funnel.optimizer_eligible_parents or 0) > 0
    ) or (funnel.incremental_available and funnel.incremental_pass > 0)
    if downstream:
        return {
            "state": PROMISING,
            "reasons": ["DOWNSTREAM_RESEARCH_PROGRESS"],
            "stop_reason": None,
        }
    if funnel.optimizer_eligible_available and (
        funnel.optimizer_eligible_parents or 0
    ) == 0:
        reasons = ["ZERO_DOWNSTREAM_CONVERSION"]
        if novelty_flat:
            reasons.append("NOVELTY_FLAT")
        return {
            "state": LOW_INFORMATION,
            "reasons": reasons,
            "stop_reason": None,
        }
    return {
        "state": INCONCLUSIVE,
        "reasons": ["EVIDENCE_INCOMPLETE"],
        "stop_reason": None,
    }


def continuation_decision(
    state,
    *,
    reroute_count: int = 0,
    no_gain_count: int = 0,
    max_no_gain_attempts: int = 2,
    max_route_attempts: int = 3,
):
    """Map a family outcome onto the existing bounded continuation vocabulary.

    This is a pure derived input for the existing route policy; it does not
    create a new continuation workflow or scheduler.
    """
    if state == PROMISING:
        return {"decision": "CONTINUE", "stop_reason": None, "consumes_quota": True}
    if state == INCONCLUSIVE:
        return {"decision": "OBSERVE", "stop_reason": None, "consumes_quota": True}
    if state == LOW_INFORMATION:
        if int(no_gain_count) >= int(max_no_gain_attempts):
            return {
                "decision": "STOP",
                "stop_reason": LOW_RESEARCH_YIELD,
                "consumes_quota": False,
            }
        return {"decision": "REROUTE", "stop_reason": None, "consumes_quota": True}
    if state == EXHAUSTED:
        if int(reroute_count) >= int(max_route_attempts):
            return {
                "decision": "STOP",
                "stop_reason": MECHANISM_FAMILY_EXHAUSTED,
                "consumes_quota": False,
            }
        return {"decision": "REROUTE", "stop_reason": None, "consumes_quota": True}
    if state == BLOCKED:
        return {
            "decision": "WAIT",
            "stop_reason": INFRASTRUCTURE_BLOCKED,
            "consumes_quota": False,
        }
    return {"decision": "OBSERVE", "stop_reason": None, "consumes_quota": True}


def incremental_stop_reason(funnel):
    """NO_INCREMENTAL_CHILD_EVIDENCE only after a real child opportunity settled.

    Without a legal parent, generated children, completed children, or a
    settled incremental verdict this reason must not be used.
    """
    if funnel.children_generated <= 0:
        return None
    if funnel.children_done < 1:
        return None
    if not funnel.incremental_available:
        return None
    if funnel.incremental_pass > 0:
        return None
    return NO_INCREMENTAL_CHILD_EVIDENCE


def session_control_metadata(
    funnels,
    *,
    policy: ResearchYieldPolicy | None = None,
    exhaustion_evidence: Iterable[str] = (),
    novelty_flat: bool = False,
):
    """Minimal control metadata for an existing factory_session envelope.

    Only mechanism family, evaluated count, outcome state and stop reason;
    no SearchOutcome list, metrics, checks bodies or reward history.
    """
    rows = []
    for key in sorted(funnels):
        funnel = funnels[key]
        decision = family_state(
            funnel,
            policy=policy,
            exhaustion_evidence=exhaustion_evidence,
            novelty_flat=novelty_flat,
        )
        rows.append({
            "mechanism_family": funnel.mechanism_key,
            "evaluated_count": funnel.quality_evaluated,
            "outcome_state": decision["state"],
            "stop_reason": decision["stop_reason"],
        })
    return rows


def research_outcome_summary(
    funnels,
    *,
    policy: ResearchYieldPolicy | None = None,
    exhaustion_evidence: Iterable[str] = (),
    novelty_flat: bool = False,
):
    """Low-frequency aggregate for a heartbeat-style RESEARCH_OUTCOME view.

    Counts only; raw metrics and checks never enter this summary.
    """
    states = Counter()
    evaluated = 0
    parents = 0
    children = 0
    incremental_pass = 0
    for funnel in funnels.values():
        decision = family_state(
            funnel,
            policy=policy,
            exhaustion_evidence=exhaustion_evidence,
            novelty_flat=novelty_flat,
        )
        states[decision["state"]] += 1
        evaluated += funnel.quality_evaluated
        parents += funnel.optimizer_eligible_parents or 0
        children += funnel.children_generated
        incremental_pass += funnel.incremental_pass
    return {
        "mechanism_families": len(funnels),
        "evaluated": evaluated,
        "optimizer_eligible_parents": parents,
        "children_generated": children,
        "incremental_pass": incremental_pass,
        "outcome_states": dict(states),
    }

def _evidence_records(funnel):
    """All evidence-bearing records (FINAL + PROVISIONAL + LEGACY)."""
    return (
        funnel.final_evidence_count
        + funnel.provisional_evidence_count
        + funnel.legacy_evidence_count
    )
