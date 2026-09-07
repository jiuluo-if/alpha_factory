# 阶段 3：搜索效率与 Alpha 多样性策略

## 调用链

`suggest → FieldDiscovery → AlphaFactory/CandidateBuilder → SearchPolicy.annotate → 生产预检 → SearchPolicy.accept → Simulator`

真实 Simulation 仍只能从 `main.py --suggest` 生成 canonical proposals 后，经
`main.py --run-proposals` 进入；`SearchPolicy` 不访问网络、不写状态，也不创建第二个提交入口。

## 三层 diversity

1. **Syntax diversity**：`structural_fingerprint` 将字段匿名化、数值窗口归一化，保留算子、括号和组合结构；`subtree_fingerprints` 用于重复子树惩罚。
2. **Empirical diversity**：有平台或测试提供的 returns/PnL 序列时计算池内最大、 中位和最近相关性；高相关候选的 incremental value 降低。没有序列时明确标记 `UNAVAILABLE`，不伪造相关性。
3. **Incremental novelty**：综合结构差异、字段重合和行为增量，写入提案的 `search_evidence` 与 `novelty_score`，供多目标排序和审计使用。

## BudgetAllocator 与分阶段分配

研究 arm 为 `dataset family × mechanism family`。`BudgetAllocator` 使用有界 UCB：

- 未完成、UNKNOWN、已预留都占用 arm 槽位，默认同一 arm 只允许一个待定任务；
- DONE 才累积 reward，UNKNOWN 不当作负收益；
- BASELINE 先探索，只有完成且通过质量门的 parent 才进入 EXPLOIT/ROBUSTNESS；最终仍由既有 validation/submission 手工门控；
- `SearchPolicy` 是可扩展外观，MCTS 暂不实现，避免在证据不足时增加复杂度。

Fitness 只作为辅助 reward/特征，不再单独决定候选。`pareto_front` 同时保留质量、换手、保证金、回撤和 novelty 之间的非支配折中。

## 验收

`tests/test_search_policy.py` 使用合成表达式、PnL 序列和 arm 状态验证：结构等价、语法不同但行为相同、缺失 PnL、Pareto 折中、pending 防轰炸以及 novelty 证据。没有真实 Simulation 或生产状态修改。
