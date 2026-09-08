# Alpha Factory Agent 指南

本仓库是面向 AI Agents 的 WorldQuant BRAIN Alpha 研究工具。仓库是研究仪器，不是研究员：Agent 做研究判断，Python 保证真实执行、证据、恢复和安全边界。

## 30 秒安全接管

- 先读：`AGENTS.md` → `wqb_agent/research_api.py` → 当前任务目标 → 一个直接依赖和一个测试；不要递归扫描仓库。
- 只读上下文：`python main.py --agent-context --compact`；机器读取加 `--json`。它复用 takeover preflight/audit/doctor，`BLOCKED` 时只做对账/恢复，不启动 Simulation。
- 唯一执行入口：`python main.py --suggest` → 审阅 `.wqb_state/proposals.json` → `python main.py --run-proposals`；不得绕过 `Agent.run_proposals()`。
- 不可绕过：`SUBMIT_UNKNOWN` 不重发、known progress URL 只读、checkpoint exactly-once、trajectory append-only、UNKNOWN/UNAVAILABLE 不升 PASS、Alpha submission 手动完成。
- 任务路由：状态恢复看 `preflight.py/audit.py/state.py` + `test_research_constraints.py/test_runtime_safety.py`；执行看 `agent.py/simulator.py/client.py` + `test_simulator.py/test_recovery.py`；配置看 `config.py/agent.py` + `test_runtime_safety.py/test_agent_flow.py`。
- 改完至少运行：`python -m unittest discover -s tests`、`python -m compileall -q wqb_agent scripts tests`、`python -m ruff check .`；不要为 lint 顺手重写无关业务。

## 四个核心概念

### BRAIN 接口

负责 datasets、fields、operators、Simulation、metrics、checks，以及能力可用时的 correlation / aggregates。当前 BRAIN live response 高于静态文档、cache 和 fixture。

### Experiment

一次可审计研究尝试：hypothesis、expression、settings 和 evidence/result。Agent-facing 的轻量输入是 `wqb_agent/research_api.py` 中的 `ExperimentSpec`。

### Research State

现有 trajectory、checkpoint、ledger 和压缩上下文保存已经发生的实验、证据和恢复边界。cache 与报告是可重建派生物，不是事实源。

### Evaluation

解释 headline metrics、checks、yearly stability、correlation、robustness 和 statistical diagnostics。它描述证据，不替 Agent 选择研究方向。

## 默认研究闭环

```text
inspect → discover → hypothesize → run → evaluate → record → iterate
```

## Alpha 经济含义与自相关硬约束

- 不生成固定多腿 `权重 * rank(ts_decay_linear(ts_zscore(...)))` 参数堆叠，不把窗口/权重/符号扫描包装成新发现。
- 不把同一表达式的 `-signal`、`reverse(signal)` 或等价方向变化当成新 Alpha；必须有新的经济机制、方向理由和可证伪问题。
- production integrity 模式下，每个模板和候选必须具备 `economic_mechanism`、`direction`、`direction_transform`、`expected_horizon`、`falsification` 与 `self_correlation_impact`。
- 自相关影响预测为 `HIGHER` 或 `BLOCK` 时拒绝；`SIMILAR/UNKNOWN` 只能 `REVIEW`，只有有依据的 `LOWER` 才能先验 `ALLOW`。Simulation 后必须真实获取平台 `SELF_CORRELATION`，待定或缺失不得冒充通过。

Agent 接管现有项目先运行 `python main.py --takeover-preflight --offline`；若为 `BLOCKED`，先处理 checkpoint 和状态对账。异步自相关只用 `scripts/refresh_self_correlation.py` 做限窗只读回填，不新增第二套执行路径。

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
python main.py --suggest
# Agent 审阅建议并写入 .wqb_state/proposals.json
python main.py --run-proposals
```

特殊诊断、reconciliation 和兼容 factory 命令不属于默认 mental model。任何远程 Simulation 操作必须沿现有安全路径，任何状态事实以 BRAIN live response 和 append-only 证据为准。

## 修改与验证

优先删除重复概念，合并而不是新增第二套 state、proposal contract、evaluation、facade 或 manager/orchestrator。研究策略不要硬编码成机制。

修改代码后运行：

```powershell
python -m unittest discover -s tests
python -m compileall -q wqb_agent scripts tests
```

提交或推送必须得到用户明确授权；获授权时 Git 邮箱必须为 `2966684515@qq.com`，提交信息必须以 `fix：` 或其他前缀加中文内容。
