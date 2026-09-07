"""Canonical extraction of trusted behavioral return/PnL series."""

from __future__ import annotations


def _get(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def extract_behavior_series(experiment):
    """Use only explicitly LIVE_VERIFIED PnL/return series.

    Aggregate metrics, yearly summaries and structural fingerprints are never
    treated as behavioral observations.
    """
    pnl = _get(experiment, "pnl")
    if not isinstance(pnl, dict):
        pnl = _get(experiment, "pnl_evidence")
    if not isinstance(pnl, dict):
        return {"series": None, "source": None, "capability": "UNAVAILABLE",
                "availability": "UNAVAILABLE", "reason": "no PnL evidence"}
    status = str(pnl.get("status") or pnl.get("capability") or "").upper()
    series = pnl.get("series") or pnl.get("returns")
    if status != "LIVE_VERIFIED" or not isinstance(series, dict) or not series:
        return {"series": None, "source": "PNL", "capability": status or "UNKNOWN",
                "availability": "UNAVAILABLE", "reason": "PnL is not LIVE_VERIFIED"}
    return {"series": dict(series), "source": "LIVE_VERIFIED_PNL",
            "capability": "LIVE_VERIFIED", "availability": "AVAILABLE",
            "reason": None}
