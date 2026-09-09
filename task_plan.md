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
