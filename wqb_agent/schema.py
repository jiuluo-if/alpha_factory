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
ARTIFACT_SCHEMAS = {
    name: SCHEMA_VERSION for name in (
        TRAJECTORY_SCHEMA, TRIAL_LEDGER_SCHEMA, CHECKPOINT_SCHEMA,
        VALIDATION_SCHEMA, SUBMISSION_POOL_SCHEMA,
    )
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
