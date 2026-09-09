"""已有研究证据驱动的优化候选工作流。

这个模块只编排已有证据、代码初筛和 Agent 已提供的 child hypothesis。
它不生成经济机制，不执行参数扫描，也不拥有 Simulation 或研究状态写入。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .research_guard import overfit_expression_reason, parameter_only_change_reason
from .state import Experiment


@dataclass(frozen=True)
class OptimizerHooks:
    """Optimizer 所需的窄操作回调。"""

    ensure_loaded: Callable[[], None]
    terminal_expressions: Callable[[], set]


class OptimizerWorkflow:
    """编排证据驱动的 CHILD 候选，不决定经济含义。"""

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

    def optimizable_signal_records(self, limit=128):
        """返回已有 DONE 证据，并按 cloud 轻量索引提示排序。"""
        records = []
        cloud_ids = self._cloud_alpha_ids()
        for position, exp in enumerate(reversed(self.trajectory.recent(limit))):
            if exp.status != "DONE" or not exp.metrics:
                continue
            if not exp.field_analysis or not exp.field_understanding:
                continue
            record = exp.to_dict()
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
        return records

    def _cloud_alpha_ids(self):
        """读取 weekly cache 中的 Alpha ID，仅作为优先级提示。"""
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
        report = {
            "parent_count": 0,
            "done_parent_count": 0,
            "ready_parent_count": 0,
            "blocked_reasons": {},
        }

        def block(reason):
            blocked = report["blocked_reasons"]
            blocked[reason] = blocked.get(reason, 0) + 1

        for parent in parents or []:
            report["parent_count"] += 1
            if not isinstance(parent, (dict, Experiment)):
                block("invalid_parent")
                continue
            if str(self._optimizer_value(parent, "status", "")).upper() != "DONE":
                block("parent_not_done")
                continue
            report["done_parent_count"] += 1
            missing = []
            metrics = self._optimizer_value(parent, "metrics")
            if not isinstance(metrics, dict) or not metrics:
                missing.append("metrics")
            if not self._optimizer_value(parent, "fields_used"):
                missing.append("fields_used")
            if not self._optimizer_value(parent, "datasets"):
                missing.append("datasets")
            if not isinstance(
                self._optimizer_value(parent, "field_understanding"), dict
            ):
                missing.append("field_understanding")
            if not isinstance(
                self._optimizer_value(parent, "field_analysis"), dict
            ):
                missing.append("field_analysis")
            if not isinstance(
                self._optimizer_value(parent, "child_economic_hypothesis"), dict
            ):
                missing.append("child_economic_hypothesis")
            if missing:
                for reason in missing:
                    block(f"missing_{reason}")
                continue
            report["ready_parent_count"] += 1
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
        return self.alpha_factory.optimize_signal_proposals(
            agent_screened,
            self.operator_reference,
            max_candidates=max_candidates,
            excluded_expressions=self.hooks.terminal_expressions(),
            min_sharpe=quality.get("promising_sharpe", 0.9),
            min_fitness=quality.get("promising_fitness", 0.6),
            min_turnover=quality.get("min_turnover", 0.01),
            max_turnover=quality.get("max_turnover", 0.7),
        )
