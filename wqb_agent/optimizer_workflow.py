"""已有研究证据驱动的优化候选工作流。

这个模块只编排已有证据、代码初筛和 Agent 已提供的 child hypothesis。
它不生成经济机制，不执行参数扫描，也不拥有 Simulation 或研究状态写入。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypedDict

from .optimization_decision import (
    OptimizationDecision,
    decision_rejections,
    summarize_parent,
)
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
    evidence_eligible_parent_count: int
    evidence_rejected_parent_count: int
    agent_reviewed_parent_count: int
    agent_decision_child_count: int
    agent_decision_validate_count: int
    agent_decision_reroute_count: int
    agent_decision_stop_count: int
    child_generated_count: int
    child_done_count: int
    incremental_pass_count: int
    incremental_fail_count: int
    incremental_unknown_count: int
    ready_parent_count: int
    blocked_reasons: dict[str, int]
    simulation_done: int
    trajectory_recorded: int
    optimizer_candidates: int
    optimizer_rejected: int
    child_generated: int


def _decision_for_parent(parent):
    """Build the formal decision for one parent record, if the Agent supplied one."""
    payload = parent.get("optimization_decision")
    if isinstance(payload, Mapping):
        try:
            return OptimizationDecision.from_mapping(payload)
        except (TypeError, ValueError):
            return None
    child = parent.get("child_economic_hypothesis")
    if isinstance(child, Mapping):
        try:
            return OptimizationDecision.from_child_hypothesis(
                str(parent.get("id") or ""), child
            )
        except (TypeError, ValueError):
            return None
    return None


def optimizer_conversions(report):
    """Agent Optimization Yield：derived 转化率；分母 0 一律 None。"""
    def ratio(numerator, denominator):
        if not denominator:
            return None
        return numerator / denominator

    return {
        "done_to_evidence_parent": ratio(
            report["evidence_eligible_parent_count"], report["done_parent_count"]
        ),
        "evidence_parent_to_agent_review": ratio(
            report["agent_reviewed_parent_count"],
            report["evidence_eligible_parent_count"],
        ),
        "agent_review_to_child_decision": ratio(
            report["agent_decision_child_count"], report["agent_reviewed_parent_count"]
        ),
        "child_decision_to_child_generated": ratio(
            report["child_generated_count"], report["agent_decision_child_count"]
        ),
        "child_to_done": ratio(
            report["child_done_count"], report["child_generated_count"]
        ),
        "child_to_incremental_pass": ratio(
            report["incremental_pass_count"], report["child_done_count"]
        ),
    }


def optimization_eligibility_map(parents):
    """Per-parent optimizer stage map for the ResearchYield funnel.

    Keeps the two optimizer stages distinct: ``eligible`` is the Python
    evidence gate, ``reviewed`` / ``decision`` is the Agent
    ``OptimizationDecision``.  Only existing gate helpers are reused, so a
    parent that was never reviewed simply has no Agent stage.
    """
    result = {}
    for parent in parents or ():
        record = (
            parent if isinstance(parent, Mapping)
            else getattr(parent, "to_dict", lambda: {})()
        )
        if not isinstance(record, Mapping):
            continue
        key = (
            record.get("proposal_id") or record.get("id")
            or record.get("submission_fingerprint")
        )
        if key in (None, ""):
            continue
        plain = dict(record)
        reasons = list(OptimizerWorkflow._parent_rejections(plain))
        decision = _decision_for_parent(plain)
        result[str(key)] = {
            "eligible": not reasons,
            "reasons": reasons,
            "reviewed": decision is not None,
            "decision": decision.decision if decision is not None else None,
        }
    return result


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
        """验证 Agent 已提供的经济机制、单一变化与反过拟合约束。"""
        selected = []
        for parent in parents or ():
            if not isinstance(parent, dict):
                continue
            if isinstance(parent.get("optimization_decision"), Mapping):
                # 正式 OptimizationDecision 契约：完整字段 + 单一变化 +
                # self-correlation 准入；不再依赖隐式 dict mutation。
                decision = _decision_for_parent(parent)
                if decision is None or not decision.is_child:
                    continue
                if decision_rejections(decision, parent):
                    continue
                selected.append(parent)
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

    def inspect_optimizer_parents(self, limit=8):
        """有限、只读的 evidence-eligible parent summary（不泄漏无限历史）。"""
        self.hooks.ensure_loaded()
        limit = max(1, int(limit or 8))
        summaries = []
        for experiment in reversed(self.trajectory.recent(max(limit * 8, 64))):
            record = experiment.to_dict() if hasattr(experiment, "to_dict") else experiment
            if not isinstance(record, Mapping):
                continue
            if self._parent_rejections(dict(record)):
                continue
            summaries.append(summarize_parent(record))
        # Optimization-opportunity ranking: a parent with a concrete,
        # evidence-derived blocker outranks one with no clear opportunity.
        # This is a context-hint order, never an automatic action.
        summaries.sort(
            key=lambda item: item.get("opportunity") == "NO_CLEAR_OPPORTUNITY"
        )
        return summaries[:limit]

    @staticmethod
    def _optimizer_value(parent, key, default=None):
        if isinstance(parent, dict):
            return parent.get(key, default)
        return getattr(parent, key, default)

    def gate_report(self, parents=None, *, children=None):
        """返回纯计数 gate：evidence eligibility 与 Agent decision 分离。"""
        if parents is None:
            parents = [
                experiment.to_dict()
                for experiment in self.trajectory.recent(128)
            ]
        report: OptimizerGateReport = {
            "parent_count": 0,
            "done_parent_count": 0,
            "evidence_eligible_parent_count": 0,
            "evidence_rejected_parent_count": 0,
            "agent_reviewed_parent_count": 0,
            "agent_decision_child_count": 0,
            "agent_decision_validate_count": 0,
            "agent_decision_reroute_count": 0,
            "agent_decision_stop_count": 0,
            "child_generated_count": len(list(children or ())),
            "child_done_count": 0,
            "incremental_pass_count": 0,
            "incremental_fail_count": 0,
            "incremental_unknown_count": 0,
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
            record = parent if isinstance(parent, dict) else parent.to_dict()
            evidence = list(self._parent_rejections(record))
            missing = list(evidence)
            decision = _decision_for_parent(record)
            # Readiness needs an Agent-authored *CHILD* decision: either the
            # legacy ``child_economic_hypothesis`` dict or the formal
            # ``OptimizationDecision`` contract.  VALIDATE / REROUTE / STOP are
            # explicit decisions not to derive a child.  This stays separate
            # from the Python evidence gate counted above.
            if decision is None:
                missing.append("PARENT_INCREMENTAL_EVIDENCE_INSUFFICIENT")
            if evidence:
                report["evidence_rejected_parent_count"] += 1
            else:
                report["evidence_eligible_parent_count"] += 1
                if decision is not None:
                    report["agent_reviewed_parent_count"] += 1
                    if decision.decision == "CHILD":
                        report["agent_decision_child_count"] += 1
                    elif decision.decision == "VALIDATE":
                        report["agent_decision_validate_count"] += 1
                    elif decision.decision == "REROUTE":
                        report["agent_decision_reroute_count"] += 1
                    else:
                        report["agent_decision_stop_count"] += 1
            if missing:
                for reason in missing:
                    block(reason)
            if missing or decision is None or not decision.is_child:
                continue
            report["ready_parent_count"] += 1
        for child in children or ():
            record = (
                child if isinstance(child, dict)
                else getattr(child, "to_dict", lambda: {})()
            )
            if not isinstance(record, Mapping):
                continue
            if str(record.get("status") or "").upper() == "DONE":
                report["child_done_count"] += 1
            incremental_row = record.get("incremental_evidence")
            verdict = ""
            if isinstance(incremental_row, Mapping):
                verdict = str(incremental_row.get("decision") or "").upper()
            elif isinstance(record.get("final_outcome"), Mapping):
                verdict = str(
                    record["final_outcome"].get("incremental_decision") or ""
                ).upper()
            if verdict == "PASS":
                report["incremental_pass_count"] += 1
            elif verdict == "FAIL":
                report["incremental_fail_count"] += 1
            elif verdict:
                report["incremental_unknown_count"] += 1
        report["simulation_done"] = report["done_parent_count"]
        report["trajectory_recorded"] = report["evidence_eligible_parent_count"]
        report["optimizer_candidates"] = report["evidence_eligible_parent_count"]
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

    def _canonical_parent(self, parent_id):
        """Resolve one parent from canonical evidence; never fabricate a record."""
        target = str(parent_id or "")
        if not target:
            return None
        for experiment in reversed(self.trajectory.recent(256)):
            record = (
                experiment.to_dict() if hasattr(experiment, "to_dict") else experiment
            )
            if isinstance(record, Mapping) and str(record.get("id")) == target:
                return record
        finder = getattr(self.trajectory, "find_row", None)
        if callable(finder):
            row = finder(target)
            if isinstance(row, Mapping):
                return row
        return None

    def generate_from_decisions(self, decisions, *, max_candidates=4):
        """Validate Agent OptimizationDecisions, then reuse the one CHILD path.

        Python only checks the decision against canonical evidence and the
        deterministic gates; it never authors a mechanism.  Non-CHILD decisions
        (VALIDATE/STOP/REROUTE) never produce a child proposal.
        """
        self.hooks.ensure_loaded()
        accepted = []
        rejected = []
        for decision in decisions or ():
            if not isinstance(decision, OptimizationDecision):
                rejected.append({"parent_id": None, "reasons": ["DECISION_INVALID"]})
                continue
            parent = self._canonical_parent(decision.parent_id)
            if parent is None:
                rejected.append(
                    {"parent_id": decision.parent_id, "reasons": ["PARENT_NOT_FOUND"]}
                )
                continue
            reasons = list(self._parent_rejections(parent))
            if not reasons:
                reasons = list(decision_rejections(decision, parent))
            if not decision.is_child:
                rejected.append({
                    "parent_id": decision.parent_id,
                    "decision": decision.decision,
                    "reasons": reasons or ["NOT_A_CHILD_DECISION"],
                })
                continue
            if reasons:
                rejected.append({
                    "parent_id": decision.parent_id,
                    "decision": decision.decision,
                    "reasons": reasons,
                })
                continue
            record = dict(parent)
            record["optimization_decision"] = decision.as_dict()
            record["child_economic_hypothesis"] = decision.to_child_hypothesis()
            accepted.append(record)
        proposals = (
            self.generate(accepted, max_candidates=max_candidates)
            if accepted else []
        )
        return {
            "proposals": proposals,
            "accepted": [
                {"parent_id": record.get("id"),
                 "change_type": record["optimization_decision"].get("change_type")}
                for record in accepted
            ],
            "rejected": rejected,
            "decision_report": {
                "reviewed": len(list(decisions or ())),
                "accepted": len(accepted),
                "rejected": len(rejected),
                "child_generated": len(proposals or []),
            },
        }
