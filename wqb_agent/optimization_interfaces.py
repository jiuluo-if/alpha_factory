"""优化 Agent 的窄接口：证据采集、指标诊断和经验记账。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class OptimizationEvidenceSnapshot:
    """一个 Alpha 的真实只读证据快照；raw payload 仍由既有 owner 保存。"""

    alpha_id: str
    alpha_detail: Mapping[str, Any]
    aggregates: Mapping[str, Any]
    pnl: Any
    self_correlation: Mapping[str, Any] | None


class OptimizationEvidenceProvider(Protocol):
    def collect(self, alpha_id: str) -> OptimizationEvidenceSnapshot: ...


class ClientOptimizationEvidenceProvider:
    """将唯一 WQBClient 投影成优化专用的只读接口。"""

    def __init__(self, client):
        self.client = client

    def collect(self, alpha_id: str) -> OptimizationEvidenceSnapshot:
        alpha_id = str(alpha_id).strip()
        if not alpha_id:
            raise ValueError("alpha_id must be non-empty")
        return OptimizationEvidenceSnapshot(
            alpha_id=alpha_id,
            alpha_detail=self.client.get_alpha(alpha_id),
            aggregates=self.client.get_aggregates(alpha_id),
            pnl=self.client.get_pnl(alpha_id),
            self_correlation=self.client.get_self_correlation(alpha_id),
        )


@dataclass(frozen=True)
class OptimizationTrial:
    """可压缩写入 ExperienceMemory 的 trial 结论，不替代 TrialLedger。"""

    parent_id: str
    outcome: str
    mechanism: str
    changed_variable: str
    evidence_refs: Sequence[str] = ()
    competing_explanations: Sequence[str] = ()


class OptimizationExperienceSink(Protocol):
    def add_short_term(self, kind, text, round_no, *, evidence=1, detail=None): ...


def diagnose_optimization(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """返回 bounded hint，不替 Agent 做经济决策。"""
    if not isinstance(metrics, Mapping):
        return {"primary_problem": "MISSING_EVIDENCE", "recommended_focus": "STOP"}
    sharpe, turnover, returns = (_number(metrics.get(key))
                                 for key in ("sharpe", "turnover", "returns"))
    if sharpe is None or turnover is None or returns is None:
        return {"primary_problem": "MISSING_EVIDENCE", "recommended_focus": "RECONCILE"}
    if sharpe < 1.0:
        return {"primary_problem": "LOW_SHARPE", "recommended_focus": "SIGNAL_OR_MECHANISM"}
    if turnover > 0.125:
        return {"primary_problem": "HIGH_TURNOVER", "recommended_focus": "HORIZON_OR_SMOOTHING"}
    if returns <= 0:
        return {"primary_problem": "LOW_RETURN", "recommended_focus": "INFORMATION_DENSITY"}
    return {"primary_problem": "NO_CLEAR_HEADLINE_BLOCKER", "recommended_focus": "ROBUSTNESS"}


def record_optimization_trial(sink: OptimizationExperienceSink, trial: OptimizationTrial, *, round_no: int):
    """把成功、失败或剪枝 trial 投影到既有短期 memory owner。"""
    detail = {
        "optimization_trial": True,
        "parent_id": trial.parent_id,
        "outcome": str(trial.outcome).upper(),
        "mechanism": trial.mechanism,
        "changed_variable": trial.changed_variable,
        "evidence_refs": list(trial.evidence_refs),
        "competing_explanations": list(trial.competing_explanations),
    }
    return sink.add_short_term("observation", trial.mechanism, round_no,
                               evidence=1, detail=detail)


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
