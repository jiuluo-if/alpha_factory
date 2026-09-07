"""Single, typed, fail-closed application configuration parse."""

from __future__ import annotations

from dataclasses import dataclass, field
import copy

from .incremental_policy import IncrementalValuePolicy
from .search_policy import validate_budget_hierarchy


@dataclass(frozen=True)
class IncrementalValueConfig:
    mode: str = "required_when_available"
    max_abs_correlation: float = 0.7
    min_overlap: int = 60


@dataclass(frozen=True)
class SearchConfig:
    enabled: bool = True
    max_simulations: int = 100
    validation_max_simulations: int = 4


@dataclass(frozen=True)
class FactoryConfig:
    max_simulations: int = 300
    max_runtime_sec: int = 86400


@dataclass(frozen=True)
class AppConfig:
    simulation: dict = field(default_factory=dict)
    agent: dict = field(default_factory=dict)
    search: SearchConfig = field(default_factory=SearchConfig)
    factory: FactoryConfig = field(default_factory=FactoryConfig)
    incremental_value: IncrementalValueConfig = field(default_factory=IncrementalValueConfig)

    def as_dict(self):
        return copy.deepcopy({"simulation": self.simulation, "agent": self.agent})


def parse_config(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("simulation", {}), dict):
        raise ValueError("config.simulation 必须是对象")
    agent = raw.get("agent")
    if not isinstance(agent, dict):
        raise ValueError("config.agent 必须是对象")
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
    factory = FactoryConfig(
        max_simulations=factory_max,
        max_runtime_sec=int(factory_raw.get("max_runtime_sec", 86400)),
    )
    return AppConfig(
        simulation=copy.deepcopy(raw.get("simulation", {})),
        agent=copy.deepcopy(agent),
        search=search,
        factory=factory,
        incremental_value=IncrementalValueConfig(policy.mode, policy.max_abs_correlation, policy.min_overlap),
    )
