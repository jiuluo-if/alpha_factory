# Phase 5：决策语义与预算完整性

本阶段把搜索、试验账本和稳定性验证收敛为可恢复的研究决策系统。生产 Simulation 仍只有 `Agent.run_proposals()` 一条提交链；本文只描述状态和证据语义，不代表平台实时状态。

## 候选与试验身份

- `candidate_id` 在候选第一次进入研究系统时生成，基于轮次、规范化表达式、设置、字段和模板/族，稳定且与 `proposal_id` 分离。
- `candidate_id` 覆盖所有候选（包括本地拒绝）；`proposal_id` 只表示通过生产预检、可以进入 Simulation 的提案身份。
- TrialLedger 的候选事件使用 `candidate_id`，并记录 stage、reason_code、模板族、数据族和 structural fingerprint。

## 预算和 UCB

候选先 admission，再由 diversity、arm 和 batch cap 选出最终执行集合；只有最终集合才 commit Simulation budget。`SKIPPED_LOCAL` 释放 admission，不消耗预算；已经 POST 结果不明的 `UNKNOWN/SUBMIT_UNKNOWN` 保留 committed budget。

allocator 同时保留 admitted、submitted、evaluated、done、failed_research、failed_infra、skipped_local、pending、unknown 和 reward_count。UCB 均值和分母只使用真正完成并有研究意义的 evaluated/DONE 结果，基础设施失败和本地跳过不作为负 reward。

## 三轴证据

新证据同时表达：

- `availability`：`AVAILABLE`、`UNAVAILABLE`、`NOT_APPLICABLE`；
- `quality`：`VERIFIED`、`APPROXIMATE`、`PROXY`；
- `decision`：`PASS`、`FAIL`、`INCONCLUSIVE`。

旧 `status/evidence_status` 仍可读取，但 `AVAILABLE` 不再自动等于 `PASS`。Capability verification 只说明接口能力，不直接构成研究通过。

PSR/DSR 使用 `statistical_policy` 的项目阈值；数据不足是 `UNAVAILABLE/INCONCLUSIVE`，fallback DSR 是 `APPROXIMATE`，可计算但未达阈值是 `FAIL`。`STABLE` 是 robustness、年度和平台质量的聚合结果，`statistical_status` 单独报告，不互相冒充。

## ValidationPlan 与恢复

当前新计划为 schema v3，decay 与 truncation 是独立真实维度；旧 v1/v2 计划在读取时迁移为 v3，不改写 append-only 历史证据。`NOT_APPLICABLE` 只有预注册计划声明后才能跳过；REQUIRED 维度必须 `decision=PASS`。

SearchSnapshot 是由 trajectory、checkpoint 和 TrialLedger 重建的只读 projection，负责恢复 allocator、pending/unknown、committed budget、reward、family counts 和 structural-family counts；它不访问文件、不调用传输。

