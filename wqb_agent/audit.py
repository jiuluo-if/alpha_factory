"""Small, read-only invariant audit for local state."""

from __future__ import annotations

from .state import TERMINAL_STATUSES
from .workspace_snapshot import read_workspace_snapshot


def audit_state(state_dir, *, snapshot=None):
    snapshot = snapshot or read_workspace_snapshot(state_dir)
    errors = []
    trajectory_summary = snapshot.trajectory
    trajectory_ids = set(trajectory_summary.trajectory_ids)
    committed = set(trajectory_summary.committed)
    submitted = set(trajectory_summary.submitted)
    settled = set(trajectory_summary.settled)
    checkpoint_terminal = {}
    ledger_terminal = set()
    ledger_summary = snapshot.ledger
    if (
        trajectory_summary.duplicate_settlements
        or ledger_summary.duplicate_settlements
    ):
        errors.append("duplicate_settlement")
    committed.update(ledger_summary.committed)
    submitted.update(ledger_summary.submitted)
    settled.update(ledger_summary.research_settled)
    ledger_terminal.update(ledger_summary.simulation_settled)
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
    if not submitted.issubset(committed) or not settled.issubset(submitted):
        errors.append("lifecycle_order")
    if checkpoint_terminal and not snapshot.inventory.info("trial_ledger.jsonl").exists:
        errors.append("ledger_missing")
    if any(proposal_id not in ledger_terminal for proposal_id in checkpoint_terminal):
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
            "committed": len(committed), "submitted": len(submitted),
            "settled": len(settled)}
