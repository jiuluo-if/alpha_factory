"""Alpha 多样性 / 信号族冗余检查（从远程 Self-Evolution-wqb 参考实现吸收）。

对应本地 AGENTS.md §6 的候选相关性比对纪律的代码化：

1. 精确字段提取：从表达式里提取「实际用到」的字段（最长 id 优先，避免
   ``returns`` 与 ``returns_5d`` 的前缀误报）。提交池/ACTIVE 比对必须用
   实际字段（含辅助腿），不能用 discovery 的候选清单。
2. 相似度：表达式 token Jaccard、字段集合 Jaccard、假设标签 Jaccard。
3. 冗余判定：字段 + 表达式双重相似度达标即判定冗余（可调阈值）。
4. 提交池去重：保留每组最高分，丢弃近重复。

注意：平台 SELF_CORRELATION 是「与已提交 ACTIVE 池的相关性」，本地只能
用字段/信号族比对粗估（AGENTS.md §6 纪律）；本模块是粗估工具，不是
提交资格判定。
"""

import re
from collections import Counter

from .expression import analyze_expression
from .metrics import score_of

_FIELD_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _clean(value):
    value = str(value or "").strip().lower()
    return value if value and value not in {"unknown", "none", "null"} else "unknown"


def _is_known_traits(traits):
    return isinstance(traits, dict) and (
        str(traits.get("status") or "").upper() == "KNOWN"
        or str(traits.get("semantic_admission") or "").upper() == "ALLOW"
    ) and _clean(traits.get("concept")) != "unknown"


def _proposal_traits(proposal):
    if not isinstance(proposal, dict):
        return []
    traits = []
    analyses = proposal.get("field_analysis") or {}
    if isinstance(analyses, dict):
        for value in analyses.values():
            if isinstance(value, dict) and isinstance(value.get("semantic_traits"), dict):
                traits.append(value["semantic_traits"])
    if traits:
        return traits
    basis = proposal.get("field_hypothesis_basis") or {}
    if isinstance(basis, dict):
        for value in basis.values():
            if isinstance(value, dict) and isinstance(value.get("semantic_traits"), dict):
                traits.append(value["semantic_traits"])
    return traits


def semantic_mechanism_key_from_traits(traits, template_family=None,
                                       relationship_type=None):
    """Build a coarse mechanism identity from derived semantic evidence.

    Field IDs and free-form economic-mechanism prose are intentionally absent:
    changing either must not manufacture semantic diversity.
    """
    traits = [item for item in (traits or []) if isinstance(item, dict)]
    known = [item for item in traits if _is_known_traits(item)]
    if not known or len(known) != len(traits):
        return "UNKNOWN"
    concepts = sorted({
        ":".join(_clean(item.get(key)) for key in ("concept", "measurement", "behavior"))
        for item in known
    })
    relationship = _clean(relationship_type)
    if len(concepts) > 1 or relationship != "unknown":
        return f"{'+'.join(concepts)}:{relationship}"
    return concepts[0]


def semantic_mechanism_key(proposal):
    """Return a stable semantic key for one proposal, or ``UNKNOWN``."""
    if not isinstance(proposal, dict):
        return "UNKNOWN"
    explicit = proposal.get("semantic_mechanism_family")
    if isinstance(explicit, str) and _clean(explicit) != "unknown":
        return explicit.strip().lower()
    audit = proposal.get("relationship_audit") or {}
    return semantic_mechanism_key_from_traits(
        _proposal_traits(proposal),
        proposal.get("template_family") or proposal.get("template_id"),
        audit.get("relationship_type") if isinstance(audit, dict) else None,
    )


def structural_family_key(proposal):
    if not isinstance(proposal, dict):
        return "UNKNOWN"
    return _clean(proposal.get("template_family") or proposal.get("template_id"))


def field_concept_keys(proposal):
    return {
        _clean(item.get("concept"))
        for item in _proposal_traits(proposal)
        if _is_known_traits(item)
    }


def _lineage_key(proposal):
    if not isinstance(proposal, dict):
        return None
    for key in ("lineage_id", "parent_id", "hypothesis_id"):
        value = proposal.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    provenance = proposal.get("optimizer_provenance")
    if isinstance(provenance, dict):
        for key in ("lineage_id", "parent_id", "hypothesis_id"):
            value = provenance.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()
    return None


def _share(counter):
    total = sum(counter.values())
    if not total:
        return None
    return max(counter.values()) / total


def _dominant(counter):
    return counter.most_common(1)[0][0] if counter else None


def _audit_subset(proposals):
    expressions = {
        str(proposal.get("expression")).strip()
        for proposal in proposals
        if isinstance(proposal, dict) and str(proposal.get("expression") or "").strip()
    }
    structures = Counter(structural_family_key(item) for item in proposals)
    mechanisms = Counter(semantic_mechanism_key(item) for item in proposals)
    known_mechanisms = Counter({key: value for key, value in mechanisms.items()
                                if key != "UNKNOWN"})
    concepts = set()
    unknown_concepts = 0
    datasets = set()
    lineage_keys = set()
    for proposal in proposals:
        traits = _proposal_traits(proposal)
        known_traits = [item for item in traits if _is_known_traits(item)]
        concepts.update(_clean(item.get("concept")) for item in known_traits)
        unknown_concepts += len(traits) - len(known_traits) if traits else 1
        for value in proposal.get("datasets") or [] if isinstance(proposal, dict) else []:
            if value is not None and str(value).strip():
                datasets.add(str(value).strip())
        lineage = _lineage_key(proposal)
        if lineage is not None:
            lineage_keys.add(lineage)
    warnings = []
    if _share(known_mechanisms) is not None and _share(known_mechanisms) > 0.4:
        warnings.append("MECHANISM_CONCENTRATED")
    if _share(structures) is not None and _share(structures) > 0.4:
        warnings.append("STRUCTURE_CONCENTRATED")
    if lineage_keys:
        lineage_counter = Counter(_lineage_key(item) for item in proposals if _lineage_key(item))
        if _share(lineage_counter) > 0.4:
            warnings.append("LINEAGE_CONCENTRATED")
    lineage_counter = Counter(_lineage_key(item) for item in proposals if _lineage_key(item))
    result = {
        "proposal_count": len(proposals),
        "expression": {"unique_count": len(expressions),
                        "diversity_ratio": len(expressions) / len(proposals) if proposals else 0.0},
        "structure": {"unique_family_count": len(structures),
                       "dominant_family": _dominant(structures),
                       "dominant_share": _share(structures)},
        "semantic": {"known_mechanism_count": len(known_mechanisms),
                      "unknown_mechanism_count": mechanisms.get("UNKNOWN", 0),
                      "dominant_mechanism": _dominant(known_mechanisms),
                      "dominant_share": _share(known_mechanisms)},
        "field_concepts": {"unique_known_count": len(concepts),
                            "unknown_count": unknown_concepts},
        "datasets": {"unique_count": len(datasets)},
        "lineages": {"unique_independent_count": len(lineage_keys),
                      "unknown_count": len(proposals) - sum(lineage_counter.values()),
                      "dominant_lineage_share": _share(lineage_counter)},
        "warnings": warnings,
    }
    result["dominant_mechanism"] = result["semantic"]["dominant_mechanism"]
    result["dominant_mechanism_share"] = result["semantic"]["dominant_share"]
    result["dominant_structure"] = result["structure"]["dominant_family"]
    result["dominant_structure_share"] = result["structure"]["dominant_share"]
    return result


def diversity_audit(proposals):
    """Compute one-pass, deterministic semantic diversity statistics."""
    items = [item for item in (proposals or []) if isinstance(item, dict)]
    result = _audit_subset(items)
    layers = {}
    for layer in ("optimization", "exploration"):
        subset = [item for item in items
                  if str(item.get("research_layer") or "").lower() == layer]
        audit = _audit_subset(subset)
        layers[layer] = {
            "count": len(subset),
            "mechanism_count": audit["semantic"]["known_mechanism_count"],
            "lineage_count": audit["lineages"]["unique_independent_count"],
            "field_concept_count": audit["field_concepts"]["unique_known_count"],
        }
    result["layers"] = layers
    return result
def extract_fields(expression, known_fields):
    r"""返回表达式里实际出现的 known_fields 子集。

    按 id 长度降序匹配，保证 ``returns`` 不会因 ``returns_5d`` 的前缀
    关系产生误报；边界用 (?<!\w)(?!\w) 防止把 ``returns`` 匹配进
    ``returns_5d``。
    """
    known_fields = [
        str(field) for field in (known_fields or [])
        if isinstance(field, (str, int)) and str(field)
    ]
    found = set(analyze_expression(expression, known_fields).fields)
    return [field for field in sorted(set(known_fields), key=len, reverse=True) if field in found]


def expression_tokens(expr):
    """把表达式切成 token（操作符/字段/数字），用于结构相似度。"""
    return [t for t in _FIELD_TOKEN_RE.findall(str(expr or "")) if t]


def expression_similarity(a, b):
    """表达式 token 的 Jaccard 相似度。"""
    ta = set(expression_tokens(a))
    tb = set(expression_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def field_similarity(fields_a, fields_b):
    """字段集合的 Jaccard 相似度（字段级重合粗估）。"""
    fa = {str(field) for field in (fields_a or []) if isinstance(field, (str, int))}
    fb = {str(field) for field in (fields_b or []) if isinstance(field, (str, int))}
    if not fa or not fb:
        return 0.0
    return len(fa & fb) / len(fa | fb)


def hypothesis_similarity(h1_tags, h2_tags):
    """假设标签的 Jaccard 相似度。"""
    ta = {str(tag) for tag in (h1_tags or []) if isinstance(tag, (str, int))}
    tb = {str(tag) for tag in (h2_tags or []) if isinstance(tag, (str, int))}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _record_fields(rec):
    if isinstance(rec, dict):
        return rec.get("fields_used") or []
    return getattr(rec, "fields_used", [])


def _record_expr(rec):
    if isinstance(rec, dict):
        return rec.get("expression") or ""
    return getattr(rec, "expression", "")


def _record_score(rec):
    """记录统一评分（复用 metrics.score_of）。"""
    metrics = rec.get("metrics") if isinstance(rec, dict) else getattr(rec, "metrics", None)
    return score_of(metrics)


def is_redundant(record, pool_records, expr_th=0.6, field_th=0.5):
    """record 是否与池中某条近重复（字段 + 表达式双重相似度都达标）。

    返回 (True, keeper) 或 (False, None)。
    """
    for rec in pool_records:
        fs = field_similarity(_record_fields(record), _record_fields(rec))
        ts = expression_similarity(_record_expr(record), _record_expr(rec))
        if fs >= field_th and ts >= expr_th:
            return True, rec
    return False, None


def deduplicate(pool_records, expr_th=0.6, field_th=0.6):
    """提交池去重：按分数降序保留每组最高分，其余丢弃。"""
    kept = []
    dropped = []
    for rec in sorted(pool_records, key=_record_score, reverse=True):
        redundant, _ = is_redundant(rec, kept, expr_th=expr_th, field_th=field_th)
        if redundant:
            dropped.append(rec)
        else:
            kept.append(rec)
    return kept, dropped
