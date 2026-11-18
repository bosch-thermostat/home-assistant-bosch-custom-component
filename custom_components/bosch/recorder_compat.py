"""Home Assistant recorder statistics metadata helpers (HA 2026.11+)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticMetaData
from homeassistant.core import HomeAssistant

try:
    from homeassistant.components.recorder.statistics import StatisticMeanType
except ImportError:  # pragma: no cover - older HA
    StatisticMeanType = None

_LOGGER = logging.getLogger(__name__)

_UNIT_CLASS_MAP = {
    "kWh": "energy",
    "Wh": "energy",
    "kW": "power",
    "m³": "volume",
    "m3": "volume",
}

# Probe once: HA 2026.11+ rejects has_mean on StatisticMetaData construction.
_HAS_MEAN_SUPPORTED: bool | None = None


def _supports_has_mean() -> bool:
    """Whether StatisticMetaData still accepts has_mean."""
    global _HAS_MEAN_SUPPORTED
    if _HAS_MEAN_SUPPORTED is not None:
        return _HAS_MEAN_SUPPORTED
    if StatisticMeanType is None:
        _HAS_MEAN_SUPPORTED = True
        return True
    try:
        StatisticMetaData(
            has_mean=False,
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name="probe",
            source="energy",
            statistic_id="energy:probeexternal",
            unit_of_measurement="kWh",
            unit_class="energy",
        )
        _HAS_MEAN_SUPPORTED = True
    except TypeError:
        _HAS_MEAN_SUPPORTED = False
    return _HAS_MEAN_SUPPORTED


def unit_class_for(unit: str | None) -> str | None:
    """Map unit of measurement to recorder unit_class."""
    if not unit:
        return None
    return _UNIT_CLASS_MAP.get(unit)


def build_external_statistic_metadata(
    *,
    name: str,
    source: str,
    statistic_id: str,
    unit_of_measurement: str | None,
) -> StatisticMetaData:
    """Build StatisticMetaData safe for HA 2026.11 (mean_type + unit_class)."""
    meta: dict[str, Any] = {
        "has_sum": True,
        "name": name,
        "source": source,
        "statistic_id": statistic_id,
        "unit_of_measurement": unit_of_measurement,
        "unit_class": unit_class_for(unit_of_measurement),
    }
    if StatisticMeanType is not None:
        meta["mean_type"] = StatisticMeanType.NONE
    if _supports_has_mean():
        meta["has_mean"] = False
    return StatisticMetaData(**meta)


async def async_clear_statistics_range(
    hass: HomeAssistant,
    statistic_ids: list[str],
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> bool:
    """Clear statistic rows. Prefer a time range when HA supports it.

    Returns True when a clear was queued. Returns False when range clear is
    required but unavailable (never falls back to a full wipe).
    """
    instance = get_instance(hass)
    clear = getattr(instance, "async_clear_statistics", None)
    if clear is None:
        _LOGGER.warning("Recorder clear_statistics is unavailable.")
        return False

    done = asyncio.Event()

    def _on_done() -> None:
        hass.loop.call_soon_threadsafe(done.set)

    try:
        if start_time is not None and end_time is not None:
            clear(
                statistic_ids,
                start_time=start_time,
                end_time=end_time,
                on_done=_on_done,
            )
        else:
            # Full clear only when caller passes no range (explicit service).
            clear(statistic_ids, on_done=_on_done)
    except TypeError:
        if start_time is not None:
            _LOGGER.warning(
                "Range clear not supported; refusing full wipe for %s",
                statistic_ids,
            )
            return False
        clear(statistic_ids, on_done=_on_done)

    try:
        async with asyncio.timeout(10):
            await done.wait()
    except TimeoutError:
        _LOGGER.debug("clear_statistics timed out for %s", statistic_ids)
    return True
