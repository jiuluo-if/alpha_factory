"""Fail-closed TOML loading for the built-in template resource."""

import importlib.resources as resources
import io
import tomllib

from .model import FIXED_NUMERICS, NUMBER_TOKEN_RE, AlphaTemplate, TemplateNumericSlot

_KINDS = {"baseline", "economic"}
_DIRECTIONS = {"long", "reversal"}
_SLOTS = {"p", "s", "t", "data_field"}
_GROUPS = {"default", "factory_default", "reversal", "relationship", "momentum", "candidate_scratch", "economic", "vector"}
_REQUIRED = (
    "id", "version", "kind", "family", "expression", "required_slots",
    "stage_path", "economic_mechanism", "direction", "direction_transform",
    "expected_horizon", "falsification", "self_correlation_impact",
    "selection_groups",
)


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"template {name}: {name} must be a non-empty string")
    return value.strip()


def _slot(raw, template_id):
    if not isinstance(raw, dict):
        raise ValueError(f"{template_id}: numeric slot must be a table")
    name = _text(raw.get("name"), "numeric slot name")
    allowed = raw.get("allowed_values")
    if not isinstance(allowed, list) or not allowed:
        raise ValueError(f"{template_id}: slot {name} missing allowed_values")
    token = raw.get("token")
    token = str(token) if token is not None else str(raw.get("default"))
    return TemplateNumericSlot(
        name=name,
        kind=_text(raw.get("kind", "window"), "numeric slot kind"),
        default=raw.get("default"),
        allowed_values=tuple(allowed),
        economic_role=_text(raw.get("economic_role"), "economic_role"),
        token=token,
        occurrence=raw.get("occurrence", 0),
    )


def _parse(document):
    if not isinstance(document, dict) or not isinstance(document.get("templates"), list):
        raise ValueError("catalog must contain [[templates]] entries")
    templates = []
    seen = set()
    for raw in document["templates"]:
        if not isinstance(raw, dict):
            raise ValueError("template entry must be a table")
        missing = [key for key in _REQUIRED if key not in raw]
        if missing:
            raise ValueError(f"template missing required keys: {', '.join(missing)}")
        template_id = _text(raw["id"], "id")
        if template_id in seen:
            raise ValueError(f"duplicate template id: {template_id}")
        seen.add(template_id)
        kind = _text(raw["kind"], "kind")
        if kind not in _KINDS:
            raise ValueError(f"{template_id}: unknown kind {kind}")
        required_slots = raw["required_slots"]
        if (not isinstance(required_slots, list) or not required_slots
                or any(slot not in _SLOTS for slot in required_slots)
                or len(set(required_slots)) != len(required_slots)):
            raise ValueError(f"{template_id}: invalid required_slots")
        groups = raw["selection_groups"]
        if (not isinstance(groups, list) or not groups or
                any(group not in _GROUPS for group in groups)):
            raise ValueError(f"{template_id}: invalid selection_groups")
        direction = _text(raw["direction"], "direction")
        if direction not in _DIRECTIONS:
            raise ValueError(f"{template_id}: invalid direction {direction}")
        numeric_slots = tuple(_slot(item, template_id) for item in raw.get("numeric_slots", []))
        if len({slot.name for slot in numeric_slots}) != len(numeric_slots):
            raise ValueError(f"{template_id}: duplicate numeric slot name")
        templates.append(AlphaTemplate(
            template_id=template_id,
            version=_text(raw["version"], "version"),
            kind=kind,
            family=_text(raw["family"], "family"),
            expression=_text(raw["expression"], "expression"),
            required_slots=tuple(required_slots),
            stage_path=_text(raw["stage_path"], "stage_path"),
            economic_mechanism=_text(raw["economic_mechanism"], "economic_mechanism"),
            direction=direction,
            direction_transform=raw["direction_transform"],
            expected_horizon=_text(raw["expected_horizon"], "expected_horizon"),
            falsification=_text(raw["falsification"], "falsification"),
            self_correlation_impact=raw["self_correlation_impact"],
            tags=tuple(str(tag) for tag in raw.get("tags", [])),
            selection_groups=tuple(groups),
            selection_order=raw.get("selection_order", 1000),
            numeric_slots=numeric_slots,
        ))
    result = tuple(templates)
    for template in result:
        declared = {
            (str(slot.token or slot.default), int(slot.occurrence)): slot
            for slot in template.numeric_slots
        }
        seen = {}
        for match in NUMBER_TOKEN_RE.finditer(template.expression):
            token = match.group(1)
            occurrence = seen.get(token, 0)
            seen[token] = occurrence + 1
            slot = declared.pop((token, occurrence), None)
            if slot is None and token not in FIXED_NUMERICS:
                raise ValueError(
                    f"{template.template_id}: unclassified numeric literal {token}#{occurrence}"
                )
        if declared:
            missing = next(iter(declared.values()))
            raise ValueError(
                f"{template.template_id}: numeric slot {missing.name} not present in expression"
            )
    return result


def load_templates(source):
    """Load templates from a binary/text stream or TOML path."""
    if hasattr(source, "read"):
        content = source.read()
        if isinstance(content, str):
            content = content.encode("utf-8")
    else:
        with open(source, "rb") as handle:
            content = handle.read()
    return _parse(tomllib.load(io.BytesIO(content)))


def load_builtin_templates():
    resource = resources.files("wqb_agent.alpha_templates").joinpath(
        "catalog", "builtin.toml"
    )
    with resource.open("rb") as handle:
        return _parse(tomllib.load(handle))
