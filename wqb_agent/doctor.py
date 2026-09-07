"""Read-only local health diagnostics; no client construction or network."""

from __future__ import annotations

import json
import os
import re

from .config import AppConfig, parse_config
from .diagnostics import DiagnosticEvent


def _readable(path):
    return not os.path.exists(path) or os.access(path, os.R_OK)


def run_doctor(raw_config, *, offline=True):
    parsed = raw_config if isinstance(raw_config, AppConfig) else parse_config(raw_config)
    state_dir = parsed.agent.get("state_dir", ".wqb_state")
    result = {
        "config_valid": True,
        "offline": bool(offline),
        "state_dir": state_dir,
        "state_dir_writable": os.path.isdir(state_dir) and os.access(state_dir, os.W_OK),
        "ledger_readable": _readable(os.path.join(state_dir, "trial_ledger.jsonl")),
        "checkpoint_consistency": "PASS",
        "schema_versions": {},
        "operator_reference": os.path.exists(os.path.join(os.path.dirname(__file__), "..", "docs", "OPERATORS_CHEATSHEET.md")),
        "field_cache_status": "PRESENT" if os.path.exists(os.path.join(state_dir, "fields_cache.json")) else "MISSING",
        "unresolved_simulation_count": 0,
        "submit_unknown_count": 0,
        "pending_validation_count": 0,
        "pnl_capability": "UNAVAILABLE",
        "incremental_capability": "UNAVAILABLE",
    }
    unresolved = 0
    submit_unknown = 0
    pending_validation = 0
    for name in (os.listdir(state_dir) if os.path.isdir(state_dir) else ()):
        if not re.fullmatch(r"round_\d+\.checkpoint\.json", name):
            continue
        try:
            with open(os.path.join(state_dir, name), encoding="utf-8") as handle:
                checkpoint = json.load(handle)
            if not isinstance(checkpoint, dict) or not checkpoint.get("complete", False):
                unresolved += 1
            for row in checkpoint.get("experiments") or []:
                if isinstance(row, dict) and row.get("status") == "SUBMIT_UNKNOWN":
                    submit_unknown += 1
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            result["checkpoint_consistency"] = "FAIL"
            unresolved += 1
    trajectory_path = os.path.join(state_dir, "trajectory.jsonl")
    try:
        with open(trajectory_path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(row, dict):
                    continue
                if row.get("status") == "SUBMIT_UNKNOWN":
                    submit_unknown += 1
                if row.get("validation_status") in {"PENDING", "UNVALIDATED"}:
                    pending_validation += 1
    except OSError:
        pass
    result["unresolved_simulation_count"] = unresolved
    result["submit_unknown_count"] = submit_unknown
    result["pending_validation_count"] = pending_validation
    if unresolved:
        result["checkpoint_consistency"] = "UNRESOLVED"
    diagnostics = []
    if not result["state_dir_writable"]:
        diagnostics.append(DiagnosticEvent(
            "STATE_DIR_NOT_WRITABLE", "ERROR", "doctor", message=state_dir
        ).as_dict())
    if result["pnl_capability"] != "LIVE_VERIFIED":
        diagnostics.append(DiagnosticEvent(
            "PNL_CAPABILITY_UNAVAILABLE", "WARN", "incremental_value",
            message="仅允许记录 UNAVAILABLE，不生成行为相关性"
        ).as_dict())
    result["diagnostics"] = diagnostics
    artifact_names = [
        "trajectory.jsonl", "trial_ledger.jsonl", "submission_pool.json",
        "fields_cache.json", "evidence_cache.json", "factory_session.json",
        "sims_results.json", "validation_reports.jsonl",
    ]
    if os.path.isdir(state_dir):
        artifact_names.extend(
            name for name in os.listdir(state_dir)
            if re.fullmatch(r"round_\d+\.checkpoint\.json", name)
            or re.fullmatch(r"active_alphas_\d{8}\.json", name)
        )
    for name in artifact_names:
        path = os.path.join(state_dir, name)
        if not os.path.exists(path):
            continue
        try:
            if name.endswith(".json"):
                with open(path, encoding="utf-8") as handle:
                    payload = json.load(handle)
                result["schema_versions"][name] = payload.get("schema_version", "LEGACY") if isinstance(payload, dict) else "INVALID"
            else:
                with open(path, encoding="utf-8") as handle:
                    result["schema_versions"][name] = "JSONL_PRESENT"
        except (OSError, ValueError, json.JSONDecodeError):
            result["schema_versions"][name] = "UNREADABLE"
    return result
