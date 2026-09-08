"""Single, typed, fail-closed application configuration parse."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .incremental_policy import IncrementalValuePolicy
from .search_policy import validate_budget_hierarchy


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
    settings: dict = field(default_factory=dict)


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
    search_policy: dict = field(default_factory=dict)
    field_selection: dict = field(default_factory=dict)
    submission_pool_filename: str = "submission_pool.json"
    memory: dict = field(default_factory=dict)
    quality: dict = field(default_factory=dict)
    statistical_policy: dict = field(default_factory=dict)
    robustness_policy: dict = field(default_factory=dict)
    yearly_policy: dict = field(default_factory=dict)

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
    max_simulations: int = 300
    max_runtime_sec: int = 86400


@dataclass(frozen=True)
class AppConfig:
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
    factory_max = int(factory_raw.get("max_simulations", search_max))
    validate_budget_hierarchy(
        factory_max_simulations=factory_max,
        search_max_simulations=search_max,
        research_max_simulations=research_max,
    )
    search = SearchConfig(
        enabled=bool(search_raw.get("enabled", bool(research_raw))),
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
    )
    if search.max_simulations + search.validation_max_simulations > factory.max_simulations:
        raise ValueError("discovery + validation 预算不得超过 factory.max_simulations")
    field_selection = dict(agent.get("field_selection") or {})
    # Keep the validated typed factory model; the raw mapping remains
    # available only through ``runtime.factory`` for extensible legacy keys.
    factory_settings = dict(agent.get("factory") or {})
    research_allocation_raw = dict(agent.get("research_allocation") or {})
    search_policy = dict(agent.get("search_policy") or {})
    memory = dict(agent.get("memory") or {})
    quality = dict(agent.get("quality") or {})
    statistical_policy = dict(agent.get("statistical_policy") or {})
    robustness_policy = dict(agent.get("robustness_policy") or {})
    yearly_policy = dict(agent.get("yearly_policy") or {})
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
        research_integrity=bool(agent.get("research_integrity", False)),
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
        max_field_alpha_count=field_selection.get("max_alpha_count"),
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
        validation=ValidationConfig(int((agent.get("yearly_policy") or {}).get("min_years", 2)),),
        statistical=StatisticalConfig(str((agent.get("statistical_policy") or {}).get("mode", "required_when_available"))),
        robustness=RobustnessConfig(
            float((agent.get("robustness_policy") or {}).get("min_sharpe_retention", 0.7)),
            float((agent.get("robustness_policy") or {}).get("min_fitness_retention", 0.6)),
        ),
        simulation_config=SimulationConfig(copy.deepcopy(raw.get("simulation", {}))),
        runtime=runtime,
    )


def normalize_config(config):
    """Normalize the one supported external config boundary."""
    if isinstance(config, AppConfig):
        return config
    return parse_config(config)
