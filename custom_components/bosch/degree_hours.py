"""Derived heating degree-hours from outdoor hourly recording."""

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
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .environment_energy import MAX_BACKFILL_DAYS
from .recorder_compat import build_external_statistic_metadata
from .recording_merge import degree_hours

_LOGGER = logging.getLogger(__name__)

OUTDOOR_STAT_ID = "recording:routdoor_t1external"
HDH_STAT_ID = "recording:rheatingdegreehoursexternal"
BASE_C = 15.0
HDH_UNIT = "°C·h"

__all__ = [
    "BASE_C",
    "HDH_STAT_ID",
    "async_backfill_hdh",
    "async_update_hdh_tail",
    "async_write_hdh_range",
    "build_hdh_statistics",
    "degree_hours",
]


def hdh_metadata() -> Any:
    """Recorder metadata for the derived HDH series."""
    return build_external_statistic_metadata(
        name="Stats rHeatingDegreeHours",
        source="recording",
        statistic_id=HDH_STAT_ID,
        unit_of_measurement=HDH_UNIT,
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


def build_hdh_statistics(
    *,
    outdoor_rows: list[dict[str, Any]],
    anchor_sum: float,
    start: datetime,
    end: datetime,
) -> list[StatisticData]:
    """Build HDH StatisticData rows for [start, end).

    Missing outdoor skips the hour.
    """
    outdoor = _hour_map(outdoor_rows)
    starts = sorted(
        ts
        for ts in outdoor
        if dt_util.utc_from_timestamp(ts) >= start
        and dt_util.utc_from_timestamp(ts) < end
    )
    running = float(anchor_sum)
    out: list[StatisticData] = []
    for ts in starts:
        hdh = degree_hours(_row_state(outdoor.get(ts)), base_c=BASE_C)
        if hdh is None:
            continue
        running += hdh
        out.append(
            StatisticData(
                start=dt_util.utc_from_timestamp(ts),
                state=hdh,
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


async def async_write_hdh_range(
    hass: HomeAssistant,
    *,
    start: datetime,
    end: datetime,
) -> int:
    """Recompute and write HDH stats for [start, end). Returns hour count."""
    if end <= start:
        return 0
    lookback_start = start - timedelta(hours=1)
    raw = await _async_stats(
        hass,
        [OUTDOOR_STAT_ID, HDH_STAT_ID],
        lookback_start,
        end,
    )
    outdoor_rows = raw.get(OUTDOOR_STAT_ID, [])
    hdh_rows = raw.get(HDH_STAT_ID, [])
    anchor = 0.0
    start_ts = dt_util.as_timestamp(start)
    for row in hdh_rows:
        ts = row.get("start")
        if ts is None or float(ts) >= start_ts:
            continue
        try:
            anchor = float(row.get("sum") or 0.0)
        except (TypeError, ValueError):
            anchor = 0.0
    stats = build_hdh_statistics(
        outdoor_rows=outdoor_rows,
        anchor_sum=anchor,
        start=start,
        end=end,
    )
    if not stats:
        return 0
    async_add_external_statistics(hass, hdh_metadata(), stats)
    return len(stats)


async def async_update_hdh_tail(hass: HomeAssistant, *, hours: int = 48) -> int:
    """Refresh recent HDH hours after a recording pull."""
    now = dt_util.now()
    end = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    start = end - timedelta(hours=max(hours, 2))
    return await async_write_hdh_range(hass, start=start, end=end)


async def async_backfill_hdh(
    hass: HomeAssistant,
    *,
    start_date: date,
    end_date: date,
) -> int:
    """Backfill HDH stats for inclusive local dates. Returns hours written.

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
        part = await async_write_hdh_range(hass, start=start, end=end)
        written += part
        _LOGGER.debug(
            "HDH backfill chunk %s..%s wrote %s hours",
            chunk_start,
            chunk_end,
            part,
        )
        chunk_start = chunk_end + timedelta(days=1)
    _LOGGER.info(
        "Backfilled %s HDH hours from %s to %s",
        written,
        start_date,
        end_date,
    )
    return written
