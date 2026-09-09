"""Ephemeral research cache keyed by the America/New_York calendar day.

The cache is deliberately process-local.  It is a convenience for the active
factory run, not an evidence store or a recovery mechanism.  Checkpoints own
the only durable execution boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


NEW_YORK = ZoneInfo("America/New_York")


class DailyResearchCache:
    """Keep only today's lightweight result views in memory."""

    def __init__(self, *, clock=None):
        self._clock = clock or __import__("time").time
        self._local_date = None
        self._buckets = {}

    @property
    def local_date(self):
        self._ensure_current_day()
        return self._local_date

    def _today(self):
        return datetime.fromtimestamp(self._clock(), tz=timezone.utc).astimezone(
            NEW_YORK
        ).date().isoformat()

    def _ensure_current_day(self):
        today = self._today()
        if today != self._local_date:
            self._local_date = today
            self._buckets = {
                "simulations": [],
                "submitted_alphas": [],
                "colors": [],
            }

    def _put(self, key, records):
        self._ensure_current_day()
        if not isinstance(records, list):
            raise TypeError(f"{key} 必须是 list")
        current = self._buckets[key]
        positions = {
            str(item.get("alpha_id") or item.get("id")): index
            for index, item in enumerate(current)
            if item.get("alpha_id") is not None or item.get("id") is not None
        }
        for item in records:
            if not isinstance(item, dict):
                continue
            value = dict(item)
            identity = value.get("alpha_id") or value.get("id")
            if identity is not None and str(identity) in positions:
                current[positions[str(identity)]] = value
            else:
                current.append(value)
                if identity is not None:
                    positions[str(identity)] = len(current) - 1

    def _get(self, key):
        self._ensure_current_day()
        return [dict(item) for item in self._buckets[key]]

    def put_simulations(self, records):
        self._put("simulations", records)

    def simulations(self):
        return self._get("simulations")

    def put_submitted_alphas(self, records):
        self._put("submitted_alphas", records)

    def submitted_alphas(self):
        return self._get("submitted_alphas")

    def put_colors(self, records):
        self._put("colors", records)

    def colors(self):
        return self._get("colors")

    def snapshot(self):
        self._ensure_current_day()
        return {
            "local_date": self._local_date,
            "simulations": self.simulations(),
            "submitted_alphas": self.submitted_alphas(),
            "colors": self.colors(),
        }
