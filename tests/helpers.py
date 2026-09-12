"""Shared synthetic builders for the test suite.

Builders create synthetic evidence only: no real research exports, no network
access and no `.wqb_state` mutation.
"""

import datetime as dt
import os


def utc_timestamp(value):
    return value.replace(tzinfo=dt.UTC).timestamp()


def diversity_proposal(expression, *, concept="fundamental", measurement="level",
                       behavior="slow_moving", template_family="persistent_level",
                       dataset="fundamental6", lineage_id=None, layer="exploration",
                       relationship_type=None):
    traits = {
        "concept": concept, "measurement": measurement, "behavior": behavior,
        "status": "KNOWN" if concept != "unknown" else "UNKNOWN",
    }
    item = {
        "expression": expression,
        "template_family": template_family,
        "research_layer": layer,
        "field_analysis": {"field": {"semantic_traits": traits}},
        "field_refs": [{"id": "field", "dataset": dataset}],
        "datasets": [dataset],
    }
    if lineage_id is not None:
        item["lineage_id"] = lineage_id
    if relationship_type is not None:
        item["relationship_audit"] = {"relationship_type": relationship_type}
    return item


def proposal(index, origin="factory"):
    return {
        "expression": f"rank(field_{index})",
        "proposal_origin": origin,
        "fields": [f"field_{index}"],
    }


def operator_reference():
    root = os.path.dirname(os.path.dirname(__file__))
    from wqb_agent.proposal_contract import _operator_reference

    return _operator_reference(
        os.path.join(root, "docs", "reference", "OPERATORS_CHEATSHEET.md")
    )


def semantic_field(field_id, description, *, dataset="research1",
                   frequency="daily", category=None):
    return {
        "id": field_id,
        "name": description,
        "description": description,
        "dataset": dataset,
        "type": "MATRIX",
        "frequency": frequency,
        "category": category or "market",
        "coverage": 0.9,
        "semantic_status": "KNOWN",
    }
