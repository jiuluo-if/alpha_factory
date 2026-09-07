"""Generate a human-readable research report from the agent state.

Reads .wqb_state/trajectory.jsonl + experience.json and writes
docs/archive/reports/RESEARCH_REPORT.md (or --output).

Usage:
    python scripts/generate_report.py [--state-dir .wqb_state] [--output docs/archive/reports/RESEARCH_REPORT.md]
"""

import argparse
import heapq
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.artifacts import atomic_write_text_if_changed, iter_jsonl_objects
from wqb_agent.metrics import num


def _safe_text(value, limit=None):
    text = str(value or "")
    return text[:limit] if limit is not None else text


def _load_json_object(path):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}, None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def iter_trajectory(path):
    """Compatibility wrapper around the shared JSONL reader."""
    yield from iter_jsonl_objects(path)


def state_snapshot_time(paths):
    """Use input-state mtime so an unchanged report remains byte-stable."""
    latest = 0
    for path in paths:
        try:
            latest = max(latest, os.path.getmtime(path))
        except OSError:
            continue
    return latest


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state-dir", default=".wqb_state")
    parser.add_argument("--output", default=os.path.join("docs", "archive", "reports", "RESEARCH_REPORT.md"))
    args = parser.parse_args()

    traj_path = os.path.join(args.state_dir, "trajectory.jsonl")
    exp_path = os.path.join(args.state_dir, "experience.json")

    # First collect only the hypothesis IDs that the report can display.  The
    # previous implementation retained an alpha mapping for every historical
    # experiment, even though only the first hypothesis per round is shown.
    hypothesis_by_round = {}
    experiment_count = 0
    for e in iter_trajectory(traj_path):
        experiment_count += 1
        round_no = e.get("round")
        if not hypothesis_by_round.get(round_no) and e.get("hypothesis_id"):
            hypothesis_by_round[round_no] = str(e.get("hypothesis_id"))

    display_hypothesis_ids = {
        hypothesis_id
        for hypothesis_id in hypothesis_by_round.values()
        if re.fullmatch(r"[a-f0-9]{12}", str(hypothesis_id or ""))
    }
    local_to_alpha = {}

    def _display_hyp(hid):
        """Show the platform alpha_id instead of a 12-hex local id."""
        if not hid:
            return ""
        hid = str(hid)
        if re.fullmatch(r"[a-f0-9]{12}", hid) and hid in local_to_alpha:
            return local_to_alpha[hid]
        return hid

    memory, memory_error = _load_json_object(exp_path)

    lines = []
    lines.append("# WQB 自进化研究报告")
    lines.append("")
    import datetime
    snapshot_time = state_snapshot_time((traj_path, exp_path))
    snapshot_label = (
        datetime.datetime.fromtimestamp(snapshot_time).isoformat(timespec="seconds")
        if snapshot_time else "unknown"
    )
    lines.append(f"- 状态快照时间：{snapshot_label}")
    lines.append(f"- 实验总数：{experiment_count}（append-only trajectory）")
    lines.append(f"- 记忆轮次：{memory.get('updated_round')}")
    if memory_error:
        lines.append(f"- 记忆文件读取失败：{memory_error}（本报告未将其视为研究结论）")
    lines.append("")

    # ---- best ----
    best = memory.get("current_best")
    lines.append("## 当前最佳（current_best）")
    if isinstance(best, dict) and best:
        m = best.get("metrics") if isinstance(best.get("metrics"), dict) else {}
        lines.append(f"- 表达式：`{_safe_text(best.get('expression'))}`")
        lines.append(f"- 字段：{best.get('fields_used')}")
        lines.append(f"- 指标：sharpe={m.get('sharpe')} fitness={m.get('fitness')} "
                     f"turnover={m.get('turnover')} returns={m.get('returns')} "
                     f"drawdown={m.get('drawdown')} margin={m.get('margin')} passed={m.get('passed')}")
    else:
        lines.append("- （无）")
    lines.append("")

    # ---- per-round stats ----
    by_round = defaultdict(lambda: {"count": 0, "statuses": Counter(), "hypothesis_id": ""})
    top_done = []
    sequence = 0
    for e in iter_trajectory(traj_path):
        sequence += 1
        local_id = _safe_text(e.get("id"))
        if local_id in display_hypothesis_ids and e.get("alpha_id"):
            local_to_alpha.setdefault(str(local_id), str(e.get("alpha_id")))
        round_no = e.get("round")
        stats = by_round[round_no]
        stats["count"] += 1
        stats["statuses"][e.get("status")] += 1
        if not stats["hypothesis_id"]:
            stats["hypothesis_id"] = e.get("hypothesis_id") or ""
        metrics = e.get("metrics") if isinstance(e.get("metrics"), dict) else {}
        fitness = num(metrics.get("fitness"))
        if metrics and fitness is not None:
            score = abs(fitness)
            item = (score, sequence, e)
            if len(top_done) < 15:
                heapq.heappush(top_done, item)
            elif item[:2] > top_done[0][:2]:
                heapq.heapreplace(top_done, item)
    lines.append("## 各轮次执行统计")
    lines.append("")
    lines.append("| 轮次 | 实验数 | DONE | UNKNOWN | FAILED | 假设 |")
    lines.append("|------|--------|------|---------|--------|------|")
    for r in sorted(by_round):
        stats = by_round[r]
        statuses = stats["statuses"]
        hyp = _display_hyp(stats["hypothesis_id"])
        lines.append(
            f"| {r} | {stats['count']} | {statuses.get('DONE', 0)} | "
            f"{statuses.get('UNKNOWN', 0)} | {statuses.get('FAILED', 0)} | {hyp} |"
        )
    lines.append("")

    # ---- top experiments by |fitness| ----
    done = [item[2] for item in sorted(top_done, key=lambda item: item[:2], reverse=True)]
    lines.append("## 关键实验（按 |Fitness| 排序，前 15）")
    lines.append("")
    lines.append("| 轮 | sharpe | fitness | turnover | returns | drawdown | margin | passed | 表达式 |")
    lines.append("|----|--------|---------|----------|---------|----------|--------|--------|--------|")
    for e in done[:15]:
        m = e["metrics"]
        lines.append(
            f"| {e.get('round')} | {m.get('sharpe')} | {m.get('fitness')} | {m.get('turnover')} "
            f"| {m.get('returns')} | {m.get('drawdown')} | {m.get('margin')} | {m.get('passed')} "
            f"| `{_safe_text(e.get('expression'), 60)}` |"
        )
    lines.append("")

    # ---- memory summary ----
    lines.append("## 记忆沉淀")
    lines.append("")
    lines.append(f"- lessons：{len(memory.get('lessons', []))} 条")
    lines.append(f"- avoid：{len(memory.get('avoid', []))} 条")
    lines.append(f"- next：{len(memory.get('next', []))} 条")
    seen_count = memory.get("seen_expressions_count")
    if seen_count is None:
        seen_count = len(memory.get("seen_expressions", []))
    lines.append(f"- seen_expressions：{seen_count} 条（有界热缓存；全历史去重以 trajectory 为准）")
    lines.append("")
    lines.append("### Top lessons")
    lessons = sorted(
        (item for item in memory.get("lessons", []) if isinstance(item, dict)),
        key=lambda item: -(num(item.get("evidence")) or 0.0),
    )[:8]
    for l in lessons:
        lines.append(f"- [ev={l.get('evidence')}] {_safe_text(l.get('claim'), 120)}")
    lines.append("")
    lines.append("### Top next ideas")
    nexts = sorted(
        (item for item in memory.get("next", []) if isinstance(item, dict)),
        key=lambda item: -(num(item.get("priority")) or 0.0),
    )[:6]
    for n in nexts:
        extra = ""
        if n.get("fields"):
            extra = f" fields={n['fields'][:3]}"
        if n.get("datasets"):
            extra += f" datasets={n['datasets'][:3]}"
        lines.append(f"- [p{n.get('priority')}] {_safe_text(n.get('idea'), 100)}{extra}")
    lines.append("")
    lines.append("### 假设分支状态")
    for h in memory.get("active_hypotheses", []) or []:
        if not isinstance(h, dict):
            continue
        lines.append(f"- [{h.get('status')}] {h.get('id')}: {_safe_text(h.get('statement'), 70)}")
    lines.append("")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    atomic_write_text_if_changed(args.output, "\n".join(lines))
    print(f"report written: {args.output} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
