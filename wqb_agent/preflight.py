"""Local, read-only takeover preflight for an Agent session."""

from __future__ import annotations

import json
import os
import re

from .audit import audit_state
from .config import AppConfig, parse_config
from .doctor import run_doctor


def _count_unfinished_checkpoints(state_dir):
    unfinished = []
    for name in os.listdir(state_dir) if os.path.isdir(state_dir) else ():
        if not re.fullmatch(r"round_\d+\.checkpoint\.json", name):
            continue
        path = os.path.join(state_dir, name)
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict) or not payload.get("complete", False):
                unfinished.append(name)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            unfinished.append(name)
    return sorted(unfinished)


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as handle:
            value = json.load(handle)
        return value
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return default


def run_takeover_preflight(raw_config):
    """Return one bounded evidence bundle before suggestion or execution.

    The result is deliberately derived at call time and is never persisted.
    It tells a newly attached Agent what to read first without creating a
    second state machine or treating cache/report files as platform truth.
    """
    config = raw_config if isinstance(raw_config, AppConfig) else parse_config(raw_config)
    state_dir = config.agent.get("state_dir", ".wqb_state")
    doctor = run_doctor(config, offline=True)
    state = audit_state(state_dir)
    unfinished = _count_unfinished_checkpoints(state_dir)
    proposals = _read_json(os.path.join(state_dir, "proposals.json"), {})
    evidence_cache = _read_json(os.path.join(state_dir, "evidence_cache.json"), {})
    experience = _read_json(os.path.join(state_dir, "experience.json"), {})
    trajectory_path = os.path.join(state_dir, "trajectory.jsonl")
    trajectory_count = 0
    latest_round = None
    try:
        with open(trajectory_path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
                if isinstance(row, dict):
                    trajectory_count += 1
                    if isinstance(row.get("round"), int):
                        latest_round = max(latest_round or row["round"], row["round"])
    except OSError:
        pass
    blocking = list(unfinished)
    if not state.get("ok"):
        blocking.extend(state.get("errors") or [])
    status = "READY" if not blocking else "BLOCKED"
    return {
        "status": status,
        "network_write": False,
        "state_dir": state_dir,
        "blocking": sorted(set(blocking)),
        "doctor": doctor,
        "state": state,
        "unfinished_checkpoints": unfinished,
        "trajectory": {"records": trajectory_count, "latest_round": latest_round},
        "current_best": experience.get("current_best") if isinstance(experience, dict) else None,
        "evidence_cache_entries": len(evidence_cache) if isinstance(evidence_cache, dict) else 0,
        "proposal_round": proposals.get("round_no") if isinstance(proposals, dict) else None,
        "proposal_count": len(proposals.get("proposals") or []) if isinstance(proposals, dict) else 0,
    }
