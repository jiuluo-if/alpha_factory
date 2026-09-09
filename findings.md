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
