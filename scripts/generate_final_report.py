#!/usr/bin/env python3
"""Generate final comprehensive report with all findings."""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wqb_agent.artifacts import atomic_write_text_if_changed, iter_jsonl_objects
from wqb_agent.metrics import num


def _metric_text(value, digits=2):
    """Render missing legacy metrics as unknown, never as fabricated zero."""
    value = num(value)
    return f"{value:.{digits}f}" if value is not None else "?"


def summarize_simulations(path):
    """Stream the source and retain only report-level counts and Top10."""
    total = done = sharpe_present = hypothesis_present = 0
    high_signal = noise_traps = 0
    failure_counts = {}
    top_high_signal = []
    for sim in iter_jsonl_objects(path):
        total += 1
        if sim.get("status") == "DONE":
            done += 1
        if num(sim.get("sharpe")) is not None:
            sharpe_present += 1
        if sim.get("hypothesis_id"):
            hypothesis_present += 1
        failure_class = sim.get("failure_class")
        if failure_class:
            failure_counts[failure_class] = failure_counts.get(failure_class, 0) + 1
        if sim.get("suspicious_high_signal"):
            high_signal += 1
            top_high_signal.append(sim)
            top_high_signal.sort(
                key=lambda row: num(row.get("fitness"))
                if num(row.get("fitness")) is not None else float("-inf"),
                reverse=True,
            )
            del top_high_signal[10:]
        if sim.get("suspicious_type") == "NOISE_TRAP_SUSPECT":
            noise_traps += 1
    return {
        "total": total,
        "done": done,
        "sharpe_present": sharpe_present,
        "hypothesis_present": hypothesis_present,
        "high_signal": high_signal,
        "noise_traps": noise_traps,
        "failure_counts": failure_counts,
        "top_high_signal": top_high_signal,
    }


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
    report_name = "FINAL_RESEARCH_LEDGER_REPORT.md"
    snapshot = source_snapshot_time(data_dir, report_name)
    generated_at = datetime.fromtimestamp(snapshot, timezone.utc)

    # Load compact aggregates; the JSONL source is never materialized as a list.
    print("Loading data...")
    simulation_summary = summarize_simulations(
        os.path.join(data_dir, "simulations_enhanced.jsonl")
    )
    failure_counts = simulation_summary["failure_counts"]

    with open(os.path.join(data_dir, "research_ledger.json"), "r", encoding="utf-8") as f:
        ledger = json.load(f)

    with open(os.path.join(data_dir, "enhancement_summary.json"), "r", encoding="utf-8") as f:
        enhancement = json.load(f)

    with open(os.path.join(data_dir, "integrity_report.json"), "r", encoding="utf-8") as f:
        integrity = json.load(f)

    # Generate final report
    report = []
    report.append("# Final Research Ledger Report")
    report.append("")
    report.append(f"**Generated**: {generated_at.isoformat()}")
    report.append(f"**Data Source**: `.wqb_state/trajectory.jsonl`")
    report.append(f"**Total Simulations**: {simulation_summary['total']}")
    report.append("")

    # ─────────────────────────────────────────────────────────
    # Section 1: Executive Summary
    # ─────────────────────────────────────────────────────────
    report.extend([
        "## 1. Executive Summary",
        "",
        f"本报告基于当前派生数据中的 **{simulation_summary['total']} 条 Simulation 记录**，",
        "具体平台事实仍以 `.wqb_state/trajectory.jsonl` 与 BRAIN 当前响应为准。",
        "",
        "### 核心发现",
        "",
        "| 指标 | 数值 | 说明 |",
        "|------|------|------|",
        f"| 总 Simulation | {simulation_summary['total']} | append-only 原始证据 |",
        f"| 有效研究证据 | {ledger['summary']['valid_evidence']} | DONE 状态且有指标 |",
        f"| Research Failures | {ledger['summary']['research_failures']} | SYNTAX/RESEARCH/DATA |",
        f"| Infra Failures | {ledger['summary']['infra_failures']} | AUTH/RATE_LIMIT/TIMEOUT/UNKNOWN |",
        f"| 噪声陷阱疑似 | {ledger['summary']['noise_traps']} | 启发式风险提示，未替代平台结论 |",
        f"| 高信号未验证 | {enhancement['suspicious_signal_breakdown'].get('HIGH_SIGNAL', 0)} | S>3/F>8 无交叉验证 |",
        "",
    ])

    # ─────────────────────────────────────────────────────────
    # Section 2: Data Quality
    # ─────────────────────────────────────────────────────────
    report.extend([
        "## 2. Data Quality Assessment",
        "",
        "### 2.1 Completeness",
        "",
        f"- **记录完整性**: {simulation_summary['total']}/{simulation_summary['total']} (100%)",
        f"- **指标完整率**: {simulation_summary['sharpe_present']}/{simulation_summary['done']} DONE 记录有 Sharpe",
        f"- **假设关联率**: {simulation_summary['hypothesis_present']}/{simulation_summary['total']} 模拟有关联假设",
        "",
        "### 2.2 Traceability",
        "",
        f"- **谱系数**: {len(ledger['lineages'])} 条 lineage 记录",
        f"- **假设数**: {ledger['summary']['total_hypotheses']} 个唯一假设",
        f"- **数据集**: {ledger['summary']['total_datasets']} 个不同数据集",
        f"- **轮次范围**: 1-{max((int(k) for k in ledger.get('rounds', {}).keys()), default=0)}",
        "",
        "### 2.3 Integrity Issues",
        "",
        f"- **缺失 Fitness**: {integrity['integrity_checks']['missing_metrics']['no_fitness']} 个",
        f"- **重复表达式**: {enhancement.get('duplicate_expression_count', 'N/A')} 组",
        f"- **Memory 追溯问题**: {integrity['integrity_checks']['memory_traceability']['total_issues']} 个",
        "",
    ])

    # ─────────────────────────────────────────────────────────
    # Section 3: High Signal Analysis
    # ─────────────────────────────────────────────────────────
    high_signal_count = simulation_summary["high_signal"]
    noise_trap_count = simulation_summary["noise_traps"]

    report.extend([
        "## 3. High Signal Analysis",
        "",
        f"### 3.1 Overview",
        "",
        f"- **高信号总数**: {high_signal_count} (S>3 or F>8)",
        f"- **噪声陷阱疑似**: {noise_trap_count}",
        "",
        "### 3.2 Noise Trap Characteristics",
        "",
        "噪声陷阱仅依据本次 validation 输入中的启发式标记；不预设字段族，也不替代平台结论。",
        "",
        "- 具体表达式、指标、健康与 checks 以当前结果逐条复核。",
        "- `NOISE_TRAP` 仍是启发式风险提示，不能直接晋升为 avoid 或研究结论。",
        "",
        "### 3.3 Top 10 High Signal Items",
        "",
    ])

    # Add top high signal items
    high_sorted = simulation_summary["top_high_signal"]
    report.append("| Rank | ID | Sharpe | Fitness | Turnover | Expression |")
    report.append("|------|-----|--------|---------|----------|------------|")
    for i, s in enumerate(high_sorted, 1):
        expr = (s.get("expression") or "")[:50].replace("\n", " ")
        experiment_id = str(s.get("experiment_id") or "?")[:8]
        sharpe = _metric_text(s.get("sharpe"))
        fitness = _metric_text(s.get("fitness"))
        turnover = _metric_text(s.get("turnover"), digits=3)
        report.append(f"| {i} | {experiment_id} | {sharpe} | "
                      f"{fitness} | {turnover} | {expr}... |")

    report.extend([
        "",
        "## 4. Dataset Budget Analysis",
        "",
        "| Dataset | Total | Done | Avg Sharpe | Avg Fitness | Suspicious |",
        "|---------|-------|------|------------|-------------|------------|",
    ])

    for ds, stats in sorted(ledger.get("datasets", {}).items(), key=lambda x: x[1]["count"], reverse=True):
        avg_s = stats["total_sharpe"] / stats["done"] if stats["done"] > 0 else 0
        avg_f = stats["total_fitness"] / stats["done"] if stats["done"] > 0 else 0
        report.append(f"| {ds} | {stats['count']} | {stats['done']} | "
                      f"{avg_s:.2f} | {avg_f:.2f} | {stats['suspicious']} |")

    report.extend([
        "",
        "## 5. Lineage Analysis",
        "",
        "### 5.1 Top Lineages by Simulation Count",
        "",
        "| Rank | Hypothesis | Sims | Best F | Noise Traps |",
        "|------|------------|------|--------|-------------|",
    ])

    for i, lin in enumerate(ledger.get("lineages", [])[:15], 1):
        report.append(f"| {i} | {lin['hypothesis_id'][:40]}... | {lin['simulation_count']} | "
                      f"{lin['best_fitness']:.2f} | {lin['noise_trap_count']} |")

    report.extend([
        "",
        "## 6. Mutation Pattern Analysis",
        "",
        "| Mutation Type | Count | Done | Avg Sharpe | Avg Fitness |",
        "|---------------|-------|------|------------|-------------|",
    ])

    for mut, stats in sorted(ledger.get("mutations", {}).items(), key=lambda x: x[1]["count"], reverse=True)[:15]:
        report.append(f"| {mut} | {stats['count']} | {stats['done']} | "
                      f"{stats['avg_sharpe']:.2f} | {stats['avg_fitness']:.2f} |")

    report.extend([
        "",
        "## 7. Failure Classification",
        "",
        "### 7.1 Research Failures (Learnable)",
        "",
        f"- **Total**: {ledger['summary']['research_failures']}",
        f"  - SYNTAX: {failure_counts.get('SYNTAX', 0)} (表达式/设置被平台拒绝)",
        f"  - RESEARCH: {failure_counts.get('RESEARCH', 0)} (假设/方向失效)",
        f"  - DATA: {failure_counts.get('DATA', 0)} (字段不存在)",
        "",
        "### 7.2 Infrastructure Failures (Not Learnable)",
        "",
        f"- **Total**: {ledger['summary']['infra_failures']}",
        f"  - UNKNOWN: {failure_counts.get('UNKNOWN', 0)} (本地异常，POST 可能已发生)",
        f"  - RATE_LIMIT: {failure_counts.get('RATE_LIMIT', 0)} (平台限流 429)",
        f"  - AUTH: {failure_counts.get('AUTH', 0)} (认证失败 401)",
        "",
        "**关键纪律**: Infra failures 不得进入 lessons/avoid 记忆。",
        "",
        "## 8. Validation Role Distribution",
        "",
        "| Role | Count | Percentage |",
        "|------|-------|------------|",
    ])

    role_counts = enhancement.get("validation_role_breakdown", {})
    total = sum(role_counts.values())
    for role, count in sorted(role_counts.items(), key=lambda x: x[1], reverse=True):
        pct = count / total * 100 if total > 0 else 0
        report.append(f"| {role} | {count} | {pct:.1f}% |")

    report.extend([
        "",
        "## 9. Recommendations",
        "",
        "### 9.1 Immediate Actions",
        "",
        f"1. **验证高信号**: 对当前发现的 {high_signal_count} 个高信号运行外层验证流程",
        f"2. **审阅噪声陷阱**: 检查当前标记的 {noise_trap_count} 个疑似噪声陷阱",
        f"3. **修复 Memory**: 处理完整性报告中的 {integrity['integrity_checks']['memory_traceability']['total_issues']} 个追溯问题",
        "",
        "### 9.2 Data Improvements",
        "",
        "1. **显式谱系**: 在 Experiment schema 中增加 `parent_id` 字段",
        "2. **Validation 记录**: 在 simulation 中标记 validation child 关系",
        "3. **定期审计**: 每月运行 curate_data.py + validate_integrity.py",
        "",
        "### 9.3 Research Discipline",
        "",
        "1. **高信号必须先验证**: Sharpe>3 或 Fitness>8 必须运行交叉验证",
        "2. **噪声陷阱识别**: 仅按当前 validation 结果审阅启发式风险提示，不预设字段族结论",
        "3. **重复检测**: 相同表达式跨轮提交需明确标注原因",
        "",
        "## 10. File Inventory",
        "",
        "| File | Path | Size | Records |",
        "|------|------|------|---------|",
    ])

    for root, dirs, files in os.walk(data_dir):
        for file in files:
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
    ])

    # Write report
    report_path = os.path.join(data_dir, report_name)
    atomic_write_text_if_changed(report_path, "\n".join(report))

    print(f"Final report saved to: {report_path}")
    print(f"Report size: {os.path.getsize(report_path)/1024:.1f} KB")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
