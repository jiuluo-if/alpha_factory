"""Composition helpers for the existing Agent runtime."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass

from .candidate import CandidateBuilder
from .checkpoints import CheckpointStore
from .discovery import FieldDiscovery
from .memory import ExperienceMemory
from .evidence import load_evidence_cache
from .reflection import Reflector
from .simulator import Simulator
from .state import Trajectory
from .submission import SubmissionPool
from .trial_ledger import TrialLedger


@dataclass
class RuntimeComponents:
    """Already-resolved runtime objects; contains no orchestration logic."""

    search_policy: object
    memory: ExperienceMemory
    trajectory: Trajectory
    trial_ledger: TrialLedger
    builder: CandidateBuilder
    discovery: FieldDiscovery
    simulator: Simulator
    reflector: Reflector
    checkpoints: CheckpointStore
    submission_pool: SubmissionPool
    operator_reference: dict


def build_runtime_components(client, config, *, operator_reference, quality_policy,
                             field_selection):
    """Construct the existing runtime components from resolved AppConfig."""
    runtime = config.runtime
    search_cfg = {
        **runtime.search_policy,
        "enabled": config.search.enabled,
        "max_simulations": config.search.max_simulations,
        "validation_max_simulations": config.search.validation_max_simulations,
    }
    from .search_policy import SearchPolicy

    search_policy = SearchPolicy(search_cfg)
    state_dir = runtime.state_dir
    submission_pool = SubmissionPool(state_dir, filename=runtime.submission_pool_filename)
    memory = ExperienceMemory(
        state_dir,
        max_lessons=runtime.memory.get("max_lessons", 20),
        max_avoid=runtime.memory.get("max_avoid", 30),
        max_next=runtime.memory.get("max_next", 15),
        max_hypotheses=runtime.memory.get("max_hypotheses", 12),
        max_short_term=runtime.memory.get("max_short_term", 30),
        short_term_window=runtime.memory.get("short_term_window", 5),
        promote_hits=runtime.memory.get("promote_hits", 2),
        max_garbage=runtime.memory.get("max_garbage", 200),
        garbage_max_age_rounds=runtime.memory.get("garbage_max_age_rounds", 60),
        next_max_age_rounds=runtime.memory.get("next_max_age_rounds", 20),
        max_lineages=runtime.memory.get("max_lineages", 256),
        max_seen_expressions=runtime.memory.get("max_seen_expressions", 4096),
        max_used_hypotheses=runtime.memory.get("max_used_hypotheses", 256),
    )
    trajectory = Trajectory(
        max_len=runtime.trajectory_window,
        path=os.path.join(state_dir, "trajectory.jsonl"),
    )
    trial_ledger = TrialLedger(os.path.join(state_dir, "trial_ledger.jsonl"))
    builder = CandidateBuilder(
        neutralization=config.simulation.get("neutralization", "SUBINDUSTRY")
    )
    discovery = FieldDiscovery(
        client,
        pagination_limit=runtime.pagination_limit,
        max_pages=runtime.max_pagination_pages,
        cache_path=os.path.join(state_dir, "fields_cache.json"),
        cache_ttl_sec=runtime.fields_cache_ttl_sec,
        max_alpha_count=runtime.max_field_alpha_count,
        selection_mode=field_selection.get("mode", "semantic_random"),
        random_fraction=field_selection.get("random_fraction", 0.35),
        random_seed=field_selection.get("random_seed", "newwqb"),
    )
    simulator = Simulator(
        client,
        max_concurrent=runtime.max_concurrent_sims,
        poll_timeout_sec=runtime.poll_timeout_sec,
        replace_attempts=runtime.replace_attempts,
        replace_backoff_sec=runtime.replace_backoff_sec,
        yearly_policy={
            "min_sharpe": quality_policy.get("promising_sharpe", 0.0),
            "min_fitness": quality_policy.get("promising_fitness", 0.0),
            "max_turnover": quality_policy.get("max_turnover"),
            "min_years": runtime.yearly_policy.get("min_years", config.validation.yearly_min_years),
        },
    )
    reflector_keys = {
        "success_sharpe": "success_sharpe",
        "promising_sharpe": "promising_sharpe",
        "promising_fitness": "promising_fitness",
        "success_fitness": "success_fitness",
        "min_turnover": "min_turnover",
        "max_turnover": "max_turnover",
        "max_drawdown": "max_drawdown",
        "max_self_correlation": "self_correlation_limit",
    }
    reflector = Reflector(
        memory,
        **{target: quality_policy[key] for key, target in reflector_keys.items()
           if key in quality_policy},
    )
    reflector.evidence_cache = load_evidence_cache(state_dir)
    lock = threading.Lock()
    return RuntimeComponents(
        search_policy=search_policy,
        memory=memory,
        trajectory=trajectory,
        trial_ledger=trial_ledger,
        builder=builder,
        discovery=discovery,
        simulator=simulator,
        reflector=reflector,
        checkpoints=CheckpointStore(state_dir, lock=lock),
        submission_pool=submission_pool,
        operator_reference=operator_reference,
    )
