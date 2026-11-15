"""Resolve EasyControl / ECUS energy history JSON keys."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

# Prefer gas keys (CT200) then older electric keys.
EASYCONTROL_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "T": ("T",),
    "CH": ("gCh", "eCH"),
    "HW": ("gHw", "eHW"),
}


def _is_numeric(value: Any) -> bool:
    """Whether value can be used as an energy field."""
    if value in (None, "unavailable"):
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def resolve_energy_field_key(row: dict[str, Any], logical_attr: str) -> str | None:
    """Return Bosch JSON key for logical attr (T/CH/HW) from one history row.

    Prefers known candidates in order. Falls back to no match rather than
    substring search (which mis-maps when keys share letters).
    """
    candidates = EASYCONTROL_FIELD_CANDIDATES.get(logical_attr, ())
    for candidate in candidates:
        if candidate in row and _is_numeric(row[candidate]):
            return candidate
    return None


def energy_keys_collide(row: dict[str, Any]) -> bool:
    """True when CH and HW resolve to the same JSON key."""
    ch = resolve_energy_field_key(row, "CH")
    hw = resolve_energy_field_key(row, "HW")
    return bool(ch and hw and ch == hw)


def row_for_day(bosch_data: dict[str, Any], day_key: str) -> dict[str, Any] | None:
    """History row for a dd-mm-YYYY key (dict key or nested d field)."""
    row = bosch_data.get(day_key)
    if isinstance(row, dict):
        return row
    for value in bosch_data.values():
        if isinstance(value, dict) and value.get("d") == day_key:
            return value
    return None


def missing_history_days(
    bosch_data: dict[str, Any] | None,
    *,
    start: datetime,
    end: datetime,
    read_key: str,
) -> list[str]:
    """Days in [start, end) without a numeric value for the energy field.

    Empty result means the gateway holds data for every requested day.
    """
    missing: list[str] = []
    day = start
    data = bosch_data or {}
    while day < end:
        day_key = day.strftime("%d-%m-%Y")
        row = row_for_day(data, day_key)
        if not isinstance(row, dict) or not _is_numeric(row.get(read_key)):
            missing.append(day_key)
        day += timedelta(days=1)
    return missing


def short_statistic_id(entity_id: str) -> str:
    """Build short id from entity_id without stripping every 'sensor' substring.

    ``sensor.energy_central_heating`` → ``energy_central_heating``.
    """
    if entity_id.startswith("sensor."):
        return entity_id[len("sensor.") :].replace(".", "")
    return entity_id.replace(".", "")
