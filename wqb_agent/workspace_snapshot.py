"""One-command, read-only summaries of local workspace evidence."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re

from .artifacts import iter_jsonl_objects
from .checkpoints import CheckpointStore
from .state import Trajectory


_CHECKPOINT_NAME = re.compile(r"round_\d+\.checkpoint\.json")
_FIXED_ARTIFACT_NAMES = (
    "trajectory.jsonl", "trial_ledger.jsonl", "submission_pool.json",
    "fields_cache.json", "evidence_cache.json", "factory_session.json",
    "sims_results.json", "validation_reports.jsonl", "proposals.json",
    "experience.json",
)
_DOCTOR_ARTIFACT_NAMES = frozenset(_FIXED_ARTIFACT_NAMES[:8])


def is_doctor_artifact(name):
    return name in _DOCTOR_ARTIFACT_NAMES or bool(
        re.fullmatch(r"round_\d+\.checkpoint\.json", name)
        or re.fullmatch(r"active_alphas_\d{8}\.json", name)
    )


@dataclass(frozen=True)
class ArtifactInfo:
    name: str
    exists: bool = False
    readable: bool = False
    kind: str = "other"
    schema_version: object = None


@dataclass(frozen=True)
class ArtifactInventory:
    """Ephemeral file metadata; no artifact payload is retained here."""

    entries: tuple = ()

    def info(self, name):
        for entry in self.entries:
            if entry.name == name:
                return entry
        return ArtifactInfo(name)


@dataclass(frozen=True)
class LedgerSummary:
    """Lifecycle evidence owned by TrialLedger, not the trajectory projection."""

    committed: frozenset = frozenset()
    submitted: frozenset = frozenset()
    simulation_settled: frozenset = frozenset()
    research_settled: frozenset = frozenset()
    settlement_ids: frozenset = frozenset()
    duplicate_settlements: int = 0


@dataclass(frozen=True)
class ValidationSummary:
    parent_ids: frozenset = frozenset()
    plan_pairs: tuple = ()


@dataclass(frozen=True)
class SubmissionPoolSummary:
    candidate_identities: tuple = ()


@dataclass(frozen=True)
class TrajectorySummary:
    records: int = 0
    latest_round: int | None = None
    submit_unknown_count: int = 0
    pending_validation_count: int = 0
    trajectory_ids: frozenset = frozenset()
    settlement_ids: frozenset = frozenset()
    committed: frozenset = frozenset()
    submitted: frozenset = frozenset()
    settled: frozenset = frozenset()
    duplicate_settlements: int = 0


@dataclass(frozen=True)
class WorkspaceSnapshot:
    """Ephemeral facts only; it is never persisted or treated as state truth."""

    state_dir: str
    checkpoint_records: tuple
    trajectory: TrajectorySummary
    inventory: ArtifactInventory = ArtifactInventory()
    ledger: LedgerSummary = LedgerSummary()
    validation: ValidationSummary = ValidationSummary()
    submission_pool: SubmissionPoolSummary = SubmissionPoolSummary()
    proposal_round: object = None
    proposal_count: int = 0
    current_best: object = None
    evidence_cache_entries: int = 0

    @property
    def unfinished_checkpoint_paths(self):
        return tuple(
            sorted(
                os.path.basename(record["path"])
                for record in self.checkpoint_records
                if record["malformed"]
                or not record["checkpoint"].get("complete", False)
            )
        )


def _trajectory_summary(state_dir):
    trajectory = Trajectory(path=os.path.join(state_dir, "trajectory.jsonl"))
    trajectory_ids = set()
    settlement_ids = set()
    committed = set()
    submitted = set()
    settled = set()
    summary = {
        "records": 0,
        "latest_round": None,
        "submit_unknown_count": 0,
        "pending_validation_count": 0,
        "duplicate_settlements": 0,
    }
    for row in trajectory.iter_rows() or ():
        summary["records"] += 1
        if isinstance(row.get("round"), int):
            summary["latest_round"] = max(
                summary["latest_round"] or row["round"], row["round"]
            )
        if row.get("status") == "SUBMIT_UNKNOWN":
            summary["submit_unknown_count"] += 1
        if row.get("validation_status") in {"PENDING", "UNVALIDATED"}:
            summary["pending_validation_count"] += 1
        for key in (row.get("id"), row.get("alpha_id"), row.get("proposal_id")):
            if key:
                trajectory_ids.add(str(key))
        proposal_id = row.get("proposal_id")
        phase = row.get("phase")
        if proposal_id:
            if phase == "simulation_committed":
                committed.add(str(proposal_id))
            elif phase in {"simulation_submitted", "simulation_settled"}:
                submitted.add(str(proposal_id))
            elif phase == "research_outcome_settled":
                settled.add(str(proposal_id))
        if phase == "research_outcome_settled":
            settlement_id = (row.get("settlement") or {}).get("settlement_id")
            if settlement_id and str(settlement_id) in settlement_ids:
                summary["duplicate_settlements"] += 1
            elif settlement_id:
                settlement_ids.add(str(settlement_id))
    return TrajectorySummary(
        **summary,
        trajectory_ids=frozenset(trajectory_ids),
        settlement_ids=frozenset(settlement_ids),
        committed=frozenset(committed),
        submitted=frozenset(submitted),
        settled=frozenset(settled),
    )


def _load_json(path):
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return True, json.load(handle)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False, None


def _kind(name):
    if name.endswith(".jsonl"):
        return "jsonl"
    if name.endswith(".json"):
        return "json"
    return "other"


def _inventory(state_dir, names, checkpoint_records):
    names = set(names)
    checkpoint_by_name = {
        os.path.basename(record["path"]): record
        for record in checkpoint_records
    }
    all_names = names | set(_FIXED_ARTIFACT_NAMES)
    entries = []
    payloads = {}
    for name in sorted(all_names):
        path = os.path.join(state_dir, name)
        exists = name in names
        readable = exists and os.path.isfile(path) and os.access(path, os.R_OK)
        kind = _kind(name)
        schema_version = None
        if readable and _CHECKPOINT_NAME.fullmatch(name):
            record = checkpoint_by_name.get(name)
            if record is None or record["malformed"]:
                schema_version = "UNREADABLE"
            else:
                schema_version = record["checkpoint"].get("schema_version", "LEGACY")
        elif readable and kind == "json" and (
            name in _FIXED_ARTIFACT_NAMES or is_doctor_artifact(name)
        ):
            valid, payload = _load_json(path)
            if not valid:
                schema_version = "UNREADABLE"
            elif isinstance(payload, dict):
                schema_version = payload.get("schema_version", "LEGACY")
                payloads[name] = payload
            else:
                schema_version = "INVALID"
                payloads[name] = payload
        elif readable and kind == "jsonl":
            schema_version = "JSONL_PRESENT"
        elif readable:
            schema_version = "PRESENT"
        entries.append(ArtifactInfo(name, exists, readable, kind, schema_version))
    return ArtifactInventory(tuple(entries)), payloads


def _ledger_summary(path):
    committed = set()
    submitted = set()
    simulation_settled = set()
    research_settled = set()
    settlement_ids = set()
    duplicate_settlements = 0
    for row in iter_jsonl_objects(path):
        proposal_id = row.get("proposal_id")
        phase = row.get("phase")
        if proposal_id and phase == "simulation_committed":
            committed.add(str(proposal_id))
        elif proposal_id and phase in {"simulation_submitted", "simulation_settled"}:
            submitted.add(str(proposal_id))
        if proposal_id and phase == "simulation_settled":
            simulation_settled.add(str(proposal_id))
        if proposal_id and phase == "research_outcome_settled":
            research_settled.add(str(proposal_id))
        if phase != "research_outcome_settled":
            continue
        settlement_id = (row.get("settlement") or {}).get("settlement_id")
        if not settlement_id:
            continue
        settlement_id = str(settlement_id)
        if settlement_id in settlement_ids:
            duplicate_settlements += 1
        else:
            settlement_ids.add(settlement_id)
    return LedgerSummary(
        committed=frozenset(committed),
        submitted=frozenset(submitted),
        simulation_settled=frozenset(simulation_settled),
        research_settled=frozenset(research_settled),
        settlement_ids=frozenset(settlement_ids),
        duplicate_settlements=duplicate_settlements,
    )


def _validation_summary(path):
    parent_ids = set()
    plan_pairs = []
    for row in iter_jsonl_objects(path):
        if row.get("parent_id"):
            parent_ids.add(str(row["parent_id"]))
        nested = row.get("report")
        if isinstance(nested, dict):
            plan_pairs.append((row.get("plan_id"), nested.get("plan_id")))
    return ValidationSummary(frozenset(parent_ids), tuple(plan_pairs))


def _submission_pool_summary(payload):
    identities = []
    rows = payload.get("candidates") if isinstance(payload, dict) else []
    for row in rows or []:
        if isinstance(row, dict):
            identities.append(frozenset(str(row.get(key)) for key in ("alpha_id", "proposal_id")))
    return SubmissionPoolSummary(tuple(identities))


def read_workspace_snapshot(state_dir):
    """Read checkpoint and trajectory facts once for one command lifecycle."""
    state_dir = os.fspath(state_dir)
    try:
        names = os.listdir(state_dir)
    except OSError:
        names = []
    store = CheckpointStore(state_dir)
    checkpoint_records = tuple(store.scan(names=names))
    inventory, payloads = _inventory(state_dir, names, checkpoint_records)
    proposals = payloads.get("proposals.json")
    experience = payloads.get("experience.json")
    evidence_cache = payloads.get("evidence_cache.json")
    return WorkspaceSnapshot(
        state_dir=state_dir,
        checkpoint_records=checkpoint_records,
        trajectory=_trajectory_summary(state_dir),
        inventory=inventory,
        ledger=_ledger_summary(os.path.join(state_dir, "trial_ledger.jsonl")),
        validation=_validation_summary(os.path.join(state_dir, "validation_reports.jsonl")),
        submission_pool=_submission_pool_summary(payloads.get("submission_pool.json")),
        proposal_round=proposals.get("round_no") if isinstance(proposals, dict) else None,
        proposal_count=(len(proposals.get("proposals") or [])
                        if isinstance(proposals, dict) else 0),
        current_best=(experience.get("current_best")
                      if isinstance(experience, dict) else None),
        evidence_cache_entries=(len(evidence_cache)
                               if isinstance(evidence_cache, dict) else 0),
    )
