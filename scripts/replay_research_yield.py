"""Read-only replay of real campaign evidence into ResearchYield funnels.

No Simulation, no writes to .wqb_state.  It reads checkpoint experiments,
proposals.json (round 13) and the r11/r12 metrics snapshots, aggregates them
per semantic mechanism family, and prints family funnels plus deterministic
family outcomes.

Evidence-quality rules applied during replay:
- checkpoint experiments carry execution facts only -> no FINAL evidence;
- r11/r12 metrics snapshots still have SELF_CORRELATION pending and failed
  checks -> at most PROVISIONAL observations, never FINAL;
- optimizer gate output does not exist for historical rounds -> eligibility
  stays unavailable (frozen #14 handoff rule), DONE never fabricates parents.

Usage:
  python scripts/replay_research_yield.py
  python scripts/replay_research_yield.py --assume-eligibility-rejected
  python scripts/replay_research_yield.py --assume-handoff-rehydrated
  python scripts/replay_research_yield.py --compare-handoff
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = _SCRIPT_DIR.parent if _SCRIPT_DIR.name == "scripts" else _SCRIPT_DIR
sys.path.insert(0, str(ROOT))

from wqb_agent.research_yield import (  # noqa: E402
    ResearchYieldPolicy,
    build_research_yield,
    family_state,
    research_outcome_summary,
    session_control_metadata,
)

STATE = ROOT / ".wqb_state"
FAMILY_KEY = "semantic_mechanism_key"
REJECTED_REASON = "PARENT_INCREMENTAL_EVIDENCE_INSUFFICIENT"


def _proposal_key_fn(record):
    """Reuse the stored diversity-derived mechanism key; missing -> UNKNOWN."""
    value = record.get(FAMILY_KEY)
    return str(value).strip().lower() if value else "UNKNOWN"


def load_checkpoint_experiments():
    rows = []
    for round_no in range(1, 14):
        path = STATE / f"round_{round_no}.checkpoint.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for exp in data.get("experiments", []):
            row = dict(exp)
            row.setdefault("round", round_no)
            rows.append(row)
    return rows


def load_proposals():
    data = json.loads((STATE / "proposals.json").read_text(encoding="utf-8"))
    round_no = data.get("round_no", 13)
    return [dict(proposal, round=round_no) for proposal in data.get("proposals", [])]


def load_metrics_snapshots():
    rows = []
    for name, round_no in (
        ("_round11_metrics.json", 11),
        ("_round_12_metrics.json", 12),
    ):
        path = STATE / name
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            record = dict(row)
            record["round"] = round_no
            record["reward_quality"] = "PROVISIONAL_EVIDENCE"
            record["outcome_kind"] = "PROVISIONAL"
            rows.append(record)
    return rows


def _status_summary(rows):
    return dict(Counter(str(row.get("status")) for row in rows))


def _round13_eligibility(checkpoints, *, eligible):
    """HYPOTHETICAL gate output for round 13 (the only round with proposals).

    ``eligible=False`` models "gate ran and rejected every parent"; the
    historical UNKNOWN bucket keeps eligibility unavailable.  ``eligible=True``
    models the "after #14" view where canonical trajectory evidence has been
    rehydrated.  Both are explicit assumptions, never real evidence.
    """
    eligibility = {}
    for row in checkpoints:
        if row.get("round") != 13:
            continue
        for key in ("proposal_id", "id", "submission_fingerprint"):
            value = row.get(key)
            if value not in (None, ""):
                eligibility[str(value)] = {
                    "eligible": eligible,
                    "reasons": [] if eligible else [REJECTED_REASON],
                }
                break
    return eligibility


def _run(proposals, checkpoints, snapshots, eligibility):
    funnels = build_research_yield(
        proposals,
        checkpoints,
        snapshots,
        mechanism_key_fn=_proposal_key_fn,
        eligibility=eligibility,
    )
    return funnels, ResearchYieldPolicy()


def _handoff_view(funnels, policy):
    """Compact control-plane view of the optimizer-handoff stage only."""
    states = Counter(
        family_state(funnel, policy=policy)["state"] for funnel in funnels.values()
    )
    return {
        "family_states": dict(sorted(states.items())),
        "optimizer_eligible_available": any(
            funnel.optimizer_eligible_available for funnel in funnels.values()
        ),
        "optimizer_eligible_parents": sum(
            funnel.optimizer_eligible_parents or 0 for funnel in funnels.values()
        ),
        "optimizer_rejected_parents": sum(
            funnel.optimizer_rejected_parents or 0 for funnel in funnels.values()
        ),
        "final_evidence": sum(
            funnel.final_evidence_count or 0 for funnel in funnels.values()
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assume-eligibility-rejected",
        action="store_true",
        help=(
            "HYPOTHETICAL view: assume the optimizer gate ran for every "
            "record and rejected every parent (frozen #14 fixed).  This is "
            "an explicit assumption, not real evidence."
        ),
    )
    parser.add_argument(
        "--assume-handoff-rehydrated",
        action="store_true",
        help=(
            "HYPOTHETICAL 'after #14' view: assume the canonical trajectory "
            "evidence of round 13 is rehydrated so the optimizer gate can "
            "evaluate those parents.  This is an explicit assumption, not "
            "real evidence."
        ),
    )
    parser.add_argument(
        "--compare-handoff",
        action="store_true",
        help=(
            "Print the 'before' (no rehydrated evidence -> BLOCKED) versus "
            "'after' (rehydrated evidence -> eligibility available) handoff "
            "yield view."
        ),
    )
    args = parser.parse_args()

    checkpoints = load_checkpoint_experiments()
    proposals = load_proposals()
    snapshots = load_metrics_snapshots()
    print(f"checkpoint experiments: {len(checkpoints)}")
    print(f"proposals (round 13):   {len(proposals)}")
    print(f"metrics snapshots:      {len(snapshots)}")

    mode = "real"
    eligibility = None
    if args.assume_eligibility_rejected:
        # HYPOTHESIS ONLY: inject a rejected-gate result for round 13
        # checkpoint records (the only round with proposal metadata).  The
        # historical UNKNOWN bucket keeps eligibility unavailable.
        mode = "assume-eligibility-rejected"
        eligibility = _round13_eligibility(checkpoints, eligible=False)
    elif args.assume_handoff_rehydrated:
        # HYPOTHESIS ONLY: the frozen #14 handoff gap is closed by rehydrating
        # canonical trajectory evidence, so the gate can evaluate parents.
        mode = "handoff-rehydrated"
        eligibility = _round13_eligibility(checkpoints, eligible=True)

    funnels, policy = _run(proposals, checkpoints, snapshots, eligibility)
    print(f"\nmechanism families: {len(funnels)}")
    print("\nfamily funnel + outcome:")
    for key in sorted(funnels):
        funnel = funnels[key]
        decision = family_state(funnel, policy=policy)
        print(f"- {key}")
        print(
            f"    assembled={funnel.assembled_proposals} "
            f"dispatched={funnel.simulations_dispatched} "
            f"done={funnel.simulations_done} failed={funnel.simulations_failed} "
            f"unresolved={funnel.simulations_unresolved} "
            f"quality={funnel.quality_evaluated} "
            f"final={funnel.final_evidence_count} "
            f"provisional={funnel.provisional_evidence_count} "
            f"infra={funnel.infrastructure_failure_count} "
            f"research_fail={funnel.research_failure_count} "
            f"eligible={funnel.optimizer_eligible_parents} "
            f"children={funnel.children_generated} "
            f"inc_pass={funnel.incremental_pass} "
            f"lineages={funnel.independent_lineage_count}"
        )
        print(f"    state={decision['state']} reasons={decision['reasons']}")

    report = {
        "mode": mode,
        "read_only": True,
        "checkpoint_experiments": len(checkpoints),
        "proposals_round13": len(proposals),
        "metrics_snapshots": len(snapshots),
        "checkpoint_status": _status_summary(checkpoints),
        "snapshot_status": _status_summary(snapshots),
        "handoff_view": _handoff_view(funnels, policy),
        "families": {
            key: {
                "assembled": funnel.assembled_proposals,
                "simulations_done": funnel.simulations_done,
                "simulations_failed": funnel.simulations_failed,
                "simulations_unresolved": funnel.simulations_unresolved,
                "quality_evaluated": funnel.quality_evaluated,
                "final_evidence": funnel.final_evidence_count,
                "provisional_evidence": funnel.provisional_evidence_count,
                "infrastructure_failures": funnel.infrastructure_failure_count,
                "research_failures": funnel.research_failure_count,
                "optimizer_eligible_available": funnel.optimizer_eligible_available,
                "optimizer_eligible_parents": funnel.optimizer_eligible_parents,
                "children_generated": funnel.children_generated,
                "incremental_pass": funnel.incremental_pass,
                "independent_lineage_count": funnel.independent_lineage_count,
                "outcome": family_state(funnel, policy=policy),
                "conversions": funnel.conversions(),
            }
            for key, funnel in sorted(funnels.items())
        },
        "outcome_summary": research_outcome_summary(funnels, policy=policy),
        "session_control_metadata": session_control_metadata(funnels, policy=policy),
    }
    print("\nreport JSON:\n" + json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    if args.compare_handoff:
        before = _handoff_view(*_run(proposals, checkpoints, snapshots, None))
        after = _handoff_view(
            *_run(
                proposals,
                checkpoints,
                snapshots,
                _round13_eligibility(checkpoints, eligible=True),
            )
        )
        print("\nhandoff before/after:")
        print(json.dumps(
            {"before": before, "after": after},
            ensure_ascii=False, indent=2, sort_keys=True,
        ))


if __name__ == "__main__":
    main()
