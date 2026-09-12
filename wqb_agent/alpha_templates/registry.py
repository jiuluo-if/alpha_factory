"""Catalog-backed template registry and numeric audit."""

from .loader import load_builtin_templates
from .model import FIXED_NUMERICS, NUMBER_TOKEN_RE, AlphaTemplate

TEMPLATE_FIXED_NUMERICS = FIXED_NUMERICS


def template_numeric_audit(templates=None):
    source = tuple(templates) if templates is not None else load_builtin_templates()
    rows = []
    problems = []
    for template in source:
        declared = {}
        for slot in template.numeric_slots:
            declared[(str(slot.token or slot.default), int(slot.occurrence))] = slot
        seen = {}
        for match in NUMBER_TOKEN_RE.finditer(template.expression):
            token = match.group(1)
            index = seen.get(token, 0)
            seen[token] = index + 1
            slot = declared.pop((token, index), None)
            if slot is not None:
                allowed = tuple(slot.allowed_values or ())
                if not allowed:
                    problems.append(f"{template.template_id}: slot {slot.name} missing allowed_values")
                rows.append({"template_id": template.template_id, "token": token,
                             "occurrence": index, "class": "RESEARCH_SLOT",
                             "name": slot.name, "allowed_values": allowed})
                continue
            entry = TEMPLATE_FIXED_NUMERICS.get(token)
            if entry is None:
                problems.append(f"{template.template_id}: unclassified numeric literal {token}#{index}")
                rows.append({"template_id": template.template_id, "token": token,
                             "occurrence": index, "class": "UNCLASSIFIED",
                             "name": None, "allowed_values": ()})
            else:
                rows.append({"template_id": template.template_id, "token": token,
                             "occurrence": index, "class": entry[0], "name": None,
                             "allowed_values": (), "role": entry[1]})
        for slot in declared.values():
            problems.append(f"{template.template_id}: slot {slot.name} not present in expression")
    return {"ok": not problems, "problems": problems, "rows": rows,
            "rotatable": [row for row in rows if row["class"] == "RESEARCH_SLOT"]}


class AlphaTemplateRegistry:
    """Immutable-by-default view over the validated catalog."""

    def __init__(self, templates=None):
        self._templates = {}
        source = load_builtin_templates() if templates is None else tuple(templates)
        for template in source:
            self.register(template)
        audit = template_numeric_audit(tuple(self._templates.values()))
        if not audit["ok"]:
            raise ValueError("template numeric audit failed: " + "; ".join(audit["problems"]))

    def register(self, template):
        if not isinstance(template, AlphaTemplate):
            raise TypeError("template must be AlphaTemplate")
        if template.template_id in self._templates:
            raise ValueError(f"duplicate template_id: {template.template_id}")
        if template.kind == "economic" and not 3 <= template.operator_count <= 8:
            raise ValueError(f"economic template {template.template_id} operator count invalid")
        self._templates[template.template_id] = template

    def get(self, template_id):
        return self._templates.get(template_id)

    def catalog(self):
        return [self._templates[key].catalog_entry() for key in sorted(self._templates)]

    def economic_templates(self):
        return [self._templates[key] for key in sorted(self._templates)
                if self._templates[key].economic]

    def select(self, hypothesis=None):
        if not isinstance(hypothesis, dict):
            return []
        explicit = hypothesis.get("template_ids") or []
        if isinstance(explicit, str):
            explicit = [explicit]
        if not isinstance(explicit, (list, tuple)) or any(
                not isinstance(item, str) or not item.strip() for item in explicit):
            return []
        selected = [self.get(item) for item in explicit]
        if explicit and any(item is None for item in selected):
            return []
        if selected:
            return selected
        if explicit:
            return []
        ref = hypothesis.get("template_ref") or {}
        if not isinstance(ref, dict):
            return []
        family = hypothesis.get("template_family") or ref.get("family")
        if not family:
            family = ref.get("template_skeleton_family")
        if ref and not family and (ref.get("catalog_id") or ref.get("skeleton_fingerprint")):
            return []
        if family:
            return sorted(
                (t for t in self._templates.values() if t.family == family),
                key=lambda item: item.template_id,
            )
        requested_group = hypothesis.get("selection_group")
        if requested_group:
            matching = [t for t in self._templates.values()
                        if requested_group in t.selection_groups]
            if requested_group == "factory_default":
                return matching
            return sorted(
                matching,
                key=(
                    (lambda item: (item.selection_order, item.template_id))
                    if requested_group == "candidate_scratch"
                    else (lambda item: item.template_id)
                ),
            )
        tags = {str(tag).lower() for tag in hypothesis.get("tags", [])
                if isinstance(hypothesis.get("tags"), (list, tuple, set))}
        direction = str(hypothesis.get("direction") or "").lower()
        if direction == "reversal" or tags & {"reversal", "contrarian"}:
            group = "reversal"
        elif tags & {"relationship", "pair", "spread", "corr"}:
            group = "relationship"
        elif tags & {"momentum", "trend", "continuation"}:
            group = "momentum"
        else:
            group = "default"
        return sorted(
            (t for t in self._templates.values() if group in t.selection_groups),
            key=lambda item: item.template_id,
        )


_BUILTIN_TEMPLATES = load_builtin_templates()
DEFAULT_TEMPLATES = tuple(item for item in _BUILTIN_TEMPLATES if item.kind == "baseline")
ECONOMIC_TEMPLATES = tuple(item for item in _BUILTIN_TEMPLATES if item.kind == "economic")
