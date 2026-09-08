"""Small, read-only invariant audit for local state."""

from __future__ import annotations

from .state import TERMINAL_STATUSES
from .workspace_snapshot import read_workspace_snapshot


def audit_state(state_dir, *, snapshot=None):
    snapshot = snapshot or read_workspace_snapshot(state_dir)
    errors = []
    trajectory_summary = snapshot.trajectory
    trajectory_ids = set(trajectory_summary.trajectory_ids)
    observed_committed = set(trajectory_summary.observed_committed)
    observed_submitted = set(trajectory_summary.observed_submitted)
    observed_simulation_settled = set(trajectory_summary.observed_simulation_settled)
    observed_research_settled = set(trajectory_summary.observed_research_settled)
    checkpoint_terminal = {}
    ledger_summary = snapshot.ledger
    ledger_committed = set(ledger_summary.committed)
    ledger_submitted = set(ledger_summary.submitted)
    ledger_simulation_settled = set(ledger_summary.simulation_settled)
    ledger_research_settled = set(ledger_summary.research_settled)
    if (
        trajectory_summary.duplicate_observed_settlements
        or ledger_summary.duplicate_settlements
    ):
        errors.append("duplicate_settlement")
    for record in snapshot.checkpoint_records:
        if record["malformed"]:
            errors.append("checkpoint_unreadable")
        for row in record["checkpoint"].get("experiments") or []:
            if isinstance(row, dict) and row.get("status") == "PENDING" and not row.get("proposal_id"):
                errors.append("phantom_reservation")
                break
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "").upper()
            proposal_id = row.get("proposal_id")
            if proposal_id and status in TERMINAL_STATUSES:
                checkpoint_terminal[str(proposal_id)] = status
            if status == "SUBMIT_UNKNOWN" and row.get("budget_held") is False:
                errors.append("unknown_not_budget_held")
            if status in {"DONE", "FAILED", "SKIPPED"} and row.get("reserved") is True:
                errors.append("terminal_occupies_arm")
    if (
        not ledger_submitted.issubset(ledger_committed)
        or not ledger_simulation_settled.issubset(ledger_submitted)
        or not ledger_research_settled.issubset(ledger_submitted)
    ):
        errors.append("lifecycle_order")
    if (
        not observed_submitted.issubset(observed_committed)
        or not observed_simulation_settled.issubset(observed_submitted)
        or not observed_research_settled.issubset(observed_submitted)
    ):
        errors.append("trajectory_lifecycle_order")
    observed_by_phase = (
        (observed_committed, ledger_committed),
        (observed_submitted, ledger_submitted),
        (observed_simulation_settled, ledger_simulation_settled),
        (observed_research_settled, ledger_research_settled),
    )
    if any(observed - authoritative for observed, authoritative in observed_by_phase):
        errors.append("trajectory_lifecycle_missing_ledger")
    ledger_lifecycle_ids = (
        ledger_committed | ledger_submitted | ledger_simulation_settled
        | ledger_research_settled
    )
    if any(proposal_id not in trajectory_ids for proposal_id in ledger_lifecycle_ids):
        errors.append("ledger_lifecycle_missing_trajectory")
    if checkpoint_terminal and not snapshot.inventory.info("trial_ledger.jsonl").exists:
        errors.append("ledger_missing")
    if any(proposal_id not in ledger_simulation_settled for proposal_id in checkpoint_terminal):
        errors.append("checkpoint_ledger_mismatch")

    for parent_id in snapshot.validation.parent_ids:
        if parent_id not in trajectory_ids:
            errors.append("orphan_validation_parent")
    for plan_id, nested_plan_id in snapshot.validation.plan_pairs:
        if plan_id != nested_plan_id:
            errors.append("validation_plan_mismatch")
    for identities in snapshot.submission_pool.candidate_identities:
        if not any(identity in trajectory_ids for identity in identities):
            errors.append("orphan_submission")
            break
    unique_errors = list(dict.fromkeys(errors))
    return {"ok": not unique_errors, "errors": unique_errors,
            "committed": len(ledger_committed), "submitted": len(ledger_submitted),
            "settled": len(ledger_research_settled),
            "trajectory_observed_committed": len(observed_committed),
            "trajectory_observed_submitted": len(observed_submitted),
            "trajectory_observed_simulation_settled": len(observed_simulation_settled),
            "trajectory_observed_research_settled": len(observed_research_settled)}
