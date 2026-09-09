# 进度日志

## 2026-09-08

- 已读取项目 `AGENTS.md`。
- 已完成相关长期记忆快速检索。
- 已读取 self-evolution、planning-with-files、systematic-debugging、verification-before-completion；Superpowers 实际路径已纠正。
- 当前只读接管，尚未删除或修改研究状态。
- 离线 agent context 已运行：状态为 `BLOCKED`，发现 checkpoint/ledger 不一致和 ledger 生命周期缺 trajectory；尚未触碰状态。
- 已完成数据审计和根因追踪；已确认 2017-2018 异常指标、高换手失败、自相关待定、参数扫描式提案及临时脚本问题。
- 测试基线：425 tests OK；compileall 通过；ruff 失败 5 项且全部来自待删除的根目录临时 helper。
- 已按固定清单删除 `.wqb_state`（674 个文件，71,409,762 bytes）、10 个临时 helper，以及 root 构建/缓存/coverage；合计 16 个目标、72,146,606 bytes。
- 删除脚本执行后已移除自身；未删除正式源码、测试、文档、配置和 `.planning`。
- 清理验证阶段复跑：425 tests OK、ruff 0 errors、compileall 退出码 0；随后移除验证生成的 92 个 Python/cache 目标及临时验证脚本。
- 末次核验发现测试曾重建空的 root `.wqb_state` 目录；已确认无文件、无活动 Python 进程后再次删除，之后不再运行会触发默认状态目录创建的命令。

## 新阶段结果

- 已实现 `America/New_York` 本地日内存缓存；跨纽约午夜自动丢弃模拟、已提交 Alpha 和颜色视图，运行时不写结果侧车。
- 已实现工厂 `factory_100` 原子批次：固定 100 个、批内唯一、来源合法、全量预检通过后才允许进入 `Agent.run_proposals()`；不足 100 或任何成员失败均整批阻断。
- 已拆分职责：Agent 只输出有完成证据、明确新经济机制的优化题案；工厂负责经过核验字段上的有限经济模板广度；数值窗口/权重/符号扫描不能伪装成新 Alpha。
- 已接入 Alpha 颜色分组：基于真实健康、质量、自相关、年度稳定性和增量证据给出 GREEN/PURPLE/BLUE/YELLOW/RED；颜色证据只进当日内存缓存，颜色同步仍不提交 Alpha。
- 已将运行期 trajectory、trial ledger、experience、context、simulation results、submission pool 和 color sidecar 改为非持久；检查点只保留恢复/去重身份和已知 progress URL，不保留指标、checks 或 Alpha ID。
- 回归证据：`python -m unittest discover -s tests` 为 439 tests OK；`compileall` 退出码 0；Ruff 全部通过；随后已删除本轮验证重建的根 `.wqb_state`、5 个 `__pycache__` 和 `.ruff_cache`。

## 连续模拟阶段（2026-09-08）

- 已开始真实多轮运行前的只读接管检查。
- 第一次 preflight 命令误将 `--compact --json` 与 `--takeover-preflight` 同时传入，CLI 拒绝；入口要求 compact/json 只能和 `--agent-context` 联用。已改为合法命令，未发生 Simulation 或远程写入。
- 平台字段查重根因：`FieldDiscovery` 命中本地 `fields_cache.json` 时不会重新取得平台 `alphaCount`，且旧路径只读取 `alphaCount` 驼峰键；这使不保留本地 Simulation/Alpha 结果后，字段使用量可能过期或被漏判。
- 已加入只读平台字段使用刷新：生产配置对当前研究数据集重新请求 `/data-fields`，用 `alphaCount` 覆盖本地字段缓存，仅保留字段发现缓存，不保存模拟结果；缺计数在严格模式下为 UNKNOWN 并阻断。
- 新增回归测试覆盖“平台 99 覆盖本地 1 并排除”及“平台缺计数 fail-closed”；验证结果为 442 tests OK、compileall 通过、Ruff 通过。
- 真实工厂运行 `python main.py --factory-run --factory-hours 0.5` 仍在进行：第 1 批 100 个已进入检查点，最近状态为 `DONE=14, FAILED=3, PENDING=80, RUNNING=3`；未出现 `sims_results.json`、`trajectory`、`trial_ledger`、`submission_pool` 或颜色侧车。
- 后续轮询观察到该批进入 `DONE=50, FAILED=12, PENDING=35, RUNNING=3`；0.5 小时 deadline 已到但 `run_proposals()` 仍在等待在途平台任务，控制面尚未落定。这是需交给后续 Agent 修复的时限边界问题：截止时间可阻止新轮，但不能安全中断已提交任务。
- 最后观察到 `DONE=56, FAILED=15, PENDING=26, RUNNING=3`；远程进程仍存活，故保留 `.wqb_state` 当前检查点，不宣称本轮已完成。
- 第 2 轮真实 `--suggest` 已验证平台刷新：返回 100 个字段，`brain_api` 快照时间为 `2026/9/8 14:14:32`；随后发现 `platform_usage_by_field` 曾按裸字段名合并不同数据集的同名字段，已改为 `(dataset_id, field_id)` 分层映射并新增回归测试。

## 多数据集字段目录与通用多字段模板（2026-09-08）

- 已将 discovery 改为可复现 seed 驱动的多数据集分层轮询；显式单数据集仍保持单数据集意图，显式多数据集、配置池和分类池不再由第一个数据集独占目标数量。
- 已加入 `platform_field_catalog_YYYYMMDD/` 元数据快照：manifest 记录 USA/EQUITY/TOP3000/Delay scope、抓取时间、数据集字段数量、字段哈希和 alphaCount 状态；不含 Simulation、Alpha、metrics 或提交结果。
- 已修复 discovery 选择与 Agent proposal profile 的裸 field id 合并风险，使用 `(dataset, field_id)` 内部身份；proposal 对多字段候选携带 `field_refs`。
- 已新增通用模板：`{data_field}` 主字段别名、`{s}` 双字段和 `{t}` 三字段槽位；`low`/`high`/`close`/`volume` 仅作为真实平台字段的语义示例，不再硬编码。
- 双字段模板在有跨数据集候选时优先选择类型兼容的其他数据集；工厂统计记录主数据集分布、字段数据集分布、模板数、双/多字段数及跨数据集组合数。
- 生产配置已启用 `dataset_sampling=stratified`、6 个数据集池、`min_datasets=3`、`min_cross_dataset_pairs=1` 和 `persist_catalog=true`；批次 gate 会拒绝不满足真实覆盖的 100 题案。
- 最终只读现场验证：`python main.py --suggest` 退出码 0，返回 100 个字段、覆盖 `pv1=13`、`pv13=17`、`option8=18`、`option9=17`、`fundamental6=17`、`news18=18`，100 个 `(dataset, field_id)` 唯一键；策略为 `stratified_round_robin`。
- 同日字段目录 manifest 已核验为 USA/EQUITY/TOP3000/Delay1，6 个数据集均为 KNOWN，且 `.wqb_state` 未发现 Simulation/Alpha/metrics/submission/color 结果侧车。
- 最终回归：`python -m unittest discover -s tests` 为 451 tests OK；`compileall`、Ruff、`git diff --check` 均通过；未启动新的 Simulation 或 Alpha 提交。
- 最终清理：删除本轮验证生成的根目录、`scripts`、`tests`、`wqb_agent` 下 `__pycache__` 及根 `.ruff_cache`；复查无残留，`.wqb_state` 仅保留检查点、字段目录、建议/工厂会话和字段元数据缓存。

## 连续模拟接管（2026-09-09）

- 只读接管复核：PID `31780` 仍存活；`factory_session.status=RUNNING`、`last_round=2`、`rounds_completed=0`，未启动第二个进程。
- `round_2.checkpoint.json` 仍为 `complete=false`，当前计数 `DONE=46, FAILED=9, RUNNING=3, PENDING=42`；3 个在途实验均保有已知 `progress_url`，未发现 `SUBMIT_UNKNOWN`，因此继续等待自然收敛，不重 POST、不改写 checkpoint。
- 轮询进程退出后的最终对账为 `DONE=48, FAILED=9, UNKNOWN=1, PENDING=42`；session 为 `DEADLINE/RUN_PROPOSALS_PENDING`，checkpoint 仍未完成，唯一 `UNKNOWN` 保有已知 URL，未发现 `SUBMIT_UNKNOWN`。
- 根因验证后新增最小回归：已知 `progress_url` 的普通 `UNKNOWN` 只需只读恢复，不应阻塞独立 `PENDING` 题案；保留无 URL 的 `SUBMIT_UNKNOWN` 暂停语义。`tests.test_simulator` 当前 12 tests OK。
- 新增并先失败后通过的 session 账目回归：从旧 deadline session 恢复未完成 checkpoint 时，`last_round` 记录实际 checkpoint round；当前隔离测试通过。
- 第二次全量验证首次因架构测试要求 `simulator.py` 保留 `UNKNOWN_STATUSES` canonical import 而失败；已恢复该共享集合并保留“有 URL 的 UNKNOWN 不暂停、无 URL/`SUBMIT_UNKNOWN` 暂停”分支，随后 `python -m unittest discover -s tests` 为 458 tests OK，compileall 与 Ruff 均通过。
- 修复后恢复运行：round 2 从 `DONE=48, FAILED=9, UNKNOWN=1, PENDING=42` 自然收敛为 `complete=true, DONE=85, FAILED=15`，无 UNKNOWN；session 记账为 `rounds_completed=1, reserved=100`，随后按唯一入口进入 round 3。
- round 3 已建立固定 100 题案 checkpoint，session `reserved=200`，当前仍在 deadline 后等待已提交批次自然收敛，最近只读状态为 `DONE=27, FAILED=3, PENDING=67, RUNNING=3`，无 `SUBMIT_UNKNOWN`，未启动新轮。
- 目标更新后已按 `config.json` 的 `max_runtime_sec=86400` 重新启动持续工厂：新 session `RUNNING`、round 4、reserved=100；当前 `DONE=2, PENDING=95, RUNNING=3`，retry=0，未发现新的运行时错误。
- 持续会话最新只读状态：round 4 `DONE=10, FAILED=1, PENDING=86, RUNNING=3`，session `RUNNING`、`rounds_completed=0`、`simulations_reserved=100`、`retry=0`，Python PID 4900 存活，未发现新的工程运行时错误或 `SUBMIT_UNKNOWN`。
- 持续会话最新只读状态：round 4 `DONE=31, FAILED=5, PENDING=61, RUNNING=3`，session `RUNNING`、`rounds_completed=0`、`simulations_reserved=100`、`retry=0`，Python PID 4900 存活；新增 FAILED 项均保有 progress URL 且 `error=null`，未发现工程运行时错误或 `SUBMIT_UNKNOWN`。
- 持续会话最新只读状态：round 5 `DONE=25, FAILED=6, PENDING=66, RUNNING=3`，session `RUNNING`、`rounds_completed=1`、`simulations_reserved=200`、`retry=0`，Python PID 4900 存活；最新 FAILED 项均保有 progress URL 且 `error=null`，未发现工程运行时错误或 `SUBMIT_UNKNOWN`。

## 2026-09-09 新需求：设计确认中

- 已核查颜色分类、自主优化和工厂预算调用链；未修改代码，未启动 Simulation。
- 设计建议：settle 后即时颜色视图、整批收尾重算；Agent 只在有合格 DONE parent 和 `child_economic_hypothesis` 时生成 CHILD；新增按纽约本地日刷新的周预算控制。
- 用户已确认当前阶段周上限按 `7*1600=11200`，每日上限 `1600`，按 `America/New_York` 本地日刷新；进入实现与分批上传阶段。

## 2026-09-09 自主模拟双层实现

- 已新增优化层代码初筛、Agent 经济机制/反过拟合二筛；云端轻量 Alpha 元数据仅提升已有本地完成证据的优先级。
- 已新增探索层稳定种子随机化字段/经济模板组合，并标记 `signal_discovery`；未引入参数、窗口、权重或符号扫描。
- 已将双层来源、目标和策略写入 `factory_batch_stats`/当前 proposals 审计视图，仍复用 `Agent.run_proposals()`。
- 新增回归后全量测试为 478 tests OK；fresh review 无 Critical，compileall、Ruff、diff check 均通过；代码与文档已分两批推送到 `main`，远端核验 SHA 为 `372f438372a69e073bc28c1a13ad29a755d3aa4f`。
