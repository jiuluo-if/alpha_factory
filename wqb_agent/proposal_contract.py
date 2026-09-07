"""Pure proposal contract and allocation validation.

This module has no transport, persistence, or Agent dependency.  Keeping the
proposal contract here lets the long-running orchestrator compose discovery,
execution, and state updates without owning every validation rule itself.
"""

import hashlib
import os
import re

from .diversity import extract_fields
from .validation_report import validate_plan


PROPOSAL_EXPERIMENT_QS = {
    "field_understanding": "字段含义及其信息含义（必须基于本轮 discovery）",
    "operator_mapping": "算子如何表达该经济机制",
    "experiment_question": "本次 simulation 要回答的单一问题",
}

RESEARCH_ROLES = {"EXPLORE", "EXPLOIT", "VALIDATION"}
# 18 remains the safe default.  Larger batches are an explicit configuration
# choice for factory runs; the upper bound prevents an accidental unbounded
# inbox from becoming a production batch.
MAX_PROPOSALS_PER_ROUND = 18
MAX_CONFIGURED_PROPOSALS_PER_ROUND = 100
EXPERIMENT_STAGES = {"BASELINE", "CHILD", "ROBUSTNESS"}
CHILD_CHANGE_TYPES = {
    "field_swap", "window_change", "operator_variant", "smoothing",
    "neutralization", "decay", "window_locality", "semantic_field_swap",
    "universe", "universe_robustness", "decay_truncation",
}
SETTING_OVERRIDES = {"universe", "truncation", "decay"}
_VEC_INPUT_RE = re.compile(
    r"\b(vec_avg|vec_sum)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
    re.IGNORECASE,
)
_EXPR_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_EXPR_NON_FIELD_IDENTIFIERS = {
    "abs", "add", "and", "bucket", "densify", "divide", "group_backfill", "group_mean", "group_neutralize",
    "group_rank", "group_scale", "group_zscore", "if_else", "inverse", "is_nan", "kth_element", "log", "max",
    "min", "multiply", "normalize", "not", "or", "power", "quantile", "rank", "reverse", "scale", "sign", "signed_power", "sqrt", "subtract",
    "trade_when", "days_from_last_change", "last_diff_value", "ts_arg_max", "ts_arg_min", "ts_av_diff", "ts_backfill", "ts_corr", "ts_count_nans", "ts_covariance", "ts_decay_linear", "ts_delay",
    "ts_delta", "ts_mean", "ts_product", "ts_quantile", "ts_rank", "ts_regression", "ts_scale", "ts_step",
    "ts_std_dev", "ts_sum", "ts_zscore", "vec_avg", "vec_sum", "winsorize", "zscore",
    "driver", "gaussian", "cauchy", "uniform", "filter", "dense", "constant",
    "longscale", "shortscale", "std", "rate", "hump", "ignore", "range", "sigma",
    "subindustry", "industry", "sector", "market", "lookback",
}


def proposal_budget_cap(candidates_per_round, allocation_cap, hard_cap=18):
    """Return the effective cap under config and an explicit bounded limit."""
    try:
        hard_cap = max(0, min(int(hard_cap), MAX_CONFIGURED_PROPOSALS_PER_ROUND))
    except (TypeError, ValueError):
        hard_cap = 18
    return max(
        0, min(int(candidates_per_round), int(allocation_cap), hard_cap),
    )


def _operator_reference(path):
    """Read the checked-in operator table and produce proposal evidence."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    operators = sorted(set(re.findall(r"`([a-z][a-z0-9_]*)\s*\(", text)))
    return {
        "path": os.path.abspath(path),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "operators": operators,
    }


def _expression_operators(expression):
    return sorted(set(re.findall(r"\b([a-z][a-z0-9_]*)\s*\(", expression or "")))


def validate_proposal(p, discovered_fields=None, strict_experiment=False,
                      operator_reference=None, require_research_evidence=False,
                      max_alpha_count=None):
    """Validate proposal metadata and field/operator provenance."""
    if not isinstance(p, dict):
        return False, ["proposal 必须是对象"]
    problems = []
    expression = (p.get("expression") or "").strip()
    declared_fields = p.get("fields")
    if not isinstance(declared_fields, list) or not declared_fields:
        problems.append("fields 必须是非空数组")
    elif expression and not extract_fields(expression, [str(f) for f in declared_fields]):
        problems.append("fields 必须至少包含一个实际出现在 expression 中的真实字段")
    if strict_experiment:
        for key, meaning in PROPOSAL_EXPERIMENT_QS.items():
            value = p.get(key)
            valid = (
                isinstance(value, dict) and bool(value)
                if key == "field_understanding"
                else isinstance(value, str) and bool(value.strip())
            )
            if not valid:
                problems.append(f"缺 {key}（{meaning}）")
        if not isinstance(p.get("datasets"), list) or not p.get("datasets"):
            problems.append("datasets 必须是非空数组")
        failure_modes = p.get("expected_failure_modes")
        if not (isinstance(failure_modes, list) and failure_modes
                and all(isinstance(x, str) and x.strip() for x in failure_modes)):
            problems.append("expected_failure_modes 必须是非空字符串数组")
        if not isinstance(p.get("tuning_risk"), bool):
            problems.append("tuning_risk 必须显式为 true 或 false")
        stage = p.get("experiment_stage")
        change_type = p.get("change_type")
        if stage not in EXPERIMENT_STAGES:
            problems.append(f"experiment_stage 必须是 {sorted(EXPERIMENT_STAGES)} 之一")
        elif stage == "BASELINE":
            if change_type not in (None, "baseline"):
                problems.append("BASELINE 的 change_type 只能是 baseline 或省略")
        else:
            if change_type not in CHILD_CHANGE_TYPES:
                problems.append(
                    "Child/ROBUSTNESS 必须声明单一 change_type: "
                    + ", ".join(sorted(CHILD_CHANGE_TYPES))
                )
            if not isinstance(p.get("parent_expression"), str) or not p["parent_expression"].strip():
                problems.append("Child/ROBUSTNESS 必须声明已完成 baseline 的 parent_expression")
            if not isinstance(p.get("changed_variable"), str) or not p["changed_variable"].strip():
                problems.append("Child/ROBUSTNESS 必须声明唯一 changed_variable")
            if stage == "ROBUSTNESS":
                plan_ok, plan_errors = validate_plan(p.get("validation_plan"))
                if not plan_ok:
                    problems.extend(["ROBUSTNESS 必须先注册 ValidationPlan: " + error
                                     for error in plan_errors])
        profiles = {
            str(field.get("id")): field for field in (discovered_fields or [])
            if isinstance(field, dict) and field.get("id")
        }
        if not profiles:
            problems.append("缺少本轮 discovery 字段画像；请先运行 --suggest")
        else:
            used = extract_fields(expression, [str(f) for f in declared_fields or []])
            understanding = p.get("field_understanding")
            if not isinstance(understanding, dict):
                problems.append("field_understanding 必须是以 field id 为键的对象")
            for field_id in used:
                profile = profiles.get(field_id)
                if profile is None:
                    problems.append(f"字段 {field_id} 不在本轮真实 discovery 中")
                    continue
                if profile.get("semantic_status") == "UNKNOWN" or not profile.get("description"):
                    problems.append(f"字段 {field_id} 缺平台语义 metadata，状态为 UNKNOWN")
                entry = understanding.get(field_id) if isinstance(understanding, dict) else None
                if not isinstance(entry, str) or not entry.strip():
                    problems.append(f"field_understanding 缺 {field_id} 的解释")
                if max_alpha_count is not None:
                    count = profile.get("alpha_count", profile.get("alphaCount"))
                    try:
                        if count is not None and float(count) > float(max_alpha_count):
                            problems.append(f"字段 {field_id} alphaCount={count} 超过上限 {max_alpha_count}")
                    except (TypeError, ValueError):
                        problems.append(f"字段 {field_id} alphaCount 无法判读")
            analysis = p.get("field_analysis")
            if not isinstance(analysis, dict):
                problems.append("field_analysis 必须逐字段记录 semantic/coverage/frequency/data_type")
            else:
                for field_id in used:
                    item = analysis.get(field_id)
                    if not isinstance(item, dict):
                        problems.append(f"field_analysis 缺 {field_id} 的字段画像")
                        continue
                    required = {"semantic", "coverage", "frequency", "data_type"}
                    if not required.issubset(item):
                        problems.append(f"field_analysis 缺 {field_id} 的 semantic/coverage/frequency/data_type")
                        continue
                    if item.get("data_type") != (profiles.get(field_id) or {}).get("type"):
                        problems.append(f"field_analysis 的 {field_id} data_type 必须与 BRAIN discovery 一致")
            identifiers = set(_EXPR_IDENTIFIER_RE.findall(expression))
            unknown = sorted(
                ident for ident in identifiers
                if ident not in profiles and ident.lower() not in _EXPR_NON_FIELD_IDENTIFIERS
            )
            if unknown:
                problems.append(f"表达式含本轮 discovery 未确认的字段/标识符: {unknown}")
            if require_research_evidence:
                basis = p.get("field_hypothesis_basis")
                if not isinstance(basis, dict):
                    problems.append("field_hypothesis_basis 必须逐字段引用真实 description 并说明机制")
                else:
                    for field_id in used:
                        item = basis.get(field_id)
                        profile = profiles.get(field_id) or {}
                        if not isinstance(item, dict) or not isinstance(item.get("mechanism"), str) or not item["mechanism"].strip():
                            problems.append(f"field_hypothesis_basis 缺 {field_id} 的机制说明")
                        elif item.get("description") != profile.get("description"):
                            problems.append(f"field_hypothesis_basis 的 {field_id} 必须逐字引用 discovery description")
                evidence = p.get("operator_evidence")
                actual_ops = set(_expression_operators(expression))
                if not isinstance(evidence, dict):
                    problems.append("operator_evidence 必须记录算子表 hash、实际算子及理由")
                elif evidence.get("sha256") != (operator_reference or {}).get("sha256"):
                    problems.append("operator_evidence 不匹配当前 OPERATORS_CHEATSHEET 快照")
                else:
                    declared_ops = set(evidence.get("operators") or [])
                    allowed_ops = set((operator_reference or {}).get("operators") or [])
                    if not actual_ops.issubset(declared_ops):
                        problems.append("operator_evidence 必须覆盖表达式实际使用的全部算子")
                    if not actual_ops.issubset(allowed_ops):
                        problems.append("表达式含不在 OPERATORS_CHEATSHEET 的算子")
                    if not isinstance(evidence.get("rationale"), str) or not evidence["rationale"].strip():
                        problems.append("operator_evidence 缺少算子选择理由")
    return not problems, problems


def proposal_priority(proposal):
    """Small, inspectable priority heuristic; it is not a tuning score."""
    if not isinstance(proposal, dict):
        return 0.0

    def value(name, default=1.0):
        try:
            return max(0.1, float(proposal.get(name, default)))
        except (TypeError, ValueError):
            return default
    return value("expected_quality") * value("information_gain") * value("novelty") / value("simulation_cost")


def validate_vector_inputs(p, field_types):
    """Require vec_avg/vec_sum inputs to be verified VECTOR fields."""
    if not isinstance(p, dict):
        return False, ["proposal 必须是对象"]
    if not isinstance(field_types, dict):
        return False, ["field_types 必须是对象"]
    problems = []
    for operator, field_id in _VEC_INPUT_RE.findall(p.get("expression") or ""):
        field_type = (field_types.get(field_id) or "").upper()
        if not field_type:
            problems.append(f"{operator} 输入字段 {field_id} 类型未知；须先查平台真实字段类型")
        elif field_type != "VECTOR":
            problems.append(f"{operator} 只能作用于 VECTOR；{field_id} 实际类型为 {field_type}")
    return not problems, problems
