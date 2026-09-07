"""Rebuildable search state view; no writes and no transport dependencies."""

from collections import Counter, defaultdict
import re

from .search_policy import BudgetAllocator, structural_fingerprint


class SearchSnapshot(dict):
    """Compact projection of trajectory, ledger and unfinished checkpoint facts."""

    @classmethod
    def from_sources(cls, experiments=(), ledger_summary=None, checkpoint_experiments=()):
        arms = defaultdict(lambda: {"completed": 0, "pending": 0, "running": 0, "unknown": 0,
                                     "reserved": 0, "reward": 0.0})
        family_counts = Counter()
        structural_counts = Counter()
        candidate_count = 0
        simulation_count = 0
        proposal_states = {}

        def value(item, key, default=None):
            return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)

        def arm(item):
            return BudgetAllocator.arm_key({
                "datasets": value(item, "datasets") or value(item, "dataset_family"),
                "template_family": value(item, "template_family") or value(item, "mechanism_family"),
            })

        seen_items = set()
        for item in list(experiments or ()) + list(checkpoint_experiments or ()):
            candidate_count += 1
            status = str(value(item, "status", "UNKNOWN") or "UNKNOWN").upper()
            key = arm(item)
            proposal_id = str(value(item, "proposal_id") or value(item, "id") or value(item, "expression") or candidate_count)
            if proposal_id in seen_items:
                continue
            seen_items.add(proposal_id)
            proposal_states[proposal_id] = {"arm": key, "status": status}
            family = str(value(item, "template_family") or "unknown")
            family_counts[family] += 1
            structural = structural_fingerprint(value(item, "expression", ""), value(item, "fields_used") or value(item, "fields") or [])
            structural_counts[structural] += 1
            if status in {"DONE", "FAILED", "SKIPPED_STALE", "SKIPPED_UNKNOWN", "SKIPPED"}:
                simulation_count += 1
                if status == "DONE":
                    metrics = value(item, "metrics", {}) or {}
                    try:
                        arms[key]["reward"] += float(metrics.get("fitness", 0.0))
                    except (TypeError, ValueError):
                        pass
                    arms[key]["completed"] += 1
                elif status.startswith("SKIPPED") or status == "FAILED":
                    arms[key]["completed"] += 1
            elif status in {"PENDING", "SUBMITTING"}:
                arms[key]["pending"] += 1
            elif status == "RUNNING":
                arms[key]["running"] += 1
            else:
                arms[key]["unknown"] += 1

        if isinstance(ledger_summary, dict):
            for key, value in (ledger_summary.get("arm_counts") or {}).items():
                if key not in arms and isinstance(value, dict):
                    arms[key].update(value)
            phase_counts = ledger_summary.get("phase_counts") or {}
            candidate_count = max(candidate_count, int(ledger_summary.get("generated_trials", 0) or 0))
            simulation_count = max(simulation_count, int(phase_counts.get("submitted", 0) or 0))

        return cls({
            "schema_version": 1,
            "arms": {key: dict(value) for key, value in arms.items()},
            "family_counts": dict(family_counts),
            "structural_family_counts": dict(structural_counts),
            "candidate_count": candidate_count,
            "simulation_count": simulation_count,
            "proposals": proposal_states,
        })

    def allocator_state(self, total_budget=100):
        consumed = sum(value.get("completed", 0) + value.get("pending", 0) + value.get("running", 0) +
                       value.get("unknown", 0) + value.get("reserved", 0)
                       for value in self.get("arms", {}).values())
        return {
            "total_budget": total_budget,
            "consumed_budget": consumed,
            "arms": self.get("arms", {}),
            "proposals": self.get("proposals", {}),
        }
