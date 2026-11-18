"""Compressor-on time attribution per heating circuit / DHW / pool."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

MAX_TICK_SECONDS = 300.0


def sinks_from_snapshot(snapshot: Any) -> list[str]:
    """Active energy sinks while the compressor is on.

    hc1 is skipped when another heating circuit also requests (buffer follows).
    Multiple sinks (e.g. dhw + hc2) share the tick equally.
    """
    if not getattr(snapshot, "compressor_on", False):
        return []
    sinks: list[str] = []
    if getattr(snapshot, "dhw_charging", False):
        sinks.append("dhw")
    circuits = list(getattr(snapshot, "requesting_circuits", []) or [])
    leaders = [cid for cid in circuits if cid != "hc1"]
    sinks.extend(leaders if leaders else circuits)
    if getattr(snapshot, "pool_heating", False):
        sinks.append("pool")
    if not sinks:
        sinks.append("other")
    return sinks


@dataclass
class HeatpumpSplitAccumulator:
    """Accumulate compressor-on seconds per sink for the local day."""

    seconds: dict[str, float] = field(default_factory=dict)
    day: date | None = None
    last_tick: datetime | None = None

    def reset_day(self, day: date) -> None:
        """Clear counters for a new local calendar day."""
        self.seconds = {}
        self.day = day
        self.last_tick = None

    def ensure_day(self, now: datetime) -> None:
        """Reset when the local date changes."""
        today = now.date()
        if self.day != today:
            self.reset_day(today)

    def add_tick(self, snapshot: Any, now: datetime) -> None:
        """Attribute elapsed time since last tick to current sinks."""
        self.ensure_day(now)
        previous = self.last_tick
        self.last_tick = now
        if previous is None:
            return
        dt = (now - previous).total_seconds()
        if dt <= 0:
            return
        if dt > MAX_TICK_SECONDS:
            dt = MAX_TICK_SECONDS
        sinks = sinks_from_snapshot(snapshot)
        if not sinks:
            return
        share = dt / len(sinks)
        for sink in sinks:
            self.seconds[sink] = self.seconds.get(sink, 0.0) + share

    def total_seconds(self) -> float:
        """Sum of compressor-attributed seconds today."""
        return float(sum(self.seconds.values()))

    def minutes(self, sink: str) -> float | None:
        """Compressor minutes today for one sink."""
        value = self.seconds.get(sink)
        if value is None or value <= 0:
            if self.total_seconds() <= 0:
                return None
            return 0.0
        return round(value / 60.0, 1)

    def share_percent(self, sink: str) -> float | None:
        """Percent of compressor-on time for one sink."""
        total = self.total_seconds()
        if total <= 0:
            return None
        return round(100.0 * self.seconds.get(sink, 0.0) / total, 1)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for Home Assistant Store."""
        return {
            "day": self.day.isoformat() if self.day else None,
            "seconds": dict(self.seconds),
            "last_tick": self.last_tick.isoformat() if self.last_tick else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> HeatpumpSplitAccumulator:
        """Restore from Store payload."""
        acc = cls()
        if not data:
            return acc
        day_raw = data.get("day")
        if day_raw:
            acc.day = date.fromisoformat(str(day_raw))
        seconds = data.get("seconds") or {}
        if isinstance(seconds, dict):
            acc.seconds = {
                str(key): float(value)
                for key, value in seconds.items()
                if value is not None
            }
        tick_raw = data.get("last_tick")
        if tick_raw:
            acc.last_tick = datetime.fromisoformat(str(tick_raw))
        return acc
