"""Derived heat-pump environment energy statistics (produced − compressor)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    statistics_during_period,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .recorder_compat import build_external_statistic_metadata
from .recording_merge import environment_kwh

_LOGGER = logging.getLogger(__name__)

PRODUCED_STAT_ID = "recording:routputproducedexternal"
COMPRESSOR_STAT_ID = "recording:rcompressorexternal"
ENVIRONMENT_STAT_ID = "recording:renvironmentexternal"
MAX_BACKFILL_DAYS = 400

__all__ = [
    "ENVIRONMENT_STAT_ID",
    "async_backfill_environment",
    "async_update_environment_tail",
    "async_write_environment_range",
    "build_environment_statistics",
    "environment_kwh",
]


def environment_metadata() -> Any:
    """Recorder metadata for the derived environment series."""
    return build_external_statistic_metadata(
        name="Stats rEnvironment",
        source="recording",
        statistic_id=ENVIRONMENT_STAT_ID,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )


def _hour_map(rows: list[dict[str, Any]] | None) -> dict[float, dict[str, Any]]:
    """Map statistic start timestamp → row."""
    out: dict[float, dict[str, Any]] = {}
    for row in rows or []:
        start = row.get("start")
        if start is None:
            continue
        out[float(start)] = row
    return out


def _row_state(row: dict[str, Any] | None) -> float | None:
    """Numeric state from a statistics row."""
    if not row:
        return None
    raw = row.get("state")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def build_environment_statistics(
    *,
    produced_rows: list[dict[str, Any]],
    compressor_rows: list[dict[str, Any]],
    anchor_sum: float,
    start: datetime,
    end: datetime,
) -> list[StatisticData]:
    """Build environment StatisticData rows for [start, end).

    Missing produced skips the hour. Missing compressor counts as 0.
    """
    produced = _hour_map(produced_rows)
    compressor = _hour_map(compressor_rows)
    starts = sorted(
        ts
        for ts in produced
        if dt_util.utc_from_timestamp(ts) >= start
        and dt_util.utc_from_timestamp(ts) < end
    )
    running = float(anchor_sum)
    out: list[StatisticData] = []
    for ts in starts:
        env = environment_kwh(_row_state(produced.get(ts)), _row_state(compressor.get(ts)))
        if env is None:
            continue
        running += env
        out.append(
            StatisticData(
                start=dt_util.utc_from_timestamp(ts),
                state=env,
                sum=running,
            )
        )
    return out


async def _async_stats(
    hass: HomeAssistant,
    statistic_ids: list[str],
    start: datetime,
    end: datetime,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch hourly statistics for the given ids."""
    return await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        end,
        statistic_ids,
        "hour",
        None,
        {"state", "sum"},
    )


async def async_write_environment_range(
    hass: HomeAssistant,
    *,
    start: datetime,
    end: datetime,
) -> int:
    """Recompute and write environment stats for [start, end). Returns hour count."""
    if end <= start:
        return 0
    lookback_start = start - timedelta(hours=1)
    raw = await _async_stats(
        hass,
        [PRODUCED_STAT_ID, COMPRESSOR_STAT_ID, ENVIRONMENT_STAT_ID],
        lookback_start,
        end,
    )
    produced_rows = raw.get(PRODUCED_STAT_ID, [])
    compressor_rows = raw.get(COMPRESSOR_STAT_ID, [])
    env_rows = raw.get(ENVIRONMENT_STAT_ID, [])
    anchor = 0.0
    start_ts = dt_util.as_timestamp(start)
    for row in env_rows:
        ts = row.get("start")
        if ts is None or float(ts) >= start_ts:
            continue
        try:
            anchor = float(row.get("sum") or 0.0)
        except (TypeError, ValueError):
            anchor = 0.0
    stats = build_environment_statistics(
        produced_rows=produced_rows,
        compressor_rows=compressor_rows,
        anchor_sum=anchor,
        start=start,
        end=end,
    )
    if not stats:
        return 0
    async_add_external_statistics(hass, environment_metadata(), stats)
    return len(stats)


async def async_update_environment_tail(hass: HomeAssistant, *, hours: int = 48) -> int:
    """Refresh recent environment hours after a recording pull."""
    now = dt_util.now()
    end = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    start = end - timedelta(hours=max(hours, 2))
    return await async_write_environment_range(hass, start=start, end=end)


async def async_backfill_environment(
    hass: HomeAssistant,
    *,
    start_date: date,
    end_date: date,
) -> int:
    """Backfill environment stats for inclusive local dates. Returns hours written.

    Large ranges are processed in ``MAX_BACKFILL_DAYS`` chunks so the recorder
    query stays bounded.
    """
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    written = 0
    chunk_start = start_date
    while chunk_start <= end_date:
        chunk_end = min(
            chunk_start + timedelta(days=MAX_BACKFILL_DAYS - 1),
            end_date,
        )
        start = dt_util.start_of_local_day(
            datetime.combine(chunk_start, datetime.min.time())
        )
        end = dt_util.start_of_local_day(
            datetime.combine(chunk_end, datetime.min.time())
        ) + timedelta(days=1)
        part = await async_write_environment_range(hass, start=start, end=end)
        written += part
        _LOGGER.debug(
            "Environment backfill chunk %s..%s wrote %s hours",
            chunk_start,
            chunk_end,
            part,
        )
        chunk_start = chunk_end + timedelta(days=1)
    _LOGGER.info(
        "Backfilled %s environment hours from %s to %s",
        written,
        start_date,
        end_date,
    )
    return written
