"""Parse KM200 temperature recording hours (keep valid 0 °C)."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def hour_value(recording: dict[str, Any]) -> float | None:
    """Average for one hour, or None when sample count is 0."""
    try:
        count = float(recording.get("c") or 0)
        raw_y = float(recording.get("y") or 0)
    except (TypeError, ValueError):
        return None
    if count == 0:
        return None
    return round(raw_y / count, 1)


def parse_temperature_day(
    payload: dict[str, Any] | None,
    *,
    day: datetime,
) -> list[dict[str, Any]]:
    """Build ``{d, value}`` rows for one local day; keep 0 °C when ``c > 0``."""
    if not payload:
        return []
    rows_raw = payload.get("recording")
    if not isinstance(rows_raw, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, recording in enumerate(rows_raw):
        if not isinstance(recording, dict):
            continue
        val = hour_value(recording)
        if val is None:
            continue
        stamp = day.replace(hour=idx, minute=0, second=0, microsecond=0)
        out.append({"d": stamp, "value": val})
    return out


def is_temperature_unit(unit: str | None) -> bool:
    """Whether this recording uses °C (not energy)."""
    if not unit:
        return False
    return unit in ("°C", "C", "°F", "F")


def keep_hour_for_lts(
    state: float,
    *,
    is_temperature: bool,
    already_recorded: bool = False,
) -> bool:
    """Whether an hour state belongs in long-term statistics.

    Energy kWh zeros are empty hours and stay omitted until revised.
    Temperature zeros are real samples and are always kept.
    """
    if state != 0:
        return True
    return is_temperature or already_recorded
