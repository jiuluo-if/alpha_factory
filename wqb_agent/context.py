"""Compressed research context export (context.md).

Shared by the Agent (end of each round) and the memory maintenance
script (after a maintenance pass), so both always write the same format.
"""

import os

from .artifacts import atomic_write_text_if_changed
from .metrics import num


def _safe_text(value, limit=None):
    text = str(value or "")
    return text[:limit] if limit is not None else text


def key_experiments(experiments, n=10):
    """Pick the most informative finished experiments (by |fitness|)."""
    done = [e for e in experiments if isinstance(getattr(e, "metrics", None), dict)]
    done.sort(
        key=lambda e: abs(
            num(e.metrics.get("fitness"))
            or num(e.metrics.get("sharpe"))
            or 0.0
        ),
        reverse=True,
    )
    return [e.to_dict() for e in done[:n]]


def write_context(state_dir, memory, recent_experiments, context_experiments=10):
    """Write the compressed research context the model reads next round."""
    try:
        digest_size = max(0, int(context_experiments))
    except (TypeError, ValueError):
        digest_size = 10
    recent = key_experiments(recent_experiments, n=digest_size)
    ctx = memory.context(recent_experiments=recent)
    lines = ["# WQB 研究上下文（压缩记忆）", ""]
    lines.append(f"- 最近更新轮次：{memory.updated_round}")
    lines.append("")

    lines.append("## current_best")
    if ctx["current_best"]:
        b = ctx["current_best"]
        lines.append(f"- expression: `{_safe_text(b.get('expression'))}`")
        lines.append(f"- fields_used: {b.get('fields_used')}")
        lines.append(f"- datasets: {b.get('datasets')}")
        lines.append(f"- metrics: {b.get('metrics')}")
    else:
        lines.append("- (none)")
    lines.append("")

    lines.append("## active_hypotheses")
    for h in ctx["active_hypotheses"] or []:
        lines.append(f"- [{h.get('status')}] {h.get('id')}: {_safe_text(h.get('statement'), 120)}")
    lines.append("")

    lines.append("## short_term（短期记忆：最近几轮现场，过期自动晋升/回收）")
    for e in ctx["short_term"] or []:
        lines.append(
            f"- [{e.get('kind')} r{e.get('round')} hits={e.get('hits', 1)}] "
            f"{_safe_text(e.get('text'), 150)}"
        )
    if not ctx["short_term"]:
        lines.append("- (none)")
    lines.append("")

    lines.append("## recent_key_experiments")
    for e in ctx["recent_key_experiments"] or []:
        m = e.get("metrics") or {}
        lines.append(
            f"- {e.get('round')} {e.get('status')} sharpe={m.get('sharpe')} "
            f"fitness={m.get('fitness')} turnover={m.get('turnover')} "
            f"drawdown={m.get('drawdown')} `{_safe_text(e.get('expression'), 90)}`"
        )
    lines.append("")

    lines.append("## lessons")
    for lesson in ctx["lessons"] or []:
        lines.append(
            f"- [ev={lesson.get('evidence')},cf={lesson.get('confidence')}] "
            f"{lesson.get('claim')}"
        )
    lines.append("")

    lines.append("## avoid")
    for item in ctx["avoid"] or []:
        lines.append(f"- `{_safe_text(item.get('direction'), 80)}`: {_safe_text(item.get('reason'))}")
    lines.append("")

    lines.append("## next experiments")
    for idea in ctx["next"] or []:
        extra = ""
        if idea.get("fields"):
            extra = f" fields={idea['fields'][:3]}"
        if idea.get("datasets"):
            extra += f" datasets={idea['datasets'][:3]}"
        lines.append(
            f"- [p{idea.get('priority')}] {_safe_text(idea.get('idea'))}{extra}"
        )
    lines.append("")

    gdigest = ctx.get("garbage_digest") or {}
    gstats = gdigest.get("stats") or {}
    lines.append("## garbage（垃圾记忆：软删除墓碑，可恢复；超龄由维护脚本清除）")
    lines.append(f"- total={gstats.get('total', 0)} by_reason={gstats.get('by_reason', {})}")
    for t in (gdigest.get("recent") or [])[:3]:
        entry = t.get("entry") or {}
        snippet = ""
        if t.get("kind") == "lesson":
            snippet = entry.get("claim", "")
        elif t.get("kind") == "avoid":
            snippet = entry.get("direction", "")
        elif t.get("kind") == "short_term":
            snippet = entry.get("text", "")
        lines.append(
            f"- [{t.get('kind')} reason={t.get('reason')} r{t.get('moved_round')}] "
            f"{_safe_text(snippet, 100)}"
        )
    lines.append("")

    path = os.path.join(state_dir, "context.md")
    atomic_write_text_if_changed(path, "\n".join(lines))
    return path
