"""Pre-correlation eligibility policy（Phase V）。

唯一允许发起 SELF_CORRELATION 只读查询的准入逻辑。BRAIN 的 SELF_CORRELATION 是
异步结算的：只有当一个 DONE Alpha 除相关性外的条件全部满足时，查询才可能改变决策；
否则只会增加延迟。Agent、CLI 脚本与 optimizer context 必须共用这一套门槛，不得各写
一套。

本模块是纯策略：不读状态、不发起请求、不写任何 owner 的数据。
"""

from __future__ import annotations

from .metrics import check_pass, checks_ready_for_self_correlation_refresh, num

# Fitness = Sharpe * sqrt(abs(Returns) / max(Turnover, 0.125))。0.125 是平台 Fitness
# 的分母下限，不是“所有 Alpha 都要把 Turnover 压到 12.5%”的目标值。
TURNOVER_FITNESS_FLOOR = 0.125

DEFAULT_MIN_TURNOVER = 0.01
DEFAULT_MAX_TURNOVER = 0.70
DEFAULT_MAX_DRAWDOWN = 0.5

# Delay-aware 过线标准；严格大于，不含等号。
DELAY_THRESHOLDS = {
    0: {"sharpe": 2.0, "fitness": 1.5},
    1: {"sharpe": 1.25, "fitness": 1.0},
}


def delay_metric_thresholds(delay):
    """返回该 delay 的过线阈值；未知或非 0/1 的 delay 返回 ``None``。"""
    if isinstance(delay, bool) or delay is None:
        return None
    try:
        value = float(delay)
    except (TypeError, ValueError):
        return None
    if not value.is_integer():
        return None
    thresholds = DELAY_THRESHOLDS.get(int(value))
    return dict(thresholds) if thresholds else None


def _policy_number(policy, name, default):
    value = num(policy.get(name, default))
    return default if value is None else value


def pre_self_correlation_eligibility(metrics, *, delay, quality_policy=None,
                                    health=None):
    """结构化 SELF_CORRELATION 查询准入报告（fail-closed）。

    ``eligible`` 只有在全部条件成立时才为 True：delay 已知、非相关性 checks 全部解析
    为 PASS、``health.ok``、``Returns > 0``、Turnover 落在配置区间、Drawdown 不超上限，
    且 Sharpe / Fitness 严格超过当前 delay 的阈值。缺失值一律保持 UNKNOWN，不是 PASS。
    """
    policy = quality_policy if isinstance(quality_policy, dict) else {}
    values = metrics if isinstance(metrics, dict) else {}
    reasons = []

    required = delay_metric_thresholds(delay)
    if required is None:
        reasons.append("DELAY_UNKNOWN")
    required_sharpe = required.get("sharpe") if required else None
    required_fitness = required.get("fitness") if required else None

    sharpe = num(values.get("sharpe"))
    fitness = num(values.get("fitness"))
    returns = num(values.get("returns"))
    turnover = num(values.get("turnover"))
    drawdown = num(values.get("drawdown"))
    margin = num(values.get("margin"))

    if required_sharpe is not None:
        if sharpe is None:
            reasons.append("SHARPE_MISSING")
        elif sharpe <= required_sharpe:
            reasons.append("SHARPE_BELOW_THRESHOLD")
    if required_fitness is not None:
        if fitness is None:
            reasons.append("FITNESS_MISSING")
        elif fitness <= required_fitness:
            reasons.append("FITNESS_BELOW_THRESHOLD")

    returns_positive = returns is not None and returns > 0
    if returns is None:
        reasons.append("RETURNS_MISSING")
    elif not returns_positive:
        reasons.append("RETURNS_NOT_POSITIVE")

    minimum_turnover = _policy_number(policy, "min_turnover", DEFAULT_MIN_TURNOVER)
    maximum_turnover = _policy_number(policy, "max_turnover", DEFAULT_MAX_TURNOVER)
    turnover_valid = (
        turnover is not None and minimum_turnover <= turnover <= maximum_turnover
    )
    if turnover is None:
        reasons.append("TURNOVER_MISSING")
    elif not turnover_valid:
        reasons.append("TURNOVER_OUT_OF_RANGE")

    max_drawdown = _policy_number(policy, "max_drawdown", DEFAULT_MAX_DRAWDOWN)
    drawdown_valid = drawdown is not None and drawdown <= max_drawdown
    if drawdown is None:
        reasons.append("DRAWDOWN_MISSING")
    elif not drawdown_valid:
        reasons.append("DRAWDOWN_EXCEEDS_LIMIT")

    if not isinstance(health, dict) or health.get("ok") is None:
        reasons.append("HEALTH_UNKNOWN")
        health_ok = False
    else:
        health_ok = health.get("ok") is True
        if not health_ok:
            reasons.append("HEALTH_NOT_OK")

    non_correlation_checks_pass = checks_ready_for_self_correlation_refresh(values)
    if not non_correlation_checks_pass:
        reasons.append("NON_CORRELATION_CHECKS_NOT_PASS")

    return {
        "eligible": not reasons,
        "delay": delay,
        "sharpe": sharpe,
        "required_sharpe": required_sharpe,
        "sharpe_gap": (
            None if sharpe is None or required_sharpe is None
            else sharpe - required_sharpe
        ),
        "fitness": fitness,
        "required_fitness": required_fitness,
        "fitness_gap": (
            None if fitness is None or required_fitness is None
            else fitness - required_fitness
        ),
        "returns": returns,
        "returns_positive": returns_positive,
        "turnover": turnover,
        "turnover_valid": turnover_valid,
        "turnover_penalty_active": (
            None if turnover is None else turnover > TURNOVER_FITNESS_FLOOR
        ),
        "turnover_fitness_floor": TURNOVER_FITNESS_FLOOR,
        "drawdown": drawdown,
        "drawdown_valid": drawdown_valid,
        "max_drawdown": max_drawdown,
        "margin": margin,
        "health_ok": health_ok,
        "non_correlation_checks_pass": non_correlation_checks_pass,
        "reasons": reasons,
    }


# 优化 readiness band 只是 Agent summary（§42），不是新的 top-level research state。
READINESS_BANDS = (
    "PRE_CORRELATION_READY",
    "ONE_REPAIR_AWAY",
    "STRUCTURAL_REPAIR_REQUIRED",
    "NUMERIC_VALIDATION_CANDIDATE",
    "LOW_INFORMATION",
    "STOP",
)

# 这些 checks 失败是结构问题：微调数值无法解决，必须先改经济结构或暴露来源。
STRUCTURAL_CHECK_BLOCKERS = ("CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE")
# 这些 checks 失败属于可修的数值 / 控制变量问题，允许单变量 VALIDATE。
REPAIRABLE_CHECK_BLOCKERS = (
    "HIGH_TURNOVER",
    "LOW_TURNOVER",
    "LOW_SHARPE",
    "LOW_FITNESS",
    "HIGH_DRAWDOWN",
    "LOW_RETURNS",
)


def failing_check_names(metrics, *, exclude_self_correlation=True):
    """返回 FAIL 的 check 名；默认排除异步的 SELF_CORRELATION。"""
    if not isinstance(metrics, dict) or not isinstance(metrics.get("checks"), list):
        return []
    names = []
    for check in metrics["checks"]:
        if not isinstance(check, dict):
            continue
        name = str(check.get("name") or "").upper()
        if not name:
            continue
        if exclude_self_correlation and name == "SELF_CORRELATION":
            continue
        if check_pass(check) is False:
            names.append(name)
    return names


def _metric_line_passes(report):
    """Sharpe / Fitness 的严格过线，加 Returns / Turnover / Drawdown / health。"""
    sharpe_gap = report.get("sharpe_gap")
    fitness_gap = report.get("fitness_gap")
    return (
        sharpe_gap is not None and sharpe_gap > 0
        and fitness_gap is not None and fitness_gap > 0
        and report.get("returns_positive") is True
        and report.get("turnover_valid") is True
        and report.get("drawdown_valid") is True
        and report.get("health_ok") is True
    )


def optimization_opportunities(report, *, blocking_checks=()):
    """从真实证据派生的机会提示；不发明经济机制，也不自动提交。"""
    blocking = {str(name).upper() for name in blocking_checks}
    opportunities = []
    if "CONCENTRATED_WEIGHT" in blocking:
        opportunities.append("CONCENTRATION_REPAIR")
    if "LOW_SUB_UNIVERSE_SHARPE" in blocking:
        opportunities.append("SUB_UNIVERSE_REPAIR")
    if "HIGH_TURNOVER" in blocking:
        opportunities.append("TURNOVER_REPAIR")
    fitness_gap = report.get("fitness_gap")
    if (report.get("turnover_penalty_active") is True
            and fitness_gap is not None and fitness_gap <= 0):
        opportunities.append("TURNOVER_EFFICIENCY")
    sharpe_gap = report.get("sharpe_gap")
    if sharpe_gap is not None and sharpe_gap <= 0:
        opportunities.append("SHARPE_GAP")
    if not opportunities:
        opportunities.append("NO_CLEAR_OPPORTUNITY")
    return opportunities


def optimization_readiness(report, *, blocking_checks=()):
    """确定性的 readiness band；只派生，不改变任何 owner 的状态。"""
    if report.get("eligible"):
        return "PRE_CORRELATION_READY"
    blocking = [str(name).upper() for name in blocking_checks]
    if any(name in STRUCTURAL_CHECK_BLOCKERS for name in blocking):
        return "STRUCTURAL_REPAIR_REQUIRED"
    if report.get("delay") is None:
        # delay 未知时 Sharpe / Fitness 门槛无从判断，先补证据而不是调参。
        return "LOW_INFORMATION"
    repairable = [name for name in blocking if name in REPAIRABLE_CHECK_BLOCKERS]
    if _metric_line_passes(report) and len(blocking) == 1:
        return "ONE_REPAIR_AWAY"
    sharpe_gap = report.get("sharpe_gap")
    fitness_gap = report.get("fitness_gap")
    if (sharpe_gap is not None and sharpe_gap > 0
            and report.get("turnover_penalty_active") is True
            and fitness_gap is not None and fitness_gap <= 0):
        return "NUMERIC_VALIDATION_CANDIDATE"
    sharpe = report.get("sharpe")
    required_sharpe = report.get("required_sharpe")
    if (not repairable and sharpe is not None and required_sharpe
            and sharpe < 0.5 * required_sharpe):
        return "STOP"
    return "LOW_INFORMATION"


def metric_optimization_context(metrics, *, delay, quality_policy=None,
                               health=None):
    """parent 的派生优化上下文（§11）；不是第二份 metrics store。"""
    report = pre_self_correlation_eligibility(
        metrics, delay=delay, quality_policy=quality_policy, health=health
    )
    blocking_checks = failing_check_names(metrics)
    turnover = report.get("turnover")
    drawdown = report.get("drawdown")
    max_drawdown = report.get("max_drawdown")
    context = {
        "delay": report.get("delay"),
        "sharpe": report.get("sharpe"),
        "required_sharpe": report.get("required_sharpe"),
        "sharpe_gap": report.get("sharpe_gap"),
        "fitness": report.get("fitness"),
        "required_fitness": report.get("required_fitness"),
        "fitness_gap": report.get("fitness_gap"),
        "returns": report.get("returns"),
        "returns_positive": report.get("returns_positive"),
        "turnover": turnover,
        "turnover_valid": report.get("turnover_valid"),
        "turnover_penalty_active": report.get("turnover_penalty_active"),
        "turnover_distance_to_0_125": (
            None if turnover is None else turnover - TURNOVER_FITNESS_FLOOR
        ),
        "turnover_fitness_floor": TURNOVER_FITNESS_FLOOR,
        "drawdown": drawdown,
        "drawdown_valid": report.get("drawdown_valid"),
        "max_drawdown": max_drawdown,
        "drawdown_headroom": (
            None if drawdown is None or max_drawdown is None
            else max_drawdown - drawdown
        ),
        "margin": report.get("margin"),
        "health_ok": report.get("health_ok"),
        "pre_correlation_eligible": report.get("eligible"),
        "non_correlation_checks_pass": report.get("non_correlation_checks_pass"),
        "blocking_checks": blocking_checks,
        "structural_blockers": [
            name for name in blocking_checks if name in STRUCTURAL_CHECK_BLOCKERS
        ],
        "repairable_blockers": [
            name for name in blocking_checks if name in REPAIRABLE_CHECK_BLOCKERS
        ],
        "reasons": report.get("reasons"),
    }
    context["opportunities"] = optimization_opportunities(
        report, blocking_checks=blocking_checks
    )
    context["readiness"] = optimization_readiness(
        report, blocking_checks=blocking_checks
    )
    # §37：只有 Turnover 真正进入 Fitness 分母、且 Fitness 未过线时，才提示
    # turnover 效率；Turnover <= 0.125 时继续压低 turnover 不会直接改善 Fitness。
    fitness_gap = report.get("fitness_gap")
    context["fitness_turnover_efficiency_hint"] = bool(
        report.get("turnover_penalty_active") is True
        and fitness_gap is not None and fitness_gap <= 0
    )
    return context
