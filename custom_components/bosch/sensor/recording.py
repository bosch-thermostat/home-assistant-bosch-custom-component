"""Bosch sensor for Recording sensor in IVT."""
from datetime import timedelta
import datetime
import logging

from .statistic_helper import StatisticHelper

from ..const import SIGNAL_RECORDING_UPDATE_BOSCH, UNITS_CONVERTER, VALUE
from .base import BoschBaseSensor
from homeassistant.components.recorder.models import (
    StatisticData,
)
from homeassistant.components.recorder.statistics import (
    get_last_statistics,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class RecordingSensor(BoschBaseSensor, StatisticHelper):
    """Representation of Recording Sensor."""

    signal = SIGNAL_RECORDING_UPDATE_BOSCH
    _domain_name = "Recording"

    def __init__(
        self, new_stats_api: bool = False, fetch_past_days: bool = False, **kwargs
    ) -> None:
        """Initialize Recording sensor."""
        StatisticHelper.__init__(
            self, new_stats_api=new_stats_api, fetch_past_days=fetch_past_days
        )
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

        def get_last_full_hour() -> datetime.datetime:
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
            _LOGGER.debug("Invoking external statistic function.")
            await self._insert_statistics()
        else:
            _LOGGER.debug("Old gather data algorithm.")
            await self.async_old_gather_update()

    async def fetch_past_data(
        self, start_time: datetime.datetime, stop_time: datetime.datetime
    ) -> list:
        """Rename old entity_id in statistic table."""
        return await self._bosch_object.fetch_range(
            start_time=start_time, stop_time=stop_time
        )

    async def _insert_statistics(self) -> None:
        """Insert external statistics."""
        _sum = 0
        last_stats = await self.hass.async_add_executor_job(
            get_last_statistics, self.hass, 1, self.statistic_id, True
        )
        today = dt_util.now()
        end_time = None
        if not last_stats:
            _LOGGER.debug("Last stats not exist. Trying to fetch last 30 days of data.")
            start_time = (
                today - timedelta(days=30)
                if self._fetch_past_days
                else today - timedelta(days=1)
            )
            all_stats = await self.fetch_past_data(
                start_time=start_time, stop_time=today
            )
            if not all_stats:
                return
            _sum = 0
        elif self.statistic_id in last_stats:
            last_stats_row = last_stats[self.statistic_id][0]
            end = last_stats_row["end"]
            end_time = datetime.datetime.strptime(end, "%Y-%m-%dT%H:%M:%S%z")
            _sum = last_stats_row["sum"] or 0
            diff = today - end_time
            if diff > timedelta(days=1):
                if diff > timedelta(days=29):
                    end_time = today - timedelta(days=30)
                all_stats = await self.fetch_past_data(
                    start_time=end_time, stop_time=today
                )
            else:
                all_stats = self._bosch_object.state
        statistics_to_push = []
        for stat in all_stats:
            _date: datetime.datetime = stat["d"]
            if (
                end_time
                and _date.date() == end_time.date()
                and _date.hour == end_time.hour
            ):
                _LOGGER.debug("Skip re-adding day which already exists in database.")
                continue
            _state = stat["value"]
            if _state == 0:
                continue
            _sum += _state
            statistics_to_push.append(
                StatisticData(
                    start=_date,
                    state=_state,
                    sum=_sum,
                )
            )
        print(statistics_to_push)
        self.add_external_stats(stats=statistics_to_push)
