#!/usr/bin/env python3
"""
Schema Enhancement - Add parent_id and validation child relationships.

This script enhances the simulation records with:
1. Explicit parent_id for each experiment (based on mutation patterns)
2. Validation child relationships (parent → children)
3. Lineage depth calculation
4. Mutation dimension classification
"""

import os
import re
from collections import defaultdict
from datetime import datetime, timezone

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.artifacts import (
    atomic_write_json_if_changed,
    atomic_write_jsonl_if_changed,
    atomic_write_text_if_changed,
    iter_jsonl_objects,
)


def parse_expression_structure(expression):
    """Parse expression to extract structure components."""
    if not expression:
        return {}

    structure = {
        "operators": [],
        "fields": [],
        "windows": [],
        "weights": [],
        "is_composite": False,
    }

    # Extract operators
    operator_patterns = [
        r'\b(rank|zscore|ts_mean|ts_rank|ts_zscore|ts_av_diff|ts_decay_linear|group_neutralize|ts_corr|ts_covariance|if_else|vec_avg|vec_sum)\b',
    ]
    for pattern in operator_patterns:
        matches = re.findall(pattern, expression.lower())
        structure["operators"].extend(matches)

    # Extract windows (numbers in ts_* functions)
    window_matches = re.findall(r'ts_\w+\([^,]+,\s*(\d+)\)', expression)
    structure["windows"].extend([int(w) for w in window_matches])

    # Extract weights (0.X * patterns)
    weight_matches = re.findall(r'(\d+\.\d+)\s*\*', expression)
    structure["weights"].extend([float(w) for w in weight_matches])

    # Check if composite (multiple legs)
    if len(structure["weights"]) > 1 or expression.count('+') > 1:
        structure["is_composite"] = True

    return structure


def classify_mutation_type(expression, parent_expr, hypothesis_id):
    """Classify mutation type based on differences from parent."""
    if not parent_expr:
        return "baseline"

    # Extract structures
    child_struct = parse_expression_structure(expression)
    parent_struct = parse_expression_structure(parent_expr)

    # Compare operators
    child_ops = set(child_struct["operators"])
    parent_ops = set(parent_struct["operators"])
    new_ops = child_ops - parent_ops
    removed_ops = parent_ops - child_ops

    # Compare windows
    child_windows = sorted(set(child_struct["windows"]))
    parent_windows = sorted(set(parent_struct["windows"]))
    window_changed = child_windows != parent_windows

    # Compare weights
    child_weights = sorted(child_struct["weights"])
    parent_weights = sorted(parent_struct["weights"])
    weight_changed = child_weights != parent_weights

    # Extract fields
    child_fields = set(re.findall(r'[a-z_][a-z0-9_]*(?=[,\)\+\-\*/\s])', expression.lower()))
    parent_fields = set(re.findall(r'[a-z_][a-z0-9_]*(?=[,\)\+\-\*/\s])', parent_expr.lower()))
    field_swapped = child_fields != parent_fields

    # Classify mutation
    if new_ops:
        return f"operator-{list(new_ops)[0]}"
    elif window_changed:
        return "window-tweak"
    elif weight_changed:
        return "weight-tweak"
    elif field_swapped:
        return "field-swap"
    elif expression.startswith("-") and not parent_expr.startswith("-"):
        return "sign-flip"
    elif parent_expr.startswith("-") and not expression.startswith("-"):
        return "sign-flip"
    else:
        return "structural-modification"


def find_parent_sim(sim, all_sims, hypothesis_id):
    """Find the parent simulation for a given simulation."""
    exp_id = sim.get("experiment_id")
    expr = sim.get("expression") or ""
    round_no = sim.get("round") or 0
    created_at = sim.get("created_at") or ""

    # Find same-hypothesis simulations created before this one
    candidates = []
    for other in all_sims:
        if other.get("experiment_id") == exp_id:
            continue
        if other.get("hypothesis_id") != hypothesis_id:
            continue
        if other.get("status") != "DONE":
            continue

        other_created = other.get("created_at") or ""
        if other_created >= created_at:
            continue

        # Check similarity (heuristic)
        other_expr = other.get("expression") or ""
        if not other_expr:
            continue

        # Prefer experiments with similar structure
        candidates.append((other, other_created))

    if not candidates:
        return None

    # Sort by creation time (most recent first)
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def enhanced_rows(path, parent_map, child_map, lineage_depth):
    """Attach computed lineage metadata while streaming the source."""
    for sim in iter_jsonl_objects(path):
        exp_id = sim.get("experiment_id")
        sim["parent_id"] = parent_map.get(exp_id)
        sim["validation_children"] = child_map.get(exp_id, [])
        sim["lineage_depth"] = lineage_depth.get(exp_id, 0)
        yield sim


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(base_dir) == "scripts":
        base_dir = os.path.dirname(base_dir)
    data_dir = os.path.join(base_dir, "research_data")

    print("Streaming validated simulations...")
    input_path = os.path.join(data_dir, "simulations_validated.jsonl")

    # Group by hypothesis
    by_hypothesis = defaultdict(list)
    total_simulations = 0
    for sim in iter_jsonl_objects(input_path):
        total_simulations += 1
        hyp = sim.get("hypothesis_id")
        if hyp:
            by_hypothesis[hyp].append(sim)

    print(f"Grouped into {len(by_hypothesis)} hypotheses")

    # Enhance each simulation
    parent_map = {}
    child_map = defaultdict(list)
    lineage_depth = {}
    hyp_depths = {}

    for hyp_id, hyp_sims in by_hypothesis.items():
        # Sort by creation time
        hyp_sims_sorted = sorted(hyp_sims, key=lambda x: x.get("created_at") or 0)

        for i, sim in enumerate(hyp_sims_sorted):
            exp_id = sim.get("experiment_id")

            # Find parent
            if i > 0:
                parent_sim = hyp_sims_sorted[i - 1]
                parent_id = parent_sim.get("experiment_id")
                parent_map[exp_id] = parent_id
                child_map[parent_id].append(exp_id)

                # Classify mutation
                mutation_type = classify_mutation_type(
                    sim.get("expression"),
                    parent_sim.get("expression"),
                    hyp_id
                )
                sim["mutation_type_enhanced"] = mutation_type
            else:
                parent_map[exp_id] = None
                sim["mutation_type_enhanced"] = "baseline"

            # Calculate lineage depth
            depth = 0
            current_id = exp_id
            visited = set()
            while current_id and current_id in parent_map and parent_map[current_id] and current_id not in visited:
                visited.add(current_id)
                current_id = parent_map[current_id]
                depth += 1

            lineage_depth[exp_id] = depth
            sim["lineage_depth"] = depth
        hyp_depths[hyp_id] = max(
            (lineage_depth.get(s.get("experiment_id"), 0) for s in hyp_sims),
            default=0,
        )

    print(f"\nEnhancement results:")
    print(f"  Parent mappings: {len(parent_map)}")
    print(f"  Child mappings: {len(child_map)}")
    average_depth = sum(lineage_depth.values()) / len(lineage_depth) if lineage_depth else 0
    print(f"  Average lineage depth: {average_depth:.2f}")

    # Save enhanced simulations without retaining a second full source list.
    output_path = os.path.join(data_dir, "simulations_final.jsonl")
    atomic_write_jsonl_if_changed(
        output_path, enhanced_rows(input_path, parent_map, child_map, lineage_depth)
    )
    print(f"\nFinal simulations saved to: {output_path}")

    # Generate lineage report
    lineage_stats = {
        "total_simulations": total_simulations,
        "with_parent": sum(1 for v in parent_map.values() if v),
        "root_simulations": sum(1 for v in parent_map.values() if not v),
        "max_depth": max(lineage_depth.values()) if lineage_depth else 0,
        "avg_depth": average_depth,
        "by_depth": defaultdict(int),
    }

    for depth in lineage_depth.values():
        lineage_stats["by_depth"][str(depth)] += 1

    # Convert defaultdict to dict for JSON serialization
    lineage_stats["by_depth"] = dict(lineage_stats["by_depth"])

    stats_path = os.path.join(data_dir, "lineage_statistics.json")
    atomic_write_json_if_changed(stats_path, lineage_stats)
    print(f"Lineage statistics saved to: {stats_path}")

    # Generate markdown summary
    lines = [
        "# Schema Enhancement Report",
        "",
        f"**Input snapshot**: {datetime.fromtimestamp(os.path.getmtime(os.path.join(data_dir, 'simulations_validated.jsonl')), tz=timezone.utc).isoformat()}",
        "",
        "## Lineage Statistics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Simulations | {lineage_stats['total_simulations']} |",
        f"| With Parent | {lineage_stats['with_parent']} |",
        f"| Root Simulations | {lineage_stats['root_simulations']} |",
        f"| Max Lineage Depth | {lineage_stats['max_depth']} |",
        f"| Average Lineage Depth | {lineage_stats['avg_depth']:.2f} |",
        "",
        "## Depth Distribution",
        "",
        "| Depth | Count |",
        "|-------|-------|",
    ]

    for depth in sorted(lineage_stats["by_depth"].keys(), key=int):
        lines.append(f"| {depth} | {lineage_stats['by_depth'][depth]} |")

    lines.extend([
        "",
        "## Top Lineages by Depth",
        "",
    ])

    top_lineages = sorted(hyp_depths.items(), key=lambda x: x[1], reverse=True)[:10]
    for i, (hyp_id, depth) in enumerate(top_lineages, 1):
        lines.append(f"{i}. **{hyp_id}**: depth={depth}")

    summary_path = os.path.join(data_dir, "SCHEMA_ENHANCEMENT_REPORT.md")
    atomic_write_text_if_changed(summary_path, "\n".join(lines))
    print(f"Schema enhancement report saved to: {summary_path}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
