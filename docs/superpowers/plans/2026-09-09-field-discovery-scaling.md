# FieldDiscovery Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `FieldDiscovery` 建立按 dataset/type 的分页完整性契约、动态 dataset universe 边界、分层字段检索和可解释排序 provenance。

**Architecture:** 继续使用现有 `FieldDiscovery` 的 metadata cache 作为唯一 field evidence owner。分页 helper 产出字段和完整性 provenance；catalog manifest 携带同一 provenance；discover 在 bounded candidate pool 上做排序并把解释写入 profile。Factory、Simulator、Trajectory、CheckpointStore 和 template semantics 不变。

**Tech Stack:** Python 3.11、标准库、`unittest`、现有 BRAIN client fake。

**Spec:** `docs/superpowers/specs/2026-09-09-field-discovery-scaling-design.md`

## Global Constraints

- 保留 `DATASET_CATEGORIES` 作为 seed/fallback，不虚构远端能力。
- `max_pages` 仍是安全预算；达到预算只能产生 `INCOMPLETE/TRUNCATED`，不能产生完整目录。
- MATRIX/VECTOR completeness 分开记录。
- 不创建第二套 field state 或 research state。
- 不改变 Alpha Factory template semantics、Simulation POST 路径或真实研究状态。
- discovery artifact 不得写入 Simulation metrics/results、Alpha payload 或 submission state。

### Task 1: Lock the pagination contract with failing tests

**Files:**
- Modify: `tests/test_discovery.py`

**Interfaces:**
- Consumes: existing `FieldDiscovery._fields_for()` and `source_provenance()`.
- Produces: regression coverage for per-type completeness, bounded truncation, malformed fail-closed behavior and artifact safety.

- [x] **Step 1: Write failing tests** for a fake client with 1001 MATRIX and 1001 VECTOR fields, asserting separate `expected_count`, `loaded_count`, and `complete=True` when `max_pages` is sufficient; add a `max_pages=20` case asserting `complete=False` and `MAX_PAGES`; add count-underrun and malformed-page cases asserting incomplete provenance.
- [x] **Step 2: Run the focused tests** with `python -m unittest tests.test_discovery.TestFieldDiscovery -v` and confirm the new assertions fail because current provenance has no completeness contract and max-page exhaustion is silent.
- [x] **Step 3: Keep the test fixtures read-only** and assert no simulation metrics/results keys are present in persisted catalog payloads.

### Task 2: Implement bounded pagination and provenance

**Files:**
- Modify: `wqb_agent/discovery.py`
- Modify: `tests/test_discovery.py`

**Interfaces:**
- Consumes: `client.get_datafields(dataset_id, limit, offset, field_type)`.
- Produces: `field_completeness`, `catalog_status`, and `source_provenance()` metadata with MATRIX/VECTOR rows.

- [x] **Step 1: Add the smallest private pagination helper** that validates integer non-negative count, list page, stable count, advancing offset, and max-page budget, returning fields plus one contract row.
- [x] **Step 2: Run the focused pagination tests** and confirm they pass.
- [x] **Step 3: Integrate both `FIELD_TYPES` through the helper** while preserving field deduplication and existing cache behavior.
- [x] **Step 4: Run existing discovery cache/catalog tests** and repair only compatibility behavior required by the explicit contract.
- [x] **Step 5: Write completeness and catalog status into new manifests**, and make catalog loading fail closed for malformed/incomplete snapshots while preserving scope checks.
- [x] **Step 6: Run `python -m unittest tests.test_discovery -v` and `python -m compileall -q wqb_agent tests`.**

### Task 3: Add dynamic dataset boundary and layered candidate retrieval

**Files:**
- Modify: `wqb_agent/discovery.py`
- Modify: `tests/test_discovery.py`

**Interfaces:**
- Consumes: optional read-only `client.get_datasets()` and existing dataset pool/categories.
- Produces: explicit dataset universe provenance and bounded candidate list before semantic ranking.

- [x] **Step 1: Add failing tests** for dynamic dataset listing, fallback when listing is unavailable/malformed, candidate pool boundedness, and unchanged multi-dataset stratified sampling.
- [x] **Step 2: Run those tests and confirm expected failures.**
- [x] **Step 3: Implement normalized dynamic listing with explicit fallback provenance.**
- [x] **Step 4: Implement cheap candidate retrieval with a fixed constructor limit (default 100) without changing `target_count`.**
- [x] **Step 5: Run the focused dataset/ranking tests and then the full discovery module.**

### Task 4: Make tokens and ranking explanations bilingual and transparent

**Files:**
- Modify: `wqb_agent/discovery.py`
- Modify: `tests/test_discovery.py`

**Interfaces:**
- Consumes: hypothesis statement/tags and field metadata.
- Produces: stable Chinese/English keywords and `ranking_provenance` on active profiles.

- [x] **Step 1: Add failing tests** asserting Chinese hypothesis text yields useful Chinese tokens and each selected field exposes all four contribution keys.
- [x] **Step 2: Run the focused tests and confirm current ASCII-only extraction and opaque score fail them.**
- [x] **Step 3: Implement bounded CJK token extraction and split `_score_field()` into contribution values while retaining compatible aggregate score.**
- [x] **Step 4: Include deterministic exploration contribution only when the selection mode enables it; preserve random seed and stratified order.**
- [x] **Step 5: Run focused discovery tests and inspect serialized profiles for absence of metrics/results.**

### Task 5: Full verification and repository handoff

**Files:**
- Modify: `task_plan.md`
- Modify: `progress.md`
- Modify: `findings.md`

- [x] **Step 1: Re-check `git status` and diff for overlap with the parallel Factory conversation.**
- [x] **Step 2: Run `python -m unittest discover -s tests`.**
- [x] **Step 3: Run `python -m compileall -q wqb_agent scripts tests`.**
- [x] **Step 4: Run `python -m ruff check .` and `git diff --check`.**
- [x] **Step 5: Run fresh code review against the final diff and resolve actionable findings.**
- [x] **Step 6: Configure Git email `2966684515@qq.com`, commit with an English prefix and Chinese message, push to `origin/main`, and verify remote SHA.**
