#!/usr/bin/env python3
"""Enhance simulations with health checks and validation roles."""

import os
import re
from collections import defaultdict
from datetime import datetime, timezone

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.artifacts import (
    atomic_write_json_if_changed,
    atomic_write_jsonl_if_changed,
    iter_jsonl_objects,
)
from wqb_agent.metrics import check_health as metrics_check_health, num


def check_health(payload_checks):
    """Compatibility adapter around the production health evaluator."""
    if not payload_checks:
        return None
    return metrics_check_health({"is": {"checks": payload_checks}})


def classify_validation_role(mutation, rationale=""):
    """Classify validation role based on mutation type."""
    if not mutation:
        return "UNKNOWN_ROLE"

    mutation_lower = mutation.lower()
    rationale_lower = (rationale or "").lower()

    # Validation perturbations
    if mutation_lower.startswith("validation-"):
        return "VALIDATION"
    if "perturbation" in mutation_lower or "robustness" in mutation_lower:
        return "VALIDATION"

    # Deepening mutations
    if mutation_lower.startswith("deepening") or "deepen" in mutation_lower:
        return "DEEPENING"
    if any(kw in rationale_lower for kw in ["iterate", "improve", "refine", "optimize"]):
        return "DEEPENING"

    # Discovery mutations
    if mutation_lower in ("baseline", "sign-flip", ""):
        return "DISCOVERY"
    if any(kw in mutation_lower for kw in ["seed", "explore", "initial"]):
        return "DISCOVERY"

    return "UNKNOWN_ROLE"


def detect_noise_trap_pattern(expression, sharpe, fitness):
    """Detect noise trap patterns based on known characteristics."""
    # Known noise trap field families
    noise_fields = [
        "composite_factor_score_derivative",
        "growth_potential_rank_derivative",
        "multi_factor_static_score_derivative",
        "acceleration_rank_derivative",
    ]

    expr_lower = (expression or "").lower()

    # Check if expression uses known noise trap fields
    uses_noise_field = any(field in expr_lower for field in noise_fields)

    # High sharpe + specific field patterns = suspicious
    if uses_noise_field and sharpe and sharpe > 3.5:
        return True

    return False


def enhance_rows(input_path, counters):
    """Enhance and yield one source row at a time."""
    for sim in iter_jsonl_objects(input_path):
        old_role = sim.get("validation_role", "UNKNOWN_ROLE")
        new_role = classify_validation_role(
            sim.get("mutation_type"), sim.get("research_question")
        )
        if new_role != old_role:
            sim["validation_role"] = new_role
            counters["validation_role_updates"] += 1
        counters["role_counts"][sim.get("validation_role", "UNKNOWN_ROLE")] += 1

        if sim.get("status") == "DONE":
            sharpe = num(sim.get("sharpe"))
            fitness = num(sim.get("fitness"))
            expr = sim.get("expression") or ""
            is_suspicious = False
            if (sharpe is not None and sharpe > 3.5) or (fitness is not None and fitness > 8.0):
                is_suspicious = detect_noise_trap_pattern(expr, sharpe, fitness)
                if is_suspicious:
                    counters["noise_traps_detected"] += 1
            if (sharpe is not None and sharpe > 3.0) or (fitness is not None and fitness > 8.0):
                sim["suspicious_high_signal"] = True
                if is_suspicious:
                    sim["suspicious_type"] = "NOISE_TRAP_SUSPECT"
            health = check_health(sim.get("checks") or [])
            if health and health != sim.get("health"):
                sim["health"] = health
                counters["health_checks_added"] += 1

        if sim.get("suspicious_high_signal"):
            counters["suspicious_counts"][sim.get("suspicious_type", "HIGH_SIGNAL")] += 1
        counters["enhanced_count"] += 1
        yield sim


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(base_dir) == "scripts":
        base_dir = os.path.dirname(base_dir)
    data_dir = os.path.join(base_dir, "research_data")
    print("Streaming simulations...")
    input_path = os.path.join(data_dir, "simulations.jsonl")
    counters = {
        "enhanced_count": 0,
        "validation_role_updates": 0,
        "health_checks_added": 0,
        "noise_traps_detected": 0,
        "role_counts": defaultdict(int),
        "suspicious_counts": defaultdict(int),
    }
    output_path = os.path.join(data_dir, "simulations_enhanced.jsonl")
    atomic_write_jsonl_if_changed(output_path, enhance_rows(input_path, counters))

    print(f"\nEnhancement results:")
    print(f"  Simulations processed: {counters['enhanced_count']}")
    print(f"  Validation role updates: {counters['validation_role_updates']}")
    print(f"  Health checks added: {counters['health_checks_added']}")
    print(f"  Noise traps detected: {counters['noise_traps_detected']}")
    print(f"\nEnhanced simulations saved to: {output_path}")

    summary = {
        "generated_at": datetime.fromtimestamp(
            os.path.getmtime(input_path),
            tz=timezone.utc,
        ).isoformat(),
        "total_simulations": counters["enhanced_count"],
        "validation_role_breakdown": dict(counters["role_counts"]),
        "suspicious_signal_breakdown": dict(counters["suspicious_counts"]),
        "noise_traps_detected": counters["noise_traps_detected"],
    }

    summary_path = os.path.join(data_dir, "enhancement_summary.json")
    atomic_write_json_if_changed(summary_path, summary, ignored_keys=("generated_at",))
    print(f"Summary saved to: {summary_path}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
