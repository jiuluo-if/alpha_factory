"""Pure yearly aggregate normalization and stability evidence."""

from __future__ import annotations

from .metrics import num
from .evidence_status import annotate_evidence


def _yearly_rows(payload):
    if not isinstance(payload, dict):
        return []
    rows = payload.get("yearlyData")
    if rows is None and isinstance(payload.get("is"), dict):
        rows = payload["is"].get("yearlyData")
    if rows is None and isinstance(payload.get("data"), dict):
        rows = payload["data"].get("yearlyData")
    return rows if isinstance(rows, list) else []


def build_yearly_evidence(payload, *, min_sharpe=0.0, min_fitness=0.0,
                          max_turnover=None, min_years=1):
    """Create compact annual evidence without retaining the raw payload."""
    rows = []
    for raw in _yearly_rows(payload):
        if not isinstance(raw, dict):
            continue
        year = raw.get("year", raw.get("yearStart", raw.get("date")))
        record = {"year": year}
        for key in ("sharpe", "fitness", "returns", "turnover", "drawdown", "margin"):
            value = num(raw.get(key))
            if value is not None:
                record[key] = value
        if len(record) > 1:
            rows.append(record)
    if not rows:
        return annotate_evidence({
            "status": "UNKNOWN", "source": "BRAIN /alphas/{id}/aggregates",
            "years": [], "year_count": 0, "coverage_status": "UNAVAILABLE",
            "stable": None, "reason": "yearlyData 缺失或为空",
        }, status="UNAVAILABLE")
    sharpe = [row["sharpe"] for row in rows if "sharpe" in row]
    fitness = [row["fitness"] for row in rows if "fitness" in row]
    turnover = [row["turnover"] for row in rows if "turnover" in row]
    passing = sum(
        row.get("sharpe", float("-inf")) >= float(min_sharpe)
        and row.get("fitness", float("-inf")) >= float(min_fitness)
        and (max_turnover is None or row.get("turnover", float("inf")) <= float(max_turnover))
        for row in rows
    )
    coverage_status = "VERIFIED" if len(rows) >= int(min_years) else "INCONCLUSIVE"
    stable = (coverage_status == "VERIFIED" and passing == len(rows)
              and bool(sharpe) and bool(fitness))
    return annotate_evidence({
        "status": "VERIFIED",
        "source": "BRAIN /alphas/{id}/aggregates",
        "years": rows,
        "year_count": len(rows),
        "coverage_status": coverage_status,
        "passing_years": passing,
        "stable": bool(stable),
        "summary": {
            "min_sharpe": min(sharpe) if sharpe else None,
            "min_fitness": min(fitness) if fitness else None,
            "max_turnover": max(turnover) if turnover else None,
        },
        "thresholds": {
            "min_sharpe": min_sharpe, "min_fitness": min_fitness,
            "max_turnover": max_turnover,
        },
    }, status="PASS" if stable else "FAIL")
