# 任务计划：运行数据审查、清理与工厂/Agent 边界修复

## 已完成目标

审查最近运行产生的数据，诊断 Agent/执行链问题；核对并删除用户指定的外部 `.wqb_state`，以及本仓库中经过证据确认的多余生成物。

## 已完成阶段

- [x] 只读接管：读取核心源码、相关测试、运行上下文和状态目录
- [x] 数据审计：按时间、checkpoint、trajectory、ledger、proposals、日志对账
- [x] 根因诊断：区分 Agent 判断问题、执行器问题、环境/数据证据问题
- [x] 清理核准：形成删除清单，确认不触碰未完成研究状态
- [x] 执行清理：删除已授权目标并记录结果
- [x] 完成验证：复查路径、状态、测试/编译和剩余风险

## 当前阶段

清理目标和新阶段实现均已完成：工厂每批固定 100 个题案，Agent 只生成有证据的优化题案，模板负责受控广度，避免参数过拟合；结果/提交/颜色数据按美国东部日只在进程内缓存，检查点保留恢复边界。

## 新阶段

- [x] 先锁定纽约本地日内存缓存和只保留 checkpoint 的失败测试
- [x] 固定工厂 100 题案 gate，拆分 Agent 优化/模板角色
- [x] 加强抗过拟合结构检查和 Alpha 颜色只读检测
- [x] 移除结果、提交池、trajectory、ledger、轮次摘要的默认落盘
- [x] 完整测试、编译、lint、代码审查和生成物复核

## 多数据集与多字段改造

- [x] 用失败测试锁定多数据集覆盖、目录固化、双字段和三字段占位符契约
- [x] 实现纽约本地日字段目录、可复现分层轮询和 `(dataset_id, field_id)` 画像身份
- [x] 接通 `{data_field}`、`{p}`、`{s}`、`{t}` 通用模板及 `field_refs`
- [x] 将数据集覆盖、模板分布和跨数据集组合纳入 100 题案 gate/统计
- [x] 真实平台只读 `--suggest` 复核最终数据集分布和目录 manifest
- [x] 完成 fresh code review、compileall、ruff、生成物与状态目录复核

## 设计与执行记录

- 设计：`docs/superpowers/specs/2026-09-08-factory-agent-boundaries-design.md`
- 计划：`docs/superpowers/plans/2026-09-08-factory-agent-boundaries.md`
- 采用整批 gate：不足 100 个唯一且预检通过的题案时，不部分提交、不填充重复题案。

## 错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| Superpowers 初始路径不存在 | 1 | 已定位实际安装路径，改用 `C:\\Users\\联想\\.agents\\skills\\superpowers\\...` |
| 用户提示更新后的 proposal_contract 缩进错误 | 1 | 复查 diff 与 py_compile 发现，恢复 `if not profiles_by_id` 体缩进并重新通过全量测试 |

## 2026-09-09 增量修复阶段

- [x] 只读接管 round 2，等待旧进程退出并核对 `DONE/FAILED/UNKNOWN/PENDING` 与 session 账目
- [x] 修复已知 `progress_url` 的普通 `UNKNOWN` 不阻塞独立 `PENDING` 派发；保留 `SUBMIT_UNKNOWN` exactly-once 暂停
- [x] 修复新 factory session 恢复 checkpoint 时缺失 `last_round` 的账目映射
- [x] 最小回归、架构回归、全量 unittest、compileall、Ruff 与 diff check
- [ ] 等待当前 round 3 远程批次收敛后做最终状态对账与生成物复核

## 当前下一步

等待当前 `python main.py --factory-run --factory-hours 0.5` 自然返回；只读核对 round 3 checkpoint、session、锁和进程，随后清理本轮构建缓存并完成最终验证记录。

## 2026-09-09 本次接管：真实状态驱动恢复边界

- [x] 只读接管并确认 `round_11` 的真实 checkpoint 状态
- [x] 先用失败测试锁定 `SUBMIT_UNKNOWN` 存在时禁止同批 `PENDING` 新提交
- [x] 实现最小恢复边界修复，不修改现有研究状态
- [x] 运行定向测试、全量测试、compileall、Ruff 和 diff check
- [ ] 若预检恢复为 READY，才沿唯一入口继续真实 Simulation；否则保持暂停并报告重大阻塞

## 本次当前下一步

全量验证已通过；真实只读恢复已完成，预检仍为 BLOCKED，按安全边界保持暂停并报告重大结果。

## 2026-09-09 自主模拟双层改造

- [x] 经用户确认双层设计：优化层云端优先/本轮其次，代码初筛后 Agent 二筛；探索层大批量随机定位信号
- [x] 用失败测试锁定稳定随机种子、层级标记、代码筛选和云端轻量元数据优先级
- [x] 实现现有 AlphaFactory/Agent/FactoryRunner 双层边界，不新增状态机或执行入口
- [x] 补充 batch stats、AGENTS/README/STATE_LAYOUT 约束
- [x] fresh code review、全量验证、分批提交并推送 main

## 2026-09-09 配置边界收敛第一阶段

- [x] 读取任务要求、最新 main、配置入口和相关测试；建立 480 tests 基线
- [x] 先写并验证配置边界/数值验证/CLI override 回归测试
- [x] 实现统一 fail-closed validators 与 typed CLI override
- [x] 强化架构守卫并复测完整配置兼容性
- [x] 完成 unittest、compileall、Ruff、doctor/audit 离线验证及风险复核

## 当前下一步

阶段完成：保留未提交工作树，交付配置边界、回归证据和 deferred/risk review。

## 2026-09-09 第二阶段：结构化 CLI（设计门）

- [x] 读取新阶段要求、最新 main、局部规则及直接依赖
- [x] 确认基线 SHA、工作树、旧 CLI 引用和全量测试状态
- [x] 用户确认 CLI canonical grammar、legacy adapter 和安全矩阵
- [x] 先写 CLI grammar/safety 回归并观察红灯
- [x] 实现单一 canonical command dispatch，不改 Agent/Client/Simulation 机制
- [x] 更新文档、完成 fresh review 和完整验证

## 当前下一步

阶段实现与验证已完成；未触碰 Client、Simulator、checkpoint、quota、研究状态或远程 Simulation，Agent 仅更新了面向用户的 CLI 提示文字。

## 2026-09-09 第三阶段：抽离提案执行与恢复工作流

目标：将 proposal execution / checkpoint recovery orchestration 从 `Agent` 抽出为独立的 `ProposalExecutionWorkflow`，保持输入、checkpoint、Simulation POST 次数、顺序、状态、输出和失败语义完全不变。

- [x] 重新读取并记录执行调用图，区分执行专属 helper、Agent 共享 workflow、纯领域函数和 state owner
- [x] 新增 characterization tests，锁定缺失/损坏 proposals、非法 round、foreign checkpoint、`SUBMIT_UNKNOWN` exactly-once、complete checkpoint 和 stats contract
- [x] 建立窄依赖 `ProposalExecutionContext` / `ProposalExecutionWorkflow`，不反向导入 `Agent`，不新增第二条 Simulation POST 路径
- [x] 分批迁移入口、checkpoint recovery、payload/round validation、dispatch/settlement orchestration；让 `Agent.run_proposals()` 成为兼容 facade
- [x] 增加 facade delegation、直接 workflow 等价性、依赖方向、POST 次数和 `last_run_stats` 回归测试
- [x] 更新 AGENTS/architecture 文档，明确 Agent、Workflow、Simulator、Client、CheckpointStore owner
- [x] 完成定向测试、全量 unittest、compileall、Ruff、doctor/audit、diff check、fresh architecture review
- [x] 使用 `fix：`/`refactor：` 英文前缀加中文内容提交，并自动推送到 `origin/main`，重新确认远端 SHA

## 本阶段当前下一步

已完成调用图、红绿 characterization 测试、workflow 迁移、兼容边界复核、文档更新和独立审查；全量门已通过，下一步提交并推送后核对远端 SHA。

## 2026-09-09 渐进式工程质量门

- [x] 重新读取 `origin/main`，确认 baseline SHA 为 `d49287436ad23978bf4ba4b250c16e95290a2ed95`
- [x] 测量 fresh baseline：`wqb_agent` statement `80.83%`、branch `69.00%`、branch-aware `77.54%`；595 tests OK
- [x] 完成 Ruff dry-run：`I=85`、选定安全 UP 子集 `33`、`B007/B904=11`
- [x] 确定 9 个 typed frontier 模块；mypy 初测仅被缺少 `types-requests` 阻断
- [x] 保存设计与实施计划：`docs/superpowers/specs/2026-09-09-quality-gates-design.md`、`docs/superpowers/plans/2026-09-09-quality-gates.md`
- [x] 配置 pyproject、CI 和文档质量入口
- [x] 以最小 diff 清理选定 Ruff 规则
- [x] 验证 mypy、branch coverage fail-under、doctor/audit 和完整安全边界

## 本阶段当前下一步

质量门实现与本地验证已完成；保留真实 `.wqb_state` 的既有阻塞，不启动 Simulation，等待用户决定是否授权提交/推送。

## 本阶段错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| `pip install ".[dev]"` 的隔离构建下载 `setuptools>=68` 返回 HTTP 403 | 1 | 保留声明的 dev extra；改用当前已安装工具并单独验证 `types-requests`，CI 使用标准安装路径 |
| PowerShell 变量插值 `"$f:$start"` 被解析为非法变量引用 | 1 | 改用 `${f}` 分隔变量后重新读取目标代码 |
| 批量 `Remove-Item -LiteralPath` 清理多个 coverage 生成物被执行策略拒绝 | 1 | 改为逐个、已核验的明确路径清理 |

## 2026-09-09 FieldDiscovery scaling

- [x] 写入并审查 FieldDiscovery scaling spec/plan
- [x] 先写 pagination completeness、malformed response、中文 token、stratified sampling 和 artifact safety 回归
- [x] 实现 MATRIX/VECTOR 独立 completeness、动态 dataset boundary 和 bounded candidate retrieval
- [x] 输出透明 ranking provenance，不改变 Factory template semantics
- [x] 完成全量 unittest、compileall、Ruff、diff review、提交并推送

## 2026-09-09 Factory-Discovery semantic calibration

- [ ] 审计 Factory、Discovery、proposal contract、diversity、SuggestionWorkflow 与架构边界
- [ ] 用回归测试锁定 analyst/option false-positive、semantic admission 与 rationale 分层
- [ ] 统一 coverage normalization 并让 Discovery/Factory 共用同一 contract
- [ ] 复核动态 dataset bounded selection 与 incomplete catalog 生命周期；只修有测试证明的问题
- [ ] 完成 full quality gate、doctor/state audit、fresh diff review，并提交推送

## 本阶段当前下一步

先完成目标文件列出的源码与测试审计，记录可复现缺口后再写失败测试。

## 2026-09-09 Factory-Discovery semantic calibration 验收

- [x] 审计 Factory、Discovery、proposal contract、diversity、SuggestionWorkflow 与架构边界
- [x] 用回归测试锁定 analyst/option false-positive、semantic admission 与 rationale 分层
- [x] 统一 coverage normalization 并让 Discovery/Factory 共用同一 contract
- [x] 复核动态 dataset bounded selection 与 incomplete catalog 生命周期；只修有测试证明的问题
- [x] 完成 full quality gate、doctor/state audit、fresh diff review，并提交推送

## 2026-09-09 multi-field relationship contract 收紧

- [x] 审计所有 multi-field template 入口、relationship gate、companion selection 与 proposal validation
- [x] 用失败测试锁定 slot assignment、frequency compatibility、template-specific relationship contract 与 triple confirmation
- [x] 让 Factory 自动路径对 relationship REVIEW/UNKNOWN fail-closed，并补齐 audit metadata
- [x] 完成 bounded companion/performance、绕过审查、完整质量门、提交与推送

## 本阶段当前下一步

已完成关系契约实现、绕过入口回归、完整质量门、只读状态审计，并提交推送；真实工作区仍按既有 BLOCKED checkpoint 保持暂停。

## 2026-09-10 长期自主研究接管

目标：恢复当前未完成研究状态；仅在预检 `READY` 时沿唯一安全入口持续开展有经济机制、稳健、低相关的 Alpha 研究，并记录可复用的研究/工程证据。除用户明确暂停或停止外，不把一轮结束视为任务完成。

- [x] 只读接管：确认 checkpoint、SUBMIT_UNKNOWN、session、锁、进程和 live preflight
- [x] 安全恢复检查：执行只读 reconcile；当前无已有 `progress_url`，无 URL UNKNOWN 禁止重发
- [ ] READY 后：同步必要 Alpha Feed，选择 information gain 最高的 exploration/optimization 方向
- [ ] 研究循环：生成完整实验假设，沿 factory/proposal execution 执行，评估全指标并记录结果
- [ ] 工程证据：按结构化格式记录重复异常、吞吐、无效实验和恢复摩擦；重复证据后再提出局部改进
- [ ] 每轮结束：更新 progress/findings，重新 preflight；BLOCKED 时回到安全恢复阶段

## 当前下一步

下一步：等待用户对无 URL `SUBMIT_UNKNOWN`/控制状态作明确人工处置；在此之前不生成 proposals、不启动 Simulation。

## 2026-09-10 工厂字段生成效率优化计划（只读设计，待实施）

目标：在不放宽字段语义、跨 dataset 关系、表达式去重、quota、checkpoint 或唯一 Simulation 入口的前提下，把“100 个生成 proposal”转化为“可审计、可执行的有效批次”。当前证据为 100 个字段覆盖 6 个 dataset，历史表达式排除后跨 dataset 多字段候选为 0，当前 factory session 尚未预留 Simulation。

### Phase 0 — 观测补全（P0，先做）

- 为每次 probe 记录 discovery 耗时、字段总数/已知数、dataset 数、带明确 frequency 的字段数、模板兼容字段对数、排除表达式数、生成数、跨 dataset 数、gate 错误和新颖表达式数。
- 将“字段发现不足”“关系证据不足”“历史表达式全部排除”“proposal contract 失败”分开，不再统一显示为 `FACTORY_BATCH_NOT_READY`。
- 记录每次 probe 相对上一 probe 的新增字段关系和新增表达式；连续无新增时进入机制级换路，而不是继续等待。
- 验收：诊断只读、不会写 Simulation/checkpoint，不改变 fail-closed 判定；可由单元测试覆盖零字段、零 pair、全排除和成功批次。

### Phase 1 — 先做 pair feasibility，再组装 100（P0/P1）

- 在 `generate_factory_batch` 前按 `(dataset, field_id)` 建索引，先筛选有真实 semantic/frequency/relationship evidence 的跨 dataset field pair/triple。
- 只有确认至少一个可审计 pair 后才进入完整 proposal assembly；否则直接输出诊断并换 discovery route/template pool，避免先生成 100 个注定被拒的 proposal。
- pair 选择采用 dataset-stratified、semantic bucket 和 frequency compatibility 的 bounded sampling；不做窗口、权重、符号或随机参数扫描。
- 保留 exact canonical expression dedupe；换路只能改变经济机制、字段关系或数据来源，不能靠反号或微调制造“新颖性”。
- 目标：每个可执行批次至少 1 个 cross-dataset pair；参考此前成功批次的 20/100，优先恢复可重复的两位数候选而非盲目追求满 quota。

### Phase 2 — 兼容路线与历史排除协同（P1）

- 当当前 bundle 在排除历史表达式后 pair 数为 0，优先请求新的兼容字段组合或新的经济模板族；不要对同一 bundle 仅递增 seed 重试。
- 为每个失败 family 设 bounded retry budget：达到阈值后记录 STOP 原因并换机制（例如 liquidity/dispersion、fundamental/news revision、option relative），不持续微调失败 family。
- 维护“候选 pair → 可用模板 → 被排除原因”的轻量诊断，不把指标、trajectory 或远端结果写入 Alpha Feed metadata cache。

### Phase 3 — 恢复 optimization evidence 链（P1）

- 先审计为什么 round checkpoint 有 DONE 而 live `trajectory_records=0`；补充一个只读、可测试的 handoff/recovery diagnosis。
- 只有真实 trajectory DONE evidence 才生成 CHILD；每个 CHILD 只改变一个经济意义变量，并完整记录 hypothesis、falsification、horizon、self-correlation impact。
- 不把 checkpoint 中的精简状态伪装成 metrics，也不从 Alpha Feed 恢复表达式或证据。

### Phase 4 — 真实 Simulation 与评估（P1）

- 仅在 preflight READY、批次 gate 通过且无未完成 checkpoint/UNKNOWN 时沿 `Agent.run_proposals()` 执行。
- 逐批记录 reserved、DONE/FAILED/UNKNOWN、Fitness、Sharpe、Turnover、Returns、Drawdown、yearly stability、checks、SELF_CORRELATION、复杂度和增量价值。
- 结果按 PROMOTE/CONTINUE/STOP/RECONCILE 分类；缺失或 UNKNOWN 指标保持 UNKNOWN，不进入支持结论或人工审核池。

### Phase 5 — 可观测性与颜色同步（P2）

- 增加 batch/probe 摘要和等待阶段心跳，区分远端 discovery 等待、组装耗时和 Simulation settlement 等待。
- 分组上色继续作为显式 `alpha sync-colors` 工作流，只对已有候选做远端 color metadata 同步；不让 factory 自动写颜色、不把颜色当作 Alpha 质量证据。

### 暂不采取的方案

- 不放宽 cross-dataset gate、frequency REVIEW、semantic UNKNOWN 或 relationship admission。
- 不把 100 拆成绕过原子批次的零散提交。
- 不做窗口/权重/符号暴力扫描、随机参数微调、简单反号或无机制叠加。
- 不在当前运行实例存活期间启动第二个 factory，不手改 `.wqb_state`。

### 成功判据

1. 连续 probe 能报告可解释的 pair/template/排除证据，而非只有统一失败字符串。
2. 可执行 bundle 在组装前能证明至少一个跨 dataset 多字段候选；批次 gate 通过率和每批有效 cross-dataset 数量可统计。
3. 通过的批次真实进入 checkpoint/trajectory，且评估证据完整；未通过的 family 有明确 STOP 或换路记录。
4. 优化层只消费 DONE trajectory，探索层只承担 signal discovery，二者来源和结果可审计。

## 接管证据（2026-09-10）

- live `context --compact` / `state preflight`: `BLOCKED`，`round_11.checkpoint.json` 未完成，`SUBMIT_UNKNOWN=1`，`network_write=false`。
- round 11 checkpoint：`DONE=59, FAILED=8, PENDING=32, SUBMIT_UNKNOWN=1`；未知项 proposal `p-52b9c26b61b4e283` 无 `progress_url`，32 个 PENDING 也均无 `progress_url`。
- `scripts/reconcile_pending.py --timeout 1`：`[SCAN] 0 reconcilable experiments with progress_url`，无远端任务可只读轮询。
- `factory_session.json`：`status=RUNNING` 但 `stop_requested=true`、`last_action=STOP_REQUESTED`；不能在未解决 checkpoint 上清除控制状态或新开轮次。
- `state audit`：`ok=true`、无 errors；doctor 报 `LEDGER_MISSING`、`checkpoint_consistency=UNRESOLVED`，属于恢复证据缺口而非可自动修复项。

结论：保持暂停；不执行 `suggest`、`run-proposals`、`factory run`、`skip-submit-unknown` 或任何 POST。恢复需要用户明确授权的人工处理（确认无 URL UNKNOWN 的处置，并补齐/重建合法 ledger 或按既有 recovery contract 处理）。
