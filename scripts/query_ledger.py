#!/usr/bin/env python3
"""Data query tool for research ledger."""

import json
import os
import sys
import argparse
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.artifacts import iter_jsonl_objects
from wqb_agent.metrics import num


def _metric_text(value, digits=2):
    value = num(value)
    return f"{value:.{digits}f}" if value is not None else "?"


def _text(value):
    """Normalize optional expression text before string-only operations."""
    return str(value or "")


def _key(value, default=None):
    """Return a hashable scalar key for malformed legacy rows."""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return default


def _round_number(value):
    value = num(value)
    if value is None:
        return None
    return int(value) if value.is_integer() else value


def _push_top(top, sim, n, metric):
    value = num(sim.get(metric))
    if sim.get("status") != "DONE" or value is None:
        return
    top.append((value, sim))
    top.sort(key=lambda item: item[0], reverse=True)
    del top[n:]


def iter_simulations(data_dir):
    """Stream simulations; list materialization remains an explicit API."""
    return iter_jsonl_objects(os.path.join(data_dir, "simulations_final.jsonl"))


def load_simulations(data_dir):
    """Compatibility list loader for callers that explicitly need a list."""
    return list(iter_simulations(data_dir))


def query_by_round(sims, round_no):
    """Query simulations by round."""
    target = _round_number(round_no)
    return [s for s in sims if _round_number(s.get("round")) == target]


def query_by_hypothesis(sims, hyp_id):
    """Query simulations by hypothesis."""
    return [s for s in sims if s.get("hypothesis_id") == hyp_id]


def query_by_dataset(sims, dataset):
    """Query simulations by dataset."""
    return [s for s in sims if s.get("dataset") == dataset]


def query_by_status(sims, status):
    """Query simulations by status."""
    return [s for s in sims if s.get("status") == status]


def query_by_validation(sims, validation_status):
    """Query simulations by validation status."""
    return [s for s in sims if s.get("validation_status") == validation_status]


def query_top_performers(sims, n=10, metric="fitness"):
    """Query top N performers."""
    n = max(0, int(n))
    top = []
    for sim in sims:
        _push_top(top, sim, n, metric)
    return [sim for _value, sim in top]


def matches(sim, args):
    """Apply CLI filters without creating intermediate filtered lists."""
    return (
        (args.round is None or _round_number(sim.get("round")) == args.round)
        and (not args.hypothesis or sim.get("hypothesis_id") == args.hypothesis)
        and (not args.dataset or sim.get("dataset") == args.dataset)
        and (not args.status or sim.get("status") == args.status)
        and (not args.validation or sim.get("validation_status") == args.validation)
        and (not args.expression or args.expression.lower() in _text(sim.get("expression")).lower())
    )


def query_noise_traps(sims):
    """Query all noise traps."""
    return [s for s in sims if s.get("validation_status") == "NOISE_TRAP"]


def query_suspicious(sims):
    """Query all suspicious items."""
    return [s for s in sims if s.get("validation_status") == "SUSPICIOUS"]


def query_by_expression(sims, expression_pattern):
    """Query simulations by expression pattern."""
    pattern = _text(expression_pattern).lower()
    return [s for s in sims if pattern in _text(s.get("expression")).lower()]


def print_summary(sims):
    """Print summary statistics."""
    print("\n=== Research Ledger Summary ===\n")
    print(f"Total simulations: {len(sims)}")
    print(f"  DONE: {sum(1 for s in sims if s.get('status') == 'DONE')}")
    print(f"  FAILED: {sum(1 for s in sims if s.get('status') == 'FAILED')}")
    print(f"  UNKNOWN: {sum(1 for s in sims if s.get('status') == 'UNKNOWN')}")
    print(f"  PENDING: {sum(1 for s in sims if s.get('status') == 'PENDING')}")
    print()
    print(f"Hypotheses: {len(set(s.get('hypothesis_id') for s in sims if s.get('hypothesis_id')))}")
    print(f"Datasets: {len(set(s.get('dataset') for s in sims if s.get('dataset')))}")
    rounds = [_round_number(s.get("round")) for s in sims]
    rounds = [value for value in rounds if value is not None]
    print(f"Rounds: {min(rounds)}-{max(rounds)}" if rounds else "Rounds: none")
    print()
    validation_counts = defaultdict(int)
    for sim in sims:
        validation_counts[sim.get("validation_status") or "NONE"] += 1
    print("Validation Status:")
    for status, count in sorted(validation_counts.items(), key=lambda item: -item[1]):
        print(f"  {status}: {count}")
    print()
    noise_traps = query_noise_traps(sims)
    print(f"Noise traps: {len(noise_traps)}")
    if noise_traps:
        fields = defaultdict(int)
        for trap in noise_traps:
            expression = _text(trap.get("expression")).lower()
            for field in (
                "growth_potential_rank_derivative",
                "multi_factor_static_score_derivative",
                "composite_factor_score_derivative",
            ):
                if field in expression:
                    fields[field] += 1
        for field, count in sorted(fields.items(), key=lambda item: -item[1]):
            print(f"  {field}: {count}")
    print()
    print("Top 5 by Fitness:")
    for i, sim in enumerate(query_top_performers(sims, 5, "fitness"), 1):
        print(f"  {i}. Round {sim.get('round')}: S={_metric_text(sim.get('sharpe'))} "
              f"F={_metric_text(sim.get('fitness'))} Dataset={sim.get('dataset')} "
              f"Expression={_text(sim.get('expression'))[:50]}...")
    print()


def print_summary_stream(data_dir):
    """Print the summary directly from the source stream."""
    counts = defaultdict(int)
    validation_counts = defaultdict(int)
    hypotheses = set()
    datasets = set()
    min_round = max_round = None
    noise_fields = defaultdict(int)
    noise_total = 0
    top = []
    path = os.path.join(data_dir, "simulations_final.jsonl")
    for sim in iter_simulations(data_dir):
        counts[_key(sim.get("status"), "UNKNOWN")] += 1
        validation_counts[_key(sim.get("validation_status"), "NONE") or "NONE"] += 1
        hypothesis = _key(sim.get("hypothesis_id"))
        if hypothesis:
            hypotheses.add(hypothesis)
        dataset = _key(sim.get("dataset"))
        if dataset:
            datasets.add(dataset)
        if sim.get("round") is not None:
            round_no = _round_number(sim["round"])
            if round_no is None:
                continue
            min_round = round_no if min_round is None else min(min_round, round_no)
            max_round = round_no if max_round is None else max(max_round, round_no)
        if sim.get("validation_status") == "NOISE_TRAP":
            noise_total += 1
            expression = _text(sim.get("expression")).lower()
            for field in (
                "growth_potential_rank_derivative",
                "multi_factor_static_score_derivative",
                "composite_factor_score_derivative",
            ):
                if field in expression:
                    noise_fields[field] += 1
        _push_top(top, sim, 5, "fitness")
    total = sum(counts.values())
    print("\n=== Research Ledger Summary ===\n")
    print(f"Total simulations: {total}")
    for status in ("DONE", "FAILED", "UNKNOWN", "PENDING"):
        print(f"  {status}: {counts[status]}")
    print()
    print(f"Hypotheses: {len(hypotheses)}")
    print(f"Datasets: {len(datasets)}")
    if min_round is not None:
        print(f"Rounds: {min_round}-{max_round}")
    else:
        print("Rounds: none")
    print()
    print("Validation Status:")
    for status, count in sorted(validation_counts.items(), key=lambda item: -item[1]):
        print(f"  {status}: {count}")
    print()
    print(f"Noise traps: {noise_total}")
    if noise_fields:
        print("  Top noise trap fields:")
        for field, count in sorted(noise_fields.items(), key=lambda item: -item[1]):
            print(f"    {field}: {count}")
    print()
    print("Top 5 by Fitness:")
    for i, sim in enumerate((sim for _value, sim in top), 1):
        print(f"  {i}. Round {sim.get('round')}: S={_metric_text(sim.get('sharpe'))} "
              f"F={_metric_text(sim.get('fitness'))} Dataset={sim.get('dataset')} "
              f"Expression={_text(sim.get('expression'))[:50]}...")
    print()
def main():
    parser = argparse.ArgumentParser(description="Query the research ledger")
    parser.add_argument("--data-dir", default="research_data", help="Path to research_data directory")
    parser.add_argument("--summary", action="store_true", help="Print summary statistics")
    parser.add_argument("--round", type=int, help="Query by round number")
    parser.add_argument("--hypothesis", help="Query by hypothesis ID")
    parser.add_argument("--dataset", help="Query by dataset name")
    parser.add_argument("--status", choices=["DONE", "FAILED", "UNKNOWN", "PENDING"], help="Query by status")
    parser.add_argument("--validation", choices=["NOISE_TRAP", "SUSPICIOUS", "PROMISING"], help="Query by validation status")
    parser.add_argument("--top", type=int, default=10, help="Show top N performers")
    parser.add_argument("--metric", choices=["sharpe", "fitness"], default="fitness", help="Metric for top performers")
    parser.add_argument("--expression", help="Query by expression pattern")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--count", action="store_true", help="Only show count")

    args = parser.parse_args()

    source = iter_simulations(args.data_dir)
    all_count = sum(1 for _ in source)
    print(f"Loaded {all_count} simulations from {args.data_dir}")

    # Output
    if args.summary:
        print_summary_stream(args.data_dir)
    elif args.count:
        result_count = sum(
            1 for sim in iter_simulations(args.data_dir) if matches(sim, args)
        )
        print(f"Result count: {result_count}")
    elif args.top:
        top = query_top_performers(
            (sim for sim in iter_simulations(args.data_dir) if matches(sim, args)),
            args.top, args.metric,
        )
        if args.json:
            print(json.dumps(top, indent=2, ensure_ascii=False))
        else:
            print(f"\nTop {len(top)} by {args.metric}:")
            for i, s in enumerate(top, 1):
                print(f"{i}. Round {s.get('round')}: S={_metric_text(s.get('sharpe'))} "
                      f"F={_metric_text(s.get('fitness'))} D={s.get('dataset')} "
                      f"{_text(s.get('expression'))[:60]}...")
    elif args.json:
        filtered = [sim for sim in iter_simulations(args.data_dir) if matches(sim, args)]
        print(json.dumps(filtered, indent=2, ensure_ascii=False))
    else:
        # Default: print first 20 results
        filtered = [sim for sim in iter_simulations(args.data_dir) if matches(sim, args)]
        for s in filtered[:20]:
            print(f"[{s.get('status')}] Round {s.get('round')}: S={s.get('sharpe')} F={s.get('fitness')} "
                  f"D={s.get('dataset')} {_text(s.get('expression'))[:60]}...")
        if len(filtered) > 20:
            print(f"... and {len(filtered) - 20} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())
