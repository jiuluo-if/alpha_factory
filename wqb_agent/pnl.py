"""Read-only PnL adapter for a verified BRAIN capability.

No transport is implemented here.  The adapter refuses to interpret a
community-observed or unknown endpoint as live PnL, which prevents fabricated
DSR/PBO evidence when the platform does not expose the series.
"""

from __future__ import annotations

import math
import random
import statistics

from .metrics import num
from .evidence_status import annotate_evidence


def _series(payload):
    if isinstance(payload, dict):
        for key in ("returns", "pnl", "data", "records"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                payload = candidate
                break
    values = []
    for row in payload or ():
        value = row
        if isinstance(row, dict):
            value = row.get("return", row.get("returns", row.get("pnl", row.get("value"))))
        parsed = num(value)
        if parsed is not None:
            values.append(parsed)
    return values


def _dated_series(payload):
    if isinstance(payload, dict):
        for key in ("returns", "pnl", "data", "records"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    result = {}
    for index, row in enumerate(payload or ()):
        if not isinstance(row, dict):
            continue
        date = row.get("date") or row.get("timestamp") or row.get("time")
        value = num(row.get("return", row.get("returns", row.get("pnl", row.get("value")))))
        if date is not None and value is not None:
            result[str(date)] = value
    return result


def _correlation(left, right):
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    left_dev = [value - left_mean for value in left]
    right_dev = [value - right_mean for value in right]
    denom = math.sqrt(sum(value * value for value in left_dev) * sum(value * value for value in right_dev))
    return sum(a * b for a, b in zip(left_dev, right_dev)) / denom if denom else None


def correlation_evidence(left, right):
    """Use date inner-join when records carry dates; report signed/absolute corr."""
    if isinstance(left, dict) and isinstance(right, dict):
        keys = sorted(set(left) & set(right))
        left, right = [left[key] for key in keys], [right[key] for key in keys]
    value = _correlation(left or [], right or [])
    if value is None:
        return annotate_evidence({"status": "UNAVAILABLE", "signed_corr": None,
                                  "abs_corr": None, "overlap_count": len(left or [])},
                                 status="UNAVAILABLE")
    return annotate_evidence({"status": "PASS", "signed_corr": value,
                              "abs_corr": abs(value), "overlap_count": len(left),
                              "overlap_ratio": len(left) / max(len(left), len(right))}, status="PASS")


def rolling_stability(values, window=20):
    values = _series(values)
    try:
        window = max(3, int(window))
    except (TypeError, ValueError):
        window = 20
    if len(values) < window:
        return annotate_evidence({"status": "UNAVAILABLE", "reason": "insufficient PnL history", "n_observations": len(values)}, status="UNAVAILABLE")
    windows = [values[index:index + window] for index in range(len(values) - window + 1)]
    sharpe = []
    for chunk in windows:
        std = statistics.pstdev(chunk)
        sharpe.append(statistics.fmean(chunk) / std if std else 0.0)
    positive = sum(value > 0 for value in sharpe) / len(sharpe)
    return annotate_evidence({
        "status": "PASS" if positive >= 0.5 else "FAIL",
        "window": window,
        "n_windows": len(sharpe),
        "positive_window_fraction": positive,
        "median_window_sharpe": statistics.median(sharpe),
    }, status="PASS" if positive >= 0.5 else "FAIL")


def bootstrap_diagnostics(values, samples=500, seed=17):
    values = _series(values)
    if len(values) < 8:
        return annotate_evidence({"status": "UNAVAILABLE", "reason": "need at least 8 PnL observations"}, status="UNAVAILABLE")
    try:
        samples = max(100, int(samples))
    except (TypeError, ValueError):
        samples = 500
    rng = random.Random(seed)
    means = [statistics.fmean(rng.choice(values) for _ in values) for _ in range(samples)]
    ordered = sorted(means)
    return annotate_evidence({
        "status": "PASS" if sum(value > 0 for value in means) / len(means) >= 0.95 else "FAIL",
        "samples": samples,
        "probability_positive": sum(value > 0 for value in means) / len(means),
        "q05": ordered[int(0.05 * (len(ordered) - 1))],
        "q50": ordered[int(0.50 * (len(ordered) - 1))],
        "q95": ordered[int(0.95 * (len(ordered) - 1))],
    }, status="PASS" if sum(value > 0 for value in means) / len(means) >= 0.95 else "FAIL")


class PnlAdapter:
    """Interpret a caller-supplied PnL response only after live verification."""

    def __init__(self, capability_status):
        self.capability_status = str(capability_status or "UNKNOWN").upper()

    def analyze(self, payload, benchmark=None, *, window=20, bootstrap_samples=500):
        if self.capability_status != "LIVE_VERIFIED":
            return annotate_evidence({
                "status": "UNAVAILABLE",
                "capability_status": self.capability_status,
                "reason": "PnL capability is not LIVE_VERIFIED",
            }, status="UNAVAILABLE")
        values = _series(payload)
        benchmark_values = _series(benchmark) if benchmark is not None else []
        dated_values = _dated_series(payload)
        dated_benchmark = _dated_series(benchmark) if benchmark is not None else {}
        rolling = rolling_stability(values, window=window)
        bootstrap = bootstrap_diagnostics(values, samples=bootstrap_samples)
        result = {
            "status": "PASS" if rolling.get("status") == "PASS" and bootstrap.get("status") == "PASS" else "FAIL",
            "capability_status": self.capability_status,
            "n_observations": len(values),
            "rolling_stability": rolling,
            "correlation": correlation_evidence(dated_benchmark, dated_values) if dated_values and dated_benchmark else (correlation_evidence(benchmark_values, values) if benchmark_values else {
                "status": "NOT_APPLICABLE", "evidence_status": "NOT_APPLICABLE"
            }),
            "bootstrap": bootstrap,
        }
        result["evidence_status"] = "PASS" if result["status"] == "PASS" else "FAIL"
        return result
