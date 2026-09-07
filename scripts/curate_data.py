#!/usr/bin/env python3
"""
Simulation Data Curator - Research Ledger Generator

This script processes the append-only trajectory.jsonl and produces:
1. simulations.jsonl - Normalized simulation records with canonical schema
2. experiments.jsonl - Experiment-level records with lineage tracking
3. lineages.jsonl - Lineage reconstruction (Hypothesis → Simulation)
4. data_quality_report.json - Integrity checks and statistics

Pipeline:
  Raw trajectory → Normalize → Classify → Deduplicate → Link lineage → Validate
"""

import json
import os
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.artifacts import atomic_write_json_if_changed, atomic_write_jsonl_if_changed
from wqb_agent.failures import FailureKind, classify_error
from wqb_agent.expression import canonical_expression
from wqb_agent.metrics import num


# ──────────────────────────────────────────────────────────────
# Schema definitions
# ──────────────────────────────────────────────────────────────

SIMULATION_SCHEMA = [
    "experiment_id",
    "simulation_id",
    "alpha_id",
    "round",
    "hypothesis_id",
    "belief_key",
    "candidate_id",
    "parent_id",
    "lineage_root",
    "mutation_type",
    "research_question",
    "dataset",
    "fields_used",
    "expression",
    "settings",
    "status",
    "failure_class",
    "sharpe",
    "fitness",
    "turnover",
    "returns",
    "drawdown",
    "margin",
    "checks",
    "created_at",
    "submitted_at",
    "completed_at",
    "validation_role",
    "source_file",
    "source_line",
]

EXPERIMENT_SCHEMA = [
    "experiment_id",
    "round",
    "hypothesis_id",
    "expression",
    "settings",
    "fields_used",
    "datasets",
    "status",
    "metrics",
    "error",
    "alpha_id",
    "mutation",
    "rationale",
    "direction",
    "expected_horizon",
    "falsification",
    "health",
    "elapsed_sec",
    "created_at",
    "simulations",  # list of simulation_ids
]

LINEAGE_SCHEMA = [
    "lineage_id",
    "root_hypothesis",
    "parent_expression",
    "child_expression",
    "mutation_dimension",
    "depth",
    "experiment_count",
    "created_at",
    "updated_at",
]


# ──────────────────────────────────────────────────────────────
# Failure classification (mirrors wqb_agent/failures.py)
# ──────────────────────────────────────────────────────────────

def classify_failure(error_text: str, status: str) -> str:
    """Compatibility adapter around the production failure taxonomy."""
    if status == "UNKNOWN":
        return FailureKind.UNKNOWN
    return classify_error(error_text)


def normalize_round(value):
    """Use one comparable numeric round key for legacy string rounds."""
    number = num(value)
    if number is None:
        return None if value is None else value
    return int(number) if number.is_integer() else number


# ──────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────

def iter_trajectory(path: str, *, warn_invalid=True):
    """Yield valid trajectory rows without materializing the full history."""
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                exp = json.loads(line)
                if not isinstance(exp, dict):
                    continue
                exp["_source_line"] = line_no
                yield exp
            except json.JSONDecodeError as e:
                if warn_invalid:
                    print(f"[WARN] Invalid JSON at line {line_no}: {e}", file=sys.stderr)


def load_trajectory(path: str) -> list[dict]:
    """Compatibility wrapper for callers that explicitly need a list."""
    return list(iter_trajectory(path))


def _experiment_row(exp):
    """Build the legacy experiment-level view from one trajectory row."""
    return {
        "experiment_id": exp.get("id"),
        "round": normalize_round(exp.get("round")),
        "hypothesis_id": exp.get("hypothesis_id"),
        "expression": exp.get("expression"),
        "settings": exp.get("settings"),
        "fields_used": exp.get("fields_used"),
        "datasets": exp.get("datasets"),
        "status": exp.get("status"),
        "metrics": exp.get("metrics"),
        "error": exp.get("error"),
        "alpha_id": exp.get("alpha_id"),
        "mutation": exp.get("mutation"),
        "rationale": exp.get("rationale"),
        "direction": exp.get("direction"),
        "expected_horizon": exp.get("expected_horizon"),
        "falsification": exp.get("falsification"),
        "health": exp.get("health"),
        "elapsed_sec": exp.get("elapsed_sec"),
        "created_at": exp.get("created_at"),
        "source_file": "trajectory.jsonl",
        "source_line": exp.get("_source_line"),
    }


def iter_experiment_rows(path):
    """Stream the compatibility experiment view on a second bounded pass."""
    for exp in iter_trajectory(path, warn_invalid=False):
        yield _experiment_row(exp)


def load_experience(path: str) -> dict:
    """Load experience.json for hypothesis context."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


# ──────────────────────────────────────────────────────────────
# Normalization
# ──────────────────────────────────────────────────────────────

def normalize_simulation(exp: dict, source_file: str, source_line: int) -> dict:
    """Normalize one trajectory entry to canonical simulation record."""
    metrics = exp.get("metrics") if isinstance(exp.get("metrics"), dict) else {}
    raw_checks = metrics.get("checks") or []
    checks = raw_checks if isinstance(raw_checks, list) else []

    # Determine validation role
    mutation = exp.get("mutation") if isinstance(exp.get("mutation"), str) else ""
    rationale = exp.get("rationale") if isinstance(exp.get("rationale"), str) else ""
    if mutation.startswith("validation-"):
        role = "VALIDATION"
    elif mutation in ("baseline", "sign-flip"):
        role = "DISCOVERY"
    elif mutation.startswith("deepening") or "deepen" in rationale.lower():
        role = "DEEPENING"
    else:
        role = "UNKNOWN_ROLE"

    # Determine failure class if applicable
    failure_class = None
    if exp.get("status") == "FAILED":
        failure_class = classify_failure(exp.get("error") or "", exp.get("status"))
    elif exp.get("status") == "UNKNOWN":
        failure_class = FailureKind.UNKNOWN

    # Timestamps
    created_at = num(exp.get("created_at"))
    submitted_at = None
    completed_at = None
    if created_at is not None:
        try:
            dt = datetime.fromtimestamp(created_at, tz=timezone.utc)
            submitted_at = dt.isoformat()
            completed_at = dt.isoformat()
        except (TypeError, ValueError, OSError, OverflowError):
            pass

    # Settings normalization
    settings = exp.get("settings") if isinstance(exp.get("settings"), dict) else {}

    # Fields extraction
    fields_used = exp.get("fields_used") if isinstance(exp.get("fields_used"), list) else []
    datasets = exp.get("datasets") if isinstance(exp.get("datasets"), list) else []
    dataset = datasets[0] if datasets else None

    # Extract hypothesis statement from experience memory if available
    hypothesis_statement = None
    hyp_id = exp.get("hypothesis_id")
    if hyp_id is not None and not isinstance(hyp_id, str):
        hyp_id = str(hyp_id)
    if hyp_id and hyp_id.startswith("h-r"):
        # Try to find in experience active_hypotheses
        pass  # Will be populated in linkage phase

    record = {
        # Core identifiers
        "experiment_id": exp.get("id"),
        "simulation_id": exp.get("id"),  # In this system, experiment=simulation
        "alpha_id": exp.get("alpha_id"),
        "round": normalize_round(exp.get("round")),
        "hypothesis_id": hyp_id,

        # Lineage
        "belief_key": None,  # Will be filled in linkage
        "candidate_id": None,  # Will be filled in linkage
        "parent_id": None,  # Will be filled in linkage
        "lineage_root": hyp_id,
        "mutation_type": mutation,

        # Research context
        "research_question": rationale or None,
        "dataset": dataset,
        "fields_used": fields_used,
        "expression": (
            exp.get("expression")
            if isinstance(exp.get("expression"), str)
            else (str(exp.get("expression")) if exp.get("expression") is not None else None)
        ),

        # Settings
        "settings": {
            "universe": settings.get("universe", "TOP3000"),
            "region": settings.get("region", "USA"),
            "delay": settings.get("delay", 1),
            "decay": settings.get("decay", 4),
            "neutralization": settings.get("neutralization", "SUBINDUSTRY"),
            "truncation": settings.get("truncation", 0.08),
            "pasteurization": settings.get("pasteurization", "ON"),
        },

        # Results
        "status": exp.get("status", "UNKNOWN"),
        "failure_class": failure_class,
        "sharpe": num(metrics.get("sharpe")),
        "fitness": num(metrics.get("fitness")),
        "turnover": num(metrics.get("turnover")),
        "returns": num(metrics.get("returns")),
        "drawdown": num(metrics.get("drawdown")),
        "margin": num(metrics.get("margin")),
        "checks": checks,

        # Timestamps
        "created_at": submitted_at,
        "submitted_at": submitted_at,
        "completed_at": completed_at,

        # Validation role
        "validation_role": role,

        # Source tracking
        "source_file": source_file,
        "source_line": source_line,
    }

    # Add optional fields if present
    if exp.get("health"):
        record["health"] = exp["health"]
    if exp.get("direction"):
        record["direction"] = exp["direction"]
    if exp.get("expected_horizon"):
        record["expected_horizon"] = exp["expected_horizon"]
    if exp.get("falsification"):
        record["falsification"] = exp["falsification"]
    if exp.get("elapsed_sec"):
        record["elapsed_sec"] = exp["elapsed_sec"]

    return record


# ──────────────────────────────────────────────────────────────
# Lineage reconstruction
# ──────────────────────────────────────────────────────────────

def build_lineages(simulations: list[dict]) -> list[dict]:
    """Reconstruct lineage from simulation records."""
    # Group by hypothesis
    by_hypothesis = defaultdict(list)
    for sim in simulations:
        hyp_id = sim.get("hypothesis_id")
        if hyp_id:
            by_hypothesis[hyp_id].append(sim)

    lineages = []
    for hyp_id, sims in by_hypothesis.items():
        # Sort by creation time
        sims_sorted = sorted(sims, key=lambda x: x.get("created_at") or 0)

        # Build lineage chains based on mutation patterns
        roots = []
        for sim in sims_sorted:
            mutation = sim.get("mutation_type") or ""
            if mutation in ("baseline", "") or mutation.endswith("-seed"):
                roots.append(sim.get("experiment_id"))

        if not roots:
            # If no clear root, use first experiment
            roots = [sims_sorted[0].get("experiment_id")] if sims_sorted else []

        # Track parent relationships with one indexed pass.  Repeated
        # positional lookup made long histories quadratic before the lineage
        # report was written.
        children_by_parent = defaultdict(list)
        for idx, sim in enumerate(sims_sorted):
            mutation = sim.get("mutation_type") or ""

            parent_id = None
            if mutation not in ("baseline", "sign-flip", "") and idx > 0:
                parent_id = sims_sorted[idx - 1].get("experiment_id")

            if parent_id is not None:
                children_by_parent[parent_id].append(sim.get("experiment_id"))

        # Build lineage entries
        for root_id in roots:
            lineage_id = f"lg-{hyp_id[:8]}"
            depth = 0
            chain = [root_id]

            # Find children
            visited = {root_id}
            queue = deque([(root_id, 0)])
            while queue:
                current_id, current_depth = queue.popleft()
                for sim_id in children_by_parent.get(current_id, ()):
                    if sim_id in visited:
                        continue
                    chain.append(sim_id)
                    visited.add(sim_id)
                    queue.append((sim_id, current_depth + 1))
                    depth = max(depth, current_depth + 1)

            # Count experiments in this lineage
            exp_count = len(chain)

            created_at = None
            updated_at = None
            chain_set = set(chain)
            for sim in sims_sorted:
                if sim.get("experiment_id") in chain_set:
                    ts = sim.get("created_at")
                    if ts:
                        if created_at is None or ts < created_at:
                            created_at = ts
                        if updated_at is None or ts > updated_at:
                            updated_at = ts

            # Get root expression
            root_expr = None
            child_expr = None
            for sim in sims_sorted:
                if sim.get("experiment_id") == root_id:
                    root_expr = sim.get("expression")
                elif sim.get("experiment_id") in chain_set:
                    child_expr = sim.get("expression")
                    break

            lineage = {
                "lineage_id": lineage_id,
                "root_hypothesis": hyp_id,
                "parent_expression": root_expr,
                "child_expression": child_expr,
                "mutation_dimension": sims_sorted[0].get("mutation_type") if sims_sorted else None,
                "depth": depth,
                "experiment_count": exp_count,
                "created_at": created_at,
                "updated_at": updated_at,
            }
            lineages.append(lineage)

    return lineages


# ──────────────────────────────────────────────────────────────
# Deduplication detection
# ──────────────────────────────────────────────────────────────

def detect_duplicates(simulations: list[dict]) -> dict:
    """Detect duplicate simulations by expression or alpha_id."""
    by_expression = defaultdict(list)
    by_alpha_id = defaultdict(list)

    for sim in simulations:
        expr = sim.get("expression")
        alpha_id = sim.get("alpha_id")
        if expr:
            # Match the production identity: whitespace/case-only variants
            # are one expression and must not be counted as independent work.
            by_expression[canonical_expression(expr)].append(sim)
        if alpha_id:
            by_alpha_id[alpha_id].append(sim)

    duplicates = {
        "by_expression": {},
        "by_alpha_id": {},
        "orphan_simulations": [],
    }

    for expr, sims in by_expression.items():
        if len(sims) > 1:
            duplicates["by_expression"][expr] = [s.get("experiment_id") for s in sims]

    for alpha_id, sims in by_alpha_id.items():
        if len(sims) > 1:
            duplicates["by_alpha_id"][alpha_id] = [s.get("experiment_id") for s in sims]

    # Find orphan simulations (no hypothesis_id)
    for sim in simulations:
        if not sim.get("hypothesis_id"):
            duplicates["orphan_simulations"].append(sim.get("experiment_id"))

    return duplicates


# ──────────────────────────────────────────────────────────────
# Integrity checks
# ──────────────────────────────────────────────────────────────

def run_integrity_checks(simulations: list[dict], duplicates: dict) -> dict:
    """Run data integrity checks per §9 requirements."""
    checks = {
        "completed_without_record": [],
        "memory_evidence_without_simulation": [],
        "validation_without_parent": [],
        "infra_as_research_evidence": [],
        "duplicate_counted_as_independent": [],
        "missing_metrics_assumed_zero": [],
        "missing_checks_assumed_pass": [],
        "suspicious_high_unverified": [],
    }

    # 1. Completed simulations must have unique record
    seen_ids = set()
    for sim in simulations:
        sim_id = sim.get("experiment_id")
        if sim_id in seen_ids:
            checks["completed_without_record"].append(sim_id)
        seen_ids.add(sim_id)

    # 2. Validation evidence must have parent
    for sim in simulations:
        if sim.get("validation_role") == "VALIDATION":
            if not sim.get("parent_id"):
                checks["validation_without_parent"].append(sim.get("experiment_id"))

    # 3. INFRA failures must not be research evidence
    for sim in simulations:
        if sim.get("failure_class") in (FailureKind.INFRA, FailureKind.AUTH,
                                         FailureKind.RATE_LIMIT, FailureKind.TIMEOUT):
            if sim.get("status") == "DONE" and sim.get("sharpe") is not None:
                checks["infra_as_research_evidence"].append({
                    "id": sim.get("experiment_id"),
                    "failure_class": sim.get("failure_class"),
                    "sharpe": sim.get("sharpe"),
                })

    # 4. Missing metrics should not be auto-assumed 0
    for sim in simulations:
        if sim.get("status") == "DONE":
            metrics = [sim.get(k) for k in ["sharpe", "fitness", "turnover", "returns", "drawdown", "margin"]]
            if any(m is None for m in metrics):
                checks["missing_metrics_assumed_zero"].append({
                    "id": sim.get("experiment_id"),
                    "missing": [k for k, v in zip(["sharpe", "fitness", "turnover", "returns", "drawdown", "margin"], metrics) if v is None],
                })

    # 5. Missing checks should not be auto-assumed PASS
    for sim in simulations:
        if sim.get("status") == "DONE":
            checks_list = sim.get("checks")
            if checks_list is not None and len(checks_list) == 0:
                checks["missing_checks_assumed_pass"].append(sim.get("experiment_id"))

    # 6. Suspicious high signal without validation
    parent_ids = {sim.get("parent_id") for sim in simulations if sim.get("parent_id")}
    for sim in simulations:
        if sim.get("status") == "DONE":
            sharpe = sim.get("sharpe")
            fitness = sim.get("fitness")
            if (sharpe and sharpe > 3.0) or (fitness and fitness > 8.0):
                # Check if it has validation children
                if sim.get("experiment_id") not in parent_ids:
                    checks["suspicious_high_unverified"].append({
                        "id": sim.get("experiment_id"),
                        "sharpe": sharpe,
                        "fitness": fitness,
                    })

    return checks


# ──────────────────────────────────────────────────────────────
# Statistics generation
# ──────────────────────────────────────────────────────────────

def compute_statistics(simulations: list[dict], duplicates: dict, lineages: list[dict]) -> dict:
    """Compute research ledger statistics."""
    total = len(simulations)

    # Status breakdown
    status_counts = defaultdict(int)
    for sim in simulations:
        status_counts[sim.get("status", "UNKNOWN")] += 1

    # Failure class breakdown
    failure_counts = defaultdict(int)
    for sim in simulations:
        fc = sim.get("failure_class")
        if fc:
            failure_counts[fc] += 1

    # Validation role breakdown
    role_counts = defaultdict(int)
    for sim in simulations:
        role = sim.get("validation_role", "UNKNOWN_ROLE")
        role_counts[role] += 1

    # Research vs infra failures
    research_failures = sum(1 for s in simulations
                           if s.get("failure_class") in (FailureKind.RESEARCH,
                                                         FailureKind.SYNTAX,
                                                         FailureKind.DATA))
    infra_failures = sum(1 for s in simulations
                        if s.get("failure_class") in (FailureKind.INFRA,
                                                      FailureKind.AUTH,
                                                      FailureKind.RATE_LIMIT,
                                                      FailureKind.TIMEOUT,
                                                      FailureKind.UNKNOWN))

    # Valid research evidence (DONE with metrics)
    valid_evidence = sum(1 for s in simulations
                        if s.get("status") == "DONE" and s.get("sharpe") is not None)

    # Round breakdown
    round_counts = defaultdict(int)
    for sim in simulations:
        round_counts[sim.get("round")] += 1

    # Dataset breakdown
    dataset_counts = defaultdict(int)
    for sim in simulations:
        ds = sim.get("dataset")
        if ds:
            dataset_counts[ds] += 1

    # Hypothesis breakdown
    hypothesis_counts = defaultdict(int)
    for sim in simulations:
        hyp = sim.get("hypothesis_id")
        if hyp:
            hypothesis_counts[hyp] += 1

    # Lineage breakdown
    lineage_counts = defaultdict(int)
    for lin in lineages:
        lineage_counts[lin.get("lineage_id")] = lin.get("experiment_count", 0)

    # Duplicate counts
    dup_expr_count = sum(len(v) for v in duplicates.get("by_expression", {}).values())
    dup_alpha_count = sum(len(v) for v in duplicates.get("by_alpha_id", {}).values())

    stats = {
        "total_simulations": total,
        "status_breakdown": dict(status_counts),
        "failure_class_breakdown": dict(failure_counts),
        "validation_role_breakdown": dict(role_counts),
        "research_failures": research_failures,
        "infra_failures": infra_failures,
        "valid_research_evidence": valid_evidence,
        "round_count": len(round_counts),
        "rounds_range": [min(round_counts.keys()), max(round_counts.keys())] if round_counts else [0, 0],
        "dataset_breakdown": dict(dataset_counts),
        "hypothesis_count": len(hypothesis_counts),
        "lineage_count": len(lineages),
        "duplicate_expressions": dup_expr_count,
        "duplicate_alpha_ids": dup_alpha_count,
        "orphan_simulations": len(duplicates.get("orphan_simulations", [])),
    }

    return stats


# ──────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────

def write_jsonl_if_changed(path: str, rows: list[dict]) -> bool:
    """Write one derived JSONL artifact only when its logical bytes change."""
    return atomic_write_jsonl_if_changed(path, rows)

def main():
    """Main data curation pipeline."""
    print("=" * 60)
    print("Simulation Data Curator - Research Ledger Generator")
    print("=" * 60)

    # Paths
    # Find project root by looking for .wqb_state directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # Check if we're in scripts/ subdir
    if os.path.basename(base_dir) == "scripts":
        base_dir = os.path.dirname(base_dir)
    state_dir = os.path.join(base_dir, ".wqb_state")
    output_dir = os.path.join(base_dir, "research_data")
    os.makedirs(output_dir, exist_ok=True)

    trajectory_path = os.path.join(state_dir, "trajectory.jsonl")
    experience_path = os.path.join(state_dir, "experience.json")

    if not os.path.exists(trajectory_path):
        print(f"[ERROR] Trajectory file not found: {trajectory_path}", file=sys.stderr)
        sys.exit(1)

    # Load data
    print("\n[1/5] Loading trajectory data...")
    simulations = []
    for exp in iter_trajectory(trajectory_path):
        simulations.append(
            normalize_simulation(exp, "trajectory.jsonl", exp.get("_source_line"))
        )
    print(f"       Loaded {len(simulations)} experiments")

    experience = load_experience(experience_path)
    print(f"       Loaded experience memory (updated_round={experience.get('updated_round', '?')})")

    # Normalize
    print("\n[2/5] Normalizing simulation records...")
    print(f"       Normalized {len(simulations)} records")

    # Build lineages
    print("\n[3/5] Reconstructing lineages...")
    lineages = build_lineages(simulations)
    print(f"       Reconstructed {len(lineages)} lineages")

    # Detect duplicates
    print("\n[4/5] Detecting duplicates and anomalies...")
    duplicates = detect_duplicates(simulations)
    print(f"       Found {len(duplicates.get('by_expression', {}))} duplicate expressions")
    print(f"       Found {len(duplicates.get('by_alpha_id', {}))} duplicate alpha_ids")
    print(f"       Found {len(duplicates.get('orphan_simulations', []))} orphan simulations")

    # Run integrity checks
    integrity = run_integrity_checks(simulations, duplicates)
    print(f"       Integrity issues found:")
    for key, value in integrity.items():
        if value:
            print(f"         - {key}: {len(value) if isinstance(value, list) else 'N/A'}")

    # Compute statistics
    print("\n[5/5] Computing statistics...")
    stats = compute_statistics(simulations, duplicates, lineages)

    # Write outputs
    print("\nWriting output files...")

    # 1. simulations.jsonl
    sim_path = os.path.join(output_dir, "simulations.jsonl")
    write_jsonl_if_changed(sim_path, simulations)
    print(f"       {sim_path} ({len(simulations)} records)")

    # 2. experiments.jsonl (can be same as simulations in this simple case)
    exp_path = os.path.join(output_dir, "experiments.jsonl")
    write_jsonl_if_changed(exp_path, iter_experiment_rows(trajectory_path))
    print(f"       {exp_path} ({len(simulations)} records)")

    # 3. lineages.jsonl
    lineage_path = os.path.join(output_dir, "lineages.jsonl")
    write_jsonl_if_changed(lineage_path, lineages)
    print(f"       {lineage_path} ({len(lineages)} records)")

    # 4. data_quality_report.json
    report_path = os.path.join(output_dir, "data_quality_report.json")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "statistics": stats,
        "integrity_checks": integrity,
        "duplicates": {
            "by_expression_count": len(duplicates.get("by_expression", {})),
            "by_alpha_id_count": len(duplicates.get("by_alpha_id", {})),
            "orphan_count": len(duplicates.get("orphan_simulations", [])),
        },
        "schema_compliance": {
            "simulation_schema": SIMULATION_SCHEMA,
            "experiment_schema": EXPERIMENT_SCHEMA,
            "lineage_schema": LINEAGE_SCHEMA,
        },
    }
    atomic_write_json_if_changed(
        report_path, report, ignored_keys=("generated_at",)
    )
    print(f"       {report_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("RESEARCH LEDGER SUMMARY")
    print("=" * 60)
    print(f"Total Simulations: {stats['total_simulations']}")
    print(f"Valid Research Evidence: {stats['valid_research_evidence']}")
    print(f"Research Failures: {stats['research_failures']}")
    print(f"Infra/System Failures: {stats['infra_failures']}")
    print(f"Duplicate Expressions: {stats['duplicate_expressions']}")
    print(f"Orphan Simulations: {stats['orphan_simulations']}")
    print(f"Lineages Reconstructed: {stats['lineage_count']}")
    print(f"Hypotheses Tested: {stats['hypothesis_count']}")
    print(f"Datasets Used: {len(stats.get('dataset_breakdown', {}))}")
    print(f"Rounds Covered: {stats['rounds_range'][0]}-{stats['rounds_range'][1]}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
