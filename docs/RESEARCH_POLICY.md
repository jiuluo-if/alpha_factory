# Alpha Research Policy

## 事实与实验边界

1. BRAIN 当前响应是字段、Simulation、Alpha 指标、checks、aggregates 和 correlation 的最高事实源。
2. `trajectory.jsonl` 是已确认实验的 append-only 证据；checkpoint 是 exactly-once 恢复边界；两者不能手工改写。
3. 唯一 Simulation POST 路径是 `Agent.run_proposals()`。任何 timeout、网络中断、5xx 或写入结果不明都不能自动重 POST。
4. 429 必须遵守 Retry-After gate；`SUBMIT_UNKNOWN` 必须先只读对账；人工最终 Alpha 提交始终由用户完成。
5. capability 只有在对应证据等级成立时才能被消费。社区观察 endpoint 不得被当作官方可用接口。

## TrialLedger

`TrialLedger` 是 append-only 审计侧车，不替代 trajectory、checkpoint 或 proposals。每个 trial 可以产生四类事件：

```json
{
  "trial_id": "local-experiment-id",
  "phase": "generated|preflight|submitted|completed",
  "status": "PENDING|RUNNING|DONE|FAILED|SUBMIT_UNKNOWN",
  "template_family": "economic-family",
  "lineage_id": "hypothesis-or-lineage",
  "template_id": "template-name",
  "fields": ["verified_field"],
  "expression_fingerprint": "sha256"
}
```

`TrialLedger.summarize()` 流式统计 phase/status，以及 family、lineage、template、field 的 trial count；缺少 ledger 文件不影响旧状态恢复。

## 年度稳定性 evidence

DONE Alpha 会通过已知 Alpha id 请求 `/alphas/{id}/aggregates`。成功后只保存紧凑的年度 evidence，不复制原始 payload：

```json
{
  "status": "VERIFIED",
  "year_count": 2,
  "passing_years": 2,
  "stable": true,
  "summary": {"min_sharpe": 1.1, "min_fitness": 0.7, "max_turnover": 0.3},
  "years": [
    {"year": 2022, "sharpe": 1.1, "fitness": 0.7, "returns": 0.12,
     "turnover": 0.2, "drawdown": 0.08, "margin": 0.04},
    {"year": 2023, "sharpe": 1.3, "fitness": 0.8, "returns": 0.15,
     "turnover": 0.3, "drawdown": 0.07, "margin": 0.05}
  ]
}
```

aggregates endpoint 缺失、超时或返回畸形数据时，evidence 为 `UNKNOWN`，但不会把已经完成的 Simulation 改成失败，也不会触发重复 POST。未知年度证据不能被解释为稳定通过。

## Canonical STABLE 与 ValidationReport

`SUCCESS` 是单次 headline 结果，`ROBUSTNESS` 是单个预注册变量的结果，二者都
不能直接写成 `STABLE`。只有 parent 的 `ValidationPlan` 已在 robustness 运行前
注册，并且所有 required dimensions 聚合为 `ValidationReport.status=PASS`，parent
才可以获得 `validation_status=STABLE`。

本地 robustness 是局部敏感性与机制反驳证据，不称为 hidden OOS，也不替代真正的
时间外样本验证。

ValidationPlan 至少覆盖：window locality、semantic field swap、universe robustness、
decay/truncation 单变量变化和 yearly aggregates；每项必须记录变量、理由、预算、
falsification 和 stopping rule。

统计证据不压缩成 magic 综合分数：

- PSR 需要足够的有限 return series，并显式使用偏度和非 excess kurtosis；
- DSR 使用 TrialLedger 的 generated trial count，以及已记录 trial Sharpe 的均值/波动
  调高 selection threshold；搜索越多或搜索空间波动更大，raw max Sharpe 的可信度不会
  自动上升。缺少完整 trial Sharpe 分布时才使用明确标注的零均值、单位波动保守 fallback；
- PBO/CSCV 只有在至少两个长度相同、时间对齐的 return series 存在时才可用，否则为
  `UNAVAILABLE`；
- PnL 只有 capability `LIVE_VERIFIED` 时才可进入 rolling stability、correlation 和
  bootstrap diagnostics。社区观察或缺失 PnL 不能伪造 DSR/PBO。

PSR/DSR 的公式依据 Bailey 与 López de Prado 的原论文《The Deflated Sharpe Ratio:
Correcting for Selection Bias, Backtest Overfitting and Non-Normality》：
[论文 PDF](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)。实现采用论文中
基于偏度、kurtosis、样本长度，以及 trial Sharpe 分布和独立 trial 数估计 expected
maximum Sharpe 的定义；当这些输入不足时返回 `UNAVAILABLE` 或明确的保守 fallback。
