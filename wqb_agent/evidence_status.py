"""Shared evidence vocabulary without changing legacy ``status`` fields."""

from enum import Enum


class EvidenceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"
    APPROXIMATE = "APPROXIMATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceQuality(str, Enum):
    VERIFIED = "VERIFIED"
    APPROXIMATE = "APPROXIMATE"
    PROXY = "PROXY"


class Decision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


def evidence_status(value, *, default=EvidenceStatus.UNAVAILABLE):
    """Compatibility-only normalizer; research logic must read ``decision``.

    Availability or verification alone is not a research decision.  The
    explicit ``decision`` field is therefore required before this helper can
    return PASS for mapping-shaped evidence.
    """
    if isinstance(value, dict):
        explicit_decision = value.get("decision")
        if explicit_decision is not None:
            value = explicit_decision
        else:
            availability = str(value.get("availability", "")).upper()
            if availability == Availability.AVAILABLE.value:
                return EvidenceStatus.INCONCLUSIVE.value
            value = value.get("evidence_status", value.get("status"))
    text = str(value or "").upper()
    if text in {"AVAILABLE", "VERIFIED"}:
        return EvidenceStatus.INCONCLUSIVE.value
    if text in {"PASS", "STABLE"}:
        return EvidenceStatus.PASS.value
    if text in {"FAIL", "FAILED"}:
        return EvidenceStatus.FAIL.value
    if text in {"APPROXIMATE", "PROXY"}:
        return EvidenceStatus.APPROXIMATE.value
    if text in {"NOT_APPLICABLE", "N/A", "NA"}:
        return EvidenceStatus.NOT_APPLICABLE.value
    if text == "INCONCLUSIVE":
        return EvidenceStatus.INCONCLUSIVE.value
    return default.value if isinstance(default, EvidenceStatus) else str(default)


def annotate_evidence(payload, *, status=None, availability=None, quality=None,
                      decision=None):
    result = dict(payload or {})
    legacy = result.get("status") or status
    text = str(legacy or "").upper()
    decision_text = str(status or result.get("decision") or result.get("status") or "").upper()
    if availability is None:
        availability = (
            "AVAILABLE" if text in {"AVAILABLE", "VERIFIED", "PASS", "STABLE", "APPROXIMATE", "PROXY", "FAIL"}
            else "NOT_APPLICABLE" if text in {"NOT_APPLICABLE", "N/A", "NA"}
            else "UNAVAILABLE"
        )
    if quality is None:
        quality = (
            "APPROXIMATE" if decision_text == "APPROXIMATE" else
            "PROXY" if decision_text == "PROXY" else
            "VERIFIED" if text in {"VERIFIED", "STABLE", "PASS", "FAIL", "AVAILABLE"}
            else "APPROXIMATE" if text == "APPROXIMATE"
            else "PROXY" if text == "PROXY" else None
        )
    if decision is None:
        decision = decision_text if decision_text in {"PASS", "FAIL"} else "INCONCLUSIVE"
    result["availability"] = str(availability.value if isinstance(availability, Enum) else availability)
    if quality is not None:
        result["quality"] = str(quality.value if isinstance(quality, Enum) else quality)
    result["decision"] = str(decision.value if isinstance(decision, Enum) else decision)
    # Compatibility field: this is the decision, never availability.
    legacy_status = evidence_status(decision)
    if text == "UNAVAILABLE":
        legacy_status = EvidenceStatus.UNAVAILABLE.value
    elif decision_text in {"APPROXIMATE", "PROXY"} or (
        decision_text == "INCONCLUSIVE" and str(quality or "").upper() in {"APPROXIMATE", "PROXY"}
    ):
        legacy_status = str(quality).upper()
    result["evidence_status"] = legacy_status
    return result
