# Agent-facing 架构

本文是仓库的认知压缩层：说明 AI Agent 在阅读运行时代码前必须理解的稳定概念。仓库是研究仪器，不是研究员。

## 一条研究闭环

```text
Agent
  → research_api.py
  → discovery / simulation
  → WorldQuant BRAIN
  → experiment evidence
  → evaluation
  → state / history
```

Agent 选择 hypothesis、experiment、解释和下一步；Python 保证平台事实、执行、持久化、校验、安全与恢复。

## 事实与状态层级

| 层级 | 含义 | 例子 |
|---|---|---|
| live truth | 当前平台响应 | BRAIN datasets、fields、operator capability、Simulation progress、metrics、checks |
| immutable evidence | 已发生的研究事实 | `trajectory.jsonl`、完成的 experiment record、append-only ledger |
| derived state | 可由证据重建的工作视图 | `context.md`、`experience.json`、报告和摘要 |
| cache | 有界的性能或提示数据 | field cache、evidence cache |

冲突时依次信任 BRAIN live truth、immutable evidence、derived state、cache。缺失或含糊证据保持 `UNKNOWN` / `UNAVAILABLE`。

## 稳定概念与运行时映射

- **BRAIN 接口**：由 `client.py`、`discovery.py` 和 `simulator.py` 实现；负责实时事实、Simulation 安全 POST 和已知 URL 轮询。
- **Experiment**：一次可审计尝试，包含 hypothesis、expression、settings 和 evidence/result。`ExperimentSpec` 是轻量 agent 输入；旧 proposal contract 只作为兼容适配和校验边界。
- **Research State**：由现有 trajectory、checkpoint、`TrialLedger` 和压缩 workspace 视图承担；facade 不创建第二个 store。
- **Evaluation**：由 metrics、checks、yearly、correlation、robustness 和 statistical diagnostics 组成，描述证据，不替 Agent 选方向。

## 机制与研究策略

必须 fail-closed 的机制包括 schema、expression dedup、hard budget、checkpoint recovery、锁、Retry-After、known-URL polling 和 unknown-write reconciliation。

研究策略可由 Agent 调整：hypothesis/dataset 选择、mutation 方向、窗口、优先级以及继续或停止。search allocation、stalled-space rotation 等启发式不是 BRAIN 事实，也不是不可变机制。

## Agent-facing 入口

`wqb_agent/research_api.py` 提供：

- `inspect_state`：查看有限的当前状态视图；
- `discover_fields` / `get_operator_reference`：获取并标记平台能力证据；
- `run_experiment`：通过既有安全 proposal/Simulation 路径执行；
- `get_experiment` / `compare_experiments` / `search_history`：读取证据与历史；
- `reconcile`：只读对账已知远端作业。

## 按问题定位

| 问题 | 起点 |
|---|---|
| Agent 能调用什么？ | `wqb_agent/research_api.py` |
| 如何获得 fields 和平台事实？ | `wqb_agent/discovery.py`、`wqb_agent/client.py` |
| 如何安全执行 Simulation？ | `wqb_agent/simulator.py`、`wqb_agent/client.py` |
| 如何保存实验和恢复？ | `wqb_agent/state.py`、`wqb_agent/trial_ledger.py` |
| 如何解释结果？ | `wqb_agent/metrics.py`、`wqb_agent/validation_report.py`、`wqb_agent/robustness.py` |
| 如何对账未知写结果？ | `wqb_agent/client.py`、`scripts/reconcile_pending.py` |
| 算子和设置参考在哪里？ | `docs/reference/OPERATORS_CHEATSHEET.md`、`docs/reference/SIMULATION_SETTINGS.md`（REFERENCE） |

不要默认阅读整个 package：先读 facade，再读目标模块、一个直接依赖、一个相关测试和一份必要的 policy。

`factory_runner.py`、历史 phase 文档和 `docs/superpowers/**` 不属于默认认知模型。`.wqb_state/` 是 live research state，不能作为普通清理对象。
