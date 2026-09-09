#!/usr/bin/env python3
"""
Data Integrity Validator - Cross-reference memory with simulation evidence.

This script checks:
1. Memory lessons can be traced to real simulations
2. Validation evidence has proper parents
3. HIGH-SIGNAL items are marked but not validated
4. Duplicate simulations are flagged
"""

import json
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.artifacts import atomic_write_json_if_changed, iter_jsonl_objects
from wqb_agent.expression import canonical_expression
from wqb_agent.metrics import num

iter_jsonl = iter_jsonl_objects


def load_jsonl(path):
    """Compatibility list loader for callers that explicitly need a list."""
    return list(iter_jsonl(path))


def load_json_object(path):
    """Load an optional state object without turning audit into a crash loop."""
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def round_key(value):
    """Compare numeric and legacy string round values consistently."""
    number = num(value)
    if number is None:
        return value if isinstance(value, (str, int, float, bool)) else None
    return int(number) if number.is_integer() else number


def _prefix(value, limit):
    """Keep malformed optional memory text from aborting unattended audits."""
    return str(value or "")[:limit]


def duplicate_groups(records, field, canonicalize=False):
    """Return duplicate record ids with the production identity semantics."""
    groups = defaultdict(list)
    for record in records:
        value = record.get(field)
        if not isinstance(value, (str, int, float, bool)) or not str(value).strip():
            continue
        value = str(value)
        if value:
            key = canonical_expression(value) if canonicalize else value
            groups[key].append(record.get("experiment_id"))
    return {key: ids for key, ids in groups.items() if len(ids) > 1}


def main():
    # Find project root by looking for .wqb_state directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(base_dir) == "scripts":
        base_dir = os.path.dirname(base_dir)
    state_dir = os.path.join(base_dir, ".wqb_state")
    output_dir = os.path.join(base_dir, "research_data")
    input_paths = [
        os.path.join(output_dir, name)
        for name in ("simulations.jsonl", "experiments.jsonl", "lineages.jsonl")
    ] + [os.path.join(state_dir, name) for name in ("experience.json", "garbage.json")]

    # Stream derived JSONL files.  The compatibility ``load_jsonl`` function
    # remains available, but the unattended audit itself must not materialize
    # the full simulation/experiment/lineage ledgers.
    print("Loading data...")
    simulations_path = os.path.join(output_dir, "simulations.jsonl")
    experiments_path = os.path.join(output_dir, "experiments.jsonl")
    lineages_path = os.path.join(output_dir, "lineages.jsonl")
    experience = load_json_object(os.path.join(state_dir, "experience.json"))

    simulation_count = 0
    simulation_rounds = set()
    validated_parent_ids = set()
    expression_counts = defaultdict(int)
    alpha_counts = defaultdict(int)
    hypothesis_ids = set()
    for sim in iter_jsonl(simulations_path):
        simulation_count += 1
        round_value = round_key(sim.get("round"))
        if round_value is not None:
            simulation_rounds.add(round_value)
        parent_id = sim.get("parent_id")
        if isinstance(parent_id, (str, int, float, bool)) and str(parent_id).strip():
            validated_parent_ids.add(str(parent_id))
        expression = sim.get("expression")
        if isinstance(expression, (str, int)) and str(expression).strip():
            expression_counts[canonical_expression(str(expression))] += 1
        alpha_id = sim.get("alpha_id")
        if isinstance(alpha_id, (str, int, float, bool)) and str(alpha_id).strip():
            alpha_counts[str(alpha_id)] += 1
        hypothesis_id = sim.get("hypothesis_id")
        if isinstance(hypothesis_id, (str, int, float, bool)) and str(hypothesis_id).strip():
            hypothesis_ids.add(str(hypothesis_id))

    experiment_count = sum(1 for _ in iter_jsonl(experiments_path))
    lineage_count = sum(1 for _ in iter_jsonl(lineages_path))

    # ─────────────────────────────────────────────────────────
    # 1. Memory → Simulation Traceability
    # ─────────────────────────────────────────────────────────
    print("\n[1] Checking memory traceability...")

    memory_issues = []

    # Check lessons
    for lesson in experience.get("lessons", []) or []:
        if not isinstance(lesson, dict):
            continue
        source_round = lesson.get("source_round")
        if not source_round:
            memory_issues.append({
                "type": "lesson_missing_source",
                "id": lesson.get("id"),
                "claim": _prefix(lesson.get("claim"), 80),
            })
            continue

        if round_key(source_round) not in simulation_rounds:
            memory_issues.append({
                "type": "lesson_no_simulation",
                "id": lesson.get("id"),
                "round": source_round,
                "claim": _prefix(lesson.get("claim"), 80),
            })

    # Check avoid entries
    for avoid_item in experience.get("avoid", []) or []:
        if not isinstance(avoid_item, dict):
            continue
        source_round = avoid_item.get("source_round")
        if source_round and round_key(source_round) not in simulation_rounds:
            memory_issues.append({
                "type": "avoid_no_simulation",
                "id": avoid_item.get("id"),
                "round": source_round,
                "direction": _prefix(avoid_item.get("direction"), 60),
            })

    print(f"       Memory traceability issues: {len(memory_issues)}")

    # ─────────────────────────────────────────────────────────
    # 2. Validation Evidence Parent Check
    # ─────────────────────────────────────────────────────────
    print("\n[2] Checking validation evidence parents...")

    validation_count = 0
    validation_without_parent_count = 0
    validation_without_parent = []
    for vsim in iter_jsonl(simulations_path):
        if vsim.get("validation_role") != "VALIDATION":
            continue
        validation_count += 1
        parent_id = vsim.get("parent_id")
        if not parent_id:
            validation_without_parent_count += 1
            if len(validation_without_parent) < 5:
                validation_without_parent.append({
                    "id": vsim.get("experiment_id"),
                    "mutation": vsim.get("mutation_type"),
                    "expression": _prefix(vsim.get("expression"), 60),
                })

    print(f"       Validation simulations: {validation_count}")
    print(f"       Without parent: {validation_without_parent_count}")

    # ─────────────────────────────────────────────────────────
    # 3. High Signal Audit
    # ─────────────────────────────────────────────────────────
    print("\n[3] Auditing high-signal items...")

    high_signal_count = 0
    unvalidated_count = 0
    unvalidated = []
    for sim in iter_jsonl(simulations_path):
        if sim.get("status") == "DONE":
            sharpe = sim.get("sharpe")
            fitness = sim.get("fitness")
            sharpe_value = num(sharpe)
            fitness_value = num(fitness)
            if ((sharpe_value is not None and sharpe_value > 3.0)
                    or (fitness_value is not None and fitness_value > 8.0)):
                # Check if validated
                has_validation = sim.get("experiment_id") in validated_parent_ids
                high_signal_count += 1
                if not has_validation:
                    unvalidated_count += 1
                    if len(unvalidated) < 10:
                        unvalidated.append({
                            "id": sim.get("experiment_id"),
                            "sharpe": sharpe,
                            "fitness": fitness,
                            "validated": has_validation,
                            "health": sim.get("health"),
                        })

    print(f"       High signal items (S>3 or F>8): {high_signal_count}")
    print(f"       Unvalidated: {unvalidated_count}")

    # ─────────────────────────────────────────────────────────
    # 4. Duplicate Detection
    # ─────────────────────────────────────────────────────────
    print("\n[4] Detecting duplicates...")

    duplicate_expressions = {
        key: count for key, count in expression_counts.items() if count > 1
    }
    print(f"       Duplicate expressions: {len(duplicate_expressions)}")

    duplicate_alphas = {
        key: count for key, count in alpha_counts.items() if count > 1
    }
    print(f"       Duplicate alpha_ids: {len(duplicate_alphas)}")

    # ─────────────────────────────────────────────────────────
    # 5. ORPHAN Check
    # ─────────────────────────────────────────────────────────
    print("\n[5] Checking orphans...")

    orphan_count = sum(
        1 for sim in iter_jsonl(simulations_path) if not sim.get("hypothesis_id")
    )
    print(f"       Simulations without hypothesis: {orphan_count}")

    # ─────────────────────────────────────────────────────────
    # 6. Missing Metrics
    # ─────────────────────────────────────────────────────────
    print("\n[6] Checking missing metrics...")

    missing_sharpe_count = 0
    missing_fitness_count = 0
    for sim in iter_jsonl(simulations_path):
        if sim.get("status") != "DONE":
            continue
        missing_sharpe_count += sim.get("sharpe") is None
        missing_fitness_count += sim.get("fitness") is None
    print(f"       DONE with missing Sharpe: {missing_sharpe_count}")
    print(f"       DONE with missing Fitness: {missing_fitness_count}")

    # ─────────────────────────────────────────────────────────
    # 7. Lineage Completeness
    # ─────────────────────────────────────────────────────────
    print("\n[7] Checking lineage completeness...")

    hyps_in_lineages = {
        str(lineage.get("root_hypothesis")) for lineage in iter_jsonl(lineages_path)
        if isinstance(lineage.get("root_hypothesis"), (str, int, float, bool))
        and str(lineage.get("root_hypothesis")).strip()
    }
    hyps_in_sims = hypothesis_ids

    hyps_without_lineage = hyps_in_sims - hyps_in_lineages
    print(f"       Hypotheses without lineage: {len(hyps_without_lineage)}")

    # ─────────────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("DATA INTEGRITY SUMMARY")
    print("=" * 60)
    print(f"Total Simulations: {simulation_count}")
    print(f"Total Experiments: {experiment_count}")
    print(f"Total Lineages: {lineage_count}")
    print(f"Memory Issues: {len(memory_issues)}")
    print(f"Validation Without Parent: {validation_without_parent_count}")
    print(f"High Signal (Unvalidated): {unvalidated_count}")
    print(f"Duplicate Expressions: {len(duplicate_expressions)}")
    print(f"Orphan Simulations: {orphan_count}")
    print(f"Missing Metrics: {missing_sharpe_count}")
    print(f"Hypotheses Without Lineage: {len(hyps_without_lineage)}")
    print("=" * 60)

    # Write integrity report
    report = {
        "generated_at": datetime.fromtimestamp(
            max((Path(path).stat().st_mtime for path in input_paths if Path(path).exists()),
                default=0),
            tz=UTC,
        ).isoformat() if any(Path(path).exists() for path in input_paths) else "unknown",
        "integrity_checks": {
            "memory_traceability": {
                "total_issues": len(memory_issues),
                "issues": memory_issues[:20],  # First 20
            },
            "validation_parents": {
                "total_validation": validation_count,
                "without_parent": validation_without_parent_count,
                "examples": validation_without_parent,
            },
            "high_signal": {
                "total": high_signal_count,
                "unvalidated": unvalidated_count,
                "examples": unvalidated,
            },
            "duplicates": {
                "by_expression": len(duplicate_expressions),
                "by_alpha_id": len(duplicate_alphas),
            },
            "orphans": {
                "no_hypothesis": orphan_count,
            },
            "missing_metrics": {
                "no_sharpe": missing_sharpe_count,
                "no_fitness": missing_fitness_count,
            },
            "lineage_completeness": {
                "hypotheses_without_lineage": len(hyps_without_lineage),
            },
        },
    }

    report_path = os.path.join(output_dir, "integrity_report.json")
    atomic_write_json_if_changed(report_path, report, ignored_keys=("generated_at",))
    print(f"\nIntegrity report written to: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
