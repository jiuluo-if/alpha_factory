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

## Agent 接管与效率

接管已有 workspace 的第一步是 `python main.py --takeover-preflight --offline`。该命令只读汇总未完成 checkpoint、状态审计、proposal/cache 概况和 trajectory 计数；`BLOCKED` 时先恢复或对账，不直接启动新实验。自相关回填使用 `scripts/refresh_self_correlation.py` 的时间窗和数量上限，避免重复扫描全部历史。它只调用现有 evidence cache GET 路径，不创建第二套 Simulation 或 submission API。
