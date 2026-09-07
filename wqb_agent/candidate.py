import re

from .diversity import extract_fields
from .alpha_factory import AlphaFactory
from .expression import canonical_expression
from .mutations import WINDOW_STEPS, _swap_field, _window_change

# Bounded, knowledge-backed single-step changes only. No random operator
# stacking, no arbitrary "special window" hunting.
class CandidateBuilder:
    def __init__(self, neutralization="SUBINDUSTRY"):
        self.neutralization = neutralization.lower()
        self.factory = AlphaFactory(neutralization=neutralization)

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
        reversal = hypothesis.get("direction") == "reversal"
        group = self.neutralization
        s = "-" if reversal else ""  # hypothesis-driven sign
        base = f"rank({primary})"
        candidates = [
            {
                "expression": f"{s}{base}",
                "rationale": "Baseline: raw cross-sectional rank of primary field.",
                "mutation": "baseline",
                "parent": None,
                "fields_used": extract_fields(f"{s}{base}", [primary] + [f["id"] for f in fields]),
            },
            {
                "expression": base if reversal else f"-{base}",
                "rationale": "Opposite sign of baseline rank.",
                "mutation": "sign-flip",
                "parent": None,
            },
            {
                "expression": f"{s}rank(ts_rank({primary}, 20))",
                "rationale": "Time-series rank over 20d to smooth cross-sectional noise.",
                "mutation": "ts-rank-20",
                "parent": None,
            },
            {
                "expression": f"{s}zscore({primary})",
                "rationale": "Standardize field with cross-sectional zscore.",
                "mutation": "zscore",
                "parent": None,
            },
            {
                "expression": f"group_neutralize({s}rank({primary}), {group})",
                "rationale": f"Neutralize baseline rank within {group}.",
                "mutation": f"neutralize-{group}",
                "parent": None,
            },
            {
                "expression": f"{s}rank(ts_mean({primary}, 5))",
                "rationale": "Short 5d mean of field to lower turnover.",
                "mutation": "ts-mean-5",
                "parent": None,
            },
            {
                "expression": f"{s}rank(ts_zscore({primary}, 20))",
                "rationale": "20d z-score of the field: level-relative signal.",
                "mutation": "ts-zscore-20",
                "parent": None,
            },
            {
                "expression": f"{s}rank(ts_zscore({primary}, 60))",
                "rationale": "60d z-score of the field: slower, lower-turnover signal.",
                "mutation": "ts-zscore-60",
                "parent": None,
            },
            {
                "expression": f"{s}rank(ts_delta({primary}, 5))",
                "rationale": "5d change of the field: short-term momentum/reversal of the signal.",
                "mutation": "ts-delta-5",
                "parent": None,
            },
        ]
        # 精确记录每个候选实际用到的字段（含辅助腿），供信号族比对。
        all_ids = [primary] + [
            f.get("id") for f in fields
            if isinstance(f, dict) and isinstance(f.get("id"), (str, int))
        ]
        for c in candidates:
            c["fields_used"] = extract_fields(c["expression"], all_ids)
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

        # Knowledge-backed mutation: for the champion template
        # rank(ts_zscore(field, N)), combine with a sibling field's z-score.
        # Legacy research validated two-field guidance z-score combinations
        # (Sharpe ~1.38) as an information-density improvement.
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

        if best_expr.startswith("-"):
            add(best_expr[1:], "Flip sign from negative to positive.", "sign-flip")
        else:
            add(f"-{best_expr}", "Flip sign from positive to negative.", "sign-flip")

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
