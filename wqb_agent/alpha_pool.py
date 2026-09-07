"""Trusted, as-of Alpha pool snapshots for incremental evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True)
class AlphaPoolSnapshot:
    snapshot_id: str
    as_of: float | None
    policy: str
    members: tuple

    def as_dict(self):
        return {"snapshot_id": self.snapshot_id, "as_of": self.as_of,
                "policy": self.policy, "members": list(self.members)}


def build_pool_snapshot(rows, *, as_of=None, snapshot_id=None,
                        policy="DONE_CHECKS_IDENTITY_BEHAVIOR"):
    accepted = []
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").upper() != "DONE":
            continue
        if row.get("checks_passed") is not True or not row.get("identity"):
            continue
        if not isinstance(row.get("behavior_series"), dict):
            continue
        entered = row.get("pool_entered_at")
        if as_of is not None:
            if not isinstance(entered, (int, float)) or entered > as_of:
                continue
        normalized = dict(row)
        if "series" not in normalized:
            normalized["series"] = normalized.get("behavior_series")
        accepted.append(normalized)
    accepted.sort(key=lambda item: str(item.get("alpha_id") or item.get("candidate_id") or ""))
    if snapshot_id is None:
        payload = json.dumps({"as_of": as_of, "policy": policy,
                              "members": accepted}, sort_keys=True, separators=(",", ":"), default=str)
        snapshot_id = "pool-" + hashlib.sha256(payload.encode()).hexdigest()[:16]
    return AlphaPoolSnapshot(snapshot_id, as_of, policy, tuple(accepted))
