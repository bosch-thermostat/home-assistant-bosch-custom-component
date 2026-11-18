"""Recent-window repair for EasyControl energy external statistics."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, cast

from homeassistant.util import dt as dt_util

from .energy_fields import missing_history_days, row_for_day
from .recorder_compat import async_clear_statistics_range

if TYPE_CHECKING:
    from .sensor.energy import EnergySensor

_LOGGER = logging.getLogger(__name__)


async def repair_energy_statistics_window(
    entity: EnergySensor, *, days: int
) -> bool:
    """Clear and re-import the last N full days for one energy statistic series.

    Never includes today. Uses range clear when available; refuses a full wipe.
    Returns whether a re-import was performed.
    """
    if not entity._uses_external_statistics:
        return False
    days = max(0, min(int(days), 30))
    if days <= 0:
        return False

    now = dt_util.now()
    start = dt_util.start_of_local_day(now - timedelta(days=days))
    end = dt_util.start_of_local_day(now)  # exclusive end = start of today

    if not entity._resolve_read_key():
        _LOGGER.warning("Repair skipped; energy field unresolved for %s", entity.name)
        return False

    statistic_id = entity.statistic_id
    bosch_data = await entity.fetch_past_data(
        start_time=start, stop_time=end + timedelta(hours=1)
    )
    missing = missing_history_days(
        bosch_data,
        start=start,
        end=end,
        read_key=entity._attr_read_key or "",
    )
    if missing:
        _LOGGER.warning(
            "Repair aborted for %s: gateway missing %s of %s days (%s)",
            statistic_id,
            len(missing),
            days,
            ", ".join(missing[:10]),
        )
        return False

    _LOGGER.info(
        "Repairing energy statistics %s for %s days (%s .. %s)",
        statistic_id,
        days,
        start,
        end,
    )

    cleared = await async_clear_statistics_range(
        entity.hass,
        [statistic_id],
        start_time=start,
        end_time=end,
    )
    if not cleared:
        _LOGGER.warning(
            "Repair aborted for %s: range clear unavailable", statistic_id
        )
        return False

    # Sum anchor strictly before the repair window.
    before = await entity.get_stats_from_ha_db(
        start_time=start - timedelta(hours=48),
        end_time=start,
    )
    anchor = entity.get_last_stats_before_date(
        last_stats=before,
        day=start,
        allow_window_fallback=False,
    )
    _sum = cast(float, anchor.get("sum", 0.0) or 0.0)

    day = start
    while day < end:
        day_key = day.strftime("%d-%m-%Y")
        row = row_for_day(bosch_data, day_key)
        if isinstance(row, dict) and entity._attr_read_key in row:
            try:
                daily = float(row[entity._attr_read_key])
            except (TypeError, ValueError):
                day += timedelta(days=1)
                continue
            hourly = round(daily / 24, 2)
            _sum, stats = entity._generate_easycontrol_statistics(
                start=day,
                end=day + timedelta(days=1),
                single_value=hourly,
                init_value=_sum,
            )
            entity.add_external_stats(stats=stats)
        day += timedelta(days=1)

    _LOGGER.info("Repair finished for %s with sum=%s", statistic_id, _sum)
    return True


async def clear_energy_statistics(
    entity: EnergySensor,
    *,
    reimport: bool = False,
) -> None:
    """Fully clear one statistic series; optionally bootstrap from fetch_all."""
    statistic_id = entity.statistic_id
    await async_clear_statistics_range(entity.hass, [statistic_id])
    if not reimport:
        return
    entity._resolve_read_key()
    all_stats = list((await entity._bosch_object.fetch_all()).values())
    if all_stats:
        entity.append_statistics(stats=all_stats, sum=0.0)
