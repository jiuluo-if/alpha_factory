"""Small, read-only invariant audit for local state."""

from __future__ import annotations

import json
import os


def audit_state(state_dir):
    errors = []
    settlement_ids = set()
    trajectory_ids = set()
    trajectory_path = os.path.join(state_dir, "trajectory.jsonl")
    try:
        with open(trajectory_path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(row, dict):
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
                if not isinstance(row, dict) or row.get("phase") != "research_outcome_settled":
                    continue
                settlement_id = (row.get("settlement") or {}).get("settlement_id")
                if settlement_id and settlement_id in settlement_ids:
                    errors.append("duplicate_settlement")
                elif settlement_id:
                    settlement_ids.add(str(settlement_id))
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
    return {"ok": not errors, "errors": errors}
