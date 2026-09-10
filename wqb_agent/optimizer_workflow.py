"""已有研究证据驱动的优化候选工作流。

这个模块只编排已有证据、代码初筛和 Agent 已提供的 child hypothesis。
它不生成经济机制，不执行参数扫描，也不拥有 Simulation 或研究状态写入。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict

from .research_guard import overfit_expression_reason, parameter_only_change_reason
from .state import Experiment


@dataclass(frozen=True)
class OptimizerHooks:
    """Optimizer 所需的窄操作回调。"""

    ensure_loaded: Callable[[], None]
    terminal_expressions: Callable[[], set]


class OptimizerGateReport(TypedDict):
    parent_count: int
    done_parent_count: int
    ready_parent_count: int
    blocked_reasons: dict[str, int]
    simulation_done: int
    trajectory_recorded: int
    optimizer_candidates: int
    optimizer_rejected: int
    child_generated: int


class OptimizerWorkflow:
    """编排证据驱动的 CHILD 候选，不决定经济含义。

    Optimization evidence is process-local to the supplied trajectory
    object.  The persisted Alpha Feed contains only remote ID/status/time
    metadata and can change priority for an already-present trajectory row;
    it can never reconstruct a DONE parent or its metrics.
    """

    def __init__(
        self,
        *,
        trajectory,
        alpha_feed_cache,
        alpha_factory,
        quality_policy,
        operator_reference,
        hooks: OptimizerHooks,
    ):
        self.trajectory = trajectory
        self.alpha_feed_cache = alpha_feed_cache
        self.alpha_factory = alpha_factory
        self.quality_policy = quality_policy
        self.operator_reference = operator_reference
        self.hooks = hooks
        self.last_handoff_report: dict[str, int] = {}

    @staticmethod
    def _parent_rejections(parent):
        if not isinstance(parent, dict):
            return ["INVALID_PARENT"]
        if str(parent.get("status") or "").upper() != "DONE":
            return ["PARENT_NOT_DONE"]
        reasons = []
        metrics = parent.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            reasons.append("PARENT_METRICS_MISSING")
        if not isinstance(metrics, dict) or "checks" not in metrics:
            reasons.append("PARENT_CHECKS_INCOMPLETE")
        if not parent.get("expression"):
            reasons.append("PARENT_METRICS_MISSING")
        field_missing = False
        for key in ("fields_used", "datasets", "field_understanding",
                    "field_analysis", "field_source", "field_hypothesis_basis"):
            value = parent.get(key)
            if not value:
                field_missing = True
        if field_missing:
            reasons.append("PARENT_FIELD_EVIDENCE_MISSING")
        if (not parent.get("hypothesis_id") or
            not isinstance(parent.get("economic_mechanism"), str) or
            not parent["economic_mechanism"].strip()):
            reasons.append("PARENT_HYPOTHESIS_MISSING")
        return reasons

    def optimizable_signal_records(self, limit=128):
        """返回 trajectory 中已有 DONE 证据，并按 cloud metadata 排序。"""
        records = []
        rejected = 0
        cloud_ids = self._cloud_alpha_ids()
        for position, exp in enumerate(reversed(self.trajectory.recent(limit))):
            record = exp.to_dict()
            reasons = self._parent_rejections(record)
            if reasons:
                rejected += 1
                continue
            # Keep evidence ownership separate from the compatibility source
            # label consumed by existing proposal/batch statistics.
            record["evidence_source"] = "local_trajectory"
            record["priority_source"] = (
                "cloud_metadata"
                if str(exp.alpha_id or "") in cloud_ids
                else "trajectory_recency"
            )
            record["optimization_source"] = (
                "cloud" if str(exp.alpha_id or "") in cloud_ids else "current_run"
            )
            record["optimization_recency"] = position
            records.append(record)
        records.sort(
            key=lambda item: (
                item.get("optimization_source") != "cloud",
                item.get("optimization_recency", 0),
            )
        )
        self.last_handoff_report = {
            "simulation_done": sum(
                1 for exp in self.trajectory.recent(limit)
                if str(getattr(exp, "status", "")).upper() == "DONE"
            ),
            "trajectory_recorded": len(records),
            "optimizer_candidates": len(records),
            "optimizer_rejected": rejected,
            "child_generated": 0,
        }
        return records

    def _cloud_alpha_ids(self):
        """读取 weekly cache 中的 Alpha ID，仅作为优先级提示。

        This method intentionally returns IDs only; it never creates a local
        Experiment, imports remote metrics, or changes the trajectory.
        """
        payload = self.alpha_feed_cache.load()
        if not isinstance(payload, dict):
            return set()
        ids = set()
        for bucket in (payload.get("days") or {}).values():
            if not isinstance(bucket, dict):
                continue
            for key in ("simulations", "submitted_alphas"):
                for row in bucket.get(key) or ():
                    if not isinstance(row, dict):
                        continue
                    alpha_id = row.get("alpha_id") or row.get("id")
                    if alpha_id is not None and str(alpha_id).strip():
                        ids.add(str(alpha_id))
        return ids

    def _agent_screen_optimization_parents(self, parents):
        """验证 Agent 已提供的经济机制和反过拟合约束。"""
        selected = []
        for parent in parents or ():
            if not isinstance(parent, dict):
                continue
            child = parent.get("child_economic_hypothesis")
            if not isinstance(child, dict):
                continue
            required = ("expression", "economic_mechanism", "change_type")
            if not all(
                isinstance(child.get(key), str) and child[key].strip()
                for key in required
            ):
                continue
            if parameter_only_change_reason(
                parent.get("expression"), child.get("expression")
            ) or overfit_expression_reason(child.get("expression")):
                continue
            selected.append(parent)
        return selected

    @staticmethod
    def _optimizer_value(parent, key, default=None):
        if isinstance(parent, dict):
            return parent.get(key, default)
        return getattr(parent, key, default)

    def gate_report(self, parents=None):
        """返回纯计数 gate，不泄漏指标或 Alpha 标识。"""
        if parents is None:
            parents = [
                experiment.to_dict()
                for experiment in self.trajectory.recent(128)
            ]
        report: OptimizerGateReport = {
            "parent_count": 0,
            "done_parent_count": 0,
            "ready_parent_count": 0,
            "blocked_reasons": {},
            "simulation_done": 0, "trajectory_recorded": 0,
            "optimizer_candidates": 0, "optimizer_rejected": 0,
            "child_generated": 0,
        }

        def block(reason):
            blocked = report["blocked_reasons"]
            blocked[reason] = blocked.get(reason, 0) + 1

        for parent in parents or []:
            report["parent_count"] += 1
            if not isinstance(parent, (dict, Experiment)):
                block("INVALID_PARENT")
                continue
            if str(self._optimizer_value(parent, "status", "")).upper() != "DONE":
                block("PARENT_NOT_DONE")
                continue
            report["done_parent_count"] += 1
            missing = self._parent_rejections(
                parent if isinstance(parent, dict) else parent.to_dict()
            )
            missing = list(missing)
            if not isinstance(self._optimizer_value(parent, "child_economic_hypothesis"), dict):
                missing.append("PARENT_INCREMENTAL_EVIDENCE_INSUFFICIENT")
            if missing:
                for reason in missing:
                    block(reason)
                continue
            report["ready_parent_count"] += 1
        report["simulation_done"] = report["done_parent_count"]
        report["trajectory_recorded"] = report["ready_parent_count"]
        report["optimizer_candidates"] = report["ready_parent_count"]
        report["optimizer_rejected"] = max(
            0, report["parent_count"] - report["ready_parent_count"]
        )
        return report

    def generate(self, parents=None, *, max_candidates=4):
        """生成受限 CHILD proposal；绝不自行补全 hypothesis。"""
        self.hooks.ensure_loaded()
        parents = (
            self.optimizable_signal_records()
            if parents is None else parents
        )
        quality = self.quality_policy or {}
        code_screened = self.alpha_factory.screen_optimization_parents(
            parents,
            excluded_expressions=self.hooks.terminal_expressions(),
            min_sharpe=quality.get("promising_sharpe", 0.9),
            min_fitness=quality.get("promising_fitness", 0.6),
            min_turnover=quality.get("min_turnover", 0.01),
            max_turnover=quality.get("max_turnover", 0.7),
        )
        agent_screened = self._agent_screen_optimization_parents(code_screened)
        result = self.alpha_factory.optimize_signal_proposals(
            agent_screened,
            self.operator_reference,
            max_candidates=max_candidates,
            excluded_expressions=self.hooks.terminal_expressions(),
            min_sharpe=quality.get("promising_sharpe", 0.9),
            min_fitness=quality.get("promising_fitness", 0.6),
            min_turnover=quality.get("min_turnover", 0.01),
            max_turnover=quality.get("max_turnover", 0.7),
        )
        self.last_handoff_report.update({
            "optimizer_candidates": len(agent_screened),
            "optimizer_rejected": max(0, len(parents) - len(agent_screened)),
            "child_generated": len(result or []),
        })
        return result
