# 探索路线图

本文件定义可长期复用的研究空间与选择纪律，不记录实时轮次、指标、Alpha 数量或“当前最佳”。这些事实只读取 `.wqb_state/` 和 BRAIN API。

## 每轮选择规则

1. 先读 `context.md`、`experience.json`、未完成 checkpoint 与 `trajectory.jsonl`，排除已关闭或已模拟的表达式。
2. 选择与 ACTIVE/待提交 Alpha 低重合的研究空间和数据集。
3. 使用本地完整字段目录；只有目录缺失、不完整或缺目标字段时才允许只读刷新。
4. 字段描述、类型、coverage、frequency 与 alphaCount 必须保持平台原值；缺失则记录缺失，不补全。
5. 只为能改变下一步决策的问题写 proposal；没有问题则停止，不填满预算。

## 优先研究空间

| 研究空间 | 最小问题 | 主要风险 |
|---|---|---|
| 价格结构与协动 | 日内位置、范围、相关性或跳空是否提供与现有池低重合的信息？ | 高换手、与价格反转族重合 |
| 基本面慢变量 | 盈利质量、资本结构或现金流变化能否在长窗口中形成稳定横截面信息？ | 缓慢更新、sub-universe 弱、字段拥挤 |
| 信息与情绪 | 新闻、社媒或分析师信息的变化是否在字段语义支持的 horizon 内定价不足？ | VECTOR 类型、低覆盖、事件噪声 |
| 成交量与流动性 | 成交量、流动性和价格的结构关系是否提供独立信息？ | 极端换手、同族重复 |
| 已见信号的单变量验证 | 有信号但未达提交门槛的 parent 是窗口、字段、算子、平滑还是设置问题？ | 参数搜索、相关性升高 |

## 构造纪律

- `BASELINE` 只检验一个最小机制；`CHILD`/`ROBUSTNESS` 只允许一个 `change_type`。
- 多字段只能是语义互证、比率、差分或状态—信号配对；禁止无机制加权堆叠。
- `vec_avg`/`vec_sum` 只能接收已验证的 VECTOR；转换路径和后续类型必须记录。
- 优先低相关新机制。精确表达式、等价表达式、无新证据的同族变体不得复跑。
- `expected_quality × information_gain × novelty ÷ simulation_cost` 只用于预算排序，不是调参目标。

## 结果后的决策

- `PROMOTE`：六指标、checks、健康、稳定性与平台 SELF_CORRELATION 全部通过；只写入人工审核池。
- `CONTINUE`：结果提供可归因的信息，下一步只改变一个变量。
- `STOP` / `KILL`：仅按已达可提交候选的防过拟合纪律或明确机制证伪执行。
- `RECONCILE`：UNKNOWN、TIMEOUT、RATE_LIMIT、AUTH、INFRA 或缺少必须证据；不写入 avoid 或长期 lesson。

公开研究政策与安全门控以 [RESEARCH_POLICY.md](RESEARCH_POLICY.md) 为准；本地执行约束不作为公开 API 契约。
