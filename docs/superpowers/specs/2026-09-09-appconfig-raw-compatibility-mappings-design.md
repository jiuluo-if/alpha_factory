# AppConfig Raw Compatibility Mapping Removal

## Goal

Remove the historical raw `simulation` and `agent` shadow mappings from the internal `AppConfig` model while preserving the external configuration file contract and all current runtime semantics.

## Scope and invariants

The accepted external schema remains:

```json
{
  "simulation": {"neutralization": "SUBINDUSTRY"},
  "agent": {"state_dir": ".wqb_state"}
}
```

`parse_config()` remains the only place that interprets those raw keys. It deep-copies values into the existing typed sections so later mutation of the caller's raw dictionary cannot alter the normalized object. After `normalize_config()` returns, `AppConfig` has only the typed sections `search`, `research_allocation`, `factory`, `incremental_value`, `validation`, `statistical`, `robustness`, `simulation_config`, and `runtime`.

No deprecated `AppConfig(agent=..., simulation=...)` constructor support will be added. This is an internal model cleanup, not an external schema migration.

## Runtime boundary

The existing typed runtime projection remains authoritative:

```text
raw JSON/dict
    -> parse_config()/normalize_config()
typed AppConfig
    -> AgentRuntimePolicy / RuntimeComponents / workflows
```

The read-only smoke helper currently reaches through `config.agent` to obtain the optional `smoke_dataset`. That value will become `AgentRuntimeConfig.smoke_dataset`, and the helper will require `AppConfig` and read only `config.runtime.smoke_dataset`. This preserves the current smoke selection behavior without retaining a raw mapping.

`runtime_policy.py`, `runtime_components.py`, `agent.py`, diagnostics, and workflows remain otherwise unchanged. `main.py` continues to load raw JSON only before normalization and uses `typed_config` thereafter.

## Compatibility and error behavior

- External keys `agent` and `simulation` remain accepted.
- Parser error paths remain `config.agent...` and `config.simulation...` because they describe user input.
- Existing defaults, budget hierarchy, simulation settings, incremental policy, and CLI `state_dir` override remain unchanged.
- `normalize_config(AppConfig)` remains an identity operation.
- `apply_cli_overrides()` continues to return a replacement typed config without mutating its input.
- Raw input and typed policy mappings remain separately copied; this task does not attempt deep immutability for every policy mapping.

## Tests and architecture guards

Add regression tests that prove:

1. `dataclasses.fields(AppConfig)` contains neither `agent` nor `simulation`.
2. Normalizing the external schema still produces the expected typed values.
3. Typed normalization preserves identity and CLI override semantics.
4. Raw input mutation does not change `runtime` or `simulation_config`.
5. Production modules do not read `config.agent` or `config.simulation`; parser-only raw reads remain allowed in `config.py`.
6. The smoke helper uses the typed `smoke_dataset` projection.

Documentation will state the external-schema/internal-model naming split and the one-way raw-to-typed boundary in the root and package architecture guidance.

## Explicitly deferred

Alpha color workflows, credential discovery, broad policy-map typing, mypy, coverage gates, Ruff expansion, Simulation behavior, checkpoint/state schema, quotas, research policy, and CLI redesign.
