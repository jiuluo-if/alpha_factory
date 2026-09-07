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


def _correlation(left, right):
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    left_dev = [value - left_mean for value in left]
    right_dev = [value - right_mean for value in right]
    denom = math.sqrt(sum(value * value for value in left_dev) * sum(value * value for value in right_dev))
    return sum(a * b for a, b in zip(left_dev, right_dev)) / denom if denom else None


def rolling_stability(values, window=20):
    values = _series(values)
    try:
        window = max(3, int(window))
    except (TypeError, ValueError):
        window = 20
    if len(values) < window:
        return {"status": "UNAVAILABLE", "reason": "insufficient PnL history", "n_observations": len(values)}
    windows = [values[index:index + window] for index in range(len(values) - window + 1)]
    sharpe = []
    for chunk in windows:
        std = statistics.pstdev(chunk)
        sharpe.append(statistics.fmean(chunk) / std if std else 0.0)
    positive = sum(value > 0 for value in sharpe) / len(sharpe)
    return {
        "status": "PASS" if positive >= 0.5 else "FAIL",
        "window": window,
        "n_windows": len(sharpe),
        "positive_window_fraction": positive,
        "median_window_sharpe": statistics.median(sharpe),
    }


def bootstrap_diagnostics(values, samples=500, seed=17):
    values = _series(values)
    if len(values) < 8:
        return {"status": "UNAVAILABLE", "reason": "need at least 8 PnL observations"}
    try:
        samples = max(100, int(samples))
    except (TypeError, ValueError):
        samples = 500
    rng = random.Random(seed)
    means = [statistics.fmean(rng.choice(values) for _ in values) for _ in range(samples)]
    ordered = sorted(means)
    return {
        "status": "PASS" if sum(value > 0 for value in means) / len(means) >= 0.95 else "FAIL",
        "samples": samples,
        "probability_positive": sum(value > 0 for value in means) / len(means),
        "q05": ordered[int(0.05 * (len(ordered) - 1))],
        "q50": ordered[int(0.50 * (len(ordered) - 1))],
        "q95": ordered[int(0.95 * (len(ordered) - 1))],
    }


class PnlAdapter:
    """Interpret a caller-supplied PnL response only after live verification."""

    def __init__(self, capability_status):
        self.capability_status = str(capability_status or "UNKNOWN").upper()

    def analyze(self, payload, benchmark=None, *, window=20, bootstrap_samples=500):
        if self.capability_status != "LIVE_VERIFIED":
            return {
                "status": "UNAVAILABLE",
                "capability_status": self.capability_status,
                "reason": "PnL capability is not LIVE_VERIFIED",
            }
        values = _series(payload)
        benchmark_values = _series(benchmark) if benchmark is not None else []
        rolling = rolling_stability(values, window=window)
        bootstrap = bootstrap_diagnostics(values, samples=bootstrap_samples)
        return {
            "status": "PASS" if rolling.get("status") == "PASS" and bootstrap.get("status") == "PASS" else "FAIL",
            "capability_status": self.capability_status,
            "n_observations": len(values),
            "rolling_stability": rolling,
            "correlation": _correlation(values, benchmark_values) if benchmark_values else None,
            "bootstrap": bootstrap,
        }
