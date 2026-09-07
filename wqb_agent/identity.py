"""Stable identities for generated candidates and submitted proposals."""

from __future__ import annotations

import hashlib
import json

from .expression import canonical_expression


def _field_value(value):
    if isinstance(value, dict):
        return value.get("id") or value.get("name") or ""
    return value


def candidate_identity(candidate, *, round_no=None):
    """Return a deterministic identity for a candidate before preflight.

    Candidate identity includes settings and design metadata so the same
    expression under different authorised settings remains a new candidate.
    It is intentionally independent of UUIDs and proposal/submission IDs.
    """
    if isinstance(candidate, dict):
        expression = candidate.get("expression", "")
        settings = candidate.get("settings") or {}
        fields = candidate.get("fields_used") or candidate.get("fields") or []
        datasets = candidate.get("datasets") or []
        family = candidate.get("template_family") or candidate.get("mechanism_family") or ""
        template = candidate.get("template_id") or candidate.get("template_ref") or ""
        actual_round = candidate.get("round", round_no)
    else:
        expression = str(candidate or "")
        settings, fields, datasets, family, template = {}, [], [], "", ""
        actual_round = round_no
    payload = {
        "version": 1,
        "round": actual_round,
        "expression": canonical_expression(str(expression or "")),
        "settings": settings,
        "fields": sorted(str(_field_value(field)) for field in fields if _field_value(field) is not None),
        "datasets": sorted(str(_field_value(dataset)) for dataset in datasets if _field_value(dataset) is not None),
        "template_family": str(family),
        "template_id": str(template),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "c-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]

