"""Bosch statistic helper for Recording/Energy sensor."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from ..coordinator import BoschDataUpdateCoordinator
    from ..types import BoschObject, BoschGateway

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    datetime_to_timestamp_or_none,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
    StatisticsRow,
)

try:
    from homeassistant.components.recorder.statistics import StatisticMeanType
except ImportError:  # HA without mean_type support
    StatisticMeanType = None
from homeassistant.util import dt as dt_util

from .base import BoschBaseSensor

_LOGGER = logging.getLogger(__name__)


class StatisticHelper(BoschBaseSensor):
    """Statistic helper class to manage external long-term statistics."""

    def __init__(
        self,
        coordinator: BoschDataUpdateCoordinator,
        uuid: str,
        bosch_object: BoschObject,
        gateway: BoschGateway,
        name: str,
        attr_uri: str,
        domain_name: str | None = None,
        circuit_type: str | None = None,
        is_enabled: bool = False,
        new_stats_api: bool = False,
    ) -> None:
        """Initialize statistic helper."""
        self._short_id: str | None = None
        self._new_stats_api = new_stats_api
        self._statistic_import_lock = asyncio.Lock()
        self._unit_of_measurement: str | None = None
        super().__init__(
            coordinator=coordinator,
            uuid=uuid,
            bosch_object=bosch_object,
            gateway=gateway,
            name=name,
            attr_uri=attr_uri,
            domain_name=domain_name,
            circuit_type=circuit_type,
            is_enabled=is_enabled,
        )

    def _register_with_coordinator(self) -> None:
        """Use the hourly recording schedule instead of the regular refresh."""
        self.coordinator.register_recording_entity(self)

    def _unregister_from_coordinator(self) -> None:
        """Leave the hourly recording schedule."""
        self.coordinator.unregister_recording_entity(self)

    @property
    def _uses_external_statistics(self) -> bool:
        """Whether this sensor writes external long-term statistics."""
        return self._new_stats_api

    async def async_update_recording(self) -> None:
        """Push freshly fetched recording data to HA (called hourly)."""
        if self._uses_external_statistics:
            _LOGGER.debug(
                "Invoking external statistic function for %s.", self.statistic_id
            )
            await self._insert_statistics()
        else:
            self.async_write_ha_state()

    async def _insert_statistics(self) -> None:
        """Insert external statistics. Must be implemented by subclasses."""
        raise NotImplementedError()

    @property
    def statistic_id(self) -> str:
        """External API statistic ID."""
        raise NotImplementedError()

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement

    @property
    def should_poll(self) -> bool:
        """Don't poll; updates are managed by the coordinator or internal logic."""
        return False

    _UNIT_CLASS_MAP = {
        "kWh": "energy",
        "Wh": "energy",
        "kW": "power",
    }

    def _get_unit_class(self) -> str | None:
        """Derive unit_class from unit_of_measurement."""
        return self._UNIT_CLASS_MAP.get(self._unit_of_measurement or "")

    @property
    def statistic_metadata(self) -> StatisticMetaData:
        """Statistic Metadata recorder model class."""
        return StatisticMetaData(
            has_mean=False,
            **({"mean_type": StatisticMeanType.NONE} if StatisticMeanType else {}),
            has_sum=True,
            name=f"Stats {self._attr_name}",
            source=self._domain_name.lower() if self._domain_name else "bosch",
            statistic_id=self.statistic_id,
            unit_of_measurement=self._unit_of_measurement,
            unit_class=self._get_unit_class(),
        )

    async def get_last_stat(self) -> dict[str, list[StatisticsRow]]:
        """Get the last statistic row from the database."""
        return await get_instance(self.hass).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.statistic_id,
            True,
            {"state", "sum"},
        )

    async def get_stats_from_ha_db(
        self, start_time: datetime, end_time: datetime
    ) -> dict[str, list[StatisticsRow]]:
        """Get statistics during a specific period."""
        return await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start_time,
            end_time,
            [self.statistic_id],
            "hour",
            None,
            {"state", "sum"},
        )

    def add_external_stats(self, stats: list[StatisticData]) -> None:
        """Add external statistics to Home Assistant's recorder."""
        self._state = -17  # Indicate that data is stored externally
        if not stats:
            return
        async_add_external_statistics(self.hass, self.statistic_metadata, stats)
        self.async_write_ha_state()

    def get_last_stats_before_date(
        self, last_stats: dict[str, list[StatisticsRow]], day: datetime
    ) -> StatisticsRow:
        """Find the last statistic row before a given date."""
        day_stamp = datetime_to_timestamp_or_none(day)
        closest_stat: StatisticsRow | None = None
        for stat in last_stats.get(self.statistic_id, []):
            tstmp = stat.get("start")
            if tstmp is not None and day_stamp is not None and tstmp < day_stamp:
                if closest_stat is None or tstmp > cast(float, closest_stat.get("start")):
                    closest_stat = stat
        if not closest_stat and last_stats.get(self.statistic_id):
            closest_stat = last_stats[self.statistic_id][-1]
            _LOGGER.debug("Closest stat not found, using last available row.")
        
        if not closest_stat:
            return StatisticsRow(start=0.0, state=0.0, sum=0.0)
        return closest_stat

    async def insert_statistics_range(self, start_time: datetime) -> None:
        """Attempt to put past data into database for a 24-hour range."""
        start = dt_util.start_of_local_day(start_time)
        stop = start + timedelta(hours=24)
        async with self._statistic_import_lock:
            await self._upsert_past_statistics(start=start, stop=stop)

    async def fetch_past_data(
        self, start_time: datetime, stop_time: datetime
    ) -> dict[Any, Any]:
        """Fetch range of data from the Bosch gateway, keyed by timestamp."""
        start_time = dt_util.start_of_local_day(start_time)
        _LOGGER.debug(
            "Attempting to fetch range %s - %s for %s",
            start_time,
            stop_time,
            self.statistic_id,
        )
        return await self._bosch_object.fetch_range(
            start_time=start_time, stop_time=stop_time
        )

    async def _upsert_past_statistics(
        self, start: datetime, stop: datetime
    ) -> None:
        """Upsert past statistics. Must be implemented by subclasses."""
        raise NotImplementedError()
