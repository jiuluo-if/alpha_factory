#!/usr/bin/env python3
"""
High Signal Validation - Plan real cross-validation for high-signal simulations.

This script generates perturbation experiments for high-signal items and
emits heuristic-only review labels and perturbation plans.  It never writes a
platform validation verdict; real validation must be executed by the outer
production proposal/checkpoint path.

Since we cannot run real simulations in this context, we perform:
1. Static analysis of perturbation patterns
2. Heuristic validation based on known noise trap characteristics
3. Generate validation plan for future execution
"""

import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from itertools import islice

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.artifacts import (
    atomic_write_json_if_changed,
    atomic_write_jsonl_if_changed,
    atomic_write_text_if_changed,
    iter_jsonl_objects,
)
from wqb_agent.metrics import num


# A report is a decision aid, not a second historical ledger.  The full
# heuristic annotation is regenerated directly into simulations_validated.jsonl;
# only the most useful bounded subset is retained in validation_report.json.
MAX_VALIDATION_REPORT_RESULTS = 256


def _metric_text(value):
    """Render legacy numeric strings and missing metrics safely in reports."""
    value = num(value)
    return f"{value:.2f}" if value is not None else "?"


def _short_text(value, limit=8):
    """Keep report identifiers/expressions bounded and printable."""
    text = str(value or "?").replace("\n", " ")
    return text[:limit]


def extract_fields(expression):
    """Extract field names from expression."""
    if not expression:
        return []
    # Common field patterns
    patterns = [
        r'[a-z_][a-z0-9_]*(?=[,\)\+\-\*/\s])',  # simple fields
        r'([a-z_][a-z0-9_]*(?:\-[a-z0-9_]+)*)',  # compound fields
    ]
    fields = set()
    for pattern in patterns:
        matches = re.findall(pattern, expression.lower())
        fields.update(matches)
    return sorted(fields)


def generate_perturbations(expression, fields_used, max_perturbs=4):
    """Generate perturbation expressions for validation."""
    expression = expression if isinstance(expression, str) else str(expression or "")
    fields_used = fields_used if isinstance(fields_used, list) else []
    perms = []
    seen = set()

    def add(new_expr, label):
        if new_expr and new_expr != expression and new_expr not in seen:
            seen.add(new_expr)
            perms.append((new_expr, label))

    # Window perturbation
    window_patterns = [
        (r'ts_zscore\(([^,]+),\s*(\d+)\)', r'ts_zscore(\1, \g<2>)'),
        (r'ts_mean\(([^,]+),\s*(\d+)\)', r'ts_mean(\1, \g<2>)'),
        (r'ts_rank\(([^,]+),\s*(\d+)\)', r'ts_rank(\1, \g<2>)'),
        (r'ts_av_diff\(([^,]+),\s*(\d+)\)', r'ts_av_diff(\1, \g<2>)'),
    ]

    for old_pattern, new_pattern in window_patterns:
        match = re.search(old_pattern, expression)
        if match:
            old_window = match.group(2)
            # Try +20% and -20% window
            for factor in [0.8, 1.2]:
                new_window = str(int(float(old_window) * factor))
                if new_window != old_window:
                    new_expr = re.sub(old_pattern, lambda m: f'{m.group(1)}, {new_window}', expression)
                    add(new_expr, f"window-{old_window}->{new_window}")

    # Smooth perturbation
    if 'ts_mean(' not in expression and 'rank(' in expression:
        add(f"ts_mean({expression}, 5)", "smooth-ts-mean-5")

    # Field swap perturbation (if multiple fields)
    if len(fields_used) >= 2:
        primary = fields_used[0]
        for alt_field in fields_used[1:3]:
            if alt_field != primary:
                new_expr = expression.replace(primary, alt_field, 1)
                if new_expr != expression:
                    add(new_expr, f"field-swap->{alt_field}")

    return perms[:max_perturbs]


def heuristic_validate(sim):
    """Perform heuristic validation based on known patterns."""
    raw_expression = sim.get("expression")
    expression = (
        raw_expression if isinstance(raw_expression, str)
        else (str(raw_expression) if raw_expression is not None else "")
    )
    sharpe = num(sim.get("sharpe")) or 0
    fitness = num(sim.get("fitness")) or 0
    turnover = num(sim.get("turnover")) or 0
    margin = num(sim.get("margin")) or 0
    health = sim.get("health") if isinstance(sim.get("health"), dict) else {}
    fields = extract_fields(expression)

    # Known noise trap indicators
    noise_indicators = []

    # 1. Check for derivative fields (known noise trap)
    derivative_fields = [
        "growth_potential_rank_derivative",
        "multi_factor_static_score_derivative",
        "acceleration_rank_derivative",
        "composite_factor_score_derivative",
    ]
    for df in derivative_fields:
        if df in expression.lower():
            noise_indicators.append(f"derivative_field:{df}")

    # 2. Check health indicators
    if health and not health.get("ok"):
        reasons = health.get("reasons", [])
        reasons = reasons if isinstance(reasons, list) else []
        for reason in reasons:
            if "CONCENTRATED_WEIGHT" in reason or "longCount" in reason:
                noise_indicators.append("concentrated_weight_fail")
            if "LOW_SUB_UNIVERSE_SHARPE" in reason:
                noise_indicators.append("low_sub_universe_sharpe_fail")

    # 3. Check turnover (extremely low = suspicious)
    if turnover < 0.15 and sharpe > 3.0:
        noise_indicators.append("extremely_low_turnover")

    # 4. Check longCount/shortCount distribution
    # These are not in simulation record but can be inferred
    # If CONCENTRATED_WEIGHT fails, likely extreme distribution

    # Determine validation status
    if len(noise_indicators) >= 2:
        status = "NOISE_TRAP"
        confidence = 0.9
    elif len(noise_indicators) == 1:
        status = "SUSPICIOUS"
        confidence = 0.7
    elif sharpe > 4.0 or fitness > 10.0:
        status = "SUSPICIOUS"
        confidence = 0.8
    else:
        status = "PROMISING"
        confidence = 0.5

    return {
        "status": status,
        "confidence": confidence,
        "noise_indicators": noise_indicators,
        "recommendation": _get_recommendation(status, noise_indicators),
    }


def _get_recommendation(status, indicators):
    """Get recommendation based on validation status."""
    if status == "NOISE_TRAP":
        return "标记为噪声陷阱，避免重用此字段族"
    elif status == "SUSPICIOUS":
        return "需要交叉验证：运行窗口步进+平滑+字段替换重跑"
    elif status == "PROMISING":
        return "保留为候选，继续探索"
    return "无需操作"


def apply_validation_rows(path, validation_by_id):
    """Stream source rows and attach only matching heuristic evidence."""
    for sim in iter_jsonl_objects(path):
        result = validation_by_id.get(sim.get("experiment_id"))
        if result is not None:
            # Keep production ``validation_status`` untouched. These are
            # static heuristics, not executed BRAIN evidence.
            sim["heuristic_validation_status"] = result["heuristic_status"]
            sim["heuristic_validation_confidence"] = result["confidence"]
            sim["heuristic_noise_indicators"] = result["noise_indicators"]
            sim["heuristic_recommendation"] = result["recommendation"]
            sim["heuristic_perturbation_plan"] = result["perturbations"]
        yield sim


def _validation_record(sim):
    """Build one compact heuristic record, or ``None`` for ordinary rows."""
    if not isinstance(sim, dict) or not sim.get("suspicious_high_signal"):
        return None
    result = heuristic_validate(sim)
    fields = sim.get("fields_used") if isinstance(sim.get("fields_used"), list) else []
    perturbations = generate_perturbations(
        sim.get("expression"), fields, max_perturbs=4
    )
    return {
        "experiment_id": sim.get("experiment_id"),
        "alpha_id": sim.get("alpha_id"),
        "round": sim.get("round"),
        "hypothesis_id": sim.get("hypothesis_id"),
        "expression": sim.get("expression"),
        "fields_used": fields,
        "original_metrics": {
            "sharpe": sim.get("sharpe"),
            "fitness": sim.get("fitness"),
            "turnover": sim.get("turnover"),
            "margin": sim.get("margin"),
        },
        "heuristic_status": result["status"],
        "evidence_level": "HEURISTIC_ONLY",
        "confidence": result["confidence"],
        "noise_indicators": result["noise_indicators"],
        "recommendation": result["recommendation"],
        "perturbations": [
            {"expression": p[0], "label": p[1]} for p in perturbations
        ],
    }


def _validation_priority(record):
    return (
        0 if record["heuristic_status"] == "NOISE_TRAP" else
        1 if record["heuristic_status"] == "SUSPICIOUS" else 2,
        -num(record.get("confidence")) if num(record.get("confidence")) is not None
        else 0,
    )


def _retain_validation_result(results, record, limit=MAX_VALIDATION_REPORT_RESULTS):
    """Keep a bounded report view without dropping source annotations."""
    results.append(record)
    results.sort(key=_validation_priority)
    del results[limit:]


def iter_annotated_validation_rows(path):
    """Recompute heuristic annotations while streaming the source once."""
    for sim in iter_jsonl_objects(path):
        record = _validation_record(sim)
        if record is not None:
            sim["heuristic_validation_status"] = record["heuristic_status"]
            sim["heuristic_validation_confidence"] = record["confidence"]
            sim["heuristic_noise_indicators"] = record["noise_indicators"]
            sim["heuristic_recommendation"] = record["recommendation"]
            sim["heuristic_perturbation_plan"] = record["perturbations"]
        yield sim


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(base_dir) == "scripts":
        base_dir = os.path.dirname(base_dir)
    data_dir = os.path.join(base_dir, "research_data")
    input_path = os.path.join(data_dir, "simulations_enhanced.jsonl")
    snapshot = os.path.getmtime(input_path)
    generated_at = datetime.fromtimestamp(snapshot, tz=timezone.utc)

    print("Streaming enhanced simulations...")
    # Validate high-signal items in one pass.  Keep the report evidence, but
    # do not retain a second full list containing the same source rows.
    validation_results = []
    status_counts = defaultdict(int)
    total_high_signal = 0
    for sim in iter_jsonl_objects(input_path):
        record = _validation_record(sim)
        if record is None:
            continue
        total_high_signal += 1
        status_counts[record["heuristic_status"]] += 1
        _retain_validation_result(validation_results, record)
    print(f"High signal items: {total_high_signal}")

    # Sort by confidence (highest first for NOISE_TRAP/SUSPICIOUS)
    # Save updated simulations
    output_path = os.path.join(data_dir, "simulations_validated.jsonl")
    atomic_write_jsonl_if_changed(
        output_path, iter_annotated_validation_rows(input_path)
    )
    print(f"\nUpdated simulations saved to: {output_path}")

    # Generate summary statistics
    print("\nValidation Summary:")
    print(f"  NOISE_TRAP: {status_counts.get('NOISE_TRAP', 0)}")
    print(f"  SUSPICIOUS: {status_counts.get('SUSPICIOUS', 0)}")
    print(f"  PROMISING:  {status_counts.get('PROMISING', 0)}")

    # Save validation report
    report = {
        "generated_at": generated_at.isoformat(),
        "total_high_signal": total_high_signal,
        "validation_breakdown": dict(status_counts),
        "results": validation_results,
        "results_retained": len(validation_results),
        "results_limit": MAX_VALIDATION_REPORT_RESULTS,
        "evidence_level": "HEURISTIC_ONLY",
    }

    report_path = os.path.join(data_dir, "validation_report.json")
    atomic_write_json_if_changed(
        report_path, report, ignored_keys=("generated_at",)
    )
    print(f"Validation report saved to: {report_path}")

    # Generate markdown summary
    lines = [
        "# High Signal Validation Report",
        "",
        f"**Generated**: {report['generated_at']}",
        f"**Total High Signal**: {total_high_signal}",
        "",
        "## Validation Breakdown",
        "",
        f"| Status | Count | Description |",
        f"|--------|-------|-------------|",
        f"| NOISE_TRAP | {status_counts.get('NOISE_TRAP', 0)} | 启发式噪声标记，未确认 |",
        f"| SUSPICIOUS | {status_counts.get('SUSPICIOUS', 0)} | 启发式疑似，需真实验证 |",
        f"| PROMISING | {status_counts.get('PROMISING', 0)} | 启发式保留，未形成平台结论 |",
        "",
        "## NOISE_TRAP Items (Heuristic Only)",
        "",
    ]

    noise_traps = (vr for vr in validation_results if vr["heuristic_status"] == "NOISE_TRAP")
    for i, vr in enumerate(islice(noise_traps, 10), 1):
        lines.extend([
            f"### {i}. {_short_text(vr['experiment_id'])} (Round {vr['round']})",
            "",
            f"- **Original**: S={_metric_text(vr['original_metrics']['sharpe'])} F={_metric_text(vr['original_metrics']['fitness'])}",
            f"- **Indicators**: {', '.join(vr['noise_indicators'])}",
            f"- **Recommendation**: {vr['recommendation']}",
            f"- **Expression**: `{_short_text(vr['expression'], 80)}...`",
            "",
        ])

    lines.extend([
        "## SUSPICIOUS Items (Need Validation)",
        "",
    ])

    suspicious = (vr for vr in validation_results if vr["heuristic_status"] == "SUSPICIOUS")
    for i, vr in enumerate(islice(suspicious, 10), 1):
        lines.extend([
            f"### {i}. {_short_text(vr['experiment_id'])} (Round {vr['round']})",
            "",
            f"- **Original**: S={_metric_text(vr['original_metrics']['sharpe'])} F={_metric_text(vr['original_metrics']['fitness'])}",
            f"- **Confidence**: {vr['confidence']:.0%}",
            f"- **Perturbations**: {len(vr['perturbations'])} generated",
            "",
        ])

    lines.extend([
        "## Next Actions",
        "",
        "1. **Run perturbations** for SUSPICIOUS items through the production proposal/checkpoint path",
        "2. **Do not archive or write avoid** from heuristic labels alone",
        "3. **Continue exploration** with PROMISING items",
        "",
    ])

    summary_path = os.path.join(data_dir, "VALIDATION_SUMMARY.md")
    atomic_write_text_if_changed(summary_path, "\n".join(lines))
    print(f"Validation summary saved to: {summary_path}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
