"""平台证据缓存侧车（evidence cache side-car）。

背景：BRAIN 的 SELF_CORRELATION check 是异步计算的。模拟完成时抓取的 alpha
payload 中该检查通常仍为 PENDING（``pass`` 三态 None），导致 Reflection 把
DONE 实验判为 RECONCILE，VALIDATION 角色的 parent 资格门
（SUCCESS / SUSPICIOUS_HIGH_SIGNAL）永远无法通过——晋升与提交池管线被结构性阻塞。

本模块提供一个可选的证据缓存接口；生产 Agent 默认只使用进程内缓存：
- 只读平台（GET /alphas/{id}），把已结算的 checks 缓存下来；
- 不修改 trajectory.jsonl、checkpoint、sims_results 等任何 append-only 状态；
- Reflector 在分类时把缓存中已结算（bool pass）的检查叠加到存储指标之上，
  仅用于判定，不回写原始实验记录。
"""
import json
import math
import os
import time

from .artifacts import atomic_write_json_if_changed
from .client import WQBError
from .metrics import check_pass, checks_passed
from .schema import EVIDENCE_CACHE_VERSION, CREATED_BY_VERSION

EVIDENCE_FILE = "evidence_cache.json"
SELF_CORRELATION_LIMIT = 0.5
EVIDENCE_SAVE_BATCH = 4
EVIDENCE_CACHE_MAX_ENTRIES = 4096


def evidence_path(state_dir):
    return os.path.join(state_dir, EVIDENCE_FILE)


def load_evidence_cache(state_dir):
    """读取证据缓存；缺失或损坏时返回空 dict（降级为无缓存）。"""
    try:
        with open(evidence_path(state_dir), encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        return {}
    cache = _bounded_cache(cache)
    for entry in cache.values():
        entry.setdefault("schema_version", EVIDENCE_CACHE_VERSION)
        entry.setdefault("created_by_version", CREATED_BY_VERSION)
    return cache


def _bounded_cache(cache, max_entries=EVIDENCE_CACHE_MAX_ENTRIES):
    """Keep only valid, recent-enough advisory entries in process memory.

    The cache is rebuildable from the platform.  A hard bound prevents an
    all-day factory from turning every historical Alpha correlation into a
    permanent in-memory index.  ``updated_at`` is used when available; the
    original insertion position is the deterministic fallback for legacy
    entries without that field.
    """
    if not isinstance(cache, dict):
        return {}
    try:
        limit = max(0, int(max_entries))
    except (TypeError, ValueError):
        limit = EVIDENCE_CACHE_MAX_ENTRIES
    entries = [
        (str(key), value, index)
        for index, (key, value) in enumerate(cache.items())
        if isinstance(value, dict)
    ]
    if limit == 0:
        return {}
    if len(entries) > limit:
        entries.sort(
            key=lambda item: (str(item[1].get("updated_at") or ""), item[2])
        )
        entries = entries[-limit:]
    return {key: value for key, value, _index in entries}


def save_evidence_cache(state_dir, cache):
    os.makedirs(state_dir, exist_ok=True)
    cache = _bounded_cache(cache)
    cache = {
        key: dict(value, schema_version=EVIDENCE_CACHE_VERSION,
                  created_by_version=CREATED_BY_VERSION)
        for key, value in cache.items()
    }
    atomic_write_json_if_changed(
        evidence_path(state_dir), cache, ignored_keys=("updated_at",),
        sort_keys=True,
    )


def has_resolved_self_correlation(entry):
    """Return whether a side-car entry contains a usable settled value.

    ``passed`` alone is not enough: older or manually repaired cache entries
    may contain a boolean without the numeric evidence needed to re-apply the
    current strict threshold.  Only settled, finite values are safe to reuse.
    """
    if not isinstance(entry, dict) or not isinstance(entry.get("passed"), bool):
        return False
    for check in entry.get("checks") or []:
        if not isinstance(check, dict):
            continue
        if check.get("name") != "SELF_CORRELATION":
            continue
        try:
            value = float(check.get("value"))
        except (TypeError, ValueError):
            return False
        return math.isfinite(value) and isinstance(check.get("pass"), bool)
    return False


def _correlation_values(payload):
    """Extract finite correlation candidates from known BRAIN read shapes."""
    if not isinstance(payload, dict):
        return []
    roots = [payload]
    nested = payload.get("is")
    if isinstance(nested, dict):
        roots.insert(0, nested)
    values = []
    for root in roots:
        schema = root.get("schema")
        properties = schema.get("properties", []) if isinstance(schema, dict) else []
        names = [
            item.get("name") for item in properties
            if isinstance(item, dict) and item.get("name")
        ]
        records = root.get("records") or root.get("data") or []
        if isinstance(records, list):
            for record in records:
                if isinstance(record, dict):
                    value = record.get("correlation")
                    if value is not None:
                        values.append(value)
                elif isinstance(record, (list, tuple)) and names:
                    row = dict(zip(names, record))
                    if row.get("correlation") is not None:
                        values.append(row["correlation"])
        for key in ("correlation", "max"):
            if root.get(key) is not None:
                values.append(root[key])
    return values


def refresh_self_correlation_cache(client, state_dir, alpha_ids,
                                   timeout_sec=20, correlation_limit=None,
                                   *, persist=True, cache=None):
    """Read-only refresh of settled BRAIN SELF_CORRELATION checks.

    ``GET /alphas/{id}`` commonly exposes the check as PENDING even after the
    simulation is complete.  The platform settles the value on the separate
    ``correlations/self`` endpoint.  Cache only resolved checks; unresolved or
    failed reads remain absent and therefore fail closed in promotion gates.
    ``persist=False`` is the production mode and keeps the cache in memory.
    """
    cache = cache if isinstance(cache, dict) else load_evidence_cache(state_dir)
    try:
        correlation_limit = float(
            SELF_CORRELATION_LIMIT if correlation_limit is None
            else correlation_limit
        )
    except (TypeError, ValueError):
        correlation_limit = SELF_CORRELATION_LIMIT
    refreshed = 0
    dirty = False
    alpha_ids = alpha_ids if isinstance(alpha_ids, (list, tuple, set)) else []
    unique_alpha_ids = []
    seen_alpha_ids = set()
    for value in alpha_ids:
        if not isinstance(value, (str, int)) or not str(value).strip():
            continue
        alpha_id = str(value)
        if alpha_id not in seen_alpha_ids:
            seen_alpha_ids.add(alpha_id)
            unique_alpha_ids.append(alpha_id)
    for alpha_id in unique_alpha_ids:
        # A settled result is immutable for this evidence purpose.  Reusing
        # it avoids one GET per alpha on every factory iteration; unresolved
        # or malformed entries still go through the read-only refresh path.
        if has_resolved_self_correlation(cache.get(alpha_id)):
            continue
        try:
            payload = client.get_self_correlation(alpha_id, timeout_sec=timeout_sec)
        except (WQBError, AttributeError, ValueError, TypeError):
            # A read-only evidence refresh is advisory.  Preserve the
            # unresolved cache state and let the caller continue; this must
            # not turn a transient platform fault into a research failure or
            # trigger a duplicate POST.
            continue
        if not isinstance(payload, dict):
            continue
        values = _correlation_values(payload)
        if not values:
            continue
        numeric_values = []
        for value in values:
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(parsed):
                numeric_values.append(parsed)
        if not numeric_values:
            # Malformed platform evidence is unresolved, never a pass and
            # never a reason to abort the whole unattended round.
            continue
        max_corr = max(abs(value) for value in numeric_values)
        # Match the configured production submission gate: strict maximum
        # absolute correlation below the current local policy limit.
        check = {"name": "SELF_CORRELATION",
                 "pass": max_corr < correlation_limit,
                 "result": "PASS" if max_corr < correlation_limit else "FAIL",
                 "value": max_corr, "limit": correlation_limit}
        cache[alpha_id] = {"checks": [check], "passed": check["pass"],
                           "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        refreshed += 1
        dirty = True
        # The cache is advisory and fully re-fetchable. Batch writes reduce
        # atomic rewrites during an 18-candidate round while retaining a
        # bounded crash-loss window.
        if persist and refreshed % EVIDENCE_SAVE_BATCH == 0:
            save_evidence_cache(state_dir, cache)
            dirty = False
    if persist and dirty:
        save_evidence_cache(state_dir, cache)
    return refreshed


def overlay_cached_checks(metrics, cached, correlation_limit=None):
    """把缓存中已结算（pass 为 bool）的检查叠加到存储指标视图上。

    只替换存储中 ``pass is None`` 的同名检查；任何未结算项保留原样并使整体
    ``passed`` 保持三态。无变化时原样返回同一 metrics 对象。
    """
    if not cached or not isinstance(metrics, dict):
        return metrics
    try:
        correlation_limit = float(
            SELF_CORRELATION_LIMIT if correlation_limit is None
            else correlation_limit
        )
    except (TypeError, ValueError):
        correlation_limit = SELF_CORRELATION_LIMIT
    checks = metrics.get("checks")
    if not isinstance(checks, list) or not checks:
        return metrics
    by_name = {
        c.get("name"): c
        for c in (cached.get("checks") or [])
        if isinstance(c, dict) and c.get("name")
    }
    if not by_name:
        return metrics
    merged = []
    changed = False
    for check in checks:
        if not isinstance(check, dict):
            merged.append(check)
            continue
        name = check.get("name")
        if check_pass(check) is None and name in by_name:
            rep = by_name[name]
            if check_pass(rep) is not None:
                rep_pass = check_pass(rep)
                rep_value = rep.get("value", check.get("value"))
                # Re-evaluate legacy sidecar values under the current strict
                # gate; old entries may have been written under another limit.
                if name == "SELF_CORRELATION" and rep_value is not None and rep_pass:
                    try:
                        rep_pass = abs(float(rep_value)) < correlation_limit
                    except (TypeError, ValueError):
                        rep_pass = False
                merged.append({**check,
                               "pass": rep_pass,
                               "result": ("PASS" if rep_pass else "FAIL")
                               if name == "SELF_CORRELATION"
                               else rep.get("result", check.get("result")),
                               "value": rep_value,
                               "limit": correlation_limit
                               if name == "SELF_CORRELATION"
                               else rep.get("limit", check.get("limit"))})
                changed = True
                continue
        merged.append(check)
    if not changed:
        return metrics
    view = dict(metrics)
    view["checks"] = merged
    view["passed"] = checks_passed({"checks": merged})
    return view
