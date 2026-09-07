# Phase 7：增量 Alpha 价值与研究质量

本阶段把“独立质量”与“对已有研究池的新增价值”分开。文档和报告中的事实必须来自当前 trajectory、ledger、ValidationReport 或平台响应；缺失证据显示 UNKNOWN/UNAVAILABLE，不用结构新颖度替代行为新颖度。

## 证据维度

- `quality`：Simulation 完成后的基础指标和 checks，只回答 Alpha 自身是否有信号。
- `robustness`：根据预注册 ValidationPlan 的 `acceptance` 对 parent/child 计算 Sharpe/Fitness retention、换手和回撤倍数；每个 criterion 输出 PASS、FAIL 或 UNAVAILABLE。child DONE 且 checks PASS 不再自动代表稳健性通过。
- `statistical`：DSR/PSR/PBO 仍独立存在，SearchOutcome 从 `validation_report.statistical_evidence.statistical_decision` 读取。
- `incremental`：仅使用 `DONE + checks_passed + identity` 的可信 Alpha pool，按日期 inner join 计算行为相关性。低 overlap 是 UNAVAILABLE；高 `abs_corr` 是 FAIL；缺 PnL 不会被描述为低相关。
- `yearly`：报告 `year_count` 与 `coverage_status`。只有达到 `yearly_policy.min_years` 才能描述为跨年度覆盖。

`ResearchEvidenceBundle` 只用于序列化展示，不实现决策逻辑。研究分类是 `REJECTED`、`PROMISING`、`STABLE`、`PORTFOLIO_CANDIDATE`，最后一类也只进入人工审核池，仍保持 `MANUAL_REQUIRED`。

## 时间一致性

`SearchPolicyReplay` 按 `candidate_available_at`/`generated_at`/`sequence`/`round` 推进。未来候选不可见；某个 reward 只有 `outcome_observed_at` 或 `settled_at` 到达决策时点后才进入 observed history。传入 `decision_timestamp` 时，未来 evidence 会 fail closed。可选的 pool 快照同样按 `pool_entered_at <= decision_time` 生成。

Simulation DONE 的结果先是 `provisional_outcome`。ValidationReport 聚合完成后追加 `research_outcome_settled` ledger 事件，并以 final reward 替换 allocator 中同一 proposal 的 observation，不增加 reward count。旧事件不改写，重启时以最新 settlement 覆盖 provisional 值。

## 离线校准

Production SearchPolicy 只使用 `reward_v1`。`reward_v2` 只作为离线 replay 的阶段性比较：在已有 reward 上对 incremental PASS 做有限提升，仍保持 `[0, 1]`；incremental FAIL 不把 standalone quality 改写成零。只有未来独立证据证明 reward_v2 在多个历史 checkpoint 持续更优，才可以另行评审切换。

## 配置与审计

统一策略位于 `config.example.json`：

```json
"robustness_policy": {
  "min_sharpe_retention": 0.7,
  "min_fitness_retention": 0.6,
  "max_turnover_multiple": 1.5,
  "max_drawdown_multiple": 1.5,
  "require_checks_passed": true
},
"incremental_value": {
  "max_abs_correlation": 0.7,
  "min_overlap": 60,
  "mode": "required_when_available"
}
```

Acceptance criteria 会写进 ValidationPlan 的 canonical hash；计划注册后不得用结果反向改门槛。结构 cluster 只作为近似 trial proxy，必须标记 `quality=APPROXIMATE`，不能未经验证替换 DSR 的 `n_trials`。
