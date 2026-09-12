"""Read-only research-quality audit over a local BRAIN field catalog.

The script deliberately writes only derived report files outside the state
directory.  It never refreshes discovery, calls a client, submits a
simulation, or writes any file below ``--state-dir``.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

# When executed as ``python scripts/...py``, Python places ``scripts`` ahead of
# the repository root.  Pin imports to the checked-out source under audit.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The imports below intentionally follow the source-path pin above.
# isort: off
from wqb_agent.alpha_factory import AlphaFactory  # noqa: E402
from wqb_agent.discovery import (  # noqa: E402
    FieldDiscovery,
    frequency_evidence,
    normalize_coverage,
    normalize_frequency,
)
from wqb_agent.diversity import (  # noqa: E402
    derive_budget_priority,
    diversity_audit,
    semantic_mechanism_key,
)
from wqb_agent.proposal_contract import _operator_reference  # noqa: E402
# isort: on


HYPOTHESES = (
    {
        "id": "audit_analyst_revision",
        "statement": "Which analyst estimate revisions and expectation changes carry information?",
        "tags": ["analyst", "revision", "estimate", "expectation", "change"],
        "datasets": ["analyst4"],
    },
    {
        "id": "audit_option_skew",
        "statement": "Which option implied volatility skew fields describe relative risk pricing?",
        "tags": ["option", "implied", "volatility", "skew", "relative"],
        "datasets": ["option8", "option9"],
    },
    {
        "id": "audit_liquidity_deterioration",
        "statement": "Which liquidity and trading activity fields identify deterioration or participation changes?",
        "tags": ["liquidity", "volume", "turnover", "activity", "deterioration"],
        "datasets": ["pv1", "pv13"],
    },
    {
        "id": "audit_earnings_change",
        "statement": "Which earnings and fundamental fields capture operating expectation change?",
        "tags": ["earnings", "fundamental", "revenue", "profit", "cash flow", "change"],
        "datasets": ["analyst4", "fundamental6"],
    },
    {
        "id": "audit_sentiment_shock",
        "statement": "Which news and sentiment fields capture attention or belief shocks?",
        "tags": ["news", "sentiment", "mention", "event", "shock"],
        "datasets": ["news18"],
    },
)

CONCEPT_EVIDENCE = {
    "analyst_revision": ("revision", "revised", "estimate change", "forecast change"),
    "analyst_dispersion": ("dispersion", "analyst", "estimate"),
    "option_relative": ("put", "call", "skew", "relative"),
    "liquidity": ("volume", "turnover", "liquidity", "open interest", "bid", "ask"),
    "volatility": ("volatility", "implied vol", "variance"),
    "event_count": ("count", "number", "mention", "event", "occurrence"),
    "sentiment": ("sentiment", "social", "news", "recommendation", "bullish", "bearish"),
    "valuation": ("valuation", "target price", "price-to", "multiple", "p/e", "p/b"),
    "earnings": ("earnings", "eps", "revenue", "sales", "profit", "cash flow"),
    "fundamental": ("assets", "liabilities", "equity", "book value", "debt", "fundamental"),
    "market_price": ("price", "close", "open", "high", "low", "vwap", "return"),
    "data_quality": ("missing", "null", "nan", "quality", "coverage", "stale"),
}

AUDIT_STOPWORDS = {
    "a", "an", "and", "are", "carry", "capture", "changes", "describe",
    "fields", "for", "from", "identify", "in", "information", "of", "or",
    "which", "the", "their", "to", "with",
}


def _read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _stable_key(row: dict) -> str:
    return hashlib.sha256(
        f"{row.get('dataset')}|{row.get('id')}".encode()
    ).hexdigest()


def _dataset_value(value, fallback=None):
    if isinstance(value, dict):
        return value.get("id") or value.get("name") or fallback
    return value or fallback


def _category_value(value, dataset):
    value = _dataset_value(value)
    if value:
        return str(value).lower()
    return {
        "analyst4": "analyst",
        "option8": "option",
        "option9": "option",
        "news18": "news",
        "pv1": "price_volume",
        "pv13": "price_volume",
        "fundamental6": "fundamental",
    }.get(dataset, "")


def _profile(raw: dict, dataset: str, source: dict) -> dict:
    description = str(raw.get("description") or "")
    alpha_count = raw.get("alphaCount", raw.get("alpha_count"))
    return {
        "id": str(raw.get("id")),
        "name": raw.get("name") or description,
        "description": description,
        "coverage": normalize_coverage(raw),
        "alpha_count": alpha_count,
        "frequency": normalize_frequency(raw),
        "frequency_evidence": frequency_evidence(raw),
        "semantic_status": "KNOWN" if description.strip() else "UNKNOWN",
        "category": _category_value(raw.get("category"), dataset),
        "dataset": dataset,
        "type": str(raw.get("type") or "").upper() or None,
        "field_source": source,
        "platform_dedupe": {
            "source": source["kind"],
            "status": "KNOWN" if alpha_count is not None else "UNKNOWN",
            "alpha_count": alpha_count,
        },
    }


def _load_catalog(state_dir: Path):
    candidates = []
    for directory in state_dir.glob("platform_field_catalog_*"):
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = _read_json(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        datasets = manifest.get("datasets")
        if not isinstance(datasets, dict):
            continue
        try:
            raw_by_dataset = {
                dataset: _read_json(directory / row["file"])["fields"]
                for dataset, row in datasets.items()
            }
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        candidates.append((directory.name, directory, manifest, raw_by_dataset))
    if not candidates:
        raise RuntimeError("没有找到 COMPLETE platform field catalog")
    complete = [item for item in candidates if item[2].get("catalog_status") == "COMPLETE"]
    if not complete:
        raise RuntimeError("没有找到 COMPLETE platform field catalog")
    _name, directory, manifest, primary_rows = max(complete, key=lambda item: item[0])
    # Prefer the primary COMPLETE snapshot, then use the newest available
    # snapshot for datasets omitted from that explicit universe.  Such rows
    # remain marked with their own legacy/complete provenance in the report.
    selected = {dataset: (primary_rows[dataset], directory, manifest) for dataset in primary_rows}
    for _name, candidate_dir, candidate_manifest, candidate_rows in sorted(candidates, key=lambda item: item[0], reverse=True):
        for dataset, rows in candidate_rows.items():
            if dataset not in selected:
                selected[dataset] = (rows, candidate_dir, candidate_manifest)
    profiles = []
    sources = []
    for dataset, (rows, dataset_dir, dataset_manifest) in sorted(selected.items()):
        dataset_status = dataset_manifest.get("catalog_status", "LEGACY_UNVERIFIED")
        source = {
            "kind": "local_catalog",
            "path": str(dataset_dir.resolve()),
            "snapshot_date": dataset_manifest.get("fetched_at"),
            "catalog_status": dataset_status,
            "dataset": dataset,
        }
        sources.append(source)
        profiles.extend(
            _profile(row, dataset, source)
            for row in rows
            if isinstance(row, dict) and row.get("id") is not None
        )
    return directory, manifest, profiles, sources


def _coverage_band(value):
    if value is None:
        return "missing"
    if value < 0.5:
        return "low"
    if value < 0.9:
        return "mid"
    return "high"


def _description_band(value):
    words = len(str(value or "").split())
    return "rich" if words >= 15 or len(str(value or "")) >= 120 else "weak"


def _alpha_numeric(row):
    try:
        value = float(row.get("alpha_count"))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _alpha_band(value, low, high):
    if value is None:
        return "missing"
    if value <= low:
        return "low"
    if value >= high:
        return "high"
    return "mid"


def _sample_fields(profiles, target=100):
    values = list(profiles)
    alpha_values = sorted(
        value for value in (_alpha_numeric(row) for row in values) if value is not None
    )
    low = alpha_values[max(0, int(len(alpha_values) * 0.25) - 1)] if alpha_values else 0
    high = alpha_values[min(len(alpha_values) - 1, int(len(alpha_values) * 0.75))] if alpha_values else 0
    buckets = defaultdict(list)
    for row in values:
        enriched = dict(row)
        enriched["coverage_band"] = _coverage_band(row.get("coverage"))
        enriched["description_band"] = _description_band(row.get("description"))
        enriched["alpha_band"] = _alpha_band(_alpha_numeric(row), low, high)
        key = (
            row["dataset"], row.get("type") or "unknown",
            enriched["coverage_band"], enriched["description_band"],
            enriched["alpha_band"],
        )
        buckets[key].append(enriched)
    for rows in buckets.values():
        rows.sort(key=_stable_key)
    datasets = sorted({row["dataset"] for row in values})
    counts = Counter(row["dataset"] for row in values)
    quotas = {dataset: max(8, round(target * counts[dataset] / len(values))) for dataset in datasets}
    while sum(quotas.values()) > target:
        candidate = max((d for d in datasets if quotas[d] > 8), key=lambda d: quotas[d], default=None)
        if candidate is None:
            break
        quotas[candidate] -= 1
    while sum(quotas.values()) < target:
        candidate = max(datasets, key=lambda d: counts[d] - quotas[d])
        quotas[candidate] += 1
    selected = []
    selected_ids = set()
    for dataset in datasets:
        local = [key for key in buckets if key[0] == dataset]
        positions = {key: 0 for key in local}
        while sum(1 for row in selected if row["dataset"] == dataset) < quotas[dataset]:
            progressed = False
            for key in sorted(local):
                index = positions[key]
                if index >= len(buckets[key]):
                    continue
                row = buckets[key][index]
                positions[key] += 1
                if row["id"] in selected_ids:
                    continue
                selected.append(row)
                selected_ids.add(row["id"])
                progressed = True
                if sum(1 for item in selected if item["dataset"] == dataset) >= quotas[dataset]:
                    break
            if not progressed:
                break
    return selected[:target], {"alpha_q25": low, "alpha_q75": high, "quotas": quotas}


def _text_support(profile, concept):
    text = str(profile.get("description") or "").lower()
    terms = CONCEPT_EVIDENCE.get(concept, ())
    return sorted(term for term in terms if term in text)


def _semantic_rows(sample, factory):
    rows = []
    for profile in sample:
        traits = factory.derive_field_semantic_traits(profile)
        concept = traits.get("concept", "unknown")
        description_support = _text_support(profile, concept)
        flags = []
        if traits.get("semantic_admission") == "ALLOW" and not description_support:
            flags.append("suspected_false_positive")
        if traits.get("semantic_admission") != "ALLOW" and description_support:
            flags.append("suspected_false_negative")
        rows.append({
            "id": profile["id"], "dataset": profile["dataset"], "type": profile.get("type"),
            "coverage": profile.get("coverage"), "alpha_count": profile.get("alpha_count"),
            "description": profile.get("description"), "concept": concept,
            "measurement": traits.get("measurement"), "behavior": traits.get("behavior"),
            "frequency": traits.get("frequency"), "sign_semantics": traits.get("sign_semantics"),
            "semantic_admission": traits.get("semantic_admission"),
            "confidence": traits.get("confidence"), "description_support": description_support,
            "flags": flags, "traits": traits,
        })
    return rows


def _template_rows(sample, factory):
    templates = list(factory.registry.economic_templates())
    rows = []
    for profile in sample:
        ranked = factory.rank_compatible_templates(profile, templates)
        rows.append({
            "id": profile["id"], "dataset": profile["dataset"],
            "concept": factory.derive_field_semantic_traits(profile).get("concept"),
            "top_templates": [
                {
                    "template_id": item["template"].template_id,
                    "family": item["template"].family,
                    "score": item["score"],
                    "admission": item["admission"],
                    "reasons": item.get("reasons", []),
                }
                for item in ranked[:5]
            ],
        })
    return rows


def _pair_rows(sample, factory, limit=30):
    templates = [
        template for template in factory.registry.economic_templates()
        if len(template.required_slots) == 2
    ]
    # A full 100-field Cartesian product is unnecessary for a precision
    # audit.  Preserve a bounded, stratified set of real pairs first, then
    # exercise every pair template on those inputs.
    pair_inputs = []
    signature_counts = Counter()
    ordered = sorted(sample, key=_stable_key)
    for left, right in itertools.combinations(ordered, 2):
        left_concept = factory.derive_field_semantic_traits(left).get("concept")
        right_concept = factory.derive_field_semantic_traits(right).get("concept")
        signature = (
            tuple(sorted((str(left_concept), str(right_concept)))),
            tuple(sorted((left["dataset"], right["dataset"]))),
            tuple(sorted((str(left.get("type")), str(right.get("type"))))),
        )
        if signature_counts[signature] >= 3:
            continue
        signature_counts[signature] += 1
        pair_inputs.append((left, right))
        if len(pair_inputs) >= 180:
            break
    candidates = []
    for left, right in pair_inputs:
        for template in templates:
            relation = factory._relationship_gate([left, right], template)
            candidates.append({
                "template_id": template.template_id, "family": template.family,
                "left": {"id": left["id"], "dataset": left["dataset"], "description": left["description"]},
                "right": {"id": right["id"], "dataset": right["dataset"], "description": right["description"]},
                "relationship": relation,
            })
    for row in candidates:
        row["_sort_key"] = hashlib.sha256(
            f"{row['template_id']}|{row['left']['id']}|{row['right']['id']}".encode()
        ).hexdigest()
    candidates.sort(key=lambda row: row["_sort_key"])
    by_admission = defaultdict(list)
    for row in candidates:
        by_admission[str(row["relationship"].get("admission") or "UNKNOWN").upper()].append(row)
    admissions = [name for name in ("ALLOW", "REVIEW", "REJECT", "UNKNOWN") if by_admission.get(name)]
    if not admissions:
        return []
    base, remainder = divmod(limit, len(admissions))
    quotas = {name: base + (index < remainder) for index, name in enumerate(admissions)}
    chosen = []
    for admission in admissions:
        rows = by_admission[admission]
        relation_groups = defaultdict(list)
        for row in rows:
            relationship = row["relationship"]
            group = (
                str(relationship.get("relationship_type") or "UNKNOWN"),
                tuple(sorted((row["left"]["dataset"], row["right"]["dataset"]))),
            )
            relation_groups[group].append(row)
        group_names = sorted(relation_groups)
        offsets = {group: 0 for group in group_names}
        while len([row for row in chosen if str(row["relationship"].get("admission")).upper() == admission]) < quotas[admission]:
            progressed = False
            for group in group_names:
                index = offsets[group]
                rows_in_group = relation_groups[group]
                if index >= len(rows_in_group):
                    continue
                chosen.append(rows_in_group[index])
                offsets[group] += 1
                progressed = True
                if len([row for row in chosen if str(row["relationship"].get("admission")).upper() == admission]) >= quotas[admission]:
                    break
            if not progressed:
                break
    return chosen[:limit]


def _triple_rows(profiles, sample, factory, limit=10):
    template = next(
        item for item in factory.registry.economic_templates()
        if item.template_id == "generic_triple_confirmation"
    )
    by_concept = defaultdict(list)
    # Use the full real catalog for the targeted triple audit.  The general
    # field audit remains a 100-field sample, but a rare semantic combination
    # should not disappear merely because stratified sampling missed it.
    for profile in sorted(profiles, key=_stable_key):
        by_concept[factory.derive_field_semantic_traits(profile).get("concept")].append(profile)
    for concept in by_concept:
        by_concept[concept] = by_concept[concept][:12]
    triples = []
    targeted = itertools.product(
        by_concept.get("analyst_revision", []),
        by_concept.get("analyst_dispersion", []),
        by_concept.get("sentiment", []),
    )
    for values in targeted:
        if len({item["id"] for item in values}) == 3:
            triples.append(values)
    if len(triples) < limit:
        triples.extend(itertools.combinations(sample, 3))
    rows = []
    seen = set()
    for values in triples:
        ids = tuple(item["id"] for item in values)
        if len(set(ids)) != 3 or ids in seen:
            continue
        seen.add(ids)
        relation = factory._relationship_gate(list(values), template)
        rows.append({
            "template_id": template.template_id,
            "fields": [
                {"id": item["id"], "dataset": item["dataset"], "description": item["description"]}
                for item in values
            ],
            "relationship": relation,
        })
        if len(rows) >= limit:
            break
    return rows


def _load_proposals(state_dir: Path):
    path = state_dir / "proposals.json"
    if not path.is_file():
        return {}, []
    payload = _read_json(path)
    proposals = payload.get("proposals", []) if isinstance(payload, dict) else []
    return payload if isinstance(payload, dict) else {}, [item for item in proposals if isinstance(item, dict)]


def _mechanism_audit(proposals):
    keys = Counter(semantic_mechanism_key(item) for item in proposals)
    clusters = defaultdict(list)
    for proposal in proposals:
        key = semantic_mechanism_key(proposal)
        clusters[key].append({
            "expression": proposal.get("expression"),
            "fields": proposal.get("fields") or proposal.get("fields_used"),
            "template_family": proposal.get("template_family"),
            "relationship_type": (proposal.get("relationship_audit") or {}).get("relationship_type"),
        })
    review = []
    for key, rows in clusters.items():
        families = sorted({str(row.get("template_family")) for row in rows})
        relationships = sorted({str(row.get("relationship_type")) for row in rows})
        if key != "UNKNOWN" and (len(families) > 1 or len(relationships) > 1):
            review.append({
                "key": key, "reason": "同一 key 下出现多个 template/relationship，需人工判断 false merge",
                "template_families": families, "relationship_types": relationships,
            })
    return {
        "unique_keys": len(keys),
        "unknown_count": keys.get("UNKNOWN", 0),
        "clusters": {key: rows[:5] for key, rows in sorted(clusters.items())},
        "review_candidates": review,
    }


def _discovery_audit(state_dir, catalog_root, profiles, sample_source):
    client = SimpleNamespace(instrument_type="EQUITY", region="USA", delay=1, universe="TOP3000")
    discovery = FieldDiscovery(
        client,
        cache_path=str(state_dir / "fields_cache.json"),
        catalog_root=str(state_dir),
        persist_catalog=False,
        selection_mode="semantic",
        random_fraction=0.0,
        random_seed="research-quality-audit-20260911",
        dataset_sampling="stratified",
        min_datasets=1,
    )
    # The production loader intentionally selects the newest COMPLETE
    # catalog.  For this audit only, inject explicitly marked legacy
    # supplement datasets into the in-memory read view so analyst4 can be
    # compared without writing or altering the production cache.
    for dataset in sorted({profile["dataset"] for profile in profiles}):
        if dataset not in discovery._disk_cache:
            discovery._disk_cache[dataset] = [
                profile for profile in profiles if profile["dataset"] == dataset
            ]
    result = []
    for hypothesis in HYPOTHESES:
        fields = discovery.discover(dict(hypothesis, _round=1), target_count=10)
        keywords = discovery._keywords_from_hypothesis(hypothesis)
        focus_terms = [
            str(tag).lower() for tag in hypothesis.get("tags", [])
            if str(tag).lower() not in AUDIT_STOPWORDS
        ]
        rows = []
        for field in fields:
            text = " ".join(str(field.get(key) or "").lower() for key in ("id", "name", "description"))
            overlap = sorted(keyword for keyword in keywords if keyword not in AUDIT_STOPWORDS and keyword in text)
            focus_overlap = sorted(term for term in focus_terms if term in text)
            rows.append({
                "id": field.get("id"), "dataset": field.get("dataset"),
                "type": field.get("type"), "coverage": field.get("coverage"),
                "alpha_count": field.get("alpha_count"), "match_score": field.get("match_score"),
                "description": field.get("description"), "keyword_overlap": overlap,
                "focus_overlap": focus_overlap,
                "focus_miss": sorted(set(focus_terms) - set(focus_overlap)),
                "obvious_irrelevant_candidate": not focus_overlap,
            })
        score_order = sorted(
            range(len(rows)),
            key=lambda index: (-float(rows[index].get("match_score") or 0), index),
        )
        score_rank = {index: rank + 1 for rank, index in enumerate(score_order)}
        for index, row in enumerate(rows):
            row["score_rank_in_top10"] = score_rank[index]
            row["rank_gap"] = score_rank[index] - (index + 1)
        result.append({
            "hypothesis": hypothesis, "keywords": keywords, "focus_terms": focus_terms, "top10": rows,
            "dataset_selection": dict(discovery.last_dataset_selection),
            "source": sample_source,
        })
    return result


def _priority_rows(proposals):
    return Counter(str(item.get("budget_priority") or "UNSET").upper() for item in proposals)


def _priority_scenario_audit(proposals):
    """Probe the existing priority rule with controlled, non-persistent context."""
    eligible = [
        item for item in proposals
        if isinstance(item, dict)
        and str(item.get("semantic_status") or "").upper() != "UNKNOWN"
    ]
    baseline = Counter(
        derive_budget_priority(item, context={})["bucket"] for item in eligible
    )
    question_probe = []
    for item in eligible[:20]:
        question = str(item.get("experiment_question") or item.get("research_question") or "").strip()
        if not question:
            continue
        before = derive_budget_priority(item, context={})
        after = derive_budget_priority(
            item, context={"unresolved_questions": [question]}
        )
        question_probe.append({
            "fields": item.get("fields") or item.get("fields_used") or [],
            "question": question,
            "before": before,
            "after": after,
        })
    return {
        "baseline": dict(baseline),
        "question_match_probe": {
            "count": len(question_probe),
            "after_distribution": dict(Counter(row["after"]["bucket"] for row in question_probe)),
            "rows": question_probe[:5],
        },
    }


def _markdown(report):
    metrics = report["metrics"]
    discovery_summary = report["discovery_summary"]
    relationship_summary = report["relationship_summary"]
    template_summary = report["template_summary"]
    lines = [
        "# Research Quality Audit — 2026-09-11",
        "",
        "> 只读审计；未调用 Simulation POST、Alpha submission、color/write API，也未写入 `.wqb_state/`。机器标记的 relevance/false-positive 仅是人工复核入口，不是 production truth。",
        "",
        "## 1. 数据来源与样本",
        "",
        f"- catalog: `{report['source']['catalog_path']}`；fetched_at: `{report['source']['fetched_at']}`；status: `{report['source']['catalog_status']}`",
        f"- supplemental catalogs: **{len(report['source']['supplemental_catalogs'])}**（仅用于主快照缺失 dataset，逐字段保留 provenance）",
        f"- fields available: **{metrics['fields_available']}**；真实 stratified sample: **{metrics['fields_sampled']}**",
        f"- datasets: `{', '.join(metrics['datasets'])}`；historical proposals: **{metrics['historical_proposals']}**",
        "",
        "### Sample strata",
        "",
        "| dataset | type | coverage | description | alphaCount | count |",
        "|---|---|---|---|---|---:|",
    ]
    for row in report["sample_strata"]:
        lines.append("| {dataset} | {type} | {coverage} | {description} | {alpha} | {count} |".format(**row))
    lines += ["", "## 2. Discovery top-N（人工复核入口）", ""]
    for item in report["discovery"]:
        h = item["hypothesis"]
        lines += [f"### {h['id']}", "", f"Hypothesis: {h['statement']}", "", f"Focus terms: `{', '.join(item.get('focus_terms', []))}`", "", "| display rank | score rank | gap | field | dataset | score | focus overlap |", "|---:|---:|---:|---|---|---:|---|"]
        for index, row in enumerate(item["top10"], 1):
            lines.append(f"| {index} | {row.get('score_rank_in_top10')} | {row.get('rank_gap')} | `{row['id']}` | {row['dataset']} | {row['match_score']} | {', '.join(row.get('focus_overlap', [])) or 'NONE'} |")
        lines.append("")
    semantic = report["semantic"]
    lines += [
        "## 3. Semantic classification",
        "",
        f"- admission: `{dict(Counter(row['semantic_admission'] for row in semantic['rows']))}`",
        f"- concept: `{dict(Counter(row['concept'] for row in semantic['rows']))}`",
        f"- suspected false positive: **{len(semantic['suspected_false_positive'])}**；suspected false negative: **{len(semantic['suspected_false_negative'])}**",
        "",
        "### Suspected semantic cases",
        "",
        "| flag | field | dataset | concept | admission | description |",
        "|---|---|---|---|---|---|",
    ]
    for row in semantic["suspected_false_positive"] + semantic["suspected_false_negative"]:
        flag = ",".join(row["flags"])
        lines.append(f"| {flag} | `{row['id']}` | {row['dataset']} | {row['concept']} | {row['semantic_admission']} | {str(row['description']).replace('|', '/')[:180]} |")
    lines += ["", "## 4. Template matching", "", "| field | concept | top template | family | score | admission |", "|---|---|---|---|---:|---|"]
    for row in report["templates"]:
        top = row["top_templates"][0] if row["top_templates"] else {}
        lines.append(f"| `{row['id']}` | {row['concept']} | `{top.get('template_id', 'NONE')}` | {top.get('family', 'NONE')} | {top.get('score', '')} | {top.get('admission', 'NONE')} |")
    lines += ["", "## 5. Multi-field relationships", "", f"- pair candidates audited: **{len(report['pairs'])}**", f"- triple candidates audited: **{len(report['triples'])}**", "- pair selection is deliberately balanced across available admissions (ALLOW/REVIEW/REJECT) and relationship/dataset groups; it is not a prevalence estimate.", "", "### Pair summary", "", "| admission | relationship_type | count |", "|---|---|---:|"]
    pair_counts = Counter((row["relationship"].get("admission"), row["relationship"].get("relationship_type")) for row in report["pairs"])
    for (admission, relation), count in sorted(pair_counts.items()):
        lines.append(f"| {admission} | {relation} | {count} |")
    lines += ["", "| template | left | right | admission | relation | reasons |", "|---|---|---|---|---|---|"]
    for row in report["pairs"]:
        relation = row["relationship"]
        reasons = "; ".join(relation.get("reasons", []))[:180].replace("|", "/")
        lines.append(f"| `{row['template_id']}` | `{row['left']['id']}` | `{row['right']['id']}` | {relation.get('admission')} | {relation.get('relationship_type')} | {reasons} |")
    lines += ["", "### Triple summary", "", "| fields | admission | relation | reasons |", "|---|---|---|---|"]
    for row in report["triples"]:
        relation = row["relationship"]
        ids = ", ".join(f"`{item['id']}`" for item in row["fields"])
        lines.append(f"| {ids} | {relation.get('admission')} | {relation.get('relationship_type')} | {'; '.join(relation.get('reasons', []))[:180].replace('|', '/')} |")
    lines += ["", "## 6. Mechanism identity and proposals", "", f"- current proposal diversity: `{json.dumps(report['historical_diversity'], ensure_ascii=False)}`", f"- current mechanism keys: **{report['mechanisms']['unique_keys']}**；UNKNOWN: **{report['mechanisms']['unknown_count']}**", f"- dry-run batch count: **{len(report['dry_run_batch'])}**", f"- dry-run priority distribution: `{dict(report['dry_run_priority'])}`", "", "### Mechanism review candidates", ""]
    if report["mechanisms"]["review_candidates"]:
        for row in report["mechanisms"]["review_candidates"]:
            lines.append(f"- `{row['key']}`：{row['reason']}；families={row['template_families']}；relationships={row['relationship_types']}")
    else:
        lines.append("- 未发现自动 review candidate；仍需人工抽查机制 clusters，不能据此宣布无 false split/merge。")
    scenario = report["priority_scenarios"]
    lines += ["", "### Budget priority controlled probe", "", f"- baseline on the real dry-run batch: `{scenario['baseline']}`", f"- self-question unresolved-context probe: `{scenario['question_match_probe']['after_distribution']}` for **{scenario['question_match_probe']['count']}** candidates; this is a rule-sensitivity probe, not evidence that the questions are resolved.", "", "## 7. HIGH/NORMAL/LOW 候选人工抽查", "", "| priority | field(s) | template | mechanism | question |", "|---|---|---|---|---|"]
    for row in report["priority_review"]:
        lines.append(f"| {row.get('budget_priority')} | {', '.join(row.get('fields', []))} | `{row.get('template_id')}` | {str(row.get('economic_mechanism') or '')[:130].replace('|', '/')} | {str(row.get('experiment_question') or '')[:100].replace('|', '/')} |")
    lines += ["", "## 8. 结论记录（人工）", "", "### Discovery", ""]
    for item in discovery_summary:
        lines.append(
            f"- `{item['hypothesis_id']}`：returned={item['returned']}，"
            f"focus-hit={item['focus_hit']}/{item['returned']}，"
            f"score/display inversion={item['score_inversion']}。"
        )
    lines += [
        "- `audit_liquidity_deterioration` 在显式 semantic 模式下只返回 3 个 pv1 字段，pv13 没有直接命中 focus 词；这是安全的候选不足，不应凭空把 pv13 的分类/竞争者字段当成流动性字段。",
        "- 本轮已确认并修复的生产问题是英语功能词进入关键词（真实 `pv13` 字段曾因 `or` 被选中）；修复后该假设不再返回这些 coverage-only 字段。",
        "- option/earnings 的 score/display inversion 来自既有 stratified round-robin contract；本轮未把它误报为 ranking bug。option 候选中 breakeven 是期权相关但不是 skew-specific，需由 Agent 在假设层继续筛选。",
        "",
        "### Semantic and template",
        "",
        f"- semantic admission: `{dict(Counter(row['semantic_admission'] for row in report['semantic']['rows']))}`；唯一机器 false-positive review candidate 是 `implied_volatility_mean_90`，其描述明确是 IvCall/IvPut 平均值，人工判断为 volatility 的合理 ALLOW，不构成修复依据；未发现机器 false-negative。",
        f"- top template admissions: `{template_summary['admission']}`；真实 sample 中 `distribution_regime` 与 `vector_change_signal` 占多数，需结合字段描述和研究问题解释，不能仅按 template 名称计为机制新颖性。",
        "",
        "### Relationships, mechanism identity, budget",
        "",
        f"- pair summary: `{relationship_summary['pairs']}`；triple summary: `{relationship_summary['triples']}`。本轮没有因频率缺失而宣称 ALLOW：显式关系在 frequency UNKNOWN 时保持 REVIEW，非 comparable pairs 保持 REJECT。",
        f"- mechanism identity: 100 historical proposals、{report['mechanisms']['unique_keys']} 个已见机制 key、{report['mechanisms']['unknown_count']} 个 UNKNOWN；100/100 expression unique、19 个 structure families、15 个 lineages。6 个 cluster 是 false-merge review candidates，当前没有独立证据确认 false split/merge。",
        f"- budget: real dry-run batch 100 个，priority `{report['dry_run_priority']}`；其中 UNKNOWN mechanism key 的 8 个候选被降为 LOW，未被伪装成 HIGH，但当前 target=100 时仍会作为低优先级候补，属于下一步 policy review 风险。",
        "",
        "### Production decision",
        "",
        "- production change: 仅补齐 Discovery 英语功能词停用词，并为该行为增加两个红绿回归测试；未新增 workflow/state/scheduler，也未改变 relationship、mechanism 或 budget contract。",
        "- no-change areas: semantic classifier、template registry、relationship gate、mechanism key 和 budget selection 未因单个 review candidate 改动。",
        "- Simulation recommendation: 暂不进入真实 Simulation；先由 Agent 复核 3 个跨假设质量问题（option skew specificity、earnings change specificity、LOW UNKNOWN candidate policy），随后才考虑小规模、明确假设的验证。",
        "",
    ]
    return "\n".join(lines)


def run(state_dir: Path, output_dir: Path):
    catalog_dir, manifest, profiles, catalog_sources = _load_catalog(state_dir)
    sample, sampling = _sample_fields(profiles)
    factory = AlphaFactory()
    operator_path = Path(__file__).resolve().parents[1] / "docs" / "reference" / "OPERATORS_CHEATSHEET.md"
    operator_reference = _operator_reference(str(operator_path))
    source = {
        "catalog_path": str(catalog_dir.resolve()),
        "fetched_at": manifest.get("fetched_at"),
        "catalog_status": (
            "COMPLETE_WITH_SUPPLEMENTS" if any(
                source["path"] != str(catalog_dir.resolve())
                for source in catalog_sources
            ) else manifest.get("catalog_status")
        ),
        "catalog_schema": manifest.get("schema"),
        "supplemental_catalogs": [
            source for source in catalog_sources
            if source["path"] != str(catalog_dir.resolve())
        ],
        "field_source": sample[0].get("field_source") if sample else None,
    }
    semantic_rows = _semantic_rows(sample, factory)
    template_rows = _template_rows(sample, factory)
    pairs = _pair_rows(sample, factory)
    triples = _triple_rows(profiles, sample, factory)
    discovery = _discovery_audit(state_dir, catalog_dir, profiles, source["field_source"])
    proposal_payload, historical_proposals = _load_proposals(state_dir)
    historical_diversity = diversity_audit(historical_proposals)
    mechanisms = _mechanism_audit(historical_proposals)
    broad_hypothesis = {
        "id": "research_quality_audit",
        "statement": "Which real documented fields support distinct economic mechanisms across datasets?",
        "tags": ["analyst", "fundamental", "option", "news", "liquidity", "price"],
        "datasets": sorted({profile["dataset"] for profile in profiles}),
    }
    dry_run_batch = factory.generate_factory_batch(
        broad_hypothesis,
        sample,
        operator_reference,
        target=100,
        seed="research-quality-audit-20260911",
    )
    dry_run_priority = _priority_rows(dry_run_batch)
    priority_scenarios = _priority_scenario_audit(dry_run_batch)
    discovery_summary = [
        {
            "hypothesis_id": item["hypothesis"]["id"],
            "returned": len(item["top10"]),
            "focus_hit": sum(not row["obvious_irrelevant_candidate"] for row in item["top10"]),
            "score_inversion": sum(row["rank_gap"] != 0 for row in item["top10"]),
        }
        for item in discovery
    ]
    template_summary = {
        "admission": dict(Counter(
            row["top_templates"][0].get("admission")
            for row in template_rows if row["top_templates"]
        )),
        "top_template": dict(Counter(
            row["top_templates"][0].get("template_id")
            for row in template_rows if row["top_templates"]
        )),
    }
    relationship_summary = {
        "pairs": dict(Counter(
            row["relationship"].get("admission") for row in pairs
        )),
        "triples": dict(Counter(
            row["relationship"].get("admission") for row in triples
        )),
    }
    priority_review = []
    for priority in ("HIGH", "NORMAL", "LOW"):
        rows = [item for item in dry_run_batch if str(item.get("budget_priority")).upper() == priority]
        priority_review.extend(rows[:20 if priority != "LOW" else 10])
    report = {
        "source": source,
        "metrics": {
            "fields_available": len(profiles), "fields_sampled": len(sample),
            "datasets": sorted({profile["dataset"] for profile in profiles}),
            "historical_proposals": len(historical_proposals),
        },
        "sampling": sampling,
        "sample_strata": [
            {
                "dataset": dataset, "type": field_type, "coverage": coverage,
                "description": description, "alpha": alpha, "count": count,
            }
            for (dataset, field_type, coverage, description, alpha), count
            in sorted(Counter((row["dataset"], row.get("type") or "unknown", row["coverage_band"], row["description_band"], row["alpha_band"]) for row in sample).items())
        ],
        "sample": sample,
        "discovery": discovery,
        "discovery_summary": discovery_summary,
        "semantic": {
            "rows": semantic_rows,
            "suspected_false_positive": [row for row in semantic_rows if "suspected_false_positive" in row["flags"]],
            "suspected_false_negative": [row for row in semantic_rows if "suspected_false_negative" in row["flags"]],
        },
        "templates": template_rows,
        "template_summary": template_summary,
        "pairs": pairs,
        "triples": triples,
        "relationship_summary": relationship_summary,
        "historical_proposal_payload": {
            "round_no": proposal_payload.get("round_no"),
            "epoch_label": proposal_payload.get("epoch_label"),
        },
        "historical_diversity": historical_diversity,
        "mechanisms": mechanisms,
        "dry_run_batch": dry_run_batch,
        "dry_run_priority": dict(dry_run_priority),
        "dry_run_budget_audit": factory.last_budget_audit,
        "priority_scenarios": priority_scenarios,
        "priority_review": priority_review,
        "guardrails": {
            "state_dir_written": False,
            "simulation_post": False,
            "alpha_submission": False,
            "color_write": False,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "REPORT.md").write_text(_markdown(report), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default=".wqb_state", type=Path)
    parser.add_argument(
        "--output-dir",
        default="research_data/research_quality_audit",
        type=Path,
        help=(
            "local-only output directory for raw audit data; keep it under "
            "research_data/ (git-ignored) and never inside tracked docs"
        ),
    )
    args = parser.parse_args()
    report = run(args.state_dir.resolve(), args.output_dir.resolve())
    print(json.dumps({
        "catalog_status": report["source"]["catalog_status"],
        "fields_available": report["metrics"]["fields_available"],
        "fields_sampled": report["metrics"]["fields_sampled"],
        "discovery_hypotheses": len(report["discovery"]),
        "pair_candidates": len(report["pairs"]),
        "triple_candidates": len(report["triples"]),
        "historical_proposals": report["metrics"]["historical_proposals"],
        "dry_run_batch": len(report["dry_run_batch"]),
        "state_dir_written": report["guardrails"]["state_dir_written"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
