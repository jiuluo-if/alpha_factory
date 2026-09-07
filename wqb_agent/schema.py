"""Central names and in-memory migrations for persistent artifacts."""

from __future__ import annotations

import copy

SCHEMA_VERSION = 1
CURRENT_SCHEMA_VERSION = SCHEMA_VERSION
CREATED_BY_VERSION = "alpha-factory"

TRAJECTORY_SCHEMA = "trajectory"
TRIAL_LEDGER_SCHEMA = "trial_ledger"
CHECKPOINT_SCHEMA = "checkpoint"
VALIDATION_SCHEMA = "validation"
SUBMISSION_POOL_SCHEMA = "submission_pool"
FIELDS_CACHE_SCHEMA = "fields_cache"
EVIDENCE_CACHE_SCHEMA = "evidence_cache"
ACTIVE_SNAPSHOT_SCHEMA = "active_snapshot"
TRAJECTORY_VERSION = 1
TRIAL_LEDGER_VERSION = 2
CHECKPOINT_VERSION = 1
VALIDATION_VERSION = 1
SUBMISSION_POOL_VERSION = 1
FIELDS_CACHE_VERSION = 1
EVIDENCE_CACHE_VERSION = 1
ACTIVE_SNAPSHOT_VERSION = 1
SIMULATION_RESULTS_VERSION = 1
MEMORY_VERSION = 2
SEARCH_SNAPSHOT_VERSION = 1
VALIDATION_PLAN_VERSION = 3
ARTIFACT_SCHEMAS = {
    TRAJECTORY_SCHEMA: TRAJECTORY_VERSION,
    TRIAL_LEDGER_SCHEMA: TRIAL_LEDGER_VERSION,
    CHECKPOINT_SCHEMA: CHECKPOINT_VERSION,
    VALIDATION_SCHEMA: VALIDATION_VERSION,
    SUBMISSION_POOL_SCHEMA: SUBMISSION_POOL_VERSION,
    FIELDS_CACHE_SCHEMA: FIELDS_CACHE_VERSION,
    EVIDENCE_CACHE_SCHEMA: EVIDENCE_CACHE_VERSION,
    ACTIVE_SNAPSHOT_SCHEMA: ACTIVE_SNAPSHOT_VERSION,
    "simulation_results": SIMULATION_RESULTS_VERSION,
    "memory": MEMORY_VERSION,
    "search_snapshot": SEARCH_SNAPSHOT_VERSION,
    "validation_plan": VALIDATION_PLAN_VERSION,
}


def migrate_artifact(kind, payload):
    """Migrate a mapping in memory; never writes the source artifact."""
    if not isinstance(payload, dict):
        raise ValueError("artifact must be an object")
    if kind not in ARTIFACT_SCHEMAS:
        raise ValueError("unknown artifact schema: %s" % kind)
    result = copy.deepcopy(payload)
    result["schema_version"] = ARTIFACT_SCHEMAS[kind]
    result.setdefault("created_by_version", CREATED_BY_VERSION)
    return result
