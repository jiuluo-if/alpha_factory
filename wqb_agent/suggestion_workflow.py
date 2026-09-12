"""Read-only suggestion/discovery round orchestration."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .artifacts import atomic_write_json_if_changed
from .context import key_experiments
from .research_guard import ResearchLoopGuard


@dataclass(frozen=True)
class SuggestionHooks:
    """Agent-owned operations needed without giving the workflow an Agent."""

    ensure_loaded: Callable[[], None]
    next_round_no: Callable[[], int]
    epoch_label: Callable[[int], str]
    form_research_space: Callable[[int], dict[str, Any]]
    trusted_current_best: Callable[[], Mapping[str, Any] | None]
    ensure_best_field: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    optimizer_gate_report: Callable[[], Mapping[str, Any]]
    fallback_templates: Callable[[], Sequence[Mapping[str, Any]]]
    # metric-aware bounded optimizer context；缺省时回落纯 gate 计数，保持兼容。
    optimizer_context: Callable[[], Mapping[str, Any]] | None = None


class SuggestionWorkflow:
    """Own the read/discovery side of one suggestion round.

    The workflow deliberately receives no transport, simulator or checkpoint
    dependency.  It can discover platform fields and emit the derived
    suggestions artifact, but it has no path to submit a Simulation.
    """

    def __init__(
        self,
        *,
        discovery,
        memory,
        trajectory,
        alpha_factory,
        state_dir: str,
        fields_per_discovery: int,
        context_experiments: int,
        simulation_settings: Mapping[str, Any],
        operator_reference: Mapping[str, Any],
        hooks: SuggestionHooks,
    ):
        self.discovery = discovery
        self.memory = memory
        self.trajectory = trajectory
        self.alpha_factory = alpha_factory
        self.state_dir = state_dir
        self.fields_per_discovery = fields_per_discovery
        self.context_experiments = context_experiments
        self.simulation_settings = simulation_settings
        self.operator_reference = operator_reference
        self.hooks = hooks

    def _optimizer_context(self):
        """优先给出 metric-aware bounded context；缺 hook 时回落 gate 计数。"""
        hook = getattr(self.hooks, "optimizer_context", None)
        if callable(hook):
            return hook()
        return self.hooks.optimizer_gate_report()

    def run(self, round_no=None):
        """Discover fields and write the suggestion bundle without Simulation."""
        self.hooks.ensure_loaded()
        round_no = round_no or self.hooks.next_round_no()
        research_space = self.hooks.form_research_space(round_no)
        research_space = self.rotate_stalled_research_space(
            research_space, round_no
        )
        research_space["_round"] = round_no
        fields = self.discovery.discover(
            research_space, target_count=self.fields_per_discovery
        )
        if not fields:
            fallback_templates = list(self.hooks.fallback_templates())
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
        if research_space.get("parent_best") and self.hooks.trusted_current_best():
            fields = self.hooks.ensure_best_field(fields)

        bundle = {
            "round_no": round_no,
            "epoch_label": self.hooks.epoch_label(round_no),
            "research_space": research_space,
            "fields": [self._field_bundle(field) for field in fields],
            "context": self.memory.context(
                recent_experiments=key_experiments(
                    self.trajectory.recent(self.context_experiments * 2)
                )
            ),
            "simulation_settings": self.simulation_settings,
            "field_source": self.discovery.source_provenance(),
            "operator_reference": self.operator_reference,
            "alpha_templates": self.alpha_factory.catalog(),
            "research_guard": ResearchLoopGuard(
                self.trajectory.experiments
            ).snapshot(),
            "optimizer_context": self._optimizer_context(),
            "field_selection": {
                "max_alpha_count": self.discovery.max_alpha_count,
                "excluded_high_usage": self.discovery.last_excluded_high_usage,
                "excluded_unknown_usage": self.discovery.last_excluded_unknown_usage,
                "platform_dedupe": self.discovery.platform_dedupe_view(),
                "dataset_selection": self.discovery.last_dataset_selection,
                "catalog_provenance": self.discovery.source_provenance(),
            },
            "dataset_selection": self.discovery.last_dataset_selection,
            "catalog_provenance": self.discovery.source_provenance(),
        }
        os.makedirs(self.state_dir, exist_ok=True)
        path = os.path.join(self.state_dir, "suggestions.json")
        atomic_write_json_if_changed(path, bundle)
        print(f"\n=== Suggestion round {round_no} ({self.hooks.epoch_label(round_no)}) ===")
        print(f"Research space: {research_space['statement']}")
        print(f"Fields ({len(fields)}): {[f['id'] for f in fields]}")
        print(f"Bundle written: {path}")
        print("-> read suggestions.json + context.md, write proposals.json, "
              "then run python main.py run-proposals")
        return bundle

    def rotate_stalled_research_space(
        self, research_space, round_no, window=40, concentration=0.8
    ):
        """Avoid another round on a recently exhausted dataset."""
        # RESEARCH_POLICY: heuristic only; this is not a BRAIN invariant.
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
        counts: dict[str, int] = {}
        for dataset in observed:
            counts[dataset] = counts.get(dataset, 0) + 1
        dominant, dominant_count = max(counts.items(), key=lambda item: item[1])
        if dominant not in datasets or dominant_count / len(observed) < concentration:
            return research_space

        candidates = list(self.hooks.fallback_templates())
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

    def _field_bundle(self, field):
        return {
            "id": field["id"],
            "name": field.get("name", ""),
            "description": field.get("description", ""),
            "dataset": field.get("dataset"),
            "type": field.get("type"),
            "coverage": field.get("coverage"),
            "frequency": field.get("frequency"),
            "alpha_count": field.get("alpha_count"),
            "platform_dedupe": field.get("platform_dedupe"),
            "semantic_status": field.get("semantic_status", "UNKNOWN"),
            "field_source": field.get("field_source") or self.discovery.source_provenance(),
            "field_ref": {
                "dataset": field.get("dataset"),
                "id": field.get("id"),
            },
        }
