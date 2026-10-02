"""Bosch sensor for Energy URI in Easycontrol."""
from __future__ import annotations
import logging
from datetime import timedelta, datetime
from typing import Any, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from ..coordinator import BoschDataUpdateCoordinator
    from ..types import BoschObject, BoschGateway

from bosch_thermostat_client.const import UNITS
from .statistic_helper import StatisticHelper
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.util import dt as dt_util
from homeassistant.components.recorder.models import (
    StatisticData,
    timestamp_to_datetime_or_none,
)


from ..const import VALUE

_LOGGER = logging.getLogger(__name__)

EnergySensors = [
    {
        "name": "energy temperature",
        "attr": "T",
        "unitOfMeasure": UnitOfTemperature.CELSIUS,
        "deviceClass": SensorDeviceClass.TEMPERATURE,
        "stateClass": SensorStateClass.MEASUREMENT,
    },
    {
        "name": "energy central heating",
        "attr": "CH",
        "unitOfMeasure": UnitOfEnergy.KILO_WATT_HOUR,
        "deviceClass": SensorDeviceClass.ENERGY,
        "stateClass": SensorStateClass.TOTAL,
    },
    {
        "name": "energy hot water",
        "attr": "HW",
        "unitOfMeasure": UnitOfEnergy.KILO_WATT_HOUR,
        "deviceClass": SensorDeviceClass.ENERGY,
        "stateClass": SensorStateClass.TOTAL,
    },
]

EcusRecordingSensors = [
    {
        "name": "ecus avg outdoor temperature",
        "attr": "T",
        "unitOfMeasure": UnitOfTemperature.CELSIUS,
        "normalize": lambda x: x / 10,
        "deviceClass": SensorDeviceClass.TEMPERATURE,
        "stateClass": SensorStateClass.MEASUREMENT,
    },
    {
        "name": "central heating",
        "attr": "CH",
        "unitOfMeasure": UnitOfVolume.CUBIC_METERS,
        "deviceClass": SensorDeviceClass.GAS,
        "stateClass": SensorStateClass.TOTAL,
    },
    {
        "name": "hot water",
        "attr": "HW",
        "unitOfMeasure": UnitOfVolume.CUBIC_METERS,
        "deviceClass": SensorDeviceClass.GAS,
        "stateClass": SensorStateClass.TOTAL,
    },
]


def _start_of_day(day: str | None) -> datetime | None:
    """Local start of a "dd-mm-YYYY" day as reported by the gateway."""
    try:
        parsed = datetime.strptime(day, "%d-%m-%Y")
    except (TypeError, ValueError):
        return None
    return dt_util.start_of_local_day(parsed.date())


class EnergySensor(StatisticHelper):
    """Representation of Energy Sensor."""

    _domain_name = "Energy"

    def __init__(
        self,
        coordinator: BoschDataUpdateCoordinator,
        uuid: str,
        bosch_object: BoschObject,
        gateway: BoschGateway,
        sensor_attributes: dict[str, Any],
        attr_uri: str,
        is_enabled: bool = False,
        new_stats_api: bool = False,
    ) -> None:
        """Initialize Energy sensor."""
        self._attr_read_key: str | None = None
        self._read_attr_to_search: str = sensor_attributes.get("attr", "")
        self._normalize = sensor_attributes.get("normalize")
        self._attr_unique_id = f"{self._domain_name}{self._read_attr_to_search}{uuid}"

        super().__init__(
            coordinator=coordinator,
            uuid=uuid,
            bosch_object=bosch_object,
            gateway=gateway,
            name=sensor_attributes.get("name", ""),
            attr_uri=attr_uri,
            is_enabled=is_enabled,
            new_stats_api=new_stats_api,
        )
        self._unit_of_measurement = sensor_attributes.get(
            UNITS, sensor_attributes.get("unitOfMeasure")
        )
        self._attr_device_class = sensor_attributes.get(
            "deviceClass", SensorDeviceClass.ENERGY
        )
        # Each derived sensor declares its own state class instead of inheriting
        # the one of the underlying Bosch object. The kWh / m3 values are the
        # total of one day, so they are TOTAL with last_reset at that day's start.
        self._attr_state_class = sensor_attributes.get("stateClass")

    @property
    def device_name(self) -> str:
        """Device name."""
        return "Energy sensors"

    @property
    def _uses_external_statistics(self) -> bool:
        """Only energy/gas volume readings go to long-term statistics."""
        return self._new_stats_api and self._unit_of_measurement in (
            UnitOfEnergy.KILO_WATT_HOUR,
            UnitOfVolume.CUBIC_METERS,
        )

    @property
    def last_reset(self) -> datetime | None:
        """Start of the day the daily kWh / m3 total covers."""
        if self._attr_state_class != SensorStateClass.TOTAL:
            return None
        data = self._bosch_object.get_property(self._attr_uri)
        value = data.get(VALUE) if data else None
        return _start_of_day(value.get("d")) if isinstance(value, dict) else None

    def _native_value(self) -> Any:
        """Return the raw state of the sensor."""
        data = self._bosch_object.get_property(self._attr_uri)
        if not data:
            return None
        value = data.get(VALUE)
        if not value:
            return None
        
        if not self._attr_read_key:
            for attr in value:
                if self._read_attr_to_search in attr.upper():
                    self._attr_read_key = attr
                    break
        
        if not self._attr_read_key or self._attr_read_key not in value:
            return None

        raw_value = value.get(self._attr_read_key)
        if raw_value in (None, "unavailable"):
            return None
        if self._normalize:
            return self._normalize(raw_value)
        return raw_value


    @property
    def statistic_id(self) -> str:
        """External API statistic ID."""
        if not self._short_id:
            self._short_id = self.entity_id.replace(".", "").replace("sensor", "")
        return (
            f"{self._domain_name}:{self._attr_read_key}{self._short_id}external".lower()
        )

    def _generate_easycontrol_statistics(
        self, start: datetime, end: datetime, single_value: float, init_value: float
    ) -> tuple[float, list[StatisticData]]:
        statistics = []
        now = start
        _sum = init_value
        while now < end:
            _sum = round(_sum + single_value, 2)
            statistics.append(
                StatisticData(
                    start=now,
                    state=single_value,
                    sum=_sum,
                )
            )
            now = now + timedelta(hours=1)
        return (_sum, statistics)

    async def fetch_past_data(self, start_time: datetime, stop_time: datetime) -> dict[str, Any]:
        """Fetch a range of past data from the gateway."""
        _LOGGER.debug(
            "Attempt to fetch range %s - %s for %s",
            start_time,
            stop_time,
            self.statistic_id,
        )
        data = await self._bosch_object.fetch_range(
            start_time=start_time, stop_time=stop_time
        )
        return cast(dict[str, Any], data)

    async def _upsert_past_statistics(self, start: datetime, stop: datetime) -> None:
        now = dt_util.now()
        diff = now - start
        if now.day == start.day:
            _LOGGER.warning("Can't upsert today date. Try again tomorrow.")
            return
        if diff > timedelta(days=60):
            _LOGGER.warning(
                "Update more than 60 days in past might take some time! Component will try to do that anyway!"
            )
        start_time = dt_util.start_of_local_day(start)
        bosch_data = await self.fetch_past_data(
            start_time=start_time, stop_time=start + timedelta(hours=26)
        )
        _day_dt = start_time.strftime("%d-%m-%Y")
        if not bosch_data or _day_dt not in bosch_data:
            _LOGGER.debug("No stats found. Exiting.")
            return
        day_data = bosch_data[_day_dt]
        if not self._attr_read_key or self._attr_read_key not in day_data:
            return
        _value = round(day_data[self._attr_read_key] / 24, 2)
        last_stats = await self.get_stats_from_ha_db(
            start_time=start - timedelta(hours=1), end_time=now
        )
        last_stat = last_stats.get(self.statistic_id)
        _sum: float = cast(float, last_stat[0].get("sum", 0.0)) if last_stat else 0.0
        _sum, statistics = self._generate_easycontrol_statistics(
            start=start_time,
            end=start_time + timedelta(days=1),
            single_value=_value,
            init_value=_sum,
        )
        self.add_external_stats(stats=statistics)

    def append_statistics(self, stats: list[Any], sum: float) -> float:
        statistics_to_push: list[StatisticData] = []
        start_of_day = dt_util.start_of_local_day()
        for stat in stats:
            day_dt: datetime = datetime.strptime(stat["d"], "%d-%m-%Y")
            _date = start_of_day.replace(
                year=day_dt.year, month=day_dt.month, day=day_dt.day
            )
            if not self._attr_read_key or self._attr_read_key not in stat:
                continue
            _value = round(stat[self._attr_read_key] / 24, 2)
            sum, statistics = self._generate_easycontrol_statistics(
                start=_date,
                end=_date + timedelta(days=1),
                single_value=_value,
                init_value=sum,
            )
            statistics_to_push += statistics
            _LOGGER.debug(
                "Appending day to statistic table with id: %s. Date: %s, state: %s, sum: %s.",
                self.statistic_id,
                _date,
                _value,
                sum,
            )
        self.add_external_stats(stats=statistics_to_push)
        return sum

    async def _insert_statistics(self) -> None:
        """Insert statistics from the past."""
        async with self._statistic_import_lock:
            _sum: float = 0.0
            now = dt_util.now()
            last_stat = await self.get_last_stat()
            if not last_stat or self.statistic_id not in last_stat or len(last_stat[self.statistic_id]) == 0:
                _LOGGER.debug("Last stats not exist. Trying to fetch ALL data.")
                all_stats = list((await self._bosch_object.fetch_all()).values())
                if not all_stats:
                    _LOGGER.warning("Stats not found.")
                    return
                self.append_statistics(stats=all_stats, sum=_sum)
                return

            now = dt_util.now()
            start_of_yesterday = now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=1)
            start_of_yesterday_utc = dt_util.as_utc(start_of_yesterday)
            yesterday = now - timedelta(days=1)

            last_stat_row = last_stat[self.statistic_id][0]
            last_stat_start = timestamp_to_datetime_or_none(last_stat_row.get("start"))

            last_stats = (
                await self.get_stats_from_ha_db(
                    start_time=dt_util.start_of_local_day(last_stat_start)
                    - timedelta(hours=3),
                    end_time=yesterday,
                )
                if last_stat_start and last_stat_start <= start_of_yesterday_utc
                else await self.get_stats_from_ha_db(
                    start_time=start_of_yesterday_utc - timedelta(hours=1),
                    end_time=yesterday - timedelta(hours=1),
                )
            )

            async def get_last_stats_from_bosch_api() -> tuple[list[Any], float]:
                last_stats_row = self.get_last_stats_before_date(
                    last_stats=last_stats, day=start_of_yesterday_utc
                )
                start_time_raw = last_stats_row.get("start")
                _sum = cast(float, last_stats_row.get("sum", 0.0))
                
                start_time: datetime | None = None
                if isinstance(start_time_raw, (int, float)):
                    start_time = timestamp_to_datetime_or_none(start_time_raw)
                
                if not start_time:
                    _LOGGER.debug(
                        "Start time not found. %s found %s", self.statistic_id, start_time
                    )
                elif start_time.date() < yesterday.date() - timedelta(days=2):
                    _LOGGER.debug(
                        "Last row of statistic %s found %s, missing more than 1 day with current sum %s",
                        self.statistic_id,
                        start_time,
                        _sum,
                    )
                    bosch_data = await self.fetch_past_data(
                        start_time=start_time, stop_time=yesterday
                    )
                    if not bosch_data:
                        return [], _sum
                    return (
                        [
                            row
                            for row in bosch_data.values()
                            if dt_util.start_of_local_day(
                                datetime.strptime(row["d"], "%d-%m-%Y")
                            )
                            > start_time
                        ],
                        _sum,
                    )

                _LOGGER.debug(
                    "Returning state to put to statistic table %s", self.statistic_id
                )
                last_entry = self._bosch_object.last_entry
                return list(last_entry.values()) if last_entry else [], _sum

            if self.statistic_id in last_stats:
                bosch_stats, _sum = await get_last_stats_from_bosch_api()
                self.append_statistics(stats=bosch_stats, sum=_sum)
