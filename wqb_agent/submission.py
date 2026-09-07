"""Manual-submission pool and platform SELF_CORRELATION evidence.

This module never submits an Alpha.  It only preserves candidates which have
already passed the platform's correlation check against the ACTIVE universe.
"""

import json
import os
import re
import time

from .artifacts import atomic_write_json_if_changed
from .metrics import check_pass


_SELF_CORRELATION = re.compile(r"self[-_ ]?correlation", re.I)


def self_correlation_evidence(metrics):
    """Normalize the platform SELF_CORRELATION check from an alpha payload."""
    checks = (metrics or {}).get("checks") or []
    for check in checks:
        if isinstance(check, dict) and _SELF_CORRELATION.search(str(check.get("name", ""))):
            passed = check_pass(check)
            result = check.get("result")
            if isinstance(result, str) and result.strip().upper() in {
                    "PENDING", "UNKNOWN", "INCOMPLETE"
            }:
                passed = None
            return {
                "status": "PASS" if passed is True else "FAIL" if passed is False else "PENDING",
                "check": dict(check),
                "source": "BRAIN alpha payload",
            }
    return {"status": "PENDING", "check": None, "source": "BRAIN check missing"}


def latest_active_snapshot(state_dir):
    """Read the newest local ACTIVE snapshot as audit provenance only."""
    latest_name = None
    try:
        with os.scandir(state_dir) as entries:
            for entry in entries:
                if (entry.is_file()
                        and re.fullmatch(r"active_alphas_\d{8}\.json", entry.name)
                        and (latest_name is None or entry.name > latest_name)):
                    latest_name = entry.name
    except OSError:
        latest_name = None
    if latest_name is None:
        return None
    path = os.path.join(state_dir, latest_name)
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        return {
            "path": os.path.abspath(path),
            "fetched_at": payload.get("fetched_at"),
            "total": payload.get("total"),
        }
    except (OSError, ValueError, json.JSONDecodeError):
        return None


class SubmissionPool:
    """Append/update a local review queue; it intentionally has no POST API."""

    def __init__(self, state_dir, filename="submission_pool.json"):
        self.path = os.path.join(state_dir, filename)

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"schema_version": 1, "candidates": []}
            candidates = data.get("candidates")
            if not isinstance(candidates, list):
                data["candidates"] = []
            else:
                data["candidates"] = [item for item in candidates if isinstance(item, dict)]
            return data
        except (OSError, ValueError, json.JSONDecodeError):
            return {"schema_version": 1, "candidates": []}

    def upsert(self, experiment, rating, correlation, active_snapshot):
        """Persist one manually reviewable candidate."""
        records = self.upsert_many([(experiment, rating, correlation, active_snapshot)])
        return records[0] if records else None

    def upsert_many(self, items):
        """Upsert a batch with one read and one atomic write.

        A round can produce several eligible candidates. Writing the same
        canonical pool once per candidate creates avoidable I/O and increases
        the chance of observing a half-updated review queue during a crash.
        """
        items = list(items or [])
        if not items:
            return []
        data = self._load()
        data.setdefault("schema_version", 1)
        candidates = data.setdefault("candidates", [])
        records = []
        for experiment, rating, correlation, active_snapshot in items:
            existing = next(
                (x for x in candidates
                 if isinstance(x, dict) and x.get("alpha_id") == experiment.alpha_id),
                None,
            )
            record = {
                "alpha_id": experiment.alpha_id,
                "proposal_id": experiment.proposal_id,
                "expression": experiment.expression,
                "metrics": experiment.metrics,
                "health": experiment.health,
                "validation_status": experiment.validation_status,
                "yearly_evidence": experiment.yearly_evidence,
                "validation_report": experiment.validation_report,
                "research_classification": getattr(experiment, "research_classification", None),
                "robustness_status": (getattr(experiment, "robustness_evidence", None) or {}).get("decision")
                    if isinstance(getattr(experiment, "robustness_evidence", None), dict) else getattr(experiment, "validation_status", None),
                "statistical_status": (getattr(experiment, "validation_report", None) or {}).get("statistical_evidence", {}).get("statistical_decision")
                    if isinstance(getattr(experiment, "validation_report", None), dict) else None,
                "incremental_status": (getattr(experiment, "incremental_evidence", None) or {}).get("decision")
                    if isinstance(getattr(experiment, "incremental_evidence", None), dict) else "UNKNOWN",
                "nearest_alpha": (getattr(experiment, "incremental_evidence", None) or {}).get("nearest_alpha_id")
                    if isinstance(getattr(experiment, "incremental_evidence", None), dict) else None,
                "max_abs_corr": (getattr(experiment, "incremental_evidence", None) or {}).get("max_abs_corr")
                    if isinstance(getattr(experiment, "incremental_evidence", None), dict) else None,
                "rating": rating,
                "self_correlation": correlation,
                "active_snapshot": active_snapshot,
                # Updating an already-known Alpha is not a new memory event.
                "added_at": (existing or {}).get("added_at", time.time()),
                "submission": "MANUAL_REQUIRED",
            }
            candidates[:] = [
                x for x in candidates
                if isinstance(x, dict) and x.get("alpha_id") != experiment.alpha_id
            ]
            candidates.append(record)
            records.append(record)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        atomic_write_json_if_changed(self.path, data)
        return records
