# 渐进式工程质量门实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 coverage 回归、typed frontier 类型回归和低风险 Ruff 回归都能真实阻断 CI 的质量底线，同时保持研究与生产安全语义不变。

**Architecture:** 只在 `pyproject.toml` 声明统一工具配置，Coverage 以 `wqb_agent` 为唯一 production source 并开启 branch gate；mypy 只检查 9 个边界清晰模块，保留非 strict 全局设置；CI 按 install → compile → type → unit → Ruff → coverage → doctor/audit 执行同一组命令。代码改动仅限 Ruff 低风险机械修复和必要的精确异常链修复，不触碰 Client retry、Simulation、checkpoint、credentials、Alpha Feed/Color 或研究策略。

**Tech Stack:** Python 3.11、unittest、coverage.py、mypy、Ruff、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-09-09-quality-gates-design.md`

## Global Constraints

- The pre-configuration `--include` baseline was statements `80.83%`, branches `69.00%`, branch-aware `77.54%`; the enforceable configured baseline is statements `79.99%`, branches `68.31%`, branch-aware `76.74%` because `source=["wqb_agent"]` includes unimported production files.
- Initial `fail_under` is `76.0`; it is based on the configured production baseline (`79.99%` statements, `68.18%` branches, `76.71%` branch-aware) and may only increase later unless explicitly justified.
- Typed frontier is exactly `config.py`, `runtime_policy.py`, `runtime_components.py`, `runtime_composition.py`, `credentials.py`, `suggestion_workflow.py`, `alpha_feed_workflow.py`, `optimizer_workflow.py`, and `alpha_color_workflow.py`.
- Ruff enables `E4,E7,E9,F,I,UP009,UP012,UP017,UP031,UP035,UP037,B007,B904`; it does not enable `ALL`, `UP042`, `B025`, `B905`, `SIM`, or `RUF`.
- No live BRAIN authentication, Simulation POST, Alpha submission, or mutation of real research state is allowed.

---

### Task 1: Record baseline and freeze the quality contract

**Files:**
- Modify: `task_plan.md`, `findings.md`, `progress.md`
- Create: `docs/superpowers/plans/2026-09-09-quality-gates.md`

**Interfaces:**
- Produces the measured coverage/Ruff/mypy baseline and the exact frontier used by later tasks.

- [x] **Step 1: Run fresh baseline commands**

Run `git fetch origin main`, `coverage erase`, `coverage run --branch -m unittest discover -s tests`, `coverage report -m`, production-only coverage report, Ruff dry-runs, and the candidate mypy command.

- [x] **Step 2: Record evidence and decisions**

Record the results in the project ledgers and keep the existing untracked design spec intact.

### Task 2: Add configuration and a single CI quality sequence

**Files:**
- Modify: `pyproject.toml`, `.github/workflows/ci.yml`, `AGENTS.md`, `wqb_agent/AGENTS.md`, `README.md`

**Interfaces:**
- `pyproject.toml` owns dev dependencies and tool gates.
- CI invokes the same typed, lint, unit, coverage, doctor, and audit commands documented for local use.

- [x] **Step 1: Add dev tools and non-strict mypy frontier configuration**

Add `mypy` to the dev extra; the measured nine-module frontier is clean without `types-requests` under `follow_imports = "skip"`, so do not add an unnecessary stub dependency. Configure Python 3.11, `check_untyped_defs`, `no_implicit_optional`, warning options, and the nine explicit typed modules in the command/documentation rather than enabling full-repository strict mode.

- [x] **Step 2: Configure production branch coverage**

Set `branch = true`, `source = ["wqb_agent"]`, `show_missing = true`, `skip_covered = false`, `precision = 1`, and `fail_under = 76.0`; do not omit security-critical modules.

- [x] **Step 3: Expand only the selected Ruff families**

Keep the existing rules and add `I`, the selected UP rules, `B007`, and `B904`; preserve the current test per-file ignores.

- [x] **Step 4: Align CI and documentation**

Use install → compile → type → unit → Ruff → `coverage erase`/branch coverage/report → doctor → audit, with no live network step and no duplicate ad-hoc quality contract.

### Task 3: Make the selected lint gate green with minimal edits

**Files:**
- Modify: only files reported by the selected `I`, UP subset, `B007`, and `B904` checks.
- Test: existing `tests/` suite; add no coverage-only tests.

**Interfaces:**
- All changes preserve current runtime values, exception types, retry semantics, and serialized contracts.

- [x] **Step 1: Apply import sorting only**

Run `python -m ruff check . --select I --fix`, inspect the diff, and reject unrelated formatter churn.

- [x] **Step 2: Apply safe UP fixes**

Use only the selected safe UP families; inspect `datetime.UTC`, encoding, import-source, and format-string changes individually.

- [x] **Step 3: Fix B007 and B904 precisely**

Rename unused loop variables to `_` where semantics are unchanged. Add `from exc` or `from None` only where it preserves the current exception type and fail-closed behavior; do not enable or fix B905 zip semantics.

- [x] **Step 4: Run focused lint and regression tests**

Run the selected Ruff command, compileall, and the full unittest suite; if any behavior changes, stop and add a behavior regression before continuing.

### Task 4: Prove typed frontier and coverage gates

**Files:**
- Modify: only `pyproject.toml` or typed frontier code if mypy reports a real, local type issue.

**Interfaces:**
- Mypy must report zero errors for the nine modules without blanket ignores.
- Coverage must fail below `76.0` and must report `wqb_agent` only.

- [x] **Step 1: Install the declared dev extra in the verification environment**

Run `python -m pip install ".[dev]"` and verify the declared tools are available.

- [x] **Step 2: Run mypy on the exact frontier**

Run the nine-module mypy command and record checked-file count and zero errors.

- [x] **Step 3: Run branch coverage with the configured gate**

Run `coverage erase`, `coverage run --branch -m unittest discover -s tests`, and `coverage report`; confirm the configured source and fail-under are effective.

### Task 5: Fresh review and final validation

**Files:**
- Modify: `task_plan.md`, `findings.md`, `progress.md` only for evidence.

**Interfaces:**
- Produces a reviewable diff and evidence-backed delivery report; no commit or push unless separately authorized.

- [x] **Step 1: Review the complete diff**

Check coverage threshold provenance, absence of junk tests/excludes/blanket ignores, runtime safety invariants, Ruff diff scope, and CI fail behavior.

- [x] **Step 2: Run the complete validation set**

Run compileall, unittest, Ruff, exact mypy frontier, branch coverage/report, fixture doctor/audit, compact JSON context, and `git diff --check`.

- [x] **Step 3: Clean generated artifacts and report deferred work**

Remove only generated coverage/cache artifacts created by this validation, then report baseline SHA, final local SHA, evidence, safety proof, and deferred broader typing/lint/coverage work.
