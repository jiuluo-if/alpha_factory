# -*- coding: utf-8 -*-
"""Refresh settled platform evidence into the evidence-cache side-car.

BRAIN 的 SELF_CORRELATION 等 check 是异步计算的：模拟完成时抓取的 payload 里
通常是 PENDING。本脚本对指定 alpha（或指定轮次 checkpoint 里的全部 DONE alpha）
重新只读拉取 GET /alphas/{id}，把已结算（pass 为 bool）的 checks 写入
``.wqb_state/evidence_cache.json`` 侧车；Reflector 分类时会叠加该缓存，
从而解除 VALIDATION 角色与晋升管线因 PENDING 而结构性阻塞的问题。

不修改 trajectory.jsonl / checkpoint / sims_results 等任何既有状态。

Usage:
  python scripts/refresh_evidence.py --alpha RR77Qv6e [--alpha ...]
  python scripts/refresh_evidence.py --round 972
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wqb_agent.client import WQBClient
from wqb_agent.evidence import (
    has_resolved_self_correlation,
    load_evidence_cache,
    overlay_cached_checks,
    refresh_self_correlation_cache,
    save_evidence_cache,
)
from wqb_agent.metrics import check_pass, extract_metrics as _extract_metrics


def pending_check_names(metrics):
    if not isinstance(metrics, dict):
        return []
    names = []
    for check in (metrics or {}).get("checks") or []:
        if isinstance(check, dict) and check_pass(check) is None:
            names.append(check.get("name"))
    return names


def fetch_settled(client, state_dir, alpha_id, cache=None):
    """返回指标视图：payload 指标 + 由 correlations/self 合成的 SELF_CORRELATION 检查。"""
    payload = client.get_alpha(alpha_id)
    metrics = _extract_metrics(payload)
    if not isinstance(metrics, dict):
        return None
    if cache is None:
        cache = load_evidence_cache(state_dir)
    cached = cache.get(alpha_id) if isinstance(cache, dict) else None
    metrics = overlay_cached_checks(metrics, cached)
    still_pending = pending_check_names(metrics)
    if still_pending:
        print(f"[PENDING] {alpha_id}: {still_pending}")
        return None
    return metrics


def alphas_from_checkpoint(state_dir, round_no):
    path = os.path.join(state_dir, f"round_{round_no}.checkpoint.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        print(f"[MISS] checkpoint not found: {path}")
        return []
    if not isinstance(data, dict):
        print(f"[MISS] checkpoint is not an object: {path}")
        return []
    out = []
    for exp in data.get("experiments") or []:
        if isinstance(exp, dict) and exp.get("status") == "DONE" and exp.get("alpha_id"):
            out.append(exp["alpha_id"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--alpha", action="append", default=[],
                    help="alpha id to refresh (repeatable)")
    ap.add_argument("--round", type=int, default=None,
                    help="refresh every DONE alpha in round_N.checkpoint.json")
    ap.add_argument("--timeout", type=int, default=120,
                    help="per-alpha correlation refresh timeout in seconds")
    ap.add_argument("--state-dir", default=".wqb_state")
    args = ap.parse_args()

    targets = list(args.alpha)
    if args.round is not None:
        targets.extend(alphas_from_checkpoint(args.state_dir, args.round))
    if not targets:
        ap.print_usage()
        sys.exit(2)

    client = WQBClient()
    cache = load_evidence_cache(args.state_dir)
    unique_targets = list(dict.fromkeys(targets))
    settled_before = {
        alpha_id for alpha_id in unique_targets
        if has_resolved_self_correlation(cache.get(alpha_id))
    }
    pending_targets = [
        alpha_id for alpha_id in unique_targets
        if alpha_id not in settled_before
    ]
    if pending_targets:
        refresh_self_correlation_cache(
            client, args.state_dir, pending_targets, timeout_sec=args.timeout
        )
        cache = load_evidence_cache(args.state_dir)
    refreshed = 0
    errors = 0
    for idx, alpha_id in enumerate(unique_targets):
        if alpha_id in settled_before:
            print("[SKIP] %s SELF_CORRELATION already settled" % alpha_id, flush=True)
            continue
        try:
            metrics = fetch_settled(client, args.state_dir, alpha_id, cache=cache)
        except Exception as exc:
            errors += 1
            print("[ERR] %s: %s" % (alpha_id, str(exc)[:120]), flush=True)
            if refreshed and refreshed % 10 == 0:
                save_evidence_cache(args.state_dir, cache)
            continue
        if metrics is None:
            continue
        cache[alpha_id] = {
            "checks": metrics.get("checks") or [],
            "passed": metrics.get("passed"),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        refreshed += 1
        sc = next((c for c in metrics.get("checks") or []
                   if isinstance(c, dict)
                   and c.get("name") == "SELF_CORRELATION"), None)
        sc_text = "n/a" if sc is None else str(sc.get("value", sc.get("pass")))
        print("[OK] %s SELF_CORRELATION=%s" % (alpha_id, sc_text), flush=True)
        if refreshed % 10 == 0:
            save_evidence_cache(args.state_dir, cache)
            print("[SAVE] %d entries @ %d/%d" % (len(cache), idx + 1,
                                                 len(targets)), flush=True)
    save_evidence_cache(args.state_dir, cache)
    print(f"[DONE] refreshed {refreshed}/{len(set(targets))} -> "
          f"{os.path.join(args.state_dir, 'evidence_cache.json')}")


if __name__ == "__main__":
    main()
