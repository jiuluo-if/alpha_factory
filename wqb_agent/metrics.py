"""Pure metric helpers shared by state and research-domain modules.

This module must remain free of persistence, network, and orchestration
dependencies so lightweight proposal/audit tools can be imported cheaply.
"""

import math


METRIC_KEYS = ("sharpe", "fitness", "turnover", "returns", "drawdown", "margin")


def check_pass(check):
    """Normalize boolean ``pass`` and string ``result`` check formats."""
    if not isinstance(check, dict):
        return None
    value = check.get("pass") if "pass" in check else check.get("result")
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in ("PENDING", "UNKNOWN", "INCOMPLETE"):
            return None
        if normalized in ("PASS", "PASSED", "TRUE", "OK"):
            return True
        if normalized in ("FAIL", "FAILED", "FALSE", "ERROR",
                          "REJECT", "REJECTED"):
            return False
        return None
    if isinstance(value, (int, float)) and not math.isfinite(float(value)):
        return None
    return bool(value) if value is not None else None


def checks_passed(metrics):
    """Aggregate resolved checks with a tri-state result.

    Empty or unresolved checks are evidence-incomplete, not a pass.  Keeping
    this rule here prevents submission, reflection, and validation callers
    from each interpreting legacy ``pass``/``result`` payloads differently.
    """
    if not isinstance(metrics, dict):
        return None
    checks = metrics.get("checks")
    if not isinstance(checks, list) or not checks:
        return None
    values = [check_pass(check) for check in checks]
    if any(value is None for value in values):
        return None
    return all(value is True for value in values)


def extract_metrics(payload):
    """Extract the six metrics and tri-state checks from a platform payload."""
    if not isinstance(payload, dict):
        payload = {}
    is_block = payload.get("is")
    is_block = is_block if isinstance(is_block, dict) else {}
    checks = is_block.get("checks")
    checks = checks if isinstance(checks, list) else []
    passed = checks_passed({"checks": checks})
    return {
        "sharpe": num(is_block.get("sharpe")),
        "fitness": num(is_block.get("fitness")),
        "turnover": num(is_block.get("turnover")),
        "margin": num(is_block.get("margin")),
        "returns": num(is_block.get("returns")),
        "drawdown": num(is_block.get("drawdown")),
        "checks": [
            {
                "name": check.get("name") if isinstance(check, dict) else None,
                "pass": check_pass(check),
                "result": check.get("result") if isinstance(check, dict) else None,
                "value": check.get("value") if isinstance(check, dict) else None,
                "limit": check.get("limit") if isinstance(check, dict) else None,
            }
            for check in checks
        ],
        "passed": passed,
    }


def check_health(payload):
    """Return heuristic health evidence for concentrated-weight noise traps."""
    if not isinstance(payload, dict):
        payload = {}
    is_block = payload.get("is")
    is_block = is_block if isinstance(is_block, dict) else {}
    raw_checks = is_block.get("checks")
    raw_checks = raw_checks if isinstance(raw_checks, list) else []
    checks = {
        check.get("name"): check for check in raw_checks
        if isinstance(check, dict)
    }
    long_count = num(is_block.get("longCount"))
    short_count = num(is_block.get("shortCount"))
    reasons = []
    if long_count is not None and long_count < 50:
        reasons.append(f"longCount={long_count:g}<50")
    if short_count is not None and short_count < 50:
        reasons.append(f"shortCount={short_count:g}<50")
    for name in ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE"):
        check = checks.get(name) or {}
        passed = check_pass(check)
        result = check.get("result")
        if isinstance(result, str):
            result = result.strip().upper()
        if result is None and passed is not None:
            result = "PASS" if passed else "FAIL"
        if passed is False:
            reasons.append(f"{name}={result or 'FAIL'} v={check.get('value')}")
    return {"ok": not reasons, "reasons": reasons}


def normalized_metrics(metrics):
    """Return a numeric view of the six platform metrics.

    Older derived files and a few platform payload variants store numbers as
    strings.  Keeping this conversion at one pure boundary prevents each
    consumer from implementing a slightly different comparison rule.
    """
    if not isinstance(metrics, dict):
        return {}
    normalized = dict(metrics)
    for key in METRIC_KEYS:
        if key in normalized:
            normalized[key] = num(normalized.get(key))
    return normalized


def score_of(metrics):
    """统一质量评分：Fitness 优先，其次 Sharpe；无指标返回 -1。"""
    metrics = normalized_metrics(metrics)
    if not metrics:
        return -1.0
    fitness = metrics.get("fitness")
    sharpe = metrics.get("sharpe")
    if fitness is not None and fitness != 0:
        return fitness
    return sharpe if sharpe is not None else -1.0


def num(value):
    """安全转有限 float；None/非法/NaN/Infinity 返回 None。"""
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
