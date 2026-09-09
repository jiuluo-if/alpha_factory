# Alpha Factory Agent 指南

本仓库是面向 AI Agents 的 WorldQuant BRAIN Alpha 研究工具。仓库是研究仪器，不是研究员：Agent 做研究判断，Python 保证真实执行、证据、恢复和安全边界。

## 30 秒安全接管

- 先读：`AGENTS.md` → `wqb_agent/research_api.py` → 当前任务目标 → 一个直接依赖和一个测试；不要递归扫描仓库。
- 只读上下文：`python main.py context --compact`；机器读取加 `--json`。它复用 takeover preflight/audit/doctor，`BLOCKED` 时只做对账/恢复，不启动 Simulation。
- 唯一执行入口：`python main.py suggest` → 审阅 `.wqb_state/proposals.json` → `python main.py run-proposals`；不得绕过 `Agent.run_proposals()`。
- 提案执行编排归 `wqb_agent/proposal_execution.py` 的 `ProposalExecutionWorkflow` 所有；`Agent.run_proposals()` 只作兼容 facade。Workflow 不导入 `Agent`、不直接调用 Client POST；Simulation 提交由 `Simulator`、checkpoint 持久化由 `CheckpointStore` 负责。
- Suggestion/discovery 编排归 `wqb_agent/suggestion_workflow.py` 的 `SuggestionWorkflow` 所有；`Agent.run_suggestion_round()` 只作兼容 facade。该 workflow 只读 discovery/context，不能导入 `Agent`、`Client`、`Simulator` 或 `ProposalExecutionWorkflow`，不产生 Simulation POST、checkpoint 写入或 owner lock。
- 不可绕过：`SUBMIT_UNKNOWN` 不重发、known progress URL 只读、checkpoint exactly-once、UNKNOWN/UNAVAILABLE 不升 PASS、Alpha submission 手动完成。模拟/已提交 Alpha 的远端轻量元数据只按美国东部本地滚动 7 日窗口缓存，指标、轨迹、checkpoint 和证据不进入该缓存。
- 任务路由：状态恢复看 `preflight.py/audit.py/state.py` + `test_research_constraints.py/test_runtime_safety.py`；执行看 `agent.py/simulator.py/client.py` + `test_simulator.py/test_recovery.py`；配置看 `config.py/agent.py` + `test_runtime_safety.py/test_agent_flow.py`。
- 改完至少运行：`python -m unittest discover -s tests`、`python -m compileall -q wqb_agent scripts tests`、`python -m ruff check .`；不要为 lint 顺手重写无关业务。

## 四个核心概念

### BRAIN 接口

负责 datasets、fields、operators、Simulation、metrics、checks，以及能力可用时的 correlation / aggregates。当前 BRAIN live response 高于静态文档、cache 和 fixture。

### Experiment

一次可审计研究尝试：hypothesis、expression、settings 和 evidence/result。Agent-facing 的轻量输入是 `wqb_agent/research_api.py` 中的 `ExperimentSpec`。

### Research State

checkpoint 保存未完成实验的恢复边界；trajectory、ledger、压缩上下文和结果视图仍是研究状态来源。远端 Alpha 仅额外生成 `.alpha_feed_cache/weekly.json` 轻量元数据视图：按 `America/New_York` 本地日分桶，只保留当前周，指标/表达式/证据不落入该缓存，BRAIN live response 才是平台事实。

### Evaluation

解释 headline metrics、checks、yearly stability、correlation、robustness 和 statistical diagnostics。它描述证据，不替 Agent 选择研究方向。

## 默认研究闭环

```text
inspect → discover → hypothesize → run → evaluate → record → iterate
```

## Agent 运行时装配边界

运行时装配必须保持以下单向关系：

```text
AppConfig
  ↓
AgentRuntimePolicy
  ↓
RuntimeComponents
  ↓
Agent 提供显式 operation hooks
  ├── SuggestionWorkflow
  └── ProposalExecutionWorkflow
```

- `build_agent_runtime_policy()` 是 Agent 配置投影的唯一 owner；`Agent.__init__` 不得再次逐字段解释 `config.runtime`、`config.factory` 或 `field_selection`。
- `RuntimeComponents` 只拥有已经解析的领域对象，不放入 workflow，也不反向导入 `Agent`；workflow composition 只能接收既有组件，不能重新构造 `Trajectory`、`TrialLedger`、`Simulator`、`CheckpointStore` 或 `SubmissionPool`。
- `Agent` 可以保留 `self.memory`、`self.trajectory` 等兼容属性，但这些属性必须集中投影自同一组组件；两个 workflow 必须通过 identity tests 证明共享对象。
- 不引入 DI/IoC 框架，不创建 `Workflow(agent=self)` 或 `hooks.get_attr` 逃生通道；hooks 必须是窄的、按操作定义的显式回调。

## Alpha 经济含义与自相关硬约束

- 不生成固定多腿 `权重 * rank(ts_decay_linear(ts_zscore(...)))` 参数堆叠，不把窗口/权重/符号扫描包装成新发现。
- 不把同一表达式的 `-signal`、`reverse(signal)` 或等价方向变化当成新 Alpha；必须有新的经济机制、方向理由和可证伪问题。
- production integrity 模式下，每个模板和候选必须具备 `economic_mechanism`、`direction`、`direction_transform`、`expected_horizon`、`falsification` 与 `self_correlation_impact`。
- 自相关影响预测为 `HIGHER` 或 `BLOCK` 时拒绝；`SIMILAR/UNKNOWN` 只能 `REVIEW`，只有有依据的 `LOWER` 才能先验 `ALLOW`。Simulation 后必须真实获取平台 `SELF_CORRELATION`，待定或缺失不得冒充通过。

Agent 接管现有项目先运行 `python main.py state preflight`；若为 `BLOCKED`，先处理 checkpoint 和状态对账。异步自相关只用 `scripts/refresh_self_correlation.py` 做限窗只读回填，不新增第二套执行路径。

Agent 负责 hypothesis、研究方向、dataset/field 选择、expression、实验优先级、结果解释和继续/停止判断。Python 负责 BRAIN 事实、schema、字段/算子校验、去重、硬预算、Retry-After、checkpoint、reconciliation、持久化和确定性统计。

## 不可破坏的机制边界

- 未知 Simulation 写结果保持 `SUBMIT_UNKNOWN`，不能假设失败后再次 POST。
- 已知 progress URL 只读对账和轮询，不能替换成新提交。
- checkpoint 是恢复边界；锁、去重、schema 校验、硬预算和 timeout 必须 fail-closed。
- 缺失证据保持 `UNKNOWN` / `UNAVAILABLE`，不得伪装成 `PASS`。
- Alpha submission 始终由用户手工完成。
- 不得手改 `.wqb_state/` 的 trajectory、checkpoint、proposals、experience 或 lock；任何归档先 dry-run、审计锁与未完成 checkpoint，并取得用户确认。
- 不绕过 `Agent.run_proposals()` 或当前唯一安全 Simulation 路径，除非建立经过测试的等价唯一入口。

## Agent 默认阅读路径

1. `AGENTS.md`
2. `wqb_agent/research_api.py`
3. 当前任务目标文件
4. 一个直接依赖模块
5. 一个相关测试
6. 必要时一个 `docs/` 协议或研究政策文档

不要默认递归阅读整个仓库。历史 phase 文档、`docs/superpowers/**`、兼容 factory、一次性 report 脚本和 specialized skills 只有在当前任务确实需要时才读。

## 运行入口

```powershell
python main.py suggest
# Agent 审阅建议并写入 .wqb_state/proposals.json
python main.py run-proposals
```

旧式 boolean flag 命令在有限兼容窗口内仍可使用，但会输出弃用提示；新文档和 CI 只使用结构化子命令。任何远程 Simulation 操作必须沿现有安全路径，任何状态事实以 BRAIN live response 和 append-only 证据为准。

## Alpha feed 定时约束

- 每 3 小时工作周期执行一次 `python main.py alpha sync-feed`，再执行只读接管预检；提交 Alpha 与模拟 Alpha 必须同批次刷新。该约束由 Agent/代码遵守，不创建独立调度任务。
- 同步必须分页拉取“当前工作日往前 7 个自然日”的数据，并按 `America/New_York` 本地日分桶；本地只保留轻量 ID、状态和时间戳，缓存更新时间写入 `updated_at`，过期时间写入 `expires_at`。
- 周模拟元数据上限固定为 `11200（7*1600）`；超限时优先清理更早本地日，当前日优先保留。每次同步清理跨周缓存和超时临时资源。
- 只有预检 `READY` 才能继续 `python main.py factory run --hours 3`；`BLOCKED`、未完成 checkpoint、`SUBMIT_UNKNOWN` 或 stop 请求时只读对账并保持暂停。

## 自主模拟双层研究约束

- 每个自主 factory round 同时区分优化层（`research_layer=optimization`）与探索层（`research_layer=exploration`）；两层共享同一 100 题案原子批次、同一预算和 `Agent.run_proposals()` 安全入口。
- 优化层候选顺序为云端 Alpha 轻量元数据命中的本地完成证据优先、本轮完成证据其次。云端缓存只用于优先级、去重和谱系，不含指标/表达式/证据，不能单独生成优化题案。
- 优化层先由代码筛选 `DONE`、有限指标、健康状态、字段/数据集画像、有限换手和有限表达式；再由 Agent 提供新的经济机制、变化类型和反过拟合判断。参数、窗口、权重、符号或方向扫描不得进入优化层。
- 探索层由工厂进行大批量、带轮次稳定种子的随机字段/经济模板组合，目标是定位信号（`exploration_objective=signal_discovery`），不是调参；候选必须保持 `EXPLORE/BASELINE`、唯一表达式和完整字段证据。
- `factory_batch_stats` 必须记录两层数量、优化来源和探索目标；层级元数据是当前 proposals 的审计视图，不建立第二套状态或结果存储。

## 修改与验证

优先删除重复概念，合并而不是新增第二套 state、proposal contract、evaluation、facade 或 manager/orchestrator。研究策略不要硬编码成机制。

修改代码后运行：

```powershell
python -m unittest discover -s tests
python -m compileall -q wqb_agent scripts tests
```

提交或推送必须得到用户明确授权；获授权时 Git 邮箱必须为 `2966684515@qq.com`，提交信息必须以 `fix：` 或其他前缀加中文内容。
