import re

from .alpha_factory import AlphaFactory
from .diversity import extract_fields
from .expression import canonical_expression
from .mutations import _swap_field, _window_change
from .research_guard import is_direction_only_change, overfit_expression_reason


# Bounded, knowledge-backed single-step changes only. No random operator
# stacking, no arbitrary "special window" hunting.
class CandidateBuilder:
    def __init__(self, neutralization="SUBINDUSTRY", catalog_path=None,
                 require_private=False):
        self.neutralization = neutralization.lower()
        self.factory = AlphaFactory(
            neutralization=neutralization, catalog_path=catalog_path,
            require_private=require_private,
        )

    def build(self, hypothesis, fields, current_best, count=6):
        if AlphaFactory.requested(hypothesis) and not current_best:
            return self.factory.generate(hypothesis, fields, count=count)
        if current_best and current_best.get("expression"):
            return self._mutate_best(hypothesis, fields, current_best, count)
        return self._from_scratch(hypothesis, fields, count)

    @staticmethod
    def _main_field(fields):
        if not isinstance(fields, (list, tuple)) or not fields:
            return None
        first = fields[0]
        if isinstance(first, dict):
            field_id = first.get("id")
            return field_id if isinstance(field_id, (str, int)) else None
        return first if isinstance(first, (str, int)) else None

    def _from_scratch(self, hypothesis, fields, count):
        primary = self._main_field(fields)
        if not primary:
            return []
        all_ids = [primary] + [
            f.get("id") for f in fields
            if isinstance(f, dict) and isinstance(f.get("id"), (str, int))
        ]
        generated = self.factory.generate(
            {"selection_group": "candidate_scratch"}, fields, count=count
        )
        candidates = []
        reversal = hypothesis.get("direction") == "reversal"
        for item in generated:
            candidate = dict(item)
            expression = candidate["expression"]
            if reversal:
                if expression.startswith("group_neutralize(rank("):
                    expression = expression.replace(
                        "group_neutralize(rank(", "group_neutralize(-rank(", 1
                    )
                else:
                    expression = f"-{expression}"
            candidate["expression"] = expression
            candidate["parent"] = None
            candidate["fields_used"] = extract_fields(expression, all_ids)
            candidate["rationale"] = candidate.get("rationale") or "Catalog baseline."
            candidate["mutation"] = candidate.get("mutation") or (
                f"template:{candidate['template_id']}"
            )
            candidates.append(candidate)
        return candidates[:count]

    def _mutate_best(self, hypothesis, fields, current_best, count):
        best_expr = current_best["expression"]
        best_fields = current_best.get("fields_used") or []
        primary = best_fields[0] if best_fields else self._main_field(fields)
        candidate_fields = [
            f.get("id") for f in fields if isinstance(f, dict) and f.get("id")
        ]
        secondary = None
        for fid in candidate_fields:
            if fid != primary:
                secondary = fid
                break
        group = self.neutralization
        candidates = []
        seen_expressions = {canonical_expression(best_expr)}

        def add(expression, rationale, mutation):
            identity = canonical_expression(expression)
            if identity in seen_expressions:
                return
            if overfit_expression_reason(expression):
                return
            if is_direction_only_change(best_expr, expression):
                return
            seen_expressions.add(identity)
            candidates.append(
                {
                    "expression": expression,
                    "rationale": rationale,
                    "mutation": mutation,
                    "parent": current_best.get("id"),
                    # 只记录表达式实际用到的字段（含辅助腿），
                    # 供 AGENTS.md §6 信号族比对使用，不记 discovery 清单。
                    "fields_used": extract_fields(expression, candidate_fields),
                }
            )

        if secondary:
            swapped = _swap_field(best_expr, primary, secondary)
            if swapped:
                add(
                    swapped,
                    f"Single-variable field swap: {primary} -> {secondary}.",
                    "field-swap",
                )

        # Knowledge-backed mutation: combine two fields' standardized signals
        # as a bounded confirmation structure.
        combo = re.fullmatch(r"rank\(ts_zscore\(([^,()]+),\s*(\d+)\)\)", best_expr)
        if combo and secondary:
            sibling = f"rank(ts_zscore({combo.group(1)}, {combo.group(2)}) + ts_zscore({secondary}, {combo.group(2)}))"
            add(
                sibling,
                f"Additive combination with sibling field {secondary} "
                f"(two-field z-score combo family).",
                "add-sibling-zscore",
            )

        add(
            f"ts_mean({best_expr}, 5)",
            "Wrap in 5d ts_mean to reduce turnover.",
            "smooth-ts-mean-5",
        )

        add(
            f"ts_mean({best_expr}, 10)",
            "Wrap in 10d ts_mean for stronger turnover reduction.",
            "smooth-ts-mean-10",
        )

        add(
            f"group_neutralize({best_expr}, {group})",
            f"Add {group} neutralization layer.",
            f"neutralize-{group}",
        )

        new_window = self._next_window(best_expr, primary)
        if new_window:
            add(
                new_window,
                "Single-step window change on the time-series operator.",
                "window-step",
            )

        new_window2 = self._next_window(new_window, primary) if new_window else None
        if new_window2:
            add(
                new_window2,
                "Two-step window change on the time-series operator.",
                "window-step-2",
            )

        if "ts_rank" not in best_expr:
            add(
                f"rank(ts_rank({primary}, 20))",
                "Replace primary field with 20d time-series rank.",
                "ts-rank-20",
            )

        if len(candidates) < count and "zscore(" not in best_expr:
            add(
                f"zscore({best_expr})",
                "Add a zscore normalization layer.",
                "zscore-layer",
            )

        return candidates[:count]

    @staticmethod
    def _next_window(expression, primary_field):
        """向上步进（兼容旧调用）；统一实现见模块级 _window_change。"""
        return _window_change(expression, +1)
