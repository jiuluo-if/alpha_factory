"""Small, read-only invariant audit for local state."""

from __future__ import annotations

import json
import os


def audit_state(state_dir):
    errors = []
    settlement_ids = set()
    trajectory_ids = set()
    committed = set()
    submitted = set()
    settled = set()
    trajectory_path = os.path.join(state_dir, "trajectory.jsonl")
    try:
        with open(trajectory_path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(row, dict):
                    proposal_id = row.get("proposal_id")
                    if proposal_id:
                        phase = row.get("phase")
                        if phase == "simulation_committed":
                            committed.add(str(proposal_id))
                        elif phase in {"simulation_submitted", "simulation_settled"}:
                            submitted.add(str(proposal_id))
                        elif phase == "research_outcome_settled":
                            settled.add(str(proposal_id))
                    if row.get("phase") == "research_outcome_settled":
                        settlement_id = (row.get("settlement") or {}).get("settlement_id")
                        if settlement_id and settlement_id in settlement_ids:
                            errors.append("duplicate_settlement")
                        elif settlement_id:
                            settlement_ids.add(str(settlement_id))
                    for key in (row.get("id"), row.get("alpha_id"), row.get("proposal_id")):
                        if key:
                            trajectory_ids.add(str(key))
    except OSError:
        pass
    try:
        for name in os.listdir(state_dir):
            if not name.startswith("round_") or not name.endswith(".checkpoint.json"):
                continue
            with open(os.path.join(state_dir, name), encoding="utf-8") as handle:
                checkpoint = json.load(handle)
            for row in ((checkpoint.get("experiments") or []) if isinstance(checkpoint, dict) else ()):
                if isinstance(row, dict) and row.get("status") == "PENDING" and not row.get("proposal_id"):
                    errors.append("phantom_reservation")
                    break
                if not isinstance(row, dict):
                    continue
                status = str(row.get("status") or "").upper()
                if status == "SUBMIT_UNKNOWN" and row.get("budget_held") is False:
                    errors.append("unknown_not_budget_held")
                if status in {"DONE", "FAILED", "SKIPPED"} and row.get("reserved") is True:
                    errors.append("terminal_occupies_arm")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        errors.append("checkpoint_unreadable")
    ledger_path = os.path.join(state_dir, "trial_ledger.jsonl")
    try:
        with open(ledger_path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(row, dict):
                    continue
                proposal_id = row.get("proposal_id")
                phase = row.get("phase")
                if proposal_id and phase == "simulation_committed":
                    committed.add(str(proposal_id))
                elif proposal_id and phase in {"simulation_submitted", "simulation_settled"}:
                    submitted.add(str(proposal_id))
                if phase != "research_outcome_settled":
                    continue
                if proposal_id:
                    settled.add(str(proposal_id))
                settlement_id = (row.get("settlement") or {}).get("settlement_id")
                if settlement_id and settlement_id in settlement_ids:
                    errors.append("duplicate_settlement")
                elif settlement_id:
                    settlement_ids.add(str(settlement_id))
    except OSError:
        pass
    if not submitted.issubset(committed) or not settled.issubset(submitted):
        errors.append("lifecycle_order")

    report_path = os.path.join(state_dir, "validation_reports.jsonl")
    try:
        with open(report_path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(row, dict):
                    continue
                if row.get("parent_id") and str(row["parent_id"]) not in trajectory_ids:
                    errors.append("orphan_validation_parent")
                nested = row.get("report")
                if isinstance(nested, dict) and row.get("plan_id") != nested.get("plan_id"):
                    errors.append("validation_plan_mismatch")
    except OSError:
        pass
    pool_path = os.path.join(state_dir, "submission_pool.json")
    try:
        with open(pool_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        for row in (payload.get("candidates") if isinstance(payload, dict) else []) or []:
            if isinstance(row, dict) and not any(str(row.get(key)) in trajectory_ids for key in ("alpha_id", "proposal_id")):
                errors.append("orphan_submission")
                break
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    unique_errors = list(dict.fromkeys(errors))
    return {"ok": not unique_errors, "errors": unique_errors,
            "committed": len(committed), "submitted": len(submitted),
            "settled": len(settled)}
