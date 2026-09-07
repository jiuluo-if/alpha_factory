# Agent-facing architecture

This is the repository's cognitive compression layer. It describes the
stable concepts an external coding/research agent needs before reading runtime
implementation details.

## One research loop

```text
Agent
  -> research_api.py
  -> discovery / simulation
  -> WorldQuant BRAIN
  -> experiment evidence
  -> evaluation
  -> workspace / memory
```

The agent chooses the hypothesis, experiment, interpretation, and next step.
The Python runtime enforces truth, execution, persistence, validation, safety,
and recovery.

## Facts and state

| Layer | Meaning | Examples |
|---|---|---|
| live truth | Current platform response | BRAIN datasets, fields, operator capability, Simulation progress, metrics, checks |
| immutable evidence | What happened in a research attempt | `trajectory.jsonl`, completed experiment record, append-only ledger |
| derived state | Rebuildable views for the next decision | `context.md`, `experience.json`, reports, summaries, submission review material |
| cache | Bounded performance/advisory data | field cache, evidence cache |

When layers disagree, prefer live BRAIN truth, then immutable evidence, then
derived state, then cache. Missing or ambiguous evidence remains
`UNKNOWN`/`UNAVAILABLE`.

## Core concepts

`BrainGateway` is the conceptual platform boundary implemented by the client,
discovery, and simulator layers. It retrieves current BRAIN facts and submits
or polls Simulations under retry and unknown-write rules.

An `Experiment` is one auditable attempt: hypothesis, expression, settings,
and result/evidence. `ExperimentSpec` in `research_api.py` is the lightweight
agent-authored input; the existing proposal contract expands and validates it.

`ExperimentStore` is the conceptual evidence boundary implemented by
`Trajectory`, checkpoints, `TrialLedger`, and compact memory/workspace views.
There is no second store introduced by the facade.

`Evaluation` combines metrics, checks, yearly behavior, correlation,
statistical diagnostics, and robustness. Evaluation describes evidence; it
does not invent platform truth or choose the research direction.

## Mechanism versus research policy

Mechanism invariants must remain fail-closed: schema validation, expression
deduplication, hard budgets, checkpoint recovery, OS locks, Retry-After,
known-URL polling, and unknown Simulation write reconciliation.

Research policy is adjustable: hypothesis/dataset selection, mutation direction,
window choice, experiment priority, and whether to continue or stop a line.
Heuristics such as search allocation or stalled-space rotation are policy, not
BRAIN requirements.

## Where to look

| Question | Start here |
|---|---|
| What can an agent call? | `wqb_agent/research_api.py` |
| How are fields and platform facts obtained? | `wqb_agent/discovery.py`, `wqb_agent/client.py` |
| How is one Simulation executed safely? | `wqb_agent/simulator.py`, `wqb_agent/client.py` |
| How are experiments and recovery persisted? | `wqb_agent/state.py`, `wqb_agent/trial_ledger.py` |
| How are results evaluated? | `wqb_agent/metrics.py`, `validation_report.py`, `robustness.py` |
| How are unknown writes reconciled? | `wqb_agent/client.py`, `scripts/reconcile_pending.py` |
| What are current operator/settings rules? | `docs/OPERATORS_CHEATSHEET.md`, `docs/SIMULATION_SETTINGS.md` |
| What is historical context only? | `docs/PHASE*.md`, `docs/superpowers/**` |

Do not read the whole package by default. Read the facade, then the target
module, one direct dependency, one relevant test, and one policy document.

## Future simplification candidates

These are deliberately recorded, not removed in this task:

- `factory_runner.py` and its session lifecycle: compatibility control plane
  outside the default agent-facing loop.
- `docs/PHASE*.md` and `docs/superpowers/**`: historical design archaeology.
- Completed round summaries and completed checkpoints in `.wqb_state/`: safe
  archive candidates only after dry-run, lock/checkpoint audit, and explicit
  confirmation.
- Large derived/cache files such as `trajectory.jsonl` and field caches:
  investigate bounded views or rebuildability before any compaction; the
  append-only evidence source must remain recoverable.
