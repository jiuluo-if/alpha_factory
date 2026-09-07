# -*- coding: utf-8 -*-
"""Analyze bulk-reconciled evidence cache: surface recovered pool-external candidates.

判定标准（与 AGENTS 晋升纪律一致的前置筛选）：
  - SELF_CORRELATION 已结算且 PASS (<0.5)
  - 历史 DONE 指标：Sharpe>=1.4 且 Fitness>=1.0
  - 健康 OK、无 CONCENTRATED_WEIGHT / LOW_SUB_UNIVERSE_SHARPE 失败

Usage:
  python scripts/analyze_bulk.py [--min-sharpe 1.4] [--min-fitness 1.0]
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wqb_agent.evidence import load_evidence_cache
from wqb_agent.artifacts import atomic_write_json_if_changed, iter_jsonl_objects
from wqb_agent.metrics import check_pass, num

RECOVERED_CANDIDATE_LIMIT = 256


def _retain_candidate(rows, candidate, limit=RECOVERED_CANDIDATE_LIMIT):
    """Keep only the strongest rebuildable candidates in memory."""
    rows.append(candidate)
    rows.sort(key=lambda item: -(item["fitness"] + item["sharpe"]))
    del rows[limit:]


def pass_correlation_ids(cache, max_correlation=0.5):
    """Return settled, low-correlation alpha ids from an evidence cache."""
    pass_ids = {}
    for aid, entry in (cache or {}).items():
        if not isinstance(entry, dict):
            continue
        sc = next((c for c in entry.get("checks") or []
                   if isinstance(c, dict)
                   and c.get("name") == "SELF_CORRELATION"), None)
        correlation = num(sc.get("value")) if sc else None
        if check_pass(sc) is True and correlation is not None and correlation < max_correlation:
            pass_ids[aid] = correlation
    return pass_ids


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state-dir", default=".wqb_state")
    ap.add_argument("--min-sharpe", type=float, default=1.4)
    ap.add_argument("--min-fitness", type=float, default=1.0)
    args = ap.parse_args()

    cache = load_evidence_cache(args.state_dir)
    pass_ids = pass_correlation_ids(cache)

    traj_path = os.path.join(args.state_dir, "trajectory.jsonl")
    seen = set()
    recovered = []
    eligible_seen = 0
    for e in iter_jsonl_objects(traj_path):
        aid = e.get("alpha_id")
        if not isinstance(aid, (str, int)) or not str(aid).strip():
            continue
        aid = str(aid)
        if aid not in pass_ids or aid in seen or e.get("status") != "DONE":
            continue
        seen.add(aid)
        m = e.get("metrics") if isinstance(e.get("metrics"), dict) else {}
        s, fi = num(m.get("sharpe")), num(m.get("fitness"))
        to = num(m.get("turnover"))
        if (s or 0) < args.min_sharpe or (fi or 0) < args.min_fitness:
            continue
        if not (0.01 <= (to or 1) <= 0.7):
            continue
        checks = {c.get("name"): c for c in m.get("checks") or []
                  if isinstance(c, dict)}
        hard = [n for n in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE")
                if n in checks and check_pass(checks[n]) is False]
        if hard:
            continue
        h = e.get("health") if isinstance(e.get("health"), dict) else {}
        if h.get("ok") is False:
            continue
        eligible_seen += 1
        _retain_candidate(recovered, {
            "alpha_id": aid, "round": e.get("round"),
            "sharpe": s, "fitness": fi, "turnover": to,
            "margin": num(m.get("margin")), "corr": pass_ids[aid],
            "expression": e.get("expression")},
        )

    out_path = os.path.join(args.state_dir, "recovered_candidates.json")
    source_mtimes = []
    for source in (traj_path, os.path.join(args.state_dir, "evidence_cache.json")):
        try:
            source_mtimes.append(os.path.getmtime(source))
        except OSError:
            continue
    snapshot = max(source_mtimes, default=0)
    atomic_write_json_if_changed(
        out_path,
        {"generated_at": datetime.fromtimestamp(snapshot, tz=timezone.utc).isoformat()
         if snapshot else "unknown",
         "count": len(recovered),
         "total_eligible_seen": eligible_seen,
         "candidates": recovered,
         "retention_limit": RECOVERED_CANDIDATE_LIMIT},
        ignored_keys=("generated_at",),
    )
    print(f"[RECOVERED] {len(recovered)} candidates -> {out_path}")
    for r in recovered[:15]:
        print("F=%.2f S=%.2f TO=%.3f corr=%.3f r%s %s" % (
            r["fitness"], r["sharpe"], r["turnover"], r["corr"],
            r["round"], r["alpha_id"]))
        print("   ", str(r["expression"] or "")[:90])

if __name__ == "__main__":
    main()
