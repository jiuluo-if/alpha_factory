# Phase 4：Correctness & Consolidation

本阶段不新增 Simulation 入口。唯一生产链仍为：

`--suggest → proposals.json → Agent.run_proposals() → Simulator → WQBClient`

## 权威事实源

- `trajectory.jsonl`：已进入执行链的 Experiment 事实；
- `trial_ledger.jsonl`：候选生命周期与搜索试验计数的 append-only 审计；
- `round_*.checkpoint.json`：未完成任务和恢复边界；
- `SearchSnapshot`：从上述事实源重建的只读投影，不是第四份状态；
- `SearchPolicy/BudgetAllocator`：仅内存决策层，不读写磁盘。

Allocator 状态为 `RESERVED → PENDING/RUNNING → DONE | FAILED | UNKNOWN | SKIPPED`。
前三种活动态以及 `UNKNOWN` 占用 arm 槽位；`DONE/FAILED/SKIPPED` 释放槽位；UNKNOWN 只有对账后才可终结。proposal 级 transition 可安全重放。

## Validation 与统计证据

`STABLE` 只表示预注册 plan 的 required robustness dimensions、yearly/platform quality 和父 Alpha 质量门均通过；它不等于统计置信度。统计输出另有 `statistical_status`：

- `UNAVAILABLE`：没有可信 return/PnL，不伪造 PSR/DSR/PBO；
- `APPROXIMATE`：DSR fallback 或 `pbo_proxy`，不能描述为严格论文复现；
- `PASS/FAIL`：有可用数据并完成相应诊断。

无适用实验必须在 plan 中写 `NOT_APPLICABLE` 与理由。`decay`、`truncation` 已作为独立变量预注册，不能把两者一次同时改变。
