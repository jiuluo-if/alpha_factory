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
