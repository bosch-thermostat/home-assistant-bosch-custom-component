"""Bosch sensor for Recording sensor in IVT."""

from __future__ import annotations
import logging
from datetime import timedelta, datetime
from typing import Any, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from ..coordinator import BoschDataUpdateCoordinator
    from ..types import BoschObject, BoschGateway

from .statistic_helper import StatisticHelper

from ..const import VALUE
from homeassistant.components.recorder.models import (
    StatisticData,
    timestamp_to_datetime_or_none,
)
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class RecordingSensor(StatisticHelper):
    """Representation of Recording Sensor."""

    _domain_name = "Recording"

    def __init__(
        self,
        coordinator: BoschDataUpdateCoordinator,
        uuid: str,
        bosch_object: BoschObject,
        gateway: BoschGateway,
        name: str,
        attr_uri: str,
        is_enabled: bool = False,
        new_stats_api: bool = False,
    ) -> None:
        """Initialize Recording sensor."""
        super().__init__(
            coordinator=coordinator,
            uuid=uuid,
            bosch_object=bosch_object,
            gateway=gateway,
            name=name,
            attr_uri=attr_uri,
            is_enabled=is_enabled,
            new_stats_api=new_stats_api,
        )
        self._unit_of_measurement = bosch_object.unit_of_measurement

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

    @staticmethod
    def _last_full_hour() -> datetime:
        return (dt_util.now() - timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0
        )

    @property
    def last_reset(self) -> datetime | None:
        """The value covers the last full hour (state_class total)."""
        if self._new_stats_api:
            return None
        return self._last_full_hour()

    def _native_value(self) -> Any:
        """Return the raw state of the sensor."""
        if self._new_stats_api:
            return -17 # Legend state for external stats
        
        data = self._bosch_object.get_property(self._attr_uri)
        if not data or not data.get(VALUE):
            return None

        last_hour = self._last_full_hour()
        for row in data[VALUE]:
            if row["d"] == last_hour:
                return row.get(VALUE)
        return None

    async def _upsert_past_statistics(
        self, start: datetime, stop: datetime
    ) -> None:
        now = dt_util.now()
        diff = now - start
        if now.day == start.day:
            _LOGGER.warning("Can't upsert today date. Try again tomorrow.")
            return
        if diff > timedelta(days=60):
            _LOGGER.warning(
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
        _sum: float = cast(float, last_stat[0].get("sum", 0.0)) if last_stat else 0.0
        out: dict[float, StatisticData] = {}
        current_time = start
        while current_time <= stop:
            current_ts = dt_util.as_timestamp(current_time)
            if current_ts in stats_dict:
                stat = stats_dict[current_ts]
                _state: float = float(stat["value"])
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
                    state=0.0,
                    sum=_sum,
                )
            current_time += timedelta(hours=1)

        if last_stat:
            start_ts = dt_util.as_timestamp(start)
            for stat in last_stat:
                _start = cast(float, stat["start"])
                if _start in out or start_ts > _start:
                    continue
                _state = cast(float, stat.get("state", 0.0))
                _sum += _state
                out[_start] = StatisticData(
                    start=dt_util.utc_from_timestamp(_start),
                    state=_state,
                    sum=_sum,
                )
        self.add_external_stats(stats=list(out.values()))

    def append_statistics(
        self, stats: list[Any], sum: float, now: datetime
    ) -> float:
        statistics_to_push: list[StatisticData] = []
        for stat in stats:
            _date: datetime = stat["d"]
            _state: float = float(stat["value"])
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
        async with self._statistic_import_lock:
            _sum: float = 0.0
            now = dt_util.now()
            last_stat = await self.get_last_stat()
            if not last_stat or self.statistic_id not in last_stat or len(last_stat[self.statistic_id]) == 0:
                _LOGGER.debug(
                    "Last stats not exist. Trying to fetch last 30 days of data."
                )
                all_stats = await self.fetch_past_data(
                    start_time=now - timedelta(days=30), stop_time=now
                )
                if not all_stats:
                    _LOGGER.warning("Stats not found.")
                    return
                self.append_statistics(
                    stats=list(all_stats.values()), sum=_sum, now=now
                )
                return

            start_of_day = dt_util.start_of_local_day()
            last_stat_row = last_stat[self.statistic_id][0]
            last_stat_start = timestamp_to_datetime_or_none(
                last_stat_row.get("start")
            )

            async def get_last_stats_in_ha() -> dict[str, list[Any]]:
                if not last_stat_start:
                    return {}
                start_time = dt_util.start_of_local_day(
                    last_stat_start
                ) - timedelta(hours=24)
                return await self.get_stats_from_ha_db(
                    start_time=start_time,
                    end_time=now,
                )

            last_stats = await get_last_stats_in_ha()

            async def get_last_stats_from_bosch_api() -> tuple[list[Any], float]:
                last_stats_row = self.get_last_stats_before_date(
                    last_stats=last_stats, day=start_of_day
                )
                start_time_raw = last_stats_row.get("start")
                _sum = cast(float, last_stats_row.get("sum", 0.0))
                
                start_time: datetime | None = None
                if isinstance(start_time_raw, (int, float)):
                    start_time = timestamp_to_datetime_or_none(start_time_raw)
                
                if not start_time:
                    _LOGGER.debug(
                        "Start time not found. %s found %s",
                        self.statistic_id,
                        start_time,
                    )
                elif start_time and start_time.date() < now.date() - timedelta(days=1):
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
                state = self._bosch_object.state
                if state:
                    # let's get last state once again
                    # as bosch state provide whole day always.
                    first_date_from_state = state[0]
                    last_stats_row = self.get_last_stats_before_date(
                        last_stats=last_stats, day=first_date_from_state["d"]
                    )
                    _sum = cast(float, last_stats_row.get("sum", 0.0))
                return state, _sum

            if self.statistic_id in last_stats:
                bosch_stats, _sum = await get_last_stats_from_bosch_api()
                self.append_statistics(stats=bosch_stats, sum=_sum, now=now)

