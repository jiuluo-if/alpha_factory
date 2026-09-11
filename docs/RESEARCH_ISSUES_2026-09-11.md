# 研究过程问题整理汇总（2026-09-11）

范围：本次自主 Alpha 研究 campaign（rounds 1-13，factory sessions `e6ec7891`/`6df26582`/`dca94762`/`89c78860`/`3a803043`/`a4a3f3ac`/`5d895622` + Agent 自编批次 round_8/10）。
所有条目基于 `findings.md`、`progress.md`、各 round checkpoint 与执行日志；未验证的标注"待验证"。

## 1. 平台语法 / 参数个数拒绝（rounds 1-4 的 FAILED 根源）

BRAIN live response 高于静态 cheatsheet；本项目 42+20+32+15 条平台拒绝全部归因于 7 个算子用法。修复后 rounds 5/6/11/12 连续 4 批 100/100 零拒绝。

| # | 被拒用法 | 平台错误 | 发现轮次 | 处置 | 状态 |
|---|---|---|---|---|---|
| 1 | `normalize(x, true, 0.0)`（3 参） | `exactly 1 input` | r1 | 模板改 `rank(winsorize(ts_delta({p},5)))` | 已修复，live 验证 |
| 2 | 裸位置参数 `gaussian`（quantile 驱动） | `unknown variable "gaussian"` | r1 | 模板改 `rank(ts_zscore(ts_delta({p},5),60))` / `rank(ts_rank(ts_zscore({p},20),60))` | 已修复，live 验证 |
| 3 | `group_rank(rank(group_backfill(X,g,20,4)),g)` | `exactly 2 inputs` | r1 | 模板改 ts_backfill+group_mean+subtract | 已修复（后见 #7 再修） |
| 4 | `winsorize(X, 4)`（双参） | `exactly 1 input` | r4 | 单参 `rank(winsorize(ts_delta({p},5)))` | 已修复，live 验证 |
| 5 | `hump(X, 0.01)`（双参） | `exactly 1 input` | r4 | 单参 `hump(rank(ts_delta({p},5)))` | 已修复，live 验证 |
| 6 | `ts_regression(..., lookback=0)` | `invalid value "0" for attribute "lookback"` | r4 | 省略 lookback 的 3 参形式 | 已修复，live 验证 |
| 7 | `group_mean(X, G)`（2 参） | `exactly 3 inputs` | **r9（Agent 批次 E2）** | 3 参 `group_mean(X, 1, G)`（与 r1-r7 group_scaled_mean 38 次 DONE 对齐）；**同时暴露 round_4 的 `group_filled_rank` 修复写成了 2 参（潜在 bug）**，已修正 | 已修复，r11/r12 批量验证 |

教训：静态算子文档（cheatsheet）的 arity 与 USA/EQUITY/TOP3000/Delay1 region 实测不一致；`docs/reference/OPERATORS_CHEATSHEET.md` 已维护"平台实测拒绝记录"表 + 全注册表 arity 测试守卫（`tests/test_factory_boundaries.py::TestTemplateLiveOperatorEvidence`），新模板只用已实证算子。

## 2. 工厂路由 / 门禁失配

| # | 现象 | 根因 | 处置 | 状态 |
|---|---|---|---|---|
| 8 | round_3 工厂 `STOP_MECHANISM_ROUTE`（3 条 bounded route 全部 `NO_INFORMATION_GAIN`，0 模拟消耗） | 收紧后关系契约下 256 个 cross-dataset 对 0 ALLOW（86 REVIEW / 86 UNKNOWN / 170 INCOMPATIBLE；82/100 字段缺显式 frequency），而 `min_cross_dataset_pairs=1` 门禁要求 ≥1 对 | `config.json` `min_cross_dataset_pairs` 1→0（保留 `min_datasets=3`），rationale 记录在案 | 已修复，r4-r7 恢复出批 |

## 3. 恢复边界与状态面问题

| # | 现象 | 根因/机制 | 处置 | 状态 |
|---|---|---|---|---|
| 9 | 某 UNKNOWN 模拟卡在 progress 0.1 超 2h | 远端作业停滞（STALE） | 3 次只读 reconcile 记录在案后经授权 `recovery skip-stale` 跳过（既有 CLI，min_attempts=3） | 已处置（r2） |
| 10 | SUBMIT_UNKNOWN `p-8b55502e89a6cc12`（pcr_vol_all，r3） | POST 结果含糊且无唯一远端身份 | 重复只读对账后经授权 `recovery skip-submit-unknown` 跳过（冻结契约：不重 POST） | 已处置（r3） |
| 11 | **无 URL UNKNOWN** `0db18e84c686`（pcr_vol_all downside_risk，r7，proposal `p-3d87af4949987b88`） | ambiguous-POST 家族：有 `submission_started_at` 但 `progress_url=null` → 既有 CLI 均不覆盖（skip-submit-unknown 仅 SUBMIT_UNKNOWN；skip-stale 需 URL）→ 同批 4 PENDING fail-closed 暂停 → round_7 无法 complete → preflight BLOCKED → 新轮被 `[CHECKPOINT BLOCKED]` 拦截 | 扩展授权跳过路径（`ProposalExecutionWorkflow.skip_submit_unknown_authorized` 接受"无 URL 的 UNKNOWN"；有 URL 的 UNKNOWN 明确不可 skip）+ 3 条回归测试 + 全质量门 + `docs/ARCHITECTURE_AGENT.md` 冻结边界同步；经授权 skip → canonical `run-proposals` 以 round_7 恢复 stub inbox 派发 4 PENDING → **round_7 complete（99 DONE + 1 SKIPPED，0 FAILED），preflight 恢复 READY** | 已处置（本 campaign 期间） |
| 12 | factory 进程在 round_7 派发中静默死亡（session `a4a3f3ac`，08:21） | 进程意外终止（日志 0 字节，缓冲区丢失）；session 停留 stale `RUNNING` | canonical `run-proposals` 恢复该轮 checkpoint；后续 factory 启动自动 mint 新 session（陈旧控制面自愈，无需手改） | 已处置 |
| 13 | 未完成 checkpoint 期间的 inbox 覆盖（r7 未完成时 proposals.json 被写成 r8 批次） | Agent 批次覆盖工厂 inbox → r7 恢复需匹配 round_no | 写入 round_no=7 的恢复 stub inbox（数据全部来自 round_7 checkpoint，非伪造）→ resume 派发成功 | 已处置（流程留痕） |

## 4. 证据缺口（架构冻结带来的研究约束）

| # | 缺口 | 影响 | 当前状态 |
|---|---|---|---|
| 14 | **优化层 handoff 缺口**：生产配置下 trajectory 非持久，新进程内存轨迹为空 → `EXPLOIT/ROBUSTNESS` 题案的 `parent_expression` 无法在 `run-proposals` 新进程中解析（`PARENT_NOT_DONE` 拒绝） | Agent 自编优化批次只能按 `EXPLORE/BASELINE` 注册（parent/lineage 审计元数据保留），机器强校验的"单变量 ROBUSTNESS + ValidationPlan"链路不可用；optimizer workflow 同样空转 | 已知未修（9-10 识别为 P1）；修复需 checkpoint→trajectory 的证据重连（动冻结边界，需测试+文档+质量门），**待用户决定** |
| 15 | **SELF_CORRELATION 全 PENDING**：平台结算值迟迟不落地 | 质量门"无 FAIL 且全过"永远差一项；`scripts/refresh_self_correlation.py` 回填无对象（规则要求"除自相关外全过"候选）；0 个可提交候选 | 持续观察；每批判定 RECONCILE |
| 16 | yearly 稳定性在 simulation 阶段 UNAVAILABLE（payload `is` 块无 `yearly`） | ROBUSTNESS 的 `yearly_aggregates` 变量恒 NOT_APPLICABLE；稳定性证据缺失 | 持续观察 |
| 17 | 静态 cheatsheet 与 live region 行为不一致（§1 全部条目） | 首次出批必踩 arity 拒绝（r1-r4 共 89 FAILED） | 拒绝记录表 + arity 守卫测试已建立，新增算子需 live 实证后才进模板 |

## 5. 研究侧系统性阻塞（非工程 bug，是信号属性）

- **横截面 rank 构造三重阻塞**：`CONCENTRATED_WEIGHT`（TOP3000 下 top 桶集中 0.1-0.5）+ `LOW_SUB_UNIVERSE_SHARPE` + SELF_CORRELATION PENDING → 9 个 100 题案批次 0 全过候选（r1-r7、r11、r12）。
- **revere 结构字段族**（pv13_revere_term/index/key_sector_total）：r2/r3/r4/r7 反复出强信号（fit 0.84-13.68，sharpe 最高 4.9），但集中度 0.5 + 子域失败是**字段族属性**——行业中性化（r8 P1）修复子域但不降集中度，组均值 3 参构造（r10 N1）两者均不移除 → 按预注册判据**整族关闭**。
- **churn 伪信号**：risk_adjusted_reversal 族（波动率缩放 5 日反转）在 close（r8 P3）与 forward_price_270（r9 E1）上经单参 hump 单变量检验 → 限幅后 P&L 崩塌（fitness 0.07/0.03）→ **族内成员关闭**；forward_price_30/120、vwap 等同族 Sharpe 带（1.2-1.4）保持观察项（不追测 hump，避免谱系内反复微调）。
- 推论（r12 后）：后续机制方向优先**交易类字段（volume/vwap）的组级/中性化构造**（集中度可能为构造属性而非字段族属性），而非继续堆字段族探索——已列为下一方向，**未启动（研究暂停中）**。

## 6. 操作 / 工具摩擦（harness 层面）

| # | 问题 | 应对 |
|---|---|---|
| 18 | pwsh 执行器 ~600s 上限，长 `Start-Sleep` 被强杀 | 后台 watcher 循环 job + 分段 ≤9min 轮询 |
| 19 | `python -c` 嵌套引号在 PowerShell 下失败 | 改用临时脚本文件（用后即删） |
| 20 | `.wqb_state` JSON 带 UTF-8 BOM | 一律 `utf-8-sig` 读取 |
| 21 | `get_progress_snapshot` 返回包装体（`payload` 内层才是 alpha 状态） | 首次恢复脚本读顶层 key 得 0/156 → 提取 `.payload` 修复 |
| 22 | 正则在嵌套调用上误判 arity（`normalize\([^)]*,` 假阳性） | 深度感知的 `_top_level_arity` 助手（入测试） |
| 23 | 共享机器上存在其他用户的 miniconda python 进程 | 只识别、只操作本 campaign 进程（按启动时间/命令行识别） |

## 7. 汇总：状态与未决项

**已闭环**：#1-#8（平台语法 7 项 + 路由门禁 1 项）、#9-#13（恢复边界 5 项）、#18-#23（工具摩擦 6 项，流程性规避）。
**持续观察**：#15（SELF_CORRELATION PENDING）、#16（yearly UNAVAILABLE）。
**未决 / 待用户决定**：
1. **#14 优化层 handoff 缺口**——是否立项做 checkpoint→trajectory 证据重连（冻结边界改动：测试 + 文档 + 质量门）。
2. **工作树 commit 授权**——`alpha_factory.py`（模板修复）、`tests`（arity/skip 守卫）、`docs`（cheatsheet/ARCHITECTURE_AGENT）、`findings.md`/`progress.md`、`proposal_execution.py`+`cli.py`（无 URL UNKNOWN 授权跳过扩展）尚未提交（git 邮箱 `2966684515@qq.com`，前缀中文提交信息，需用户明确授权）。
3. **Alpha 提交**：全部手工（用户）；当前 0 个"全 checks 通过"候选，无可提交对象。
4. **研究恢复**：用户已下令暂停；在途 round_13（session `5d895622`，300 槽位第 3/3 轮）自然收尾后不启动新周期；恢复时按 3h 周期约束先 `alpha sync-feed` → 只读 preflight → `factory run --hours 3`。
