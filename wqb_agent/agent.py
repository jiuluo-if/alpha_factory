"""
ROLE: CORE
AGENT_RELEVANCE: HIGH
PURPOSE: Compose discovery, proposal validation, guarded Simulation execution,
recovery, and evidence updates through the existing runtime.
READ WHEN: changing experiment execution or recovery orchestration.
DO NOT USE FOR: choosing economic hypotheses or bypassing `research_api`.
"""

import json
import os
import re
import threading
import time

from .candidate import CandidateBuilder
from .artifacts import (
    atomic_write_json_if_changed,
    append_jsonl_if_unique,
    iter_jsonl_objects,
)
from .research_guard import ResearchLoopGuard, structural_family_key
from .search_policy import SearchPolicy, validate_budget_hierarchy
from .search_outcome import SearchOutcome, settle_search_outcome, extract_statistical_decision
from .research_evidence import classify_research
from .search_snapshot import SearchSnapshot
from .context import key_experiments, write_context
from .discovery import FieldDiscovery
from .diversity import extract_fields, is_redundant
from .evidence import (
    load_evidence_cache,
    overlay_cached_checks,
    refresh_self_correlation_cache,
)
from .expression import canonical_expression, submission_fingerprint
from .identity import candidate_identity
from .memory import ExperienceMemory
from .metrics import (
    check_pass,
    checks_passed,
    checks_ready_for_self_correlation_refresh,
    num,
)
from .proposal_contract import (
    CHILD_CHANGE_TYPES,
    EXPERIMENT_STAGES,
    MAX_PROPOSALS_PER_ROUND,
    PROPOSAL_EXPERIMENT_QS,
    RESEARCH_ROLES,
    SETTING_OVERRIDES,
    _expression_operators,
    _operator_reference,
    proposal_budget_cap,
    proposal_priority,
    validate_proposal,
    validate_vector_inputs,
)
from .reflection import Reflector
from .simulator import Simulator
from .state import Experiment, ResearchState, Trajectory
from .submission import SubmissionPool, latest_active_snapshot, self_correlation_evidence
from .submission import submission_eligibility
from .trial_ledger import TrialLedger
from .behavior import extract_behavior_series
from .alpha_pool import build_pool_snapshot
from .incremental_policy import IncrementalValuePolicy
from .incremental_value import build_incremental_value
from .validation_report import (
    build_validation_report,
    default_validation_plan,
)
from .config import AppConfig
from .research_evidence import ResearchEvidenceBundle
from .schema import (CREATED_BY_VERSION, CHECKPOINT_VERSION, VALIDATION_VERSION,
                      SIMULATION_RESULTS_VERSION, migrate_artifact)

SEED_HYPOTHESES = [
    {
        "id": "h-seed-reversal",
        "statement": "Short-term return reversal: stocks that rose sharply over the last 5 days tend to revert in the near term.",
        "tags": ["reversal", "return", "price", "short-term"],
        "direction": "reversal",
        "datasets": ["pv1", "pv13"],
    },
    {
        "id": "h-seed-analyst",
        "statement": "Analyst target-price revisions upward predict short-term outperformance.",
        "tags": ["analyst", "forecast", "revision", "target"],
        "direction": "long",
        "datasets": ["analyst4"],
    },
    {
        "id": "h-seed-option",
        "statement": "Stocks with elevated implied volatility earn lower forward returns.",
        "tags": ["option", "volatility", "implied", "risk"],
        "direction": "reversal",
        "datasets": ["option8", "option9"],
    },
    {
        "id": "h-seed-model",
        "statement": "High model risk scores predict lower forward returns.",
        "tags": ["model", "score", "risk", "composite"],
        "direction": "reversal",
        "datasets": ["model16", "model51"],
    },
    {
        "id": "h-seed-news",
        "statement": "Positive news sentiment predicts short-term positive returns.",
        "tags": ["news", "sentiment", "positive"],
        "direction": "long",
        "datasets": ["news18", "news12"],
    },
    {
        "id": "h-seed-fundamental",
        "statement": "Firms with strong earnings growth continue to outperform.",
        "tags": ["fundamental", "growth", "earning"],
        "direction": "long",
        "datasets": ["fundamental6", "fundamental2"],
    },
]

EXPLORATION_HYPOTHESES = [
    {"id": "h-explore-fund-cashflow", "statement": "Strong operating cash flow quality predicts outperformance.", "tags": ["cashflow", "operating", "quality"], "direction": "long", "datasets": ["fundamental6", "fundamental2"]},
    {"id": "h-explore-fund-leverage", "statement": "High leverage and debt burden predict lower forward returns.", "tags": ["debt", "leverage", "liability"], "direction": "reversal", "datasets": ["fundamental6", "fundamental2"]},
    {"id": "h-explore-fund-value", "statement": "Low valuation relative to book value or enterprise value predicts outperformance.", "tags": ["value", "book", "enterprise"], "direction": "long", "datasets": ["fundamental6", "fundamental2"]},
    {"id": "h-explore-fund-assets", "statement": "Efficient asset utilization and profitability predict outperformance.", "tags": ["asset", "profitability", "efficiency"], "direction": "long", "datasets": ["fundamental6", "fundamental2"]},
    {"id": "h-explore-news-attention", "statement": "Abnormally high news attention is followed by short-term reversal.", "tags": ["attention", "buzz", "count"], "direction": "reversal", "datasets": ["news18", "news12"]},
    {"id": "h-explore-news-novelty", "statement": "Novel company news contains information that persists into future returns.", "tags": ["novelty", "novel", "unique"], "direction": "long", "datasets": ["news18", "news12"]},
    {"id": "h-explore-news-relevance", "statement": "Highly relevant company-specific news predicts short-term returns.", "tags": ["relevance", "relevant", "company"], "direction": "long", "datasets": ["news18", "news12"]},
    {"id": "h-explore-news-volume", "statement": "Extreme news volume reflects overreaction and predicts reversal.", "tags": ["volume", "story", "article"], "direction": "reversal", "datasets": ["news18", "news12"]},
]


class Agent:
    def __init__(self, client, config):
        self.client = client
        typed_config = config if isinstance(config, AppConfig) else None
        if typed_config is not None:
            config = config.as_dict()
        self.simulation_settings = config["simulation"]
        agent_cfg = config["agent"]
        self.state_dir = agent_cfg.get("state_dir", ".wqb_state")
        self.max_rounds = agent_cfg.get("max_rounds", 5)
        self.factory_config = dict(agent_cfg.get("factory") or {})
        self.candidates_per_round = agent_cfg.get("candidates_per_round", 6)
        # Keep ordinary runs at the historical 18 cap, while allowing the
        # unattended factory to opt into a bounded 100-proposal batch.
        configured_batch = self.factory_config.get(
            "max_proposals_per_round", agent_cfg.get("max_proposals_per_round", 18)
        )
        try:
            self.max_proposals_per_round = max(0, min(100, int(configured_batch)))
        except (TypeError, ValueError):
            self.max_proposals_per_round = 18
        self.research_allocation = agent_cfg.get("research_allocation") or {}
        self.research_integrity = bool(agent_cfg.get("research_integrity", False))
        search_cfg = dict(agent_cfg.get("search_policy") or {})
        search_cfg.setdefault("enabled", bool(self.research_allocation))
        if "max_simulations" not in search_cfg:
            search_cfg["max_simulations"] = self.research_allocation.get(
                "max_simulations", 100
            )
        validate_budget_hierarchy(
            factory_max_simulations=self.factory_config.get(
                "max_simulations", search_cfg["max_simulations"]
            ),
            search_max_simulations=search_cfg["max_simulations"],
            research_max_simulations=self.research_allocation.get(
                "max_simulations", search_cfg["max_simulations"]
            ),
        )
        search_cfg.setdefault(
            "validation_max_simulations",
            (self.research_allocation.get("maximum") or {}).get("VALIDATION", 0),
        )
        self.search_policy = SearchPolicy(search_cfg)
        self.fields_per_discovery = agent_cfg.get("fields_per_discovery", 6)
        self.pagination_limit = agent_cfg.get("pagination_limit", 50)
        self.max_pagination_pages = agent_cfg.get("max_pagination_pages", 20)
        self.poll_timeout_sec = agent_cfg.get("poll_timeout_sec", 1500)
        self.context_experiments = agent_cfg.get("context_experiments", 10)
        try:
            self.correlation_refresh_window = max(
                1, int(agent_cfg.get("correlation_refresh_window", 256))
            )
        except (TypeError, ValueError):
            self.correlation_refresh_window = 256
        self.quality_policy = agent_cfg.get("quality", {})
        self.statistical_policy = dict(agent_cfg.get("statistical_policy") or {})
        self.statistical_policy.setdefault("mode", "required_when_available")
        self.robustness_policy = dict(agent_cfg.get("robustness_policy") or {
            "min_sharpe_retention": 0.7,
            "min_fitness_retention": 0.6,
            "max_turnover_multiple": 1.5,
            "max_drawdown_multiple": 1.5,
            "require_checks_passed": True,
        })
        if typed_config is not None:
            self.incremental_policy = IncrementalValuePolicy(
                typed_config.incremental_value.mode,
                typed_config.incremental_value.max_abs_correlation,
                typed_config.incremental_value.min_overlap,
            )
        else:
            incremental_cfg = dict(agent_cfg.get("incremental_value") or {})
            self.incremental_policy = IncrementalValuePolicy(
                mode=incremental_cfg.get("mode", "required_when_available"),
                max_abs_correlation=incremental_cfg.get("max_abs_correlation", 0.7),
                min_overlap=incremental_cfg.get("min_overlap", 60),
            )
        field_selection = agent_cfg.get("field_selection") or {}
        self.max_field_alpha_count = field_selection.get("max_alpha_count")
        operator_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "reference", "OPERATORS_CHEATSHEET.md"))
        self.operator_reference = _operator_reference(operator_path)
        self.submission_pool = SubmissionPool(
            self.state_dir,
            filename=(agent_cfg.get("submission_pool") or {}).get("filename", "submission_pool.json"),
        )

        mem_cfg = agent_cfg.get("memory", {})
        self.memory = ExperienceMemory(
            self.state_dir,
            max_lessons=mem_cfg.get("max_lessons", 20),
            max_avoid=mem_cfg.get("max_avoid", 30),
            max_next=mem_cfg.get("max_next", 15),
            max_hypotheses=mem_cfg.get("max_hypotheses", 12),
            max_short_term=mem_cfg.get("max_short_term", 30),
            short_term_window=mem_cfg.get("short_term_window", 5),
            promote_hits=mem_cfg.get("promote_hits", 2),
            max_garbage=mem_cfg.get("max_garbage", 200),
            garbage_max_age_rounds=mem_cfg.get("garbage_max_age_rounds", 60),
            next_max_age_rounds=mem_cfg.get("next_max_age_rounds", 20),
            max_lineages=mem_cfg.get("max_lineages", 256),
            max_seen_expressions=mem_cfg.get("max_seen_expressions", 4096),
            max_used_hypotheses=mem_cfg.get("max_used_hypotheses", 256),
        )
        self.trajectory = Trajectory(
            max_len=agent_cfg.get("trajectory_window", 100),
            path=os.path.join(self.state_dir, "trajectory.jsonl"),
        )
        self.trial_ledger = TrialLedger(
            os.path.join(self.state_dir, "trial_ledger.jsonl")
        )
        self.builder = CandidateBuilder(
            neutralization=self.simulation_settings.get("neutralization", "SUBINDUSTRY")
        )
        self.alpha_factory = self.builder.factory
        self.discovery = FieldDiscovery(
            self.client,
            pagination_limit=self.pagination_limit,
            max_pages=self.max_pagination_pages,
            cache_path=os.path.join(self.state_dir, "fields_cache.json"),
            cache_ttl_sec=agent_cfg.get("fields_cache_ttl_sec", 7 * 24 * 3600),
            max_alpha_count=self.max_field_alpha_count,
            selection_mode=field_selection.get("mode", "semantic_random"),
            random_fraction=field_selection.get("random_fraction", 0.35),
            random_seed=field_selection.get("random_seed", "newwqb"),
        )
        self.simulator = Simulator(
            self.client,
            max_concurrent=agent_cfg.get("max_concurrent_sims", 3),
            poll_timeout_sec=self.poll_timeout_sec,
            replace_attempts=agent_cfg.get("replace_attempts", 3),
            replace_backoff_sec=agent_cfg.get("replace_backoff_sec", 60),
            yearly_policy={
                "min_sharpe": (self.quality_policy or {}).get("promising_sharpe", 0.0),
                "min_fitness": (self.quality_policy or {}).get("promising_fitness", 0.0),
                "max_turnover": (self.quality_policy or {}).get("max_turnover"),
                "min_years": (agent_cfg.get("yearly_policy") or {}).get("min_years", 2),
            },
        )
        _REFLECTOR_KWARGS = {
            "success_sharpe": "success_sharpe",
            "promising_sharpe": "promising_sharpe",
            "promising_fitness": "promising_fitness",
            "success_fitness": "success_fitness",
            "min_turnover": "min_turnover",
            "max_turnover": "max_turnover",
            "max_drawdown": "max_drawdown",
            "max_self_correlation": "self_correlation_limit",
        }
        reflector_quality = {
            _REFLECTOR_KWARGS[key]: value
            for key, value in self.quality_policy.items()
            if key in _REFLECTOR_KWARGS
        }
        self.reflector = Reflector(self.memory, **reflector_quality)
        self.reflector.evidence_cache = load_evidence_cache(self.state_dir)
        self._loaded = False
        self._last_round_skipped = False
        # In-process accounting hook for the long-running factory.  It lets
        # the session release candidates rejected by preflight without a
        # second validation path or a second ledger.
        self.last_run_stats = {"accepted": 0, "rejected": 0, "skipped": 0}
        self._checkpoint_lock = threading.Lock()

    # ------------------------------------------------------------ running

    def run(self, max_rounds=None):
        raise RuntimeError(
            "自动候选路径已退役：生产研究只能使用 --suggest 后再 --run-proposals。"
        )

    def next_round_no(self):
        """Continue from the last completed round (never restart from zero)."""
        self._ensure_loaded()
        rounds = [e.round for e in self.trajectory.experiments]
        return (max(rounds) + 1) if rounds else 1

    EPOCH_START = 619  # r619 起启用新纪元标签（用户 2026-08-22 政策）

    def epoch_label(self, round_no):
        """New-era round label: 'rb' + hexadecimal sequence.
        r619 -> rb0, r620 -> rb1, ... r634 -> rbf, r635 -> rb10."""
        seq = max(int(round_no) - self.EPOCH_START, 0)
        return f"rb{format(seq, 'x')}"

    # ------------------------------------------------- LLM-driven research

    def run_suggestion_round(self, round_no=None):
        """Phase 1 of LLM-driven research: form a hypothesis, discover real
        fields from BRAIN, and export a suggestion bundle for the agent (LLM)
        to read. No simulation happens here."""
        self._ensure_loaded()
        round_no = round_no or self.next_round_no()
        # 2026-08-22 用户政策变更：删除字段级全量排除机制。字段允许跨轮重复
        # 进入 discovery；重复防护收敛到 run_proposals 的表达式级去重
        # （精确/等价表达式与同族变体不复跑），以及模拟前与 ACTIVE/已提交
        # Alpha 的相关性预检与噪点结构审计。

        research_space = self._form_research_space(round_no)
        research_space = self._rotate_stalled_research_space(
            research_space, round_no
        )
        research_space["_round"] = round_no
        fields = self.discovery.discover(
            research_space, target_count=self.fields_per_discovery
        )
        # A research space can legitimately have no eligible fields after the
        # current alphaCount gate.  Do not leave the persistent suggestion
        # phase stuck on the same empty round; try the next declared space
        # while keeping the statement itself non-economic until discovery
        # returns usable descriptions.
        if not fields:
            fallback_templates = list(EXPLORATION_HYPOTHESES) + list(SEED_HYPOTHESES)
            for template in fallback_templates:
                if template.get("id") == research_space.get("id"):
                    continue
                candidate = {
                    "id": template.get("id", f"space-r{round_no}"),
                    "statement": research_space["statement"],
                    "tags": list(template.get("tags") or []),
                    "datasets": list(template.get("datasets") or []),
                    "parent_best": None,
                    "_round": round_no,
                }
                candidate_fields = self.discovery.discover(
                    candidate, target_count=max(self.fields_per_discovery * 4, 50)
                )
                candidate_fields = candidate_fields[: self.fields_per_discovery]
                if candidate_fields:
                    research_space = candidate
                    fields = candidate_fields
                    print(
                        "[DISCOVERY FALLBACK] 初始研究空间无合格字段，"
                        f"切换到数据集提示: {candidate['datasets']}"
                    )
                    break
        if research_space.get("parent_best") and self._trusted_current_best():
            fields = self._ensure_best_field(fields)

        bundle = {
            "round_no": round_no,
            "epoch_label": self.epoch_label(round_no),
            "research_space": research_space,
            "fields": [
                {
                    "id": f["id"],
                    "name": f.get("name", ""),
                    "description": f.get("description", ""),
                    "dataset": f.get("dataset"),
                    "type": f.get("type"),
                    "coverage": f.get("coverage"),
                    "frequency": f.get("frequency"),
                    "alpha_count": f.get("alpha_count"),
                    "semantic_status": f.get("semantic_status", "UNKNOWN"),
                    "field_source": f.get("field_source") or self.discovery.source_provenance(),
                }
                for f in fields
            ],
            "context": self.memory.context(
                recent_experiments=key_experiments(
                    self.trajectory.recent(self.context_experiments * 2)
                )
            ),
            "simulation_settings": self.simulation_settings,
            "field_source": self.discovery.source_provenance(),
            "operator_reference": self.operator_reference,
            "alpha_templates": self.alpha_factory.catalog(),
            "research_guard": ResearchLoopGuard(self.trajectory.experiments).snapshot(),
            "field_selection": {
                "max_alpha_count": self.max_field_alpha_count,
                "excluded_high_usage": self.discovery.last_excluded_high_usage,
            },
        }
        os.makedirs(self.state_dir, exist_ok=True)
        path = os.path.join(self.state_dir, "suggestions.json")
        atomic_write_json_if_changed(path, bundle)
        print(f"\n=== Suggestion round {round_no} ({self.epoch_label(round_no)}) ===")
        print(f"Research space: {research_space['statement']}")
        print(f"Fields ({len(fields)}): {[f['id'] for f in fields]}")
        print(f"Bundle written: {path}")
        print("-> read suggestions.json + context.md, write proposals.json, "
              "then run --run-proposals")
        return bundle

    def optimizable_signal_records(self, limit=128):
        """Return a bounded view of completed signals for factory optimization."""
        records = []
        for exp in reversed(self.trajectory.recent(limit)):
            if exp.status != "DONE" or not exp.metrics:
                continue
            # Older trajectory rows predate the auditable metadata needed for
            # a CHILD proposal; they remain evidence but are not auto-mutated.
            if not exp.field_analysis or not exp.field_understanding:
                continue
            records.append(exp.to_dict())
        return records

    def _rotate_stalled_research_space(self, research_space, round_no,
                                       window=40, concentration=0.8):
        # RESEARCH_POLICY:
        # Heuristic only. Not a BRAIN invariant; an external research agent
        # may override or bypass this direction choice.
        """Avoid spending another round on a recently exhausted dataset.

        A research-space hypothesis can remain valid while its current
        dataset produces only weak baselines.  Continuing to select fields
        from that same dataset then consumes simulation budget without adding
        a new experiment family.  This guard is deliberately based only on
        the bounded recent trajectory window and changes no persisted state.
        """
        if not isinstance(research_space, dict):
            return research_space
        datasets = {
            str(value) for value in (research_space.get("datasets") or [])
            if isinstance(value, (str, int)) and str(value).strip()
        }
        if not datasets:
            return research_space
        recent = self.trajectory.recent(window)
        observed = [
            str(dataset)
            for experiment in recent
            for dataset in (experiment.datasets or [])
            if isinstance(dataset, (str, int)) and str(dataset).strip()
        ]
        if not observed:
            return research_space
        counts = {}
        for dataset in observed:
            counts[dataset] = counts.get(dataset, 0) + 1
        dominant, dominant_count = max(counts.items(), key=lambda item: item[1])
        if dominant not in datasets or dominant_count / len(observed) < concentration:
            return research_space

        candidates = list(EXPLORATION_HYPOTHESES) + list(SEED_HYPOTHESES)
        for offset in range(len(candidates)):
            candidate = candidates[(int(round_no) + offset) % len(candidates)]
            candidate_datasets = {
                str(value) for value in (candidate.get("datasets") or [])
                if isinstance(value, (str, int)) and str(value).strip()
            }
            if not candidate_datasets or candidate_datasets & set(counts):
                continue
            rotated = dict(candidate)
            rotated["statement"] = research_space.get("statement") or candidate.get("statement")
            rotated["parent_best"] = None
            rotated["rotation_reason"] = (
                f"recent dataset concentration: {dominant} "
                f"{dominant_count}/{len(observed)}"
            )
            return rotated
        return research_space

    def run_proposals(self, path=None, allow_unresolved_checkpoint=False):
        # MECHANISM_INVARIANT:
        # This is the guarded execution boundary. Keep preflight, dedup,
        # checkpoint, and unknown-write handling fail-closed.
        """Phase 2 of LLM-driven research: execute the agent's proposals
        through real BRAIN simulation, then reflect and update memory."""
        self.last_run_stats = {"accepted": 0, "rejected": 0, "skipped": 0}
        self._ensure_loaded()
        path = path or os.path.join(self.state_dir, "proposals.json")
        if not os.path.exists(path):
            print(f"No proposals file at {path}.")
            return None
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError) as exc:
            print(f"[PROPOSALS ERROR] {path} 无法读取或不是有效 JSON：{exc}")
            return None
        if not isinstance(payload, dict):
            print(f"[PROPOSALS ERROR] {path} 顶层必须是对象（含 round_no/proposals）。")
            return None

        raw_round_no = payload.get("round_no")
        if raw_round_no is None:
            round_no = self.next_round_no()
        elif isinstance(raw_round_no, bool):
            print("[PROPOSALS ERROR] round_no 必须是正整数；未执行任何提案。")
            return None
        else:
            try:
                round_no = int(raw_round_no)
            except (TypeError, ValueError):
                print("[PROPOSALS ERROR] round_no 必须是正整数；未执行任何提案。")
                return None
            if round_no <= 0:
                print("[PROPOSALS ERROR] round_no 必须是正整数；未执行任何提案。")
                return None
        foreign_checkpoint = self._unfinished_checkpoint_except(round_no)
        if foreign_checkpoint and not allow_unresolved_checkpoint:
            print(
                f"[CHECKPOINT BLOCKED] 存在未完成 {os.path.basename(foreign_checkpoint)}；"
                "必须先以原 proposals.json 恢复，禁止开启新轮。"
            )
            return None
        if foreign_checkpoint and allow_unresolved_checkpoint:
            print(
                f"[FORCE NEW ROUND] 保留未完成 {os.path.basename(foreign_checkpoint)} "
                "及其原 progress_url；按用户明确授权开启新轮。"
            )
        checkpoint_path = self._proposal_checkpoint_path(round_no)
        checkpoint = self._load_proposal_checkpoint(round_no)
        if os.path.exists(checkpoint_path) and checkpoint is None:
            # A malformed or mismatched checkpoint is still a recovery
            # boundary. Never treat it as an absent checkpoint and issue a
            # fresh POST for the same round.
            print(
                f"[CHECKPOINT ERROR] {checkpoint_path} 无法解析或轮次不匹配；"
                "保留原文件，需先人工对账。"
            )
            return None
        if checkpoint and not checkpoint.get("complete"):
            return self._resume_proposal_checkpoint(checkpoint)
        if checkpoint and checkpoint.get("complete"):
            print(f"[CHECKPOINT COMPLETE] round {round_no} 已完成；不重新派发其中的 proposals。")
            return None
        proposal_list = payload.get("proposals") or []
        if not isinstance(proposal_list, list):
            print("[PROPOSALS ERROR] proposals 必须是数组；未执行任何提案。")
            return None
        if not proposal_list:
            print("No proposals in file; nothing to run.")
            return None

        hypothesis = payload.get("hypothesis")
        if hypothesis is None:
            hypothesis = {
                "id": f"h-llm-r{round_no}",
                "statement": payload.get("statement", "LLM-proposed research direction"),
                "tags": ["llm", "proposal"],
                "direction": "long",
                "datasets": [],
            }
        elif not isinstance(hypothesis, dict):
            print("[PROPOSALS ERROR] hypothesis 必须是对象；未执行任何提案。")
            return None
        else:
            hypothesis = dict(hypothesis)
        hypothesis["_round"] = round_no

        terminal_expressions, terminal_fingerprints = self._terminal_identities(
            [item.get("expression") for item in proposal_list
             if isinstance(item, dict)]
        )
        local_seen = set(terminal_expressions)
        local_seen.update(terminal_fingerprints)
        # 文件内部重复也要跳过；settings 变体仍保留为独立、可审计实验。
        pending = [
            e for e in self.trajectory.experiments
            if e.status in ("UNKNOWN", "PENDING")
        ]
        if pending:
            print(
                f"[NOTE] {len(pending)} 个历史实验未完成（UNKNOWN/PENDING），"
                f"其表达式已豁免去重，可在本轮重新提交。"
            )
        fresh = []
        skipped = []
        rejected = []
        diversity_rejected = []
        settings_rejected = []
        loop_guard = ResearchLoopGuard(self.trajectory.experiments)
        cached_field_types, cached_profiles = self._read_field_cache()
        field_types = self._known_field_types(
            payload, cached_field_types=cached_field_types
        )
        # AGENTS.md permits fields from the current discovery bundle or the
        # verified on-disk field library.  Keep current discovery authoritative
        # while supplementing it with cache profiles for manually reviewed
        # proposals from an unselected dataset.
        discovered_profiles = {}
        for field in (payload.get("suggestion_fields") or payload.get("fields") or []):
            if isinstance(field, dict) and field.get("id"):
                discovered_profiles[str(field["id"])] = field
        for field_id, field in cached_profiles.items():
            discovered_profiles.setdefault(field_id, field)
        proposal_field_profiles = list(discovered_profiles.values())
        completed_parent_index = self.trajectory.find_completed_expressions(
            [item.get("parent_expression") for item in proposal_list
             if isinstance(item, dict)]
        )
        candidate_event_records = []
        for raw_proposal in proposal_list:
            if not isinstance(raw_proposal, dict):
                malformed = {"round": round_no, "expression": str(raw_proposal or "")}
                malformed["candidate_id"] = candidate_identity(malformed, round_no=round_no)
                candidate_event_records.append(malformed)
                self._record_trial_phase(malformed, "candidate_generated", outcome="CONSIDERED")
                self._record_candidate_rejection(malformed, "schema", "NOT_OBJECT", "proposal 必须是对象")
                rejected.append((str(raw_proposal), ["proposal 必须是对象"]))
                continue
            # Keep input immutable on disk, but carry suggestion provenance
            # into the durable experiment/checkpoint record.
            p = dict(raw_proposal)
            p["round"] = round_no
            p["candidate_id"] = candidate_identity(p, round_no=round_no)
            candidate_event_records.append(p)
            self._record_trial_phase(p, "candidate_generated", outcome="CONSIDERED")
            source = p.get("field_source") or payload.get("field_source")
            if source is None:
                for profile in discovered_profiles.values():
                    if profile.get("field_source"):
                        source = profile["field_source"]
                        break
            if source is not None:
                p["field_source"] = source
            expression = (p.get("expression") or "").strip()
            if not expression:
                self._record_candidate_rejection(p, "schema", "MISSING_EXPRESSION", "expression 不能为空")
                continue
            # 2026-08-22 用户政策（F>=10% 冲刺）：携带授权 settings 覆盖
            # （universe/truncation/decay）的提案按「settings+表达式」组合键
            # 去重——同一表达式在不同授权设置下是新实验；无 settings 的提案
            # 维持裸表达式去重不变。
            settings_override = p.get("settings")
            if settings_override:
                try:
                    effective_settings = self._proposal_settings(settings_override)
                except ValueError:
                    # Preserve the later settings-specific diagnostic; this
                    # fallback only prevents duplicate malformed rows within
                    # the same inbox from multiplying work.
                    effective_settings = settings_override
                if isinstance(effective_settings, dict):
                    dedup_key = "settings::" + submission_fingerprint(
                        expression, effective_settings
                    )
                else:
                    dedup_key = (
                        "settings::" + json.dumps(settings_override, sort_keys=True)
                        + "::" + canonical_expression(expression)
                    )
                if dedup_key in local_seen:
                    self._record_candidate_rejection(p, "duplicate", "DUPLICATE_LOCAL", "同一表达式与设置已在本批出现")
                    skipped.append(expression)
                    continue
                local_seen.add(dedup_key)
            elif canonical_expression(expression) in local_seen:
                self._record_candidate_rejection(p, "duplicate", "DUPLICATE_LOCAL", "同一规范化表达式已在本批出现")
                skipped.append(expression)
                continue
            else:
                local_seen.add(canonical_expression(expression))
            ok, problems = validate_proposal(
                p,
                discovered_fields=proposal_field_profiles,
                strict_experiment=True,
                operator_reference=self.operator_reference,
                require_research_evidence=bool(self.research_allocation),
                require_economic_integrity=self.research_integrity,
                max_alpha_count=self.max_field_alpha_count,
            )
            type_ok, type_problems = validate_vector_inputs(p, field_types)
            if not type_ok:
                problems.extend(type_problems)
                ok = False
            if not ok:
                self._record_candidate_rejection(p, "schema", "PREFLIGHT_REJECTED", "; ".join(problems))
                rejected.append((expression, problems))
                continue
            if self.research_allocation:
                if not (
                    isinstance(source, dict)
                    and source.get("kind") in {"local_catalog", "brain_api"}
                    and "snapshot_date" in source
                ):
                    self._record_candidate_rejection(p, "field_source", "INVALID_FIELD_SOURCE", "field_source 必须声明 local_catalog/brain_api 及 snapshot_date")
                    rejected.append((expression, [
                        "field_source 必须声明 local_catalog/brain_api 及 snapshot_date"
                    ]))
                    continue
                role = p.get("research_role")
                if role not in RESEARCH_ROLES:
                    self._record_candidate_rejection(p, "research_guard", "INVALID_RESEARCH_ROLE", "research_role 必须是 EXPLORE/EXPLOIT/VALIDATION")
                    rejected.append((expression, [
                        "research_role 必须是 EXPLORE/EXPLOIT/VALIDATION；FINAL_CHECK 是结果后的检查动作"
                    ]))
                    continue
                parent = self._completed_parent(
                    p.get("parent_expression"), completed_parent_index
                )
                if role == "EXPLORE" and p.get("experiment_stage") != "BASELINE":
                    self._record_candidate_rejection(p, "research_guard", "EXPLORE_STAGE_MISMATCH", "EXPLORE 必须是新的 BASELINE")
                    rejected.append((expression, ["EXPLORE 必须是新的 BASELINE"])); continue
                if role in {"EXPLOIT", "VALIDATION"} and parent is None:
                    self._record_candidate_rejection(p, "research_guard", "PARENT_NOT_DONE", f"{role} 缺少已完成 parent_expression")
                    rejected.append((expression, [
                        f"{role} 只能引用已完成的 parent_expression，不能在同一批提案中预支结果"
                    ])); continue
                if role == "VALIDATION":
                    parent_verdict = self.reflector._classify(parent).get("label")
                    if parent_verdict not in {"SUCCESS", "SUSPICIOUS_HIGH_SIGNAL"}:
                        self._record_candidate_rejection(p, "research_guard", "PARENT_QUALITY_FAIL", "VALIDATION 的 parent 未通过质量门")
                        rejected.append((expression, [
                            "VALIDATION 的 parent 必须已通过质量门或为需审计的高信号"
                        ])); continue
            lineage_id = p.get("lineage_id") or p.get("parent_expression") or hypothesis.get("id")
            lineage_decision = self.memory.lineage_decision(lineage_id)
            # STOP ends further exploration.  It permits only one explicitly
            # labelled robustness check to distinguish a knife-edge result
            # from a durable mechanism; KILL blocks every further spend.
            blocked = (
                lineage_decision == "KILL"
                or (lineage_decision == "STOP" and p.get("experiment_stage") != "ROBUSTNESS")
            )
            if blocked:
                self._record_candidate_rejection(p, "lineage", f"LINEAGE_{lineage_decision}", f"lineage {lineage_id!r} 已标记 {lineage_decision}")
                diversity_rejected.append((
                    expression,
                    [f"lineage {lineage_id!r} 已标记 {lineage_decision}，不再消耗探索预算"],
                ))
                continue
            guard_ok, guard_reason = loop_guard.check(
                p, default_lineage=p.get("lineage_id") or hypothesis.get("id")
            )
            if not guard_ok:
                self._record_candidate_rejection(p, "research_guard", "LOOP_GUARD", guard_reason)
                diversity_rejected.append((expression, [guard_reason]))
                continue
            try:
                effective_settings = self._proposal_settings(p.get("settings"))
            except ValueError as exc:
                self._record_candidate_rejection(p, "settings", "INVALID_SETTINGS", str(exc))
                settings_rejected.append((expression, [str(exc)]))
                continue
            p.setdefault(
                "proposal_id",
                "p-" + submission_fingerprint(expression, effective_settings)[:16],
            )
            fresh.append(p)
        # Each field family gets a core candidate plus at most one explicit
        # perturbation.  This blocks window sweeps while still permitting a
        # falsification test.  Remaining candidates are ordered by a small,
        # declared information-value heuristic and capped by the config.
        diverse = []
        diverse_records = []
        family_counts = {}
        allocation_counts = {role: 0 for role in RESEARCH_ROLES}
        historical_pool = list(self.trajectory.experiments)
        role_max = (self.research_allocation.get("maximum", {})
                    if self.research_allocation else {})
        for p in fresh:
            self.search_policy.annotate(p, historical_pool + diverse_records)
        for p in sorted(
            fresh,
            key=lambda item: (self.search_policy.priority(item), proposal_priority(item)),
            reverse=True,
        ):
            role = p.get("research_role")
            if role in role_max and allocation_counts.get(role, 0) >= int(role_max[role]):
                self._record_candidate_rejection(p, "diversity", "ARM_ROLE_CAP", f"{role} 已达到本轮动态上限 {role_max[role]}")
                diversity_rejected.append((
                    p["expression"], [f"{role} 已达到本轮动态上限 {role_max[role]}"]
                ))
                continue
            fields = extract_fields(p["expression"], p.get("fields") or [])
            # External adapters are allowed to omit template metadata.  Do
            # not let a different sibling field turn an identical operator /
            # window skeleton into a new family and consume the whole batch.
            # Prefer the explicit template family when present; otherwise
            # use the field-independent structural key.
            family = p.get("template_family")
            if not isinstance(family, (str, int)) or not str(family).strip():
                family = structural_family_key(p["expression"], p.get("fields") or fields)
            family = str(family)
            if family_counts.get(family, 0) >= 2:
                self._record_candidate_rejection(p, "diversity", "DIVERSITY_FAMILY_CAP", f"signal family {family!r} 已有两个实验")
                diversity_rejected.append((
                    p["expression"],
                    [f"signal family {family!r} 已有两个实验，拒绝参数挖掘"],
                ))
                continue
            record = {"expression": p["expression"], "fields_used": fields}
            # Keep the exact same simple redundancy rule, but retain the
            # already-extracted records instead of rebuilding/parsing the
            # entire accepted prefix for every candidate; pairwise similarity
            # checks remain necessary, but repeated field parsing is removed.
            redundant, _ = is_redundant(record, diverse_records)
            if redundant:
                self._record_candidate_rejection(p, "diversity", "DIVERSITY_REDUNDANT", "与本轮更高优先级候选近重复")
                diversity_rejected.append((p["expression"], ["与本轮更高优先级候选近重复"]))
                continue
            if not self.search_policy.accept(p):
                allocator = self.search_policy.allocator
                budget_exhausted = allocator.consumed_budget >= allocator.total_budget
                self._record_candidate_rejection(
                    p,
                    "simulation_budget" if budget_exhausted else "arm",
                    "SIMULATION_BUDGET" if budget_exhausted else "ARM_ADMISSION",
                    "Simulation budget 已耗尽" if budget_exhausted else "同一 dataset/mechanism research arm 已有待定或预留预算",
                )
                diversity_rejected.append((
                    p["expression"],
                    ["同一 dataset/mechanism research arm 已有待定或预留预算"],
                ))
                continue
            self._record_trial_phase(p, "candidate_admitted", outcome="ADMITTED")
            family_counts[family] = family_counts.get(family, 0) + 1
            if role in allocation_counts:
                allocation_counts[role] += 1
            diverse.append(p)
            diverse_records.append(record)
        try:
            allocation_cap = int(
                self.research_allocation.get("max_simulations", self.candidates_per_round)
            )
        except (TypeError, ValueError):
            allocation_cap = self.candidates_per_round
        budget_cap = proposal_budget_cap(
            self.candidates_per_round, allocation_cap,
            hard_cap=self.max_proposals_per_round,
        )
        budget_rejected = diverse[budget_cap:]
        fresh = diverse[:budget_cap]
        # Local batch trimming releases admission only; it must not consume
        # Simulation budget or enter UCB's evaluated denominator.
        for p in budget_rejected:
            self._record_candidate_rejection(p, "batch_budget", "BATCH_CAP", "本地 batch cap 淘汰，未承诺 Simulation")
            self.search_policy.release(p, status="SKIPPED_LOCAL")
        if self.research_allocation:
            role_max = self.research_allocation.get("maximum", {})
            role_counts = {role: 0 for role in RESEARCH_ROLES}
            for p in fresh:
                role = p.get("research_role")
                if role in role_counts:
                    role_counts[role] += 1
            role_errors = []
            for role, maximum in role_max.items():
                if role_counts.get(role, 0) > int(maximum):
                    role_errors.append(
                        f"{role} 有 {role_counts.get(role, 0)}，超过动态上限 {maximum}"
                    )
            if role_errors:
                print("[ALLOCATION BLOCKED] 本轮不提交 Simulation：")
                for problem in role_errors:
                    print(f"  - {problem}")
                return None
            print(
                "[ALLOCATION] 动态分配 "
                + ", ".join(f"{role}={role_counts.get(role, 0)}"
                             for role in sorted(RESEARCH_ROLES))
            )
        committed = []
        for p in fresh:
            if self.search_policy.commit(p):
                committed.append(p)
                self._record_trial_phase(p, "simulation_committed", outcome="COMMITTED")
            else:
                self._record_candidate_rejection(p, "simulation_budget", "BUDGET_COMMIT_FAILED", "最终执行集合无法承诺 Simulation budget")
                # A failed final commit is a local admission failure.  Close
                # the provisional reservation immediately so it cannot
                # occupy an arm slot until process restart.
                self.search_policy.release(p, status="SKIPPED_LOCAL")
        if len(committed) != len(fresh):
            fresh = committed
        if diversity_rejected:
            print(f"[DIVERSITY BLOCKED] {len(diversity_rejected)} 个提案未进入模拟：")
            for expr, problems in diversity_rejected:
                print(f"  - {expr[:70]} -> {'; '.join(problems)}")
        if budget_rejected:
            print(
                f"[BUDGET BLOCKED] 仅执行优先级最高的 {budget_cap} 个提案；"
                f"{len(budget_rejected)} 个未消耗 simulation。"
            )
        print(f"\n=== Round {round_no} (LLM proposals) ===")
        print(f"Hypothesis: {hypothesis['statement']}")
        if skipped:
            print(f"skipped already-simulated: {len(skipped)}")
        if rejected:
            print(f"[PREFLIGHT BLOCKED] {len(rejected)} 提案未通过生产预检：")
            for expr, problems in rejected:
                print(f"  - {expr[:70]} -> {'; '.join(problems)}")
        if settings_rejected:
            print(f"[SETTINGS BLOCKED] {len(settings_rejected)} 提案设置不合法，拒绝模拟：")
            for expr, problems in settings_rejected:
                print(f"  - {expr[:70]} -> {'; '.join(problems)}")

        if not fresh:
            self.last_run_stats = {
                "accepted": 0,
                "rejected": len(rejected) + len(diversity_rejected) + len(settings_rejected),
                "skipped": len(skipped),
            }
            if rejected and not skipped:
                print("所有提案均未通过生产预检；请补齐字段、字段画像、"
                      "算子证据、实验阶段和谱系元数据后重试。")
            else:
                print("All proposals already simulated before; nothing to run.")
            self.memory.register_hypothesis(hypothesis)
            self.memory.save()
            self._last_round_skipped = True
            self._save_state(None)
            self._write_context()
            return None
        self._last_round_skipped = False
        self.memory.best_exhausted = False
        self.last_run_stats = {
            "accepted": len(fresh),
            "rejected": len(rejected) + len(diversity_rejected) + len(settings_rejected),
            "skipped": len(skipped),
        }

        experiments = []
        # suggestions bundle 顶层字段键是 "fields"；兼容旧约定 "suggestion_fields"。
        known_ids = list(discovered_profiles)
        for p in fresh:
            fields = p.get("fields") or known_ids
            # 只保留提案声明字段里表达式实际用到的（含辅助腿），
            # 避免把未使用的 discovery 字段记进 fields_used 造成信号族误判。
            if fields:
                fields = extract_fields(p["expression"], fields)
            datasets = p.get("datasets") or []
            exp = Experiment(
                round_no,
                hypothesis["id"],
                p["expression"],
                self._proposal_settings(p.get("settings")),
                fields,
                datasets=datasets,
            )
            exp.candidate_id = p.get("candidate_id") or candidate_identity(p, round_no=round_no)
            exp.submission_fingerprint = submission_fingerprint(
                exp.expression, exp.settings
            )
            exp.proposal_id = p.get("proposal_id") or (
                "p-" + exp.submission_fingerprint[:16]
            )
            exp.field_source = p.get("field_source")
            exp.field_understanding = p.get("field_understanding")
            exp.field_analysis = p.get("field_analysis")
            exp.field_hypothesis_basis = p.get("field_hypothesis_basis")
            exp.operator_evidence = p.get("operator_evidence")
            exp.template_id = p.get("template_id")
            exp.template_family = p.get("template_family")
            exp.template_stage_path = p.get("template_stage_path")
            exp.template_ref = p.get("template_ref")
            exp.template_slots = p.get("template_slots")
            exp.search_evidence = p.get("search_evidence")
            exp.novelty_score = p.get("novelty_score")
            exp.allocation_arm = self.search_policy.allocator.arm_key(p)
            exp.allocation_key = self.search_policy.allocator.proposal_key(p)
            exp.factory_session_id = p.get("factory_session_id")
            exp.mutation = p.get("mutation") or "agent-proposed"
            exp.lineage_id = p.get("lineage_id") or p.get("parent_expression") or hypothesis["id"]
            exp.experiment_stage = p.get("experiment_stage")
            exp.research_role = p.get("research_role")
            exp.change_type = p.get("change_type") or "baseline"
            exp.parent_expression = p.get("parent_expression")
            exp.changed_variable = p.get("changed_variable")
            exp.expected_failure_modes = list(p.get("expected_failure_modes") or [])
            exp.tuning_risk = p.get("tuning_risk")
            exp.rationale = p.get("rationale") or p.get("hypothesis") or ""
            exp.direction = p.get("direction")
            exp.expected_horizon = p.get("expected_horizon")
            exp.falsification = p.get("falsification")
            exp.economic_mechanism = p.get("economic_mechanism")
            exp.direction_transform = p.get("direction_transform")
            exp.self_correlation_impact = p.get("self_correlation_impact")
            exp.validation_plan = p.get("validation_plan")
            if exp.experiment_stage == "ROBUSTNESS" and exp.validation_plan is None:
                # The proposal contract normally rejects this earlier.  Keep
                # the construction boundary fail-closed for direct callers.
                raise ValueError("ROBUSTNESS 缺少预注册 validation_plan")
            experiments.append(exp)
            self._record_trial_phase(exp, "generated", outcome="PENDING")
            self._record_trial_phase(exp, "preflight", outcome="ACCEPTED")
            self._record_trial_phase(exp, "preflight_accepted", outcome="ACCEPTED")
            self.memory.remember_expression(exp.expression)

        self.memory.register_hypothesis(hypothesis)
        checkpoint_path = self._proposal_checkpoint_path(round_no)
        self._write_proposal_checkpoint(
            round_no, hypothesis, experiments, complete=False
        )
        _round_t0 = time.time()
        self.trajectory.begin_append_batch(experiments)
        try:
            self.simulator.run(
                experiments,
                on_complete=self._record_live_result,
                on_update=lambda exp: self._on_simulation_update(
                    exp, round_no, hypothesis, experiments
                ),
            )
        finally:
            self.trajectory.end_append_batch()
        _round_elapsed = time.time() - _round_t0
        unresolved = [
            exp for exp in experiments
            if exp.status in ("PENDING", "RUNNING", "SUBMITTING", "SUBMIT_UNKNOWN", "UNKNOWN")
        ]
        if unresolved:
            for exp in experiments:
                self.search_policy.release(
                    {"proposal_id": exp.allocation_key, "expression": exp.expression,
                     "dataset_family": exp.datasets, "template_family": exp.template_family},
                    status="UNKNOWN" if exp.status in {"UNKNOWN", "SUBMIT_UNKNOWN"} else "PENDING",
                )
            self._write_proposal_checkpoint(round_no, hypothesis, experiments, complete=False)
            self._write_sims_results(round_no, experiments, total_elapsed_sec=_round_elapsed)
            print(
                f"[CHECKPOINT] {len(unresolved)} 个任务未定论，已保留 {checkpoint_path}；"
                "下次运行同一 proposals.json 只会恢复轮询，绝不重复 POST。"
            )
            return None
        # Preserve undispatched PENDING jobs too: terminal-expression recovery
        # uses them to avoid permanently deduping work paused by a local fault.
        self.trajectory.add_many(experiments)
        for exp in experiments:
            self.search_policy.release(
                {"proposal_id": exp.allocation_key, "expression": exp.expression,
                 "dataset_family": exp.datasets, "template_family": exp.template_family},
                status="DONE" if exp.status == "DONE" else exp.status,
                reward=(exp.metrics or {}).get("fitness", 0.0) if isinstance(exp.metrics, dict) else 0.0,
            )

        self._refresh_self_correlation_evidence(experiments)
        self._mark_robustness_stability(experiments)
        summary = self.reflector.reflect(
            round_no, hypothesis, experiments,
            validation_candidates=getattr(self, "_validation_candidates", None),
        )
        self._sync_submission_pool(experiments)
        state = ResearchState(
            round_no=round_no,
            hypothesis=hypothesis,
            dataset=sorted({d for e in experiments for d in e.datasets}),
            fields_used=[f for e in experiments for f in e.fields_used],
        )
        self._save_state(state)
        self._write_proposal_checkpoint(round_no, hypothesis, experiments, complete=True)
        self._write_context()
        self._print_summary(summary)
        self._write_sims_results(round_no, experiments, total_elapsed_sec=_round_elapsed)
        print(
            f"[ELAPSED] Round {round_no} 模拟总耗时 {_round_elapsed/60:.1f} 分钟"
            f"（{len(experiments)} 个模拟，3 并发真实计时）"
        )
        return summary

    # ----------------------------------------------------- crash recovery

    def _proposal_checkpoint_path(self, round_no):
        return os.path.join(self.state_dir, f"round_{round_no}.checkpoint.json")

    def skip_stale_reconciled(self, round_no, simulation_id, min_attempts=3):
        """Close one known remote job after repeated read-only STALE results.

        This is an execution-state maintenance action, not a research
        verdict.  The exact remote id is required, the evidence is read from
        the append-only reconciliation history, and no POST is possible here.
        """
        checkpoint = self._load_proposal_checkpoint(int(round_no))
        if not checkpoint or checkpoint.get("complete"):
            raise ValueError(f"round {round_no} has no unfinished checkpoint")
        history_path = os.path.join(self.state_dir, "reconcile_history.jsonl")
        attempts = []
        for row in iter_jsonl_objects(history_path):
            if (row.get("simulation_id") == simulation_id
                    and row.get("outcome") in {"STALE", "UNKNOWN"}):
                attempts.append(row)
        if len(attempts) < int(min_attempts):
            raise ValueError(
                f"only {len(attempts)} read-only STALE/UNKNOWN reconciliations; "
                f"need {min_attempts}"
            )
        experiments = [Experiment.from_dict(row) for row in checkpoint["experiments"]]
        matches = [
            exp for exp in experiments
            if (exp.progress_url or "").rstrip("/").split("/")[-1] == simulation_id
        ]
        if len(matches) != 1:
            raise ValueError(f"expected one checkpoint experiment for {simulation_id}, found {len(matches)}")
        exp = matches[0]
        if exp.status not in {"UNKNOWN", "RUNNING", "PENDING", "SUBMITTING"}:
            raise ValueError(f"simulation {simulation_id} is already {exp.status}")
        last = attempts[-1]
        exp.status = "SKIPPED_STALE"
        exp.skip_record = {
            "reason": "repeated_read_only_reconciliation_stale_or_unknown",
            "simulation_id": simulation_id,
            "attempts": len(attempts),
            "outcomes": [a.get("outcome") for a in attempts],
            "last_reconciled_at": last.get("reconciled_at"),
            "skipped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "research_decision": "N/A",
        }
        exp.error = "SKIPPED_AFTER_REPEATED_STALE_RECONCILIATION"
        unresolved = [
            e for e in experiments
            if e.status in ("PENDING", "RUNNING", "SUBMITTING", "SUBMIT_UNKNOWN", "UNKNOWN")
        ]
        self._write_proposal_checkpoint(
            int(round_no), checkpoint.get("hypothesis") or {}, experiments,
            complete=not unresolved,
        )
        self.trajectory.add(exp)
        audit_path = os.path.join(self.state_dir, "stale_skip_log.jsonl")
        append_jsonl_if_unique(
            audit_path,
            {
                "round_no": int(round_no),
                "experiment_id": exp.id,
                "expression": exp.expression,
                "progress_url": exp.progress_url,
                **exp.skip_record,
            },
            ("round_no", "experiment_id", "reason"),
        )
        print(f"[SKIP] r{round_no} {simulation_id} -> SKIPPED_STALE; attempts={len(attempts)}")
        print(f"[SKIP] audit -> {audit_path}")
        return exp

    def skip_submit_unknown_authorized(self, round_no, proposal_id):
        """Record an explicitly authorized skip for an unresolved POST.

        This is only for a user-directed terminal transport action when no
        remote simulation id/progress URL exists.  It never retries the POST;
        the proposal id and fingerprint remain in the audit record.
        """
        checkpoint = self._load_proposal_checkpoint(int(round_no))
        if not checkpoint or checkpoint.get("complete"):
            raise ValueError(f"round {round_no} has no unfinished checkpoint")
        experiments = [Experiment.from_dict(row) for row in checkpoint["experiments"]]
        matches = [e for e in experiments if e.proposal_id == proposal_id]
        if len(matches) != 1:
            raise ValueError(f"expected one checkpoint experiment for {proposal_id}, found {len(matches)}")
        exp = matches[0]
        if exp.status != "SUBMIT_UNKNOWN":
            raise ValueError(f"proposal {proposal_id} is {exp.status}, not SUBMIT_UNKNOWN")
        exp.status = "SKIPPED_UNKNOWN"
        exp.skip_record = {
            "reason": "user_authorized_skip_after_repeated_read_only_reconciliation",
            "proposal_id": proposal_id,
            "submission_fingerprint": exp.submission_fingerprint,
            "remote_id": None,
            "read_only_reconciliation": "no_unique_remote_record",
            "skipped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "research_decision": "N/A",
        }
        exp.error = "SKIPPED_AFTER_USER_AUTHORIZED_SUBMIT_UNKNOWN"
        unresolved = [e for e in experiments if e.status in ("PENDING", "RUNNING", "SUBMITTING", "SUBMIT_UNKNOWN", "UNKNOWN")]
        self._write_proposal_checkpoint(int(round_no), checkpoint.get("hypothesis") or {}, experiments, complete=not unresolved)
        self.trajectory.add(exp)
        audit_path = os.path.join(self.state_dir, "stale_skip_log.jsonl")
        append_jsonl_if_unique(
            audit_path,
            {"round_no": int(round_no), "experiment_id": exp.id,
             "expression": exp.expression, "progress_url": exp.progress_url,
             **exp.skip_record},
            ("round_no", "experiment_id", "reason"),
        )
        print(f"[SKIP] r{round_no} {proposal_id} -> SKIPPED_UNKNOWN; user-authorized")
        print(f"[SKIP] audit -> {audit_path}")
        return exp

    def finalize_recorded_round(self, round_no):
        """Diagnose a completed round from append-only trajectory evidence.

        Used only when a transport-recovery action completed a checkpoint but
        interrupted the round-level reflection.  It never submits or rewrites
        trajectory records; DONE evidence wins over a transport-only skipped
        duplicate for the same expression.
        """
        self._ensure_loaded()
        rows = [e for e in self.trajectory.experiments if e.round == int(round_no)]
        if not rows:
            raise ValueError(f"no trajectory evidence for round {round_no}")
        selected = {}
        for exp in rows:
            old = selected.get(exp.expression)
            rank = {"UNKNOWN": 0, "PENDING": 0, "SUBMITTING": 0, "RUNNING": 0,
                    "SKIPPED_STALE": 1, "SKIPPED_UNKNOWN": 1, "FAILED": 1, "DONE": 2}
            if old is None or rank.get(exp.status, 0) > rank.get(old.status, 0):
                selected[exp.expression] = exp
        experiments = list(selected.values())
        active = [e for e in experiments if e.status in {"PENDING", "RUNNING", "SUBMITTING", "SUBMIT_UNKNOWN", "UNKNOWN"}]
        if active:
            raise ValueError(f"round {round_no} still has unresolved experiments")
        checkpoint = self._load_proposal_checkpoint(int(round_no)) or {}
        hypothesis = checkpoint.get("hypothesis") or {"id": f"h-llm-r{round_no}", "_round": int(round_no)}
        self._refresh_self_correlation_evidence(experiments)
        self._mark_robustness_stability(experiments)
        summary = self.reflector.reflect(
            int(round_no), hypothesis, experiments,
            validation_candidates=getattr(self, "_validation_candidates", None),
        )
        self._sync_submission_pool(experiments)
        state = ResearchState(
            round_no=int(round_no), hypothesis=hypothesis,
            dataset=sorted({d for e in experiments for d in e.datasets}),
            fields_used=[f for e in experiments for f in e.fields_used],
        )
        self._save_state(state)
        self._write_context()
        audit_path = os.path.join(self.state_dir, "round_finalization_log.jsonl")
        append_jsonl_if_unique(
            audit_path,
            {"round_no": int(round_no), "selected": len(experiments),
             "finalized_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "source": "trajectory_append_only"},
            ("round_no", "source"),
        )
        print(f"[FINALIZE] r{round_no} diagnosed {len(experiments)} recorded terminal experiments")
        print(f"[FINALIZE] audit -> {audit_path}")
        return summary

    def _unfinished_checkpoint_except(self, round_no):
        """Return another unfinished checkpoint, if any.

        A different round with pending work is an exactly-once boundary, not
        stale housekeeping: starting a new proposal file could otherwise
        consume slots while a previous POST is still ambiguous.
        """
        try:
            entries = os.scandir(self.state_dir)
        except OSError:
            return None
        result = None
        result_round = None
        with entries:
            for entry in entries:
                match = re.fullmatch(r"round_(\d+)\.checkpoint\.json", entry.name)
                if not match:
                    continue
                checkpoint_round = int(match.group(1))
                if checkpoint_round == int(round_no):
                    continue
                if result_round is not None and checkpoint_round >= result_round:
                    continue
                path = entry.path
                try:
                    with open(path, encoding="utf-8") as f:
                        payload = json.load(f)
                    if not isinstance(payload, dict) or not payload.get("complete", False):
                        result = path
                        result_round = checkpoint_round
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    # A malformed checkpoint cannot establish submission
                    # state; block instead of assuming it is safe to submit.
                    result = path
                    result_round = checkpoint_round
        if result is not None:
            return result
        return None

    def _write_proposal_checkpoint(self, round_no, hypothesis, experiments, complete):
        """Atomically persist execution state around every POST/poll update."""
        os.makedirs(self.state_dir, exist_ok=True)
        path = self._proposal_checkpoint_path(round_no)
        data = {
            "schema_version": CHECKPOINT_VERSION,
            "created_by_version": CREATED_BY_VERSION,
            "round_no": round_no,
            "hypothesis": hypothesis,
            "experiments": [exp.to_dict() for exp in experiments],
            "complete": bool(complete),
            "updated_at": time.time(),
        }
        with self._checkpoint_lock:
            atomic_write_json_if_changed(path, data, ignored_keys=("updated_at",))

    def _load_proposal_checkpoint(self, round_no):
        path = self._proposal_checkpoint_path(round_no)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data = migrate_artifact("checkpoint", data)
            if (not isinstance(data, dict)
                    or data.get("round_no") != round_no
                    or not isinstance(data.get("experiments"), list)
                    or not isinstance(data.get("hypothesis"), dict)):
                return None
            # A malformed checkpoint is a recovery boundary, not an empty
            # batch.  Validate the fields consumed by Experiment.from_dict()
            # here so an unattended resume fails closed without constructing
            # partial objects or issuing a replacement POST.
            required = {"id", "round", "hypothesis_id", "expression",
                        "settings", "fields_used", "status"}
            for row in data["experiments"]:
                if not isinstance(row, dict) or not required.issubset(row):
                    return None
                if (not isinstance(row["id"], (str, int))
                        or not str(row["id"]).strip()
                        or not isinstance(row["expression"], str)
                        or not row["expression"].strip()
                        or not isinstance(row["settings"], dict)
                        or not isinstance(row["fields_used"], (list, tuple))
                        or not isinstance(row["status"], str)):
                    return None
            return data
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        return None

    def _resume_proposal_checkpoint(self, checkpoint):
        """Resume only known BRAIN jobs; unknown submits remain budget-held."""
        round_no = checkpoint["round_no"]
        hypothesis = checkpoint.get("hypothesis") or {"id": f"h-llm-r{round_no}"}
        experiments = [Experiment.from_dict(row) for row in checkpoint["experiments"]]
        runnable = [
            exp for exp in experiments
            if exp.status not in ("DONE", "FAILED", "SUBMIT_UNKNOWN", "SKIPPED_STALE", "SKIPPED_UNKNOWN")
        ]
        unresolved = [exp for exp in experiments if exp.status == "SUBMIT_UNKNOWN"]
        print(f"\n=== Round {round_no} checkpoint resume ===")
        if unresolved:
            print(
                f"[SUBMIT_UNKNOWN] {len(unresolved)} 个 POST 结果不明，已保留预算槽，"
                "不会重发；需先做平台侧只读对账。"
            )
        if runnable:
            self.trajectory.begin_append_batch(runnable)
            try:
                self.simulator.run(
                    runnable,
                    on_complete=self._record_live_result,
                    on_update=lambda exp: self._on_simulation_update(
                        exp, round_no, hypothesis, experiments
                    ),
                )
            finally:
                self.trajectory.end_append_batch()
        unresolved = [
            exp for exp in experiments
            if exp.status in ("PENDING", "RUNNING", "SUBMITTING", "SUBMIT_UNKNOWN", "UNKNOWN")
        ]
        if unresolved:
            self._write_proposal_checkpoint(round_no, hypothesis, experiments, complete=False)
            self._write_sims_results(round_no, experiments)
            return None
        self.trajectory.add_many(experiments)
        self._refresh_self_correlation_evidence(experiments)
        self._mark_robustness_stability(experiments)
        summary = self.reflector.reflect(
            round_no, hypothesis, experiments,
            validation_candidates=getattr(self, "_validation_candidates", None),
        )
        self._sync_submission_pool(experiments)
        state = ResearchState(
            round_no=round_no,
            hypothesis=hypothesis,
            dataset=sorted({d for exp in experiments for d in exp.datasets}),
            fields_used=[f for exp in experiments for f in exp.fields_used],
        )
        self._save_state(state)
        self._write_proposal_checkpoint(round_no, hypothesis, experiments, complete=True)
        self._write_context()
        self._print_summary(summary)
        self._write_sims_results(round_no, experiments)
        return summary

    def _read_field_cache(self):
        """Read the on-disk field cache once for types and verified profiles."""
        datasets = None
        # FieldDiscovery already selected the authoritative complete catalog
        # or the legacy TTL cache. Reuse that parsed mapping instead of
        # opening/parsing a second copy during every proposal batch.
        if hasattr(self.discovery, "cached_datasets"):
            datasets = self.discovery.cached_datasets()
        cache_path = os.path.join(self.state_dir, "fields_cache.json")
        field_types = {}
        profiles = {}
        if datasets is None:
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cache = json.load(f)
                datasets = cache.get("datasets") or {}
            except (OSError, ValueError, json.JSONDecodeError):
                return {}, {}
        try:
            for dataset_id, fields in (datasets or {}).items():
                for field in fields or []:
                    if not isinstance(field, dict):
                        continue
                    field_id = field.get("id")
                    field_type = field.get("type")
                    if field_id and field_type:
                        field_types[str(field_id)] = str(field_type)
                    if not field_id or not field_type or not field.get("description"):
                        continue
                    profile = dict(field)
                    profile.setdefault("dataset", dataset_id)
                    profile.setdefault("semantic_status", "KNOWN")
                    profiles[str(field_id)] = profile
        except (AttributeError, TypeError):
            return {}, {}
        return field_types, profiles

    def _known_field_types(self, payload, cached_field_types=None):
        """Build a field-id -> type map from real discovery artifacts."""
        # ``--suggest`` may carry an explicit field-type manifest assembled
        # from the platform response.  Prefer it as the authoritative source
        # so manually/externally verified MATRIX fields are not lost when the
        # on-disk discovery cache is stale or incomplete.
        # Cache/catalog is the fallback layer; the current suggestion bundle
        # is newer evidence and must overlay it, never the reverse.
        if cached_field_types is None:
            cached_field_types, _ = self._read_field_cache()
        field_types = {
            str(field_id): str(field_type)
            for field_id, field_type in (cached_field_types or {}).items()
            if field_id and field_type
        }
        for field_id, field_type in (payload.get("field_types") or {}).items():
            if field_id and field_type:
                field_types[str(field_id)] = str(field_type)
        for field in (payload.get("suggestion_fields") or payload.get("fields") or []):
            if isinstance(field, dict) and field.get("id") and field.get("type"):
                field_types[str(field["id"])] = str(field["type"])
        return field_types

    def _verified_field_profiles(self):
        """Load known field metadata from the TTL-bounded discovery cache."""
        _, profiles = self._read_field_cache()
        return profiles

    def _proposal_settings(self, overrides=None):
        """Merge the allowed proposal overrides onto complete defaults.

        BRAIN requires every simulation setting. A partial ``settings`` object
        must therefore never replace the full config, and settings outside the
        user-authorized universe/truncation/decay whitelist are rejected.
        """
        if overrides is None:
            return dict(self.simulation_settings)
        if not isinstance(overrides, dict):
            raise ValueError("settings 必须是对象")
        unknown = sorted(set(overrides) - SETTING_OVERRIDES)
        if unknown:
            raise ValueError(f"settings 包含未授权参数: {unknown}")
        merged = dict(self.simulation_settings)
        merged.update(overrides)
        if "universe" in overrides:
            value = overrides["universe"]
            if not isinstance(value, str) or not value.strip():
                raise ValueError("universe 必须是非空字符串")
        if "truncation" in overrides:
            try:
                value = float(overrides["truncation"])
            except (TypeError, ValueError):
                raise ValueError("truncation 必须是数值")
            if not 0.02 <= value <= 0.15:
                raise ValueError("truncation 必须在 0.02 至 0.15 之间")
            merged["truncation"] = value
        if "decay" in overrides:
            value = overrides["decay"]
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10:
                raise ValueError("decay 必须是 0 至 10 的整数")
        return merged

    def run_one_round(self, round_no):
        """Reject the retired single-round shortcut.

        Production research must pass through ``--suggest`` and
        ``--run-proposals`` so discovery, preflight, checkpoint recovery, and
        exactly-once submission rules cannot be bypassed.
        """
        raise RuntimeError(
            "run_one_round 会绕过 proposal 预检与 checkpoint，已禁止用于生产。"
        )

    # ------------------------------------------------------- hypothesis

    def _form_research_space(self, round_no):
        """Choose only a dataset/question before field discovery.

        The returned statement deliberately does not assert an economic
        effect.  The proposal's economic hypothesis is formed later from the
        selected field descriptions and must cite them verbatim.
        """
        seed = self._form_hypothesis(round_no)
        return {
            "id": seed.get("id", f"space-r{round_no}"),
            "statement": "Which low-usage, semantically documented fields can test a new mechanism?",
            "tags": list(seed.get("tags") or []),
            "datasets": list(seed.get("datasets") or seed.get("dataset_hints") or []),
            "parent_best": seed.get("parent_best"),
        }

    def _form_hypothesis(self, round_no):
        """Prefer iterating on current best; when that branch is exhausted
        (last round skipped), switch to a next-idea with genuinely different
        fields, else to an unused seed hypothesis (new research branch)."""
        trusted_best = self._trusted_current_best()
        if (
            trusted_best
            and not (self.memory.best_exhausted or self._last_round_skipped)
            and not self._best_family_is_occupied()
        ):
            return self._iterate_best_hypothesis(round_no, trusted_best)

        if trusted_best and self._best_family_is_occupied():
            return self._exploration_seed(round_no)

        best_fields = set((trusted_best or {}).get("fields_used") or [])
        idea = self.memory.next_with_fields(round_no)
        idea_fields = set(idea.get("fields") or []) if idea else set()
        if idea and (not best_fields or not (idea_fields & best_fields)):
            datasets = idea.get("datasets") or []
            tags = list(idea_fields)[:1] + ["next", "memory"]
            return {
                "id": f"h-next-r{round_no}",
                "statement": idea["idea"],
                "tags": tags,
                "direction": "long",
                "datasets": datasets,
            }

        for seed in SEED_HYPOTHESES:
            if seed["id"] not in self.memory.used_hypotheses:
                return dict(seed)
        # all seeds used: cycle deterministically to the least-recently failed
        return dict(SEED_HYPOTHESES[round_no % len(SEED_HYPOTHESES)])

    def _best_family_is_occupied(self):
        """Prefer an unused cross-family seed when best is analyst4-based."""
        best = self._trusted_current_best() or {}
        if "analyst4" not in set(best.get("datasets") or []):
            return False
        return True

    def _exploration_seed(self, round_no):
        """Rotate through non-analyst4 families once best is submit-blocked."""
        return dict(EXPLORATION_HYPOTHESES[round_no % len(EXPLORATION_HYPOTHESES)])

    def _iterate_best_hypothesis(self, round_no, best=None):
        best = best or self._trusted_current_best()
        metrics = best.get("metrics") or {}
        sharpe = metrics.get("sharpe")
        direction = "reversal" if (sharpe is not None and sharpe < 0) else "long"
        fields = best.get("fields_used") or []
        datasets = best.get("datasets") or []
        tags = ["iterate", "best"]
        if fields:
            tags.append(fields[0])

        idea = self.memory.next_with_fields(round_no)
        if idea:
            statement = (
                f"{idea['idea']} (iterating on current best: {best['expression']})"
            )
            if idea.get("datasets"):
                datasets = sorted(set(datasets) | set(idea["datasets"]))
        else:
            statement = (
                f"Iterate on current best {best['expression']} with bounded "
                f"single-variable mutations."
            )
        return {
            "id": f"h-iter-r{round_no}",
            "statement": statement,
            "tags": tags,
            "direction": direction,
            "datasets": datasets,
            "parent_best": best.get("id"),
        }

    def _ensure_best_field(self, fields):
        best = self._trusted_current_best()
        best_fields = best.get("fields_used") or []
        known = {f["id"] for f in fields}
        datasets = best.get("datasets") or []
        merged = list(fields)
        for fid in best_fields:
            if fid not in known:
                merged.insert(
                    0,
                    {
                        "id": fid,
                        "name": fid,
                        "category": "preferred",
                        "dataset": datasets[0] if datasets else None,
                        "match_score": 0,
                    },
                )
        return merged

    def _trusted_current_best(self):
        """Only a stability-validated, healthy record may steer research."""
        best = self.memory.current_best or {}
        metrics = best.get("metrics") or {}
        if checks_passed(metrics) is not True:
            return None
        if best.get("validation_status") != "STABLE":
            return None
        report = best.get("validation_report") or {}
        if report.get("status") != "PASS" or report.get("candidate") != "parent":
            return None
        health = best.get("health") or {}
        if health and not health.get("ok", False):
            return None
        return best

    def _filter_unseen(self, candidates):
        seen = self._terminal_expressions()
        fresh = []
        for c in candidates:
            if canonical_expression(c["expression"]) not in seen:
                fresh.append(c)
        return fresh

    def _terminal_identities(self, expressions=None):
        """视为"已模拟过"的表达式集合（去重依据）。

        只把已定论的表达式计入：DONE 与研究级 FAILED（SYNTAX/DATA）不重复
        提交；UNKNOWN / PENDING / 系统级失败（限流、超时、网络、认证）不
        能证明方向结论——POST 可能未发生或结果未知，剔除去重以便重试
        （2026-08-19 r256 实测：2 条提交 429 耗尽 + 15 条 PENDING 曾因去重
        被永久锁死，无法重跑）。
        """
        from .failures import classify_experiment, is_research_relevant

        scoped = expressions is not None
        target_expressions = {
            canonical_expression(expression)
            for expression in (expressions or [])
            if isinstance(expression, str) and expression.strip()
        }
        if scoped and not target_expressions:
            return set(), set()
        memory_terminal = {
            canonical_expression(expression)
            for expression in self.memory.seen_expressions
            if isinstance(expression, str) and expression.strip()
            and (not scoped
                 or canonical_expression(expression) in target_expressions)
        }
        terminal = set()
        fingerprints = set()

        def apply(row):
            if not isinstance(row, dict):
                return
            expression = row.get("expression")
            if not isinstance(expression, str) or not expression.strip():
                return
            canonical = canonical_expression(expression)
            if scoped and canonical not in target_expressions:
                return
            status = row.get("status")
            fingerprint = row.get("submission_fingerprint")
            if not isinstance(fingerprint, str) or not fingerprint:
                settings = row.get("settings")
                if isinstance(settings, dict):
                    fingerprint = submission_fingerprint(expression, settings)
            fingerprint_key = (
                "settings::" + fingerprint
                if isinstance(fingerprint, str) and fingerprint
                else None
            )
            if status in ("UNKNOWN", "PENDING", "RUNNING", "SUBMITTING", "SUBMIT_UNKNOWN"):
                terminal.discard(canonical)
                if fingerprint_key:
                    fingerprints.discard(fingerprint_key)
                return
            if status in ("SKIPPED_STALE", "SKIPPED_UNKNOWN", "DONE"):
                terminal.add(canonical)
            elif status == "FAILED":
                kind = classify_experiment(
                    type("HistoricalExperiment", (), {
                        "status": status, "error": row.get("error")
                    })()
                )
                if kind is None or not is_research_relevant(kind):
                    terminal.discard(canonical)
                    if fingerprint_key:
                        fingerprints.discard(fingerprint_key)
                else:
                    terminal.add(canonical)
            if status in ("DONE", "SKIPPED_STALE", "SKIPPED_UNKNOWN") and fingerprint_key:
                fingerprints.add(fingerprint_key)

        # trajectory is the authoritative exact-dedupe source when present;
        # the memory set is only a fallback for in-memory/unit-test callers
        # without a durable trajectory.  Filtering before status/fingerprint
        # work keeps the returned sets bounded by this proposal batch while
        # preserving the one streaming pass over the append-only source.
        trajectory_path = getattr(self.trajectory, "path", None)
        if trajectory_path and os.path.exists(trajectory_path):
            for row in self.trajectory.iter_rows() or ():
                apply(row)
        else:
            terminal.update(memory_terminal)
            for e in self.trajectory.experiments:
                apply(e.to_dict())
        return terminal, fingerprints

    def _terminal_expressions(self):
        """Compatibility view containing only canonical expressions."""
        return self._terminal_identities()[0]

    def _completed_parent(self, expression, resolved=None):
        """Return the resolved parent evidence for an evidence-dependent role."""
        if not isinstance(expression, str) or not expression.strip():
            return None
        target = canonical_expression(expression)
        for exp in reversed(self.trajectory.experiments):
            if canonical_expression(exp.expression) == target and exp.status == "DONE" and exp.metrics:
                return exp
        if resolved is not None and target in resolved:
            return resolved[target]
        return self.trajectory.find_completed_expression(expression)

    # ------------------------------------------------------------ helpers

    def _record_trial_phase(self, experiment, phase, outcome=None, reason=None, reason_code=None):
        """Best-effort audit only; never changes Simulation safety semantics."""
        try:
            self.trial_ledger.record(
                experiment, phase, outcome=outcome, reason=reason,
                reason_code=reason_code,
            )
        except Exception as exc:
            print(f"[TRIAL_LEDGER_WARN] {type(exc).__name__}: {exc}")

    def _record_candidate_rejection(self, candidate, stage, reason_code, reason):
        """Record every local rejection against its stable candidate identity."""
        try:
            if isinstance(candidate, dict):
                candidate = dict(candidate)
                candidate.setdefault("candidate_id", candidate_identity(candidate, round_no=candidate.get("round")))
            self.trial_ledger.record(
                candidate,
                "candidate_rejected",
                outcome="REJECTED",
                reason=reason,
                reason_code=reason_code,
                stage=stage,
            )
        except Exception as exc:
            print(f"[TRIAL_LEDGER_WARN] {type(exc).__name__}: {exc}")

    def _update_search_lifecycle(self, experiment, outcome=None):
        """Mirror transport state into the in-memory allocator idempotently."""
        if not hasattr(self, "search_policy"):
            return
        status = str(getattr(experiment, "status", "UNKNOWN") or "UNKNOWN").upper()
        if status == "SUBMIT_UNKNOWN":
            status = "UNKNOWN"
        if status in {"SKIPPED_STALE", "SKIPPED_UNKNOWN"}:
            status = "SKIPPED"
        if status not in {"RUNNING", "PENDING", "DONE", "FAILED", "UNKNOWN", "SKIPPED"}:
            return
        proposal = {
            "proposal_id": getattr(experiment, "allocation_key", None) or getattr(experiment, "proposal_id", None),
            "expression": getattr(experiment, "expression", ""),
            "dataset_family": getattr(experiment, "datasets", []),
            "template_family": getattr(experiment, "template_family", None),
        }
        reward = outcome.reward if outcome is not None else None
        error_text = str(getattr(experiment, "error", "") or "").upper()
        failure_category = "INFRA" if status == "FAILED" and any(token in error_text for token in (
            "TIMEOUT", "RATE_LIMIT", "AUTH", "INFRA", "NETWORK", "HTTP"
        )) else "RESEARCH"
        try:
            self.search_policy.release(
                proposal, status=status, reward=reward,
                outcome=outcome or failure_category,
            )
        except (TypeError, ValueError):
            pass

    def _on_simulation_update(self, experiment, round_no, hypothesis, experiments):
        if experiment.status in {"RUNNING", "SUBMIT_UNKNOWN"}:
            self._record_trial_phase(
                experiment, "submitted", outcome=experiment.status
            )
            self._record_trial_phase(
                experiment, "simulation_submitted", outcome=experiment.status
            )
            self._update_search_lifecycle(experiment)
        self._write_proposal_checkpoint(
            round_no, hypothesis, experiments, complete=False
        )

    def _attach_candidate_meta(self, experiment, candidate):
        experiment.hypothesis_id = candidate.get("parent") or experiment.hypothesis_id
        experiment.mutation = candidate.get("mutation")
        experiment.rationale = candidate.get("rationale")

    def _print_experiment(self, exp):
        if exp.metrics:
            m = exp.metrics
            # 同时给出本地 id 与平台真实 alpha_id：本地 id 用于查
            # trajectory，alpha_id 用于 check_health/check_correlation/提交。
            tag = f"[{exp.id}]"
            if exp.alpha_id:
                tag += f" alpha={exp.alpha_id}"
            elapsed = (
                f" elapsed={exp.elapsed_sec:.0f}s" if exp.elapsed_sec is not None else ""
            )
            print(
                f"  {tag}{elapsed} {exp.expression[:60]} "
                f"sharpe={m.get('sharpe')} fitness={m.get('fitness')} "
                f"turnover={m.get('turnover')} returns={m.get('returns')} "
                f"drawdown={m.get('drawdown')} margin={m.get('margin')} "
                f"passed={m.get('passed')}"
            )
        else:
            elapsed = (
                f" elapsed={exp.elapsed_sec:.0f}s" if exp.elapsed_sec is not None else ""
            )
            print(f"  [{exp.id}]{elapsed} {exp.expression[:60]} {exp.status}: {exp.error}")

    def _record_live_result(self, exp):
        """Persist and analyze one result as soon as BRAIN returns it."""
        # Complete the local evidence envelope before the first append.  The
        # trajectory is append-only; mutating ``exp`` after ``add`` would not
        # update the already-written JSONL row and would silently lose the
        # correlation snapshot for crash recovery/reporting.
        exp.self_correlation = self_correlation_evidence(exp.metrics)
        verdict = self.reflector._classify(exp)
        outcome = SearchOutcome.from_experiment(
            exp,
            validation=getattr(exp, "validation_report", None),
            parent=self._completed_parent(getattr(exp, "parent_expression", None)),
            quality_label=verdict.get("label"),
        )
        exp.provisional_outcome = outcome.as_dict()
        exp.search_outcome = exp.provisional_outcome
        self._update_search_lifecycle(exp, outcome=outcome)
        self._record_trial_phase(exp, "completed", outcome=exp.status)
        self._record_trial_phase(
            exp, "simulation_settled", outcome=exp.status,
            reason=exp.error,
            reason_code=("INFRA" if exp.status == "FAILED" and
                         any(token in str(exp.error or "").upper() for token in
                             ("TIMEOUT", "RATE_LIMIT", "AUTH", "INFRA", "NETWORK", "HTTP"))
                         else ("RESEARCH" if exp.status == "FAILED" else None)),
        )
        self.trajectory.add(exp)
        self._print_experiment(exp)
        metrics = exp.metrics or {}
        failed_checks = []
        for check in metrics.get("checks") or []:
            if check_pass(check) is not False:
                continue
            check = check if isinstance(check, dict) else {}
            detail = check.get("name") or "UNKNOWN_CHECK"
            if check.get("value") is not None:
                detail += f"={check.get('value')}"
            if check.get("limit") is not None:
                detail += f"(limit={check.get('limit')})"
            failed_checks.append(detail)
        health = exp.health
        health_text = "unknown"
        if health is not None:
            health_text = "OK" if health.get("ok") else (
                "FAIL:" + ";".join(health.get("reasons") or [])
            )
        rating = self._alpha_rating(metrics)
        print(
            f"[LIVE_ANALYSIS] alpha={exp.alpha_id or '-'} "
            f"verdict={verdict.get('label')} rating={rating} "
            f"self_correlation={exp.self_correlation['status']} "
            f"failed_checks={failed_checks or 'none'} health={health_text} "
            f"reason={verdict.get('reason')}"
        )
        if getattr(exp, "falsification", None):
            print(
                f"[FALSIFICATION] alpha={exp.alpha_id or '-'} "
                f"criterion={exp.falsification}"
            )

    def _settled_self_correlation(self, exp):
        """Return the SELF_CORRELATION evidence for a DONE experiment, with the
        asynchronously-settled platform check (SELF_CORRELATION is PENDING at
        completion) overlaid from the evidence side-car.  This lets the
        submission gate read the *resolved* correlation value instead of the
        raw PENDING placeholder captured at simulation end."""
        metrics = exp.metrics or {}
        cached = (self.reflector.evidence_cache or {}).get(getattr(exp, "alpha_id", None))
        if cached:
            metrics = overlay_cached_checks(
                metrics, cached,
                (self.quality_policy or {}).get("max_self_correlation", 0.5),
            )
        return self_correlation_evidence(metrics)

    def _refresh_self_correlation_evidence(self, experiments):
        """Resolve SELF_CORRELATION only for submit-capable candidates.

        Exploratory and clearly sub-threshold results cannot enter the manual
        submission pool, so querying their asynchronous correlation endpoint
        only adds latency and cannot change a decision.
        """
        alpha_ids = []
        candidates = list(experiments or [])
        candidates.extend(self.trajectory.recent(self.correlation_refresh_window))
        for parent, _report in getattr(self, "_validation_candidates", []) or []:
            candidates.append(parent)
        seen = set()
        for exp in candidates:
            if exp.status != "DONE" or not exp.alpha_id:
                continue
            if exp.alpha_id in seen:
                continue
            seen.add(exp.alpha_id)
            metrics = exp.metrics or {}
            rating = self._alpha_rating(metrics)
            turnover = metrics.get("turnover")
            turnover_value = num(turnover)
            minimum_turnover = num(self.quality_policy.get("min_turnover", 0.01))
            maximum_turnover = num(self.quality_policy.get("max_turnover", 0.70))
            turnover_ok = (
                turnover_value is not None
                and minimum_turnover is not None
                and maximum_turnover is not None
                and minimum_turnover <= turnover_value <= maximum_turnover
            )
            if (rating in {"EXCELLENT", "SPECTACULAR"}
                    and checks_ready_for_self_correlation_refresh(metrics)
                    and bool((exp.health or {}).get("ok"))
                    and turnover_ok):
                alpha_ids.append(exp.alpha_id)
        # Unit-test/fallback clients intentionally do not expose the live HTTP
        # session; leave their synthetic metrics untouched.
        if not alpha_ids or not hasattr(self.client, "_session"):
            return
        refreshed = refresh_self_correlation_cache(
            self.client, self.state_dir, alpha_ids,
            correlation_limit=(self.quality_policy or {}).get(
                "max_self_correlation", 0.5
            ),
        )
        self.reflector.evidence_cache = load_evidence_cache(self.state_dir)
        print(f"[EVIDENCE] SELF_CORRELATION refreshed {refreshed}/{len(alpha_ids)}")

    @staticmethod
    def _correlation_under(evidence, max_corr):
        """Strict correlation gate: PASS status AND a resolved numeric value
        strictly below ``max_corr``.  A missing/resolved-null value cannot be
        claimed to satisfy a numeric cap, so it fails closed."""
        if not evidence or evidence.get("status") != "PASS":
            return False
        check = evidence.get("check") or {}
        value = check.get("value")
        if value is None:
            return False
        try:
            return float(value) < float(max_corr)
        except (TypeError, ValueError):
            return False

    def _sync_submission_pool(self, experiments):
        """Queue only fully validated candidates under the platform
        SELF_CORRELATION cap set by the user (default strict <0.5).

        There is intentionally no submission call here: every record remains
        ``MANUAL_REQUIRED`` for the user to submit on BRAIN.
        """
        active_snapshot = latest_active_snapshot(self.state_dir)
        corr_cap = num((self.quality_policy or {}).get("max_self_correlation", 0.5))
        if corr_cap is None:
            corr_cap = 0.5
        eligible_records = []
        candidates = list(experiments)
        for parent, report in getattr(self, "_validation_candidates", []) or []:
            if all(existing.id != parent.id for existing in candidates):
                candidates.append(parent)
        for exp in candidates:
            if exp.status != "DONE" or not exp.alpha_id:
                continue
            exp.self_correlation = self._settled_self_correlation(exp)
            effective_metrics = exp.metrics or {}
            cached = (self.reflector.evidence_cache or {}).get(exp.alpha_id)
            if cached:
                effective_metrics = overlay_cached_checks(
                    effective_metrics, cached, corr_cap
                )
            rating = self._alpha_rating(effective_metrics)
            healthy = bool((exp.health or {}).get("ok"))
            yearly = exp.yearly_evidence or {}
            # If the platform supplied annual aggregates, an unstable annual
            # profile is a hard promotion blocker. Legacy rows without this
            # optional evidence remain readable and are not rewritten.
            yearly_ok = (
                yearly.get("status") != "VERIFIED"
                or yearly.get("stable") is True
            )
            eligible = (
                rating in {"EXCELLENT", "SPECTACULAR"}
                and checks_passed(effective_metrics) is True
                and healthy
                and exp.validation_status == "STABLE"
                and isinstance(exp.validation_report, dict)
                and exp.validation_report.get("status") == "PASS"
                and exp.validation_report.get("candidate") == "parent"
                and yearly_ok
                and self._correlation_under(exp.self_correlation, corr_cap)
                and exp.self_correlation["status"] == "PASS"
            )
            eligibility = submission_eligibility(
                platform_pass=(exp.self_correlation["status"] == "PASS"),
                health=healthy,
                validation=(exp.validation_status == "STABLE" and
                            isinstance(exp.validation_report, dict) and
                            exp.validation_report.get("status") == "PASS"),
                yearly=yearly_ok,
                incremental=getattr(exp, "incremental_evidence", None),
                incremental_mode=self.incremental_policy.mode,
            )
            exp.submission_eligibility = eligibility
            eligible = eligible and eligibility["eligible"]
            if eligible:
                eligible_records.append((
                    exp, rating, exp.self_correlation, active_snapshot
                ))
        if eligible_records:
            self.submission_pool.upsert_many(eligible_records)
        added = len(eligible_records)
        if added:
            print(
                f"[SUBMISSION_POOL] {added} 个候选已进入 {self.submission_pool.path}；"
                "仅供人工提交，程序不会 POST Alpha。"
            )

    def _mark_robustness_stability(self, experiments):
        """Apply the one canonical STABLE gate to parent candidates.

        A single SUCCESS/ROBUSTNESS row is evidence only.  The parent is
        promoted only after all pre-registered dimensions have been
        aggregated into one passing ValidationReport.
        """
        self._validation_candidates = []
        all_rows = list(self.trajectory.experiments or [])
        for exp in experiments:
            if all(existing.id != exp.id for existing in all_rows):
                all_rows.append(exp)
        for row in all_rows:
            report = getattr(row, "validation_report", None) or {}
            if (getattr(row, "validation_status", None) == "STABLE"
                    and not (report.get("status") == "PASS" and report.get("candidate") == "parent")):
                row.validation_status = "UNVALIDATED"
        children_by_parent = {}
        plans = {}
        for child in all_rows:
            if child.experiment_stage != "ROBUSTNESS":
                continue
            parent_expression = child.parent_expression
            if not isinstance(parent_expression, str) or not parent_expression.strip():
                continue
            key = canonical_expression(parent_expression)
            children_by_parent.setdefault(key, []).append(child)
            if isinstance(child.validation_plan, dict) and key not in plans:
                plans[key] = child.validation_plan

        trial_summary = self.trial_ledger.summarize()
        for key, children in children_by_parent.items():
            parent = self._completed_parent(children[0].parent_expression)
            if parent is None:
                continue
            plan = plans.get(key)
            if not isinstance(plan, dict):
                plan = default_validation_plan(
                    parent, statistical_policy=self.statistical_policy,
                    robustness_policy=self.robustness_policy,
                )
            parent.self_correlation = self._settled_self_correlation(parent)
            platform_evidence = {
                "parent": {
                    "health": parent.health,
                    "correlation": parent.self_correlation,
                },
                "children": [
                    {
                        "health": child.health,
                        "correlation": self._settled_self_correlation(child),
                    }
                    for child in children
                ],
            }
            report = build_validation_report(
                parent,
                children,
                plan,
                yearly_evidence=parent.yearly_evidence,
                trial_summary=trial_summary,
                platform_evidence=platform_evidence,
            )
            append_jsonl_if_unique(
                os.path.join(self.state_dir, "validation_reports.jsonl"),
                {
                    "schema_version": VALIDATION_VERSION,
                    "created_by_version": "alpha-factory",
                    "parent_id": parent.id,
                    "parent_expression": parent.expression,
                    "plan_id": report.get("plan_id"),
                    "status": report.get("status"),
                    "report": dict(report),
                    "recorded_at": time.time(),
                },
                ("parent_id", "plan_id", "status"),
            )
            parent.validation_report = report
            for child in children:
                child.validation_report = report
                child.validation_status = "VALIDATED" if report["status"] == "PASS" else "FAILED"
            parent.validation_status = "STABLE" if report["status"] == "PASS" else "UNVALIDATED"
            self._settle_research_outcome(parent, report)
            if report["status"] == "PASS":
                self._validation_candidates.append((parent, report))

    def _settle_research_outcome(self, experiment, report):
        """Append one final replacement observation after aggregate evidence."""
        provisional = getattr(experiment, "provisional_outcome", None) or getattr(experiment, "search_outcome", None)
        if not isinstance(provisional, dict) or not isinstance(report, dict):
            return None
        incremental = self._settle_incremental_evidence(experiment)
        incremental_decision = incremental.get("decision", "UNAVAILABLE") if isinstance(incremental, dict) else "UNAVAILABLE"
        platform = (report.get("dimensions") or {}).get("platform_quality") or {}
        platform_pass = platform.get("status") == "PASS"
        final = settle_search_outcome(
            provisional,
            validation_report=report,
            incremental_decision=incremental_decision,
            yearly_evidence=getattr(experiment, "yearly_evidence", None),
            platform_pass=platform_pass,
        )
        quality = "STABLE" if report.get("status") == "PASS" else provisional.get("base_quality")
        robustness = "PASS" if report.get("status") == "PASS" else "FAIL"
        statistical = extract_statistical_decision(report)
        experiment.final_outcome = final
        experiment.search_outcome = final
        experiment.research_classification = classify_research(
            quality, robustness, statistical, incremental_decision,
            "PASS" if platform_pass else "FAIL",
        )
        experiment.research_evidence_bundle = ResearchEvidenceBundle.from_parts(
            {"label": quality, "effective_trial_count": self.trial_ledger.summarize_cached(
                os.path.join(self.state_dir, "trial_ledger.summary.json")
            ).get("effective_trial_count")},
            report.get("dimensions", {}).get("robustness") or report,
            report.get("statistical_evidence") or {},
            incremental,
            getattr(experiment, "yearly_evidence", None) or {},
            platform,
        ).as_dict()
        self.trial_ledger.record_outcome_settled(
            experiment, reward=final.get("reward"),
            reward_version=final.get("reward_version", "reward_v1"),
            reward_quality=final.get("reward_quality", "FINAL_EVIDENCE"),
            base_quality=quality, robustness=robustness,
            statistical_decision=statistical,
            incremental_decision=incremental_decision,
            research_classification=experiment.research_classification,
            incremental_evidence=incremental,
            research_evidence_bundle=experiment.research_evidence_bundle,
            timestamp=final.get("settled_at") or time.time(),
        )
        try:
            self.search_policy.replace_reward(experiment, final.get("reward"))
        except (TypeError, ValueError):
            pass
        return final

    def _settle_incremental_evidence(self, experiment):
        """Create production evidence from the only accepted behavior source.

        The current client has no LIVE_VERIFIED PnL capability, so normal
        candidates settle explicitly as UNAVAILABLE rather than receiving a
        correlation fabricated from aggregate metrics.
        """
        behavior = extract_behavior_series(experiment)
        members = []
        for row in list(self.trajectory.experiments or []):
            series = extract_behavior_series(row)
            members.append({
                "alpha_id": getattr(row, "alpha_id", None),
                "candidate_id": getattr(row, "candidate_id", None),
                "status": getattr(row, "status", None),
                "checks_passed": checks_passed(getattr(row, "metrics", None)),
                "identity": getattr(row, "submission_fingerprint", None),
                "behavior_series": series.get("series"),
                "pool_entered_at": getattr(row, "created_at", None),
            })
        snapshot = build_pool_snapshot(members, as_of=time.time())
        evidence = build_incremental_value(
            getattr(experiment, "candidate_id", None) or getattr(experiment, "alpha_id", None) or experiment.id,
            behavior.get("series"), snapshot.members,
            min_overlap=self.incremental_policy.min_overlap,
            max_abs_correlation=self.incremental_policy.max_abs_correlation,
            as_of=snapshot.as_of,
        )
        result = evidence.as_dict() if hasattr(evidence, "as_dict") else dict(evidence)
        result.update({
            "availability": behavior.get("availability"),
            "capability": behavior.get("capability"),
            "source": behavior.get("source"),
            "snapshot_id": snapshot.snapshot_id,
            "pool_size": len(snapshot.members),
            "policy": self.incremental_policy.mode,
        })
        experiment.incremental_evidence = result
        return result

    def _alpha_rating(self, metrics):
        """Internal Excellent/Spectacular discipline from AGENTS.md."""
        required = ("sharpe", "turnover", "fitness", "margin")
        if any(metrics.get(key) is None for key in required):
            return "UNRATED"
        sharpe = num(metrics["sharpe"])
        turnover = num(metrics["turnover"])
        fitness = num(metrics["fitness"])
        margin = num(metrics["margin"])
        if any(value is None for value in (sharpe, turnover, fitness, margin)):
            return "UNRATED"
        excellent = self.quality_policy.get("excellent", {})
        spectacular = self.quality_policy.get("spectacular", {})
        if not isinstance(excellent, dict):
            excellent = {}
        if not isinstance(spectacular, dict):
            spectacular = {}
        def threshold(policy, name, default):
            value = num(policy.get(name, default))
            return default if value is None else value
        # Platform margins are fractional values; thresholds live in config.
        if (sharpe > threshold(spectacular, "min_sharpe", 2.0)
                and threshold(spectacular, "min_turnover", 0.10) <= turnover <= threshold(spectacular, "max_turnover", 0.20)
                and fitness > threshold(spectacular, "min_fitness", 2.5)
                and margin > threshold(spectacular, "min_margin", 0.0006)):
            return "SPECTACULAR"
        if (sharpe > threshold(excellent, "min_sharpe", 1.58)
                and threshold(excellent, "min_turnover", 0.049) <= turnover <= threshold(excellent, "max_turnover", 0.30)
                and fitness > threshold(excellent, "min_fitness", 1.5)
                and margin > threshold(excellent, "min_margin", 0.0004)):
            return "EXCELLENT"
        if sharpe > 1.25 and 0.01 <= turnover <= 0.70 and fitness > 1.0:
            return "GOOD"
        return "BELOW_GOOD"

    def _print_summary(self, summary, elapsed=None):
        print(
            f"Round {summary['round']} verdicts: {summary['verdicts']}"
        )
        if summary["best"]:
            b = summary["best"]
            best_id = f" alpha_id={b.get('alpha_id')}" if b.get("alpha_id") else ""
            print(
                f"  best={b['expression'][:70]} sharpe={b.get('sharpe')} "
                f"fitness={b.get('fitness')}{best_id}"
            )
        if elapsed:
            print(f"  elapsed={elapsed:.1f}s")

    # ----------------------------------------------------------- state I/O

    def _load_state(self):
        self.memory.load()
        self.trajectory.load()
        checkpoint_rows = self._search_checkpoint_rows()
        snapshot = SearchSnapshot.from_sources(
            self.trajectory.experiments,
            self.trial_ledger.summarize_cached(
                os.path.join(self.state_dir, "trial_ledger.summary.json")
            ),
            checkpoint_rows,
        )
        self.search_policy.restore(snapshot.allocator_state(
            self.search_policy.allocator.total_budget
        ))
        # In-memory window from previous sessions is authoritative for dedupe
        for exp in self.trajectory.experiments:
            self.memory.remember_expression(exp.expression)

    def search_calibration_report(self):
        """Return a read-only historical Search Calibration report."""
        from .search_calibration import build_search_calibration

        events = list(iter_jsonl_objects(self.trial_ledger.path))
        outcomes = []
        trajectory_path = getattr(self.trajectory, "path", None)
        if trajectory_path and os.path.exists(trajectory_path):
            for row in iter_jsonl_objects(trajectory_path):
                stored = row.get("search_outcome")
                if isinstance(stored, dict):
                    outcomes.append(stored)
        summary = self.trial_ledger.summarize_cached(
            os.path.join(self.state_dir, "trial_ledger.summary.json")
        )
        summary["committed_simulations"] = sum(
            1 for row in events if row.get("phase") == "simulation_committed"
        )
        final_by_proposal = {
            str(row.get("proposal_id")): dict(row.get("settlement") or {})
            for row in events
            if row.get("phase") == "research_outcome_settled" and row.get("proposal_id")
        }
        if final_by_proposal:
            merged = []
            for row in outcomes:
                replacement = final_by_proposal.get(str(row.get("proposal_id")))
                if replacement:
                    merged.append(dict(row, **replacement, outcome_kind="FINAL"))
                else:
                    merged.append(row)
            outcomes = merged
        return build_search_calibration(summary, outcomes=outcomes, events=events)

    def _search_checkpoint_rows(self):
        """Read-only projection of unfinished checkpoints for allocator restore."""
        rows = []
        try:
            entries = os.scandir(self.state_dir)
        except OSError:
            return rows
        with entries:
            for entry in entries:
                if not re.fullmatch(r"round_\d+\.checkpoint\.json", entry.name):
                    continue
                try:
                    with open(entry.path, encoding="utf-8") as handle:
                        payload = json.load(handle)
                    if not payload.get("complete"):
                        rows.extend(payload.get("experiments") or [])
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    continue
        return rows

    def _ensure_loaded(self):
        if not self._loaded:
            self._load_state()
            self._loaded = True

    def _write_sims_results(self, round_no, experiments, total_elapsed_sec=None):
        """自动输出本轮模拟结果（含平台真实 alpha_id + 每模拟真实耗时）到
        .wqb_state/sims_results.json，供外部循环/用户直接读取。

        耗时由程序自身真实计时（Simulator._simulate_one 记录 submit 到定论，
        含替换重试退避），非外部检测估算。
        """
        results = []
        for e in experiments:
            m = e.metrics or {}
            results.append(
                {
                    "id": e.id,
                    "expression": e.expression,
                    "status": e.status,
                    "alpha_id": e.alpha_id,
                    "error": e.error,
                    "elapsed_sec": e.elapsed_sec,
                    "sharpe": m.get("sharpe"),
                    "fitness": m.get("fitness"),
                    "turnover": m.get("turnover"),
                    "returns": m.get("returns"),
                    "drawdown": m.get("drawdown"),
                    "margin": m.get("margin"),
                    "passed": m.get("passed"),
                    "checks": m.get("checks"),
                    "health": e.health,
                    "self_correlation": e.self_correlation or self_correlation_evidence(m),
                    "yearly_evidence": e.yearly_evidence,
                }
            )
        path = os.path.join(self.state_dir, "sims_results.json")
        atomic_write_json_if_changed(
            path,
            {
                "schema_version": SIMULATION_RESULTS_VERSION,
                "created_by_version": CREATED_BY_VERSION,
                "round_no": round_no,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_elapsed_sec": total_elapsed_sec,
                "results": results,
            },
            ignored_keys=("updated_at",),
        )
        print(f"[RESULTS] {len(results)} 个模拟结果 -> {path}")

    def _save_state(self, state):
        os.makedirs(self.state_dir, exist_ok=True)
        if state is not None:
            state_path = os.path.join(self.state_dir, f"round_{state.round_no}.json")
            atomic_write_json_if_changed(state_path, state.to_dict())

    def _write_context(self):
        """Write the compressed research context (shared implementation)."""
        write_context(
            self.state_dir,
            self.memory,
            self.trajectory.recent(self.context_experiments * 2),
            context_experiments=self.context_experiments,
        )
        print(
            f"[CONTEXT] compressed -> {os.path.join(self.state_dir, 'context.md')}"
        )
