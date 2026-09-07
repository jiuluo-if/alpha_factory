# Phase 7 Incremental Alpha Value Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立时间一致的研究证据链，区分 standalone quality、robustness、statistical、incremental 和 yearly evidence，并保持生产搜索与人工提交边界不变。

**Architecture:** 以纯模块提供 retention、日期对齐相关性、可信 pool、cluster、分类和离线 reward_v2；Agent 只负责组装并追加 ledger 事件。现有 `ValidationReport`、`SearchPolicyReplay`、`TrialLedger` 和 `SubmissionPool` 保持 canonical 入口。

**Tech Stack:** Python 标准库、现有 unittest、JSON/JSONL append-only artifacts；禁止新数值/ML 依赖和第二 Simulation API。

**Spec:** `docs/superpowers/specs/2026-09-07-phase7-incremental-value-design.md`

## Global Constraints

- Production SearchPolicy 继续使用 `reward_v1`；`reward_v2` 只在 offline replay。
- ValidationPlan acceptance criteria 必须参与 canonical `plan_id`。
- Robustness、statistical、incremental、yearly 保持独立；不创建 master confidence score。
- Replay 不得使用 future candidate、future reward、future validation 或 future pool。
- SubmissionPool 永远 `MANUAL_REQUIRED`，不自动 POST。

### Task 1: 修复 Phase 6 replay 与 SearchOutcome 读取

**Files:**
- Modify: `wqb_agent/search_calibration.py`
- Modify: `wqb_agent/search_outcome.py`
- Modify: `wqb_agent/trial_ledger.py`
- Test: `tests/test_phase7_incremental_value.py`

- [ ] 写失败测试：round 1 不可选择 round 2 候选；settled_at 之前 reward 不进入 observed；nested statistical decision 使 reward_v1=1.0。
- [ ] 实现时间游标、可见候选集合、observed outcome 过滤和 `extract_statistical_decision()`。
- [ ] 增加 `research_outcome_settled` append-only 事件与按 proposal 替换 observation 的摘要读取。
- [ ] 运行 Phase 7 P0 测试和 Phase 6 测试。

### Task 2: Robustness retention 与预注册策略

**Files:**
- Create: `wqb_agent/robustness.py`
- Modify: `wqb_agent/validation_report.py`
- Modify: `config.example.json`
- Test: `tests/test_phase7_incremental_value.py`

- [ ] 写 retention、缺 parent、negative parent、checks 与 acceptance criteria 的失败测试。
- [ ] 实现纯 retention/criterion helper，并让 default plan 使用统一 config policy 参数。
- [ ] 让 validation report 只接受 `RobustnessEvidence.decision == PASS` 的 required dimension，输出 parent/child/criteria/reason。
- [ ] 验证 plan acceptance 改变会改变 `plan_id`。

### Task 3: Incremental value、可信 pool 和 cluster

**Files:**
- Create: `wqb_agent/incremental_value.py`
- Create: `wqb_agent/research_evidence.py`
- Modify: `wqb_agent/state.py`
- Test: `tests/test_phase7_incremental_value.py`

- [ ] 写日期 inner join、低 overlap、negative signed correlation、FAILED/future pool、deterministic union-find 测试。
- [ ] 实现可信 pool selector、pool snapshot 元数据、相关性证据、cluster 和三轴 incremental decision。
- [ ] 实现无 decision logic 的 `ResearchEvidenceBundle` 序列化对象。
- [ ] 将四维 evidence 字段持久化且兼容旧 state。

### Task 4: 分类、yearly、submission pool 与 calibration

**Files:**
- Modify: `wqb_agent/yearly.py`
- Modify: `wqb_agent/search_calibration.py`
- Modify: `wqb_agent/submission.py`
- Modify: `wqb_agent/agent.py`
- Test: `tests/test_phase7_incremental_value.py`

- [ ] 写四维分类、单年度 coverage、submission 不自动提交和校准指标测试。
- [ ] 增加 `year_count`/`coverage_status`，在 calibration 输出 stable/incremental/portfolio/cluster 指标。
- [ ] 接入研究分类与增量字段到人工 submission pool，并显式保留 UNKNOWN。
- [ ] 添加 offline reward_v2 和并列 replay 输出，确保 SearchPolicy 不读取 reward_v2。

### Task 5: 文档、全量验证与交付

**Files:**
- Create: `docs/PHASE7_INCREMENTAL_VALUE.md`
- Modify: `wqb_agent/__init__.py`
- Test: `tests/test_phase7_incremental_value.py`

- [ ] 补齐公共导出、文档、schema/version 说明和静态引用。
- [ ] 运行 `python -m unittest discover -s tests`、`python -m compileall -q wqb_agent scripts tests`、配置 JSON 解析和 `git diff --check`。
- [ ] 检查不触碰真实 `.wqb_state`、无 BRAIN 请求、无第二 Simulation API，并在用户授权范围内使用中文提交备注推送。
