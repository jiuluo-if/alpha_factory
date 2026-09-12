"""Shared synthetic builders for optimizer decision/contract tests."""

import unittest
from dataclasses import replace
from pathlib import Path

from wqb_agent.alpha_factory import (
    DEFAULT_TEMPLATES,
    ECONOMIC_TEMPLATES,
    AlphaFactory,
    template_numeric_audit,
)
from wqb_agent.diversity import semantic_mechanism_key
from wqb_agent.optimization_decision import (
    CHILD_REQUIRED_TEXT_FIELDS,
    OPPORTUNITY_CATEGORIES,
    VALID_DECISIONS,
    VALIDATION_VARIABLES,
    OptimizationDecision,
    decision_rejections,
    parent_opportunity,
    summarize_parent,
)
from wqb_agent.optimizer_workflow import (
    OptimizerHooks,
    OptimizerWorkflow,
    optimization_eligibility_map,
    optimizer_conversions,
)
from wqb_agent.pre_correlation import (
    READINESS_BANDS,
    optimization_parent_admission,
    pre_self_correlation_eligibility,
)
from wqb_agent.proposal_contract import validate_proposal
from wqb_agent.research_yield import build_research_yield

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "wqb_agent"

MECHANISM = "质量变化驱动的相对定价差异"
IMPACT = {
    "expected_effect": "LOWER",
    "basis": "子域中性化降低与现有族的相关暴露",
    "rationale": "同一字段、同一机制，仅改变可比组",
    "admission": "ALLOW",
}
CHILD_EXPRESSION = "group_neutralize(rank(field_a), SUBINDUSTRY)"
PARENT_EXPRESSION = "rank(field_a)"


def parent_record(pid, expression=PARENT_EXPRESSION, **overrides):
    record = {
        "id": pid,
        "proposal_id": pid,
        "status": "DONE",
        "round": 1,
        "expression": expression,
        "fields_used": ["field_a"],
        "datasets": ["fundamental6"],
        "field_understanding": {"field_a": "已核验字段"},
        "field_analysis": {"field_a": {"data_type": "MATRIX"}},
        "field_source": {"kind": "brain_api"},
        "field_hypothesis_basis": {"field_a": {"mechanism": MECHANISM}},
        "hypothesis_id": "h-1",
        "economic_mechanism": MECHANISM,
        "semantic_mechanism_family": "m:quality:diffusion",
        "metrics": {
            "sharpe": 1.1,
            "fitness": 0.8,
            "turnover": 0.2,
            "checks": [{"name": "SELF_CORRELATION", "status": "UNKNOWN"}],
        },
        "self_correlation": {"status": "PASS"},
        "validation_status": "STABLE",
    }
    record.update(overrides)
    return record


def child_decision(parent_id, *, expression=CHILD_EXPRESSION, **overrides):
    payload = {
        "parent_id": parent_id,
        "decision": "CHILD",
        "observed_evidence": "父代子域内表现弱于整体",
        "economic_mechanism": MECHANISM,
        "change_type": "neutralization",
        "changed_variable": "neut",
        "expression": expression,
        "expected_effect": "lower sub-universe gap",
        "falsification": "若子域检查转差则机制不成立",
        "direction": "long",
        "direction_transform": {
            "applied": False,
            "reason": "沿用 parent 方向，不把方向翻转当作新机制",
        },
        "self_correlation_impact": IMPACT,
        "why_not_parameter_tuning": "改变可比组而非窗口/权重",
    }
    payload.update(overrides)
    return OptimizationDecision(**payload)


def validate_decision(parent_id, **overrides):
    payload = {
        "parent_id": parent_id,
        "decision": "VALIDATE",
        "validation_variable": "decay",
        "old_value": 4,
        "new_value": 5,
        "expected_effect": "验证 decay 邻域内换手与稳定性是否单调",
        "falsification": "若邻域内 Sharpe 反向恶化则稳定性假设不成立",
        "reason": "Fitness 未过线且 turnover 进入分母",
    }
    payload.update(overrides)
    return OptimizationDecision(**payload)


class FakeTrajectory:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def recent(self, limit):
        return self.rows[-limit:]


class FakeCache:
    def load(self):
        return {}


class RecordingFactory:
    def __init__(self):
        self.screen_calls = []
        self.optimize_calls = []

    def screen_optimization_parents(self, parents, **kwargs):
        self.screen_calls.append((list(parents), kwargs))
        return list(parents)

    def optimize_signal_proposals(self, parents, operator_reference, **kwargs):
        self.optimize_calls.append((list(parents), operator_reference, kwargs))
        return ["factory-result"]


def workflow(trajectory=None, factory=None, operators=None):
    return OptimizerWorkflow(
        trajectory=trajectory or FakeTrajectory(),
        alpha_feed_cache=FakeCache(),
        alpha_factory=factory or RecordingFactory(),
        quality_policy={},
        operator_reference={
            "operators": list(operators or ["rank", "group_neutralize"])
        },
        hooks=OptimizerHooks(
            ensure_loaded=lambda: None,
            terminal_expressions=lambda: set(),
        ),
    )
