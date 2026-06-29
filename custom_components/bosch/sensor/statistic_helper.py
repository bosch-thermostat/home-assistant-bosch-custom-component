"""Bosch statistic helper for Recording/Energy sensor."""

from __future__ import annotations
import logging
import asyncio
from datetime import datetime, timedelta
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    datetime_to_timestamp_or_none,
)
from sqlalchemy.exc import IntegrityError
from homeassistant.util import dt as dt_util
from homeassistant.const import UnitOfEnergy, UnitOfTemperature, UnitOfVolume
from homeassistant.components.sensor import SensorDeviceClass

try:
    from homeassistant.components.recorder.db_schema import StatisticsMeta
except ImportError:
    from homeassistant.components.recorder.models import StatisticsMeta
from homeassistant.components.recorder.util import session_scope
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
    StatisticsRow,
)
from homeassistant.components.recorder import get_instance
from .base import BoschBaseSensor

_LOGGER = logging.getLogger(__name__)


class StatisticHelper(BoschBaseSensor):
    """Statistic helper class."""

    def __init__(self, new_stats_api: bool = False, **kwargs):
        """Initialize statistic helper."""
        self._short_id = None
        self._new_stats_api = new_stats_api
        self._statistic_import_lock = asyncio.Lock()
        super().__init__(**kwargs)

    async def move_old_entity_data_to_new(self, event_time=None) -> None:
        """Rename old entity_id in statistic table. Not working currently."""
        old_entity_id = self.entity_id
        _LOGGER.debug("Moving entity id statistic data to new format.")
        try:
            with session_scope(hass=self.hass) as session:
                session.query(StatisticsMeta).filter(
                    (StatisticsMeta.statistic_id == old_entity_id)
                    & (StatisticsMeta.source == "recorder")
                ).update(
                    {
                        StatisticsMeta.statistic_id: self.statistic_id,
                        StatisticsMeta.source: self._domain_name.lower(),
                        StatisticsMeta.name: f"Stats {self._name}",
                    }
                )
        except IntegrityError as err:
            _LOGGER.error("Can't move entity id. It already exists. %s", err)

    @property
    def statistic_id(self) -> str:
        """External API statistic ID."""
        raise NotImplementedError()

    @property
    def should_poll(self):
        """Don't poll."""
        return False

    def _get_statistic_unit_class(self):
        """Return Home Assistant statistic unit_class inferred from device_class/unit."""
        device_class = getattr(self, "_attr_device_class", None)
        unit = self._unit_of_measurement

        # 1) Prefer mapping by sensor device_class (strict mode)
        if device_class == SensorDeviceClass.ENERGY:
            return "energy"
        if device_class == SensorDeviceClass.TEMPERATURE:
            return "temperature"
        if device_class == SensorDeviceClass.GAS:
            return "gas"

        # 2) Fallback mapping by unit_of_measurement
        if unit in (UnitOfEnergy.KILO_WATT_HOUR, "kWh", "Wh"):
            return "energy"
        if unit in (UnitOfVolume.CUBIC_METERS, "m³"):
            return "volume"
        if unit in (UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT, "K"):
            return "temperature"

        return None

    @property
    def statistic_metadata(self) -> StatisticMetaData:
        """Statistic Metadata recorder model class."""
        unit_class = self._get_statistic_unit_class()
        supports_unit_class = "unit_class" in getattr(
            StatisticMetaData, "__annotations__", {}
        )

        # Try to import StatisticMeanType for newer HA versions
        try:
            from homeassistant.components.recorder.models import StatisticMeanType
            meta_kwargs = {
                "mean_type": StatisticMeanType.NONE,
                "has_sum": True,
                "name": f"Stats {self._name}",
                "source": self._domain_name.lower(),
                "statistic_id": self.statistic_id,
                "unit_of_measurement": self._unit_of_measurement,
            }
            if supports_unit_class and unit_class is not None:
                meta_kwargs["unit_class"] = unit_class
            return StatisticMetaData(**meta_kwargs)
        except ImportError:
            meta_kwargs = {
                "has_mean": False,
                "has_sum": True,
                "name": f"Stats {self._name}",
                "source": self._domain_name.lower(),
                "statistic_id": self.statistic_id,
                "unit_of_measurement": self._unit_of_measurement,
            }
            if supports_unit_class and unit_class is not None:
                meta_kwargs["unit_class"] = unit_class
            try:
                return StatisticMetaData(**meta_kwargs)
            except TypeError:
                # Older HA without unit_class support
                meta_kwargs.pop("unit_class", None)
                return StatisticMetaData(**meta_kwargs)

    async def get_last_stat(self) -> dict[str, list[StatisticsRow]]:
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
        """Get stats during period."""
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
        """Add external statistics."""
        if not stats:
            _LOGGER.debug("add_external_stats called with empty stats for %s", self.statistic_id)
            return

        _LOGGER.info(
            "=== EXTERNAL STATS DIAGNOSTICS ==="
        )
        _LOGGER.info(
            "Sensor: %s, statistic_id: %s",
            self._name, self.statistic_id
        )
        _LOGGER.info(
            "Number of statistics entries: %d",
            len(stats)
        )

        # Log first and last few entries
        if len(stats) > 0:
            _LOGGER.info(
                "First entry: %s",
                stats[0]
            )
            _LOGGER.info(
                "Last entry: %s",
                stats[-1]
            )

            if len(stats) > 5:
                _LOGGER.info(
                    "Sample middle entries:"
                )
                for i in range(1, min(4, len(stats) - 1)):
                    _LOGGER.info(
                        "  Entry %d: %s",
                        i, stats[i]
                    )

        _LOGGER.debug(
            "add_external_stats for %s: %d entries, first=%s, last=%s",
            self.statistic_id,
            len(stats),
            stats[0],
            stats[-1],
        )
        async_add_external_statistics(self.hass, self.statistic_metadata, stats)

        latest_stat = stats[-1]
        if isinstance(latest_stat, dict):
            _sum = latest_stat.get("sum")
            _state_val = latest_stat.get("state")
        else:
            _sum = latest_stat.sum
            _state_val = latest_stat.state

        _LOGGER.info(
            "Latest statistics entry:"
        )
        _LOGGER.info(
            "  sum (cumulative): %.4f kWh",
            _sum
        )
        _LOGGER.info(
            "  state (hourly value): %.4f kWh/h",
            _state_val
        )
        _LOGGER.info(
            "  Current sensor state (daily): %.2f kWh",
            self._state
        )
        _LOGGER.info(
            "  IMPORTANT: NOT overwriting sensor state with hourly value from stats"
        )

        _LOGGER.debug(
            "add_external_stats for %s: sum=%s, hourly_state=%s (sensor daily state remains: %s)",
            self.statistic_id,
            _sum,
            _state_val,
            self._state,
        )
        self.async_schedule_update_ha_state()

    def get_last_stats_before_date(
        self, last_stats: dict[str, list[StatisticsRow]], day: datetime
    ):
        day_stamp = datetime_to_timestamp_or_none(day)
        closest_stat = None
        for stat in last_stats[self.statistic_id]:
            tstmp = stat.get("start")
            if tstmp < day_stamp:
                if closest_stat is None or tstmp > closest_stat.get("start"):
                    closest_stat = stat
        if not closest_stat:
            closest_stat = last_stats[self.statistic_id][-1]
            _LOGGER.debug("Closest stat not found, use last one from array!")
        _LOGGER.debug(
            "Last stat for %s found %s", self.statistic_id, closest_stat
        )
        return closest_stat

    async def insert_statistics_range(self, start_time: datetime) -> None:
        """Attempt to put past data into database."""
        start = dt_util.start_of_local_day(start_time)
        stop = start + timedelta(hours=24)  # fetch one day only from API
        async with self._statistic_import_lock:
            await self._upsert_past_statistics(start=start, stop=stop)

    async def fetch_past_data(
        self, start_time: datetime, stop_time: datetime
    ) -> dict:
        """Rename old entity_id in statistic table."""
        start_time = dt_util.start_of_local_day(start_time)
        _LOGGER.debug(
            "Attempt to fetch range %s - %s for %s",
            start_time,
            stop_time,
            self.statistic_id,
        )
        my_range = await self._bosch_object.fetch_range(
            start_time=start_time, stop_time=stop_time
        )
        return my_range

    async def _upsert_past_statistics(
        self, start: datetime, stop: datetime
    ) -> None:
        raise NotImplementedError
