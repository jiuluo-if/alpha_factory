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

`TrialLedger` 的 simulation lifecycle 顺序只有一份定义：
`simulation_committed → simulation_submitted → simulation_settled → research_outcome_settled`。
`LedgerSummary.submitted` 是“至少已提交”的 cumulative 集合；需要精确事件时使用
`simulation_submitted`。审计要求 ledger 的每个 canonical phase 与 trajectory 的同名
`observed_*` projection 对齐；同 proposal 的普通 trajectory 记录不能替代缺失 phase。
trajectory 侧同样以 `observed_submitted` 表示 cumulative 状态，以
`observed_simulation_submitted` 表示 exact phase。
候选生成、拒绝、预检和 admitted 是合法的非 simulation ledger phase，不参与上述顺序。

## 稳定概念与运行时映射

- **运行时装配**：配置先由 `runtime_policy.py` 的 `build_agent_runtime_policy()` 从 `AppConfig` 解析为 Agent 执行投影，再由 `runtime_components.py` 构造唯一的基础领域对象，最后由 `runtime_composition.py` 使用 Agent 提供的显式 hooks 组合四个 workflow。`RuntimeComponents` 不拥有 workflow，也不反向依赖 Agent。
- **BRAIN 接口**：由 `client.py`、`discovery.py` 和 `simulator.py` 实现；负责实时事实、Simulation 安全 POST 和已知 URL 轮询。
- **提案执行工作流**：由 `proposal_execution.py` 的 `ProposalExecutionWorkflow` 负责 proposal 文件预检、去重/预算门、checkpoint、恢复和终态结算；`Agent.run_proposals()` 仅是兼容 facade。工作流通过显式 context/hooks 使用 Agent 组合的领域服务，不反向导入 `Agent`，不直接调用 Client POST。
- **建议生成工作流**：由 `suggestion_workflow.py` 的 `SuggestionWorkflow` 负责 suggestion round、discovery fallback、bundle assembly、`suggestions.json` emission 和 console output；`Agent.run_suggestion_round()` 仅是兼容 facade。它只接收 discovery、memory、trajectory、alpha catalog 与窄研究规划 hooks，不依赖 Agent、Client、Simulator、checkpoint 或 proposal execution。
- **优化工作流**：由 `optimizer_workflow.py` 的 `OptimizerWorkflow` 负责已有 trajectory 证据筛选、weekly Alpha metadata 优先级提示、AlphaFactory 代码初筛、Agent 已提供 hypothesis 的语义/反过拟合 gate 和受限 CHILD proposal 编排。它不生成经济机制、不扫描参数、不写 proposals、不修改 trajectory、不刷新 Alpha Feed，也不触发 Simulation；Agent 的三个优化方法只保留兼容 facade。
- **Experiment**：一次可审计尝试，包含 hypothesis、expression、settings 和 evidence/result。`ExperimentSpec` 是轻量 agent 输入；旧 proposal contract 只作为兼容适配和校验边界。
- **Research State**：由现有 trajectory、checkpoint、`TrialLedger` 和压缩 workspace 视图承担；facade 不创建第二个 store。
- **Evaluation**：由 metrics、checks、yearly、correlation、robustness 和 statistical diagnostics 组成，描述证据，不替 Agent 选方向。

### 配置输入与 typed boundary

外部配置文件和内部运行时模型是两个有意不同的命名层：

```text
config.json / raw dict
  {"simulation": {...}, "agent": {...}}
        ↓ parse_config() / normalize_config()
typed AppConfig
  ├── simulation_config
  ├── runtime
  ├── search / research_allocation / factory
  └── validation / statistical / robustness / incremental_value
        ↓ runtime policy / components / workflows
```

`simulation` 和 `agent` 是外部 schema key，不是 `AppConfig` 的运行时字段。只有
`config.py` 的 parser 可以读取它们；normalize 完成后不得保留 raw shadow mapping，
其他生产模块必须消费 typed sections。错误信息仍使用 `config.agent.*` 或
`config.simulation.*`，因为它们指向用户提交的外部配置路径。

凭据是另一条不进入 AppConfig 的本地配置边界：`credentials.py` 按显式
Client pair、完整 WQB 环境变量、显式绝对路径 env 文件、home credentials file
的顺序选择来源。它不做认证、不访问 BRAIN、不搜索 cwd/父目录/package `.env`，
也不允许 partial source 与其他来源混合；`client.py` 仍独占 Basic Auth、retry、
thread-local Session 和 `trust_env=False`。

运行时对象图如下：

```text
AppConfig
  ↓ build_agent_runtime_policy()
AgentRuntimePolicy
  ↓ build_runtime_components()
RuntimeComponents
  ├── memory / trajectory / trial_ledger
  ├── discovery / simulator / reflector
  └── checkpoints / submission_pool / builder
  ↓ AgentWorkflowHooks
AgentWorkflows
  ├── SuggestionWorkflow
  ├── ProposalExecutionWorkflow
  ├── AlphaFeedWorkflow
  └── OptimizerWorkflow
```

`SuggestionWorkflow`、`ProposalExecutionWorkflow` 与 `OptimizerWorkflow` 使用同一套 `RuntimeComponents` 身份；`AlphaFeedWorkflow` 使用 Agent 已创建的两个 cache 实例，Optimizer 复用同一 trajectory、weekly cache 和 AlphaFactory。组合器不创建第二套状态、执行器或 checkpoint 路径。Alpha Feed 只同步轻量远端元数据，Optimizer 只消费已有证据；两者都不建立第二套研究状态。Agent 继续提供旧属性 projection，避免为了装配重构而大范围改变研究方法和安全执行代码。

Alpha 颜色有意分成两个边界：`alpha_colors.py` 是纯 evidence-derived classification、轻量 evidence summary 和 trajectory candidate loading 的 owner；`alpha_color_workflow.py` 的 `AlphaColorWorkflow` 是独立的 CLI control/write workflow，不属于四个 `AgentWorkflows`。它只接收 `get_alpha` / `set_alpha_color` operation-shaped hooks，负责远端当前颜色、ownership fail-closed、dry-run、verified PATCH 与 readback 结果。`main.py` 负责 `alpha sync-colors` 的单实例锁、lazy Client、JSON/exit code；没有该显式命令时不会自动 PATCH 颜色。`DailyResearchCache.colors` 仍是进程内视图，不是远端颜色 ownership 或证据存储。

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
| 如何执行 proposal 与恢复 checkpoint？ | `wqb_agent/proposal_execution.py`、`wqb_agent/checkpoints.py`、`wqb_agent/simulator.py` |
| 如何生成只读 suggestion bundle？ | `wqb_agent/suggestion_workflow.py`、`wqb_agent/discovery.py`、`wqb_agent/agent.py` |
| 如何保存实验和恢复？ | `wqb_agent/state.py`、`wqb_agent/trial_ledger.py` |
| 如何解释结果？ | `wqb_agent/metrics.py`、`wqb_agent/validation_report.py`、`wqb_agent/robustness.py` |
| 如何对账未知写结果？ | `wqb_agent/client.py`、`scripts/reconcile_pending.py` |
| 算子和设置参考在哪里？ | `docs/reference/OPERATORS_CHEATSHEET.md`、`docs/reference/SIMULATION_SETTINGS.md`（REFERENCE） |

不要默认阅读整个 package：先读 facade，再读目标模块、一个直接依赖、一个相关测试和一份必要的 policy。

`factory_runner.py`、历史 phase 文档和 `docs/superpowers/**` 不属于默认认知模型。`.wqb_state/` 是 live research state，不能作为普通清理对象。

## Architecture Freeze（2026-09-09）

本节是当前稳定架构的冻结声明。连续架构优化在此阶段结束；后续工作进入 feature、bug fixing 和有证据的局部维护。除非出现已证明的 Critical 架构回归或安全 bug，不新增 workflow、state model、config abstraction，不重设计 API，也不继续拆 Agent 私有方法。

### 最终对象图

```text
Raw config
   ↓
config.py: parse_config / normalize_config
   ↓
typed AppConfig
   ↓
AgentRuntimePolicy
   ↓
RuntimeComponents
   ↓
Agent（研究规划、兼容 facade、显式 hooks）
   ├── SuggestionWorkflow
   ├── ProposalExecutionWorkflow
   │       ↓
   │     Simulator
   │       ↓
   │     WQBClient
   ├── AlphaFeedWorkflow
   └── OptimizerWorkflow

explicit CLI: alpha sync-colors
   ↓
AlphaColorWorkflow
   ↓
WQBClient.set_alpha_color(..., verify=True)
```

`RuntimeComponents` 只构造并持有基础领域对象；`runtime_composition.py` 只连接既有对象和窄 hooks 并构造四个 workflow。五个 workflow 都不得反向导入 `Agent`。`WQBClient.run_simulation()` 是保留给旧库调用者的兼容 helper；当前生产源码无调用者，不能作为生产研究入口，生产入口仍只有 `Agent.run_proposals()`。

### Owner matrix

| Concern | Owner | Allowed dependencies / boundary |
|---|---|---|
| External config parsing | `config.py` | 唯一读取 raw `simulation` / `agent` keys 的边界 |
| Runtime config projection | `runtime_policy.py` | 从 typed `AppConfig` 生成 `AgentRuntimePolicy` |
| Base runtime objects | `runtime_components.py` | `SearchPolicy`、`ExperienceMemory`、`Trajectory`、`TrialLedger`、`CandidateBuilder`、`FieldDiscovery`、`Simulator`、`Reflector`、`CheckpointStore`、`SubmissionPool` |
| Suggestion/discovery orchestration | `SuggestionWorkflow` | discovery、context、research-space、suggestion bundle；无 Simulation/checkpoint/远端写入 |
| Proposal execution/recovery | `ProposalExecutionWorkflow` | preflight、预算、checkpoint、恢复、终态结算；经 `Simulator` 执行 |
| Alpha metadata read sync | `AlphaFeedWorkflow` | `GET /users/self/alphas`、纽约七日窗口、dedupe、bucket、cache refresh |
| Optimization candidate orchestration | `OptimizerWorkflow` | 仅消费 `Trajectory` 中已有 DONE evidence；cloud cache 只提供 metadata priority，不恢复 evidence 或 metrics |
| Remote color sync | `AlphaColorWorkflow` | 仅显式 CLI control/write，ownership fail-closed、dry-run、verified PATCH |
| Simulation transport | `Simulator` → `WQBClient` | 唯一生产 `submit_simulation` owner chain |
| Credentials discovery | `credentials.py` | deterministic local-only source resolution |

### State ownership matrix

| State | Single owner | Contract |
|---|---|---|
| Trajectory | `Trajectory` | append-only research evidence and dedupe source |
| Trial lifecycle | `TrialLedger` | canonical lifecycle phase projection |
| Checkpoint | `CheckpointStore` | exactly-once recovery boundary；不保存 metrics/checks/Alpha 结果 |
| Memory | `ExperienceMemory` | lessons, hypotheses and bounded research memory |
| Weekly Alpha metadata | `WeeklyAlphaFeedCache` | only lightweight ID/status/time metadata, New York seven-day window |
| Daily process view | `DailyResearchCache` | in-process view; not remote ownership or evidence |

Runtime identity is tested: Agent, ProposalExecutionWorkflow and OptimizerWorkflow share the same trajectory; Agent and AlphaFeedWorkflow share the daily/weekly caches; RuntimeComponents creates one Simulator, CheckpointStore and TrialLedger instance.

`OptimizerWorkflow` 的 evidence 生命周期是 local-trajectory-only：同一进程内消费传入的 `Trajectory`；重启后由同一个 `Trajectory` owner 从 append-only `trajectory.jsonl` 只读 rehydrate 合法 `DONE` parent（owner 不变，不从 checkpoint 或 Alpha metadata 重建 metrics/checks）。`.alpha_feed_cache/weekly.json` 只提供远端 Alpha ID/status/time metadata 的优先级提示，不能单独生成 DONE parent，也不保存或重建完整 Simulation metrics。

审计 JSONL 使用 `append_jsonl_best_effort`；若唯一性是正确性不变量，owner 必须提供共享 lock（`TrialLedger` 已拥有 `_append_lock`）。未提供 lock 的普通审计追加不承诺并发或跨进程唯一。

### Remote write matrix

| Operation | Module chain | Explicit user action | Verification / safety |
|---|---|---|---|
| Simulation POST | `Agent.run_proposals()` → `ProposalExecutionWorkflow` → `Simulator` → `WQBClient.submit_simulation` | `python main.py run-proposals` after proposal review | preflight, checkpoint before POST, budget, idempotency and `SUBMIT_UNKNOWN` recovery |
| Alpha color PATCH | `main.py alpha sync-colors` → `AlphaColorWorkflow` → `WQBClient.set_alpha_color` | explicit `alpha sync-colors` only | `verify=True`; dry-run has zero PATCH; unknown ownership returns `OWNERSHIP_CONFLICT` |
| Production Alpha submission | none | manual platform action | no automated endpoint owner |
| Legacy `WQBClient.run_simulation` | compatibility helper only | old library caller, not production CLI/factory | retained for compatibility; no production callers and no checkpoint bypass in the canonical flow |

### Frozen safety invariants

- `SUBMIT_UNKNOWN` never triggers an automatic resend; a known progress URL may only be polled read-only.
- The user-authorized skip path (`recovery skip-submit-unknown`) accepts `SUBMIT_UNKNOWN` and progress-URL-less `UNKNOWN` (the same ambiguous-POST evidence gap); a progress-URL-bearing `UNKNOWN` stays read-only reconcilable and is never skippable, and `PENDING`/terminal states are rejected. Owner: `ProposalExecutionWorkflow.skip_submit_unknown_authorized`; audit row in `stale_skip_log.jsonl` with a distinct per-class `reason`.
- Every Simulation POST checks the shared rate-limit gate before acquiring the spacing slot, again after slot contention/spacing, and once more immediately before transport (including after authentication).
- The same complete checkpoint is never redispatched; checkpoint persistence has one owner, `CheckpointStore`.
- `SuggestionWorkflow` and `OptimizerWorkflow` cannot submit Simulation; Optimizer cannot invent `child_economic_hypothesis`, scan parameters, refresh Alpha Feed or write trajectory.
- `AlphaFeedWorkflow` is read-only against BRAIN and only refreshes bounded lightweight caches; submitted and unsubmitted queries remain separate (`dateSubmitted` vs `dateCreated`).
- `AlphaColorWorkflow` is the sole remote color write owner; dry-run performs GET only, and unknown ownership cannot overwrite a non-empty remote color.
- `UNKNOWN` and `UNAVAILABLE` never become `PASS`; production Alpha submission remains manual.
- Credentials resolve deterministically from complete explicit pair, environment pair, explicit absolute env file, or home credentials file; no cwd/parent/package search or source mixing.
- Quality gates remain Python 3.11, the nine-module mypy frontier, selected Ruff rules, branch coverage `fail_under=76.0`, offline doctor and audit.

### Change rules after freeze

Any future change touching a frozen boundary must include: (1) an observable characterization or regression test, (2) an owner/dependency update here, (3) the full local/CI quality gates, and (4) an explicit explanation of the owner change. New orchestration must not accumulate back into `Agent`; structural changes require a concrete feature or bug justification rather than a continuous refactoring objective.
# Feasibility diagnostics (2026-09-10)

`AlphaFactory.assess_feasibility()` is a bounded, control-plane preflight. It may inspect field semantics, frequency evidence, relationship/template compatibility, historical expression exclusion, and cross-dataset novelty, but it does not create research state, metrics, checkpoints, or Simulation writes. `factory_runner` must run it before full factory assembly when the cross-dataset gate is enabled; its summary is embedded in existing batch audit metadata.
# Bounded feasibility route and optimizer handoff (2026-09-10)

Feasibility probes remain control-plane metadata only. A blocked probe records bounded candidate/relationship fingerprints, mechanism family and dataset route; `AIFactoryRunner.route_decision()` compares those fingerprints and chooses `REROUTE` or `STOP` after configured attempt/no-gain limits. A historical candidate set with zero post-dedupe candidates is classified as `MECHANISM_FAMILY_EXHAUSTED`. This route does not submit, reconstruct metrics, or create a second state owner.

Optimizer evidence remains local and append-only: a settled `DONE` Simulation is recorded by the live-result hook into the shared `Trajectory`, then `optimizable_signal_records()` applies the complete parent evidence gate. Cloud Alpha metadata may affect priority only. Handoff counts and rejection taxonomy are control-plane diagnostics, not a result replica.

# Alpha Feed freshness and transient heartbeat (2026-09-10)

`Agent.refresh_remote_alpha_feed_if_due()` is the narrow in-process lifecycle hook used by the legacy factory loop between rounds. It delegates all querying and cache updates to `AlphaFeedWorkflow`; it does not spawn a process, acquire a second scheduler, submit Simulation/Alpha, modify checkpoint/quota, or restore optimizer evidence. Feed freshness is derived from the existing weekly cache timestamp, with a typed positive interval defaulting to three hours. Failed refreshes return a status and preserve the prior successful timestamp.

`HeartbeatSink` is transient and injected into the existing Agent/discovery/Feed lifecycle. It emits throttled aggregate `DISCOVERY`, `FEASIBILITY`, `ASSEMBLY`, `BATCH_GATE`, `ALPHA_FEED_REFRESH`, and `SIMULATION_SETTLEMENT` events. It owns no file, trajectory, checkpoint, ledger, cache, metrics, retry, reroute, cancellation, or quota behavior.

# Factory semantic diversity audit (2026-09-10)

`diversity.py` derives a stable semantic mechanism key from existing field
semantic traits and relationship metadata; it never uses field IDs or free-form
mechanism prose as identity. `factory_batch_stats()` reports expression,
structural-family, semantic-mechanism, field-concept, dataset, and independent
lineage diversity, with separate optimization/exploration summaries. UNKNOWN
evidence is recorded as unresolved and cannot increase known diversity. These
are audit fields only: hard semantic/relationship/frequency/type gates still
run first, and `route_decision()` treats expression-only changes as candidate
changes rather than research information gain.

`select_budget_candidates()` is a derived, in-memory ordering step inside the
existing factory. It keeps the existing optimizer prefix cap and quota owner,
interleaves optimization by lineage and exploration by semantic mechanism,
and records shortage/priority counts in the existing `factory_batch_stats`.
It cannot alter route state, quota reservation, exact batch validation or
checkpoint behavior; explicitly UNKNOWN candidates are not used to fill a
batch.
## 研究预算与端到端路由（2026-09-10）

- `ExperienceMemory.context()` → suggestion bundle → `AIFactoryRunner` → `generate_factory_batch(research_context=...)` 是研究反馈进入预算选择的唯一现有传递链；预算 selector 不拥有 Memory 或持久化研究状态。
- `select_budget_candidates()` 只对 hard-gated candidate pool 做确定性排序：优先级顺序为 HIGH、NORMAL、LOW；optimization 按 lineage 交错，exploration 按 semantic mechanism 交错，并在既有 `factory_batch_stats` 中记录 derived audit。
- 候选池饱和是本轮派生审计，不建立第二套 budget state；explicit UNKNOWN 仍不能填充 exact batch。Factory 早退会清空 transient `last_budget_audit`，避免跨轮读取旧审计。
- 当实际 selected batch 少于 exact-100 且存在 budget shortage audit 时，runner 将 selected-batch fingerprints 送入既有 bounded route/no-gain 控制面；重复无信息最终 `STOP_BUDGET_SHORTAGE`，不预留 quota、不调用 `run_proposals`。checkpoint、quota、Simulation POST owner 不变。


# ResearchYield derived control-plane evidence (2026-09-11)

`wqb_agent/research_yield.py` is a derived control-plane projection, not a new
state owner. It aggregates existing Experiment / SearchOutcome / optimizer
handoff / incremental evidence per stable `semantic_mechanism_key` family into
a lightweight funnel (counts only) and maps each family onto one of five
deterministic outcomes: INCONCLUSIVE / PROMISING / LOW_INFORMATION / EXHAUSTED
/ BLOCKED.

- One-way dependency: `research_yield` imports only `diversity` (mechanism
  key). It never imports `client` / `state` / `simulator` / `agent` /
  `alpha_feed_workflow` / `proposal_execution`, never calls
  `submit_simulation`, `run_proposals` or `settle_search_outcome`, and owns no
  file, checkpoint, trajectory, ledger, metrics, retry, reroute, scheduler or
  quota behavior.
- It is not platform truth, a metrics store, a trajectory/checkpoint
  replacement, an optimizer evidence owner, or a Simulation owner. Optimizer
  eligibility stays unavailable when the caller omits the gate result; DONE
  alone never fabricates parent eligibility (frozen #14 handoff rule).
- `session_control_metadata()` / `research_outcome_summary()` produce minimal
  control metadata (family, evaluated count, outcome state, stop reason,
  aggregate counts) for an existing `factory_session.json` envelope or a
  heartbeat-style RESEARCH_OUTCOME view; raw metrics and checks bodies never
  enter them.

# Settled evidence revision and Agent optimization decision (2026-09-12)

`wqb_agent/state.py` keeps the single canonical completed-Experiment evidence
owner (`trajectory.jsonl`, append-only). Phase III adds one legal *revision*
semantic to that same owner instead of a second store:

- `Trajectory.add()` / `add_many()` remain the first canonical append with
  cross-restart exactly-once dedupe. `Trajectory.settle()` / `settle_many()`
  append a `trajectory_revision="RESEARCH_SETTLED"` row for an Experiment that
  was already appended. `revision != second execution`,
  `revision != second store`.
- Settlement revisions are fail-closed: a missing canonical row, or any change
  to execution identity (id / round / hypothesis_id / expression / settings /
  fields_used / datasets / candidate_id / proposal_id / submission_fingerprint /
  submission_started_at / parent_expression / lineage_id / created_at) raises
  instead of silently overwriting the executed fact. Re-appending an identical
  revision is a no-op.
- The owner merges reads (`load()` → `_merge_rows()`, `find_row()`,
  `find_completed_expressions()`): latest valid revision wins, corrupt rows and
  identity mismatches are skipped, so the last valid evidence survives.
- `Agent._settle_research_outcome()` is the single production write point. It
  appends the revision after the settled evidence exists and audits refusal as
  `SETTLEMENT_REVISION_REJECTED`.
- No new owner appears: the checkpoint stays an execution/recovery boundary, the
  Alpha Feed stays a 7-day lightweight remote-metadata priority hint, and
  `SUBMIT_UNKNOWN` / checkpoint exactly-once / manual Alpha submission are
  untouched.

## Agent optimization decision contract

`wqb_agent/optimization_decision.py` is the formal agent-facing contract that
replaces implicit `parent["child_economic_hypothesis"] = {...}` mutation as the
primary interface. Python only verifies field completeness, parent identity,
the one-change rule, parameter-only / direction-only / overfit rejection,
operator legality and the existing `validate_self_correlation_impact`
admission. It never authors a mechanism, picks operators, writes child
expressions or scans parameters. Opportunity categories
(CONCENTRATION_REPAIR / SUB_UNIVERSE_REPAIR / TURNOVER_REPAIR /
SELF_CORRELATION_REPAIR / ROBUSTNESS_REPAIR / SEMANTIC_REROUTE /
NO_CLEAR_OPPORTUNITY) are evidence-derived context hints, not automatic actions.

`OptimizerWorkflow` separates the two stages that used to be one
`ready_parent_count`: Python evidence eligibility (`_parent_rejections`) and
Agent decision readiness (`_decision_for_parent`). `optimizer_conversions()`
reports Agent Optimization Yield under the same denominator rule as
ResearchYield (denominator 0 → `None`). `inspect_optimizer_parents()` returns a
bounded, read-only summary ordered by optimization opportunity, and
`generate_from_decisions()` reuses the single CHILD generation path.
`research_api.py` and `Agent` expose only thin facades; nothing bypasses
`OptimizerWorkflow → AlphaFactory → proposal contract`.

A CHILD proposal keeps its parent provenance: `AlphaFactory` carries
`parent_id`, `parent_expression`, `lineage_id`, the Agent-authored
`economic_mechanism` and the formal `optimization_decision` into the proposal,
while parent metrics/checks stay in canonical evidence and are never copied.
The decision reuses the existing proposal contract instead of inventing
synonyms: `change_type` must be one of `CHILD_CHANGE_TYPES` and
`direction_transform` must be the `{applied, reason}` object, so an illegal
decision is rejected inside the gate (`CHANGE_TYPE_NOT_IN_PROPOSAL_CONTRACT`,
`DIRECTION_TRANSFORM_INVALID`) instead of producing a proposal that the
production preflight (`research_integrity`) would refuse.

# Pre-correlation policy and metric-aware optimizer context (2026-09-12)

- `wqb_agent/pre_correlation.py` owns the single pre-correlation admission
  policy plus its derived readiness/opportunity bands. It is pure: no state
  read, no request, no write.
- `Agent._pre_correlation_candidates()` builds the correlation-refresh
  candidate set (settled experiments + trajectory window + validation
  candidates, deduped by alpha id) and filters it with that one policy;
  `Agent._alpha_rating()` is delay-aware and refuses to promote a GOOD rating
  when the configured delay is unknown.
- `scripts/refresh_self_correlation.py` reads the same merged trajectory view
  (`Trajectory.load()`), applies the same delay/quality policy and delegates to
  `pre_correlation_selection()`; `select_alpha_ids()` stays the CLI identity so
  Agent and script select the same alpha ids (covered by a shared-fixture test).
- `OptimizerWorkflow.optimizer_context()` is the bounded Agent-facing view: at
  most 8 parents ranked by readiness band → structural blockers → repairable
  blockers → metric distance (never `ORDER BY sharpe DESC`), the derived
  `metric_optimization_context` per parent, failure/blocker counts, declared
  numeric slots with bounded settings pools, pre-correlation eligibility,
  self-correlation status counts, the reused `child_generation_bound()` and the
  OptimizationDecision contract vocabulary. It only reads trajectory evidence:
  no new owner, no POST, no proposal write.
- `SuggestionWorkflow` prefers that hook for `bundle["optimizer_context"]` and
  falls back to the plain `gate_report` counts when the hook is absent.
- `AlphaFactory.validation_proposals()` is the single ROBUSTNESS generation
  path for VALIDATE decisions: Python resolves the bounded candidate value from
  the declared pool, the Agent only chooses which variable to validate.

# Targeted optimization batch arbitration (2026-09-12)

- `wqb_agent/proposal_contract.py` owns both batch envelopes. Exploration keeps
  `validate_factory_batch()` (exactly `FACTORY_BATCH_SIZE = 100`); Agent-authored
  optimization work uses `validate_targeted_batch()` /
  `targeted_batch_state()` with `TARGETED_BATCH_TYPE = "targeted_optimization"`,
  at most 4 CHILD + 4 VALIDATE (`MAX_TARGETED_PROPOSALS = 8`), only
  `proposal_origin="agent_optimizer"` and unique
  `submission_fingerprint(expression, settings)` identities.
- There is still exactly one inbox (`state_dir/proposals.json`), one execution
  entry (`Agent.run_proposals()` → `ProposalExecutionWorkflow` → `Simulator`
  with `CheckpointStore`), one quota owner and one `SUBMIT_UNKNOWN` contract. No
  `optimizer_proposals.json`, sidecar inbox, second Simulation path or new state
  owner is introduced; the targeted envelope only adds an explicit batch mode to
  the existing one.
- `ProposalExecutionWorkflow.run()` validates the targeted envelope fail-closed
  (`TARGETED_BATCH_BLOCKED`, no POST) and derives the local caps from the batch
  contract (`MAX_TARGETED_PROPOSALS`) instead of unrelated per-round exploration
  configuration. Member-level preflight, diversity, budget, checkpoint and
  recovery semantics are unchanged.
- `research_api.materialize_targeted_batch()` is the Agent-facing write facade:
  it reuses `OptimizerWorkflow.generate_from_decisions()` (the single CHILD
  path), the canonical `Agent.next_round_no()` counter and
  `atomic_write_json_if_changed()`. It never runs a Simulation, never writes a
  checkpoint, refuses an out-of-contract batch (`TARGETED_BATCH_REJECTED`) and
  writes nothing when the Agent produced no proposal
  (`NO_TARGETED_PROPOSAL`).
- Two execution-side breakpoints were found and fixed on 2026-09-12 (locked by
  `tests/test_control_loop_repair.py::TestTargetedBatchRunsOnTheSingleExecutionPath`):
  `OptimizerWorkflow._optimization_exclusions()` subtracts the optimized parent's
  own expression from the terminal set, so a DONE parent is no longer discarded
  by `screen_optimization_parents()` as already terminal on both the CHILD and
  the VALIDATE generation path; and `research_api._targeted_field_profiles()`
  fills the envelope `fields` from the Agent's read-only field cache so the
  production preflight accepts the batch. A missing cache leaves the profile out
  and preflight stays fail-closed instead of fabricating field metadata.
- `FactoryRunner` arbitrates the shared inbox before generating a round: a
  present, valid, unexpired and not-yet-executed targeted batch makes the loop
  record `WAIT_AGENT_DECISION` (`TARGETED_OPTIMIZATION_PENDING`) and sleep
  instead of overwriting the file with `factory_100`. Execution evidence is the
  canonical checkpoint of the envelope `round_no`, so an unfinished targeted
  batch is recovered by the existing recovery path; an invalid Agent envelope
  stays blocking (`TARGETED_BATCH_INVALID`) rather than being silently replaced;
  `TARGETED_BATCH_TTL_SEC` is the only automatic release.
- `AlphaFactory.template_numeric_audit()` classifies every numeric literal of
  `DEFAULT_TEMPLATES + ECONOMIC_TEMPLATES` as `RESEARCH_SLOT` (declared
  `TemplateNumericSlot` only), `SAFETY_CONSTANT` (divide epsilon) or
  `OPERATOR_REQUIRED_CONSTANT` (fixed lookbacks and operator-semantic
  constants); an unclassified literal fails the audit instead of becoming a
  rotatable research parameter.
