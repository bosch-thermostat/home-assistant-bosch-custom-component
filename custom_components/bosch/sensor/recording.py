"""Bosch sensor for Recording sensor in IVT."""
from __future__ import annotations
from datetime import timedelta, datetime
import logging
import json
import asyncio
from .statistic_helper import StatisticHelper

from ..const import SIGNAL_RECORDING_UPDATE_BOSCH, UNITS_CONVERTER, VALUE
from .base import BoschBaseSensor
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    timestamp_to_datetime_or_none,
)
from homeassistant.components.recorder.statistics import (
    get_last_statistics,
    statistics_during_period,
    adjust_statistics,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class RecordingSensor(BoschBaseSensor, StatisticHelper):
    """Representation of Recording Sensor."""

    signal = SIGNAL_RECORDING_UPDATE_BOSCH
    _domain_name = "Recording"

    def __init__(self, new_stats_api: bool = False, **kwargs) -> None:
        """Initialize Recording sensor."""
        self._statistic_import_lock = asyncio.Lock()
        StatisticHelper.__init__(self, new_stats_api=new_stats_api)
        BoschBaseSensor.__init__(self, **kwargs)

    @property
    def device_name(self) -> str:
        """Device name."""
        return "Recording sensors"

    @property
    def statistic_id(self) -> str:
        """External API statistic ID."""
        if not self._short_id:
            self._short_id = self.entity_id.replace(".", "").replace("sensor", "")
        return f"{self._domain_name}:{self._short_id}external".lower()

    def attrs_write(self, last_reset) -> None:
        """Entity attributes write."""
        self._unit_of_measurement = UNITS_CONVERTER.get(
            self._bosch_object.unit_of_measurement
        )
        self._attr_device_class = self._bosch_object.device_class
        self._attr_state_class = self._bosch_object.state_class

        self._attr_last_reset = last_reset
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()

    async def async_old_gather_update(self) -> None:
        """Old async update."""
        data = self._bosch_object.get_property(self._attr_uri)
        now = dt_util.now()
        if not data and not data.get(VALUE):
            return

        def get_last_full_hour() -> datetime:
            return now - timedelta(hours=1)

        last_hour = get_last_full_hour().replace(minute=0, second=0, microsecond=0)

        def find_idx():
            for row in data[VALUE]:
                if row["d"] == last_hour:
                    return row.get(VALUE)
            return STATE_UNAVAILABLE

        self._state = find_idx()
        self.attrs_write(last_reset=last_hour)

    async def async_update(self) -> None:
        """Update state of device."""
        _LOGGER.debug("Update of sensor %s called.", self.unique_id)
        if self._new_stats_api:
            self._unit_of_measurement = UNITS_CONVERTER.get(
                self._bosch_object.unit_of_measurement
            )
            _LOGGER.debug("Invoking external statistic function.")
            async with self._statistic_import_lock:
                await self._insert_statistics()
        else:
            _LOGGER.debug("Old gather data algorithm.")
            await self.async_old_gather_update()

    async def fetch_past_data(self, start_time: datetime, stop_time: datetime) -> list:
        """Rename old entity_id in statistic table."""
        _LOGGER.debug(
            "Attempt to fetch range %s - %s for %s",
            start_time,
            stop_time,
            self.statistic_id,
        )
        return await self._bosch_object.fetch_range(
            start_time=start_time, stop_time=stop_time
        )

    async def _upsert_past_statistics(self, start: datetime, stop: datetime) -> None:
        now = dt_util.now()
        diff = now - start
        if now.day == start.day:
            _LOGGER.warn("Can't upsert today date. Try again tomorrow.")
            return
        if diff > timedelta(days=60):
            _LOGGER.warn(
                "Update more than 60 days might take some time! Component will try to do that anyway!"
            )
        stats = await self.fetch_past_data(
            start_time=start, stop_time=start + timedelta(hours=26)
        )  # return list of objects {'d': datetime with timezone, 'value': 'used kWh in last hour'}
        if not stats:
            _LOGGER.debug("No stats found. Exiting.")
            return
        stats_dict = {dt_util.as_timestamp(stat["d"]): stat for stat in stats}
        # get stats from database
        last_stats = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start - timedelta(hours=1),
            now,
            [self.statistic_id],
            "hour",
            None,
            ["state", "sum"],
        )
        last_stat = last_stats.get(self.statistic_id)
        _sum = last_stat[0].get("sum", 0) if last_stat else 0
        out = {}
        current_time = start
        while current_time <= stop:
            current_ts = dt_util.as_timestamp(current_time)
            if current_ts in stats_dict:
                stat = stats_dict[current_ts]
                _state = +stat["value"]
                _sum += _state  # increase sum
                _LOGGER.debug(
                    "Putting past state to statistic table with id: %s. Date: %s, state: %s, sum: %s.",
                    self.statistic_id,
                    current_time,
                    _state,
                    _sum,
                )
                out[current_ts] = StatisticData(
                    start=current_time,
                    state=_state,
                    sum=_sum,
                )
                stats_dict[current_ts] = None
            else:
                out[current_ts] = StatisticData(
                    start=current_time,
                    state=0,
                    sum=_sum,
                )
            current_time += timedelta(hours=1)

        if last_stat:
            start_ts = dt_util.as_timestamp(start)
            for stat in last_stat:
                _start = stat["start"]
                if stat["start"] in out or start_ts > _start:
                    continue
                _state = stat["state"]
                _sum += _state
                out[stat["start"]] = StatisticData(
                    start=dt_util.utc_from_timestamp(_start),
                    state=_state,
                    sum=_sum,
                )
        self.add_external_stats(stats=list(out.values()))

    async def insert_statistics_range(self, start_time: datetime) -> None:
        """Attempt to put past data into database."""
        start = dt_util.start_of_local_day(start_time)
        stop = start + timedelta(hours=24)  # fetch one day only from API
        async with self._statistic_import_lock:
            await self._upsert_past_statistics(start=start, stop=stop)

    def append_statistics(self, stats, sum, end_time) -> float:
        statistics_to_push = []
        for stat in stats:
            _date: datetime = stat["d"]
            if end_time and _date <= end_time:
                _LOGGER.debug(
                    "Skip re-adding %s day which already exists in database. Last day is %s.",
                    _date,
                    end_time,
                )
                continue
            _state = stat["value"]
            if _state == 0:
                continue
            sum += _state
            _LOGGER.debug(
                "Appending day to statistic table with id: %s. Date: %s, state: %s, sum: %s.",
                self.statistic_id,
                _date,
                _state,
                sum,
            )
            statistics_to_push.append(
                StatisticData(
                    start=_date,
                    state=_state,
                    sum=sum,
                )
            )
        self.add_external_stats(stats=statistics_to_push)
        return sum

    async def _insert_statistics(self) -> None:
        """Insert external statistics."""
        _sum = 0
        last_stats = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics,
            self.hass,
            24,
            self.statistic_id,
            True,
            {"last_reset", "max", "mean", "min", "state", "sum"},
        )
        now = dt_util.now()
        start_of_day = dt_util.start_of_local_day()
        end_time = None
        all_stats = []

        def get_last_stats_row():
            for stat in last_stats[self.statistic_id]:
                tstmp = timestamp_to_datetime_or_none(stat["start"])
                if tstmp and tstmp < start_of_day:
                    return stat
            return last_stats[self.statistic_id][0]

        async def get_last_stats_from_bosch_api(last_stats_row):
            last_stats_row = get_last_stats_row()
            end_time = last_stats_row["end"]
            _sum = last_stats_row["sum"] or 0
            if isinstance(end_time, float):
                end_time = timestamp_to_datetime_or_none(end_time)
            if not end_time:
                _LOGGER.debug(
                    "End time not found. %s found %s", self.statistic_id, end_time
                )
            else:
                diff = now - end_time
                _LOGGER.debug(
                    "Last row of statistic %s found %s, missing %s",
                    self.statistic_id,
                    end_time,
                    diff,
                )
                if diff > timedelta(days=1):
                    if diff > timedelta(days=29):
                        end_time = now - timedelta(days=30)
                    return (
                        await self.fetch_past_data(start_time=end_time, stop_time=now),
                        _sum,
                    )
            _LOGGER.debug(
                "Returning state to put to statistic table %s", self._bosch_object.state
            )
            return self._bosch_object.state, _sum

        if not last_stats:
            _LOGGER.debug("Last stats not exist. Trying to fetch last 30 days of data.")
            start_time = now - timedelta(days=30)
            all_stats = await self.fetch_past_data(start_time=start_time, stop_time=now)
            if not all_stats:
                return
            _sum = 0
        elif self.statistic_id in last_stats:
            last_stats_row = last_stats[self.statistic_id][0]
            all_stats, _sum = await get_last_stats_from_bosch_api(last_stats_row)

        self.append_statistics(stats=all_stats, sum=_sum, end_time=end_time)
