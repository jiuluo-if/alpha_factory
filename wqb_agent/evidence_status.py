"""Shared evidence vocabulary without changing legacy ``status`` fields."""

from enum import Enum


class EvidenceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"
    APPROXIMATE = "APPROXIMATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


def evidence_status(value, *, default=EvidenceStatus.UNAVAILABLE):
    """Normalize legacy evidence statuses to the conservative vocabulary."""
    if isinstance(value, dict):
        value = value.get("evidence_status", value.get("status"))
    text = str(value or "").upper()
    if text in {"PASS", "VERIFIED", "AVAILABLE", "STABLE"}:
        return EvidenceStatus.PASS.value
    if text in {"FAIL", "FAILED"}:
        return EvidenceStatus.FAIL.value
    if text in {"APPROXIMATE", "PROXY"}:
        return EvidenceStatus.APPROXIMATE.value
    if text in {"NOT_APPLICABLE", "N/A", "NA"}:
        return EvidenceStatus.NOT_APPLICABLE.value
    return default.value if isinstance(default, EvidenceStatus) else str(default)


def annotate_evidence(payload, *, status=None):
    result = dict(payload or {})
    result["evidence_status"] = evidence_status(status if status is not None else result)
    return result
