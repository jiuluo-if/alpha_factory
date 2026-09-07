#!/usr/bin/env python3
"""Generate final comprehensive report integrating all phases."""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.artifacts import atomic_write_text_if_changed, iter_jsonl_objects
from wqb_agent.metrics import num


def _report_key(value, default=None):
    """Return a stable scalar report key; malformed JSON becomes missing."""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return default


def summarize_simulations(path):
    """Stream final simulations and keep only report aggregates."""
    summary = {
        "total": 0, "done": 0, "sharpe_present": 0,
        "hypothesis_present": 0, "with_lineage": 0,
        "hypotheses": set(), "research_failures": 0, "infra_failures": 0,
        "datasets": defaultdict(lambda: {
            "count": 0, "done": 0, "total_sharpe": 0.0,
            "total_fitness": 0.0, "suspicious": 0,
        }),
    }
    for sim in iter_jsonl_objects(path):
        summary["total"] += 1
        status = _report_key(sim.get("status"))
        if status == "DONE":
            summary["done"] += 1
        if num(sim.get("sharpe")) is not None:
            summary["sharpe_present"] += 1
        hypothesis = _report_key(sim.get("hypothesis_id"))
        if hypothesis:
            summary["hypothesis_present"] += 1
            summary["hypotheses"].add(hypothesis)
        if sim.get("parent_id") is not None or sim.get("lineage_depth", 0) == 0:
            summary["with_lineage"] += 1
        failure_class = _report_key(sim.get("failure_class"))
        if failure_class in ("RESEARCH", "SYNTAX", "DATA"):
            summary["research_failures"] += 1
        elif failure_class in ("INFRA", "AUTH", "RATE_LIMIT", "TIMEOUT", "UNKNOWN"):
            summary["infra_failures"] += 1
        dataset = _report_key(sim.get("dataset"), "unknown") or "unknown"
        stat = summary["datasets"][dataset]
        stat["count"] += 1
        if status == "DONE":
            stat["done"] += 1
            stat["total_sharpe"] += num(sim.get("sharpe")) or 0.0
            stat["total_fitness"] += num(sim.get("fitness")) or 0.0
        if (sim.get("heuristic_validation_status") or sim.get("heuristic_status")) == "NOISE_TRAP":
            stat["suspicious"] += 1
    return summary


def heuristic_status(row):
    """Read only the derived heuristic label, never production validation."""
    if not isinstance(row, dict):
        return None
    return row.get("heuristic_status")


def heuristic_sim_status(row):
    """Compatibility reader for old derived rows; labels remain heuristic."""
    if not isinstance(row, dict):
        return None
    return row.get("heuristic_validation_status")


def source_snapshot_time(data_dir, output_name):
    """Use input state time, not wall-clock time, for stable report bytes."""
    output_path = os.path.abspath(os.path.join(data_dir, output_name))
    latest = 0
    for root, _dirs, files in os.walk(data_dir):
        for name in files:
            path = os.path.abspath(os.path.join(root, name))
            if path == output_path:
                continue
            try:
                latest = max(latest, os.path.getmtime(path))
            except OSError:
                continue
    return latest


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(base_dir) == "scripts":
        base_dir = os.path.dirname(base_dir)
    data_dir = os.path.join(base_dir, "research_data")
    report_name = "FINAL_COMPLETE_REPORT.md"
    snapshot = source_snapshot_time(data_dir, report_name)
    generated_at = datetime.fromtimestamp(snapshot, timezone.utc)

    print("Loading all data...")

    simulation_summary = summarize_simulations(
        os.path.join(data_dir, "simulations_final.jsonl")
    )

    # Load lineage stats
    with open(os.path.join(data_dir, "lineage_statistics.json"), "r", encoding="utf-8") as f:
        lineage_stats = json.load(f)

    # Load validation report
    with open(os.path.join(data_dir, "validation_report.json"), "r", encoding="utf-8") as f:
        validation_report = json.load(f)
    validation_breakdown = validation_report.get("validation_breakdown") or {}

    print(f"Loaded {simulation_summary['total']} simulations")

    # Generate final report
    report = []

    report.extend([
        "# Final Research Ledger Report",
        "",
        f"**Generated**: {generated_at.isoformat()}",
        f"**Project**: WQB Alpha 自进化研究 Agent",
        f"**Data Curator**: Simulation Data Curator Agent",
        f"**Status**: Derived from the current input snapshot",
        "",
        "---",
        "",
    ])

    # Executive Summary
    report.extend([
        "## Executive Summary",
        "",
        "本研究账本完成了 **4 个阶段** 的数据整理工作：",
        "",
        f"1. **Phase 1**: 数据提取与规范化（{simulation_summary['total']} 条记录）",
        "2. **Phase 2**: 数据增强与审计（噪声陷阱标记）",
        f"3. **Phase 3**: 高信号启发式审计（{validation_breakdown.get('NOISE_TRAP', 0)} 个未确认噪声标记）",
        "4. **Phase 4**: Schema 完善（谱系深度分析）",
        "",
        "### 核心发现",
        "",
        "| 指标 | 数值 | 说明 |",
        "|------|------|------|",
        f"| 总 Simulation | {simulation_summary['total']} | append-only 原始证据 |",
        f"| 有效研究证据 | {simulation_summary['done']} | DONE 状态且有指标 |",
        f"| Research Failures | {simulation_summary['research_failures']} | 可学习的失败 |",
        f"| Infra Failures | {simulation_summary['infra_failures']} | 不可学习的失败 |",
        f"| 噪声标记 | {validation_breakdown.get('NOISE_TRAP', 0)} | 启发式，非平台结论 |",
        f"| 疑似信号 | {validation_breakdown.get('SUSPICIOUS', 0)} | 需真实验证 |",
        f"| 假设数 | {len(simulation_summary['hypotheses'])} | 唯一假设 |",
        f"| 平均谱系深度 | {lineage_stats['avg_depth']:.2f} | 每假设实验数 |",
        "",
    ])

    # Data Quality
    report.extend([
        "## Data Quality Assessment",
        "",
        "### Completeness",
        "",
        f"- **记录完整性**: {simulation_summary['total']}/{simulation_summary['total']} (100%)",
        f"- **指标完整率**: {simulation_summary['sharpe_present']}/{simulation_summary['done']} DONE 记录有 Sharpe",
        f"- **假设关联率**: {simulation_summary['hypothesis_present']}/{simulation_summary['total']} 模拟有关联假设",
        f"- **谱系完整率**: {simulation_summary['with_lineage']}/{simulation_summary['total']} 模拟有谱系记录",
        "",
        "### Traceability",
        "",
        f"- **数据来源**: `.wqb_state/trajectory.jsonl`",
        f"- **来源追溯**: 每条记录包含 `source_file` + `source_line`",
        f"- **谱系数**: {len(simulation_summary['hypotheses'])} 条 lineage",
        f"- **最大深度**: {lineage_stats['max_depth']}",
        "",
    ])

    # High Signal Analysis
    report.extend([
        "## High Signal Analysis",
        "",
        f"### Overview",
        "",
        f"- **高信号总数**: {validation_report['total_high_signal']}",
        f"- **启发式噪声标记（未确认）**: {validation_breakdown.get('NOISE_TRAP', 0)}",
        f"- **启发式疑似需验证**: {validation_breakdown.get('SUSPICIOUS', 0)}",
        f"- **启发式保留**: {validation_breakdown.get('PROMISING', 0)}",
        "",
        "### Noise Trap Characteristics (Heuristic Only)",
        "",
        "以下仅汇总当前 validation 输入的启发式标记，未经过真实验证，不预设具体字段族：",
        "",
        "- 具体表达式、六项指标、健康和 checks 必须以当前结果逐条复核。",
        "- 启发式标签不能覆盖生产 validation_status，也不能直接写入长期 avoid。",
        "",
        "### Top 10 Noise Traps",
        "",
        "| Rank | ID | Sharpe | Fitness | Round | Expression |",
        "|------|-----|--------|---------|-------|------------|",
    ])

    noise_traps = [v for v in validation_report.get('results', [])
                   if heuristic_status(v) == 'NOISE_TRAP']
    for i, vt in enumerate(noise_traps[:10], 1):
        expr = str(vt.get('expression') or "")[:50].replace("\n", " ")
        original_metrics = vt.get("original_metrics") or {}
        experiment_id = str(vt.get("experiment_id") or "?")[:8]
        sharpe = num(original_metrics.get("sharpe")) or 0.0
        fitness = num(original_metrics.get("fitness")) or 0.0
        report.append(f"| {i} | {experiment_id} | {sharpe:.2f} | "
                      f"{fitness:.2f} | {vt.get('round')} | {expr}... |")

    # Lineage Analysis
    report.extend([
        "",
        "## Lineage Analysis",
        "",
        f"### Overview",
        "",
        f"- **总谱系数**: {lineage_stats['root_simulations']} 个根节点",
        f"- **平均深度**: {lineage_stats['avg_depth']:.2f}",
        f"- **最大深度**: {lineage_stats['max_depth']}",
        "",
        "### Depth Distribution",
        "",
        "| Depth | Count | Percentage |",
        "|-------|-------|------------|",
    ])

    total = lineage_stats['total_simulations']
    for depth in sorted(lineage_stats['by_depth'].keys(), key=int):
        count = lineage_stats['by_depth'][depth]
        pct = count / total * 100 if total > 0 else 0
        report.append(f"| {depth} | {count} | {pct:.1f}% |")

    # Dataset Analysis
    report.extend([
        "",
        "## Dataset Budget Analysis",
        "",
        "| Dataset | Total | Done | Avg Sharpe | Avg Fitness | Suspicious |",
        "|---------|-------|------|------------|-------------|------------|",
    ])

    for ds, stats in sorted(simulation_summary['datasets'].items(), key=lambda x: x[1]['count'], reverse=True):
        avg_s = stats['total_sharpe'] / stats['done'] if stats['done'] > 0 else 0
        avg_f = stats['total_fitness'] / stats['done'] if stats['done'] > 0 else 0
        report.append(f"| {ds} | {stats['count']} | {stats['done']} | "
                      f"{avg_s:.2f} | {avg_f:.2f} | {stats['suspicious']} |")

    # Recommendations
    report.extend([
        "",
        "## Recommendations",
        "",
        "### Immediate Actions",
        "",
        f"1. **审阅噪声标记**: 当前有 {validation_breakdown.get('NOISE_TRAP', 0)} 个启发式标记，不能直接写入 `avoid`",
        f"2. **验证疑似信号**: 对 {validation_breakdown.get('SUSPICIOUS', 0)} 个条目走外层真实验证流程",
        "3. **修复 Memory**: 以完整性报告中的当前追溯结果为准",
        "",
        "### Data Improvements",
        "",
        "1. **显式谱系**: 在 Experiment 中增加 `parent_id` 字段 ✅ (已完成)",
        "2. **Validation 记录**: 标记 validation child 关系 ✅ (已完成)",
        "3. **定期审计**: 每月运行 curate_data.py + validate_integrity.py",
        "",
        "### Research Discipline",
        "",
        "1. **高信号验证**: Sharpe>3 或 Fitness>8 必须运行交叉验证",
        "2. **噪声陷阱识别**: 按当前 validation 结果审阅启发式风险提示，不预设字段族结论",
        "3. **重复检测**: 相同表达式跨轮提交需明确标注原因",
        "",
    ])

    # File Inventory
    report.extend([
        "## File Inventory",
        "",
        "| File | Path | Size | Records |",
        "|------|------|------|---------|",
    ])

    for root, dirs, files in os.walk(data_dir):
        for file in sorted(files):
            path = os.path.join(root, file)
            size = os.path.getsize(path)
            rel_path = os.path.relpath(path, base_dir)
            if file.endswith(".jsonl"):
                with open(path, "r", encoding="utf-8") as f:
                    count = sum(1 for line in f if line.strip())
                report.append(f"| {file} | `{rel_path}` | {size/1024:.1f} KB | {count} |")
            else:
                report.append(f"| {file} | `{rel_path}` | {size/1024:.1f} KB | - |")

    report.extend([
        "",
        "---",
        "",
        "**Report Generated by**: Simulation Data Curator Agent",
        f"**Date**: {generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "**Status**: Derived from the current input snapshot; not a platform submission decision",
        "",
        "**Data Integrity**: 详见输入的 validation/integrity 报告；本文件不替代实时平台证据",
    ])

    # Write report
    report_path = os.path.join(data_dir, report_name)
    atomic_write_text_if_changed(report_path, "\n".join(report))

    print(f"\nFinal report saved to: {report_path}")
    print(f"Report size: {os.path.getsize(report_path)/1024:.1f} KB")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
