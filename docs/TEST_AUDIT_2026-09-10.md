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

- Full unittest: 693 passed.
- Compileall, Ruff, and the nine-module mypy frontier: passed.
- Branch coverage: 78.4%, above the project 76.0% floor.
- State doctor and audit on fixtures: passed; no unresolved submissions,
  `SUBMIT_UNKNOWN`, or simulated requests.
- Diff check: passed with only normal line-ending warnings.

## Second mutation-audit update — 2026-09-11

- This second audit started from 41 test files and 692 tests and now has 41
  files and 693 tests.
- Two low-value exception-shape methods were consolidated into the existing
  table-driven contract; three route/relationship/restart integration cases
  are now present, and the optimizer case uses a real trajectory eligibility
  path.
- Final verification confirmed 693 tests and 78.4% branch coverage after the
  route-equality test change.

## Remaining risk

The intended runtime remains dependent on live BRAIN field/operator responses
and credentials when run online. This audit verifies the local control plane
and fail-closed behavior without asserting live platform availability.

## Critical Contract Matrix

| Contract | Production owner | Primary test | Failure mutation | Covered |
|---|---|---|---|---|
| `SUBMIT_UNKNOWN` never auto-resends | `Simulator._simulate_one` | `test_submit_unknown_second_run_does_not_post_again` | remove unknown no-resend branch | caught |
| checkpoint durable before POST | `ProposalExecutionWorkflow` / simulator callback | `test_checkpoint_update_precedes_first_submit` | POST before durable checkpoint | caught |
| known progress URL is read-only polled | `Simulator` / `WQBClient.poll_progress` | `test_poll_timeout_reuses_known_progress_url` | replace after poll failure | caught |
| quota reserved before execution | `AIFactoryRunner` | `test_daily_quota_blocks_batch_before_production_call` | move reserve after execution | caught |
| shared 429 gate before POST | `WQBClient` | `test_submission_slot_rechecks_gate_after_concurrent_429` | remove second gate check | caught |
| production Alpha submission remains manual | architecture/CLI boundaries | `test_no_production_alpha_submission_endpoint` | add automatic submission endpoint | caught |
| semantic UNKNOWN cannot auto-propose | `AlphaFactory` / diversity selector | `test_explicit_unknown_candidates_are_not_selected_to_fill_budget` | admit UNKNOWN candidate | caught |
| relationship REVIEW cannot auto multi-field | `AlphaFactory._relationship_gate` | `test_factory_drops_review_multi_field_optimized_prefix` | admit REVIEW | caught |
| ratio slot direction enforced | relationship gate | `test_ratio_requires_directional_earnings_over_assets_assignment` | accept reversed slots | caught |
| incompatible frequency rejected | relationship gate | `test_frequency_mismatch_is_incompatible_for_direct_correlation` | ignore frequency | caught |
| operator evidence required | `validate_proposal` | `test_production_contract_requires_description_and_operator_evidence` | skip operator evidence | caught |
| exact expression dedupe | proposal/execution contract | `test_factory_batch_rejects_duplicate_and_unowned_candidates` | remove canonical dedupe | caught |
| single observation is not SUPPORTED | `Reflector` | `test_supported_observation_does_not_become_durable_lesson_once` | default outcome SUPPORTED | caught |
| same lineage is not independent | `research_confirmation_view` | `test_same_lineage_repetition_is_not_independent_confirmation` | count duplicate lineage twice | caught |
| parameter-only variants are not independent | reflection guard | `test_parameter_only_variants_are_not_independent_confirmation` | remove parameter guard | caught |
| fake/cross-hypothesis evidence rejected | confirmation view | `test_fake_evidence_ref_blocks_confirmation` / `test_cross_hypothesis_evidence_cannot_confirm_current_hypothesis` | trust arbitrary refs | caught |
| RECONCILE is not a conclusion | reflection/evidence | `test_reconcile_evidence_cannot_write_durable_mechanism_learning` | promote reconcile | caught |
| system failure is not CONTRADICTED | reflection | `test_system_failure_cannot_contradict_hypothesis_or_pollute_avoid` | classify infra failure as negative evidence | caught |
| unresolved question reaches next budget | memory/factory selector | `test_reflection_memory_context_reaches_real_optimizer_budget` | drop question context | caught |
| expression-only change is not information gain | `AIFactoryRunner.route_decision` | `test_route_ignores_expression_only_change_but_accepts_semantic_or_relationship_change` | use candidate diff directly | caught |
| mechanism saturation reaches real selector | diversity selector | `test_budget_audit_reports_candidate_pool_saturation` | remove saturation input | caught |
| priority order is HIGH/NORMAL/LOW | budget selector | `test_priority_selection_orders_normal_before_low` | textual sort | caught |
| shortage enters bounded route | factory runner | `test_real_scarcity_routes_and_stops_without_idle_loop` | continue waiting | caught |
| shortage never executes partial batch | factory runner | same scarcity test, `run_proposals.assert_not_called()` | bypass batch gate | caught |
| restart preserves route/no-gain state | persisted factory session | `test_restart_preserves_budget_route_and_no_gain_state` | reset counters on reload | caught |

## Tests removed or consolidated in this phase

- `tests/test_client_refactor.py`: `test_mapping`, `test_kind_attribute`, and
  `test_all_are_wqberror` were consolidated into the table-driven
  `test_classified_exception_contract`. The exception mapping, kind values,
  and common base-class contract remain asserted.
- No test file was deleted. No safety or evidence contract was removed.

## Integration tests added in this phase

- `test_real_multifield_relationship_reaches_budget_with_audit`: catches loss
  of relationship admission or slot metadata between real assembly and budget.
- `test_restart_preserves_budget_route_and_no_gain_state`: catches restart
  reset, quota re-grant, checkpoint creation, or execution after bounded
  scarcity.
- `test_real_optimizer_child_preserves_parent_lineage_into_budget` now uses a
  real `Trajectory` and `OptimizerWorkflow` eligibility path before creating
  the child; it catches bypassing settled trajectory evidence or dropping the
  parent lineage.

## Mutation audit

All A–J mutations were applied in a detached temporary worktree and reverted:

`A caught` · `B caught` · `C caught` · `D caught` · `E caught` · `F caught` ·
`G caught` · `H caught` · `I caught` · `J caught`.

No uncaught critical mutation remains. No new production correctness issue
was found in this phase; the two newly found issues were test-coverage gaps
and were closed with integration tests.

## Test file classification

`CORE CONTRACT`: `test_architecture.py`, `test_checkpoint_store.py`,
`test_client_refactor.py`, `test_proposal_execution.py`,
`test_proposal_safety.py`, `test_protocol_truth.py`, `test_recovery.py`,
`test_research_constraints.py`, `test_runtime_safety.py`, `test_search_policy.py`,
`test_simulator.py`, `test_state.py`, and `test_submission.py`.

`INTEGRATION`: `test_agent_context.py`, `test_agent_evaluation.py`,
`test_agent_flow.py`, `test_alpha_color_workflow.py`,
`test_alpha_feed_workflow.py`, `test_factory_boundaries.py`,
`test_optimizer_workflow.py`, `test_research_loop.py`,
`test_suggestion_workflow.py`, and `test_workspace_snapshot.py`.

`COMPONENT`: `test_alpha_colors.py`, `test_artifacts.py`,
`test_credentials.py`, `test_discovery.py`, `test_evaluation.py`,
`test_evidence.py`, `test_expression.py`, `test_heartbeat.py`,
`test_incremental_value.py`, `test_memory_tiers.py`,
`test_robustness_audit.py`, `test_runtime_composition.py`,
`test_search_calibration.py`, and `test_validation_report.py`.

`CLI`: `test_cli.py` and `test_smoke.py`.

No file is classified as `DUPLICATE`, `LOW VALUE`, or removable `LEGACY`
after this phase's consolidation. No safety or evidence test was removed.
