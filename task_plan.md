# 任务计划：运行数据审查、清理与工厂/Agent 边界修复

## 2026-09-12（当前阶段）Phase V Metric-Aware Bounded Optimization（PAUSED/DISARMED，未运行真实 Simulation）

- [x] 只读复核 HEAD `97645b0`，把 8 个真实缺口与设计决定写入 `findings.md`
- [x] 新增唯一 pre-correlation 准入门槛 `wqb_agent/pre_correlation.py`（delay-aware、结构化报告）
- [x] Agent 自动路径与 `scripts/refresh_self_correlation.py` 共用同一 selector（一致性测试）
- [x] `_alpha_rating()` 变 delay-aware；未知 delay 不晋级
- [x] `AlphaTemplate` 显式 numeric slot + 单变量 variant（无笛卡尔积、safety constant 不轮换）
- [x] `OptimizationDecision` VALIDATE 单变量 contract + Python 有界候选池
- [x] `AlphaFactory.validation_proposals()` 只产出 ROBUSTNESS proposal
- [x] `OptimizerWorkflow.optimizer_context()` + `metric_optimization_context` 接入 suggestion bundle
- [x] 测试：`tests/test_pre_correlation.py` 与 optimizer context / bundle 契约测试
- [x] 全量质量门：`833 tests OK`、compileall exit 0、Ruff（排除 7 个未跟踪用户分析脚本）All checks passed、
  mypy 9 frontier Success、coverage branch-aware 79.8%（`fail_under=76.0`）、
  offline `state doctor` / `state audit` / `context --compact` exit 0
- [x] 文档同步（findings / progress / task_plan / RESEARCH_POLICY / ARCHITECTURE_AGENT / prompts）
- [x] 提交并推送：`2ce1f87`（前置准入与有界验证变体）、`00a5672`（文档）；`git ls-remote origin main`
  在推送 `00a5672` 时与本地 HEAD 相同（本收尾提交只回填记录）
- [x] 记录 `TARGETED_OPTIMIZATION_BATCH_BLOCKED_BY_FACTORY_BATCH_CONTRACT`（不绕过 100 契约）
- [x] 审计轮：turnover 准入区间收敛为 `pre_correlation.turnover_bounds()` 单一来源，Agent 复用（`ea38933`）
- [x] 审计轮：补齐 numeric variant 同一性/去重/预算测试与 §44/§50 准入缺口测试（`841 tests OK`）
- [x] 审计轮：只读核对 §55 VALIDATION 配额 owner 与 §56 factory batch mode 保护结论
- [x] 审计轮质量门：compileall、Ruff、mypy 9 frontier、coverage 79.8%、offline doctor/audit/context exit 0
- [x] 审计轮提交与推送：远端 SHA == LOCAL_HEAD

## 2026-09-12（前序）Phase III Autonomous Optimization（PAUSED/DISARMED，未运行真实 Simulation）

- [x] 只读复核 HEAD `43654c4` 的上一轮修复（Trajectory persist / checkpoint / Alpha Feed / optimizer gate）并写入 findings
- [x] 先写真实顺序测试证明根因（early DONE append → late settlement → restart 丢 FINAL 字段）
- [x] 实现 append-only `RESEARCH_SETTLED` revision（`Trajectory.settle/settle_many/find_row`，fail-closed、幂等、owner 合并读），`add()` 语义不变
- [x] 生产接入 `Agent._settle_research_outcome()`，拒绝时 `SETTLEMENT_REVISION_REJECTED` 审计，不静默
- [x] 建立正式 `OptimizationDecision` 契约（CHILD/VALIDATE/REROUTE/STOP + rejection taxonomy + opportunity hint + 有限 summary）
- [x] 拆分 optimizer gate 两阶段并给出 Agent Optimization Yield funnel（分母 0 → `None`）
- [x] 提供 Agent-facing `inspect_optimizer_parents()` / `propose_optimization()`，仍走唯一 `OptimizerWorkflow → AlphaFactory` 路径
- [x] ResearchYield 同步新 funnel（`agent_reviewed_parents` / `agent_child_decisions` / 两个新 conversion）
- [x] Incremental Capability Audit（只读）：平台无 PnL/行为序列能力 → `UNAVAILABLE` + `child_generation_bound()` 有界多代
- [x] 真实多代 restart 验收测试（P0 settled → 重启 → C1 proposal → C1 settled → 重启 → C2）
- [x] 质量门：`794 tests OK`、compileall、Ruff、mypy 9 frontier、coverage branch-aware 79.3%（`fail_under=76.0`）、offline doctor/audit exit 0
- [x] 完成度审计：真实 `AlphaFactory` 上复现并修复 CHILD 提案缺 `parent_id` / `economic_mechanism` /
  `optimization_decision`，以及 `change_type` / `direction_transform` 与 proposal contract 的同义值断裂；
  新增真实 factory 端到端测试（decision 路径 + legacy 路径，`validate_proposal` 零问题）
- [x] 质量门（修复后 fresh）：`797 tests OK`、compileall exit 0、Ruff All checks passed、mypy 9 frontier
  Success、coverage branch-aware 79.3%（`fail_under=76.0`）、offline `state doctor` / `state audit` exit 0
- [x] Git：`88fa066` `fix：补齐 CHILD 提案的 parent 溯源与提案契约一致性`；remote SHA == LOCAL_HEAD
  （`88fa066848c19bcd33c6e53ba035f2e050d6c683`）
- [x] 更新 docs（ARCHITECTURE_AGENT / RESEARCH_POLICY / STATE_LAYOUT）与 findings/progress/task_plan
- [x] 经用户授权后 commit 并 push 三笔（`d24368f` / `d81f896` / `5c34cd7`），`git ls-remote` 核对远端 SHA 与本地 HEAD 一致

## 2026-09-11（completed）ResearchYield 派生研究产出（PAUSED/DISARMED 只读）

- [x] 吸收 `docs/RESEARCH_ISSUES_2026-09-11.md` 与 findings/progress/task_plan，先写真实审查结论到 findings.md
- [x] 实现 `wqb_agent/research_yield.py`：派生 control-plane 漏斗 + 5 态 family outcome + 明确 denominator 的 conversions + evidence-quality 分离 + STOP taxonomy
- [x] 新增 `tests/test_research_yield.py`（30 契约测试）与 `tests/test_architecture.py` research_yield 守卫（33 架构测试）
- [x] 只读真实回放脚本 `scripts/replay_research_yield.py`（读 13 个 checkpoint + proposals.json + r11/r12 metrics 快照，不写 `.wqb_state`）
- [x] 全量质量门：`732 tests OK`、compileall OK、Ruff All checks passed
- [x] 更新 docs（ARCHITECTURE_AGENT / RESEARCH_POLICY / STATE_LAYOUT）与 task_plan/progress/findings
- [x] 已 push；提交遵循 AGENTS 规则（邮箱 `2966684515@qq.com`、中文前缀信息）

## 2026-09-11 当前阶段：跨进程 optimizer parent evidence handoff（PAUSED/DISARMED，未运行真实 Simulation）

- [x] 只读调查真实 `.wqb_state` 与源码，确认断点根因（`Trajectory(persist=False)` 使 canonical 完成证据不落盘，checkpoint 只有执行事实）并写入 `findings.md`
- [x] 最小修复 `wqb_agent/runtime_components.py`：让既有 `Trajectory` owner 持久化到 `trajectory.jsonl`；不新增 store/owner，不从 checkpoint 或 Alpha Feed 重建 metrics
- [x] 按新契约更新 `tests/test_factory_boundaries.py` 两条旧断言（canonical 证据落盘并由新进程只读 rehydrate；派生结果侧车仍只在内存）
- [x] 新增 `tests/test_historical_parent_handoff.py`（restart/serialization/dedupe/corrupt/lineage 契约）与 `tests/test_architecture.py` color 不得驱动 optimizer/yield 守卫
- [x] 只读 replay 增加 handoff before/after 视图（`scripts/replay_research_yield.py --compare-handoff`）
- [x] 同步 docs（ARCHITECTURE_AGENT / RESEARCH_POLICY / STATE_LAYOUT）：evidence owner 不变，仅新增跨进程只读 rehydrate 说明
- [x] 质量门：`750 tests OK`、compileall、Ruff、mypy 9 frontier、coverage 78.9%、offline doctor/audit 全通过
- [x] 经用户授权后 commit（`fix：恢复跨进程 optimizer parent 证据并补齐 handoff 契约`）并 push，远端 SHA 与本地 HEAD 一致（详见 `findings.md`“验证结果（第二阶段）”）

## 2026-09-10（historical）机制换路与 DONE→Optimizer

- [x] 读取 pasted task、重审远端/本地状态与既有 P0 实现
- [x] 先写红测试并确认缺口
- [x] 实现有界 feasibility route decision 与机制族耗尽分类
- [x] 收紧本地 DONE parent evidence gate，记录 handoff 计数/拒绝原因
- [x] 完成全量验证、fresh code review、提交并推送每个验证阶段
- [x] 交付 start/current/remote SHA、未启动真实 Simulation、checkpoint/SUBMIT_UNKNOWN 不变及 deferred 范围

## 阶段结果

- [x] start SHA `ba919da7b6a2ea1be509d7b3c5fe3e67c8e14714`
- [x] route commit/push `b104b81f77274f173488557333dd909934733454`
- [x] handoff commit/push `2cca40741ed70a57fb54194bc5eea56e9b0c41dd`
- [x] current local/remote SHA 已一致；真实 Simulation 未运行，checkpoint 与 `SUBMIT_UNKNOWN` 未改变

## 2026-09-10 Feed 与 heartbeat 阶段

- [x] 重审远端、调用图、cache/lock/failure 边界并写 findings
- [x] 先写 freshness、failure、Feed split heartbeat、fake-clock throttling 红测试
- [x] 实现 Agent lifecycle refresh hook 与 typed interval
- [x] 实现 transient heartbeat 及 Discovery/Feed/assembly/settlement 接入
- [x] 完成 full quality gates、architecture review、两阶段 commit/push 与 SHA 对账

## 阶段结果

- [x] freshness policy 使用 typed `alpha_feed_refresh_interval_sec`，默认 3 小时且正值有界
- [x] Feed 只读、失败保留旧成功时间、单进程 lifecycle hook、CLI lock
- [x] transient heartbeat 通过 fake clock 节流并覆盖主要等待阶段
- [x] full tests/coverage/compileall/Ruff/mypy/architecture/diff check 已通过
- [x] 依次完成 Feed 与 heartbeat 两个 commit/push，并核对 local/remote SHA

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
# 2026-09-10 当前远端重审与 feasibility 诊断阶段

- `git fetch origin` 后确认 `main`、本地 HEAD、`origin/main` 均为 `e9037d1`，工作树初始干净。
- `context --compact` 为 SAFE、无未完成 checkpoint、`SUBMIT_UNKNOWN=0`；未启动真实 Simulation。
- 已实现 frequency evidence 分级、bounded `assess_feasibility()` 和 assembly 前 runner 接入；质量门、fresh review、commit 和 push 已完成。

# 2026-09-10 Alpha Factory 端到端审计与测试瘦身

## 目标

审计完整 Alpha Research Loop，验证研究上下文、语义机制、budget、optimizer、evidence 与 route 的真实集成；只修复有证据的 P0/P1/P2 问题，并清理重复或实现细节绑定的测试。禁止真实 Simulation。

## 阶段

- [x] 建立基线与端到端调用图，核对当前工作树和关键安全状态
- [x] 审计 research context → proposal → budget 的真实链路
- [x] 审计 semantic identity、optimizer lineage、scarcity/route 与 evidence 闭环
- [x] 盘点测试价值，设计最小合并/删除与真实集成回归
- [x] 实施有证据的 production 修复与测试瘦身
- [x] 完成质量门、Test Audit、fresh review、提交推送与 SHA/CI 对账

## 约束

- 保留 SUBMIT_UNKNOWN、checkpoint/quota exactly-once、evidence fail-closed、手工 Alpha submission 等核心边界。
- 不以 coverage 或测试数量为目标；删除测试前必须有高层契约覆盖或明确低价值理由。
- 不修改 WQBClient transport、checkpoint ownership、Discovery pagination、Reflector confirmation、field taxonomy、relationship contract，除非审计发现真实 regression。

## Next Step

已完成全量质量门、fresh review 与 Test Audit；待提交推送后轮询对应 CI run。

# 2026-09-12 Phase VI：Autonomous Optimization Control Loop Repair

## 目标

修复 Phase V metric-aware optimizer 在真实控制链上的断点，使
`blocker → Agent 决策 → CHILD/VALIDATE → evidence → SELF_CORRELATION → 下一步` 一致。

## 阶段

- [x] 先只读复现 P0-A/P0-B/P0-C/P0-D/P1-A/P1-B/P1-C/P1-D 并把结论写入 `findings.md`
- [x] P0-A 结构可修 parent 不再被 health gate 杀死（且仍不可提交）
- [x] P0-B generation bound 读取真实 CHILD history
- [x] P0-C resolved SELF_CORRELATION 进入下一步判断且同进程不重复 GET
- [x] P0-D research_api canonical reads
- [x] P1-A universe VALIDATE bounded + old_value provenance
- [x] P1-B historical SELF_CORRELATION backfill window
- [x] P1-C targeted optimization batch arbitration
- [x] P1-D 工厂不伪造 Agent decision（回归测试固定）
- [x] P2 模板 numeric literal 显式分类审计
- [x] 文档（findings/progress/task_plan、ARCHITECTURE_AGENT、RESEARCH_POLICY、prompts）
- [x] 全量质量门（`861 tests OK`、compileall 0、mypy 9 frontier Success、Ruff passed、
      coverage 79.9% ≥ 76.0、state doctor/audit/context exit 0）
- [x] 提交（`6c0e4e6` 代码与测试、本笔文档）并按主题拆分推送，核对 `REMOTE_SHA == LOCAL_HEAD`
- [x] 复检 P0-C：结构 blocker 优先级高于 resolved PASS（`_next_action()` 顺序修复）
- [x] 端到端离线验收链 `TestStructuralRepairChainEndToEnd` + 复跑质量门（`862 tests OK`、coverage 79.9%）
- [x] 端到端链 1 补齐 `SELF_CORRELATION_REPAIR` 投影断言；链 2 纳入已结算 P0 父代
- [x] 锁定 `generation_bound.allowed==false → STOP` 映射并复跑质量门（`863 tests OK`、coverage 79.9%）
- [x] 修复执行侧真实断点（终态表达式排除 parent、targeted envelope 缺字段画像）并新增单路径执行验收
- [x] CHILD/VALIDATE 两条生成路径均复用 `_optimization_exclusions()` 豁免，并补 VALIDATE 真实 Agent 验收

## 约束

- 禁止真实 Simulation / run-proposals / factory run / Alpha submission / remote color write；
  只允许 fixtures、synthetic Experiment、offline AlphaFactory 与只读历史证据。
- 不新增 reward engine、scheduler、trajectory/checkpoint owner、第二 inbox 或第二 Simulation path。
