"""Durable checkpoint persistence and conservative unfinished-round scans."""

from __future__ import annotations

import json
import os
import re
import threading
import time

from .artifacts import atomic_write_json_if_changed
from .schema import CHECKPOINT_VERSION, CREATED_BY_VERSION, migrate_artifact

_CHECKPOINT_NAME = re.compile(r"round_(\d+)\.checkpoint\.json")
_REQUIRED_EXPERIMENT_FIELDS = {
    "id", "round", "hypothesis_id", "expression", "settings",
    "fields_used", "status",
}


class CheckpointStore:
    """Own only checkpoint file mechanics; never submits or appends trajectory."""

    def __init__(self, state_dir, lock=None):
        self.state_dir = state_dir
        self._lock = lock or threading.Lock()

    def path(self, round_no):
        return os.path.join(self.state_dir, f"round_{int(round_no)}.checkpoint.json")

    def write(self, round_no, hypothesis, experiments, complete):
        """Atomically persist one checkpoint and return whether bytes changed."""
        path = self.path(round_no)
        os.makedirs(self.state_dir, exist_ok=True)
        data = {
            "schema_version": CHECKPOINT_VERSION,
            "created_by_version": CREATED_BY_VERSION,
            "round_no": int(round_no),
            "hypothesis": hypothesis,
            "experiments": [exp.to_dict() for exp in experiments],
            "complete": bool(complete),
            "updated_at": time.time(),
        }
        with self._lock:
            return atomic_write_json_if_changed(
                path, data, ignored_keys=("updated_at",)
            )

    def load(self, round_no):
        """Load a validated checkpoint; malformed input returns ``None``."""
        path = self.path(round_no)
        try:
            with open(path, encoding="utf-8") as handle:
                data = migrate_artifact("checkpoint", json.load(handle))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        if (
            not isinstance(data, dict)
            or data.get("round_no") != int(round_no)
            or not isinstance(data.get("experiments"), list)
            or not isinstance(data.get("hypothesis"), dict)
        ):
            return None
        for row in data["experiments"]:
            if not isinstance(row, dict) or not _REQUIRED_EXPERIMENT_FIELDS.issubset(row):
                return None
            if (
                not isinstance(row["id"], (str, int))
                or not str(row["id"]).strip()
                or not isinstance(row["expression"], str)
                or not row["expression"].strip()
                or not isinstance(row["settings"], dict)
                or not isinstance(row["fields_used"], (list, tuple))
                or not isinstance(row["status"], str)
            ):
                return None
        return data

    def unfinished_except(self, round_no):
        """Return the lowest-round unfinished or malformed checkpoint path."""
        result = None
        result_round = None
        for record in self.scan():
            checkpoint_round = record["round_no"]
            if checkpoint_round == int(round_no):
                continue
            if result_round is not None and checkpoint_round >= result_round:
                continue
            if record["malformed"] or not record["checkpoint"].get("complete", False):
                result = record["path"]
                result_round = checkpoint_round
        return result

    def scan(self):
        """Return the authoritative read-only view of checkpoint files.

        Every consumer uses the same filename rule and ``load`` validation;
        malformed files remain visible so callers can fail closed.
        """
        try:
            names = os.listdir(self.state_dir)
        except OSError:
            return []
        records = []
        for name in sorted(names):
            match = _CHECKPOINT_NAME.fullmatch(name)
            if not match:
                continue
            round_no = int(match.group(1))
            path = os.path.join(self.state_dir, name)
            checkpoint = self.load(round_no)
            raw = {}
            try:
                with open(path, encoding="utf-8") as handle:
                    decoded = json.load(handle)
                if isinstance(decoded, dict):
                    raw = decoded
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
            records.append({
                "path": path,
                "round_no": round_no,
                "checkpoint": checkpoint if checkpoint is not None else raw,
                "malformed": checkpoint is None,
            })
        return records
