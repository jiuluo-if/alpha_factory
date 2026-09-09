# Proposal Execution Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract proposal execution and checkpoint recovery orchestration from `Agent` into `ProposalExecutionWorkflow` while preserving every existing execution and safety contract.

**Architecture:** Introduce a narrow dependency context and a workflow that owns proposal-file execution, execution preflight, checkpoint resume, dispatch coordination, and settlement orchestration. `Agent.run_proposals()` becomes a compatibility facade that delegates to the workflow; `Simulator`, checkpoint persistence owners, trajectory, trial ledger, and domain-policy modules retain their existing ownership.

**Tech Stack:** Python 3, `unittest`, dataclasses, existing `Simulator`/checkpoint/state services, Ruff, compileall.

**Spec:** `docs/superpowers/specs/2026-09-09-proposal-execution-workflow-design.md`

## Global Constraints

- Preserve inputs, checkpoint JSON, Simulation POST count, order, status transitions, output, return values, and failure semantics.
- Never resend `SUBMIT_UNKNOWN`; block same-checkpoint no-URL pending work and only poll known `progress_url` work.
- Do not create a second Simulation POST path, state store, trajectory, ledger, or state machine.
- `proposal_execution.py` must not import `Agent`, `main`, `cli`, or `factory_runner`.
- Do not change SuggestionWorkflow, optimizer, Client, CLI, config compatibility, state schema, Simulation settings, quota, or research policy.
- Every production change follows a failing characterization/regression test first; run the focused tests after each migration batch.

### Task 1: Inventory and characterization boundary

**Files:**
- Modify: `task_plan.md`, `findings.md`, `progress.md`
- Test: `tests/test_agent_flow.py`, `tests/test_recovery.py`, `tests/test_factory_boundaries.py`, `tests/test_runtime_safety.py`, `tests/test_architecture.py`, `tests/test_agent_evaluation.py`

**Interfaces:**
- Consumes: current `Agent.run_proposals()` and checkpoint behavior.
- Produces: explicit call graph, baseline counts, and failing tests for the new workflow boundary.

- [ ] **Step 1: Read the required source and tests completely and record direct callers/helpers.**
- [ ] **Step 2: Add tests for missing proposals, malformed JSON, invalid round values, foreign unfinished checkpoint, complete checkpoint, and exactly-once recovery.**
- [ ] **Step 3: Add a facade-delegation test and reverse-dependency architecture test.**
- [ ] **Step 4: Run only the new tests and confirm the failure is caused by the missing workflow boundary, not a fixture or syntax error.**

### Task 2: Introduce the narrow workflow boundary

**Files:**
- Create: `wqb_agent/proposal_execution.py`
- Modify: `wqb_agent/agent.py`
- Test: focused workflow and architecture tests

**Interfaces:**
- `ProposalExecutionContext` contains only existing runtime collaborators needed by execution.
- `ProposalExecutionWorkflow.run(path=None, allow_unresolved_checkpoint=False)` preserves the current public result contract.
- `Agent.run_proposals()` delegates through `self.proposal_execution`.

- [ ] **Step 1: Define the context/result types and workflow shell from the failing tests.**
- [ ] **Step 2: Move only entry preflight, proposal loading, round resolution, and checkpoint detection.**
- [ ] **Step 3: Run focused proposal/recovery tests and inspect POST counts and checkpoint JSON.**
- [ ] **Step 4: Keep compatibility wrappers for existing private Agent callers while marking them transitional.**

### Task 3: Move checkpoint resume and exactly-once orchestration

**Files:**
- Modify: `wqb_agent/proposal_execution.py`, `wqb_agent/agent.py`
- Test: `tests/test_agent_flow.py`, `tests/test_recovery.py`, `tests/test_runtime_safety.py`

**Interfaces:**
- Workflow owns one implementation of checkpoint path/load/write/resume orchestration.
- `Agent` wrappers, if retained, forward to that implementation and do not duplicate logic.

- [ ] **Step 1: Move checkpoint helpers and resume path without changing status filters or output strings.**
- [ ] **Step 2: Run recovery tests and assert `SUBMIT_UNKNOWN` same-checkpoint new POST count remains zero.**
- [ ] **Step 3: Run known-URL polling tests and assert polling remains allowed.**
- [ ] **Step 4: Run complete-checkpoint tests and assert no dispatch occurs.**

### Task 4: Move execution orchestration and project the result

**Files:**
- Modify: `wqb_agent/proposal_execution.py`, `wqb_agent/agent.py`
- Test: `tests/test_agent_flow.py`, `tests/test_factory_boundaries.py`, `tests/test_agent_evaluation.py`

**Interfaces:**
- `ProposalExecutionResult` preserves accepted/rejected/skipped/status values used by `last_run_stats`.
- Workflow calls `Simulator.run`/existing callbacks and never `client.submit_simulation`.

- [ ] **Step 1: Move validation, dedupe, field/profile gates, dispatch, settlement, and evidence callbacks in small batches.**
- [ ] **Step 2: After each batch run recovery, runtime safety, agent flow, and factory boundary tests.**
- [ ] **Step 3: Add direct-workflow versus Agent-facade equivalence assertions for a checkpoint fixture.**
- [ ] **Step 4: Assert `last_run_stats` keys and values remain compatible.**

### Task 5: Documentation, review, and full verification

**Files:**
- Modify: `AGENTS.md`, `wqb_agent/AGENTS.md`, `README.md`, `docs/STATE_LAYOUT.md`, `docs/reference/OPERATORS_CHEATSHEET.md`, `task_plan.md`, `findings.md`, `progress.md`
- Test: `tests/test_architecture.py` and all existing tests

- [ ] **Step 1: Document the new owner boundary and explicitly preserve Simulator/Client/CheckpointStore responsibilities.**
- [ ] **Step 2: Run fresh architecture/code review against the complete diff and fix Critical/Important findings.**
- [ ] **Step 3: Run `python -m unittest discover -s tests`, `python -m compileall -q wqb_agent scripts tests`, `python -m ruff check .`, doctor/audit, and `git diff --check`.**
- [ ] **Step 4: Verify no forbidden imports, direct client POST, duplicate state store, or uncommitted research-state changes.**
- [ ] **Step 5: Commit with `refactor：抽离提案执行与恢复工作流`, push `origin/main`, and verify the remote SHA.**
