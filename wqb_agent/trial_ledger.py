"""Append-only, bounded-memory trial lifecycle ledger."""

from __future__ import annotations

import hashlib
import time
from collections import Counter, defaultdict

from .artifacts import append_jsonl_if_unique, iter_jsonl_objects
from .expression import canonical_expression
from .identity import candidate_identity
from .search_policy import structural_fingerprint


PHASES = {
    "generated", "preflight", "submitted", "completed",
    "candidate_generated", "candidate_rejected", "preflight_accepted",
    "candidate_admitted",
}


def _text(value, default="unknown"):
    return str(value) if isinstance(value, (str, int, float, bool)) else default


class TrialLedger:
    """Record proposal lifecycle facts without replacing trajectory/checkpoint."""

    SCHEMA_VERSION = 2

    def __init__(self, path):
        self.path = path

    @staticmethod
    def _trial_id(trial):
        if isinstance(trial, dict):
            return _text(trial.get("candidate_id") or trial.get("id") or trial.get("proposal_id"), "")
        return _text(getattr(trial, "candidate_id", None) or getattr(trial, "id", None) or getattr(trial, "proposal_id", None), "")

    @staticmethod
    def _value(trial, key, default=None):
        if isinstance(trial, dict):
            return trial.get(key, default)
        return getattr(trial, key, default)

    def record(self, trial, phase, *, outcome=None, reason=None, reason_code=None,
               stage=None, timestamp=None):
        if phase not in PHASES:
            raise ValueError(f"未知 trial phase: {phase}")
        candidate_id = self._value(trial, "candidate_id") or candidate_identity(trial, round_no=self._value(trial, "round"))
        trial_id = self._trial_id(trial) or candidate_id
        expression = _text(self._value(trial, "expression", ""), "")
        fingerprint = _text(
            self._value(trial, "submission_fingerprint", "")
            or hashlib.sha256(canonical_expression(expression).encode()).hexdigest(),
            "",
        )
        state = _text(self._value(trial, "status"), "UNKNOWN")
        identity = f"{candidate_id}|{self._value(trial, 'proposal_id') or ''}|{phase}|{state}|{outcome or ''}|{reason_code or ''}|{reason or ''}"
        event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        fields = self._value(trial, "fields_used", [])
        if not isinstance(fields, (list, tuple)):
            fields = []
        row = {
            "schema_version": self.SCHEMA_VERSION,
            "event_id": event_id,
            "trial_id": trial_id,
            "candidate_id": candidate_id,
            "proposal_id": self._value(trial, "proposal_id"),
            "phase": phase,
            "event_type": phase,
            "outcome": outcome or state,
            "reason": reason,
            "reason_code": reason_code,
            "stage": stage,
            "status": state,
            "sharpe": self._value(self._value(trial, "metrics", {}) or {}, "sharpe"),
            "fitness": self._value(self._value(trial, "metrics", {}) or {}, "fitness"),
            "round": self._value(trial, "round"),
            "expression_fingerprint": fingerprint,
            "template_family": self._value(trial, "template_family") or "unknown",
            "lineage_id": self._value(trial, "lineage_id") or "unknown",
            "template_id": self._value(trial, "template_id") or "unknown",
            "dataset_family": self._value(trial, "dataset_family") or self._value(trial, "datasets") or "unknown",
            "structural_fingerprint": structural_fingerprint(expression, fields),
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
        trial_ids = set()
        generated_trials = set()
        sharpe_count = 0
        sharpe_mean = 0.0
        sharpe_m2 = 0.0
        event_type_counts = Counter()
        rejected_candidates = set()
        submitted_trials = set()
        accepted_candidates = set()
        completed_trials = set()
        admitted_families = Counter()
        admitted_structures = Counter()
        structural_trials = set()
        family_trials = set()
        latest_by_trial = {}
        for row in iter_jsonl_objects(self.path):
            events += 1
            trial_id = row.get("trial_id")
            if trial_id:
                trial_ids.add(trial_id)
            if row.get("structural_fingerprint"):
                structural_trials.add(row.get("structural_fingerprint"))
            family_trials.add((row.get("template_family", "unknown"), row.get("dataset_family", "unknown").__str__()))
            if row.get("phase") in {"generated", "candidate_generated"} and trial_id:
                generated_trials.add(trial_id)
            event_type_counts[row.get("event_type") or row.get("phase", "unknown")] += 1
            if row.get("phase") == "candidate_rejected" and row.get("candidate_id"):
                rejected_candidates.add(row.get("candidate_id"))
            if row.get("phase") == "preflight_accepted" and row.get("candidate_id"):
                accepted_candidates.add(row.get("candidate_id"))
            if row.get("phase") == "submitted" and row.get("proposal_id"):
                submitted_trials.add(row.get("proposal_id"))
            if row.get("phase") == "candidate_admitted":
                admitted_families[str(row.get("template_family") or "unknown")] += 1
                admitted_structures[str(row.get("structural_fingerprint") or "unknown")] += 1
            if trial_id:
                latest_by_trial[trial_id] = row
            if row.get("phase") == "completed":
                if row.get("proposal_id") or trial_id:
                    completed_trials.add(row.get("proposal_id") or trial_id)
                value = row.get("sharpe")
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    value = None
                if value is not None:
                    sharpe_count += 1
                    delta = value - sharpe_mean
                    sharpe_mean += delta / sharpe_count
                    sharpe_m2 += delta * (value - sharpe_mean)
            phase_counts[row.get("phase", "unknown")] += 1
            status_counts[row.get("status", "UNKNOWN")] += 1
            for key in ("template_family", "lineage_id", "template_id"):
                groups[key][row.get(key, "unknown")][row.get("phase", "unknown")] += 1
            for field in row.get("fields") or []:
                groups["field"][field][row.get("phase", "unknown")] += 1
        return {
            "schema_version": self.SCHEMA_VERSION,
            "events": events,
            "trial_count": len(trial_ids),
            "generated_trials": len(generated_trials),
            "candidate_generated_count": len(generated_trials),
            "candidate_count": len(generated_trials),
            "candidate_rejected_count": len(rejected_candidates),
            "rejected_candidate_count": len(rejected_candidates),
            "preflight_accepted_count": len(accepted_candidates),
            "submitted_count": len(submitted_trials),
            "completed_count": len(completed_trials),
            "unique_candidate_count": len({row.get("candidate_id") for row in iter_jsonl_objects(self.path) if row.get("candidate_id")}),
            "unique_proposal_count": len({row.get("proposal_id") for row in iter_jsonl_objects(self.path) if row.get("proposal_id")}),
            "simulation_count": len(submitted_trials),
            "family_counts": dict(admitted_families),
            "structural_family_counts": dict(admitted_structures),
            "structural_trial_count": len(structural_trials),
            "effective_trial_count": max(1, len(structural_trials or family_trials or trial_ids)),
            "arm_counts": self._arm_counts(latest_by_trial),
            "event_type_counts": dict(event_type_counts),
            "trial_sharpe_count": sharpe_count,
            "trial_sharpe_mean": sharpe_mean if sharpe_count else None,
            "trial_sharpe_std": (
                (sharpe_m2 / sharpe_count) ** 0.5 if sharpe_count > 1 else None
            ),
            "phase_counts": dict(phase_counts),
            "status_counts": dict(status_counts),
            "invariant": {
                "candidate_generated_ge_preflight_accepted_ge_submitted": (
                    len(generated_trials) >= len(accepted_candidates) >= len(submitted_trials)
                ),
                "note": "append-only recovery may temporarily leave accepted/submitted events incomplete",
            },
            "trial_counts": {
                key: {group: dict(counts) for group, counts in values.items()}
                for key, values in groups.items()
            },
        }

    @staticmethod
    def _arm_counts(latest_by_trial):
        result = defaultdict(lambda: {
            "admitted": 0, "submitted": 0, "evaluated": 0, "done": 0,
            "failed_research": 0, "failed_infra": 0, "skipped_local": 0,
            "completed": 0, "pending": 0, "running": 0, "unknown": 0,
            "reserved": 0, "reward_sum": 0.0, "reward_count": 0, "reward": 0.0,
        })
        for row in latest_by_trial.values():
            datasets = row.get("dataset_family") or "unknown-dataset"
            if isinstance(datasets, list):
                datasets = "+".join(sorted(str(item) for item in datasets))
            arm = f"{datasets}::{row.get('template_family') or 'unknown-mechanism'}"
            status = str(row.get("status") or "UNKNOWN").upper()
            if row.get("phase") in {"candidate_admitted", "preflight_accepted", "submitted", "completed"}:
                result[arm]["admitted"] += 1
            if row.get("phase") in {"submitted", "completed"}:
                result[arm]["submitted"] += 1
            if status == "DONE":
                result[arm]["completed"] += 1
                result[arm]["done"] += 1
                result[arm]["evaluated"] += 1
                result[arm]["reward_count"] += 1
                try:
                    reward = float(row.get("fitness", 0.0) or 0.0)
                    result[arm]["reward"] += reward
                    result[arm]["reward_sum"] += reward
                except (TypeError, ValueError):
                    pass
            elif status in {"PENDING", "SUBMITTING"}:
                result[arm]["pending"] += 1
            elif status == "RUNNING":
                result[arm]["running"] += 1
            elif status in {"UNKNOWN", "SUBMIT_UNKNOWN"}:
                result[arm]["unknown"] += 1
            elif status == "FAILED":
                result[arm]["completed"] += 1
                if str(row.get("reason_code") or row.get("reason") or "").upper() in {"INFRA", "RATE_LIMIT", "AUTH", "TIMEOUT"}:
                    result[arm]["failed_infra"] += 1
                else:
                    result[arm]["failed_research"] += 1
        return dict(result)
