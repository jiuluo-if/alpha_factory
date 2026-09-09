# Proposal Execution Workflow Design

## Goal

Extract proposal execution and checkpoint recovery orchestration from `Agent` into `wqb_agent/proposal_execution.py` without changing observable behavior.

## Non-negotiable contract

- Inputs, checkpoint JSON, Simulation POST count, execution order, state transitions, console output, return behavior, and failure semantics remain unchanged.
- A missing proposals file returns `None` without creating a Simulation or checkpoint.
- Malformed payloads, invalid `round_no` values (`bool`, `0`, negatives, and non-numeric garbage), and foreign unfinished checkpoints fail closed without a new POST.
- A complete checkpoint is terminal and is not redispatched.
- `SUBMIT_UNKNOWN` is exactly-once: it is never resent; pending work without a known `progress_url` in the same checkpoint is blocked; known `progress_url` work may be polled read-only.
- `Simulator` remains the Simulation lifecycle owner, and the workflow never calls `client.submit_simulation` directly.
- Existing checkpoint persistence, trajectory, trial ledger, and memory owners remain authoritative; no duplicate state machine or store is introduced.
- `Agent.last_run_stats` keys and semantics remain compatible with factory callers.

## Target boundary

```text
Agent (high-level research coordination and compatibility facade)
  -> ProposalExecutionWorkflow (proposal execution/recovery orchestration)
      -> Simulator (remote Simulation lifecycle)
          -> WQBClient (HTTP transport)
```

The workflow receives a narrow dependency context. It must not import `Agent` or depend on `main`, `cli`, or `factory_runner`. Existing domain modules remain shared domain owners; state owner methods are injected or called through their existing owner rather than reimplemented.

## Migration order

1. Characterization tests and call graph.
2. Workflow boundary and entry/checkpoint detection.
3. Checkpoint resume and exactly-once filtering.
4. Payload validation, round resolution, factory-batch contract, and proposal execution gates.
5. Dispatch, settlement, evidence, and stats projection.
6. Facade and compatibility wrappers.
7. Architecture/documentation review and full verification.

## Out of scope

Suggestion workflow, optimizer workflow, CLI redesign, Client refactor, credential discovery, raw config compatibility removal, mypy, coverage thresholds, Ruff expansion, state schema, Simulation settings, factory quota, and research policy changes.
