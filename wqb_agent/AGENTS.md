# `wqb_agent/` 局部规则

先读根 `AGENTS.md`、`docs/ARCHITECTURE_AGENT.md` 和 `research_api.py`。其他模块是 facade 所组合的现有运行时能力。

## 职责

- `client.py`、`discovery.py`、`simulator.py`、`state.py`、`proposal_contract.py` 是核心机制边界。
- `metrics.py`、`expression.py`、`artifacts.py`、`locking.py` 和 failure helpers 是共享安全/序列化原语。
- `search*`、`validation*`、`robustness.py`、`incremental_value.py`、`memory.py`、`submission.py` 是内部评估或 workspace 视图。
- `factory_runner.py` 是兼容/legacy control plane，不是默认 Agent mental model。

`SuggestionWorkflow` 是 suggestion round 的唯一编排 owner：它负责 discovery fallback、suggestion bundle 组装、`suggestions.json` emission 和既有控制台输出；`Agent` 只保留高层研究规划 hooks 与兼容 facade。Workflow 通过显式依赖和窄 operation-shaped hooks 工作，不反向导入 `Agent`，不直接依赖 `Client`/`Simulator`/checkpoint，也不复制 `_last_round_skipped` 或 `memory.best_exhausted`。

领域模块不得导入 `Agent` 或创建另一条执行/状态路径；BRAIN 事实留在 client/discovery 边界，纯评估函数不得产生网络写入。

## 不变量

- `ProposalExecutionWorkflow` 是 proposal 预检、checkpoint 恢复、Simulation 调度前后编排和终态结算的唯一工作流；`Agent.run_proposals()` 仅保留兼容 facade。工作流不得导入 `Agent` 或直接调用 `client.submit_simulation`，真实提交仍由 `Simulator` 持有，checkpoint 持久化仍由 `CheckpointStore` 持有。
- POST 前持久化 identity/checkpoint；写结果含糊时只轮询或对账同一 job，绝不重复 POST。Simulation 结果与 Alpha 证据不落盘；远端 Alpha 仅以轻量 ID/状态/时间戳按滚动 7 日写入 `.alpha_feed_cache/weekly.json`。
- 保留 Retry-After、锁、预算、schema、expression dedup 和 `UNKNOWN` / `UNAVAILABLE`。
- 远端 Alpha 轻量元数据写入 `.alpha_feed_cache/weekly.json`：每 3 小时与提交 Alpha 同批刷新，按纽约本地日分桶，仅保留当前工作日前推 7 个自然日和 `11200（7*1600）` 条模拟元数据上限；每次刷新清理滚动窗口外和超时临时资源，并保留 `updated_at`/`expires_at`。不得写入指标、表达式、trajectory 或证据。
- Alpha submission 始终手工完成。

## 自主模拟双层边界

- `Agent.generate_optimized_proposals()` 先调用 `AlphaFactory.screen_optimization_parents()` 做代码初筛，再做 Agent 经济机制/反过拟合筛选；云端 Alpha 轻量缓存只提升已有本地证据的优先级，不作为独立性能证据。
- 优化题案标记 `research_layer=optimization`、`research_role=EXPLOIT`；来源按 `cloud`、`current_run` 审计。探索题案由 `AlphaFactory.generate_factory_batch()` 以稳定种子随机化已核验字段和经济模板，标记 `research_layer=exploration`、`research_role=EXPLORE`、`experiment_stage=BASELINE`、`exploration_objective=signal_discovery`。
- 双层不增加执行入口：完整批次仍须通过 100 题案 gate、正常 Agent preflight 和 `Agent.run_proposals()`；代码/Agent 任一层不足或失败都不能用重复题案填充。

研究空间轮换、搜索分配和候选优先级属于 `RESEARCH_POLICY`，不是 BRAIN 机制。

## 验证

For code changes run:

```powershell
python -m unittest discover -s tests
python -m compileall -q wqb_agent scripts tests
```
