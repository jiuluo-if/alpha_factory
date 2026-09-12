# 研究政策

本文只描述研究纪律，不代替 BRAIN live response，也不把具体 dataset、field 或 hypothesis 选择硬编码成长期规则。

## 事实与实验边界

1. BRAIN 当前响应是 datasets、fields、operators、Simulation、Alpha 指标、checks、aggregates 和 correlation 的最高事实源。
2. `trajectory.jsonl` 是已确认实验的 append-only 证据，checkpoint 是 exactly-once 恢复边界；二者不得手工改写。
3. Simulation 写入只能沿现有受保护路径执行；timeout、网络中断、5xx 或写入结果不明时不得自动重 POST。
4. 429 必须遵守 Retry-After；`SUBMIT_UNKNOWN` 必须先只读对账；最终 Alpha 提交由用户完成。
5. capability 只有在对应证据等级成立时才能使用。社区观察、fixture 或静态文档不能冒充当前平台能力。

## 假设与反证

每个实验只回答一个可证伪问题，并记录 hypothesis、expression、settings、预期失败模式和结果。先区分：平台事实、回测观察、经济解释和未验证假设；不得用语言推理替代 Simulation。

- `BASELINE` 只检验最小机制；`CHILD` / `ROBUSTNESS` 每次只改变一个变量。
- 多字段必须有语义互证、比率、差分或状态—信号配对；禁止无机制堆叠。
- `VECTOR` 字段先通过已验证的 `vec_avg` 或 `vec_sum` 聚合，并记录类型证据。
- 失败先对照预注册的 falsification 判据；命中时停止该假设，不用窗口/权重扫描掩盖证伪。
- 高 Sharpe 不等于发现；优先跨年份、跨子样本、低相关且机制一致的证据。

## 经济含义与防过拟合硬约束

生产完整性模式拒绝把参数堆叠当作研究发现：固定多腿 `权重 * rank(ts_decay_linear(ts_zscore(...)))` 组合、窗口/权重/符号扫描，以及只做 `-signal` 或 `reverse(signal)` 的方向变体，都不能作为新的 Alpha。方向改变只有在新增经济机制、方向理由和独立可证伪问题时才成立。

每个模板和候选必须携带 `economic_mechanism`、`direction`、`direction_transform`、`expected_horizon` 与 `falsification`。此外必须写入 `self_correlation_impact`，包括 `expected_effect`、`basis`、`rationale`、`admission`：预测为 `HIGHER` 或 `BLOCK` 直接拒绝，`SIMILAR/UNKNOWN` 只能进入 `REVIEW`，只有有依据的 `LOWER` 才能先验 `ALLOW`。这是先验准入判断，不是对平台结果的替代。

Simulation 完成时，BRAIN 的 `SELF_CORRELATION` 可能仍是异步 `PENDING`。系统因此允许只读 GET 刷新，但仍要求所有其他 checks 已通过；真实平台结果会覆盖缓存中的待定检查。只有真实结算状态为 `PASS` 且数值严格低于配置阈值的候选，才可进入人工提交池。没有真实值时必须保持 `UNKNOWN`，不得由结构相似度、旧缓存或本地估算冒充。

## Experiment family 与 trial accounting

同一 hypothesis 下的参数、窗口、字段替换和结构变体属于同一 experiment family。记录每个 trial 的 identity、lineage、family、字段、expression fingerprint、状态和结果；不要把大量派生报告当作新证据。

搜索次数越多，selection bias 越严重。Fitness 只能作为辅助特征，不能替代原始 metrics、checks、稳健性和相关性。预算排序可以参考 expected quality、information gain、novelty 与 simulation cost，但不得把 magic 综合分数当作结论。

## 评估与稳健性

DONE 结果至少结合 Sharpe、Fitness、Turnover、Returns、Drawdown、Margin、全部 checks、健康、yearly evidence 和 SELF_CORRELATION（能力可用时）解释。`PROMISING` 不等于可提交。

稳健性是局部敏感性和机制反驳证据，不称为 hidden OOS。适用时预注册 window locality、semantic field swap、universe、decay/truncation 单变量变化和 yearly aggregates，并记录理由、预算、falsification 和 stopping rule。

相关性、健康和统计证据不足时保持 `UNKNOWN` / `UNAVAILABLE`，不默认通过。可提交候选只进入人工审核池。

## 统计诊断

- PSR 需要有限 return series，并显式使用偏度和非 excess kurtosis。
- DSR 使用 trial Sharpe 的数量及分布估计 selection threshold；缺少完整分布时只能返回明确标注的保守 fallback。
- PBO / CSCV 只有在至少两个长度相同且时间对齐的 return series 存在时才可用，否则为 `UNAVAILABLE`。
- PnL 只有 capability `LIVE_VERIFIED` 时才进入 rolling stability、correlation 和 bootstrap diagnostics。
- 统计诊断不能替代原始证据，也不能把 proxy/approximate 说成完整论文实现。

## 停止纪律

- **PROMOTE**：指标、checks、健康、稳定性和平台相关性证据均足够且通过，只进入人工审核池。
- **CONTINUE**：结果能改变下一步判断，下一次只改变一个变量。
- **STOP / KILL**：机制被证伪、已达到防过拟合停止条件或继续实验不再增加信息。
- **RECONCILE**：`UNKNOWN`、`TIMEOUT`、`RATE_LIMIT`、`AUTH`、`INFRA` 或缺少必要证据；不把它们写成长期失败结论。

研究策略属于 Agent 判断；Python 只保证事实、边界、证据和恢复，不替研究员选择方向。

## Alpha 顶层 color

`alpha sync-colors` 只把已有研究证据映射到 BRAIN Alpha 顶层 `color`，不评分、不创建 Simulation、不提交 Alpha；`alpha sync-colors --dry-run` 仅预览。`PURPLE` 表示可提交且已有独立/增量价值证据，`GREEN` 表示可提交，`RED` 表示有信号但存在自相关、相关性或稳健性阻断，`BLUE` 表示强信号但仍待关键证据，`YELLOW` 表示有机制的 promising 信号。无信号、失败、重复、参数幸运或证据不足保持无颜色；已有非本项目颜色不覆盖。颜色检测结果只保存在当前进程的 America/New_York 日缓存中，不生成颜色 evidence 侧车。

颜色触发分为两个时点：Simulation settle 时更新单个实验的当前日颜色视图，批次收尾时使用已刷新验证/相关性证据再次同步提交池视图。颜色是既有证据的派生视图，不会因为颜色分类而创建请求、修改 checkpoint 或提交 Alpha。

## 自主优化触发边界与阶段配额

自主优化不是“有历史结果就自动变参”。门禁要求 parent 已完成、拥有完整平台指标、字段理解与字段分析，并且研究 Agent 明确提交非参数性的 `child_economic_hypothesis`、变化类型和反证标准。缺少任一条件时，`optimizer_context.blocked_reasons` 记录原因，继续走普通 discovery，不生成伪 CHILD。

当前阶段本地 Simulation admission quota 为每周 `11200` 次（`7*1600`），每日 `1600` 次，日期按 `America/New_York` 计算。配额只保留 schema、日期、周起点、上限和预留计数；模拟结果、Alpha ID、metrics、颜色证据仍不进入配额文件。每日刷新只释放日槽位，不能清除周计数，也不能覆盖未完成 checkpoint 的恢复预留。

## Agent 接管与效率

接管已有 workspace 的第一步是 `python main.py state preflight`。该命令只读汇总未完成 checkpoint、状态审计、proposal/cache 概况和 trajectory 计数；`BLOCKED` 时先恢复或对账，不直接启动新实验。自相关回填使用 `scripts/refresh_self_correlation.py` 的时间窗和数量上限，避免重复扫描全部历史。它只调用现有 evidence cache GET 路径，不创建第二套 Simulation 或 submission API。
# Frequency evidence and feasibility (2026-09-10)

Frequency is auditable evidence, not an unqualified field attribute. Platform metadata is `EXPLICIT_PLATFORM`; description-derived values are `DESCRIPTION_INFERRED`; missing, ambiguous, or conflicting values remain `UNKNOWN`/`CONFLICT` and cannot silently satisfy a relationship gate. A bounded feasibility probe must establish at least one novel, relationship-`ALLOW`, frequency-compatible, template-compatible cross-dataset candidate before full atomic batch assembly.

Alpha Factory is a probe generator, not a direct submission-ready Alpha producer. Public template data is synthetic; production templates and pairings are local-only. Probe templates require explicit economic semantics, 4–6 operator occurrences and 2–4 economically distinct fields; controls are the only 1–3 operator/single-field exception. Operator diversity is preferred only when an operator's economic role, arity and field relation are verified. Horizon values use the lattice 5/22/66/120/255, multi-window profiles are adjacent rather than Cartesian, and each configuration arm changes exactly one main variable.
# Bounded mechanism reroute and DONE parent eligibility (2026-09-10)

When feasibility fails, the factory compares admissible relationships, canonical expressions, mechanism family and dataset composition. Seed changes alone do not count as information gain. Route attempts are bounded; repeated no-gain or exhausted route attempts produce a recorded STOP. REVIEW/UNKNOWN remains fail-closed.

Only local trajectory evidence from a real settled `DONE` experiment can become an optimizer parent. The parent must retain metrics, checks (including explicit UNKNOWN where applicable), expression, field audit metadata, hypothesis and economic mechanism. Alpha Feed metadata cannot restore evidence. The canonical completed Experiment evidence is appended to `trajectory.jsonl` by the sole `Trajectory` owner, so a later process rehydrates the same parent read-only after a restart; checkpoints still only carry recovery identity and never reconstruct metrics or checks.

# Feed freshness and heartbeat policy (2026-09-10)

Alpha Feed periodic refresh is read-only freshness maintenance, not Alpha evidence recovery. It reads `/users/self/alphas`, keeps only existing lightweight metadata, and reports `FEED_REFRESH_OK`, `FEED_REFRESH_NOT_DUE`, `FEED_REFRESH_QUERY_TOO_BROAD`, or `FEED_REFRESH_TRANSPORT_ERROR` without changing safe Simulation settlement. `last_attempt_at` is distinct from `last_success_at`; stale or unknown cache state never claims freshness.

Heartbeat is observability only. Throttled stage events may report stalls and aggregate progress, but cannot retry POST, skip UNKNOWN, cancel Simulation, clear checkpoint, reserve quota, reroute research, or update research state.

# Semantic diversity audit (2026-09-10)

Factory batch uniqueness is not treated as mechanism diversity. The audit keeps
expression, structural family, semantic mechanism, field concept, dataset, and
independent lineage counts separate. Semantic keys use derived traits and
relationship metadata without field IDs; missing or UNKNOWN traits remain an
unresolved bucket. Child proposals sharing one reliable parent lineage count
as one independent lineage. Diversity is computed after the existing hard
gates and is an audit/priority signal only; it cannot relax semantic
compatibility or relationship admission.

# Lightweight research budget ordering (2026-09-10)

Within the existing 100-proposal contract, hard-gated candidates receive a
derived ordinal priority and are deterministically interleaved: optimization
uses independent lineage groups and exploration uses semantic-mechanism
groups. Agent-authored unresolved/discriminating questions and INCONCLUSIVE
evidence receive priority; confirmed repeats and contradicted repeats are
deprioritized, while an explicit alternative explanation remains eligible.
This ordering never changes quota, reservation, checkpoint, route, or exact
batch rules. Shortage is reported rather than filled with UNKNOWN/REVIEW,
duplicates, or parameter variants.
## 端到端 budget shortage 与 route 边界（2026-09-10）

- 预算优先级只在 hard-gated 候选中派生，顺序固定为 HIGH → NORMAL → LOW；饱和计数来自当前候选池，属于本轮审计，不是新的研究状态。
- route 负责判断是否换路线，budget 负责选择槽位。若 selected batch 因真实候选不足无法满足 exact-100，runner 使用实际 selected batch 的 expression/semantic/dataset fingerprints 进入既有 bounded route/no-gain 控制；重复无信息时停止，不以等待代替换路，也不降低语义门槛。
- shortage 分支不调用 `run_proposals()`、不预留 quota、不创建 checkpoint；只有完整 hard-gated exact batch 才进入既有生产执行链。


# ResearchYield family outcome policy (2026-09-11)

`research_yield.family_state()` is the deterministic decision table for one
mechanism family. Order of evaluation: EXHAUSTED (explicit route/semantic
closure evidence) → BLOCKED (infra dominated) → INCONCLUSIVE (unresolved
share) → INCONCLUSIVE (below minimum sample) → BLOCKED (handoff/evidence gap:
DONE ≥ min but optimizer gate unavailable, or evidence-gap rejections
dominate) → INCONCLUSIVE (LEGACY-only) → INCONCLUSIVE (FINAL insufficient) →
PROMISING (downstream progress) → LOW_INFORMATION (ample evidence, zero
downstream) → INCONCLUSIVE fallback.

- Evidence quality reuses SearchOutcome semantics: FINAL may drive an outcome
  decision; PROVISIONAL observes trends but cannot hard-STOP; LEGACY is
  historical visibility only and caps a family at INCONCLUSIVE.
- Infrastructure failure (AUTH, rate limit, timeout, transport, platform
  unavailable, UNKNOWN, SUBMIT_UNKNOWN, unresolved progress URL, incomplete
  checkpoint) is counted separately from research failure and never implies
  the mechanism carries no information.
- Conversions use explicit denominators: denominator 0 → `None`
  (`NO_DENOMINATOR`); evidence unavailable → `None`
  (`DENOMINATOR_UNAVAILABLE`); only an occurred-but-zero stage is `0.0`.
- Minimum sample guard: only two typed knobs are added,
  `research_yield_min_evaluated` (default 40) and `research_yield_window`
  (default 200); LOW_INFORMATION / PROMISING / outcome STOP all require the
  sample guard.
- Continuation is a pure derived mapping for the existing route policy:
  PROMISING → CONTINUE; INCONCLUSIVE → OBSERVE; LOW_INFORMATION → bounded
  REROUTE, then STOP `LOW_RESEARCH_YIELD`; EXHAUSTED → existing exhaustion
  REROUTE/STOP; BLOCKED → WAIT/STOP without consuming new quota.
  `NO_INCREMENTAL_CHILD_EVIDENCE` is valid only after a real child
  opportunity, completed children, and a settled incremental verdict.

# Agent optimization decision policy (2026-09-12)

- A parent may become a CHILD only through an explicit Agent
  `OptimizationDecision` (or the legacy `child_economic_hypothesis` adapter)
  that passes the deterministic gate: complete fields (economic_mechanism,
  change_type, changed_variable, expression, expected_effect, falsification,
  why_not_parameter_tuning), parent identity match, one-change rule, no
  parameter-only / direction-only / overfit / illegal-operator change, and a
  valid self-correlation admission (HIGHER/BLOCK → reject; SIMILAR/UNKNOWN →
  REVIEW, never ALLOW).
- A CHILD proposal keeps parent provenance (`parent_id`, `parent_expression`,
  `lineage_id`, `economic_mechanism`, the formal `optimization_decision`) and
  never copies parent metrics/checks, which stay in canonical evidence. The
  decision reuses the existing proposal contract vocabulary: `change_type` must
  be in `CHILD_CHANGE_TYPES` and `direction_transform` must be the
  `{applied, reason}` object. A synonym or malformed transform is rejected in
  the gate (`CHANGE_TYPE_NOT_IN_PROPOSAL_CONTRACT` /
  `DIRECTION_TRANSFORM_INVALID`) instead of being deferred to preflight.
- VALIDATE / REROUTE / STOP never derive a child proposal. They are explicit
  Agent decisions recorded in the funnel instead of being silently dropped.
- Optimization ranking is opportunity-based, not Sharpe-based: a parent with a
  concrete, evidence-derived blocker (self-correlation / concentration /
  sub-universe / turnover / robustness / semantic reroute) outranks
  `NO_CLEAR_OPPORTUNITY`. These remain context hints, never automatic actions.
- `DONE → evidence parent` and `evidence parent → Agent decision` are separate
  funnel stages (`done_to_optimizer_parent` vs `evidence_parent_to_agent_review`);
  an unavailable Agent stage is `None`, never 0.0, so "nobody reviewed" and "the
  gate rejected everything" stay distinguishable.
- Incremental capability: the platform exposes no PnL / daily-return / behavior
  series, so incremental value stays `UNAVAILABLE`; Sharpe/fitness/returns deltas
  must never be presented as incremental correlation evidence. Without a
  verified incremental PASS, `child_generation_bound()` bounds the chain to one
  child generation (`BLOCKED` / `NO_INCREMENTAL_CHILD_EVIDENCE`) instead of
  deriving C2 → C3 → C4.
- Settled FINAL evidence is what a restart rehydrates: the canonical
  `RESEARCH_SETTLED` revision is what makes a previously completed parent
  legally reviewable in a later process.

# Pre-correlation admission and metric-aware optimization (2026-09-12)

- `wqb_agent/pre_correlation.py` is the single SELF_CORRELATION admission
  policy. `Agent._refresh_self_correlation_evidence()`,
  `scripts/refresh_self_correlation.py` and the optimizer context all reuse
  `pre_self_correlation_eligibility()`; there is no second threshold set.
- Admission order: every non-`SELF_CORRELATION` check resolved PASS →
  `health.ok` → delay-aware Sharpe/Fitness strictly above threshold →
  `Returns > 0` → `0.01 <= Turnover <= max_turnover` →
  `Drawdown <= max_drawdown`. Missing values stay `UNKNOWN`, never PASS.
- Delay thresholds are strict (`>`): delay 1 → Sharpe > 1.25 / Fitness > 1.0;
  delay 0 → Sharpe > 2.0 / Fitness > 1.5. An unknown delay is fail-closed
  (`DELAY_UNKNOWN`) and can never be promoted.
- `Turnover` 0.125 is only the Fitness denominator floor
  (`Fitness = Sharpe × sqrt(abs(Returns) / max(Turnover, 0.125))`); it is not a
  target turnover. The derived context exposes `turnover_penalty_active` and
  suppresses any "keep lowering turnover" hint at or below the floor. It never
  recomputes or replaces platform metrics.
- Readiness bands are Agent context only (no new research state):
  PRE_CORRELATION_READY / ONE_REPAIR_AWAY / STRUCTURAL_REPAIR_REQUIRED /
  NUMERIC_VALIDATION_CANDIDATE / LOW_INFORMATION / STOP.
- Numeric rotation is research-parameter only: `AlphaTemplate.numeric_slots`
  declares which literal is a research number, one slot per variant,
  `numeric_variants(max_variants=3)` never forms a Cartesian product, and
  undeclared literals (divide epsilon, operator arity constants) never rotate.
  `template_variant_id` is audit/dedupe identity, never mechanism identity;
  `semantic_mechanism_key` must not include window/decay/threshold.
- Settings variants reuse the existing `SETTING_OVERRIDES` whitelist and the
  bounded neighbours from `validation_candidate_values()`: decay is `base ± 1`
  clamped to 0..10, truncation uses the adjacent allowed values and never
  changes together with decay, and universe is only offered when the parent
  shows a real `LOW_SUB_UNIVERSE_SHARPE` blocker with an Agent reason (no
  round-robin; fail-closed when no universe pool is configured).
- Every numeric/settings change is `experiment_stage="ROBUSTNESS"` and carries
  `numeric_variant` / `settings_variant` provenance plus the formal
  `optimization_decision`; it never enters CHILD discovery.
- Targeted optimization batch (implemented 2026-09-12): exploration keeps the
  exact-100 `factory_100` contract, while Agent-authored CHILD/VALIDATE work is
  materialized as `batch_type="targeted_optimization"` in the *same* canonical
  `proposals.json`. The envelope is bounded by the contract itself (at most 4
  CHILD + 4 VALIDATE = 8 proposals, `agent_optimizer` origin, unique
  expressions) and is validated before execution
  (`MAX_TARGETED_PROPOSALS`); the previous
  `TARGETED_OPTIMIZATION_BATCH_BLOCKED_BY_FACTORY_BATCH_CONTRACT` blocker is
  therefore closed, not relaxed: exactly one inbox, one owner, one
  `Agent.run_proposals()` path, no second Simulation path.
- `FactoryRunner` treats a present, valid, unexpired and not-yet-executed
  targeted batch as the current inbox owner: it records
  `last_action="WAIT_AGENT_DECISION"` with
  `status=TARGETED_OPTIMIZATION_PENDING` and never overwrites it with
  exploration 100. An invalid Agent envelope is still blocking
  (`TARGETED_BATCH_INVALID`) so it cannot be silently dropped, and expiry
  (`TARGETED_BATCH_TTL_SEC`) is the only way the factory reclaims the inbox
  without human action. Execution evidence stays the canonical checkpoint of
  the batch round, so recovery of an unfinished targeted batch runs through the
  normal recovery path.
- The CHILD and VALIDATE generation paths read the terminal-expression hook only
  to exclude *new* proposals: the optimized parent's own expression is exempted
  (`OptimizerWorkflow._optimization_exclusions()`), and the targeted envelope
  carries the real discovery field profiles read from the Agent field cache, so
  an Agent-authored batch passes the production preflight instead of being
  blocked for missing field profiles.
