"""Explicit policy for using behavioral incremental-value evidence."""

from __future__ import annotations

from dataclasses import dataclass

VALID_MODES = frozenset({"advisory", "required_when_available", "required"})


@dataclass(frozen=True)
class IncrementalValuePolicy:
    mode: str = "required_when_available"
    max_abs_correlation: float = 0.7
    min_overlap: int = 60

    def __post_init__(self):
        mode = str(self.mode).lower()
        if mode not in VALID_MODES:
            raise ValueError("incremental_value.mode 必须是 advisory、required_when_available 或 required")
        if float(self.max_abs_correlation) < 0 or float(self.max_abs_correlation) > 1:
            raise ValueError("incremental_value.max_abs_correlation 必须在 [0, 1] 内")
        if int(self.min_overlap) < 1:
            raise ValueError("incremental_value.min_overlap 必须为正整数")


def incremental_gate(evidence, mode):
    """Return eligibility and explicit reasons without hiding UNKNOWN states."""
    mode = str(mode or "required_when_available").lower()
    if mode not in VALID_MODES:
        raise ValueError("未知 incremental value mode")
    evidence = evidence if isinstance(evidence, dict) else {}
    availability = str(evidence.get("availability") or "UNAVAILABLE").upper()
    decision = str(evidence.get("decision") or "INCONCLUSIVE").upper()
    reasons = []
    if availability != "AVAILABLE":
        reasons.append(f"incremental_value:{availability}")
    elif decision != "PASS":
        reasons.append(f"incremental_value:{decision}")
    if mode == "advisory":
        return {"eligible": True, "status": decision, "reasons": reasons, "mode": mode}
    if availability != "AVAILABLE":
        eligible = mode == "required_when_available"
    else:
        eligible = decision == "PASS"
    return {"eligible": eligible, "status": decision, "reasons": reasons, "mode": mode}
