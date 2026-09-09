"""Local weekly Simulation admission quota with a New York day refresh.

Only counters and calendar metadata are represented here.  Simulation
results, Alpha identifiers, and evidence must never enter this object.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


class QuotaExceeded(RuntimeError):
    """Raised when a reservation would cross a local daily or weekly cap."""


class WeeklySimulationQuota:
    """Normalize and reserve a daily/weekly counter state."""

    SCHEMA_VERSION = 1
    TIMEZONE = "America/New_York"

    def __init__(self, *, weekly_cap=11200, daily_cap=1600, clock=None):
        self.weekly_cap = self._cap(weekly_cap, "weekly_cap")
        self.daily_cap = self._cap(daily_cap, "daily_cap")
        if self.daily_cap > self.weekly_cap:
            raise ValueError("daily_cap 不得超过 weekly_cap")
        self._clock = clock or __import__("time").time

    @staticmethod
    def _cap(value, name):
        if isinstance(value, bool):
            raise ValueError(f"{name} 必须是非负整数")
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} 必须是非负整数") from exc
        if normalized < 0:
            raise ValueError(f"{name} 必须是非负整数")
        return normalized

    @staticmethod
    def _counter(value, name):
        if isinstance(value, bool):
            raise ValueError(f"{name} 必须是非负整数")
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} 必须是非负整数") from exc
        if normalized < 0:
            raise ValueError(f"{name} 必须是非负整数")
        return normalized

    def _local_now(self):
        return datetime.fromtimestamp(self._clock(), tz=UTC).astimezone(
            NEW_YORK
        )

    def _dates(self):
        current = self._local_now().date()
        return current.isoformat(), current.fromisocalendar(
            current.isocalendar().year,
            current.isocalendar().week,
            1,
        ).isoformat()

    def _state(self, local_date, week_start, daily_reserved, weekly_reserved):
        return {
            "schema_version": self.SCHEMA_VERSION,
            "timezone": self.TIMEZONE,
            "local_date": local_date,
            "week_start": week_start,
            "daily_cap": self.daily_cap,
            "weekly_cap": self.weekly_cap,
            "daily_reserved": daily_reserved,
            "weekly_reserved": weekly_reserved,
        }

    def initial_state(self):
        local_date, week_start = self._dates()
        return self._state(local_date, week_start, 0, 0)

    def normalize_state(self, state=None):
        if state is None or state == {}:
            return self.initial_state()
        if not isinstance(state, dict):
            raise ValueError("quota state 必须是对象")
        try:
            daily_reserved = self._counter(state["daily_reserved"], "daily_reserved")
            weekly_reserved = self._counter(state["weekly_reserved"], "weekly_reserved")
            local_date = str(state["local_date"])
            week_start = str(state["week_start"])
        except KeyError as exc:
            raise ValueError(f"quota state 缺少 {exc.args[0]}") from exc
        current_date, current_week = self._dates()
        if week_start != current_week:
            return self._state(current_date, current_week, 0, 0)
        if weekly_reserved > self.weekly_cap:
            raise ValueError("weekly_reserved 超过 weekly_cap")
        if local_date != current_date:
            daily_reserved = 0
        if daily_reserved > self.daily_cap:
            raise ValueError("daily_reserved 超过 daily_cap")
        return self._state(current_date, current_week, daily_reserved, weekly_reserved)

    def remaining(self, state=None):
        normalized = self.normalize_state(state)
        return min(
            self.daily_cap - normalized["daily_reserved"],
            self.weekly_cap - normalized["weekly_reserved"],
        )

    def reserve(self, state, count):
        normalized = self.normalize_state(state)
        amount = self._counter(count, "count")
        if amount > self.remaining(normalized):
            raise QuotaExceeded(
                f"Simulation quota exceeded: requested={amount}, "
                f"remaining={self.remaining(normalized)}"
            )
        normalized["daily_reserved"] += amount
        normalized["weekly_reserved"] += amount
        return normalized

    def release(self, state, count):
        normalized = self.normalize_state(state)
        amount = self._counter(count, "count")
        normalized["daily_reserved"] = max(
            0, normalized["daily_reserved"] - amount
        )
        normalized["weekly_reserved"] = max(
            0, normalized["weekly_reserved"] - amount
        )
        return normalized
