# Suggestion Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract suggestion/discovery orchestration into an independent `SuggestionWorkflow` while preserving the existing bundle and safety contract.

**Architecture:** `Agent` constructs a workflow with explicit dependencies and narrow research-planning hooks. The workflow owns discovery fallback, bundle assembly, persistence and output; Agent retains state-aware hypothesis planning and optimizer coordination. The workflow has no transport, simulator, checkpoint or Agent import.

**Tech Stack:** Python, dataclasses/callables, `unittest`, existing atomic JSON artifact writer, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-09-suggestion-workflow-design.md`

## Global Constraints

- Suggestion must keep `Simulation POST count = 0`, checkpoint writes `= 0`, and owner lock acquisition `= 0`.
- `SUBMIT_UNKNOWN`, checkpoint exactly-once, proposal execution, factory dual-layer strategy and Alpha feed behavior are unchanged.
- No new state store, transport path, generic Agent escape hatch, or duplicated fallback-template definitions.
- Existing bundle keys, `None`/`[]`/`{}` semantics, fallback ordering and console output remain compatible.
- All code behavior changes follow RED → GREEN → REFACTOR with fresh verification.
- Commit/push uses Git email `2966684515@qq.com`; commit message is English prefix plus Chinese content.

### Task 1: Characterization and architecture tests

**Files:**
- Create: `tests/test_suggestion_workflow.py`
- Modify: `tests/test_agent_flow.py`
- Modify: `tests/test_architecture.py`

**Interfaces:**
- Tests describe the desired `SuggestionWorkflow` constructor and `run(round_no=None)` result before implementation.

- [ ] Add failing tests for direct workflow import/delegation, no simulation/checkpoint dependencies, fallback behavior, persistence and direct/facade equivalence.
- [ ] Run the focused test module and confirm failure is caused by the missing workflow/delegation, not a fixture typo.

### Task 2: Implement the isolated workflow

**Files:**
- Create: `wqb_agent/suggestion_workflow.py`

**Interfaces:**
- Produce `SuggestionHooks` with narrow operation-shaped callables.
- Produce `SuggestionWorkflow.run(round_no=None) -> dict`.
- Produce `SuggestionWorkflow.rotate_stalled_research_space(research_space, round_no, window=40, concentration=0.8) -> dict`.

- [ ] Implement explicit dependency storage and the existing rotation logic.
- [ ] Implement fallback discovery and exact field normalization/bundle construction.
- [ ] Persist with `atomic_write_json_if_changed` and preserve console output.
- [ ] Run the focused tests and the relevant existing agent/discovery tests.

### Task 3: Wire Agent as a thin facade

**Files:**
- Modify: `wqb_agent/agent.py`
- Modify: `tests/test_agent_flow.py`
- Modify: `tests/test_factory_boundaries.py`

**Interfaces:**
- Construct `self.suggestion_workflow` in `Agent.__init__` from existing components and hooks.
- Reduce `Agent.run_suggestion_round(round_no=None)` to delegation while retaining compatibility wrappers where existing tests call private helpers.

- [ ] Add the workflow construction without changing constructor/runtime component ownership.
- [ ] Replace the old bundle orchestration with the facade and delegate rotation compatibility.
- [ ] Verify optimizer and planning methods remain Agent-owned and no new dependency cycle appears.

### Task 4: Documentation and full regression

**Files:**
- Modify: `AGENTS.md`
- Modify: `wqb_agent/AGENTS.md`
- Modify: `docs/ARCHITECTURE_AGENT.md`
- Modify: `tests/test_architecture.py`

- [ ] Document workflow ownership and safety matrix.
- [ ] Run focused RED/GREEN regression, full unittest, compileall, Ruff, CLI/doctor/audit, and diff checks.
- [ ] Perform fresh review against the nine review questions in the task specification and fix any Important/Critical findings.
- [ ] Configure the required Git identity, commit with `refactor：抽离建议生成工作流`, push, fetch/re-read `origin/main`, and report both SHAs.
