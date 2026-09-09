# Structured CLI Subcommands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the boolean-flag CLI mode explosion with a structured argparse grammar, one canonical command representation, and one runtime dispatch while preserving all research and Simulation safety boundaries.

**Architecture:** Put parser construction, `CLICommand`, and legacy-to-canonical normalization in `wqb_agent/cli.py`. Keep config loading, client construction, lock ownership, and business dispatch in `main.py`, switching only from raw argparse flags to the canonical command. Use standard-library argparse only; no changes to Agent/Client/Simulator or state data.

**Tech Stack:** Python standard library (`argparse`, `dataclasses`, `sys`), existing unittest suite, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-09-cli-subcommands-design.md`

## Global Constraints

- `Agent.run_proposals()` remains the only production Simulation execution path.
- `SUBMIT_UNKNOWN` remains fail-closed and is never re-POSTed by CLI normalization.
- Known progress URLs remain read-only recovery targets.
- `factory` daily/weekly quotas, research policy, typed config normalization, and state schema are unchanged.
- `factory stop/status`, state diagnostics, and context must not construct `WQBClient`.
- No Typer, Click, mypy expansion, or unrelated Ruff rule changes.
- Do not commit or push unless separately authorized.

### Task 1: Lock the parser contract with failing tests

**Files:**
- Create: `tests/test_cli.py`
- Modify: `task_plan.md`, `findings.md`, `progress.md`

**Interfaces:**
- Tests consume the planned `wqb_agent.cli.parse_cli(argv)` and `CLICommand` fields.
- Tests will later protect `main.main()` dispatch and lazy-client behavior.

- [ ] **Step 1: Write grammar and legacy tests first.** Cover every canonical command, command-specific options, rejected combinations, and representative legacy forms. Assert canonical command tuples/fields rather than help text.
- [ ] **Step 2: Add safety tests.** Patch client construction and lock acquisition at the existing import boundaries; verify local read-only commands do not construct a client, suggest does not acquire the owner lock, and production commands retain their lock path.
- [ ] **Step 3: Run only the new tests and confirm they fail because `wqb_agent.cli` and the new main dispatch do not yet exist.**

### Task 2: Implement canonical argparse and legacy adapter

**Files:**
- Create: `wqb_agent/cli.py`
- Modify: `main.py` only where parser setup and command field access are replaced
- Test: `tests/test_cli.py`

**Interfaces:**
- `build_parser() -> argparse.ArgumentParser`
- `parse_cli(argv: Sequence[str] | None = None) -> CLICommand`
- `CLICommand(domain: str, action: str, config: str, state_dir: str | None, ...)`

- [ ] **Step 1: Add frozen `CLICommand` with explicit fields for proposals path, hours, force-new-round, compact/json/task, dry-run, recovery round/id, offline, and legacy marker.**
- [ ] **Step 2: Build required nested subparsers for `factory`, `state`, `alpha`, and `recovery`; attach `--hours`, `--dry-run`, context options, and `--force-new-round` only to their owning commands.**
- [ ] **Step 3: Implement a finite legacy adapter that maps old mode flags to canonical argv and rejects multiple modes or invalid option ownership before canonical parsing.**
- [ ] **Step 4: Emit legacy deprecation warnings only to stderr and let canonical argparse retain exit code 2 for syntax errors.**
- [ ] **Step 5: Run `python -m unittest tests.test_cli` and confirm all parser tests pass.**

### Task 3: Switch main.py to one canonical dispatch

**Files:**
- Modify: `main.py`
- Test: `tests/test_cli.py`, `tests/test_runtime_safety.py`, `tests/test_agent_context.py`

**Interfaces:**
- `main.main()` consumes only `CLICommand` from `parse_cli()` after this task.
- Existing runtime helpers and method calls remain unchanged.

- [ ] **Step 1: Replace the top-level boolean parser and manual action mutual-exclusion block with `parse_cli()`.**
- [ ] **Step 2: Preserve typed config loading, read-only example fallback, and `apply_cli_overrides(..., state_dir=...)` exactly at the existing boundary.**
- [ ] **Step 3: Convert each branch to `(command.domain, command.action)` checks without changing imports, client construction order, lock operation names, or Agent calls.**
- [x] **Step 4: Preserve audit/preflight exit code 2 and the smoke `UNAVAILABLE` JSON contract; runtime smoke failures now return exit code 1.**
- [ ] **Step 5: Run the new tests plus existing runtime/context tests.**

### Task 4: Update documentation and CI-facing examples

**Files:**
- Modify: `AGENTS.md`, `docs/AGENTS.md`, `docs/README.md`, `scripts/README.md`, relevant `README.md` if present, `.github/workflows/ci.yml` if old CLI calls exist, `findings.md`, `progress.md`
- Test: documentation search and CLI help subprocess checks

**Interfaces:**
- Documentation presents canonical subcommands first.
- Legacy references explicitly state temporary compatibility.

- [ ] **Step 1: Replace primary examples with structured commands, retaining only a small legacy compatibility note.**
- [ ] **Step 2: Update CI to use `state doctor`, `state audit`, and other canonical forms where applicable.**
- [ ] **Step 3: Search all old flags and classify remaining references as implementation compatibility, tests, or historical evidence.**
- [ ] **Step 4: Run help for root and nested command groups and assert command-specific options are visible only under the correct parser.**

### Task 5: Fresh safety review and full verification

**Files:**
- Modify: `task_plan.md`, `findings.md`, `progress.md` with evidence and deferred items

- [ ] **Step 1: Run `python -m compileall -q wqb_agent scripts tests`.**
- [ ] **Step 2: Run `python -m unittest discover -s tests`.**
- [ ] **Step 3: Run `python -m ruff check .` and `git diff --check`.**
- [ ] **Step 4: Run canonical doctor, audit, preflight, and all required help commands; record expected preflight exit 2 separately from failures.**
- [ ] **Step 5: Review the diff for unchanged Simulation POST, `SUBMIT_UNKNOWN`, recovery, quotas, research policy, and typed config paths; do not claim completion until evidence covers every spec item.**
