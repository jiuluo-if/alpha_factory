"""Append-only, bounded-memory trial lifecycle ledger."""

from __future__ import annotations

import hashlib
import time
from collections import Counter, defaultdict

from .artifacts import append_jsonl_if_unique, iter_jsonl_objects
from .expression import canonical_expression


PHASES = {"generated", "preflight", "submitted", "completed"}


def _text(value, default="unknown"):
    return str(value) if isinstance(value, (str, int, float, bool)) else default


class TrialLedger:
    """Record proposal lifecycle facts without replacing trajectory/checkpoint."""

    SCHEMA_VERSION = 1

    def __init__(self, path):
        self.path = path

    @staticmethod
    def _trial_id(trial):
        if isinstance(trial, dict):
            return _text(trial.get("id") or trial.get("proposal_id"), "")
        return _text(getattr(trial, "id", None) or getattr(trial, "proposal_id", None), "")

    @staticmethod
    def _value(trial, key, default=None):
        if isinstance(trial, dict):
            return trial.get(key, default)
        return getattr(trial, key, default)

    def record(self, trial, phase, *, outcome=None, timestamp=None):
        if phase not in PHASES:
            raise ValueError(f"未知 trial phase: {phase}")
        trial_id = self._trial_id(trial)
        expression = _text(self._value(trial, "expression", ""), "")
        fingerprint = _text(
            self._value(trial, "submission_fingerprint", "")
            or hashlib.sha256(canonical_expression(expression).encode()).hexdigest(),
            "",
        )
        state = _text(self._value(trial, "status"), "UNKNOWN")
        identity = f"{trial_id}|{phase}|{state}|{outcome or ''}"
        event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        fields = self._value(trial, "fields_used", [])
        if not isinstance(fields, (list, tuple)):
            fields = []
        row = {
            "schema_version": self.SCHEMA_VERSION,
            "event_id": event_id,
            "trial_id": trial_id,
            "proposal_id": self._value(trial, "proposal_id"),
            "phase": phase,
            "outcome": outcome or state,
            "status": state,
            "round": self._value(trial, "round"),
            "expression_fingerprint": fingerprint,
            "template_family": self._value(trial, "template_family") or "unknown",
            "lineage_id": self._value(trial, "lineage_id") or "unknown",
            "template_id": self._value(trial, "template_id") or "unknown",
            "fields": sorted({_text(field) for field in fields if field is not None}),
            "alpha_id": self._value(trial, "alpha_id"),
            "recorded_at": timestamp if timestamp is not None else time.time(),
        }
        return append_jsonl_if_unique(self.path, row, ("event_id",))

    def summarize(self):
        phase_counts = Counter()
        status_counts = Counter()
        groups = {key: defaultdict(Counter) for key in
                  ("template_family", "lineage_id", "template_id", "field")}
        events = 0
        for row in iter_jsonl_objects(self.path):
            events += 1
            phase_counts[row.get("phase", "unknown")] += 1
            status_counts[row.get("status", "UNKNOWN")] += 1
            for key in ("template_family", "lineage_id", "template_id"):
                groups[key][row.get(key, "unknown")][row.get("phase", "unknown")] += 1
            for field in row.get("fields") or []:
                groups["field"][field][row.get("phase", "unknown")] += 1
        return {
            "schema_version": self.SCHEMA_VERSION,
            "events": events,
            "phase_counts": dict(phase_counts),
            "status_counts": dict(status_counts),
            "trial_counts": {
                key: {group: dict(counts) for group, counts in values.items()}
                for key, values in groups.items()
            },
        }
