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

from wqb_agent.artifacts import iter_jsonl_objects
from wqb_agent.client import WQBClient
from wqb_agent.evidence import refresh_self_correlation_cache
from wqb_agent.metrics import checks_ready_for_self_correlation_refresh


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


def select_alpha_ids(rows, since=None, until=None, limit=None):
    """Select unique real Alpha ids with all non-correlation checks passing."""
    selected = {}
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
        if not checks_ready_for_self_correlation_refresh(row.get("metrics")):
            continue
        selected[str(alpha_id)] = float(created_at)
    ordered = [alpha_id for alpha_id, _ in sorted(
        selected.items(), key=lambda item: (item[1], item[0])
    )]
    return ordered if limit is None else ordered[-max(0, int(limit)):]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default=".wqb_state")
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
    path = os.path.join(args.state_dir, "trajectory.jsonl")
    rows = iter_jsonl_objects(path)
    alpha_ids = select_alpha_ids(rows, since, until, args.limit)
    result = {
        "state_dir": args.state_dir,
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
