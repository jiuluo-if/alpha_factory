"""Refresh settled platform SELF_CORRELATION for real DONE trajectory rows.

This is a read-only platform operation.  It never rewrites trajectory,
checkpoint, proposals, or memory; the shared evidence module only updates its
re-fetchable ``evidence_cache.json`` sidecar.

Examples:
  python scripts/refresh_self_correlation.py --since 2026-09-07 --until 2026-09-09 --dry-run
  python scripts/refresh_self_correlation.py --since 2026-09-07 --until 2026-09-09
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wqb_agent.client import WQBClient
from wqb_agent.config import normalize_config
from wqb_agent.evidence import refresh_self_correlation_cache
from wqb_agent.pre_correlation import pre_self_correlation_eligibility
from wqb_agent.state import Trajectory


def _timestamp(value, *, end=False):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10:
        date = dt.date.fromisoformat(text)
        if end:
            date += dt.timedelta(days=1)
        parsed = dt.datetime.combine(
            date, dt.time.min,
            tzinfo=dt.timezone(dt.timedelta(hours=8)),
        )
    else:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone(dt.timedelta(hours=8)))
    return parsed.timestamp()


def load_pre_correlation_policy(config_path="config.json"):
    """只读读取 config 的 delay / quality policy / trajectory 窗口。

    缺失或损坏时返回 ``(None, {}, None)``；调用方据此保持 fail-closed，
    不会用默认阈值伪造资格。
    """
    try:
        with open(config_path, encoding="utf-8-sig") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return None, {}, None
    try:
        typed = normalize_config(raw)
    except (TypeError, ValueError):
        return None, {}, None
    settings = getattr(typed.simulation_config, "settings", None) or {}
    quality = getattr(typed.runtime, "quality", None) or {}
    window = getattr(typed.runtime, "trajectory_window", None)
    return settings.get("delay"), dict(quality), window


def load_trajectory_rows(state_dir, *, window=None, since=None, until=None):
    """复用 Trajectory owner 的 canonical merge，不被内存窗口截断。

    用第二个 JSONL parser 会让手工脚本在“一个 Experiment 占多行”时与 Agent
    选出不同集合；``max_len`` 只是内存 recent window，历史 backfill 必须走
    owner 的 canonical history streaming，才能既保持 settled revision 合并
    语义，也覆盖 ``trajectory_window`` 之外的老 Experiment。
    """
    path = os.path.join(state_dir, "trajectory.jsonl")
    try:
        limit = max(1, int(window))
    except (TypeError, ValueError):
        limit = 256
    trajectory = Trajectory(path=path, max_len=limit, persist=True)
    return [
        dict(row)
        for row in trajectory.iter_canonical_rows(since=since, until=until)
    ]


def pre_correlation_selection(rows, since=None, until=None, limit=None, *,
                              delay=None, quality_policy=None):
    """Shared selector: same gate as the Agent, plus an auditable reason tally."""
    selected = {}
    reason_counts = {}
    for row in rows or ():
        if not isinstance(row, dict) or row.get("status") != "DONE":
            continue
        alpha_id = row.get("alpha_id")
        created_at = row.get("created_at")
        if not alpha_id or not isinstance(created_at, (int, float)):
            continue
        if since is not None and created_at < since:
            continue
        if until is not None and created_at >= until:
            continue
        report = pre_self_correlation_eligibility(
            row.get("metrics"),
            delay=delay,
            quality_policy=quality_policy,
            health=row.get("health"),
        )
        if not report["eligible"]:
            for reason in report["reasons"]:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            continue
        selected[str(alpha_id)] = float(created_at)
    ordered = [alpha_id for alpha_id, _ in sorted(
        selected.items(), key=lambda item: (item[1], item[0])
    )]
    limited = ordered if limit is None else ordered[-max(0, int(limit)):]
    return {
        "alpha_ids": limited,
        "eligible": len(ordered),
        "reason_counts": reason_counts,
    }


def select_alpha_ids(rows, since=None, until=None, limit=None, *,
                     delay=None, quality_policy=None):
    """Select unique real Alpha ids that pass the shared pre-correlation gate."""
    return pre_correlation_selection(
        rows, since, until, limit, delay=delay, quality_policy=quality_policy
    )["alpha_ids"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default=".wqb_state")
    parser.add_argument("--config", default="config.json",
                        help="Path to config JSON providing delay/quality policy")
    parser.add_argument("--since", default=None, help="ISO date/time, inclusive")
    parser.add_argument("--until", default=None, help="ISO date/time, exclusive")
    parser.add_argument("--limit", type=int, default=64)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    since = _timestamp(args.since)
    until = _timestamp(args.until, end=True)
    if since is not None and until is not None and since >= until:
        parser.error("--since 必须早于 --until")
    delay, quality_policy, window = load_pre_correlation_policy(args.config)
    rows = load_trajectory_rows(
        args.state_dir, window=window, since=since, until=until
    )
    selection = pre_correlation_selection(
        rows, since, until, args.limit, delay=delay, quality_policy=quality_policy
    )
    alpha_ids = selection["alpha_ids"]
    result = {
        "state_dir": args.state_dir,
        "config": args.config,
        "delay": delay,
        "trajectory_window": window,
        "eligible": selection["eligible"],
        "ineligible_reasons": selection["reason_counts"],
        "selected": len(alpha_ids),
        "alpha_ids": alpha_ids,
        "dry_run": args.dry_run,
        "network_write": False,
        "trajectory_write": False,
    }
    if not args.dry_run and alpha_ids:
        client = WQBClient()
        result["refreshed"] = refresh_self_correlation_cache(
            client, args.state_dir, alpha_ids, timeout_sec=args.timeout
        )
    else:
        result["refreshed"] = 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
