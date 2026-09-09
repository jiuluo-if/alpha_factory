# AppConfig Raw Compatibility Mapping Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove internal raw `AppConfig.agent` and `AppConfig.simulation` fields while keeping the external `config.json` schema and runtime behavior compatible.

**Architecture:** Keep raw `agent`/`simulation` interpretation inside `parse_config()` only. Return an `AppConfig` made exclusively of existing typed sections, adding only the typed `runtime.smoke_dataset` value needed to preserve the current read-only smoke behavior. Runtime modules and tests consume the typed boundary.

**Tech Stack:** Python 3.11+, dataclasses, unittest, AST/static source guards, Ruff, existing CLI and runtime composition.

**Spec:** `docs/superpowers/specs/2026-09-09-appconfig-raw-compatibility-mappings-design.md`

## Global Constraints

- External `config.json` keys `agent` and `simulation` remain unchanged.
- Raw JSON/dict may be read only before `normalize_config()`; production typed consumers must not read `AppConfig.agent` or `AppConfig.simulation`.
- Preserve defaults, error paths, CLI compatibility, budget hierarchy, simulation settings, and raw-input copy isolation.
- Do not modify Alpha color workflows, Simulation behavior, state/checkpoint schema, quota, research policy, broad policy typing, credential discovery, mypy, coverage, or CLI design.
- Do not commit or push until verification is complete; if delivery is authorized, use Git email `2966684515@qq.com` and an English-prefix-plus-Chinese commit message per repository rules.

---

### Task 1: Lock the typed-only contract with failing tests

**Files:**
- Modify: `tests/test_architecture.py`
- Modify: `tests/test_runtime_safety.py`
- Modify: `tests/test_smoke.py`

**Interfaces:**
- Consumes: current `AppConfig`, `normalize_config`, `apply_cli_overrides`, and the external raw fixture shape.
- Produces: regression tests that fail because raw AppConfig fields and the raw smoke consumer still exist.

- [ ] **Step 1: Add the AppConfig field guard.**

  In `tests/test_architecture.py`, import `dataclasses` and add a test that computes `{field.name for field in dataclasses.fields(AppConfig)}` and asserts that `agent` and `simulation` are absent. Also scan every production `wqb_agent/*.py` except `config.py` and assert that raw access patterns `config.agent`, `config.simulation`, `hasattr(config, "agent")`, and `hasattr(config, "simulation")` are absent.

- [ ] **Step 2: Add typed normalization and copy-isolation assertions.**

  In `tests/test_runtime_safety.py`, normalize a raw mapping containing `simulation.neutralization`, `agent.smoke_dataset`, and a nested quality value. Assert both removed attributes are absent, the typed values are present, `normalize_config(typed) is typed`, and mutations to the original raw nested dictionaries do not alter `typed.runtime.quality` or `typed.simulation_config.settings`.

- [ ] **Step 3: Change the smoke characterization to cross the real boundary.**

  In `tests/test_smoke.py`, pass `normalize_config({"simulation": {}, "agent": {"smoke_dataset": "pv1"}})` to `run_readonly_smoke`. Keep the read-only client call assertions, and add a test that a non-`AppConfig` config is rejected so the helper cannot silently become another raw config entry point.

- [ ] **Step 4: Run only the new/affected tests and confirm the red failure.**

  Run:

  ```powershell
  python -m unittest tests.test_architecture tests.test_runtime_safety tests.test_smoke
  ```

  Expected: failure from the new absence/production-consumer assertions, specifically the existing `AppConfig` fields and `wqb_agent/smoke.py` raw access. If the tests error for a test defect rather than the expected contract violation, correct only the tests and rerun.

### Task 2: Remove raw fields and migrate smoke to typed runtime

**Files:**
- Modify: `wqb_agent/config.py`
- Modify: `wqb_agent/smoke.py`
- Modify: `main.py`

**Interfaces:**
- Consumes: raw external mapping through `parse_config(raw)`.
- Produces: `AppConfig` without raw fields; `AgentRuntimeConfig.smoke_dataset`; `run_readonly_smoke(client, config: AppConfig)`.

- [ ] **Step 1: Add the minimal typed smoke value.**

  Add `smoke_dataset: str | None = None` to `AgentRuntimeConfig`. In `parse_config()`, set it from the existing external `agent.get("smoke_dataset")` value while retaining all current `config.agent...` parser error paths and deep-copy behavior.

- [ ] **Step 2: Remove raw AppConfig fields.**

  Delete only the `simulation` and `agent` dataclass fields from `AppConfig`. Keep every typed field and default unchanged. Change the `return AppConfig(...)` call to omit the two removed keyword arguments while retaining the existing `simulation_config` and `runtime` construction.

- [ ] **Step 3: Make smoke typed-only.**

  Import `AppConfig` in `wqb_agent/smoke.py`, reject non-`AppConfig` input with the existing project style of `TypeError`, and read `config.runtime.smoke_dataset`. Preserve the client read methods, result statuses, fallback to the first dataset, and no-write contract.

- [ ] **Step 4: Correct the stale main boundary comment.**

  Update only the comment in `main.py` that says the legacy mapping is retained so it states that raw JSON is normalized once and subsequent operations use typed configuration. Do not alter dispatch or client/lock behavior.

- [ ] **Step 5: Run focused tests to verify green.**

  Run:

  ```powershell
  python -m unittest tests.test_architecture tests.test_runtime_safety tests.test_smoke tests.test_runtime_composition
  ```

  Expected: all affected tests pass, including the new absence and typed smoke assertions.

### Task 3: Document the boundary and verify compatibility regressions

**Files:**
- Modify: `AGENTS.md`
- Create or modify: `wqb_agent/AGENTS.md`
- Modify: `docs/ARCHITECTURE_AGENT.md`
- Modify: `.planning/2026-09-09-remove-appconfig-raw-compatibility-mappings/findings.md`
- Modify: `.planning/2026-09-09-remove-appconfig-raw-compatibility-mappings/progress.md`
- Modify: `.planning/2026-09-09-remove-appconfig-raw-compatibility-mappings/task_plan.md`

**Interfaces:**
- Consumes: the implementation from Task 2 and the external config example.
- Produces: explicit documentation and recorded evidence for the raw-to-typed boundary.

- [ ] **Step 1: Update architecture guidance without changing unrelated policy.**

  State that external `simulation`/`agent` keys are parser input only; normalized `AppConfig` contains typed sections only; runtime projections and workflows must consume typed values. Keep all existing safety and research-state rules intact.

- [ ] **Step 2: Record the package-local rule.**

  Create `wqb_agent/AGENTS.md` only if it does not exist, with the nearest-scope rule that `config.py` may parse external raw keys but all other package modules must consume typed `AppConfig` sections. Do not duplicate the full root guide.

- [ ] **Step 3: Run compatibility checks against the real example.**

  Execute a small read-only Python check that normalizes `config.example.json` and prints the field names, typed neutralization, factory/search/research caps, and CLI override state directory. Confirm external JSON still contains both `agent` and `simulation` keys and that the normalized object does not expose either raw attribute.

- [ ] **Step 4: Update planning evidence.**

  Mark Tasks 1–3 and their phases with actual test output, list changed files, and record any failures. The plan's `Next Step` must always name the next single action.

### Task 4: Full verification, fresh review, and delivery audit

**Files:**
- Review: all changed source, test, documentation, and planning files

**Interfaces:**
- Consumes: the completed implementation and compatibility evidence.
- Produces: final validation evidence and a delivery decision; no unverified completion claim.

- [ ] **Step 1: Run the required full checks.**

  Run each command freshly:

  ```powershell
  python -m unittest discover -s tests
  python -m compileall -q wqb_agent scripts tests
  python -m ruff check .
  python main.py --state-dir tests/fixtures state doctor
  python main.py --state-dir tests/fixtures state audit
  python main.py context --compact --json
  git diff --check
  ```

  Capture exit codes and relevant machine-readable results. Do not call the goal complete if any required check fails.

- [ ] **Step 2: Perform fresh code review against the spec.**

  Review the final diff and relevant line history. Confirm production raw consumers are zero except parser-only reads, no public external key was renamed, no state/Simulation path changed, and tests would fail if either raw field or typed smoke projection regressed. Report only actionable Critical/Suggestion/Nice-to-have findings with exact locations.

- [ ] **Step 3: Resolve review findings and rerun affected verification.**

  If a Critical or Important finding appears, fix it with a new failing regression test where applicable, then rerun the focused and full checks. Keep deferred scope unchanged.

- [ ] **Step 4: Decide commit/push only after verification.**

  If the user has authorized repository delivery, configure the repository-local Git email as `2966684515@qq.com`, create an English-prefix-plus-Chinese commit message such as `refactor：移除AppConfig原始配置兼容映射`, push the requested branch, and re-read `origin/main` to report the final SHA. Otherwise leave the verified changes uncommitted and explicitly report that no remote SHA exists for this phase.
