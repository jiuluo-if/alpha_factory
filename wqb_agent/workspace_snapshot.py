"""One-command, read-only summaries of local workspace evidence."""

from __future__ import annotations

from dataclasses import dataclass
import os

from .checkpoints import CheckpointStore
from .state import Trajectory


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


def read_workspace_snapshot(state_dir):
    """Read checkpoint and trajectory facts once for one command lifecycle."""
    state_dir = os.fspath(state_dir)
    return WorkspaceSnapshot(
        state_dir=state_dir,
        checkpoint_records=tuple(CheckpointStore(state_dir).scan()),
        trajectory=_trajectory_summary(state_dir),
    )
