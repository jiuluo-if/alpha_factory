#!/usr/bin/env python3
"""Generate a bounded lineage analysis and research ledger.

The source JSONL is a reproducible evidence stream. This report keeps only
aggregates and compact lineage statistics, so a long-running factory does not
need to materialize the complete historical ledger in memory.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.artifacts import (
    atomic_write_json_if_changed,
    atomic_write_text_if_changed,
    iter_jsonl_objects,
)
from wqb_agent.expression import canonical_expression
from wqb_agent.metrics import num


iter_jsonl = iter_jsonl_objects


def _value(row, key):
    value = num(row.get(key))
    return value if value is not None else 0.0


def _key(value, default=None):
    """Normalize JSON grouping keys without allowing list/dict keys."""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return default


def _new_lineage():
    return {
        "simulation_count": 0,
        "status_breakdown": defaultdict(int),
        "role_breakdown": defaultdict(int),
        "best_sharpe": 0.0,
        "best_fitness": 0.0,
        "best_expression": None,
        "expressions": set(),
        "suspicious_count": 0,
        "noise_trap_count": 0,
        "rounds": set(),
    }


def _aggregate(path):
    """Build all ledger aggregates in one source pass."""
    total = valid_evidence = research_failures = infra_failures = 0
    suspicious_signals = noise_traps = 0
    lineages = defaultdict(_new_lineage)
    datasets = defaultdict(lambda: {
        "count": 0, "done": 0, "failed": 0, "unknown": 0,
        "total_sharpe": 0.0, "total_fitness": 0.0, "suspicious": 0,
    })
    rounds = defaultdict(lambda: {
        "simulation_count": 0, "hypothesis_count": 0,
        "done_count": 0, "failed_count": 0, "suspicious_count": 0,
    })
    hypotheses_by_round = defaultdict(set)
    mutations = defaultdict(lambda: {
        "count": 0, "done": 0, "avg_sharpe": 0.0, "avg_fitness": 0.0,
    })
    mutation_sharpe_sum = defaultdict(float)
    mutation_fitness_sum = defaultdict(float)

    for sim in iter_jsonl(path):
        total += 1
        status = _key(sim.get("status"), "UNKNOWN") or "UNKNOWN"
        if status == "DONE":
            valid_evidence += 1
        failure_class = sim.get("failure_class")
        if failure_class in ("RESEARCH", "SYNTAX", "DATA"):
            research_failures += 1
        elif failure_class in ("INFRA", "AUTH", "RATE_LIMIT", "TIMEOUT", "UNKNOWN"):
            infra_failures += 1
        if sim.get("suspicious_high_signal"):
            suspicious_signals += 1
        if sim.get("suspicious_type") == "NOISE_TRAP_SUSPECT":
            noise_traps += 1

        hyp = _key(sim.get("hypothesis_id"))
        if hyp:
            lineage = lineages[hyp]
            lineage["simulation_count"] += 1
            lineage["status_breakdown"][status] += 1
            lineage["role_breakdown"][sim.get("validation_role", "UNKNOWN_ROLE")] += 1
            round_key = _key(sim.get("round"))
            if round_key:
                lineage["rounds"].add(round_key)
            expression = _key(sim.get("expression"))
            if expression:
                lineage["expressions"].add(canonical_expression(expression))
            if sim.get("suspicious_high_signal"):
                lineage["suspicious_count"] += 1
            if sim.get("suspicious_type") == "NOISE_TRAP_SUSPECT":
                lineage["noise_trap_count"] += 1
            if status == "DONE":
                sharpe = _value(sim, "sharpe")
                fitness = _value(sim, "fitness")
                if fitness > lineage["best_fitness"] or (
                    fitness == lineage["best_fitness"]
                    and sharpe > lineage["best_sharpe"]
                ):
                    lineage["best_fitness"] = fitness
                    lineage["best_sharpe"] = sharpe
                    lineage["best_expression"] = expression

        dataset = _key(sim.get("dataset"), "unknown") or "unknown"
        dataset_stat = datasets[dataset]
        dataset_stat["count"] += 1
        if status == "DONE":
            dataset_stat["done"] += 1
            dataset_stat["total_sharpe"] += _value(sim, "sharpe")
            dataset_stat["total_fitness"] += _value(sim, "fitness")
        elif status == "FAILED":
            dataset_stat["failed"] += 1
        elif status == "UNKNOWN":
            dataset_stat["unknown"] += 1
        if sim.get("suspicious_high_signal"):
            dataset_stat["suspicious"] += 1

        rnd = _key(sim.get("round"))
        if rnd:
            round_stat = rounds[rnd]
            round_stat["simulation_count"] += 1
            if status == "DONE":
                round_stat["done_count"] += 1
            elif status == "FAILED":
                round_stat["failed_count"] += 1
            if sim.get("suspicious_high_signal"):
                round_stat["suspicious_count"] += 1
            if hyp:
                hypotheses_by_round[rnd].add(hyp)

        mutation = _key(sim.get("mutation_type"), "unknown") or "unknown"
        mutation_stat = mutations[mutation]
        mutation_stat["count"] += 1
        if status == "DONE":
            mutation_stat["done"] += 1
            mutation_sharpe_sum[mutation] += _value(sim, "sharpe")
            mutation_fitness_sum[mutation] += _value(sim, "fitness")

    for rnd, stat in rounds.items():
        stat["hypothesis_count"] = len(hypotheses_by_round.get(rnd, set()))
    for mutation, stat in mutations.items():
        if stat["done"]:
            stat["avg_sharpe"] = mutation_sharpe_sum[mutation] / stat["done"]
            stat["avg_fitness"] = mutation_fitness_sum[mutation] / stat["done"]

    lineage_stats = []
    for hyp, stat in lineages.items():
        unique_count = len(stat["expressions"])
        lineage_stats.append({
            "hypothesis_id": hyp,
            "simulation_count": stat["simulation_count"],
            "status_breakdown": dict(stat["status_breakdown"]),
            "role_breakdown": dict(stat["role_breakdown"]),
            "best_sharpe": stat["best_sharpe"],
            "best_fitness": stat["best_fitness"],
            "best_expression": stat["best_expression"],
            "unique_expressions": unique_count,
            "duplicate_expressions": stat["simulation_count"] - unique_count,
            "suspicious_count": stat["suspicious_count"],
            "noise_trap_count": stat["noise_trap_count"],
            "rounds": sorted(stat["rounds"], key=str),
        })
    lineage_stats.sort(key=lambda item: item["simulation_count"], reverse=True)
    return {
        "total": total, "valid_evidence": valid_evidence,
        "research_failures": research_failures, "infra_failures": infra_failures,
        "suspicious_signals": suspicious_signals, "noise_traps": noise_traps,
        "lineage_stats": lineage_stats, "datasets": datasets,
        "rounds": rounds, "mutations": mutations,
    }


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(base_dir) == "scripts":
        base_dir = os.path.dirname(base_dir)
    data_dir = os.path.join(base_dir, "research_data")
    input_path = os.path.join(data_dir, "simulations_enhanced.jsonl")

    print("Loading enhanced simulations...")
    aggregate = _aggregate(input_path)
    lineage_stats = aggregate["lineage_stats"]
    datasets = aggregate["datasets"]
    rounds = aggregate["rounds"]
    mutations = aggregate["mutations"]
    print(f"Loaded {aggregate['total']} enhanced simulations")

    print("\n[1] Analyzing lineages...")
    print(f"  Total hypotheses: {len(lineage_stats)}")
    print("  Top 10 by simulation count:")
    for i, lineage in enumerate(lineage_stats[:10], 1):
        print(f"    {i}. {lineage['hypothesis_id']}: {lineage['simulation_count']} sims, "
              f"best F={lineage['best_fitness']:.2f}, "
              f"noise_traps={lineage['noise_trap_count']}")

    print("\n[2] Analyzing datasets...")
    print(f"  Total datasets: {len(datasets)}")
    for name, stat in sorted(datasets.items(), key=lambda item: item[1]["count"], reverse=True)[:10]:
        done = stat["done"]
        avg_sharpe = stat["total_sharpe"] / done if done else 0
        avg_fitness = stat["total_fitness"] / done if done else 0
        print(f"    {name}: {stat['count']} sims, {done} done, "
              f"avg S={avg_sharpe:.2f}, avg F={avg_fitness:.2f}, "
              f"suspicious={stat['suspicious']}")

    print("\n[3] Analyzing rounds...")
    peak_rounds = sorted(rounds.items(), key=lambda item: item[1]["simulation_count"], reverse=True)[:10]
    print(f"  Total rounds: {len(rounds)}")
    print("  Top 10 rounds by simulation count:")
    for rnd, stat in peak_rounds:
        print(f"    Round {rnd}: {stat['simulation_count']} sims, "
              f"{stat['hypothesis_count']} hypotheses, "
              f"{stat['done_count']} done, {stat['failed_count']} failed")

    print("\n[4] Analyzing mutations...")
    print(f"  Total mutation types: {len(mutations)}")
    for name, stat in sorted(mutations.items(), key=lambda item: item[1]["count"], reverse=True)[:15]:
        print(f"    {name}: {stat['count']} sims, {stat['done']} done, "
              f"avg S={stat['avg_sharpe']:.2f}, avg F={stat['avg_fitness']:.2f}")

    generated_at = datetime.fromtimestamp(
        os.path.getmtime(input_path), tz=timezone.utc
    ).isoformat()
    summary = {
        "total_simulations": aggregate["total"],
        "total_hypotheses": len(lineage_stats),
        "total_rounds": len(rounds),
        "total_datasets": len(datasets),
        "valid_evidence": aggregate["valid_evidence"],
        "research_failures": aggregate["research_failures"],
        "infra_failures": aggregate["infra_failures"],
        "suspicious_signals": aggregate["suspicious_signals"],
        "noise_traps": aggregate["noise_traps"],
    }
    ledger = {
        "generated_at": generated_at, "summary": summary,
        "lineages": lineage_stats[:50], "datasets": dict(datasets),
        "rounds": {str(key): value for key, value in sorted(rounds.items(), key=lambda item: str(item[0]))},
        "mutations": dict(mutations),
    }
    ledger_path = os.path.join(data_dir, "research_ledger.json")
    atomic_write_json_if_changed(ledger_path, ledger, ignored_keys=("generated_at",))
    print(f"\n[5] Research ledger saved to: {ledger_path}")

    report_lines = [
        "# Research Ledger - Comprehensive Analysis", "",
        f"**Generated**: {generated_at}",
        f"**Total Simulations**: {summary['total_simulations']}",
        f"**Valid Evidence**: {summary['valid_evidence']}", "",
        "## Summary", "", "| Metric | Count |", "|--------|-------|",
        f"| Total Simulations | {summary['total_simulations']} |",
        f"| Valid Research Evidence | {summary['valid_evidence']} |",
        f"| Research Failures | {summary['research_failures']} |",
        f"| Infra/System Failures | {summary['infra_failures']} |",
        f"| Suspicious Signals | {summary['suspicious_signals']} |",
        f"| Noise Traps Detected | {summary['noise_traps']} |",
        f"| Hypotheses | {summary['total_hypotheses']} |",
        f"| Rounds | {summary['total_rounds']} |",
        f"| Datasets | {summary['total_datasets']} |", "",
        "## Top Lineages by Simulation Count", "",
        "| Rank | Hypothesis | Sims | Best F | Noise Traps |",
        "|------|------------|------|--------|-------------|",
    ]
    for i, lineage in enumerate(lineage_stats[:20], 1):
        report_lines.append(
            f"| {i} | {lineage['hypothesis_id']} | {lineage['simulation_count']} | "
            f"{lineage['best_fitness']:.2f} | {lineage['noise_trap_count']} |"
        )
    report_lines.extend([
        "", "## Dataset Breakdown", "",
        "| Dataset | Total | Done | Avg Sharpe | Avg Fitness | Suspicious |",
        "|---------|-------|------|------------|-------------|------------|",
    ])
    for name, stat in sorted(datasets.items(), key=lambda item: item[1]["count"], reverse=True):
        done = stat["done"]
        avg_sharpe = stat["total_sharpe"] / done if done else 0
        avg_fitness = stat["total_fitness"] / done if done else 0
        report_lines.append(
            f"| {name} | {stat['count']} | {done} | {avg_sharpe:.2f} | "
            f"{avg_fitness:.2f} | {stat['suspicious']} |"
        )
    report_lines.extend([
        "", "## Mutation Type Distribution", "",
        "| Mutation | Count | Done | Avg Sharpe | Avg Fitness |",
        "|----------|-------|------|------------|-------------|",
    ])
    for name, stat in sorted(mutations.items(), key=lambda item: item[1]["count"], reverse=True)[:15]:
        report_lines.append(
            f"| {name} | {stat['count']} | {stat['done']} | "
            f"{stat['avg_sharpe']:.2f} | {stat['avg_fitness']:.2f} |"
        )
    report_path = os.path.join(data_dir, "RESEARCH_LEDGER_DETAILED.md")
    atomic_write_text_if_changed(report_path, "\n".join(report_lines))
    print(f"[6] Detailed report saved to: {report_path}")
    print("\n" + "=" * 60)
    print("Research Ledger Generation Complete")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
