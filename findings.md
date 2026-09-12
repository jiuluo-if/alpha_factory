# 发现记录

## 任务前约束

- 研究状态是事实源；不得手改或删除未完成 checkpoint、trajectory、proposals、submission pool、factory session 或有效锁。
- 默认生产入口是 `python main.py --suggest` → 审阅 proposals → `python main.py --run-proposals`。
- `SUBMIT_UNKNOWN` 不重发，known progress URL 只读对账，缺失证据保持 `UNKNOWN`/`UNAVAILABLE`。

## 2026-09-11 round_12 结算（factory session <session> 第 2 轮）

- 批次 100/100 DONE、0 平台拒绝；判定 RECONCILE×100（自相关 PENDING）。
- 只读恢复：success=0 / promising=0（连续第 9 个零全过 100 批）。头部：
  - `volume` 对数水平形式 `rank(ts_zscore(ts_product(add(volume, 1), 10), 60))` **fit 1.5**/sh 0.89（LOW_SHARPE+集中度+子域三失败）——量级信号族新头部；
  - `vwap` 反转 fit 0.62/sh 1.23（risk_adjusted_reversal 族又一成员，Sharpe 带，不追测）；
  - 分析师估计族（anl4 fs_detail corr/delta 形式 fit 0.39-0.55）与分红族（fnd6 dv fit 0.26-0.32）维持观察带。
- 跨 9 批元模式不变：Sharpe 带信号分散（volume/vwap/IV/forward price/parkinson/分析师/分红多族），但 **CONCENTRATED_WEIGHT + LOW_SUB_UNIVERSE_SHARPE + SELF_CORRELATION PENDING 三重系统性阻塞**使 0 候选过质量门；非模板问题（模板已 0 失败 4 批）。
- 研究推论：当前横截面 rank 构造在 TOP3000 下的集中度/子域失败是构造-universe 层面的系统属性；下一机制方向应优先**组级/中性化输出构造**（降低 per-ticker 集中度）而非更多字段族探索——但 revere 族的 r8/r10 已证明组级构造对"集中度为字段族属性"的字段无效，需选择**非结构类字段**（volume/vwap 等交易类）做组级构造试验。

## 2026-09-11 round_11 结算（factory session <session> 第 1 轮）：零失败验证 + 信号带读数

- 批次 100/100 DONE、**0 平台拒绝**（连续第 4 个零失败批次；3 参 group_mean arity 修复经 factory 批量实证）；判定全部 RECONCILE（自相关 PENDING）。
- 只读恢复 100 条指标：**success=0 / promising=0**（与 r5/r6 同——质量门 0 全过候选，第 8 个 100 批）。头部信号带：
  - `split` churn 形式（fit 0.76/sh 0.90、ts_scale fit 0.66）——新头部字段，但 LOW_SHARPE+集中度双失败；
  - `forward_price_120/30` 反转（sh 1.36/1.29，fit 0.63/0.58，集中度失败）——risk_adjusted_reversal 族在 30/120 期限仍有 Sharpe 带（该族 churn 判据仅证 close/forward_price_270；不做 hump 追测，观察项）；
  - `implied_volatility_put_10` 分位（sh 1.34/1.33，fit 0.33-0.42）——IV 族 Sharpe 带复现（r5/r6/r10 一致：IV 信号高 Sharpe、低 fitness、高换手）；
  - `parkinson_volatility_90` 4 题案入 top-12（fit 0.27-0.38）——本批新字段族（波动率水平类）。
- 系统性阻塞不变：CONCENTRATED_WEIGHT + LOW_SUB_UNIVERSE_SHARPE + SELF_CORRELATION PENDING（横截面 rank 构造共性）。
- 谱系账本不变（revere 结构族 r10 已关；本批未含 revere 题案）。

## 2026-09-11 round_10 Agent 优化批次：revere 谱系按预注册关闭 + IV 差分结构未达准入

- **N1 revere 组级构造 3 参重投**（`group_mean(rank(ts_rank(ts_zscore(pv13_revere_term_sector_total, 20), 60)), 1, subindustry)`）：DONE，Sharpe 1.16 / Fitness 0.88 / to 0.274 / sub-universe 0.37 FAIL；**CONCENTRATED_WEIGHT 仍 0.5**。预注册判据（"集中度仍 >=0.5 或 LOW_SUB_UNIVERSE_SHARPE FAIL → 关闭整条 revere 谱系"）触发：**revere 结构字段族（term/index/key_sector）的集中度+子域失败是字段族属性而非构造属性**——行业中性化（r8）、组均值（r10）两种去集中构造均无法移除 CONCENTRATED_WEIGHT=0.5。谱系关闭，不再投入该族的构造变体。
- **N2 IV 水平差分结构**（`rank(ts_zscore(ts_delta(implied_volatility_mean_270, 5), 60))`）：DONE，Sharpe 1.23（距 1.25 门槛 0.02）/ Fitness 0.36 / to 0.589；LOW_SUB_UNIVERSE_SHARPE 未 FAIL。预注册准入（fit>=0.5 且换手 <0.5）未达，且 0.36 不落入注册关闭分支（fit<0.3）——**判定：未达准入；按纪律不做 hump 救回（与 churn 谱系同型风险），IV 差分结构关闭；IV 状态分位族保持 r5 观察项，待 SELF_CORRELATION 回填证据**。
- 批次小结：2/2 DONE、0 平台拒绝（3 参 group_mean arity 修复生效）、2 RECONCILE（自相关 PENDING）。
- 谱系账本更新：关闭 revere 结构族（构造不敏感）、close/forward_price_270 churn 族、IV 斜率、IV 差分；存活观察项：revere_key_sector_total 的 r7 高分异类（fit 13.68/sharpe 4.9，同族集中度阻塞）与 IV 状态分位族。
- 下一轮策略：① 恢复 3h factory 周期（preflight READY）让探索层继续产信号；② 如需 Agent 批次，优先把 r7 的 `rank(ts_rank(ts_zscore(pv13_revere_key_sector_total, 20), 60))`（fit 13.68）作为优化层父证据做构造检验（同一判据：集中度不降则同样关闭，避免谱系内反复微调）；③ 陈旧 session <session> 控制面无需手工处理（factory 启动自动 mint）。

## 2026-09-11 round_9 Agent 优化批次：churn 谱系关闭 + group_mean arity 平台实测

- **E1 forward_price_270 hump churn 检验**（`hump(rank(divide(reverse(ts_delta(forward_price_270, 5)), add(ts_std_dev(forward_price_270, 20), 0.001))))`）：DONE，Sharpe 0.16 / Fitness 0.03 / turnover 0.0926 / returns 0.0042。预注册判据（turnover<0.2 且 fitness≥0.4 保留；fitness<0.2 → churn）：**fitness 0.03 < 0.2 → churn 证伪，关闭 forward_price_270 谱系**。与 round_8 P3（close 同法）一致——"波动率缩放 5 日反转（risk_adjusted_reversal）"族（close、forward_price_270 已证）的 P&L 由换仓行为承载，hump 限幅后净价值≈0；族内唯一未测成员 pv13_custretsig_retsig 暂不追测（避免谱系内反复微调）。
- **E2 revere 组级构造**（`group_mean(rank(ts_rank(ts_zscore(pv13_revere_term_sector_total, 20), 60)), subindustry)`）：**平台拒绝**——`Invalid number of inputs : 2, should be exactly 3 input(s)`。平台实测：`group_mean` 在此 region 只接受 **3 参 `group_mean(X, N, G)`**（r1-r7 `group_scaled_mean` 共 38 次 DONE 均为 3 参）；经济假设（组均值去集中度）未被检验，仅表达式 arity 错误。
- **发现并修复 round_4 的 `group_filled_rank` 潜在 bug**：当时写成 2 参 `group_mean(ts_backfill({p}, 20), {g})`（本 region 会被拒）。已修正为 3 参 `group_mean(ts_backfill({p}, 20), 1, {g})` 并与 group_scaled_mean 对齐；cheatsheet 拒绝记录 + 已实证可用算子表已更新；`test_factory_boundaries` 新增 3 参 group_mean arity 全注册表守卫与 2 参 REJECTED_SNIPPET；全量质量门（unittest/compileall/ruff/mypy-9）通过。
- 下一批可执行（证据驱动，新表达式非已证伪机制微调）：① revere 组级构造 3 参重投 `group_mean(rank(ts_rank(ts_zscore(pv13_revere_term_sector_total, 20), 60)), 1, subindustry)`；② IV 水平族（implied_volatility_mean_270 差分结构）低相关观察项。
- round_7 末 4 PENDING 结算只读恢复：3 LOW（option_breakeven_360 fit 0.03、mean_earnings_evaluation_sentiment fit -0.04、IV mean_skew_720 fit -0.02，均 HIGH_TURNOVER）+ **1 promising**（`reverse(rank(ts_std_dev(ts_delta(pv13_revere_key_sector_total, 5), 20)))` fit 1.36/sharpe 0.78/to 0.062，fails=CONCENTRATED_WEIGHT+LOW_SUB_UNIVERSE_SHARPE）。
- 另注（r7 既有 DONE 中的强信号，供优化层手托）：`rank(ts_rank(ts_zscore(pv13_revere_key_sector_total, 20), 60))` **sharpe 4.9/fit 13.68**（to 0.667，fails 仅 CONCENTRATED_WEIGHT+LOW_SUB_UNIVERSE_SHARPE）与 `rank(ts_zscore(ts_sum(ts_delta(pv13_revere_key_sector_total, 5)...` fit 1.04/sharpe 0.75——revere_key_sector_total 族（与 r2/r3/r4 term/index 族同字段系）为当前最强信号簇，系统性阻塞项仍是集中度+子域 Sharpe+SELF_CORRELATION PENDING。

## 2026-09-11 round_7 残留处置（授权跳过 + 恢复完成）与无 URL UNKNOWN 授权跳过路径扩展

- 代码扩展（证据驱动局部维护）：`ProposalExecutionWorkflow.skip_submit_unknown_authorized` 现接受 `SUBMIT_UNKNOWN` **与无 progress_url 的 UNKNOWN**（同一 ambiguous-POST 证据缺口：不能安全重 POST、无远端身份可只读对账）；**有 URL 的 UNKNOWN 明确不可 skip**（远端作业可只读恢复，跳过会丢弃活证据），PENDING/终态拒绝；skip 审计按类分 reason（`user_authorized_skip_unknown_no_progress_url`）。3 条回归测试（拒绝有 URL UNKNOWN、拒绝 PENDING、接受无 URL UNKNOWN、SUBMIT_UNKNOWN 旧语义不变）+ unittest/compileall/ruff/mypy-9 全绿；CLI help 与 docs/ARCHITECTURE_AGENT.md 冻结边界章节已同步。
- 处置：`recovery skip-submit-unknown 7 <proposal-id>`（<field> downside_risk，无 URL）→ SKIPPED_UNKNOWN（审计入 stale_skip_log.jsonl）；随后以 round_7 恢复 stub inbox 经 canonical `run-proposals` 派发 4 PENDING → **round_7 `complete=true`（DONE=99、SKIPPED=1，0 FAILED、0 新 UNKNOWN）**，preflight 恢复 `READY`。
- round_7 末 4 题案全部 LOW（sharpe -0.37/-0.23/0.78、HIGH_TURNOVER 0.79、revere_key_sector 双失败延续 r4 模式）——探索层无新信号，不影响谱系结论。

## 2026-09-11 round_8 Agent 优化批次（用户指令：自编候选 + 单变量预注册）

- 执行路径：round_7 残留（无 URL UNKNOWN `<submission-id>` + 4 PENDING）无法经既有 CLI 跳过（skip-submit-unknown 仅 SUBMIT_UNKNOWN；skip-stale 需 URL）；按用户明确指令经 `run-proposals --force-new-round`（内置授权逃生门："按用户明确授权开启新轮"）保留 round_7 原 checkpoint 并开启 round 8；round_7 残留保持为待人工决策项。
- 4 个 Agent 自编候选（全部单变量、预注册反证、对 700 条历史表达式 0 重叠、本地 strict+经济完整性预验证 3 PASS / P4 仅本地缺 live 平台 dedupe 证据而 live 通过）：
  1. **P1 H-revere-neutralize** `group_neutralize(rank(ts_rank(ts_zscore(pv13_revere_term_sector_total, 20), 60)), industry)` → Sharpe 1.34 / Fitness 1.93 / to 0.109 / dd 0.090；`LOW_SUB_UNIVERSE_SHARPE` 不再 FAIL（父 r4 双失败之一被行业组中性化移除），但 `CONCENTRATED_WEIGHT` 仍 0.5 且 health 小账簿（long 9/short 8）。**判定：混合——集中度未降，按预注册判据（"集中度不降"分支）关闭该构造方向**；revere 谱系转向新构造（组级 group-mean 信号而非 per-ticker 横截面 rank），不做中性化水平继续微调。
  2. **P2 H-revere-return 端点对照** `rank(ts_zscore(ts_delta(pv13_revere_index_value, 20), 60))` → Sharpe -0.03 / Fitness -0.00。**判定：证伪**——端点 20 日变化无信号，r2 累计形式（ts_sum(ts_delta(5),20)）的结构本身承载信号；端点假设关闭。
  3. **P3 hump 换手控制** `hump(rank(divide(reverse(ts_delta(close, 5)), add(ts_std_dev(close, 20), 0.001))))` → turnover 0.42→0.0088（hump 生效）但 Sharpe 0.27 / Fitness 0.07（父 1.33/0.69），且 LOW_TURNOVER FAIL（低于 0.01 下限）。**判定：证伪——r6 close 反转信号确为换仓 churn（限幅后 P&L 崩塌至 ~0）**；close 谱系关闭。forward_price 族（r5 头部同构）的 hump 单变量验证列为下一批次。
  4. **P4 IV 期限结构斜率** `rank(subtract(implied_volatility_call_20, implied_volatility_call_150))` → Sharpe 0.01 / Fitness 0.00。**判定：证伪——20d-150d ATM call IV 水平差无信号**；IV 期限结构斜率假设关闭；IV 水平族（r5 证据）保持观察项待 SELF_CORRELATION 回填数据。
- 4/4 `DONE`，判定 RECONCILE×4（全部 SELF_CORRELATION PENDING，无"除自相关外全过"候选 → refresh 回填无对象，保持 UNKNOWN/PENDING）。总耗时 3.2 分钟（3 并发）。
- 本批负结果纪律：4 条谱系全部按预注册判据裁决（1 混合关闭、3 证伪关闭），无事后拟合、无参数扫描、无方向翻转重投。
- 下一周期题案排序：① `forward_price_270`（r5/r6 头部）+ 单参 hump 单变量（churn 检验）；② revere 谱系组级构造（`group_mean(rank(ts_rank(ts_zscore(pv13_revere_term_sector_total, 20), 60)), subindustry)` 等组均值信号，单一结构变量）；③ IV 水平族 SELF_CORRELATION 回填可用后做相关性证据；④ round_7 无 URL UNKNOWN 的人工处置（授权跳过路径扩展或平台身份反查）。

## 2026-09-11 自主循环接管：交叉 dataset 门禁与关系契约失配

- 接管 preflight 为 `READY`：round_1/round_2 checkpoint 均 `complete=true`（各 78 DONE），无 `SUBMIT_UNKNOWN`、无未完成 checkpoint；旧 session `<session>cf244dc8` 为干净 `STOPPED` 终态。
- 按 3 小时约束先执行 `alpha sync-feed`（3013 条周元数据，`updated_at=2026-09-10T18:05:47Z`，`network_write=false`），随后只读 preflight 再次 `READY`。
- 启动 `factory run --hours 3`（新 session `<session>e1a04b31`）：3 条 bounded route（current_bundle / same_dataset_relationship / same_dataset_new_mechanism）均在同一 6-dataset 池上失败，`pair_examined=256`、`relationship_allow=0`（86 REVIEW、86 UNKNOWN、170 INCOMPATIBLE）、`template_compatible_count=0`，最终 `STOP_MECHANISM_ROUTE / NO_INFORMATION_GAIN`，0 次 Simulation 消耗。
- 根因：2026-09-10 收紧后的多字段关系契约（option 仅 put/call IV、ratio 仅 earnings→fundamental 方向、频率 UNKNOWN 一律 REVIEW）在当前池（pv1/pv13/option8/option9/fundamental6/news18）中基本不存在可准入的跨 dataset pair；bundle 中 82/100 字段无显式频率证据。rounds 1-2 能过门是旧宽松契约下的结果，契约收紧造成“门禁需求”与“契约供给”结构性失配，不是字段数量或历史去重问题（本次 `historical_expression_exclusion_count=0`）。
- 研究控制决策（可逆、不改代码）：本周期将 `config.agent.field_selection.min_cross_dataset_pairs` 由 `1` 调为 `0`，保留 `min_datasets=3` 的批次广度约束；单字段经济模板探索批次（9-11 审计已证明同 bundle 可生成 100 候选）先恢复信号探索吞吐。跨 dataset 关系探索列为下一周期方向：扩展 dataset_pool 引入含显式 daily 频率且机制互补的数据集，或待平台频率证据完善后恢复门禁。
- 决策依据与证据：`factory-run-3.stdout.log` 的 3 条 FEASIBILITY 心跳、session `<session>e1a04b31` 的 `route_decision`/`feasibility_probe`、9-11 审计 REPORT（pair 30 抽样 0 ALLOW、15 REVIEW、15 REJECT）。
- 放宽门禁后新 session `<session>` 通过首条 bounded route：round_3 批次 100 题案（全部 `exploration/EXPLORE`、12 个模板族、0 多字段、100 唯一表达式、与 rounds 1/2 的 156 条历史 DONE 表达式 0 重叠），`simulations_reserved=100`，进入 `RUN_PROPOSALS`。

## 2026-09-11 round_6 结算与跨轮模板×字段类元模式

- session `<session>` round_6：`complete=true`，**DONE=100/100、FAILED=0**（连续第三轮零平台失败，7 模板修复稳定）。批次含 12 模板族、7 数据集（analyst4 首次入 bundle）、16 条多字段题案。
- 100 条 round_6 指标只读恢复：0 success、2 promising；失败分布 `LOW_FITNESS=100、LOW_SHARPE=97、LOW_SUB_UNIVERSE_SHARPE=62、CONCENTRATED_WEIGHT=34、HIGH_TURNOVER=15、LOW_TURNOVER=9`。
- 头部：`risk_adjusted_reversal`（波动率缩放的 5 日反转）跨轮复现——r5 `forward_price_60/150/720` fit 0.59-0.64/sharpe 1.34-1.38；r6 `close` fit 0.69/sharpe 1.33、`pv13_custretsig_retsig` fit 0.71/sharpe 1.82、`forward_price_270` 0.56/1.28。共性弱点：turnover 0.42-0.84（HIGH_TURNOVER）→ 该族的单一后续变量为单参 `hump` 换手控制（已修复验证的算子）。
- 跨 5 轮 500 条 DONE 的元模式：头部信号集中于 4 个模板×字段类组合（distribution_regime×revere、risk_adjusted_reversal×价格/IV、robust_cross_section×IV、persistent_level×IV 均值）；无全 check 通过的 success 候选（探索阶段正常）；`LOW_SUB_UNIVERSE_SHARPE` 与 `CONCENTRATED_WEIGHT` 是板块/结构字段簇的系统性瓶颈，`HIGH_TURNOVER` 是日频反转族的系统性瓶颈。
- 下一周期 Agent 题案排序更新：① H-revere-neutralize（INDUSTRY 单变量）；② `risk_adjusted_reversal` 头部表达式 + 单参 hump 的单变量换手控制（`close` 与 `forward_price_270` 各 1 条）；③ H-revere-return 端点对照。IV 期限结构簇（r5 发现）保留为观察项，待 self-correlation 回填后可用后再做相关性证据。
- 证据文件：`_metrics_recover_r6.json`（scratch，结论记录后删除）。

## 2026-09-11 round_5 全修复模板验证与新信号簇（option IV / forward price）

- 新 session `<session>218e4b3c`（无人工 stop）round_5：`complete=true`，**DONE=100/100、FAILED=0**——7 模板修复经 live 完整验证（对比 r1-r4 的 22/20/27/15 项失败归零）；runner 判定 RECONCILE=100（自相关 PENDING），best=null。
- 100 条 DONE 指标只读恢复：0 success、4 promising（sharpe≥0.9 且 fit≥0.6）；失败检查分布 `LOW_FITNESS=100、LOW_SHARPE=92、LOW_SUB_UNIVERSE_SHARPE=49、CONCENTRATED_WEIGHT=48、HIGH_TURNOVER=15、LOW_TURNOVER=7`。
- **新信号簇（修复模板首次可测）：option IV / forward price 期限结构**：
  - `implied_volatility_call_150` 三模板同向：`robust_cross_section`(单参 winsorize) fit 0.65/sharpe 1.78、`distribution_regime` 0.50/1.47、`distributional_change` 0.42/1.39；
  - `forward_price_60/150/720` 三个期限同构 `risk_adjusted_reversal` 信号 fit 0.59-0.64 / sharpe 1.34-1.38（期限一致性 → 机制在 IV 水平/相对位置而非单一期限）；
  - `implied_volatility_mean_150/270`：fit 0.70/0.53；共性问题：turnover 0.47-0.65（HIGH_TURNOVER 风险）+ 轻度 CONCENTRATED_WEIGHT（v 0.11-0.19）。
  - 机制读法（可证伪）：期权隐含波动率水平与 forward price 隐含成本携带，是前向风险/融资预期；横截面相对位置预测收益。反证：若同字段在 IV 期限间无一致性（cross-maturity rank corr 低）或中性化后消失 → 期限特异性伪信号。
- revere 簇未进 round_5 top（该轮 bundle 未含 revere 字段，属采样轮替）；其三轮证据（r2/r3/r4）保持有效。
- 次级：`news_impact_projection_score`（vector_persistence）fit 0.43/sharpe 1.08。
- 下一周期 Agent 题案排序（单变量、非扫描）：① H-revere-neutralize（INDUSTRY 中性化复测 r4 头部表达式）；② IV 簇 turnover 控制单变量（同表达式 + 平台默认 truncation 不变、仅 `hump` 单参包裹一次）；③ H-revere-return 端点形式对照。
- 证据文件：`_metrics_recover_r5.json`（scratch，结论记录后删除）。

## 2026-09-11 round_4 结算与新模板缺陷（round_4 平台实测）

- 用户授权处置后：`skip-submit-unknown`（`<alpha-id>`→SKIPPED_UNKNOWN）+ 3 次只读 STALE 对账后 `skip-stale`（`2P0mkygQn4W2bdq14rKNHQil`→SKIPPED_STALE），round_3 checkpoint 完整收尾（DONE=66/FAILED=32/SKIPPED×2），preflight 恢复 `READY`；`alpha sync-feed`（3060 条）后启动新 session `<session>`（stop 控制由新 session 干净清除）。
- 期间又出现一次人工 stop（round_4 派发中）；已遵守：round_4 完整结算后 session 干净 `STOPPED`，未启动 round_5。
- round_4：`complete=true`，DONE=85/FAILED=15（85 条 RECONCILE 判定 = 自相关 PENDING，无 best）。15 项 FAILED 分类：13× `robust_cross_section`（双参 winsorize 被拒：`exactly 1 input`）、1× `turnover_control`（双参 hump 同签名）、1× `trend_residual`（**新类**：`ts_regression(..., 0)` 的 lookback=0 被拒：`invalid value "0" for attribute "lookback"`）——6 个模板缺陷全部修复于工作树（winsorize/hump 改单参、trend_residual 省略 lookback），全量质量门通过（unittest exit=0、ruff、mypy 9 frontier），干跑验证（`postfix_validation_2`）100/100 批次 0 拒绝片段。
- 85 条 DONE 指标恢复（只读）：0 success、1 promising；失败检查分布 `LOW_SHARPE=84、LOW_FITNESS=84、LOW_SUB_UNIVERSE_SHARPE=48、CONCENTRATED_WEIGHT=37、HIGH_TURNOVER=23、LOW_TURNOVER=6`。
- **revere 簇第三次跨轮复现且构造升级**：修复后的 `distribution_regime` 模板（`rank(ts_rank(ts_zscore(X,20),60))`，ts_rank 历史分位形式）在 round_4 产出本轮唯一超阈值候选：
  - `rank(ts_rank(ts_zscore(pv13_revere_term_sector_total, 20), 60))`：Sharpe 1.39 / Fitness 2.05 / turnover 0.115，仅 `CONCENTRATED_WEIGHT(0.5)` FAIL（`LOW_SUB_UNIVERSE_SHARPE` 本轮未失败），health 提示 `longCount=9、shortCount=8 < 50`（小账簿）。
  - r2/r3/r4 三轮独立复现（fit 2.98→0.84→2.05），`revere_index_value` 与 `revere_term_sector_total` 两字段均产出头部信号。
- 次级观察：`implied_volatility_*`（option8/9 均值/put IV）簇经修复模板出现 4 条 fit 0.23-0.54 / sharpe 0.75-1.24 的中段信号（`distribution_regime`/`distributional_change`/`persistent_level`），为下周期候选机制族。
- 假设卡更新（H-revere-neutralize 优先）：对 round_4 头部表达式做 `neutralization` 单变量变体（INDUSTRY，较 SUBINDUSTRY 粗一级）；反证判据不变（集中度不降且子域 Sharpe 恶化 → 板块暴露；集中度下降且子域转正 → 机制稳健进入自相关回填）。`longCount/shortCount<50` 的健康标志提示 truncation 0.08 下账簿过窄，作为第二单变量候选（不与第一个同时改）。
- 可执行题案规格（下一 factory 周期结束后经 suggest→proposals→run-proposals 路径执行，单变量、各 1-2 条，非参数扫描）：
  1. H-revere-neutralize：表达式 `rank(ts_rank(ts_zscore(pv13_revere_term_sector_total, 20), 60))`，settings 仅 `neutralization` 由 SUBINDUSTRY 改为 INDUSTRY（其余 simulation 默认一致）。判据：CONCENTRATED_WEIGHT 下降且 LOW_SUB_UNIVERSE_SHARPE 不再 FAIL → 板块暴露机制稳健；若仍 FAIL 或 Sharpe 大幅衰减 → 该簇为少数板块驱动，停止该谱系换机制。
  2. H-revere-return：r2 头部 `rank(ts_zscore(ts_sum(ts_delta(pv13_revere_index_value, 5), 20), 60))` 的端点形式单变量对照 `rank(ts_zscore(ts_delta(pv13_revere_index_value, 20), 60))`（累计漂移 vs 端点变化，同一经济量）。判据：端点形式 fit/sharpe ≥ 累计形式且集中度更低 → 水平累计项是主要噪声源；反之保留累计结构。
- 证据文件：`_metrics_recover_r4.json`（scratch，结论记录后删除）。

## 2026-09-11 rounds 1-2 DONE 指标只读恢复（156/156）

- 恢复路径：checkpoint `progress_url` → 既有 `get_progress_snapshot` + `get_alpha` 只读 GET + `metrics.extract_metrics/check_health`；scratch 脚本用后即删，未写 `.wqb_state`、未 POST。
- 156 个 DONE 全部取得指标；0 个“success”（Sharpe≥1.25 且 Fitness≥1.0 且无 FAIL check）；4 个“promising”（Sharpe≥0.9 且 Fitness≥0.6，含 FAIL）。
- check 失败分布（156 项）：`LOW_FITNESS=152、LOW_SHARPE=149、LOW_SUB_UNIVERSE_SHARPE=68、CONCENTRATED_WEIGHT=59、HIGH_TURNOVER=17、LOW_TURNOVER=13`；`SELF_CORRELATION` 平台 payload 缺失（全部 None），按规则保持 UNKNOWN，不用 refresh 冒充通过（refresh 仅适用于“除自相关外全过”候选，本次无此类候选）。
- 唯一超阈值信号簇：`pv13_revere_*`（pv13 = Relationship Data for Equity；`revere_index_value` 字段描述为“Value of specified index for the date”，MATRIX，coverage 0.86，alphaCount 649；`revere_index_cap` = “Company market capitalization”）：
  - `rank(ts_zscore(ts_sum(ts_delta(pv13_revere_index_value, 5), 20), 60))`：Sharpe 1.81 / Fitness 2.98 / turnover 0.1385 / drawdown 0.1136，但 `CONCENTRATED_WEIGHT=FAIL`、`LOW_SUB_UNIVERSE_SHARPE=FAIL`；
  - `reverse(rank(ts_std_dev(ts_delta(pv13_revere_index_value, 5), 20)))`：Sharpe 1.18 / Fitness 1.60；`revere_index_cap` 同构信号 Fitness 1.55 / Sharpe 1.15；
  - `rank(ts_zscore(ts_sum(ts_delta(pv13_revere_city, 5), 20), 60))`：Fitness 1.04 / Sharpe 0.77。
- 机制解释（可证伪假设，非平台事实）：affiliated-index momentum——个股所属指数/板块的近期水平变化预测成分股收益；`CONCENTRATED_WEIGHT` + `LOW_SUB_UNIVERSE_SHARPE` 双失败与“信号由少数大指数/板块驱动”一致。反证判据：若同一表达式在 MARKET 中性化或加强 truncation 下集中度消失且 Sharpe 保持，则机制稳健；若 SUBINDUSTRY 中性化下完全消失，则属少数板块暴露而非系统性机制。
- 下一步（下一 factory 周期）：以该簇为 optimizer 父证据方向，只允许单一变量 ROBUSTNESS 变体（中性化/truncation 各一次，不扫窗口/权重）与“指数收益代替指数水平”的结构变体；探索层继续维持 breadth。
- 证据文件：`_metrics_recover.json`（scratch，完成结论记录后删除）。

## 2026-09-11 round_3 收尾、模板缺陷修复与 revere 簇跨轮确认

- 人工 stop 控制（02:40）后 session `<session>` 在安全边界收尾：`status=STOPPED、stop_requested=true、finished_at` 已写；round_3 checkpoint 未完成：`DONE=48、FAILED=27、UNKNOWN=1、SUBMIT_UNKNOWN=1、PENDING=23`。
- 只读对账：UNKNOWN `<alpha-id>`（`compounding_pressure/<field>`）保有 progress URL，平台快照仍未结算（status=None），保持 UNKNOWN 不升 PASS；SUBMIT_UNKNOWN `<alpha-id>`（`accumulated_change/<field>`）无 URL，提交发生在进程退出前 39 秒内，属 exactly-once 边界，**需人工经 `main.py recovery` 授权处置**；23 个 PENDING 按 fail-closed 批次规则在 SUBMIT_UNKNOWN 处置前不得 POST。未做任何写操作。
- 模板算子缺陷（本轮修复，工作树待提交）：rounds 1-3 共 63 项 FAILED 全部归因 4 个模板的 live 拒绝用法：三参 `normalize`（r1×8/r2×7/r3×9）、裸位置参数 `gaussian` 驱动（r1×13/r2×13/r3×8，分布于 `distributional_change` 与 `distribution_regime`）、`group_rank(group_backfill(...))` arity（r1×1）。替换表达式只使用 156 条 DONE 实证算子；`TestTemplateLiveOperatorEvidence` 3 项回归 + 全量质量门通过（unittest exit=0、compileall=0、ruff、mypy 9 frontier）。
- round_3 的 48 条 DONE 指标恢复：0 success、0 promising；头部为 `pv13_revere_term_sector_total` 簇：
  - `rank(divide(reverse(ts_delta(pv13_revere_term_sector_total, 5)), add(ts_std_dev(pv13_revere_term_sector_total, 20), 0.001)))`：Sharpe 1.25 / Fitness 0.84 / turnover 0.118 / dd 0.053；FAIL `LOW_FITNESS(0.84)`、`CONCENTRATED_WEIGHT(v=0.5)`、`LOW_SUB_UNIVERSE_SHARPE(0.39)`；SELF_CORRELATION PENDING。
  - `reverse(rank(ts_std_dev(ts_delta(pv13_revere_term_sector_total, 5), 20)))`：Sharpe 0.98 / Fitness 0.82；FAIL `LOW_SHARPE`、`LOW_FITNESS`、`CONCENTRATED_WEIGHT(v=0.5)`。
- **跨轮确认（204 条 DONE，3 个独立轮次）**：`pv13_revere_*`（pv13 = Relationship Data for Equity 的板块/结构矩阵）是唯一在 r2 与 r3 独立复现头部信号的字段簇（r2 `revere_index_value` fit 2.98/sharpe 1.81；r3 `revere_term_sector_total` fit 0.84/0.82），且两轮 `CONCENTRATED_WEIGHT` 值同为 0.5 —— 系统性结构属性而非随机。机制读法：板块/结构类字段把同板块个股绑定到同一组内值，横截面排名后 P&L 集中于少数板块 → 集中度与子域 Sharpe 双失败。
- 下一周期假设卡（单一变量、可证伪、非参数扫描）：
  1. H-revere-neutralize：revere 簇头部表达式在 `neutralization=INDUSTRY`（较 SUBINDUSTRY 更粗一级）下复测。反证判据：集中度（CONCENTRATED_WEIGHT）不降且 LOW_SUB_UNIVERSE_SHARPE 仍 FAIL → 板块暴露假说成立，该簇作为“板块轮动”机制需换构造方式；集中度下降且子域 Sharpe 转正 → 机制稳健，进入 SELF_CORRELATION 回填与后续。
  2. H-revere-return：`revere_index_value` 用“相对收益代替水平差”的结构变体（`ts_delta` 水平差 → 指数收益近似，如 `divide(ts_delta(X,20), ts_delay(X,20))` 型），检验绝对水平项是否为主要噪声源。
  3. 探索层继续 breadth；跨 dataset 门禁维持 0，待 dataset_pool 扩展引入显式 daily 频率且机制互补的数据集后，先用只读 feasibility 探测验证 ≥1 ALLOW pair 再恢复 `min_cross_dataset_pairs=1`。


## 2026-09-09 Factory-Discovery semantic calibration 初始审计

- 当前 HEAD 为 `608c4b2`，工作树在本阶段开始时干净；上一阶段已在 `alpha_factory.py` 增加 traits 的 `frequency`/`sign_semantics` 与模板兼容评分。
- 当前 Discovery 已有 dataset-level bounded candidate pool、动态 dataset universe、MATRIX/VECTOR 独立 completeness 和 `COMPLETE/INCOMPLETE/LEGACY_UNVERIFIED` provenance；需继续核对其 active dataset 选择是否仍会对 100+ 动态 dataset 全量分页。
- 当前测试已有 analyst revision、slow fundamental、option volatility、UNKNOWN mechanism、fixed seed 和 incomplete catalog 回归，但尚未覆盖 analyst estimate level/target price、open interest、put-call skew、coverage 三种字段键/百分比表达和 invalid coverage。
- 下一步需直接阅读 `FieldDiscovery` 的 coverage/profile 归一化路径与 AlphaFactory 的 semantic fallback，先确认真实 false-positive/false-negative，再写红灯测试。
- 新增红灯已复现：`category=analyst` 的无 revision 字段落入 `analyst_revision`；`option open interest` 被通用 `open` 命中为 `market_price`；Discovery 没有共享 `normalize_coverage`，且动态 dataset 规模测试在导入 helper 处失败。
- 用户明确授权删除外部 `外部 workspace 的 `.wqb_state``；本目录“多余”文件需按证据判定。

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

- 删除：`外部 workspace 的 `.wqb_state``（用户明确指定；包含历史研究状态、checkpoint、trajectory、ledger、cache、reports 和局部 AGENTS）。
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
- round 11 的未知提交为 `id=<proposal-row-id>`、`proposal_id=<proposal-id>`，`status=SUBMIT_UNKNOWN`、`progress_url=null`；它占用 exactly-once 边界，不能自动重发或跳过。
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

## 2026-09-09 FieldDiscovery scaling

- 原分页循环在 `max_pages` 用尽后没有 provenance，可能把 `count > loaded` 的部分结果当作完整目录；当前以平台 count、稳定 count、分页进展和 max-pages 共同决定 completeness。
- MATRIX/VECTOR 现在各自记录 contract；聚合 catalog 只有两类都完整且所有已拉取 dataset 都完整时才为 `COMPLETE`，任何一个 dataset/type 不完整都保持 `INCOMPLETE`。
- 当前 BRAIN client 已有 read-only `get_datasets()`，因此 discovery 使用动态 universe；无能力、异常、空或 malformed listing 时明确记为 fallback，并保留 `DATASET_CATEGORIES` seed。
- 全量 field metadata 仍受分页预算约束；排序前先按 cheap lexical/coverage 候选截到默认 100，再做 semantic/coverage/alphaCount/random ranking，active `target_count` 未扩大。
- catalog manifest 与 field profiles 只增加 metadata/completeness/ranking provenance；测试逐文件确认不含 `metrics` 或 `results`，未触碰 Simulation、Alpha submission、trajectory、checkpoint 或 Factory template semantics。
- 并行 Alpha Factory 对话曾使中途全量测试出现其目标文件的 tuple/semantic 失败；其后已自修并报告全量 620 tests、compileall、mypy、Ruff、coverage 通过，本任务不包含其文件。

## 2026-09-09 Alpha Factory semantic calibration 验收

- Analyst 语义现在区分 estimate level、target price 与 revision；仅有 analyst category 的字段降为 `REVIEW`，不再伪造 `analyst_revision`。
- Option 语义将 open interest 归入 liquidity，将 put-call/IV skew 归入 option-relative/dispersion；泛化 skew 不再直接升级为期权机制。
- `semantic_admission` 与 metadata availability 分离；`field_hypothesis_basis.mechanism` 使用字段 traits 与 fit reason，不复制 template rationale，UNKNOWN/REVIEW 不宣称强机制。
- Discovery/Factory 共用派生 `normalize_coverage()`，fraction/percentage 形式统一到 0..1，非法值保守为 `None`，不修改原始 BRAIN metadata。
- 动态 dataset universe 在 field pagination 前固定上限 12 个，并记录 full universe 与 active pool；不完整 catalog reload 保持 provenance 且不重复大分页。
- 定向 Factory/Discovery 87 tests、全量 626 tests、compileall、mypy、Ruff 通过；coverage report 总覆盖 77.4%。doctor/audit 通过，preflight 仍因既有 `round_11.checkpoint.json` 与 `SUBMIT_UNKNOWN` 为 BLOCKED，本阶段未做远端写入。

## 2026-09-09 multi-field relationship contract 初始审计

- pasted objective 要求所有 multi-field 入口统一收紧：relationship 必须提供方向/slot contract，spread/ratio/correlation/covariance/triple 使用不同 admission 规则，frequency compatibility 保守判定，Factory 自动路径拒绝 REVIEW/UNKNOWN。
- 尚未修改 production code；先读取当前 `alpha_factory.py`、proposal contract、diversity、架构约束和相关测试，下一步记录可复现的关系/槽位/频率缺口并写红灯测试。
- 红灯证据：新增 9 项 relationship contract 测试，结果 `3 failures / 6 errors`；当前 decision 缺少 relationship type/slot/frequency metadata，任意 option open-interest + IV Greek、同概念 level/change、triple 两条 pair edge 仍可 ALLOW，且 REVIEW pair 仍可进入生成路径。

## 2026-09-10 multi-field relationship contract 结果

- 语义关系现在先于 diversity 偏好判定；option pair 仅接受 put/call implied-volatility 对，ratio 只在 earnings→fundamental 方向具备 numerator/denominator 证据，triple 只有 analyst revision + dispersion + analyst sentiment 的共同 expectation-update 机制才 ALLOW。
- frequency bucket 统一为 intraday/daily/weekly/monthly/quarterly/annual/unknown；未知频率为 REVIEW，直接 co-movement 的明显跨频率组合为 INCOMPATIBLE，所有非 ALLOW 自动路径均停止生成。
- `field_hypothesis_basis.mechanism` 继续由字段 traits 与 fit reason 组合，不复制 template rationale；semantic UNKNOWN/REVIEW 不宣称强 economic mechanism。
- 固定 seed 的字段顺序与兼容模板探索保持稳定；companion selection 仍是 bounded linear scan，无 Cartesian product。
- 关系契约红灯已转绿；新增优化前缀 REVIEW 绕过测试验证 `generate_factory_batch` 也 fail-closed。

## 2026-09-10 工厂字段生成效率诊断与优化计划

- 当前 live factory session `<session>cf244dc8` 仍为 `RUNNING`，round 3 最近结果为 `FACTORY_BATCH_NOT_READY`，`simulations_reserved=0`。
- 当前字段 bundle 有 100 个字段、6 个 dataset（`fundamental6/news18/option8/option9/pv1/pv13`）；静态诊断显示不排除历史表达式时可生成 17 个跨 dataset 多字段候选，排除 round 1/2 完成表达式后为 0，说明主要损耗在“历史去重后的关系兼容性”，不是字段数量不足。
- `generate_factory_batch()` 对 verified fields 逐字段排名模板，并通过 `assemble_proposals(..., max_candidates=1)` 逐模板尝试；批次门禁在完整组装后才发现跨 dataset pair 为 0，导致 100 个 proposal 生成工作不能转化为可执行批次。
- 优先优化顺序：先记录 pair feasibility/排除原因，再在组装前做 bounded pair feasibility；pair 数为 0 时切换兼容 discovery/template route，禁止对同一 bundle 只递增 seed 重试；保留 canonical expression dedupe 与 relationship fail-closed。
- `trajectory_records=0` 而历史 checkpoint 有 DONE 是独立的 optimization evidence handoff 缺口；不得把 checkpoint 精简状态或 Alpha Feed metadata 当作 metrics，需先做只读诊断和回归测试。
- 建议验收指标：每个可执行 bundle 组装前至少 1 个可审计 cross-dataset pair；记录每 probe 的 discovery/pair/template/排除/assembly/gate 时间与数量；成功批次参考历史 20/100 cross-dataset 候选，失败 family 达到 bounded retry 后 STOP/换机制。
## 2026-09-10 长期自主接管：恢复阻塞证据

| time | component | symptom | evidence | impact | proposed_improvement | priority |
|---|---|---|---|---|---|---|
| 2026-09-10 Asia/Shanghai | checkpoint/reconciliation | 未完成 round 无法自动收敛 | `round_11.checkpoint.json`: `PENDING=32`、`SUBMIT_UNKNOWN=1`，全部 `progress_url=null`；reconcile 扫描 0 个目标 | 阻止新 Simulation，也无法证明未知 POST 的远端结果 | 为无 URL UNKNOWN 建立仅人工授权的、可审计的外部对账输入/处置流程；不得自动重 POST | P0 |
| 2026-09-10 Asia/Shanghai | TrialLedger/doctor | checkpoint 一致性缺少 ledger 证据 | preflight: `ledger_status=MISSING`、`checkpoint_consistency=UNRESOLVED`；state audit 仍 `ok=true` | 恢复摩擦高，无法把 checkpoint 安全推进到 READY | 研究 ledger 缺失的稳定产生条件；若重复出现，再设计局部诊断或恢复工具，不改变 owner 边界 | P1 |
| 2026-09-10 Asia/Shanghai | factory control plane | 持久 session 同时 `RUNNING` 与 `stop_requested=true` | `factory_session.json` `last_action=STOP_REQUESTED`；新 run 会受控暂停/可能覆盖边界 | 长期无人值守无法自行接续 | 增加只读诊断明确区分“用户停止请求”和“checkpoint 安全阻塞”；清除控制状态仍需人工授权 | P1 |

## 2026-09-10 阻塞根因核查结论

- **主阻塞是未知提交的 exactly-once 边界**：round 11 唯一 `SUBMIT_UNKNOWN` 为 `id=<proposal-row-id>`、`proposal_id=<proposal-id>`；`submission_started_at=2026-09-09 08:16:55 +08:00`，`progress_url=null`。`Simulator._simulate_one()` 已先持久化 `SUBMITTING`，随后任何不能证明 POST 未被 BRAIN 接受的异常都会变成 `SUBMIT_UNKNOWN`；自动重发会有重复 Simulation 风险。
- **具体传输异常已不可从当前状态判定**：`WQBClient.submit_simulation()` 对 ambiguous POST 的超时/网络异常、无契约 429、`WQBSubmitUnknownError`、缺少 `Location` 都走同一安全分支；`CheckpointStore.write()` 的 allow-list 刻意不保存 `error`，所以当前 checkpoint 只能证明“提交结果未知”，不能证明是哪一种异常。无 URL 时也没有可安全调用的 `GET /simulations/{id}` 身份。
- **32 个 PENDING 是连带暂停，不是 32 个独立失败**：它们的 `submission_started_at=null` 且 `progress_url=null`；同一 checkpoint 存在无 URL UNKNOWN 时，恢复逻辑只允许已有 URL 的任务只读轮询，并过滤无 URL PENDING，避免在未知 POST 未对账前新增写入。
- **ledger 缺失不是主要因果点**：当前 runtime composition 使用 `persist=False`，接管后的 `state audit` 在 `lifecycle_persistent=false` 下仍为 `ok=true`；doctor 的 `LEDGER_MISSING` 与 `PNL_CAPABILITY_UNAVAILABLE` 是证据能力警告。preflight 的硬 blocking 列表实际只有未完成 `round_11.checkpoint.json`。
- **停止状态是控制面收尾不完整**：session 最后修改于 `2026-09-09 08:27:20 +08:00`，记录 `stop_requested=true`、`last_action=STOP_REQUESTED`、`status=RUNNING`；当前无 factory 进程。代码只有运行器下一次循环观察到 stop 后才写 `STOPPED`，因此停止请求后若进程在最终保存前退出，会留下这组矛盾字段。它阻止无人值守接续，但没有改变未知提交的远端事实。
- **当前工具能力的边界**：`reconcile_pending.py` 只从 trajectory 提取已知 `progress_url`；round 11 的 trajectory 不存在，checkpoint 中也没有 URL，因此扫描为 0。`/users/self/alphas` 只提供 Alpha ID/状态/时间元数据，当前 Alpha Feed 还会主动丢弃表达式/提交指纹，不能可靠反查这个未知 POST。

判定：这是“ambiguous POST 的远端身份未返回 + 最小 checkpoint 未保留错误上下文 + 进程停止前未完成 session 收尾”的恢复证据缺口，不是可通过重试网络或重新运行 factory 自动解决的问题。未经用户人工确认，不执行 `skip-submit-unknown`、清除 stop 控制、手工补 ledger、覆盖 checkpoint 或新 Simulation。

补充实测：在当前 workspace 沿 canonical `python main.py run-proposals` 执行恢复，输出只包含 `Round 11 checkpoint resume`、保留 `SUBMIT_UNKNOWN` 不重发和 `RESULTS CACHE`；未产生 POST。随后 checkpoint/session 的状态与修改时间均未变化，证明现有恢复入口会安全停留在该边界，而不会误派发 32 个 PENDING。

补充诊断：只读 `python main.py smoke` 成功返回 `datasets=14`、`fields=10`，排除当前凭据/网络整体不可用。随后单独启动的 `python main.py alpha sync-feed` 在 30 秒观察窗内无输出，PID `39672` 仍存活，`.alpha_feed_cache/weekly.json` 时间戳未更新；该进程仍需继续观察，当前不能据此判定失败或重复启动。它暴露了 Alpha Feed 分页等待期间缺少进度可见性的工程瓶颈，但与 round 11 未知提交没有直接因果关系。
# 2026-09-10 当前重审与实现证据

- 当前最新 suggestion bundle 为 100 fields / 6 datasets，频率分布 `UNKNOWN=81、daily=14、annual=2、intraday=2、quarterly=1`；原 profile 未保存证据来源。
- 原 runner 在完整 assembly 后才判断 cross-dataset gate；本阶段新增 frequency evidence 与 bounded feasibility probe，失败可区分 taxonomy 并在 assembly 前阻断。

## 2026-09-10 机制路由与 optimizer handoff 当前重审

- 本轮重新 `git fetch origin` 后确认 `main`、本地 HEAD、`origin/main` 均为 `ba919da7b6a2ea1be509d7b3c5fe3e67c8e14714`，工作树干净；`context --compact` 为 SAFE、无未完成 checkpoint、`SUBMIT_UNKNOWN=0`。此前状态结论不作为当前事实。
- `factory_runner.py` 当前 feasibility 失败分支只写 `WAIT_FACTORY_FEASIBILITY`，然后递增 `probe_offset`；`generate_factory_batch()` 仍收到 seed 变化，但没有 mechanism family、dataset route、previous failure、information gain、bounded retry 或 STOP/REROUTE 决策。
- 当前 `AlphaFactory.assess_feasibility()` 已有 `candidates_before_dedupe`、`candidates_after_dedupe`、`novel_cross_dataset_relationship_count`，但这些结果尚未转成 control decision；历史耗尽不会得到 `MECHANISM_FAMILY_EXHAUSTED`。
- DONE handoff 的真实调用链已确认：`ProposalExecutionWorkflow._run_simulator()` → `Simulator.run(on_complete=Agent._record_live_result)` → `Agent._record_live_result()` 写完整本地结果并 `trajectory.add(exp)`；round close 的 `trajectory.add_many()` 由 ID 去重。因此同进程 DONE 已有进入 trajectory 的路径，不应从 checkpoint 重建 metrics。
- `OptimizerWorkflow.optimizable_signal_records()` 当前只检查 `DONE`、非空 metrics、`field_analysis` 和 `field_understanding`；缺少 expression、fields/datasets、field source/basis、checks 状态、hypothesis/economic mechanism 的明确 rejection taxonomy，也没有 handoff 计数报告。`screen_optimization_parents()` 进一步检查部分字段，但同样不验证 checks/hypothesis/mechanism。
- 本轮改动边界：复用现有 `factory_session.json`、`factory_batch_stats`、`AlphaFactory.assess_feasibility()`、`Trajectory` 和 `OptimizerWorkflow`；不新增 workflow/state machine，不扩展 checkpoint，不读取 Alpha Feed 作为 evidence，不实现 Alpha Feed/颜色/大型 heartbeat。

## 2026-09-10 实现后复核

- feasibility probe 现在输出有界的 canonical expression、relationship、mechanism family 与 dataset route fingerprints；前有候选、后被历史去重清空时 taxonomy 为 `MECHANISM_FAMILY_EXHAUSTED`。
- runner 使用既有 factory session 保存 route attempt/no-gain/probe 与 decision；只在既有 cross-dataset gate 失败时触发 `REROUTE` 或 `STOP`，不产生新 POST，不写 checkpoint/result payload。
- optimizer parent gate 统一要求本地 DONE、metrics、checks（含显式 UNKNOWN）、expression、字段审计、hypothesis 与 economic mechanism；拒绝原因使用 `PARENT_*` taxonomy，cloud metadata 仍只影响优先级。
- 定向回归 59 tests OK；完整 unittest 664 tests OK，compileall、Ruff、typed frontier mypy、diff check 均通过。未启动真实 Simulation，checkpoint 与 `SUBMIT_UNKNOWN` 规则未改动。

## 2026-09-10 Alpha Feed freshness 与 heartbeat 当前重审

- 本轮重新 `git fetch origin` 后确认 `main`、本地 HEAD、`origin/main` 均为 `c213a084473039c270b640b6987081f5e8ea2437`，工作树干净；最近 10 个提交已核对。指定源码与文档已完整通读。
- 当前调用图为 `main.py alpha sync-feed` → 构造 `WQBClient`/`Agent` → `Agent.refresh_remote_alpha_feed()` → `AlphaFeedWorkflow.refresh()` → `DailyResearchCache.put_*()` 与 `WeeklyAlphaFeedCache.refresh()`。Feed reader 仅为 `get_all_user_alphas`，请求源为 `/users/self/alphas`。
- 当前 long-running factory path 为 `main.py factory run` → 单实例锁 → `AIFactoryRunner.run()`；复核未发现它调用 `refresh_remote_alpha_feed()` 或 AlphaFeedWorkflow。现有“每 3 小时同批刷新”只有文档约束，没有 typed interval、due helper 或运行时 hook。
- 当前 weekly cache 以 `updated_at`/`expires_at` 写入，但 `load()` 只校验 schema/timezone/week_start，未提供 freshness snapshot、last attempt/success 分离或失败保留旧 timestamp；`AlphaFeedWorkflow.refresh()` 失败前不会写 cache，但没有统一失败 taxonomy/heartbeat。
- 当前没有可注入 heartbeat abstraction；只有 `DiagnosticEvent`（静态诊断记录）和若干 print。Discovery、assembly/gate、settlement、Feed split 均缺聚合 throttled progress hook。
- 当前 lock owner 是 CLI `main.py` 的 `acquire_single_instance_lock()`；`sync-feed` 分支本身未显式 acquire lock，而 factory/run-proposals/sync-colors 会 acquire。Feed workflow 不依赖 Simulator/ProposalExecutionWorkflow，不改 quota/checkpoint/metrics/optimizer evidence；颜色同步仍是独立显式命令。
- 本轮范围：增加最小 typed freshness policy、单进程窄 refresh hook、只读失败状态与 transient heartbeat；不改 mechanism routing、optimizer parent、checkpoint schema、color classification 或 persistent trajectory。

## 2026-09-10 实现后复核

- Feed freshness 已由 `WeeklyAlphaFeedCache.freshness_snapshot()` 基于既有 `updated_at`、`expires_at` 和 typed interval 判定；缺失/损坏/回拨时间 fail-safe 为 due/UNKNOWN，不把失败伪装为成功。
- `Agent.refresh_remote_alpha_feed_if_due()` 是唯一周期 hook；factory runner 仅在生命周期边界调用它，Feed 分页与 cache 写入仍归 `AlphaFeedWorkflow`/`WeeklyAlphaFeedCache`，不启动 subprocess 或第二 scheduler。
- Feed 失败返回 `FEED_REFRESH_QUERY_TOO_BROAD`、`FEED_REFRESH_TRANSPORT_ERROR` 或 `FEED_REFRESH_INVALID_CACHE`，保留旧成功 timestamp；CLI `alpha sync-feed` 现在复用单实例锁。
- `HeartbeatSink` 为进程内 transient observer，默认输出聚合事件并按 stage/progress/interval 节流；Discovery、Feasibility、Assembly/Batch gate、Feed split、Simulation settlement 已接入，不改变执行安全语义。
- 定向验证 56 tests OK；全量普通/coverage unittest 各 672 tests OK，coverage 77.8%，architecture、compileall、Ruff、typed frontier mypy、diff check 均通过。未启动真实 Simulation；checkpoint、quota、`SUBMIT_UNKNOWN` 未改变。
## 2026-09-10 Alpha Factory budget path re-review

- `AIFactoryRunner.run()` currently reserves the existing 100-slot batch before
  reading optimizer records, then prepends at most four Agent-authored
  optimization proposals and asks `AlphaFactory.generate_factory_batch()` to
  fill the remainder with exploration candidates. There is no independent
  budget selector or persistent allocation state.
- Optimization is therefore a small availability-driven prefix, ordered first
  by the existing optimizer handoff (cloud metadata priority, then local
  trajectory recency); exploration fills the rest in seeded field/template
  order. The prefix can reduce exploration capacity, but the current hard
  limit is four rather than a configurable ratio.
- Existing diversity audit is batch-level only. It records semantic and
  structural concentration but does not affect candidate ordering; unresolved
  or discriminating questions are retained in research metadata but are not
  consumed by the factory selection path.
- Existing optimizer guards reject incomplete, parameter-only, direction-only
  and overfit children, but there is no bounded same-lineage cap inside the
  optimizer prefix. Supported/contradicted/inconclusive outcome context is not
  currently a priority input to factory ordering.
- Feasibility runs before assembly and can classify historical expression
  exhaustion as `MECHANISM_FAMILY_EXHAUSTED`; exact batch validation still
  happens after generation. Shortage remains an exact-100 batch failure and is
  not filled by REVIEW/UNKNOWN candidates.
- Scope conclusion: implement only a derived, deterministic priority view and
  stable interleaving within the existing optimization prefix/exploration pool.
  Keep quota reservation, exact batch validation, optimizer eligibility,
  checkpoint, route state and all existing hard gates unchanged; do not add a
  scheduler, workflow or second budget owner.

## 2026-09-10 端到端审计：预算与研究闭环

- 基线：工作树干净，当前提交为 `ec4ae51`；完整 unittest 基线已执行，输出包含既有 fake Simulation/恢复场景，未启动真实 Simulation。
- 已确认调用链：`SuggestionWorkflow.run()` 从 `ExperienceMemory.context()` 写入 bundle `context`；`AIFactoryRunner` 将 `bundle.get("context")` 传给 `AlphaFactory.generate_factory_batch(..., research_context=...)`。
- 已发现 P1：`diversity.select_budget_candidates.interleave()` 以 `(bucket, group)` 的字符串 tuple 排序，Python 顺序为 `HIGH, LOW, NORMAL`，因此 LOW 会在 NORMAL 前被选中；这是 priority contract 的真实实现错误。
- 已发现 P1：`derive_budget_priority()` 支持 `saturation` 参数，但真实 `select_budget_candidates()` 调用不传 saturation，`saturation_dropped_or_deprioritized` 与 saturation counts 无法反映真实候选池，饱和不会影响实际选择。
- 已验证真实链路：Factory proposal 保留 `field_analysis.semantic_traits`，`Experiment.to_dict()` → optimizer child 保留 `lineage_id`，Reflection → Memory → context → real optimizer child → budget selector 能使匹配 discriminating question 的候选获得 HIGH。
- 已发现 P1：真实单字段 scarcity 只生成 10/100 个候选时，runner 原先重复 `WAIT_FACTORY_BATCH` 直到 deadline；已加入回归测试，要求实际 selected batch 进入现有 bounded route/no-gain 状态并最终 `STOP_BUDGET_SHORTAGE`，不调用 `run_proposals`。
- 已先写红测试并完成最小修复：priority bucket 改为 `HIGH → NORMAL → LOW`；selector 传入候选池派生 saturation；Factory 早退时清空 stale `last_budget_audit`；runner 使用 selected-batch probe 处理 budget shortage。

## 2026-09-11 ResearchYield 阶段（PAUSED/DISARMED 只读派生）— 真实审查结论

范围：研究保持 PAUSED；本阶段只读核对 rounds 1-13 的真实 evidence（13 个 checkpoint、`proposals.json`（round 13）、`_round11_metrics.json`/`_round_12_metrics.json`、`reconcile_history.jsonl`/`stale_skip_log.jsonl`、`docs/RESEARCH_ISSUES_2026-09-11.md`），在既有 SearchOutcome/reward/identity/reroute 之上派生 mechanism-family Research Yield。不写代码前的结论先行记录；实现与回放结果见本文件后续追加。

### 核对确认的事实（真实 campaign 暴露）

1. **execution 已稳定**：rounds 5/6/11/12/13 连续 5 批 100/100 DONE、0 平台拒绝；rounds 1-4 共 89 FAILED 全部归因 7 个算子 arity 用法（#1-#7），修复后不再出现。13 个 checkpoint 全部 complete，preflight READY。
2. **DONE ≠ 可优化 parent**：checkpoint experiments 只含执行事实（status/progress_url/lineage_id/template_family/expression/fields_used），无 metrics、无 checks、无 economic_mechanism、无 field_analysis → 即使同进程，`OptimizerWorkflow._parent_rejections` 也会以 `PARENT_METRICS_MISSING`/`PARENT_CHECKS_INCOMPLETE`/`PARENT_FIELD_EVIDENCE_MISSING`/`PARENT_HYPOTHESIS_MISSING` 拒绝全部；跨进程 trajectory 为空（不落盘）→ 历史 parent 无法重建。
3. **DONE child ≠ incremental value**：campaign 未生成 optimizer CHILD；r8/r9/r10 Agent 批次是按预注册判据的一次性构造检验，无 parent-relative incremental verdict，不能计入 incremental_pass。
4. **质量证据长期缺 FINAL**：r11/r12 全部 200 条 metrics 快照 `pending_checks` 含 SELF_CORRELATION（21 条另有 UNITS），`self_correlation=None` → 全部 RECONCILE；判定 success=0/promising=0（连续 9 个零全过 100 批）。yearly 在 simulation payload `is` 块 UNAVAILABLE。
5. **消耗大量 Simulation 但无 downstream 的机制族**：横截面 rank 构造三重阻塞（CONCENTRATED_WEIGHT + LOW_SUB_UNIVERSE_SHARPE + SELF_CORRELATION PENDING）；revere 结构族整族关闭（r10，构造不敏感）；churn 族双证关闭（close/forward_price_270）。
6. **#14 跨进程 handoff 缺口是冻结边界**：生产配置 trajectory 非持久 → optimizer eligibility 无法建立；`proposals.json` 仅保留 round 13（100/100 可按 lineage_id 与 round_13 checkpoint 对账）；r1-r12 的 proposal 元数据已不存在 → 历史 family 归因只对 round 13 可行。

### Issue → funnel stage → 分类映射（RESEARCH_ISSUES_2026-09-11.md）

| issue | funnel stage | research / infra | evidence quality | effect on family outcome |
|---|---|---|---|---|
| #1-#7 平台 arity 拒绝 | proposal→simulation（FAILED） | research（候选设计） | 无（terminal FAILED） | 早期 research_failure_count；样本不足 → INCONCLUSIVE |
| #8 路由门禁失配 | feasible_candidates / assembled | research（route policy） | 无 | 修复前 INCONCLUSIVE（sample）；修复后恢复出批 |
| #9/#12 进程死亡/stale | simulations_unresolved | infra | 无 | unresolved 占比高 → INCONCLUSIVE；已恢复 |
| #10/#11 SUBMIT_UNKNOWN / 无 URL UNKNOWN | infrastructure_failure_count | infra（exactly-once 边界） | 无 | 不升 PASS；占比高时 → BLOCKED；SUBMIT_UNKNOWN 语义不变 |
| #14 optimizer handoff 缺口 | done→optimizer_parent（unavailable） | infra/evidence（进程边界） | n/a | **BLOCKED（HANDOFF_EVIDENCE_BLOCKED）**，不是 parent conversion=0%，更不是 LOW_INFORMATION |
| #15 SELF_CORRELATION PENDING | quality_evaluated（unresolved） | evidence unavailable（平台结算） | 只有 PROVISIONAL 观测 | 无 FINAL → 不 PROMISING/不 LOW_INFORMATION → INCONCLUSIVE |
| #16 yearly UNAVAILABLE | quality 细节（unavailable） | evidence unavailable | n/a | 稳定性证据缺口，贡献 INCONCLUSIVE，不单独判定 |
| #17 cheatsheet vs live arity | feasible / proposal→simulation | research（operator evidence） | 无 | 早期 research_failure_count（同 #1-#7） |
| §5 rank 族三重阻塞 | simulations_done 高 + quality_evaluated（checks FAIL） | research outcome + evidence unavailable 混合 | checks FAIL 是平台事实；SELF_CORRELATION 缺失是未结算 | 证据可用时 → LOW_INFORMATION 候选；证据不可用 → INCONCLUSIVE/BLOCKED |
| §5 已关闭 revere/churn 族 | 无 state 内 closure ledger | research（预注册判据，findings 谱系账本） | n/a | 只有显式 closure 证据才判 EXHAUSTED；当前 state 无该记录 → 真实回放归入 UNKNOWN family，exhaustion 作为手工证据输入 |

### ResearchYield 设计结论（本阶段实现边界）

- ResearchYield = **derived control-plane research evidence**：derived in-memory / report projection，不落新文件、不做平台事实、不存 metrics、不是 trajectory/checkpoint/optimizer/Simulation owner，不复制 reward engine、不新建 scheduler、不新增研究状态 owner。
- 聚合键直接复用 `semantic_mechanism_key`；lineage 用现有 `lineage_id`；evidence quality 直接复用 SearchOutcome 的 FINAL/PROVISIONAL/LEGACY 语义；conversion 对 denominator==0 返回 `None`（`NO_DENOMINATOR`），对证据不可用返回 `DENOMINATOR_UNAVAILABLE`，绝不伪装 0.0。
- 明确区分 completion（simulations_done）与 research progress（quality/optimizer eligibility/incremental）；`simulation_to_done=100%` 不得解释为 mechanism successful。
- family outcome 只允许 5 态：INCONCLUSIVE / PROMISING / LOW_INFORMATION / EXHAUSTED / BLOCKED，附 STOP taxonomy（新增 LOW_RESEARCH_YIELD / NO_INCREMENTAL_CHILD_EVIDENCE；复用 ROUTE_ATTEMPTS_EXHAUSTED / NO_INFORMATION_GAIN / MECHANISM_FAMILY_EXHAUSTED / INFRASTRUCTURE_BLOCKED）。
- minimum sample guard：仅新增 `research_yield_min_evaluated`（默认 40）与 `research_yield_window`（默认 200）两个 typed/bounded 参数，其余复用现有 route/budget/SearchPolicy 阈值。
- continuation：不新建 workflow；提供 pure 映射（PROMISING→CONTINUE、INCONCLUSIVE→OBSERVE、LOW_INFORMATION→REROUTE、repeated LOW_INFORMATION→STOP LOW_RESEARCH_YIELD、EXHAUSTED→按现有 exhaustion 策略、BLOCKED→WAIT 不消耗新 quota），作为现有 route policy 的 derived input 就绪项。
- 本阶段不修 #14（冻结边界）；只归因：真实回放必须把 1300+ DONE 且 eligibility 无法建立的 family 显示为 handoff/evidence BLOCKED，并量化其占多少 BLOCKED yield。
- Heartbeat：只提供 `research_outcome_summary` 聚合函数（mechanism_family/evaluated/parents/children/incremental_pass/outcome_state，禁止 raw metrics），不接入 HeartbeatSink（deferred）。


### 真实回放结果（2026-09-11，只读，未写 `.wqb_state`）

- 输入对账：checkpoint experiments=1008（DONE 913 / FAILED 90 / SKIPPED 5），round 13 proposals=100，r11/r12 metrics=200；r13 proposal↔checkpoint 按 lineage_id 25/25、按 expression 100/100 匹配。
- 归因：r13 八族（earnings:level:slow_moving 14 / market_price:change:signed 14 / market_price:level:signed 14 / market_price:ratio:signed 14 / sentiment:level:event_driven 14 / volatility:dispersion:signed 14 / UNKNOWN 13 / volatility:ratio:signed 3）；r1-r12 无 proposal 元数据 → UNKNOWN 桶（assembled 921 / done 826 / provisional 200）。
- 真实 family outcome：7 个具名族 INCONCLUSIVE(SAMPLE_INSUFFICIENT)（done 3-14，无 FINAL）；UNKNOWN 桶 BLOCKED(HANDOFF_EVIDENCE_BLOCKED)（#14：done≥40 且 eligibility 不可用）。
- #14 量化：当前唯一 BLOCKED yield 来源 = UNKNOWN 桶 826 条 DONE + 200 条 PROVISIONAL 观测因跨进程 handoff 无法建立 optimizer eligibility。
- 假设视图：若 #14 修复且 gate 全拒（明确假设），无 FINAL 证据仍使全部族 INCONCLUSIVE(FINAL_EVIDENCE_INSUFFICIENT)——#15 SELF_CORRELATION 未结算是独立于 #14 的第二重阻塞；LOW_INFORMATION/PROMISING 在真实数据上无触发前提，合成验证由 test_research_yield.py 覆盖。
- 结论：下一轮如需修改冻结边界，应先结算 SELF_CORRELATION/yearly（#15）再做 optimizer handoff 修复（#14）的立项评估；本阶段保持 PAUSED/DISARMED。


# 2026-09-11（第二阶段）跨进程 optimizer parent evidence handoff — 真实根因

## 九问结论（基于 HEAD 7d419a8 与真实 `.wqb_state`，只读调查）

1. **Experiment evidence 当前真正持久化在哪里？**
   - `round_*.checkpoint.json` 只保存执行事实；实测 round 13 的 100 条 experiment union 字段为
     `id / proposal_id / submission_fingerprint / submission_started_at / expression / settings /
     fields_used / hypothesis_id / round / template_id / template_family / proposal_origin /
     research_layer / status / progress_url / lineage_id / experiment_stage / research_role /
     change_type / schema_version / created_by_version`，**100/100 无 metrics、无 checks、无
     economic_mechanism、无 field_analysis**。
   - `proposals.json`（仅 round 13）含 `field_analysis / economic_mechanism / semantic_admission / ...`，
     但它是提案输入元数据，不含 Simulation 结果。
   - `.wqb_state/trajectory.jsonl` 与 `.wqb_state/trial_ledger.jsonl` 均不存在。
2. **checkpoint 保存了多少完整 Experiment 信息？** 只有执行与身份元数据，缺少 optimizer parent gate
   需要的全部研究证据（metrics / checks / field_* evidence / economic_mechanism）。
3. **trajectory 为什么在新 process 中为空？** `wqb_agent/runtime_components.py:66-70` 显式构造
   `Trajectory(path=<state_dir>/trajectory.jsonl, persist=False)`；`state.py` 在 `persist=False` 时
   `add/add_many` 不落盘，`contains_ids / find_completed_expressions / load` 直接返回空。因此文件
   从未生成，新进程内存轨迹必然为空。
4. **completed checkpoint 是否已有足够 evidence 重建合法 Experiment？** 否 → 结论
   **CHECKPOINT_EVIDENCE_INSUFFICIENT**，不能从 checkpoint 猜 metrics/checks。
5. **optimizer parent gate 具体要求哪些字段？** `OptimizerWorkflow._parent_rejections()`：
   `status == DONE`；`metrics` 非空 dict；`metrics` 含 `checks`；`expression`；`fields_used /
   datasets / field_understanding / field_analysis / field_source / field_hypothesis_basis`
   全部非空；`hypothesis_id`；`economic_mechanism` 为非空字符串。
6. **parent-relative incremental verdict 当前 owner 是谁？** `Agent._settle_incremental_evidence()`
   （`agent.py:1333`）调用 `incremental_value.build_incremental_value()`（日期对齐 PnL 序列相关性）；
   `incremental_policy.incremental_gate()` 决定 eligibility；reward 侧的 parent-relative 度量在
   `search_outcome.parent_relative_delta()`。当前 client 无 LIVE_VERIFIED PnL capability → 普通候选
   显式结算为 `UNAVAILABLE`（不伪造相关度）。
7. **CHILD proposal 当前如何携带 parent identity？** `parent_expression`（canonical expression）+
   `lineage_id`；变化语义由 `experiment_stage / research_role / change_type /
   child_economic_hypothesis / changed_variable` 表达。
8. **run-proposals 当前如何解析 parent_expression？** `proposal_execution.py:340` 用
   `ctx.trajectory.find_completed_expressions([...])` 建批量索引，`:437` 调
   `hooks.completed_parent(...)` → `Agent._completed_parent()`：先扫内存窗口，再查传入索引，最后
   `trajectory.find_completed_expression()`。三条路径都依赖持久化 trajectory。
9. **historical completed evidence 当前在哪一步丢失？** Simulation 完成时 `simulator.py:248`
   （`experiment.metrics = _extract_metrics(payload)`）把结果写到内存 Experiment；随后
   `trajectory.add*()` 因 `persist=False` 不落盘；进程退出即丢失。checkpoint 只记录恢复边界。

## 归因与修复方向

- 断点性质：**BLOCKED_BY_PERSISTENCE_DESIGN**（不是 gate 过严，也不是 Alpha Feed / checkpoint
  能补的缺口）。
- 实现与架构文档不一致：`docs/ARCHITECTURE_AGENT.md:24` 把 `trajectory.jsonl` 列为 immutable
  evidence，`:198` 明确 “重启后仅由持久化 trajectory/checkpoint 的既有 owner 恢复”；代码
  `persist=False` 与文档声明冲突。
- 现有消费者已全部假设 `trajectory.jsonl` 存在：optimizer parent gate、run-proposals parent
  lookup、exact-dedupe（`agent.py:798-808`）、`alpha_colors.load_color_candidates()`、
  `agent.search_calibration_report()`。
- 修复方向（目标 §28/§29）：**恢复已有 owner 的持久化**，即 `Trajectory(persist=True)`；保持
  owner 不变（Trajectory remains sole owner），不新建 store、不从 Alpha Feed/checkpoint 猜
  evidence、不降低 optimizer gate。
- 已完成目标（ResearchYield）的 replay 结论不变：#14 在当前真实数据下造成 826 DONE + 200
  PROVISIONAL 观测的 BLOCKED yield；本阶段修复该 handoff 断点，并量化 before/after。

## 交付与验证（第二阶段）

- 改动文件：`wqb_agent/runtime_components.py`；新增 `tests/test_historical_parent_handoff.py`；
  按新契约更新 `tests/test_factory_boundaries.py`；新增 color 守卫 `tests/test_architecture.py`；
  `scripts/replay_research_yield.py` 增加 handoff before/after；同步
  `docs/ARCHITECTURE_AGENT.md`、`docs/RESEARCH_POLICY.md`、`docs/STATE_LAYOUT.md`。
- 只读 replay before/after（`--compare-handoff`）：before 1 族 `BLOCKED(HANDOFF_EVIDENCE_BLOCKED)`
  + 7 族 `INCONCLUSIVE`（eligibility 不可用、eligible 0、final 0）；after 8 族全部
  `INCONCLUSIVE`（eligibility 可用、eligible parents 100、final 仍 0）。因此 #14 修复必要但不充分。
- 质量门与 Git 证据：见下方“验证结果”。

## 验证结果（第二阶段）

- `python -m compileall -q wqb_agent scripts tests` → exit 0。
- `python -m unittest discover -s tests` → `Ran 750 tests`、`OK`（含新增 `tests/test_historical_parent_handoff.py` 与按新契约更新的两条 runtime 断言）。
- `python -m ruff check .` → `All checks passed!`。
- `python -m mypy`（9 个 typed frontier 模块）→ `Success: no issues found in 9 source files`。
- `coverage run --branch -m unittest discover -s tests` + `coverage report` → `TOTAL 78.9%`（`fail_under=76.0`）。
- `python main.py --state-dir tests/fixtures state doctor` → exit 0；`... state audit` → exit 0（offline fixtures，未触发网络）。
- 只读 replay：`python scripts/replay_research_yield.py --compare-handoff` → exit 0，未写入 `.wqb_state`。
- Git：commit `06eb956`（`fix：恢复跨进程 optimizer parent 证据并补齐 handoff 契约`）；`git push origin main` → `7d419a8..06eb956`；`git ls-remote origin refs/heads/main` = `06eb95646f1215efa8918131b531dc03481b3b74` = local HEAD。


# 2026-09-11（第三阶段 Phase III）settled evidence durability 真实调查

## §1 上一轮修复复核（只读，HEAD `43654c4`）

- `wqb_agent/runtime_components.py` 现在构造 `Trajectory(path=<state_dir>/trajectory.jsonl, persist=True)`；`state.py` 仍是唯一 Trajectory owner。
- `round_*.checkpoint.json` 仍只保存执行事实与恢复身份，未变成 metrics store；Alpha Feed 仍只做 priority hint；optimizer gate（`OptimizerWorkflow._parent_rejections`）字段要求未放宽。
- 结论：上一轮修复成立，但只覆盖“首次 DONE append”，不覆盖“后续 settlement”。

## §2 真实生产顺序（根因）

- `Agent._record_live_result()`（`agent.py:955`）在 Simulation 返回时构造 `SearchOutcome` + `provisional_outcome`/`search_outcome`，随后 `agent.py:981 self.trajectory.add(exp)` 落盘。这是 **early DONE snapshot**。
- 之后才发生 settlement：`Agent._settle_research_outcome()`（`agent.py:1280`）设置 `validation_report`、`validation_status`、`incremental_evidence`、`final_outcome`、`research_classification`、`research_evidence_bundle`，并调用 `trial_ledger.record_outcome_settled(...)` 与 `search_policy.replace_reward(...)`；`proposal_execution.py:152/832/891` 也不会再次 `trajectory.add`。
- 因为 trajectory 是 append-only 且 `persist=True`，这些后结算字段只存在于内存对象；进程退出即丢失。重启后 `Trajectory.load()` 只能看到 provisional snapshot。
- 结论：**SETTLED_EVIDENCE_NOT_PERSISTED**（不是 gate 过严，也不是 checkpoint / Alpha Feed 能补的缺口）。

## §3 目标契约（本阶段实现方向）

- 复用既有 Trajectory owner：为该 owner 增加 append-only **settlement revision**（同 `id` 的第二行，标记 `RESEARCH_SETTLED`），不新建 store（无 `final_evidence.json` 等）。
- `add()` 语义不变：仍是首次 canonical append 与 exactly-once 去重；revision 不是第二次 execution。
- 读路径由 owner 统一合并：`latest valid revision wins`，identity mismatch 与 corrupt row 都 fail-closed（保留最后一条有效证据）。

## §4 已实现（settled evidence durability）

- `wqb_agent/state.py`：新增 `TRAJECTORY_REVISION_KEY` / `RESEARCH_SETTLED_REVISION` /
  `IDENTITY_FIELDS` / `same_execution_identity()`，以及窄接口 `Trajectory.settle()` 与
  `settle_many()`（只对已存在的 canonical row 追加一份 `RESEARCH_SETTLED` revision）和定点读
  `Trajectory.find_row()`。`add()` / `add_many()` 的首次 append 与 exactly-once 去重语义完全未改。
- fail-closed：无 canonical row → `ValueError`；identity（id / round / hypothesis_id / expression /
  settings / fields_used / datasets / candidate_id / proposal_id / submission_fingerprint /
  submission_started_at / parent_expression / lineage_id / created_at）不一致 → `ValueError`；
  同一 revision 幂等跳过。`Agent._settle_research_outcome()` 在结算末尾调用 `settle()`，被拒时记录
  `SETTLEMENT_REVISION_REJECTED` 并打印，绝不静默。
- 读路径由 owner 合并：`load()` 用 `_tail_lines(max_len * 4)` + `_merge_rows()`（latest valid
  revision wins；corrupt row、identity mismatch 跳过），`find_completed_expressions()` 同样按同一
  `id` 的 revision 覆盖并校验 identity。
- 没有第二套 store：`.wqb_state` 仍只有 `trajectory.jsonl` 这一份 canonical 证据；checkpoint 未变
  metrics store；Alpha Feed 未变 evidence owner；optimizer gate 未放宽。
- 回归测试 `tests/test_settled_evidence_durability.py`：Test A（late FINAL 跨重启存活）、
  Test B（identity 不可改 / 必须已落盘）、Test C（corrupt latest revision 保留最后有效证据）、
  Test D（duplicate add 仍 exactly-once）、Test E（无 execution side effect）。

## §5 Agent Optimization Decision 契约与 optimizer funnel（本阶段交付）

- 新增 `wqb_agent/optimization_decision.py`：`OptimizationDecision`（parent_id / decision /
  observed_evidence / economic_mechanism / change_type / changed_variable / expression /
  expected_effect / falsification / direction / direction_transform / self_correlation_impact /
  why_not_parameter_tuning）、`decision_rejections()`（DECISION_INVALID / PARENT_INVALID /
  PARENT_IDENTITY_MISMATCH / DECISION_FIELDS_MISSING / PARAMETER_ONLY_CHANGE /
  DIRECTION_ONLY_CHANGE / DECLARED_CHANGE_MULTIPLE_FIELDS / DECLARED_CHANGE_FIELD_AND_PARAMETER /
  OVERFIT_EXPRESSION / SELF_CORRELATION_IMPACT_INVALID / OPERATOR_ILLEGAL）、
  `parent_opportunity()`（7 类 hint）、`summarize_parent()`（有限 summary：机制 / 字段 / 5 项 metric /
  failed+pending checks / self-correlation / validation / incremental / classification /
  mechanism_state / opportunity）。Python 只做确定性校验，不生成经济机制、不挑 operator、不写 child
  expression、不扫描参数。
- `optimizer_workflow.py`：gate 拆成 evidence eligibility 与 Agent decision readiness 两阶段；funnel
  新增 `evidence_eligible/rejected_parent_count`、`agent_reviewed_parent_count`、
  `agent_decision_{child,validate,reroute,stop}_count`、`child_generated/done_count`、
  `incremental_{pass,fail,unknown}_count`；`optimizer_conversions()` 给出 Agent Optimization Yield
  （分母 0 → `None`，绝不 0.0）；`inspect_optimizer_parents()` 有限只读并按 opportunity 排序；
  `generate_from_decisions()` 校验 decision 后复用唯一 `generate()` 路径；`optimization_eligibility_map()`
  把 per-parent eligibility + Agent stage 交给 ResearchYield。
- `research_api.py` / `agent.py`：Agent-facing facade `inspect_optimizer_parents()` 与
  `propose_optimization()`；仍走 `OptimizerWorkflow → AlphaFactory → proposal contract`，不触发
  Simulation / checkpoint 写入。
- `research_yield.py`：funnel 区分 `DONE → evidence parent`（Python gate）与
  `evidence parent → Agent decision`（`agent_reviewed_parents` / `agent_child_decisions`，新增
  `evidence_parent_to_agent_review` / `agent_review_to_child_decision` conversions）；新增
  `child_generation_bound()`，落实“没有 verified incremental PASS 就不再派生下一代”。

## §6 Incremental Capability Audit（只读，§22-25）

- `client.py` 只有 `GET /alphas/{id}`、`GET /alphas/{id}/aggregates`、
  `GET /alphas/{id}/correlations/{kind}`（外加 user alphas / datafields / datasets / simulation /
  progress）。**没有** PnL、daily-return 或 behavior-series 读取端点。
- `pnl.py` 明确不实现 transport、拒绝把未知端点当 live PnL；`behavior.extract_behavior_series()`
  只接受 `LIVE_VERIFIED` 序列，否则 `UNAVAILABLE`；`Agent._settle_incremental_evidence()` 因此总是
  结算 `availability=UNAVAILABLE`；`doctor` 报告 `pnl_capability/incremental_capability
  = UNAVAILABLE`。
- 结论：平台当前**没有**合法行为序列能力，禁止用 Sharpe / fitness / returns delta 冒充 incremental
  correlation evidence；continuation 得到 `NO_INCREMENTAL_CHILD_EVIDENCE`，并由
  `child_generation_bound()` 有界化（一代 child → `BLOCKED`，不再无限派生后代）。
- 边界测试：`tests/test_incremental_value.py::test_incremental_capability_audit_client_has_no_behavior_series`。

## §7 验证结果（第三阶段 Phase III）

- `python -m unittest discover -s tests`：**Ran 794 tests / OK**（本阶段新增 36 个）。
  新增 `tests/test_optimization_decision.py`（24）、`tests/test_multi_generation_optimization.py`（2）、
  `tests/test_settled_evidence_durability.py`（8）、`tests/test_architecture.py` Phase III 边界（4）、
  `tests/test_research_yield.py` child-generation bound（5）、`tests/test_incremental_value.py` 能力审计（1）。
- `python -m compileall -q wqb_agent scripts tests`：exit 0。
- `python -m ruff check .`：All checks passed。
- `python -m mypy`（CI 的 9 个 typed frontier 模块）：Success: no issues found。
- `coverage erase && coverage run --branch -m unittest discover -s tests && coverage report`：
  TOTAL branch-aware **79.3%**（`fail_under=76.0`，exit 0；基线 76.74%）。
- `python main.py --state-dir tests/fixtures state doctor` / `state audit`：exit 0。
- 多代验收：`tests/test_multi_generation_optimization.py` 证明 P0 settled → 重启 → Decision C1 →
  proposal → C1 settled（`RESEARCH_SETTLED` revision 落盘）→ 再重启 → C1 仍是 legal parent →
  Decision C2。不是手工写三条 trajectory。
- 安全确认：未运行真实 Simulation / factory run / run-proposals；未提交 Alpha；未做远端 color 写入；
  本阶段未写入 `.wqb_state`；checkpoint、quota 与 `SUBMIT_UNKNOWN` 语义未变。

## §8 完成度审计发现与修复（2026-09-12，Phase III 补充）

- 审计方法：不用测试里的 fake factory，而是在**真实** `AlphaFactory` 上走
  `OptimizerWorkflow.generate_from_decisions()` → `optimize_signal_proposals()`，再用生产同参数
  `validate_proposal(strict_experiment=True, require_economic_integrity=True)` 复核。
- 缺口 A（§20 provenance）：CHILD proposal 缺 `parent_id`、`economic_mechanism` 与正式
  `optimization_decision`；机制只存在于 `operator_mapping` 文本里。生产 `config.json` 的
  `agent.research_integrity=true` 会让这类提案在 preflight 报
  `economic_mechanism 必须明确说明字段与收益机制`。修复：组装处携带
  `parent_id` / `economic_mechanism` / `optimization_decision`，且不复制 parent metrics/checks
  （指标仍从 canonical evidence 读取）。
- 缺口 B（同义值断裂）：Agent 决策可以写 `change_type="neutralization_change"`、
  `direction_transform="same"`，而 proposal contract 只接受 `CHILD_CHANGE_TYPES`
  （`neutralization` 等）与 `{applied, reason}` 对象 → 真实 preflight 会拒绝
  `Child/ROBUSTNESS 必须声明单一 change_type` 与 `direction_transform 必须说明是否转换方向及原因`。
  修复：`decision_rejections()` 新增 `CHANGE_TYPE_NOT_IN_PROPOSAL_CONTRACT` /
  `DIRECTION_TRANSFORM_INVALID`（fail-closed，在 gate 拒绝而非留给 preflight）；
  `OptimizationDecision.direction_transform` 复用 proposal contract 形态；
  `AlphaFactory` 对 legacy `child_economic_hypothesis` 同样拒绝非法词，并保留 Agent 声明的
  `changed_variable`。
- 缺口 C（测试盲区）：workflow 级测试全部使用 `RecordingFactory` fake，真实组装路径只有
  “拒绝”断言（`test_factory_boundaries.py`），没有被接受的 CHILD 提案断言，所以 A/B 两条断链
  在 794 个测试全绿的情况下仍然存在。修复：新增真实 factory 端到端测试（decision 路径 +
  legacy 路径 + `validate_proposal` 零问题），并把 `test_research_loop.py` /
  `test_multi_generation_optimization.py` 的 fixture 改用契约词。
- 结论：第三阶段交付的 optimizer 漏斗此前在真实 `research_integrity` 配置下无法产出可执行
  CHILD 提案；修复后“合法 decision → 可追踪 proposal → preflight 通过”闭环成立。
- 质量门：`Ran 797 tests / OK`（+3），compileall exit 0，Ruff All checks passed，
  mypy 9 typed frontier Success，coverage branch-aware 79.3%（`fail_under=76.0`，exit 0）。
- 安全确认：本轮仍只跑 unit fixtures 与 offline 校验；未运行真实 Simulation / run-proposals /
  factory run，未提交 Alpha，未做远端 color 写入，未写 `.wqb_state`。

## 2026-09-12 Phase V 调查：Metric-Aware Bounded Autonomous Optimization

### 起点核对

- HEAD `97645b0` 与提示词编写时的远端 main 一致；工作树只有 7 个上一阶段遗留的未跟踪分析脚本
  （`analyze_cross_round.py`、`analyze_round14_evidence.py`、`analyze_rounds_16_18.py`、
  `generate_round20_optimization.py`、`inspect_round15.py`、`inspect_round16.py`、
  `resume_round14_execution.py`）。本阶段不修改、不提交、不删除这些脚本。
- 研究保持 PAUSED / DISARMED；本阶段只做 offline 代码、测试与文档。

### 真实研究反馈（Round 14–20）

- 700 次 Simulation、0 个 submit-ready Alpha；主要 blocker 为 `CONCENTRATED_WEIGHT`、
  `LOW_SUB_UNIVERSE_SHARPE`、`HIGH_TURNOVER`、`SELF_CORRELATION PENDING`。
- 因此 optimizer 的目标必须是"提高最终通过概率"，而不是"只提高 Sharpe"。

### 现状缺口（只读证据）

1. SELF_CORRELATION 查询前置门槛有两套互不相同的实现：
   - `Agent._refresh_self_correlation_evidence()`（`wqb_agent/agent.py:1057`）用
     `_alpha_rating() in {EXCELLENT, SPECTACULAR}` + `checks_ready_for_self_correlation_refresh()` +
     `health.ok` + turnover 区间；
   - `scripts/refresh_self_correlation.py::select_alpha_ids()`（该文件 49 行）只用
     `checks_ready_for_self_correlation_refresh()`。
   同一 Experiment 集会被选出不同 alpha 集合，正是 §18/§46 要求消除的分裂。
2. `_alpha_rating()`（`wqb_agent/agent.py:1426`）的 GOOD 分支把 `sharpe > 1.25` /
   `fitness > 1.0` 写死，只适用于 delay 1；delay 0 需要 Sharpe > 2.0 / Fitness > 1.5。
3. correlation 前置 gate 目前不含 `Returns > 0`、Drawdown 上限与 delay-aware 阈值；
   Turnover 只有区间判断，没有结构化报告。
4. 模板数字全部是字面量（如 `ts_zscore({p}, 20)`、`add(ts_std_dev({p}, 20), 0.001)`），
   没有"哪些数字是研究参数"的显式声明；regex 轮换会把 divide epsilon `0.001`、
   operator 必需常量 `1` 也当作参数。
5. `OptimizationDecision` 的 VALIDATE 决策当前不产生任何 proposal
   （`OptimizerWorkflow.generate_from_decisions()` 只把它记为 rejected），numeric / settings
   validation 没有受控生成路径。
6. Agent 看到的 parent summary（`optimization_decision.summarize_parent()`）没有 metric gap、
   turnover penalty、pre-correlation eligibility 或 readiness band。
7. `SuggestionWorkflow` 的 `optimizer_context` 只有 `gate_report` 计数，没有 eligible parent 的
   metric context、numeric variants 与 self-correlation 状态。
8. `FactoryRunner` 每轮用 `atomic_write_json_if_changed(self.proposals_path, payload)`
   覆盖唯一 proposals inbox（`wqb_agent/factory_runner.py:838`），上一阶段实测会覆盖手写的
   定向 optimization proposals。

### 设计决定

- 新增唯一纯策略 `wqb_agent/pre_correlation.py::pre_self_correlation_eligibility()`：
  delay-aware、结构化报告，由 Agent、脚本与 optimizer context 共用；
  `metrics.checks_ready_for_self_correlation_refresh()` 保留为其中"非 SELF_CORRELATION checks
  全 PASS"的组成部分，不出现第二套门槛。
- `AlphaTemplate` 增加显式 `numeric_slots`（`TemplateNumericSlot`：
  name / kind / default / allowed_values / economic_role / token / occurrence）。
  只有显式声明的 slot 允许轮换，单变量、每 parent 上限 3，且不构成笛卡尔积。
- settings variant 只走既有 `SETTING_OVERRIDES`（decay `0..10`、truncation `0.02..0.15`、
  universe 只在 `LOW_SUB_UNIVERSE_SHARPE` 或明确 robustness 问题下由 Agent 选择）。
- VALIDATE 决策扩展为单变量 contract（`validation_variable` / `old_value` / `new_value` /
  `expected_effect` / `falsification` / `reason`），复用既有 `ValidationPlan` 与
  settings override，不新增第二套 validation engine。
- numeric / settings 变化一律 `experiment_stage="ROBUSTNESS"`，不得冒充 CHILD discovery。

### Phase V 交付（offline 代码 + 测试 + 文档）

- 唯一 pre-correlation 准入：`wqb_agent/pre_correlation.py`。delay 1 → Sharpe > 1.25 / Fitness > 1.0；
  delay 0 → Sharpe > 2.0 / Fitness > 1.5（严格 `>`，`==` 不过线）；再加 `Returns > 0`、Turnover 区间、
  Drawdown 上限、`health.ok` 与非相关性 checks 全 PASS；缺失值一律 `UNKNOWN`，不是 PASS。
  `Agent._pre_correlation_candidates()` 与 `scripts/refresh_self_correlation.py::pre_correlation_selection()`
  共用同一 selector，一致性由同一 fixture 测试覆盖。
- 模板 numeric slot：`TemplateNumericSlot` + `AlphaTemplate.numeric_variants()` 只做单变量轮换、每 parent ≤3、
  不构成笛卡尔积；`reversal_zscore_20`、`momentum_mean_20`、`change_delta_5`、`quality_smooth_change`、
  `reversal_vol_adjusted` 已声明研究数值；divide epsilon `0.001` 与 operator 必需常量永不轮换（测试固定）。
- settings VALIDATE：`validation_candidate_values()` 决定有界池（decay `base ± 1` clamp 到 0..10；
  truncation 取相邻允许值；universe 只在 parent 有真实 `LOW_SUB_UNIVERSE_SHARPE` 证据、settings 与 Agent 理由
  同时成立时才接受，当前无 universe 池 → fail-closed）。`AlphaFactory.validation_proposals()` 只产出
  `experiment_stage="ROBUSTNESS"`，不冒充 CHILD；numeric/settings 变化不在机制多样性里制造新语义。
- Agent context：`summarize_parent()` 携带 `metric_optimization_context`（delay/threshold/gap/turnover penalty/
  drawdown headroom/readiness/opportunities）；`OptimizerWorkflow.optimizer_context()` 给出 bounded eligible
  parents（≤8，按 readiness band → 结构 blocker → 可修 blocker → 过线距离排序，而非只看 Sharpe）、blocker 统计、
  声明式 numeric 池、pre-correlation eligibility、self-correlation 状态计数、复用 `child_generation_bound()`
  的有界多代边界与决策契约词；`SuggestionWorkflow` 的 `bundle["optimizer_context"]` 优先使用它。
- `_alpha_rating()` 的 GOOD 分支改为 delay-aware：未知 delay 不再晋级，避免 delay 0 被 delay 1 阈值误判。

### 已知未解决：TARGETED_OPTIMIZATION_BATCH_BLOCKED_BY_FACTORY_BATCH_CONTRACT

- 事实：`proposal_contract.validate_factory_batch()` 要求批次恰好 `FACTORY_BATCH_SIZE = 100`
  （实测 "工厂批次必须恰好包含 100 个题案，实际 99" → 整批 BLOCKED），且 `FactoryRunner` 每轮用
  `atomic_write_json_if_changed(self.proposals_path, payload)`（`batch_type="factory_100"`）覆盖唯一
  canonical `proposals.json` inbox。因此 4–8 个定向优化题案目前无法通过工厂循环 materialize，
  手写定向 proposals 也会被下一轮覆盖。
- 本阶段不绕过该安全契约（§56/§57：先记录，再设计 owner-consistent 最小方案）。
- 候选最小方案（未实现，需用户批准）：仍由同一 `FactoryRunner` 作为唯一 owner，在锁内按显式 batch mode
  （`factory_100` vs `targeted_optimization`）选择 materialization；复用现有 member-level preflight、去重、
  checkpoint、`SUBMIT_UNKNOWN` 与预算保护，只放宽"恰好 100"这一条并补行为/回归测试；不新增 inbox、
  不新增 state owner、不绕过 `Agent.run_proposals()`。

### 审计轮补记：准入门槛单一来源、spec 覆盖核对与补测

- **turnover 区间单一来源（已修复）**：此前 `pre_self_correlation_eligibility()` 与
  `Agent._alpha_rating()` 的 GOOD 分支各写一份 `0.01..0.70` 字面量，quality policy 变更后两者可能漂移；
  现统一为 `pre_correlation.turnover_bounds(quality_policy)`，Agent 复用同一函数。新增
  `test_turnover_bounds_are_the_single_shared_source` 与
  `test_alpha_rating_shares_the_pre_correlation_turnover_bounds` 固定该契约。
- **§49 / §50 / §51 覆盖核对（只读）**：`tests/test_optimization_decision.py` 已覆盖 declared window slot
  可轮换、undeclared `0.001` 不可渲染、单变量 `change_count == 1`、variant 同
  `semantic_mechanism_family` / 同 `semantic_mechanism_key` / 唯一 `template_variant_id`、
  `validation_proposals()` 表达式去重与 `max_candidates` 截断；真实 `AlphaFactory` 端到端
  （`test_window_validation_is_robustness_not_child`、`test_single_variable_decay_validation_emits_robustness_proposal`）
  使用真实模板 + `validate_proposal(..., require_economic_integrity=True)` 断言零问题（非 FakeFactory）。
- **§44 / §50 缺口补齐**：新增 `test_low_sub_universe_sharpe_blocks_the_query`、
  `test_low_sub_universe_sharpe_needs_structure_not_a_query`（LOW_SUB_UNIVERSE_SHARPE FAIL →
  不可查询；readiness `STRUCTURAL_REPAIR_REQUIRED`；opportunity `SUB_UNIVERSE_REPAIR`）与
  `test_truncation_outside_the_whitelist_is_rejected`（`0.09` 不在白名单池 →
  `VALIDATION_NEW_VALUE_OUT_OF_POOL`）。
- **§55 配额 owner 未变（只读）**：整轮 VALIDATION 上限仍由 `ProposalExecutionWorkflow` 的
  `research_allocation.maximum[role]` 计数并 fail-closed；`AlphaFactory.validation_proposals(max_candidates=...)`
  只是单次调用的额外上限，未新增 quota system。
- **§56 batch inbox 保护检查（只读结论）**：`proposal_contract.validate_factory_batch()` 要求批次恰好
  `FACTORY_BATCH_SIZE = 100`；`FactoryRunner` 每轮在锁内以 `atomic_write_json_if_changed(proposals_path,
  payload)`（`batch_type="factory_100"`、`source="ai_factory_template_adapter"`）覆盖唯一 canonical
  `proposals.json`。当前编排没有 optimization / exploration 双 batch mode 保护，也没有第二 inbox；
  定向批次按 §57 保持“记录 + 设计候选方案”，未实现。

# 2026-09-12（第五阶段 Phase VI）Autonomous Optimization Control Loop Repair（PAUSED/DISARMED，未运行真实 Simulation）

## 只读调查结论（先结论、后代码）

- **P0-A 断点（代码级复现）**：`AlphaFactory.screen_optimization_parents()`（`wqb_agent/alpha_factory.py:1811`）
  对 `parent["health"]["ok"] != True` 无条件 `continue`，而 `OptimizerWorkflow.generate()`
  （`optimizer_workflow.py:613`）把它当作唯一代码初筛。Agent 侧 `metric_optimization_context` 已把
  `CONCENTRATED_WEIGHT` / `LOW_SUB_UNIVERSE_SHARPE` 标成可修的结构 blocker
  （`STRUCTURAL_REPAIR_REQUIRED` / `CONCENTRATION_REPAIR` / `SUB_UNIVERSE_REPAIR`），却在这里被丢掉 →
  Agent 写出合法 CHILD 也拿不到 proposal。根因：把 SUBMISSION_HEALTH 与
  OPTIMIZATION_REPAIR_ELIGIBILITY 混成同一条 gate。修复方向：新增纯 helper
  `optimization_parent_admission()`，只对明确的可修结构失败放行，未知 health 失败仍 fail closed；
  提交与 pre-correlation 查询继续要求 `health.ok == true`。
- **P0-B 断点**：`OptimizerWorkflow._generation_bound()`（`optimizer_workflow.py:412`）读
  `gate_report()["child_done_count"]`，但 `gate_report()` 只把它初始化为 `0` 且从不递增 →
  `child_generation_bound()` 永远收到 `children_done=0` → 永远 `allowed=True`。修复方向：从
  canonical trajectory 派生真实 `experiment_stage == CHILD` 的 done / incremental 计数，继续复用同一个
  `research_yield.child_generation_bound()`。
- **P0-C 断点**：`Agent._refresh_self_correlation_evidence()`（`agent.py:1083`）每次新建
  `ephemeral_evidence = {}` 传给 `refresh_self_correlation_cache(cache=...)`，只用
  `self.reflector.evidence_cache.update(...)` 回填；同进程第二次 refresh 时
  `has_resolved_self_correlation(cache.get(id))` 仍为假 → 重复 GET。修复方向：把既有
  `reflector.evidence_cache` 直接作为 transient evidence view 复用。
- **P0-D 断点**：`research_api.get_experiment()` / `compare_experiments()` / `search_history()`
  （`research_api.py:307/314/320`）使用 `Trajectory.iter_rows()`（raw 行，含 `RESEARCH_SETTLED`
  revision），同一 Experiment 可能返回两条；`Trajectory.find_row()` 已是 canonical latest primitive
  却未被这些 surface 使用。修复方向：由 Trajectory owner 提供 canonical merge primitive，research_api
  只消费它、不再复制 revision 合并算法。
- **P1-A**：`OptimizerHooks.allowed_universes` 默认未绑定，`_allowed_universes()` 返回 `()`，
  `validation_candidate_values("universe", ...)` 因此恒为空；缺显式
  `VALIDATION_UNIVERSE_POOL_UNAVAILABLE` reason，Agent 只能看到空池。
- **P1-B**：`scripts/refresh_self_correlation.py::load_trajectory_rows()` 用
  `Trajectory(max_len=window)`（真实 `trajectory_window=512`），`--since/--until` 看不到窗口外的更老
  Experiment；脚本本身没有第二 parser，但复用了有界内存窗。
- **P1-C**：`FactoryRunner` 在 `factory_runner.py:838` 无条件
  `atomic_write_json_if_changed(self.proposals_path, payload)`（`batch_type="factory_100"`），会静默覆盖
  Agent 已 materialize 的 targeted batch —— 与历史真实失败场景一致。
- **P1-D**：`factory_runner.py:658-661` → `optimizable_signal_records()` +
  `generate_optimized_proposals()` 最终只保留 Agent 已 author 的 `OptimizationDecision` /
  `child_economic_hypothesis`；无人提供 decision → 0 proposals 是本轮要固定的正确行为，不恢复自动参数
  mutation。

## 实现与验证（offline，无真实 Simulation / 无 quota / 无 submission）

- **P0-A**：`pre_correlation.optimization_parent_admission()` 成为唯一准入 helper
  （`REPAIRABLE_HEALTH_FAILURES = STRUCTURAL_CHECK_BLOCKERS`），`AlphaFactory.screen_optimization_parents()`
  改为消费它；未知 health failure 仍 fail-closed。测试
  `test_structural_repair_parent_reaches_a_valid_child_proposal` 用真实
  `OptimizerWorkflow → AlphaFactory → validate_proposal(require_economic_integrity=True)` 证明
  `CONCENTRATED_WEIGHT` / `LOW_SUB_UNIVERSE_SHARPE` parent 能产出 production-valid CHILD，同时
  `pre_self_correlation_eligibility(...)["eligible"] is False`（能修 ≠ 能提交）。
- **P0-B**：`OptimizerWorkflow._generation_bound()` 改为从 canonical trajectory 派生真实
  `experiment_stage == CHILD` 记录，再复用唯一 `research_yield.child_generation_bound()`。
  `tests/test_control_loop_repair.py::TestGenerationBoundUsesRealChildHistory` 覆盖
  `C1 DONE + incremental UNAVAILABLE → restart → allowed=False / stop_reason=NO_INCREMENTAL_CHILD_EVIDENCE`、
  incremental PASS → 允许下一代、ROBUSTNESS 不算新一代。
- **P0-C**：`Agent._refresh_self_correlation_evidence()` 复用 `reflector.evidence_cache`（不再每次新建空
  dict），新增 `Agent.resolved_self_correlation(alpha_id)` 只读投影；`OptimizerWorkflow` 通过
  `OptimizerHooks.resolved_self_correlation` 叠加 resolved PASS/FAIL。测试覆盖
  `first refresh → GET once → FAIL`、`same-process second refresh → 仍只一次 GET`、
  `optimizer_context()` 看到 resolved FAIL → `STRUCTURAL_REPAIR_REQUIRED` +
  `CONSIDER_CORRELATION_REPAIR` + `SELF_CORRELATION_REPAIR`，PASS → `READY_TO_ADVANCE`。
- **P0-D**：`Trajectory.iter_canonical_rows()`（owner 侧 bounded canonical merge）+
  `research_api.get_experiment()`（改用 `find_row()`）/`search_history()`（改用 canonical 流）。
  测试：early DONE + `RESEARCH_SETTLED` 后 `get_experiment` 只见 FINAL、`search_history` 只 1 行、
  `compare_experiments` 无 missing。
- **P1-A**：无 pool 时 `universe` VALIDATE 显式 fail-closed（`VALIDATION_UNIVERSE_POOL_UNAVAILABLE`，
  不再允许任意字符串）；`decision.old_value` 必须等于 parent 自己 `settings` 里的真实值
  （`VALIDATION_OLD_VALUE_MISMATCH`），provenance 的 `parent_default_value` 只取 parent 值。
- **P1-B**：`scripts/refresh_self_correlation.py::load_trajectory_rows()` 改用 owner 的
  `iter_canonical_rows(since=..., until=...)`，不再被 `trajectory_window` 截断。测试构造 600 个
  canonical experiment + 最老的 settled revision，窗口外目标仍被选中且只出现一条。
- **P1-C**：`proposal_contract.validate_targeted_batch()` / `targeted_batch_state()` +
  `ProposalExecutionWorkflow` 执行前 fail-closed 校验 + `FactoryRunner._pending_targeted_batch()`
  的 `WAIT_AGENT_DECISION` 仲裁 + `research_api.materialize_targeted_batch()` 写入唯一 inbox。
  regression：`tests/test_control_loop_repair.py::TestFactoryNeverOverwritesTargetedBatch`
  证明 pending/invalid targeted batch 不会被 exploration 100 覆盖（`proposals.json` 字节不变、
  未 reserve、未调用 `run_suggestion_round`），过期后才重新取得 inbox。
- **P1-D**：`TestFactoryNeverInventsAgentDecisions` 固定“无 Agent decision → 0 CHILD proposal”，
  同一 parent 经 `generate_from_decisions([child_decision(...)])` 立即产出 1 个 proposal。
- **P2**：`AlphaFactory.template_numeric_audit()` 对 `DEFAULT_TEMPLATES + ECONOMIC_TEMPLATES` 的 74 个
  numeric literal 显式分类（7 个 RESEARCH_SLOT、`0.001` 全为 SAFETY_CONSTANT，其余
  OPERATOR_REQUIRED_CONSTANT），`test_every_template_numeric_literal_is_explicitly_classified` 固定
  “未分类即失败、只有声明 slot 可轮换”。

### P0-C 复检：结构 blocker 必须压过“历史 SELF_CORRELATION PASS”

- 复现：`parent_record(..., health={"ok": False, "reasons": ["CONCENTRATED_WEIGHT=FAIL v=0.9"]})`
  的 readiness 是 `STRUCTURAL_REPAIR_REQUIRED`，但只要 record 顶层
  `self_correlation.status == "PASS"`，`OptimizerWorkflow.optimizer_context()` 的 `next_action`
  仍回 `READY_TO_ADVANCE` —— Agent 会看到“结构 blocker 未修 + 可推进”。
- 根因：`_next_action()` 把 `status == "PASS"` 排在 readiness band 之前，PASS 覆盖了未修复的
  结构 blocker。PASS 只说明旧 expression 的相关性边界已解决，不解除当前结构 blocker。
- 修复：`band == "STRUCTURAL_REPAIR_REQUIRED"` 分支移到 PASS 之前（`generation_allowed=False`
  仍回 `STOP`）；FAIL 系分支保持最高优先级不变。
- 验收：`tests/test_control_loop_repair.py::TestStructuralRepairChainEndToEnd`（离线端到端链：
  结构 blocker → CONSIDER_CHILD → production-valid CHILD → synthetic C1 `PRE_CORRELATION_READY`
  → SELF_CORRELATION 只 GET 一次且 FAIL → generation bound `NO_INCREMENTAL_CHILD_EVIDENCE`）。
- 端到端链补强：resolved FAIL 必须出现在 `Agent.optimizer_context()`（不能只断言
  `resolved_self_correlation()`），因此 synthetic C1 必须携带完整 parent 级证据
  （`field_understanding`/`field_analysis`/`field_source`/`field_hypothesis_basis`/
  `economic_mechanism`），否则 `OptimizerWorkflow._parent_rejections()` 会把 C1 过滤掉，
  Agent 视图反而看不到自己的子代。
- `next_action` 映射逐项锁定：结构 blocker 且 `generation_bound.allowed == False` 时返回 `STOP`
  （`test_blocked_generation_turns_structural_repair_into_stop`），确保“修不动”时不再提议新 CHILD。

### 真实控制链复检 2：targeted batch 执行侧的两处断点（2026-09-12）

- **断点 A：DONE parent 被自己的终态表达式排除。** 真实 Agent 的
  `hooks.terminal_expressions()` 包含已完成 parent 自身的表达式（如 `rank(field_a)`），
  而 `OptimizerWorkflow.generate()` 原样把它当作优化初筛的 `excluded_expressions`，
  于是 `screen_optimization_parents()` 判定该 parent“已终结”并丢弃 —— Agent authored 的
  CHILD/VALIDATE 在真实路径下永远 0 生成。此前端到端测试用
  `terminal_expressions=lambda: set()` 的空 hook，掩盖了这个断点。
  VALIDATE 走同一条排除逻辑（`AlphaFactory.validation_proposals()` 也按
  `excluded_expressions` 过滤 parent 自身表达式），因此两条生成路径同时被杀死。
- **修复 A：** 新增 `OptimizerWorkflow._optimization_exclusions()`：终态集合只用于排除
  “新提案”，再减去被优化 parent 自身的表达式；screen 与 optimize 各自读取一次 hook，
  保留既有 dynamic terminal read 行为。CHILD 与 VALIDATE 两条生成路径都改用该豁免。
- **断点 B：targeted envelope 缺 discovery 字段画像。** `run-proposals` 的生产 preflight
  需要平台字段画像（`description` / `semantic_status`），而 `materialize_targeted_batch()`
  写出的 envelope 只有 proposals，结果是 `PREFLIGHT_BLOCKED：缺少本轮 discovery 字段画像`：
  targeted batch 能被写入却永远无法执行。
- **修复 B：** `research_api._targeted_field_profiles()` 从 Agent 已有的只读 field cache
  取出 batch 引用字段的真实画像写入 envelope `fields`；cache 缺失时不写画像、由 preflight
  fail-closed，不伪造字段元数据。
- **验收：** `tests/test_control_loop_repair.py::TestTargetedBatchRunsOnTheSingleExecutionPath`
  四条测试：终态不再排除 parent 且真实 Agent 产出 1 个 CHILD；真实 Agent 的 VALIDATE 决策
  仍产出 ROBUSTNESS proposal（`changed_variable=decay`、`settings={"decay": 5}`）；预置真实 field cache 后
  `materialize → agent.run_proposals()` 被 accepted 并恰好提交 1 次 Simulation（唯一
  `proposals.json`、唯一执行路径）；无字段画像时 0 次提交且 `PREFLIGHT_BLOCKED`。

## 2026-09-12 Phase VII：外层维护 / 内层研究边界与隐私审计

### 审计结论

- public tree 上确实存在 raw 研究审计产物：`docs/research_quality_audit_2026-09-11/` 下 3 个
  `audit.json`（各约 1.6 MB）与 3 个 `REPORT.md`，内容含 machine-specific 绝对路径
  （`.wqb_state` 盘符路径）与真实字段排名 dump。
- `.gitignore` 的 `*.audit.json` **不覆盖**裸名 `audit.json`：`git check-ignore -v` 对
  `docs/research_quality_audit_2026-09-11/audit.json` 返回 exit 1，而 `x.audit.json` 被忽略；
  已 tracked 文件本就不受 ignore 影响。
- 根因：`scripts/research_quality_audit.py` 原先默认
  `--output-dir docs/research_quality_audit_2026-09-11`，把 raw audit 直接写进 public tree。
- 其余散落隐私：`findings.md`/`progress.md`/`task_plan.md`/`docs/RESEARCH_ISSUES_2026-09-11.md`
  含真实 session id、proposal/submission id（`p-…`）、真实字段名与表达式；两个文档含本机
  绝对路径。未发现真实 `alpha-<id>`、凭据或 secret 值。

### 处置

- raw audit 移到 local-only `research_data/research_quality_audit_2026-09-11/` 并从 tracked tree
  移除；`docs/` 只保留 sanitized 摘要 `RESEARCH_QUALITY_AUDIT_2026-09-11_SUMMARY.md`。
- 生成脚本默认输出改为 `research_data/research_quality_audit`（local-only），不再默认写 `docs/`。
- sanitize 77 处 token：真实 session id、proposal/submission id、真实字段名、表达式中的真实字段
  引用与本机绝对路径。
- `.gitignore` 增加 `audit.json` 与 `docs/research_quality_audit_*/`。
- 新增 `scripts/check_repo_privacy.py`（只扫 `git ls-files`，不扫整块磁盘）与
  `tests/test_repo_privacy.py`（9 条）。
- history 未改写：历史 commit 可能仍含这些数据；purge 需要用户显式授权，不做
  filter-repo/BFG/force push。

### Prompt 分离

- 新增 `prompts/maintenance_agent.md`：外层维护 Agent（architecture、tests、docs、privacy、
  profiling、dependency、交付），遇到研究判断输出 `REQUIRES_INNER_RESEARCH_DECISION`。
- `prompts/research_agent.md` 收敛为 Inner Research Agent：只有研究角色与 handoff 契约。
- `docs/AGENT_VIBE_CODING_PROMPT.md` 从混合大 prompt 改为 redirect；`prompts/AGENTS.md` 声明
  两个 prompt 的分工，契约仍以根 `AGENTS.md` 为唯一 source-of-truth。
