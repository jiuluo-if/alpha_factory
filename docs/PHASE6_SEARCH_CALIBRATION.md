# Phase 6：Search Calibration & Budget Efficiency

本阶段只校准现有 SearchPolicy，不增加第二条 Simulation 路径，也不自动提交最终 Alpha。

## 生命周期恢复

`TrialLedger` 将候选尝试和 Simulation 生命周期分开记录：

- `candidate_generated`、`candidate_rejected`、`candidate_admitted` 只表示搜索证据；
- `simulation_committed`、`simulation_submitted`、`simulation_settled` 才能恢复 allocator 的预算、占用和失败分类。

因此，被拒候选、`BATCH_CAP` 和本地 commit 失败不会在重启后变成 `UNKNOWN` arm。`AUTH`、`RATE_LIMIT`、`TIMEOUT`、网络和服务端错误进入 `failed_infra`；真实机制失败才进入 `failed_research`。

## SearchOutcome 与 reward_v1

`wqb_agent.search_outcome.SearchOutcome` 是实验结果到搜索策略之间的窄接口。奖励不再直接使用 raw Fitness：

- 未知或基础设施失败：没有 reward，不进入 reward denominator；
- 已完成但质量门失败：显式 `0.0`；
- 有效完成：`0.25`；有信号：`0.50`；父子相对改进：至少 `0.70`；稳健性通过：至少 `0.85`；统计决策明确 PASS：`1.0`。

所有值由 `reward_v1` 限制在 `[0, 1]`。统计证据 unavailable 不会惩罚已经达到的稳健性阶段。父子比较只使用 Sharpe、Fitness、换手和回撤的方向性差异，不伪造行为新颖性。

## 预算职责

- EXPLORE/EXPLOIT 使用 discovery allocator 和 UCB；
- VALIDATION 使用受保护的 `validation_max_simulations`，不消费 discovery UCB quota；
- `factory.max_simulations >= search_policy.max_simulations >= research_allocation.max_simulations`，启动时不满足即 fail closed。

`CANDIDATE → BASELINE → PROMISING → EXPLOIT → ROBUSTNESS → STABLE` 的下一阶段和预算耗尽停止条件由 `staged_promotion()` 给出；每次只观察一个实验再决定下一次花费。

## 离线校准与 replay

`build_search_calibration()` 只读 ledger、trajectory 和 SearchOutcome，输出候选、评估、Promising/Stable、角色预算、失败率和每个有效结果的 Simulation 成本。

`SearchPolicyReplay` 在每一步只使用此前已经观察到的 reward；`calibrate_replay()` 只比较预声明的探索系数 `0.5/1.0/1.5` 和 family penalty `none/weak/current`，并同时输出 FIFO baseline。replay 不修改真实 ledger，也不参与生产提交。

可通过 `Agent.search_calibration_report()` 获取当前状态的只读效率报告。
