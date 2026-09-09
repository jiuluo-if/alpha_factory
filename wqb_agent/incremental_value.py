"""ROLE: INTERNAL
AGENT_RELEVANCE: LOW
PURPOSE: Compute date-aligned behavioral incremental-value evidence.
READ WHEN: changing PnL/series correlation diagnostics.
DO NOT USE FOR: platform truth or research-direction selection."""

import hashlib
import math
from dataclasses import dataclass


def _num(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _corr(left, right):
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean, right_mean = sum(left) / len(left), sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_var = sum((a - left_mean) ** 2 for a in left)
    right_var = sum((b - right_mean) ** 2 for b in right)
    if left_var <= 0 or right_var <= 0:
        return None
    return numerator / math.sqrt(left_var * right_var)


def _series(value):
    if not isinstance(value, dict):
        return {}
    return {str(key): _num(item) for key, item in value.items()
            if _num(item) is not None}


def select_trusted_pool(rows, *, as_of=None, policy="DONE_CHECKS_IDENTITY"):
    """Select only trusted Alpha behavior references available at ``as_of``."""
    result = []
    for row in rows or ():
        if not isinstance(row, dict) or str(row.get("status", "")).upper() != "DONE":
            continue
        if row.get("checks_passed") is not True or not row.get("identity"):
            continue
        entered = _num(row.get("pool_entered_at"))
        if as_of is not None and (entered is None or entered > _num(as_of)):
            continue
        result.append(dict(row))
    return result


@dataclass(frozen=True)
class IncrementalValueEvidence:
    availability: str
    quality: str
    decision: str
    candidate_id: str
    comparison_pool_size: int
    max_abs_corr: float | None
    median_abs_corr: float | None
    nearest_alpha_id: str | None
    cluster_id: str | None
    cluster_size: int | None
    reason: str
    overlap_count: int = 0
    overlap_ratio: float | None = None
    signed_corr: float | None = None
    pool_policy: str = "DONE_CHECKS_IDENTITY"
    pool_snapshot_size: int = 0
    pool_snapshot_id: str | None = None

    def as_dict(self):
        return self.__dict__.copy()


def _snapshot_id(pool):
    identity = "|".join(sorted(str(row.get("alpha_id")) for row in pool))
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


def build_incremental_value(candidate_id, candidate_series, pool, *, min_overlap=60,
                            max_abs_correlation=.7, pool_policy="DONE_CHECKS_IDENTITY",
                            as_of=None):
    pool_rows = [row for row in pool or () if isinstance(row, dict)]
    has_selection_metadata = any(
        any(key in row for key in ("status", "checks_passed", "identity"))
        for row in pool_rows
    )
    trusted = (select_trusted_pool(pool_rows, as_of=as_of, policy=pool_policy)
               if has_selection_metadata else pool_rows)
    candidate = _series(candidate_series)
    correlations = []
    best = None
    for row in trusted:
        other = _series(row.get("series"))
        keys = sorted(set(candidate) & set(other))
        overlap = len(keys)
        if overlap < min_overlap:
            continue
        signed = _corr([candidate[key] for key in keys], [other[key] for key in keys])
        if signed is None:
            continue
        absolute = abs(signed)
        correlations.append((absolute, signed, str(row.get("alpha_id"))))
        if best is None or absolute > best[0]:
            best = (absolute, signed, str(row.get("alpha_id")), overlap, len(keys))
    if not correlations:
        return IncrementalValueEvidence("UNAVAILABLE", "UNKNOWN", "INCONCLUSIVE",
            str(candidate_id), len(trusted), None, None, None, None, None,
            "date-aligned overlap or behavioral series unavailable", 0, None, None,
            pool_policy, len(trusted), _snapshot_id(trusted))
    correlations.sort(reverse=True)
    max_abs = correlations[0][0]
    median = correlations[len(correlations) // 2][0]
    decision = "FAIL" if max_abs > max_abs_correlation else "PASS"
    cluster_id = None
    cluster_size = None
    if max_abs >= max_abs_correlation and best is not None:
        cluster_id = "cluster-" + hashlib.sha256(
            "|".join(sorted((str(candidate_id), str(best[2])))).encode()
        ).hexdigest()[:12]
        cluster_size = 2
    return IncrementalValueEvidence(
        "AVAILABLE", "VERIFIED", decision, str(candidate_id), len(trusted),
        max_abs, median, correlations[0][2], cluster_id, cluster_size,
        "redundant behavior detected" if decision == "FAIL" else "behavior below redundancy threshold",
        best[3], best[3] / max(1, len(candidate)), best[1],
        pool_policy, len(trusted), _snapshot_id(trusted),
    )


def behavior_clusters(edges, *, threshold=.7):
    """Return deterministic connected components for (left, right, corr) edges."""
    parent = {}
    def find(value):
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value
    def union(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[max(left, right)] = min(left, right)
    for left, right, corr in sorted(edges or (), key=lambda item: (str(item[0]), str(item[1]))):
        if _num(corr) is not None and abs(float(corr)) >= threshold:
            union(str(left), str(right))
    return {node: find(node) for node in sorted(parent)}
