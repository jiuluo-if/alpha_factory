# 颜色分组、Agent 自主优化与周模拟配额设计

## 背景与已验证根因

历史 `round_1` 到 `round_11` checkpoint 中的 100 个实验全部是 `BASELINE/EXPLORE`。颜色分类只在整批没有 `PENDING/RUNNING/UNKNOWN` 时通过 `_sync_submission_pool()` 执行；未完成批次直接返回，颜色没有触发。结果和颜色又只进入进程内 `DailyResearchCache`，进程退出后不保留历史结果，因此新进程的 `--sync-alpha-colors` 无法从本地 trajectory 恢复旧实验。

自主优化入口要求 `DONE` parent、有限指标、完整字段审计元数据以及 Agent 提供的 `child_economic_hypothesis`。工厂模板只生成 `BASELINE/EXPLORE`，不会臆造经济机制，所以历史运行没有产生 `agent_optimizer/CHILD`。这属于触发输入缺失，不是应该放宽安全门槛。

## 设计

### 颜色分组

在每个 Simulation 结果 settle 后立即把当前证据映射写入当日内存颜色视图；整批收尾时继续执行现有完整证据重算，以便 validation、yearly evidence 和真实 `SELF_CORRELATION` 到齐后更新颜色。颜色分类仍只读，只有显式 `--sync-alpha-colors` 才允许 PATCH，非本项目颜色仍不覆盖。

旧进程已经丢失的指标和颜色不从 checkpoint 猜测恢复；checkpoint 仍只保存 exactly-once 身份和 progress URL。历史颜色如需补齐，必须另行使用 BRAIN live response 建立证据，不由本次本地缓存改造伪造。

### Agent 自主优化

增加可审计的 optimizer gate report，区分 `DONE`、指标阈值、字段元数据、子假设和最终候选数量，并把当前进程可优化 parent 的最小上下文放入 suggestion bundle。Agent 只在明确提供 `child_economic_hypothesis` 时产生 `CHILD/agent_optimizer`；该元数据保留在当前进程 trajectory，供下一轮 gate 读取，checkpoint 仍不保存结果侧证据。数值窗口、权重、符号或平滑变体仍 fail-closed。工厂消费优化结果并保留来源统计，不新增第二条 Simulation 执行路径。

### 本地一周配额、每日刷新

在工厂控制面增加只保存计数和日期的 quota 元数据：`weekly_simulation_cap=11200`、`daily_simulation_cap=1600`、时区 `America/New_York`。每次提交前同时检查周剩余和当日剩余；纽约本地日变化时只清零日计数，周计数持续到下一个纽约周一。计数随 `factory_session.json` 原子更新，跨进程不能通过重启绕过；不保存模拟结果、指标、Alpha ID 或颜色证据。未完成 checkpoint 的保留预算仍优先，不得因刷新重发未知 POST。

## 验收标准

- 每个已 settle 实验都能在同一进程立即产生颜色视图，整批收尾仍能用完整证据重算。
- suggestion bundle 能明确显示自主优化触发条件和阻塞原因；没有子假设时不生成 CHILD，有合格子假设时保留 `agent_optimizer/CHILD` provenance。
- 新日期清零日配额但不清零周配额；新周同时清零周/日配额；跨进程读取 session 后仍保持计数。
- 配额不足阻断新的整批提交，不影响已知 progress URL 的只读恢复；`SUBMIT_UNKNOWN` 语义不变。
- 相关单测先红后绿，全量 unittest、compileall、Ruff、diff check 和代码审查通过；不启动真实 Simulation，不自动提交 Alpha。
