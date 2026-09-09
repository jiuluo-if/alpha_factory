# 发现记录

## 任务前约束

- 研究状态是事实源；不得手改或删除未完成 checkpoint、trajectory、proposals、submission pool、factory session 或有效锁。
- 默认生产入口是 `python main.py --suggest` → 审阅 proposals → `python main.py --run-proposals`。
- `SUBMIT_UNKNOWN` 不重发，known progress URL 只读对账，缺失证据保持 `UNKNOWN`/`UNAVAILABLE`。
- 用户明确授权删除外部 `F:\\codex\\wqb_alpha_factory\\.wqb_state`；本目录“多余”文件需按证据判定。

## 当前目录快照

- `python main.py --agent-context --compact --json` 返回 `workspace_status=BLOCKED`。
- 阻塞项为 `checkpoint_ledger_mismatch` 与 `ledger_lifecycle_missing_trajectory`；当前 `unfinished_checkpoints=[]`，但不能据此删除状态。
- 快照：`latest_round=2018`、`proposal_count=4`、`trajectory_records=13053`、`submit_unknown=17`、`evidence_cache_entries=93`、`current_best=null`。
- 安全动作明确为先只读对账/恢复阻塞项，不启动 Simulation。

## 最近运行数据（round 2010-2018）

- trajectory：23 条，全部 `DONE`；ledger：274 条，其中 23 个 proposal 完整走到 `simulation_settled`。
- round 2018：4 个候选，3 个进入 Simulation，1 个因 `DIVERSITY_REDUNDANT` 拒绝；3 个均 `DONE`，但 turnover 均为 `1.0`，`HIGH_TURNOVER=FAIL`，`SELF_CORRELATION=PENDING`，`passed=null`。
- round 2018 指标：`rank(ts_delta(fscore_total,64))` Sharpe `0.49`/Fitness `0.05`；`rank(ts_rank(ts_delta(fscore_total,32),63))` Sharpe `68.67`/Fitness `18.84`；复合表达式 Sharpe `18.86`/Fitness `9.55`。后两者同时有 `LOW_SUB_UNIVERSE_SHARPE=FAIL`，均不能视为通过。
- round 2017 的 `rank(ts_delta(fscore_total,32))` 出现 Sharpe `316.22`、Fitness `121.94`、returns `0.1487`、drawdown `0`、turnover `1.0`，但 `HIGH_TURNOVER=FAIL`、`LOW_SUB_UNIVERSE_SHARPE=FAIL`、自相关仍待定；该异常结果只能作为需复核证据，不能作为 current_best。
- round 2018 hypothesis/提案均围绕窗口、时间排名、复合信号；提案全为 `BASELINE` 且 `parent_id=null`、`changed_variable=null`，与“tuning”主线和项目自相关/反参数挖掘约束不一致。

## 根因与运行器问题

- `wqb_agent/agent.py` 的 `_record_live_result()` 在完成时写 ledger 生命周期后调用 `self.trajectory.add(exp)`；实验对象序列化没有 `phase`，因此 trajectory 的 lifecycle projection 为 0。最新 `audit.py` 按 phase 集合对账，故产生 `ledger_lifecycle_missing_trajectory`，属于审计契约/写入模型不一致。
- 历史 checkpoint 的终态集合约 2,622 个，而当前 `trial_ledger.jsonl` 仅 81 个生命周期 proposal；当前 ledger 不是历史 checkpoint 的完整投影，故产生 `checkpoint_ledger_mismatch`。
- `_resolve_1964.py` 是未跟踪的危险临时脚本，包含直接 `_write_proposal_checkpoint(..., complete=True)`，绕过正常对账边界；本次将删除该类临时 helper，不修改既有代码。
- `python -m unittest discover -s tests`：425 tests OK；`compileall` 通过。`ruff check .` 失败 5 项，全部命中根目录未跟踪 helper 脚本（未使用导入/导入顺序），不是正式包代码。

## 清理核准清单

- 删除：`F:\\codex\\wqb_alpha_factory\\.wqb_state`（用户明确指定；包含历史研究状态、checkpoint、trajectory、ledger、cache、reports 和局部 AGENTS）。
- 删除：根目录未跟踪临时 helper：`_analyze_model16.py`、`_build_proposals.py`、`_check_settings.py`、`_check_status.py`、`_debug_fields.py`、`_diag_1964.py`、`_discover_analyst.py`、`_discover_more.py`、`_find_best.py`、`_resolve_1964.py`。
- 删除：可再生构建/缓存物：`__pycache__`、`.ruff_cache`、`alpha_factory.egg-info`、`build`、`.coverage`。
- 保留：正式源码、测试、文档、`AGENTS.md`、`.planning`、配置和版本库；本任务的 `task_plan.md`、`findings.md`、`progress.md` 作为审查记录保留。

## 新约束实现后的诊断结论

- 原 Agent/工厂边界问题：工厂生成的候选会被普通 6/18 上限截断，或者因模板字段类型/布尔条件预检失败后形成部分批次；现在用 100 原子 gate、模板过滤和全量预检阻断该路径。
- 原过拟合问题：自动优化器会泛化地产生 smoothing/window 变体；现在只有 Agent 明确提供非参数化新经济机制、change_type、父 Alpha 证据和反证条件时才生成优化候选，数值-only 变化被拒绝或只能进入明确的 ROBUSTNESS。
- 原结果滞留问题：模拟结果、submission pool、颜色 evidence、trajectory/ledger/memory/context 会形成跨进程本地历史；现在仅保留按纽约本地日轮换的进程内视图，检查点不再包含指标、checks 或 Alpha ID。
- 颜色机制结论：颜色是证据状态分组，不是单一指标分级；提交就绪且增量证据通过为 PURPLE，提交就绪为 GREEN，强信号但证据待定为 BLUE，硬阻塞为 RED，其余为 YELLOW，证据不足返回空值。
- 未执行真实 BRAIN 100 题案远程批次；本轮用真实 `run_proposals` 预检路径和 mock simulator 验证整批原子性，远程请求仍需用户后续按安全入口手工启动/审阅。

## 本次改造诊断

- 选择器原先先按 preferred/category 顺序向前填充，`semantic_random` 只是数据集内部排序扰动；这不能证明多数据集随机探索。现改为数据集级 seed 排序加 round-robin，输出 `dataset_selection` 证据。
- 原字段缓存已有 catalog 读取器但没有生产写入器；现由 discovery 在字段拉取后写入同日 manifest 和每数据集文件，manifest 作为完整性边界。
- 原 `AlphaFactory.assemble_proposals()` 只识别 `s`，且默认模板顺序会把显式双字段模板排除；现支持任意声明的 `s/t` 字段槽，并优先执行显式模板。
- 原 proposal profile 和字段查重仍可能按裸 id 后写覆盖；现保留兼容的 `fields` id 列表，同时通过 `field_refs` 精确定位数据集来源，重复裸 id 无 field_refs 时 fail-closed。
- 工厂的 `datasets` 现在只由实际使用字段画像生成，不再把研究池中未使用的数据集写入每个题案，避免用声明池冒充跨数据集组合。

## 最终验收（2026-09-08）

- 真实 `python main.py --suggest` 退出码 0；返回 100 个字段，6 个数据集分布为 `pv1=13`、`pv13=17`、`option8=18`、`option9=17`、`fundamental6=17`、`news18=18`，且 `(dataset, field_id)` 全部唯一。
- `platform_field_catalog_20260908/manifest.json` scope 为 USA/EQUITY/TOP3000/Delay1，6 个数据集状态均为 KNOWN；状态目录没有 Simulation/Alpha/metrics/submission/color 结果文件。
- fresh review 未发现未修复的 Critical 项；451 tests、compileall、Ruff、diff check 全部通过。验证后已移除 Python/Ruff 生成缓存；没有启动新的 Simulation 或 Alpha 提交。

## 2026-09-09 连续模拟根因核查

- round 2 真实运行在 deadline 后自然退出：checkpoint 为 `complete=false`，最终 `DONE=48, FAILED=9, UNKNOWN=1, PENDING=42`；唯一 `UNKNOWN` 仍有已知 `progress_url`，42 个 `PENDING` 尚未提交，session 为 `DEADLINE/RUN_PROPOSALS_PENDING`。
- 数据流确认：`Simulator._simulate_one()` 对已有 `progress_url` 只轮询；轮询失败耗尽重试后标记普通 `UNKNOWN`。但 `Simulator._pauses_dispatch()` 将所有 `UNKNOWN`（包括已有 URL 的可只读恢复任务）都视为暂停条件，导致一个已知远程作业阻塞其余尚未提交题案；真正不能自动继续的是无 URL 的 `SUBMIT_UNKNOWN`/无 URL `UNKNOWN`。
- 工厂 deadline 不是硬中断：`AIFactoryRunner.run()` 会等待 `Agent.run_proposals()` 返回后再落 session；因此不能在 in-flight 时杀进程或启动新轮。当前状态没有第二个进程、没有 `SUBMIT_UNKNOWN`，可安全保留 checkpoint 等待下一次同轮恢复。
- 待用最小回归先锁定“已知 progress URL 的 UNKNOWN 不阻塞独立 PENDING 派发”；再评估 deadline session 的 unresolved 账目展示，不改写当前真实状态。
- 第二个账目缺陷已复现：新 factory session 从未完成 checkpoint 恢复时，`last_action=RECOVER_CHECKPOINT` 但 `last_round` 保持 `None`，session 无法直接与 checkpoint 对账；最小修复是在恢复分支先写入 `checkpoint_round`，不改变预算或远程执行语义。

## 2026-09-09 颜色/自主优化/本地配额需求诊断

- 颜色分类只在 `run_proposals()` 的整批无 unresolved 分支调用 `_sync_submission_pool()`；存在 `RUNNING/PENDING` 时不会分类。即使整批完成，颜色只进入进程内 `DailyResearchCache`，进程退出后 `--sync-alpha-colors` 无法从不持久化的 trajectory 恢复历史结果。
- 自主优化入口存在，但历史工厂 checkpoint 全为 `BASELINE/EXPLORE`。`optimize_signal_proposals()` 还要求 `DONE`、metrics、字段审计元数据和 Agent 提供的 `child_economic_hypothesis`；工厂本身不生成经济机制，因此 `agent_optimizer/CHILD` 没有触发条件。
- 新需求涉及远程 Simulation 预算。当前阶段按 `weekly_simulation_cap=11200`（`7*1600`）、`daily_simulation_cap=1600`、`America/New_York` 本地日刷新；只保存计数/日期控制元数据，不保存模拟结果，且不能绕过未完成 checkpoint 的预算槽。

## 2026-09-09 真实 round 11 恢复审计

- `python main.py --takeover-preflight --offline` 与 `python main.py --agent-context --compact --json` 均确认 `BLOCKED`，安全动作是先只读对账/恢复，不能启动新 Simulation。
- round 11 的未知提交为 `id=5d49051762fc`、`proposal_id=p-52b9c26b61b4e283`，`status=SUBMIT_UNKNOWN`、`progress_url=null`；它占用 exactly-once 边界，不能自动重发或跳过。
- 同一 checkpoint 还有 3 个已知 URL 的 `RUNNING` 任务和 32 个无 URL 的 `PENDING` 题案。当前 `_resume_proposal_checkpoint()` 仅排除 `SUBMIT_UNKNOWN` 本身，却仍会将其余 `PENDING` 交给 `Simulator.run()`，存在未知 POST 未对账前继续新增 POST 的流程漏洞。
- `scripts/reconcile_pending.py` 只扫描 `trajectory.jsonl`；当前运行时结果/trajectory 不持久化，因此它无法发现仅存在于 checkpoint 的 3 个已知 URL，说明恢复工具也需要与 checkpoint 边界对齐后再进行有效只读对账。
- 最小修复位置是 `Agent._resume_proposal_checkpoint()`：在构造 `runnable` 后、调用 `Simulator.run()` 前检查 `SUBMIT_UNKNOWN`，发现时仅保留带已知 `progress_url` 的任务进入只读轮询，过滤无 URL 的 `PENDING`/未知任务；这样不改变未知提交、不新增 POST。
- 修复后的实际策略进一步细化为：`SUBMIT_UNKNOWN` 阻断无 URL 的 `PENDING`/未知任务，但允许仅带已知 `progress_url` 的任务进入只读轮询；真实 round 11 轮询证明 3 个已知任务均可安全收敛。
- 3 个真实完成结果均为负向/需对账证据，不构成可用 Alpha：Sharpe `0.17、0.24、-0.35`，Fitness `0.04、0.05、-0.13`；分别出现 `LOW_SUB_UNIVERSE_SHARPE` 或 `CONCENTRATED_WEIGHT` 等失败检查，`SELF_CORRELATION` 均仍为 `PENDING`。

## 第三阶段 fresh review 收敛（2026-09-09）

- 独立架构审查无 Critical；发现 1 个 Important：抽离后的 Workflow 漏掉原 Agent 对 `_last_round_skipped` 与 `memory.best_exhausted` 的更新，可能改变后续 suggestion round 的方向耗尽判断。
- 修复方式是向 `ProposalExecutionHooks` 增加两个 operation-shaped hook；拒绝/全跳过分支设置 `_last_round_skipped=True`，产生可执行提案分支设置为 `False` 并重置 `best_exhausted=False`，保持旧顺序和 fail-closed 语义。
- 修复后新增直接 Workflow checkpoint recovery 与 facade 等价性测试；全量 518 tests、compileall、Ruff、doctor/audit、diff check 均通过。

## 配置边界收敛第一阶段发现（2026-09-09）

- 唯一 CLI raw mutation 位于 `main.py:202-203`；normalize 调用在其后，故缺少 `agent` 的配置会以 `KeyError` 泄漏，而不是 `config.agent` 的统一 `ValueError`。
- `wqb_agent/config.py` 的生产 scalar 目前由散落的 `int`/`float`/`max`/`min` 解释；`max_proposals_per_round` 会把 101 静默改为 100，`correlation_refresh_window` 会把 0 静默改为 1，NaN/Infinity 也可能进入 runtime。
- 当前 typed runtime 已是 Agent 的主要消费边界；`AppConfig.agent`/`simulation` 仍是兼容映射，CLI override 应只替换 `runtime.state_dir`，不重建 raw mapping。
- 预算语义：factory/search/research hierarchy 允许非负整数并由 `validate_budget_hierarchy` 约束层级；daily cap 不得超过 weekly cap；example 使用 daily `1600`、weekly `11200`。

## 2026-09-09 第二阶段 CLI 结构化基线

- 当前 Git 与远端均为 `2c6355636cadbbd2d3e95c080fb9ce9b5f7abae6`，工作树干净。
- 全量基线为 `490 tests OK`；`compileall` 和 `ruff check .` 均通过。
- `main.py` 当前把所有动作注册为顶层 boolean flags，并在运行时手写互斥组合判断；诊断分支位于 Agent/WQBClient 构造前，factory stop/status 也位于 client import 前。
- 当前安全顺序必须保留：doctor/audit/preflight/context 不构造 client；suggest 不加 owner lock；sync-alpha-colors 加锁且可 PATCH；factory stop/status 只读本地控制面；run-proposals/factory-run/恢复类动作沿 Agent 安全路径和 owner lock。
- 旧 CLI 引用主要位于 `AGENTS.md`、`main.py`、`tests/test_runtime_safety.py`、`tests/test_agent_context.py`、`findings.md`、`progress.md`；后续文档应以新命令为主并声明兼容窗口。
- 本阶段尚未修改源码；基于 `brainstorming` 架构门，先提交 canonical grammar、legacy normalization 和行为矩阵，待用户确认后再进入 TDD。

## 2026-09-09 第二阶段实现与 review 结论

- `wqb_agent/cli.py` 现在提供 required nested argparse grammar、typed `CLICommand` 和单一 legacy adapter；`main.py` 不再维护 boolean mode explosion 或 new/legacy 两套 dispatch。
- legacy adapter 在 fresh review 中发现并修复了 inline `--run-proposals=PATH` / `--finalize-recorded-round=-1` 兼容缺口；非法 inline 值仍 fail-closed。
- fresh review 还发现 smoke runtime exception 原先返回 0；现保留 `UNAVAILABLE` JSON contract 并返回 runtime failure code 1。
- 活动 README、research prompt、Agent/proposal 用户提示和 CI 已切换到 canonical commands；测试/历史记录中的旧形式仅用于兼容验证或历史事实。
- 最终证据：508 tests OK、compileall 0、Ruff 0、diff check 0；fixtures 上 state doctor/audit/preflight 均返回 0，分别为 `config_valid=true`、`ok=true`、`status=READY`。
- review 未发现 Simulation POST、`SUBMIT_UNKNOWN`、checkpoint recovery、quota、research policy 或 typed config boundary 被触碰；这些路径仍由原有模块和安全测试覆盖。

## 2026-09-09 第三阶段：提案执行工作流抽离基线

- 远端重新确认：`HEAD=origin/main=1b87ce007133010d91cf6ab8e4be8b7423c85295`，提交为 `fix：收敛结构化 CLI 并保留兼容安全边界`，工作树干净。
- 必读执行相关文件的规模已记录：`wqb_agent/agent.py` 2667 行/128083 字符；`simulator.py` 317 行；`checkpoints.py` 140 行；`state.py` 417 行；`trial_ledger.py` 437 行；`proposal_contract.py` 443 行；`research_guard.py` 194 行；`evidence.py` 268 行；`submission.py` 178 行；`runtime_components.py` 131 行。
- `Agent.run_proposals()` 位于 `agent.py:727`；当前直接恢复边界包括 `_load_proposal_checkpoint()`、`_resume_proposal_checkpoint()`、`_write_proposal_checkpoint()`、`_proposal_checkpoint_path()`，并由恢复/维护入口继续调用这些 Agent private methods。
- 当前安全边界：`_resume_proposal_checkpoint()` 对同 checkpoint 的 `SUBMIT_UNKNOWN` 只允许已有 `progress_url` 的任务只读轮询，过滤无 URL 的新 dispatch；`SUBMIT_UNKNOWN` 本身不自动 resend。
- 当前架构边界待验证：新增 workflow 不得 import `Agent`，不得直接调用 `client.submit_simulation`，不得复制 checkpoint store、trajectory 或 trial ledger；远程 POST 继续由 `Simulator`/现有 transport owner 承担。
- 当前不应触碰：`SuggestionWorkflow`、optimizer、CLI、Client、credential/config raw compatibility、state schema、Simulation settings、factory quota 和研究策略。

## 第三阶段实现过程发现

- TDD 红灯为 `ModuleNotFoundError: wqb_agent.proposal_execution`，确认新增 architecture/facade 测试不是误测；实现窄依赖 workflow 后 focused characterization 为 7 tests OK。
- 第一轮定向回归暴露配置快照差异：旧测试在 Agent 构造后修改 `candidates_per_round`，workflow 若只保存初始化值会额外 POST；已增加 `update_agent_config()` 并在 facade 每次运行前同步兼容配置属性，定向 205 tests OK。
- 新 workflow 的 remote execution 仍只调用注入的 `simulator.run()`；源码不 import Agent，也不包含 `submit_simulation(`，checkpoint 仍由注入的现有 `CheckpointStore` 负责。

## 2026-09-09 渐进式工程质量门 baseline

- `git fetch origin main` 后，`HEAD` 与 `origin/main` 均为 `d49287436ad23978bf4ba4b250c16e95290a2ed95`，工作树原有唯一未跟踪文件是质量门设计 spec。
- fresh `coverage run --branch -m unittest discover -s tests`：`595 tests OK`。未配置 source 时用 `--include='wqb_agent/*'` 复核为 10,300 statements / 3,964 branches，statement `80.83%`、branch `69.00%`、combined `77.54%`；配置 `source=["wqb_agent"]` 后会纳入未被测试导入的 `validation.py`，真实 gate baseline 为 10,418 statements / 4,004 branches，statement `79.99%`、branch `68.31%`、combined `76.74%`，故初始 `fail_under=76.0`。
- 生产模块最低覆盖率：`factory_runner.py 50%`、`mutations.py 54%`、`client.py/diversity.py 60%`、`artifacts.py 62%`、`research_api.py 63%`、`context.py 64%`、`__init__.py 64%`、`agent.py 65%`；因此 coverage 不应通过排除低覆盖模块来抬高。
- Ruff dry-run 全规则族：`I=85`、`UP=38`、`B=19`；设计选择的安全子集为 `UP009,UP012,UP017,UP031,UP035,UP037` 共 33 项，`B007,B904` 共 11 项。暂不启用 `UP042`、`B025`、`B905`、`SIM`、`RUF`，避免 Enum、不可达防御分支、zip 长度语义和大范围判断式改写。
- 候选 9 模块 mypy 首次运行只报传递依赖 `wqb_agent/client.py` 缺 `requests` stubs；声明 `types-requests` 后再复测，不改 Client 网络/重试行为。
- Ruff B904 的生产/脚本命中为 `scripts/archive_completed_rounds.py:118`、`wqb_agent/agent.py:513`、`wqb_agent/search_policy.py:42`；需要逐处确认使用 `from exc` 或 `from None`，不改变异常类型或 fail-closed 语义。
- `python -m pip install ".[dev]"` 在当前环境的 build isolation 阶段因镜像下载 `setuptools>=68` HTTP 403 失败；不是项目构建/测试失败，后续改用当前工具环境验证并保留 CI 声明。
- 首次输出 typed frontier 上下文的 PowerShell 命令因路径变量后紧跟冒号触发 ParserError；未修改仓库，改用 `${f}` 变量边界后继续。
- 清理多个 coverage 生成物的批量 PowerShell 删除命令被执行策略拒绝；文件均为本轮明确生成的单个 artifacts，改为逐个明确路径处理。

## 2026-09-09 质量门实现与验收

- `pyproject.toml` 已启用 `branch=true`、`source=["wqb_agent"]`、`show_missing=true`、`precision=1`、`fail_under=76.0`；真实 configured baseline 为 statement `79.99%`、branch `68.31%`、branch-aware `76.74%`。
- mypy 已加入 dev extra（含 `types-requests`），9 个 typed frontier 模块最终 `Success: no issues found in 9 source files`；未启用全仓 strict、blanket ignore 或 baseline ignore 文件。
- Ruff 最终规则为既有 `E4,E7,E9,F` 加 `I`、`UP009,UP012,UP017,UP031,UP035,UP037`、`B007,B904`；dry-run 后全部通过。没有启用 `ALL`、`SIM`、`RUF`、`UP042`、`B025`、`B905`。
- CI 已统一为 install → compile → type → unit → Ruff → branch coverage/report → doctor → audit；Coverage 命令使用 `coverage erase` 和 `coverage run --branch`，低于配置阈值会返回非零。
- fresh verification：compileall exit 0；mypy exit 0；Ruff exit 0；`595 tests OK`；configured coverage `76.7%` 且 report exit 0；fixture doctor `config_valid=true`/exit 0；fixture audit `ok=true`/exit 0；compact context exit 0；`git diff --check` exit 0。
- fresh review 未发现 Critical/Important；92 个 tracked 文件中多数仅为 import/安全现代化机械修复，手工改动集中在 typed annotations、等价格式化、B007 变量命名和 `from None` 异常包装。未触碰 Client retry、Simulation、SUBMIT_UNKNOWN、checkpoint、credentials source 选择、Alpha Feed/Color 或研究政策。
- 默认 `python main.py context --compact --json` 仍报告既有真实 `.wqb_state/round_11.checkpoint.json`、`submit_unknown=1`、`workspace_status=BLOCKED`；本阶段未修改该研究状态，也未启动 live BRAIN/Simulation。
