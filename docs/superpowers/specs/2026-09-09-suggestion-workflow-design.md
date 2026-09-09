# Suggestion Workflow Design

## Goal

将 suggestion/discovery round 的编排从 `Agent` 抽离为独立的
`SuggestionWorkflow`，保持现有 bundle、fallback、字段来源和输出行为等价，
且 suggestion 路径不产生 Simulation POST、checkpoint 写入、owner lock 获取或
其他远程写请求。

## Scope and ownership

`SuggestionWorkflow` owns:

- suggestion round orchestration;
- stalled research-space rotation;
- discovery fallback orchestration;
- field bundle normalization;
- suggestion bundle assembly;
- `suggestions.json` emission and existing console output.

`Agent` continues to own:

- high-level research coordination;
- `_form_research_space` and the state-aware hypothesis planning it invokes;
- trusted-best and best-field research hooks;
- optimizer coordination and `optimizer_gate_report`.

`Discovery`, `ExperienceMemory`, `Trajectory` and `AlphaFactory` remain owners of
their existing facts and domain operations. `ProposalExecutionWorkflow` remains a
sibling workflow and is not imported by the suggestion workflow.

## Dependency shape

The workflow receives explicit domain dependencies and operation-shaped hooks:

```text
Agent
  -> SuggestionWorkflow
      -> Discovery
      -> Memory / Trajectory / AlphaFactory
      -> research-planning hooks supplied by Agent
```

The module must not import `agent`, `client`, `simulator`,
`proposal_execution`, `main` or `factory_runner`. It receives no simulator,
checkpoint store or transport object.

The hooks are narrow callables for `ensure_loaded`, `next_round_no`,
`form_research_space`, `trusted_current_best`, `ensure_best_field`,
`optimizer_gate_report`, `epoch_label`, and fallback templates. The workflow
does not read or mutate `_last_round_skipped` or `memory.best_exhausted`; those
remain inside the Agent-owned planning hook.

## Behavior contract

For a fixed runtime and deterministic discovery result, the workflow must
preserve:

- the existing round number and epoch label;
- the existing initial research-space construction and stalled-space rotation;
- the exact fallback candidate order, target count, statement, tags, datasets,
  `parent_best`, and console marker;
- trusted current-best field preservation and field metadata normalization;
- all existing bundle keys, including duplicated top-level provenance fields and
  `optimizer_context` semantics;
- atomic idempotent writing to `state_dir/suggestions.json`;
- return value equality between `Agent.run_suggestion_round()` and direct
  `SuggestionWorkflow.run()`.

The workflow may perform existing read/discovery operations, but it must not
call `Simulator`, write checkpoint state, acquire the Simulation owner lock, or
issue a remote write.

## Testing and documentation

Add tests for normal output, JSON persistence, fallback call order and target
count, trusted-best field preservation, no-Simulation/no-checkpoint behavior,
facade delegation, direct-workflow equivalence and reverse dependency guards.
Update root and package `AGENTS.md` plus `docs/ARCHITECTURE_AGENT.md` with the
new ownership map. Do not change research policy, factory dual-layer behavior,
Alpha feed, credentials, config compatibility or Simulation execution.
