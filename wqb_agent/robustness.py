"""Pure, conservative robustness retention evidence."""

from dataclasses import dataclass
import math


def _num(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def retention(parent, child, *, direction="up"):
    """Return a ratio only when a positive parent denominator is meaningful."""
    parent = _num(parent)
    child = _num(child)
    if parent is None or child is None or parent <= 0:
        return None
    if direction == "down":
        return parent / child if child > 0 else None
    return child / parent


def _multiple(parent, child):
    parent = _num(parent)
    child = _num(child)
    if parent is None or child is None or parent <= 0:
        return None
    return child / parent


@dataclass(frozen=True)
class RobustnessEvidence:
    variable: str
    availability: str
    decision: str
    sharpe_retention: float | None
    fitness_retention: float | None
    turnover_change: float | None
    drawdown_change: float | None
    checks_passed: bool | None
    reason: str
    criteria: dict
    criterion_results: dict

    def as_dict(self):
        return {
            "variable": self.variable,
            "availability": self.availability,
            "decision": self.decision,
            "sharpe_retention": self.sharpe_retention,
            "fitness_retention": self.fitness_retention,
            "turnover_change": self.turnover_change,
            "drawdown_change": self.drawdown_change,
            "checks_passed": self.checks_passed,
            "reason": self.reason,
            "criteria": dict(self.criteria),
            "criterion_results": dict(self.criterion_results),
        }


def evaluate_robustness(variable, parent_metrics, child_metrics, criteria,
                        checks_passed):
    criteria = dict(criteria or {})
    parent_metrics = parent_metrics if isinstance(parent_metrics, dict) else {}
    child_metrics = child_metrics if isinstance(child_metrics, dict) else {}
    sr = retention(parent_metrics.get("sharpe"), child_metrics.get("sharpe"))
    fr = retention(parent_metrics.get("fitness"), child_metrics.get("fitness"))
    tm = _multiple(parent_metrics.get("turnover"), child_metrics.get("turnover"))
    dm = _multiple(parent_metrics.get("drawdown"), child_metrics.get("drawdown"))
    results = {}

    def criterion(name, value, threshold, *, minimum=True):
        if threshold is None:
            return
        if value is None:
            results[name] = "UNAVAILABLE"
        elif (value >= threshold if minimum else value <= threshold):
            results[name] = "PASS"
        else:
            results[name] = "FAIL"

    criterion("min_sharpe_retention", sr, _num(criteria.get("min_sharpe_retention")))
    criterion("min_fitness_retention", fr, _num(criteria.get("min_fitness_retention")))
    criterion("max_turnover_multiple", tm, _num(criteria.get("max_turnover_multiple")), minimum=False)
    criterion("max_drawdown_multiple", dm, _num(criteria.get("max_drawdown_multiple")), minimum=False)
    if criteria.get("require_checks_passed"):
        results["require_checks_passed"] = (
            "PASS" if checks_passed is True else
            "FAIL" if checks_passed is False else "UNAVAILABLE"
        )
    availability = "AVAILABLE" if all(value != "UNAVAILABLE" for value in results.values()) else "UNAVAILABLE"
    decision = "PASS" if results and all(value == "PASS" for value in results.values()) else (
        "FAIL" if any(value == "FAIL" for value in results.values()) else "UNAVAILABLE"
    )
    reason = "all preregistered retention criteria passed" if decision == "PASS" else (
        "one or more preregistered retention criteria failed" if decision == "FAIL" else
        "retention evidence unavailable"
    )
    return RobustnessEvidence(variable, availability, decision, sr, fr,
                              tm, dm, checks_passed, reason, criteria, results)
