# Architecture Authenticity and Read-Path Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 验证上一轮 Agent 架构重构真实落地，并以最小 coherent diff 消除重复默认值、重复 state IO、重复状态/表达式解释和残余职责漂移。

**Architecture:** 先沿 `main.py → preflight/doctor/audit/state → Agent/runtime_components` 追踪真实调用链。共享事实只通过轻量只读 `WorkspaceSnapshot` 或既有 streaming primitive 读取；诊断模块仍各自解释规则，不新增 manager/container/state truth。配置默认值在 `parse_config()` 解析、转换、校验，`runtime_components` 只组装已解析对象。

**Tech Stack:** Python 标准库、`unittest`、现有 `CheckpointStore`/`Trajectory`、Ruff、coverage。

**Spec:** `<codex-attachments>/goal-objective.md`

## Global Constraints

- BRAIN live response 是最高事实源；本轮不启动真实 Simulation、不调用 Alpha submit、不修改真实研究状态。
- `SUBMIT_UNKNOWN` 不自动重 POST；known progress URL 仅只读 reconciliation；checkpoint exactly-once；trajectory append-only。
- malformed/unknown state fail-closed；UNKNOWN/UNAVAILABLE 不升级 PASS；Alpha submission 只能人工完成。
- 不创建第二套 state、proposal、checkpoint、evaluation、execution、facade、orchestrator 或持久索引。
- 每个行为改动先写失败回归测试并确认 RED，再写最小实现并确认 GREEN。

---

### Task 1: Verify previous changes and map duplicate read paths

**Files:**
- Read: `wqb_agent/config.py`, `wqb_agent/runtime_components.py`, `wqb_agent/agent.py`, `wqb_agent/checkpoints.py`, `wqb_agent/state.py`, `wqb_agent/preflight.py`, `wqb_agent/doctor.py`, `wqb_agent/audit.py`, `wqb_agent/research_api.py`, `tests/test_runtime_safety.py`, `tests/test_checkpoint_store.py`, `tests/test_agent_context.py`, `tests/test_architecture.py`
- Update: `.planning/agent-mental-model/findings.md`, `.planning/agent-mental-model/progress.md`, `.planning/agent-mental-model/task_plan.md`

**Interfaces:**
- Produces a verified table of config entry points, state readers, status sets, expression parsers, and runtime component owners.
- No production behavior changes and no writes below `.wqb_state/`.

- [ ] **Step 1: Trace the key call chains and search for duplicate literals/readers.**

Run:

```powershell
rg -n "normalize_config|parse_config|\.get\([^\n]*default|CheckpointStore|trajectory\.jsonl|proposals\.json|experience\.json|evidence_cache\.json|SUBMIT_UNKNOWN|ACTIVE_EXECUTION_STATUSES|UNRESOLVED_STATUSES|TERMINAL_STATUSES|analyze_expression|simulation_config|RuntimeComponents|object" wqb_agent main.py tests -g '*.py'
```

Read the complete bodies of the hit functions and record only confirmed duplication or drift in `findings.md`.

- [ ] **Step 2: Run the existing read-only baseline.**

```powershell
python -m unittest discover -s tests
python -m compileall -q wqb_agent scripts tests
python -m ruff check .
python main.py --doctor --offline --state-dir tests/fixtures
python main.py --audit-state --offline --state-dir tests/fixtures
python main.py --agent-context --compact --offline --state-dir tests/fixtures
```

Record exit codes and the fact that the fixture commands do not write state.

### Task 2: Normalize only confirmed runtime defaults and owners

**Files:**
- Test: `tests/test_runtime_safety.py` or the smallest existing config/runtime test file
- Modify: `wqb_agent/config.py`, `wqb_agent/runtime_components.py`, and only the direct consumer requiring the owner correction

**Interfaces:**
- `parse_config(raw)` returns validated typed values for every default moved out of runtime composition.
- `build_runtime_components(...)` consumes resolved config and instantiates existing components without re-parsing formal config semantics.

- [ ] **Step 1: Add one failing test per confirmed default/owner regression.**

Each test must assert observable resolved configuration or component construction, not implementation details. Do not add a test for a default that the audit proves is compatibility-only or intentionally local.

- [ ] **Step 2: Run the focused tests and confirm expected RED.**

```powershell
python -m unittest tests.test_runtime_safety -v
```

- [ ] **Step 3: Move the smallest confirmed default/type conversion/validation into `parse_config()` and replace the runtime fallback with direct resolved access.**

Keep untyped dict sections unmodified unless the audit proves a stable formal default. Replace `RuntimeComponents` `object` annotations only when the concrete existing type is stable and import-safe; remove duplicate fields only when a single owner is demonstrated.

- [ ] **Step 4: Run focused tests and the relevant Agent/runtime tests.**

```powershell
python -m unittest tests.test_runtime_safety tests.test_agent_flow tests.test_checkpoint_store -v
```

### Task 3: Converge one command-scoped read snapshot and trajectory primitive

**Files:**
- Test: `tests/test_agent_context.py`, `tests/test_architecture.py`, and the smallest relevant state/diagnostic test
- Modify: `wqb_agent/preflight.py`, `wqb_agent/doctor.py`, `wqb_agent/audit.py`, `wqb_agent/state.py` or `wqb_agent/artifacts.py`, `main.py` only if dependency threading requires it

**Interfaces:**
- `read_workspace_snapshot(state_dir)` is read-only, command-scoped, non-persistent, preserves malformed information, and contains summaries rather than authoritative state.
- Existing diagnostic functions retain their own rule interpretation and accept/use the shared facts without calling `CheckpointStore.scan()` or re-streaming the same trajectory within one command.

- [ ] **Step 1: Add failing call-count/behavior tests for the confirmed duplicate scan path.**

Use temporary fixture state and spies around existing read primitives. Assert one snapshot read per command and unchanged BLOCKED/UNKNOWN semantics; do not assert a new class hierarchy.

- [ ] **Step 2: Run the focused tests and confirm RED.**

```powershell
python -m unittest tests.test_agent_context tests.test_architecture -v
```

- [ ] **Step 3: Implement the smallest immutable-in-memory snapshot or single-pass summary helper.**

Reuse `CheckpointStore` and `Trajectory` streaming boundaries. Do not materialize trajectory, persist an index, infer BRAIN truth, or combine diagnostic decisions.

- [ ] **Step 4: Run focused state/recovery/context tests and confirm GREEN.**

```powershell
python -m unittest tests.test_state tests.test_recovery tests.test_agent_context tests.test_architecture -v
```

### Task 4: Add architecture regression tests and complete review

**Files:**
- Test: `tests/test_architecture.py` and the smallest affected existing tests
- Documentation: only the relevant architecture/operation document if an interface or boundary changed

**Interfaces:**
- Tests prevent raw config bypass, direct checkpoint parsing, duplicate expression facts, runtime submit/write calls, Agent default redefinition, takeover network writes, and duplicate production Simulation POST paths.

- [ ] **Step 1: Add only architecture tests backed by confirmed current contracts.**

Tests must inspect real imports/call paths or execute read-only behavior; avoid brittle line-count or filename-only assertions.

- [ ] **Step 2: Run the full verification suite.**

```powershell
python -m unittest discover -s tests
python -m compileall -q wqb_agent scripts tests
python -m ruff check .
coverage run -m unittest discover -s tests
coverage report
python main.py --doctor --offline --state-dir tests/fixtures
python main.py --audit-state --offline --state-dir tests/fixtures
python main.py --agent-context --compact --offline --state-dir tests/fixtures
git diff --check
```

- [ ] **Step 3: Perform the code review against the diff and trace one critical path end-to-end.**

Report only actionable findings with contract/runtime/correction proofs. State any unverified area explicitly.

- [ ] **Step 4: Update the planning files with changed files, evidence, errors, and remaining risks.**

Do not commit or push unless the user separately authorizes it.
