# Phase 7：增量 Alpha 价值与研究质量设计

## 目标

在不改变生产 Simulation 入口、不自动提交 Alpha 的前提下，把“独立质量、稳健性、统计证据、行为增量价值和跨年度证据”分成可审计的证据维度，并让历史 replay 严格按候选可用、结果结算和可信 Alpha pool 的时间推进。

## 约束

- Production SearchPolicy 继续只使用 `reward_v1`；`reward_v2` 只用于离线 replay。
- 所有新模块保持纯函数；不引入 numpy/pandas/scipy、ML、数据库或第二 Simulation API。
- ValidationPlan 的 acceptance criteria 在预注册时进入 `plan_id`，结果阶段不得改门槛。
- Robustness、statistical、incremental、yearly 是独立证据，不能合成为 master score。
- SubmissionPool 继续 `MANUAL_REQUIRED`，`PORTFOLIO_CANDIDATE` 不代表自动提交。

## 设计

### 时间一致 replay

`SearchPolicyReplay` 为每个候选解析 `candidate_available_at`（优先 `generated_at`，其次 `sequence`/`round`），为每个 outcome 解析 `outcome_observed_at`/`settled_at`。每一步只把已到达决策时刻的候选放入可选集合，并只把已结算结果放入 observed history；缺少时间的旧记录按输入顺序作为保守兼容顺序，绝不读取未来行的 reward 或 pool。

### 证据模块

`robustness.py` 计算 parent/child 的方向性 retention 和每项 criterion 的 PASS/FAIL/UNAVAILABLE；`incremental_value.py` 只对可信、日期对齐、达到最小 overlap 的 pool 做 correlation，使用可解释 union-find cluster；`research_evidence.py` 只序列化四维状态和薄 bundle，不包含新的决策算法。

### 结算

Simulation DONE 产生 provisional outcome；在 platform/yearly/robustness/statistical/incremental 证据齐备后追加 `research_outcome_settled` 事件。按 proposal 最新结算值替换 allocator observation，不重复累计 provisional reward。统计决定统一从 `validation_report.statistical_evidence.statistical_decision` 读取。

### 研究分类与展示

`REJECTED`、`PROMISING`、`STABLE`、`PORTFOLIO_CANDIDATE` 由独立维度组成；只有质量、稳健性、平台证据通过且 incremental 在可用时通过，才可标为最后一类。缺少行为数据明确显示 `INCREMENTAL UNKNOWN`。yearly evidence 增加 `year_count` 与 `coverage_status`，单年度不描述为跨年度验证。

## 验证

新增 Phase 7 回归覆盖目标文件列出的 23 个行为，并运行全部 Phase 1–6 测试、compileall、配置解析和生产入口静态检查。测试不连接 BRAIN、不修改真实 `.wqb_state`。
