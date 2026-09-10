# Alpha Factory Test Audit — 2026-09-10

## Scope

This audit follows the complete research loop from suggestion context through
semantic proposal assembly, budget selection, bounded factory routing, and
evidence-oriented continuation. No real BRAIN Simulation or Alpha submission
was performed.

## Test inventory

- Before: 40 test files and 688 tests.
- After: 41 test files and 692 tests.
- Retained: execution safety, checkpoint/recovery, evidence, metrics, alpha
  quality, quota, workflow ownership, and route-control contracts.
- Merged: four overlapping legacy-entrypoint tests became one parameterized
  test covering both blocked entrypoints, no Simulation calls, and no state
  write. The unique safety assertions were retained.
- Deleted: three duplicate test methods absorbed by that merged contract; no
  unique production behavior was removed.
- Added: `tests/test_research_loop.py` with seven integration tests covering
  semantic traits and stable identity, optimizer lineage, reflection-to-memory
  context reaching budget priority, priority ordering, candidate-pool
  saturation, stale-audit clearing, and bounded scarcity STOP behavior.

## Bugs found and fixed

1. `select_budget_candidates()` sorted textual priority names, causing `LOW`
   candidates to precede `NORMAL` candidates. Explicit `HIGH → NORMAL → LOW`
   ordering now controls interleaving.
2. Candidate-pool saturation was implemented in the budget-priority API but the
   real selector did not provide saturation counts. The selector now derives
   mechanism and lineage saturation from the eligible pool and records it in
   the audit.
3. A real single-field pool could produce fewer than 100 candidates, after
   which the factory runner repeatedly waited until its deadline. The selected
   batch is now projected into the existing route probe; bounded reroute or
   STOP is used, with no quota reservation or proposal execution on shortage.
4. An invalid or empty factory call could expose the previous call's budget
   audit. Each batch generation now clears the derived audit before validation.

## Verification

- Full unittest: 692 passed.
- Compileall, Ruff, and the nine-module mypy frontier: passed.
- Branch coverage: 78.4%, above the project 76.0% floor.
- State doctor and audit on fixtures: passed; no unresolved submissions,
  `SUBMIT_UNKNOWN`, or simulated requests.
- Diff check: passed with only normal line-ending warnings.

## Remaining risk

The intended runtime remains dependent on live BRAIN field/operator responses
and credentials when run online. This audit verifies the local control plane
and fail-closed behavior without asserting live platform availability.
