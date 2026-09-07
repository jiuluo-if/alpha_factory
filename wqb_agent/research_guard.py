"""Read-only guard against low-information research loops.

The guard does not close a promising lineage globally.  It blocks only an
already-resolved structural action that has repeated without material gain;
the caller can still try a different change category or research family.
"""

from collections import defaultdict
import re

from .expression import canonical_expression
from .metrics import score_of


def _lineage(candidate, default_lineage=None):
    return (
        candidate.get("lineage_id")
        or candidate.get("parent_expression")
        or default_lineage
        or candidate.get("hypothesis_id")
        or "unknown"
    )


def structural_action_key(candidate, default_lineage=None):
    """Stable key for same lineage + family + one variable + expression."""
    fields = candidate.get("fields_used") or candidate.get("fields") or []
    fields = [
        str(item.get("id") if isinstance(item, dict) else item)
        for item in fields
    ]
    family = candidate.get("template_family") or candidate.get("signal_family") or "|".join(sorted(fields))
    change = candidate.get("change_type") or candidate.get("mutation") or "baseline"
    return (
        str(_lineage(candidate, default_lineage)),
        str(family),
        str(change),
        canonical_expression(candidate.get("expression")),
    )


def structural_family_key(expression, fields=None):
    """Return an operator/window skeleton independent of the field id.

    A proposal may omit ``template_family`` (for example, an external AI
    adapter can provide only an expression and field metadata).  In that
    case, different sibling fields can otherwise make the same
    ``rank(ts_delta(field, 5))`` construction look like unrelated families.
    This key is only a bounded batch-diversity identity; exact historical
    dedupe still uses the canonical expression/fingerprint and trajectory.
    """
    normalized = canonical_expression(expression)
    valid_fields = sorted(
        {
            str(field.get("id") if isinstance(field, dict) else field)
            for field in (fields or [])
            if isinstance(field, (str, int))
            or (isinstance(field, dict) and isinstance(field.get("id"), (str, int)))
        },
        key=len,
        reverse=True,
    )
    for field in valid_fields:
        if not field:
            continue
        normalized = re.sub(
            rf"(?<![\w]){re.escape(field.lower())}(?![\w])",
            "<field>",
            normalized,
        )
    return normalized


def _numeric_score(metrics):
    value = score_of(metrics)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ResearchLoopGuard:
    """Build bounded history indexes and explain one candidate decision."""

    def __init__(self, experiments=None, max_no_gain_same_change=2):
        self.max_no_gain_same_change = max(1, int(max_no_gain_same_change))
        self._actions = set()
        self._by_action = defaultdict(list)
        for experiment in experiments or []:
            self.add(experiment)

    @staticmethod
    def _as_candidate(experiment):
        if isinstance(experiment, dict):
            return experiment
        return {
            "expression": getattr(experiment, "expression", ""),
            "fields_used": getattr(experiment, "fields_used", []),
            "lineage_id": getattr(experiment, "lineage_id", None),
            "hypothesis_id": getattr(experiment, "hypothesis_id", None),
            "change_type": getattr(experiment, "change_type", None),
            "mutation": getattr(experiment, "mutation", None),
            "template_family": getattr(experiment, "template_family", None),
            "signal_family": getattr(experiment, "signal_family", None),
            "status": getattr(experiment, "status", None),
            "metrics": getattr(experiment, "metrics", None),
        }

    def add(self, experiment):
        record = self._as_candidate(experiment)
        key = structural_action_key(record)
        self._actions.add(key)
        # Only resolved, scored experiments can establish a research loop.
        score = _numeric_score(record.get("metrics"))
        if record.get("status") != "DONE" or score is None or score < 0:
            return
        group = key[:3]
        self._by_action[group].append(score)

    def check(self, candidate, default_lineage=None):
        candidate = dict(candidate or {})
        key = structural_action_key(candidate, default_lineage)
        if key in self._actions:
            return False, "同一谱系的同模板/同变更/同表达式已完成，禁止重复研究"
        scores = self._by_action.get(key[:3], [])
        if len(scores) < self.max_no_gain_same_change:
            return True, None
        best = max(scores)
        # score_of is Fitness-first; a meaningful improvement must exceed the
        # same threshold used by lineage memory (0.05).
        if best <= min(scores) + 0.05:
            return False, (
                f"同一谱系的 {key[2]} 已连续 {len(scores)} 次无实质增益；"
                "请切换 field/operator/window/smoothing 等变更类别"
            )
        return True, None

    def snapshot(self):
        blocked = []
        for (lineage, family, change), scores in sorted(self._by_action.items()):
            if len(scores) >= self.max_no_gain_same_change and max(scores) <= min(scores) + 0.05:
                blocked.append({
                    "lineage_id": lineage,
                    "family": family,
                    "change_type": change,
                    "resolved_attempts": len(scores),
                    "best_score": max(scores),
                    "recommendation": "切换单变量类别或新研究族",
                })
        return {
            "policy": "same_change_type_no_gain_guard",
            "max_no_gain_same_change": self.max_no_gain_same_change,
            "blocked_actions": blocked,
            "resolved_action_groups": len(self._by_action),
        }
