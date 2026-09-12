"""Stable data model and rendering primitives for Alpha templates."""

import hashlib
import json
import re
from dataclasses import dataclass

from ..expression import analyze_expression

NUMBER_TOKEN_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")

FIXED_NUMERICS = {
    "0.001": ("SAFETY_CONSTANT", "divide epsilon；固定数值稳定性常量"),
    "0.2": ("OPERATOR_REQUIRED_CONSTANT", "trade_when 触发下界"),
    "0.8": ("OPERATOR_REQUIRED_CONSTANT", "trade_when 触发上界"),
    "1": ("OPERATOR_REQUIRED_CONSTANT", "算子位置参数或单位偏移"),
    "5": ("OPERATOR_REQUIRED_CONSTANT", "未声明 slot 的固定 lookback"),
    "10": ("OPERATOR_REQUIRED_CONSTANT", "未声明 slot 的固定 lookback"),
    "20": ("OPERATOR_REQUIRED_CONSTANT", "未声明 slot 的固定 lookback"),
    "60": ("OPERATOR_REQUIRED_CONSTANT", "未声明 slot 的固定 lookback"),
}


def render_numeric_token(expression, token, value, occurrence=0):
    """Replace only the selected occurrence of an explicitly declared token."""
    matches = [
        match for match in NUMBER_TOKEN_RE.finditer(expression)
        if match.group(1) == str(token)
    ]
    index = max(0, int(occurrence))
    if index >= len(matches):
        raise ValueError(f"numeric slot token not found: {token}#{index}")
    match = matches[index]
    return expression[:match.start(1)] + str(value) + expression[match.end(1):]


@dataclass(frozen=True)
class TemplateNumericSlot:
    """研究数值声明；只有声明的数字允许轮换。"""

    name: str
    kind: str = "window"
    default: float = 0.0
    allowed_values: tuple = ()
    economic_role: str = ""
    token: str = ""
    occurrence: int = 0

    def render(self, expression, value):
        return render_numeric_token(
            expression, self.token or str(self.default), value, self.occurrence
        )


@dataclass(frozen=True, init=False)
class AlphaTemplate:
    """One bounded expression skeleton loaded from the catalog."""

    template_id: str
    family: str
    expression: str
    required_slots: tuple
    stage_path: str
    economic_mechanism: str
    direction: str
    direction_transform: object
    expected_horizon: str
    falsification: str
    self_correlation_impact: object
    tags: tuple
    selection_groups: tuple
    selection_order: int
    numeric_slots: tuple
    version: str
    kind: str

    def __init__(self, template_id, family=None, expression=None,
                 required_slots=("p",),
                 stage_path="L0:raw -> L1:cross_sectional -> L2:none",
                 rationale="", economic=False, numeric_slots=(), *,
                 version="1", kind=None, economic_mechanism=None,
                 direction="long", direction_transform="identity",
                 expected_horizon="short-term", falsification="",
                 self_correlation_impact="unknown", tags=(),
                 selection_groups=(), selection_order=1000):
        object.__setattr__(self, "template_id", str(template_id))
        object.__setattr__(self, "family", family or "")
        object.__setattr__(self, "expression", expression or "")
        object.__setattr__(self, "required_slots", tuple(required_slots))
        object.__setattr__(self, "stage_path", stage_path)
        object.__setattr__(self, "economic_mechanism",
                           economic_mechanism if economic_mechanism is not None else rationale)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "direction_transform", direction_transform)
        object.__setattr__(self, "expected_horizon", expected_horizon)
        object.__setattr__(self, "falsification", falsification)
        object.__setattr__(self, "self_correlation_impact", self_correlation_impact)
        object.__setattr__(self, "tags", tuple(tags))
        object.__setattr__(self, "selection_groups", tuple(selection_groups))
        object.__setattr__(self, "selection_order", int(selection_order))
        object.__setattr__(self, "numeric_slots", tuple(numeric_slots))
        object.__setattr__(self, "version", str(version))
        object.__setattr__(self, "kind", kind or ("economic" if economic else "baseline"))

    @property
    def rationale(self):
        """Compatibility name retained for existing proposal consumers."""
        return self.economic_mechanism

    @property
    def economic(self):
        return self.kind == "economic"

    @property
    def operator_count(self):
        return len(analyze_expression(self.expression).operators)

    @property
    def fingerprint(self):
        payload = json.dumps(
            {
                "family": self.family,
                "expression": self.expression,
                "required_slots": self.required_slots,
                "stage_path": self.stage_path,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def catalog_entry(self):
        return {
            "template_id": self.template_id,
            "version": self.version,
            "kind": self.kind,
            "family": self.family,
            "expression": self.expression,
            "required_slots": list(self.required_slots),
            "stage_path": self.stage_path,
            "fingerprint": self.fingerprint,
            "source": "newwqb_builtin",
            "operator_count": self.operator_count,
            "economic": self.economic,
            "economic_mechanism": self.economic_mechanism,
            "direction": self.direction,
            "direction_transform": self.direction_transform,
            "expected_horizon": self.expected_horizon,
            "falsification": self.falsification,
            "self_correlation_impact": self.self_correlation_impact,
            "tags": list(self.tags),
            "selection_groups": list(self.selection_groups),
            "selection_order": self.selection_order,
        }

    @property
    def research_slot_names(self):
        return tuple(slot.name for slot in self.numeric_slots)

    def numeric_slot(self, name):
        return next((slot for slot in self.numeric_slots if slot.name == name), None)

    def render_numeric_variant(self, slot_name, value):
        slot = self.numeric_slot(slot_name)
        if slot is None:
            raise KeyError(f"undeclared numeric slot: {slot_name}")
        if slot.allowed_values and value not in slot.allowed_values:
            raise ValueError(f"{value} is not an allowed value for {slot_name}")
        return slot.render(self.expression, value)

    def numeric_variants(self, *, max_variants=3):
        try:
            cap = max(0, int(max_variants))
        except (TypeError, ValueError):
            cap = 3
        variants = []
        for slot in self.numeric_slots:
            for value in slot.allowed_values or ():
                if value == slot.default:
                    continue
                variants.append({
                    "source_template": self.template_id,
                    "slot": slot.name,
                    "kind": slot.kind,
                    "parent_default_value": slot.default,
                    "candidate_value": value,
                    "expression": slot.render(self.expression, value),
                    "change_count": 1,
                    "economic_role": slot.economic_role,
                    "template_variant_id": f"{self.template_id}@{slot.name}={value}",
                    "semantic_mechanism_family": self.family,
                })
        return variants[:cap]
