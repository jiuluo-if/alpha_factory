# 颜色分组、Agent 自主优化与周模拟配额实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复颜色与 Agent 自主优化的触发可见性，并增加跨进程安全的 11200/周、1600/日工厂 Simulation 配额。

**Architecture:** 颜色仍是证据视图，settle 时更新当日内存缓存、收尾时重算；自主优化通过 gate report 和 Agent-authored child hypothesis 触发，不由 Python 臆造经济机制；配额作为 factory session 的计数控制面，按纽约本地日/周刷新，不保存结果证据。

**Tech Stack:** Python 标准库、`unittest`、现有 `Agent`/`AlphaFactory`/`AIFactoryRunner`、JSON session envelope。

**Spec:** `docs/superpowers/specs/2026-09-09-color-optimizer-weekly-quota-design.md`

## Global Constraints

- Simulation 只能沿 `Agent.run_proposals()`；不得创建第二条 POST 路径。
- `SUBMIT_UNKNOWN` 不重发，已知 progress URL 只读恢复，checkpoint 不手改。
- 颜色同步仍需显式命令，Alpha submission 仍由用户手工完成。
- 研究证据缺失保持 `UNKNOWN/UNAVAILABLE`，参数扫描不能伪装成新机制。
- 提交信息使用 `英文前缀：中文内容`，Git 邮箱为 `2966684515@qq.com`。

### Task 1: settle 后颜色视图与 optimizer gate report

**Files:**
- Modify: `wqb_agent/agent.py`
- Test: `tests/test_factory_boundaries.py`, `tests/test_alpha_colors.py`

- [x] **Step 1: Write failing tests**：验证 settle 回调立即更新颜色缓存；验证 gate report 能区分无 `DONE` parent、缺字段证据和缺子假设。
- [x] **Step 2: Run targeted tests**：已先得到接口缺失的预期 RED 结果。
- [x] **Step 3: Implement minimal behavior**：在 `_record_live_result()` 完成证据封装后更新当日颜色视图；增加只读 `optimizer_gate_report()`，并把最小 report/context 接入 suggestion bundle。
- [x] **Step 4: Run targeted tests**：目标测试已通过。
- [ ] **Step 5: Commit batch 1**：`git add wqb_agent/agent.py tests/test_factory_boundaries.py tests/test_alpha_colors.py`；提交 `feat：修复颜色与Agent优化触发边界`。

### Task 2: weekly quota primitive

**Files:**
- Create: `wqb_agent/weekly_quota.py`
- Test: `tests/test_factory_boundaries.py`

- [x] **Step 1: Write failing tests**：验证 11200 周上限、1600 日上限、纽约午夜刷新、周一刷新、无效状态 fail-closed 和只保存计数元数据。
- [x] **Step 2: Run targeted tests**：已先得到模块缺失的预期 RED 结果。
- [x] **Step 3: Implement minimal primitive**：使用注入 clock 和 `ZoneInfo("America/New_York")`，提供 `normalize_state()`、`remaining()`、`reserve()`、`release()`，不接受结果 payload。
- [x] **Step 4: Run targeted tests**：目标测试已通过。
- [ ] **Step 5: Commit batch 2**：提交 `feat：增加按日刷新的每周模拟配额`。

### Task 3: integrate quota into factory control plane

**Files:**
- Modify: `wqb_agent/factory_runner.py`, `main.py`, `config.example.json`, `wqb_agent/config.py`
- Test: `tests/test_factory_boundaries.py`, `tests/test_runtime_safety.py`

- [x] **Step 1: Write failing integration tests**：验证工厂提交前同时受日/周配额限制，跨 session 保留周计数，日期变化只刷新日计数。
- [x] **Step 2: Run targeted tests**：已先由未接入 quota 的预期失败锁定边界。
- [x] **Step 3: Implement integration**：新增配置默认值 `weekly_simulation_cap=11200`、`daily_simulation_cap=1600`；session 原子保存 quota 元数据；保留已有 checkpoint 恢复优先和 reservation/release 语义。
- [x] **Step 4: Run targeted tests**：工厂边界与配置测试已通过。
- [ ] **Step 5: Commit batch 3**：提交 `feat：接通工厂周配额控制面`。

### Task 4: documentation and verification

**Files:**
- Modify: `docs/RESEARCH_POLICY.md`, `docs/STATE_LAYOUT.md`, `README.md`, `findings.md`, `progress.md`
- Create: `docs/superpowers/specs/2026-09-09-color-optimizer-weekly-quota-design.md`
- Test: full repository checks

- [x] **Step 1: Document trigger causes, quota lifecycle, and no-result-persistence boundary.**
- [x] **Step 2: Run `python -m unittest discover -s tests`.**
- [x] **Step 3: Run `python -m compileall -q wqb_agent scripts tests`.**
- [x] **Step 4: Run `python -m ruff check .` and `git diff --check`.**
- [x] **Step 5: Run fresh code review over the final diff and resolve Critical/Suggestion findings.**
- [ ] **Step 6: Commit batch 4**：提交 `docs：补充颜色优化与配额边界`。

### Task 5: GitHub upload

- [ ] **Step 1: Verify exact staged file lists and no `.wqb_state` result files are staged.**
- [ ] **Step 2: Configure local Git email `2966684515@qq.com`.**
- [ ] **Step 3: Push the four commits to a `codex/` feature branch in order.**
- [ ] **Step 4: Report branch, commit SHAs, remote URL, and any files intentionally left uncommitted.**
