#!/usr/bin/env python3
"""Analyze high-signal simulations and generate audit report."""

import os
from collections import defaultdict
from datetime import datetime, timezone

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.artifacts import atomic_write_json_if_changed, iter_jsonl_objects
from wqb_agent.expression import canonical_expression
from wqb_agent.metrics import num


TOP_AUDIT_LIMIT = 50


iter_jsonl = iter_jsonl_objects


def _metric(value):
    """Return a printable numeric metric without masking missing data."""
    value = num(value)
    return f"{value:.2f}" if value is not None else "NA"


def _display(value):
    return str(value or "")


def _compact_record(sim):
    """Keep only fields needed by the bounded audit output."""
    health = sim.get("health") if isinstance(sim.get("health"), dict) else {}
    return {
        "id": sim.get("experiment_id"),
        "alpha_id": sim.get("alpha_id"),
        "sharpe": sim.get("sharpe"),
        "fitness": sim.get("fitness"),
        "turnover": sim.get("turnover"),
        "margin": sim.get("margin"),
        "round": sim.get("round"),
        "hypothesis_id": sim.get("hypothesis_id"),
        "expression": sim.get("expression"),
        "health": health,
        "suspicious": bool(health and not health.get("ok")),
    }


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(base_dir) == "scripts":
        base_dir = os.path.dirname(base_dir)
    data_dir = os.path.join(base_dir, "research_data")
    input_path = os.path.join(data_dir, "simulations.jsonl")

    # Stream the source and keep only bounded high-signal evidence plus compact
    # counters; an all-day run must not retain the complete ledger.
    total_simulations = 0
    high_signal_count = 0
    high_signal_top = []
    healthy_count = 0
    noise_trap_count = 0
    noise_trap_examples = []
    expression_counts = defaultdict(int)
    duplicate_candidate_order = []
    hypothesis_counts = defaultdict(int)
    for sim in iter_jsonl(input_path):
        total_simulations += 1

        expr = sim.get("expression")
        if isinstance(expr, (str, int)) and str(expr).strip():
            canonical = canonical_expression(expr)
            expression_counts[canonical] += 1
            if expression_counts[canonical] == 2 and len(duplicate_candidate_order) < 5:
                duplicate_candidate_order.append(canonical)

        hyp = sim.get("hypothesis_id")
        if not isinstance(hyp, (str, int)) or not str(hyp).strip():
            hyp = None
        if hyp:
            hypothesis_counts[hyp] += 1

        if sim.get("status") != "DONE":
            continue
        sharpe = sim.get("sharpe")
        fitness = sim.get("fitness")
        sharpe_value = num(sharpe)
        fitness_value = num(fitness)
        if not ((sharpe_value is not None and sharpe_value > 3.0)
                or (fitness_value is not None and fitness_value > 8.0)):
            continue

        high_signal_count += 1
        compact = _compact_record(sim)
        high_signal_top.append(compact)
        high_signal_top.sort(
            key=lambda x: num(x.get("fitness"))
            if num(x.get("fitness")) is not None else float("-inf"),
            reverse=True,
        )
        del high_signal_top[TOP_AUDIT_LIMIT:]
        health = sim.get("health")
        if health and not health.get("ok"):
            noise_trap_count += 1
            if len(noise_trap_examples) < 5:
                noise_trap_examples.append(compact)
        else:
            healthy_count += 1

    print(f"Total simulations: {total_simulations}")

    print(f"High signal (S>3 or F>8): {high_signal_count}")
    print(f"Retained top evidence: {len(high_signal_top)} (cap={TOP_AUDIT_LIMIT})")

    # Sort by fitness
    high_signal_sorted = high_signal_top

    print("\nTop 15 by Fitness:")
    for i, s in enumerate(high_signal_sorted[:15], 1):
        expr = _display(s.get("expression"))[:60]
        print(f"{i:2}. S={_metric(s.get('sharpe'))} F={_metric(s.get('fitness'))} "
              f"TO={s.get('turnover') if s.get('turnover') is not None else 'NA'} "
              f"M={s.get('margin') if s.get('margin') is not None else 'NA'}")
        print(f"    {expr}")
        print(f"    Round={s.get('round')} Hyp={s.get('hypothesis_id')} "
              f"Alpha={s.get('alpha_id')} Health={s.get('health')}")
        print()

    # Check health of high signal (counts are calculated during the stream)
    print("\nHealth Analysis:")
    print(f"  Healthy high-signal: {healthy_count}")
    print(f"  Noise trap (CONCENTRATED_WEIGHT FAIL): {noise_trap_count}")

    if noise_trap_examples:
        print("\nNoise trap examples:")
        for s in noise_trap_examples:
            reasons = s.get("health", {}).get("reasons", [])
            print(f"  - {_display(s.get('id'))[:8]}: {reasons}")

    # Duplicate analysis.  Only after counting do we make a second bounded
    # pass for examples, avoiding a compact-record map for every expression.
    duplicate_count = sum(1 for count in expression_counts.values() if count > 1)
    duplicate_groups = {canonical: [] for canonical in duplicate_candidate_order}
    if duplicate_groups:
        for sim in iter_jsonl(input_path):
            expression = sim.get("expression")
            if not isinstance(expression, (str, int)):
                continue
            canonical = canonical_expression(expression)
            if canonical not in duplicate_groups:
                continue
            if len(duplicate_groups[canonical]) < 5:
                duplicate_groups[canonical].append(_compact_record(sim))
    print(f"\nDuplicate expressions: {duplicate_count}")

    for expr, items in duplicate_groups.items():
        print(f"\n  Expression: {expr[:80]}...")
        for item in items:
            print(f"    - Round {item.get('round')}: {_display(item.get('experiment_id'))[:8]} "
                  f"S={item.get('sharpe')} F={item.get('fitness')} "
                  f"Hyp={item.get('hypothesis_id')}")

    # Lineage depth analysis
    print("\nLineage depth distribution:")
    depth_counts = defaultdict(int)
    for count in hypothesis_counts.values():
        depth_counts[count] += 1

    for depth in sorted(depth_counts.keys())[:10]:
        print(f"  {depth} simulations: {depth_counts[depth]} hypotheses")

    # Save high signal audit
    audit = {
        "generated_at": datetime.fromtimestamp(
            os.path.getmtime(input_path), tz=timezone.utc
        ).isoformat(),
        "total_high_signal": high_signal_count,
        "healthy_count": healthy_count,
        "noise_trap_count": noise_trap_count,
        "top_high_signal": [
            s
            for s in high_signal_sorted
        ],
    }

    audit_path = os.path.join(data_dir, "high_signal_audit.json")
    atomic_write_json_if_changed(audit_path, audit, ignored_keys=("generated_at",))
    print(f"\nHigh signal audit saved to: {audit_path}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
