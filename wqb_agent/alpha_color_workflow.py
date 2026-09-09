"""Explicit remote Alpha color metadata synchronization workflow."""

from __future__ import annotations

from .alpha_colors import (
    PROJECT_COLOR_OWNER,
    _value,
    _evidence_summary,
    classify_alpha_color,
)


class AlphaColorWorkflow:
    """Synchronize derived color classifications to remote Alpha metadata.

    The workflow deliberately receives operation-shaped transport hooks rather
    than a Client or Agent.  It owns remote read/decision/write orchestration;
    color policy remains in :mod:`alpha_colors`.
    """

    def __init__(self, *, get_alpha, set_alpha_color, classifier=classify_alpha_color):
        self._get_alpha = get_alpha
        self._set_alpha_color = set_alpha_color
        self._classifier = classifier

    def sync(self, experiments, *, dry_run=False):
        """Return color changes, optionally applying verified metadata writes."""
        # There is currently no durable ownership source.  Keep this local
        # mapping as the compatibility shape of the old implementation, but
        # never infer ownership from a remote color or create a sidecar.
        local = {}
        results = []
        seen = set()
        for experiment in experiments or ():
            alpha_id = _value(experiment, "alpha_id")
            if not alpha_id or str(alpha_id) in seen:
                continue
            seen.add(str(alpha_id))
            classification = self._classifier(experiment)
            prior = local.get(str(alpha_id))
            owned = (
                isinstance(prior, dict)
                and prior.get("color_managed_by") == PROJECT_COLOR_OWNER
            )
            desired = classification
            if desired is None and not owned:
                continue

            remote = self._get_alpha(str(alpha_id))
            old_color = remote.get("color") if isinstance(remote, dict) else None
            action = "NOOP"
            if old_color == desired:
                new_color = old_color
            elif not owned and old_color is not None:
                action = "OWNERSHIP_CONFLICT"
                new_color = old_color
            elif dry_run:
                action = "DRY_RUN_PATCH"
                new_color = desired
            else:
                payload = self._set_alpha_color(
                    str(alpha_id), desired, verify=True
                )
                if not isinstance(payload, dict):
                    raise ValueError(
                        f"Alpha {alpha_id} color readback unavailable"
                    )
                new_color = payload.get("color")
                if new_color != desired:
                    raise ValueError(
                        f"Alpha {alpha_id} color readback mismatch: "
                        f"{new_color!r} != {desired!r}"
                    )
                action = "PATCHED"
            results.append({
                "alpha_id": str(alpha_id),
                "old_color": old_color,
                "new_color": new_color,
                "classification": classification,
                "evidence": _evidence_summary(experiment, classification),
                "action": action,
            })
        return results
