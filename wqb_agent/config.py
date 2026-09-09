"""Single, typed, fail-closed application configuration parse."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .incremental_policy import IncrementalValuePolicy
from .search_policy import validate_budget_hierarchy


_MEMORY_DEFAULTS = {
    "max_lessons": 20,
    "max_avoid": 30,
    "max_next": 15,
    "max_hypotheses": 12,
    "max_short_term": 30,
    "short_term_window": 5,
    "promote_hits": 2,
    "max_garbage": 200,
    "garbage_max_age_rounds": 60,
    "next_max_age_rounds": 20,
    "max_lineages": 256,
    "max_seen_expressions": 4096,
    "max_used_hypotheses": 256,
}
_FIELD_SELECTION_DEFAULTS = {
    "mode": "semantic_random",
    "random_fraction": 0.35,
    "random_seed": "newwqb",
    # Field usage is platform truth when local Simulation/Alpha results are
    # intentionally ephemeral.  Keep the switch explicit for offline tests.
    "platform_usage_refresh": False,
    "require_platform_alpha_count": False,
    "dataset_sampling": "stratified",
    "dataset_pool": [],
    "min_datasets": 1,
    "min_cross_dataset_pairs": 0,
    "persist_catalog": False,
}
_SEARCH_POLICY_DEFAULTS = {
    "max_pending_per_arm": 1,
    "ucb_exploration": 1.0,
}
_QUALITY_DEFAULTS = {
    "max_self_correlation": 0.5,
    "success_sharpe": 1.25,
    "success_fitness": 1.0,
    "promising_sharpe": 0.9,
    "promising_fitness": 0.6,
    "min_turnover": 0.01,
    "max_turnover": 0.7,
    "max_drawdown": 0.5,
}


@dataclass(frozen=True)
class IncrementalValueConfig:
    mode: str = "required_when_available"
    max_abs_correlation: float = 0.7
    min_overlap: int = 60


@dataclass(frozen=True)
class ValidationConfig:
    yearly_min_years: int = 2


@dataclass(frozen=True)
class StatisticalConfig:
    mode: str = "required_when_available"


@dataclass(frozen=True)
class RobustnessConfig:
    min_sharpe_retention: float = 0.7
    min_fitness_retention: float = 0.6


@dataclass(frozen=True)
class SimulationConfig:
    settings: dict = field(default_factory=lambda: {"neutralization": "SUBINDUSTRY"})


@dataclass(frozen=True)
class AgentRuntimeConfig:
    """Typed values consumed while constructing the existing Agent runtime.

    Policy mappings remain mappings because their schemas are intentionally
    extensible; scalar defaults and path/limit values are resolved once here.
    This is a configuration boundary, not a second runtime or state model.
    """

    state_dir: str = ".wqb_state"
    max_rounds: int = 5
    candidates_per_round: int = 6
    max_proposals_per_round: int = 18
    max_concurrent_sims: int = 3
    research_integrity: bool = False
    correlation_refresh_window: int = 256
    fields_per_discovery: int = 6
    pagination_limit: int = 50
    max_pagination_pages: int = 20
    poll_timeout_sec: float = 1500
    replace_attempts: int = 3
    replace_backoff_sec: float = 60
    trajectory_window: int = 100
    context_experiments: int = 10
    fields_cache_ttl_sec: float = 7 * 24 * 3600
    max_field_alpha_count: int | None = None
    factory: dict = field(default_factory=dict)
    research_allocation: dict = field(default_factory=dict)
    search_policy: dict = field(default_factory=lambda: dict(_SEARCH_POLICY_DEFAULTS))
    field_selection: dict = field(default_factory=lambda: dict(_FIELD_SELECTION_DEFAULTS))
    submission_pool_filename: str = "submission_pool.json"
    memory: dict = field(default_factory=lambda: dict(_MEMORY_DEFAULTS))
    quality: dict = field(default_factory=lambda: dict(_QUALITY_DEFAULTS))
    statistical_policy: dict = field(default_factory=dict)
    robustness_policy: dict = field(default_factory=dict)
    yearly_policy: dict = field(default_factory=lambda: {"min_years": 2})

@dataclass(frozen=True)
class SearchConfig:
    enabled: bool = True
    max_simulations: int = 100
    validation_max_simulations: int = 4


@dataclass(frozen=True)
class ResearchAllocation:
    """Per-round role allocation, separate from the process hard cap."""

    max_simulations: int = 100
    maximum: dict = field(default_factory=dict)


@dataclass(frozen=True)
class FactoryConfig:
    max_simulations: int = 11200
    max_runtime_sec: int = 86400
    daily_simulation_cap: int = 1600
    weekly_simulation_cap: int = 11200


@dataclass(frozen=True)
class AppConfig:
    # Compatibility-only raw mappings. New runtime code consumes the typed
    # ``simulation_config`` and ``runtime`` fields below.
    simulation: dict = field(default_factory=dict)
    agent: dict = field(default_factory=dict)
    search: SearchConfig = field(default_factory=SearchConfig)
    research_allocation: ResearchAllocation = field(default_factory=ResearchAllocation)
    factory: FactoryConfig = field(default_factory=FactoryConfig)
    incremental_value: IncrementalValueConfig = field(default_factory=IncrementalValueConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    statistical: StatisticalConfig = field(default_factory=StatisticalConfig)
    robustness: RobustnessConfig = field(default_factory=RobustnessConfig)
    simulation_config: SimulationConfig = field(default_factory=SimulationConfig)
    runtime: AgentRuntimeConfig = field(default_factory=AgentRuntimeConfig)


def _as_bool(value, default, key):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on", "1"}:
            return True
        if normalized in {"false", "no", "off", "0"}:
            return False
    raise ValueError(f"{key} 必须是布尔值")


def _resolved_ints(values, defaults, *, minimum=0):
    resolved = dict(values)
    for key, default in defaults.items():
        try:
            value = int(values.get(key, default))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"config.agent.{key} 必须是整数") from exc
        if value < minimum:
            raise ValueError(f"config.agent.{key} 不得小于 {minimum}")
        resolved[key] = value
    return resolved


def _resolve_runtime_policies(agent):
    memory_raw = dict(agent.get("memory") or {})
    memory = _resolved_ints(memory_raw, _MEMORY_DEFAULTS)
    for key in ("max_lineages", "max_seen_expressions", "max_used_hypotheses"):
        if memory[key] < 1:
            raise ValueError(f"config.agent.memory.{key} 必须大于 0")

    field_selection = {**_FIELD_SELECTION_DEFAULTS, **dict(agent.get("field_selection") or {})}
    try:
        field_selection["random_fraction"] = float(field_selection["random_fraction"])
    except (TypeError, ValueError) as exc:
        raise ValueError("config.agent.field_selection.random_fraction 必须是数字") from exc
    if not 0.0 <= field_selection["random_fraction"] <= 1.0:
        raise ValueError("config.agent.field_selection.random_fraction 必须在 0 到 1 之间")
    field_selection["mode"] = str(field_selection["mode"] or "semantic_random")
    field_selection["random_seed"] = str(field_selection["random_seed"] or "newwqb")
    field_selection["dataset_sampling"] = str(
        field_selection["dataset_sampling"] or "stratified"
    ).lower()
    try:
        field_selection["min_datasets"] = max(
            1, int(field_selection["min_datasets"])
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("config.agent.field_selection.min_datasets 必须是整数") from exc
    try:
        field_selection["min_cross_dataset_pairs"] = max(
            0, int(field_selection["min_cross_dataset_pairs"])
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "config.agent.field_selection.min_cross_dataset_pairs 必须是整数"
        ) from exc
    raw_pool = field_selection.get("dataset_pool") or []
    if isinstance(raw_pool, (str, int)):
        raw_pool = [raw_pool]
    if not isinstance(raw_pool, list):
        raise ValueError("config.agent.field_selection.dataset_pool 必须是数组")
    field_selection["dataset_pool"] = [
        str(item.get("id") or item.get("name")) if isinstance(item, dict)
        else str(item)
        for item in raw_pool
        if isinstance(item, (str, int)) or (
            isinstance(item, dict) and (item.get("id") or item.get("name"))
        )
    ]
    for key in (
        "platform_usage_refresh", "require_platform_alpha_count", "persist_catalog"
    ):
        value = field_selection[key]
        if isinstance(value, bool):
            continue
        if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
            field_selection[key] = value.strip().lower() == "true"
            continue
        raise ValueError(f"config.agent.field_selection.{key} 必须是布尔值")

    search_policy = {**_SEARCH_POLICY_DEFAULTS, **dict(agent.get("search_policy") or {})}
    try:
        search_policy["max_pending_per_arm"] = int(search_policy["max_pending_per_arm"])
        search_policy["ucb_exploration"] = float(search_policy["ucb_exploration"])
    except (TypeError, ValueError) as exc:
        raise ValueError("config.agent.search_policy 的预算参数类型无效") from exc
    if search_policy["max_pending_per_arm"] < 1 or search_policy["ucb_exploration"] < 0:
        raise ValueError("config.agent.search_policy 的预算参数无效")

    quality = {**_QUALITY_DEFAULTS, **dict(agent.get("quality") or {})}
    for key in _QUALITY_DEFAULTS:
        try:
            quality[key] = float(quality[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"config.agent.quality.{key} 必须是数字") from exc
    return memory, field_selection, search_policy, quality

def parse_config(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("simulation", {}), dict):
        raise ValueError("config.simulation 必须是对象")  # noqa: TRY004
    agent = raw.get("agent")
    if not isinstance(agent, dict):
        raise ValueError("config.agent 必须是对象")  # noqa: TRY004
    incremental = dict(agent.get("incremental_value") or {})
    policy = IncrementalValuePolicy(
        mode=incremental.get("mode", "required_when_available"),
        max_abs_correlation=incremental.get("max_abs_correlation", 0.7),
        min_overlap=incremental.get("min_overlap", 60),
    )
    search_raw = dict(agent.get("search_policy") or {})
    research_raw = dict(agent.get("research_allocation") or {})
    search_max = int(search_raw.get("max_simulations", research_raw.get("max_simulations", 100)))
    research_max = int(research_raw.get("max_simulations", search_max))
    factory_raw = dict(agent.get("factory") or {})
    legacy_factory_max = int(factory_raw.get("max_simulations", search_max))
    factory_max = int(factory_raw.get("weekly_simulation_cap", legacy_factory_max))
    daily_factory_max = int(factory_raw.get("daily_simulation_cap", factory_max))
    if daily_factory_max > factory_max:
        raise ValueError("daily_simulation_cap 不得超过 weekly_simulation_cap")
    validate_budget_hierarchy(
        factory_max_simulations=factory_max,
        search_max_simulations=search_max,
        research_max_simulations=research_max,
    )
    search = SearchConfig(
        enabled=_as_bool(
            search_raw.get("enabled"), bool(research_raw),
            "config.agent.search_policy.enabled",
        ),
        max_simulations=search_max,
        validation_max_simulations=int(search_raw.get("validation_max_simulations", 0) or 0),
    )
    allocation = ResearchAllocation(
        max_simulations=research_max,
        maximum=copy.deepcopy(research_raw.get("maximum") or {}),
    )
    factory = FactoryConfig(
        max_simulations=factory_max,
        max_runtime_sec=int(factory_raw.get("max_runtime_sec", 86400)),
        daily_simulation_cap=daily_factory_max,
        weekly_simulation_cap=factory_max,
    )
    if search.max_simulations + search.validation_max_simulations > factory.max_simulations:
        raise ValueError("discovery + validation 预算不得超过 factory.max_simulations")
    memory, field_selection, search_policy, quality = _resolve_runtime_policies(agent)
    # Keep the validated typed factory model; the raw mapping remains
    # available only through ``runtime.factory`` for extensible legacy keys.
    factory_settings = dict(agent.get("factory") or {})
    factory_settings.setdefault("daily_simulation_cap", daily_factory_max)
    factory_settings.setdefault("weekly_simulation_cap", factory_max)
    research_allocation_raw = dict(agent.get("research_allocation") or {})
    statistical_policy = dict(agent.get("statistical_policy") or {})
    robustness_policy = dict(agent.get("robustness_policy") or {})
    yearly_policy = dict(agent.get("yearly_policy") or {})
    try:
        yearly_policy["min_years"] = int(yearly_policy.get("min_years", 2))
    except (TypeError, ValueError) as exc:
        raise ValueError("config.agent.yearly_policy.min_years 必须是整数") from exc
    if yearly_policy["min_years"] < 1:
        raise ValueError("config.agent.yearly_policy.min_years 必须大于 0")
    statistical_policy.setdefault("mode", "required_when_available")
    robustness_policy = {
        "min_sharpe_retention": 0.7,
        "min_fitness_retention": 0.6,
        "max_turnover_multiple": 1.5,
        "max_drawdown_multiple": 1.5,
        "require_checks_passed": True,
        **robustness_policy,
    }
    runtime = AgentRuntimeConfig(
        state_dir=str(agent.get("state_dir", ".wqb_state")),
        max_rounds=int(agent.get("max_rounds", 5)),
        candidates_per_round=int(agent.get("candidates_per_round", 6)),
        max_proposals_per_round=max(0, min(100, int(agent.get("max_proposals_per_round", 18)))),
        max_concurrent_sims=int(agent.get("max_concurrent_sims", 3)),
        research_integrity=_as_bool(
            agent.get("research_integrity"), False,
            "config.agent.research_integrity",
        ),
        correlation_refresh_window=max(1, int(agent.get("correlation_refresh_window", 256))),
        fields_per_discovery=int(agent.get("fields_per_discovery", 6)),
        pagination_limit=int(agent.get("pagination_limit", 50)),
        max_pagination_pages=int(agent.get("max_pagination_pages", 20)),
        poll_timeout_sec=float(agent.get("poll_timeout_sec", 1500)),
        replace_attempts=int(agent.get("replace_attempts", 3)),
        replace_backoff_sec=float(agent.get("replace_backoff_sec", 60)),
        trajectory_window=int(agent.get("trajectory_window", 100)),
        context_experiments=int(agent.get("context_experiments", 10)),
        fields_cache_ttl_sec=float(agent.get("fields_cache_ttl_sec", 7 * 24 * 3600)),
        max_field_alpha_count=(
            int(field_selection["max_alpha_count"])
            if field_selection.get("max_alpha_count") is not None else None
        ),
        factory=copy.deepcopy(factory_settings),
        research_allocation=copy.deepcopy(research_allocation_raw),
        search_policy=copy.deepcopy(search_policy),
        field_selection=copy.deepcopy(field_selection),
        submission_pool_filename=str(
            (agent.get("submission_pool") or {}).get("filename", "submission_pool.json")
        ),
        memory=copy.deepcopy(memory),
        quality=copy.deepcopy(quality),
        statistical_policy=copy.deepcopy(statistical_policy),
        robustness_policy=copy.deepcopy(robustness_policy),
        yearly_policy=copy.deepcopy(yearly_policy),
    )
    return AppConfig(
        simulation=copy.deepcopy(raw.get("simulation", {})),
        agent=copy.deepcopy(agent),
        search=search,
        research_allocation=allocation,
        factory=factory,
        incremental_value=IncrementalValueConfig(policy.mode, policy.max_abs_correlation, policy.min_overlap),
        validation=ValidationConfig(yearly_policy["min_years"]),
        statistical=StatisticalConfig(str((agent.get("statistical_policy") or {}).get("mode", "required_when_available"))),
        robustness=RobustnessConfig(
            float((agent.get("robustness_policy") or {}).get("min_sharpe_retention", 0.7)),
            float((agent.get("robustness_policy") or {}).get("min_fitness_retention", 0.6)),
        ),
        simulation_config=SimulationConfig({
            "neutralization": "SUBINDUSTRY",
            **copy.deepcopy(raw.get("simulation", {})),
        }),
        runtime=runtime,
    )


def normalize_config(config):
    """Normalize the one supported external config boundary."""
    if isinstance(config, AppConfig):
        return config
    return parse_config(config)
