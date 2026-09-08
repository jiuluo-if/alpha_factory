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

from .expression import analyze_expression
from .metrics import score_of

_FIELD_TOKEN_RE = re.compile(r"[a-z0-9_]+")
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
