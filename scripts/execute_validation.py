#!/usr/bin/env python3
"""Execute cross-validation for SUSPICIOUS items."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.artifacts import atomic_write_json_if_changed

MAX_VALIDATION_JOBS = 256


def build_jobs(data):
    """Flatten valid heuristic plans without trusting malformed rows."""
    jobs = []
    for plan in (data.get("plans") or []) if isinstance(data, dict) else []:
        if not isinstance(plan, dict):
            continue
        for perturbation in plan.get("perturbations") or []:
            if not isinstance(perturbation, dict):
                continue
            expression = perturbation.get("expression")
            if not isinstance(expression, (str, int)) or not str(expression).strip():
                continue
            jobs.append({
                "parent_id": plan.get("experiment_id"),
                "parent_round": plan.get("round"),
                "expression": str(expression),
                "label": perturbation.get("label"),
                "type": perturbation.get("type"),
            })
            if len(jobs) >= MAX_VALIDATION_JOBS:
                return jobs
    return jobs

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "research_data")
    plan_path = os.path.join(data_dir, "suspicious_validation_plans.json")

    # Load validation plans
    try:
        with open(plan_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        print(f"[SKIP] validation plan not found or malformed: {plan_path}")
        return 0

    print(f"Loaded {len(data.get('plans') or []) if isinstance(data, dict) else 0} validation plans")

    # For each plan, generate simulation jobs
    jobs = build_jobs(data)

    print(f'Generated {len(jobs)} simulation jobs')

    # Save jobs for execution
    output_path = os.path.join(data_dir, "validation_jobs.json")
    atomic_write_json_if_changed(output_path, {"jobs": jobs, "total": len(jobs)})

    print(f"Saved to: {output_path}")

if __name__ == '__main__':
    main()
