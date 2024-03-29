"""Bosch sensor for Energy URI in Easycontrol."""
from __future__ import annotations
import logging
from datetime import timedelta, datetime
from bosch_thermostat_client.const import UNITS
from .statistic_helper import StatisticHelper
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfVolume,
    STATE_UNAVAILABLE,
)
from homeassistant.util import dt as dt_util
from homeassistant.components.recorder.models import (
    StatisticData,
    timestamp_to_datetime_or_none,
)


from ..const import SIGNAL_ENERGY_UPDATE_BOSCH, VALUE

_LOGGER = logging.getLogger(__name__)

EnergySensors = [
    {
        "name": "energy temperature",
        "attr": "T",
        "unitOfMeasure": UnitOfTemperature.CELSIUS,
        "deviceClass": SensorDeviceClass.TEMPERATURE,
    },
    {
        "name": "energy central heating",
        "attr": "CH",
        "unitOfMeasure": UnitOfEnergy.KILO_WATT_HOUR,
        "deviceClass": SensorDeviceClass.ENERGY,
    },
    {
        "name": "energy hot water",
        "attr": "HW",
        "unitOfMeasure": UnitOfEnergy.KILO_WATT_HOUR,
        "deviceClass": SensorDeviceClass.ENERGY,
    },
]

EcusRecordingSensors = [
    {
        "name": "ecus avg outdoor temperature",
        "attr": "T",
        "unitOfMeasure": UnitOfTemperature.CELSIUS,
        "normalize": lambda x: x / 10,
        "deviceClass": SensorDeviceClass.TEMPERATURE,
    },
    {
        "name": "central heating",
        "attr": "CH",
        "unitOfMeasure": UnitOfVolume.CUBIC_METERS,
        "deviceClass": SensorDeviceClass.GAS,
    },
    {
        "name": "hot water",
        "attr": "HW",
        "unitOfMeasure": UnitOfVolume.CUBIC_METERS,
        "deviceClass": SensorDeviceClass.GAS,
    },
]


class EnergySensor(StatisticHelper):
    """Representation of Energy Sensor."""

    signal = SIGNAL_ENERGY_UPDATE_BOSCH
    _domain_name = "Energy"

    def __init__(
        self,
        sensor_attributes,
        uuid,
        **kwargs,
    ) -> None:
        """Initialize Energy sensor."""
        self._attr_read_key = None
        self._read_attr_to_search = sensor_attributes.get("attr")
        self._normalize = sensor_attributes.get("normalize")
        self._attr_unique_id = f"{self._domain_name}{self._read_attr_to_search}{uuid}"

        super().__init__(name=sensor_attributes.get("name"), uuid=uuid, **kwargs)
        self._unit_of_measurement = sensor_attributes.get(UNITS)
        self._attr_device_class = sensor_attributes.get(
            "deviceClass", SensorDeviceClass.ENERGY
        )
        if (
            self._attr_state_class
            and self._attr_device_class == SensorDeviceClass.TEMPERATURE
        ):
            self._attr_device_class = SensorStateClass.MEASUREMENT

    @property
    def device_name(self) -> str:
        """Device name."""
        return "Energy sensors"

    async def async_update(self) -> None:
        """Update state of device."""
        data = self._bosch_object.get_property(self._attr_uri)
        value = data.get(VALUE)

        def search_read_attr():
            if not self._attr_read_key:
                for attr in value:
                    if self._read_attr_to_search in attr.upper():
                        self._attr_read_key = attr
                        return True
            else:
                return True
            _LOGGER.debug("Reading attribute not available %s", self._attr_read_key)
            self._state = STATE_UNAVAILABLE
            return False

        if not value or not search_read_attr():
            _LOGGER.debug("Energy sensor data not available %s", self._name)
            self._state = STATE_UNAVAILABLE

        if self._new_stats_api and (
            self._unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR
            or self._unit_of_measurement == UnitOfVolume.CUBIC_METERS
        ):
            await self._insert_statistics()
        else:
            if self._normalize:
                self._state = self._normalize(value.get(self._attr_read_key))
            else:
                self._state = value.get(self._attr_read_key)
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()

    @property
    def statistic_id(self) -> str:
        """External API statistic ID."""
        if not self._short_id:
            self._short_id = self.entity_id.replace(".", "").replace("sensor", "")
        return (
            f"{self._domain_name}:{self._attr_read_key}{self._short_id}external".lower()
        )

    def _generate_easycontrol_statistics(
        self, start: datetime, end: datetime, single_value: int, init_value: int
    ) -> tuple[int, list[StatisticData]]:
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

    async def fetch_past_data(self, start_time: datetime, stop_time: datetime) -> dict:
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
                "Update more than 60 days in past might take some time! Component will try to do that anyway!"
            )
        start_time = dt_util.start_of_local_day(start)
        stats = await self.fetch_past_data(
            start_time=start_time, stop_time=start + timedelta(hours=26)
        )  # return list of objects {'d': datetime with timezone, 'value': 'used kWh in last hour'}
        _day_dt = start_time.strftime("%d-%m-%Y")
        if not stats or _day_dt not in stats:
            _LOGGER.debug("No stats found. Exiting.")
            return
        day_data = stats[_day_dt]
        _value = round(day_data[self._attr_read_key] / 24, 2)
        last_stats = await self.get_stats_from_ha_db(
            start_time=start - timedelta(hours=1), end_time=now
        )
        last_stat = last_stats.get(self.statistic_id)
        _sum = last_stat[0].get("sum", 0) if last_stat else 0
        _sum, statistics = self._generate_easycontrol_statistics(
            start=start_time,
            end=start_time + timedelta(days=1),
            single_value=_value,
            init_value=_sum,
        )
        self.add_external_stats(stats=statistics)

    def append_statistics(self, stats, sum) -> float:
        statistics_to_push = []
        start_of_day = dt_util.start_of_local_day()
        for stat in stats:
            day_dt: datetime = datetime.strptime(stat["d"], "%d-%m-%Y")
            _date = start_of_day.replace(
                year=day_dt.year, month=day_dt.month, day=day_dt.day
            )
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
        _sum = 0
        last_stat = await self.get_last_stat()
        if len(last_stat) == 0 or len(last_stat[self.statistic_id]) == 0:
            _LOGGER.debug("Last stats not exist. Trying to fetch ALL data.")
            all_stats = list((await self._bosch_object.fetch_all()).values())
            if not all_stats:
                _LOGGER.warn("Stats not found.")
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
        last_stat_start = timestamp_to_datetime_or_none(last_stat_row["start"])

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

        async def get_last_stats_from_bosch_api():
            last_stats_row = self.get_last_stats_before_date(
                last_stats=last_stats, day=start_of_yesterday_utc
            )
            start_time = last_stats_row["start"]
            _sum = last_stats_row["sum"] or 0
            if isinstance(start_time, float):
                start_time = timestamp_to_datetime_or_none(start_time)
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
            return self._bosch_object.last_entry.values(), _sum

        if self.statistic_id in last_stats:
            all_stats, _sum = await get_last_stats_from_bosch_api()
            self.append_statistics(stats=all_stats, sum=_sum)
