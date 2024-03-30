"""Bosch sensor for Recording sensor in IVT."""

from __future__ import annotations
from datetime import timedelta, datetime
import logging
from .statistic_helper import StatisticHelper

from ..const import SIGNAL_RECORDING_UPDATE_BOSCH, UNITS_CONVERTER, VALUE
from homeassistant.components.recorder.models import (
    StatisticData,
    timestamp_to_datetime_or_none,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class RecordingSensor(StatisticHelper):
    """Representation of Recording Sensor."""

    signal = SIGNAL_RECORDING_UPDATE_BOSCH
    _domain_name = "Recording"

    @property
    def device_name(self) -> str:
        """Device name."""
        return "Recording sensors"

    @property
    def statistic_id(self) -> str:
        """External API statistic ID."""
        if not self._short_id:
            self._short_id = self.entity_id.replace(".", "").replace(
                "sensor", ""
            )
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

        last_hour = get_last_full_hour().replace(
            minute=0, second=0, microsecond=0
        )

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
            _LOGGER.debug(
                "Invoking external statistic function for %s.",
                self.statistic_id,
            )
            async with self._statistic_import_lock:
                await self._insert_statistics()
        else:
            _LOGGER.debug("Old gather data algorithm.")
            await self.async_old_gather_update()

    async def _upsert_past_statistics(
        self, start: datetime, stop: datetime
    ) -> None:
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
        stats_dict = {
            dt_util.as_timestamp(stat["d"]): stat for stat in stats.values()
        }
        # get stats from HA database
        last_stats = await self.get_stats_from_ha_db(
            start_time=start - timedelta(hours=1), end_time=now
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

    def append_statistics(
        self, stats: list, sum: float, now: datetime
    ) -> float:
        statistics_to_push = []
        for stat in stats:
            _date: datetime = stat["d"]
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
        self._last_reset = now
        return sum

    async def _insert_statistics(self) -> None:
        """Insert external statistics."""
        _sum = 0
        now = dt_util.now()
        last_stat = await self.get_last_stat()
        if len(last_stat) == 0 or len(last_stat[self.statistic_id]) == 0:
            _LOGGER.debug(
                "Last stats not exist. Trying to fetch last 30 days of data."
            )
            start_time = now - timedelta(days=30)
            all_stats = await self.fetch_past_data(
                start_time=start_time, stop_time=now
            )
            if not all_stats:
                _LOGGER.warn("Stats not found.")
                return
            all_stats = list(all_stats.values())
            self.append_statistics(stats=all_stats, sum=_sum, now=now)
            return

        start_of_day = dt_util.start_of_local_day()
        last_stat_row = last_stat[self.statistic_id][0]
        last_stat_start = timestamp_to_datetime_or_none(
            last_stat_row.get("start")
        )

        async def get_last_stats_in_ha():
            start_time = dt_util.start_of_local_day(
                last_stat_start
            ) - timedelta(hours=24)
            return await self.get_stats_from_ha_db(
                start_time=start_time,
                end_time=now,
            )

        last_stats = await get_last_stats_in_ha()

        all_stats = []

        async def get_last_stats_from_bosch_api():
            last_stats_row = self.get_last_stats_before_date(
                last_stats=last_stats, day=start_of_day
            )
            start_time = last_stats_row.get("start")
            _sum = last_stats_row.get("sum", 0)
            if isinstance(start_time, float):
                start_time = timestamp_to_datetime_or_none(start_time)
            if not start_time:
                _LOGGER.debug(
                    "Start time not found. %s found %s",
                    self.statistic_id,
                    start_time,
                )
            elif start_time.date() < now.date() - timedelta(days=1):
                diff = now - start_time
                _LOGGER.debug(
                    "Last row of statistic %s found %s, missing %s with current sum %s",
                    self.statistic_id,
                    start_time,
                    diff,
                    _sum,
                )
                bosch_data = await self.fetch_past_data(
                    start_time=start_time, stop_time=now
                )
                return (
                    [
                        row
                        for row in bosch_data.values()
                        if row["d"] > start_time
                    ],
                    _sum,
                )
            _LOGGER.debug(
                "Returning state to put to statistic table %s",
                self._bosch_object.state,
            )
            if self._bosch_object.state:
                # let's get last state once again
                # as bosch state provide whole day always.
                first_date_from_state = self._bosch_object.state[0]
                last_stats_row = self.get_last_stats_before_date(
                    last_stats=last_stats, day=first_date_from_state["d"]
                )
                _sum = last_stats_row.get("sum", 0)
            return self._bosch_object.state, _sum

        if self.statistic_id in last_stats:
            all_stats, _sum = await get_last_stats_from_bosch_api()
            self.append_statistics(stats=all_stats, sum=_sum, now=now)
