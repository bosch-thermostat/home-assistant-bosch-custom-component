"""Bosch sensor for Energy URI in Easycontrol."""
from __future__ import annotations
import logging
import datetime
from bosch_thermostat_client.const import UNITS
from .statistic_helper import StatisticHelper
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
    STATE_UNAVAILABLE,
    TEMP_CELSIUS,
    VOLUME_CUBIC_METERS,
)
from homeassistant.components.recorder.statistics import (
    get_last_statistics,
)
from homeassistant.components.recorder import get_instance
from homeassistant.util import dt as dt_util
from homeassistant.components.recorder.models import StatisticData


from ..const import SIGNAL_ENERGY_UPDATE_BOSCH, VALUE
from .bosch import BoschSensor

_LOGGER = logging.getLogger(__name__)

EnergySensors = [
    {"name": "energy temperature", "attr": "T", "unitOfMeasure": TEMP_CELSIUS},
    {
        "name": "energy central heating",
        "attr": "eCH",
        "unitOfMeasure": ENERGY_KILO_WATT_HOUR,
    },
    {"name": "energy hot water", "attr": "eHW", "unitOfMeasure": ENERGY_KILO_WATT_HOUR},
]

EcusRecordingSensors = [
    {
        "name": "ecus avg outdoor temperature",
        "attr": "T",
        "unitOfMeasure": TEMP_CELSIUS,
        "normalize": lambda x: x / 10,
    },
    {
        "name": "central heating",
        "attr": "ch",
        "unitOfMeasure": VOLUME_CUBIC_METERS,
    },
    {"name": "hot water", "attr": "hw", "unitOfMeasure": VOLUME_CUBIC_METERS},
]


class EnergySensor(BoschSensor, StatisticHelper):
    """Representation of Energy Sensor."""

    signal = SIGNAL_ENERGY_UPDATE_BOSCH
    _domain_name = "Sensors"

    def __init__(
        self,
        sensor_attributes,
        new_stats_api: bool = False,
        **kwargs,
    ) -> None:
        """Initialize Energy sensor."""
        BoschSensor.__init__(self, name=sensor_attributes.get("name"), **kwargs)
        StatisticHelper.__init__(self, new_stats_api=new_stats_api)
        self._read_attr = sensor_attributes.get("attr")
        self._normalize = sensor_attributes.get("normalize")
        self._unit_of_measurement = sensor_attributes.get(UNITS)
        self._attr_device_class = (
            SensorDeviceClass.TEMPERATURE
            if self._unit_of_measurement == TEMP_CELSIUS
            else SensorDeviceClass.ENERGY
        )

    async def async_update(self) -> None:
        """Update state of device."""
        data = self._bosch_object.get_property(self._attr_uri)
        value = data.get(VALUE)
        if not value or self._read_attr not in value:
            _LOGGER.debug("Reading attribute not available %s", self._read_attr)
            self._state = STATE_UNAVAILABLE
            return
        if self._new_stats_api and (
            self._unit_of_measurement == ENERGY_KILO_WATT_HOUR
            or self._unit_of_measurement == VOLUME_CUBIC_METERS
        ):
            await self._insert_statistics()
        else:
            if self._normalize:
                self._state = self._normalize(value.get(self._read_attr))
            else:
                self._state = value.get(self._read_attr)
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()

    @property
    def statistic_id(self) -> str:
        """External API statistic ID."""
        if not self._short_id:
            self._short_id = self.entity_id.replace(".", "").replace("sensor", "")
        return f"{self._domain_name}:{self._read_attr}{self._short_id}external".lower()

    def _generate_easycontrol_statistics(
        self, start: datetime, end: datetime, single_value: int, init_value: int
    ) -> tuple[int, list[StatisticData]]:
        statistics = []
        now = start
        _sum = init_value
        while now < end:
            _sum = _sum + single_value
            statistics.append(
                StatisticData(
                    start=now,
                    state=single_value,
                    sum=_sum,
                )
            )
            now = now + datetime.timedelta(hours=1)
        return (_sum, statistics)

    async def _insert_statistics(self) -> None:
        """Insert statistics from the past."""

        last_stats = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.statistic_id,
            True,
            {"last_reset", "max", "mean", "min", "state", "sum"},
        )
        today = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = None
        if not last_stats:
            all_stats = (await self._bosch_object.fetch_all()).values()
            if not all_stats:
                return
            _sum = 0
        elif self.statistic_id in last_stats:
            self._bosch_object.clear_past_data(self._read_attr)
            last_stats_row = last_stats[self.statistic_id][0]
            end_time = last_stats_row["end"]
            _sum = last_stats_row["sum"] or 0
            all_stats = self._bosch_object.last_entry.values()
        statistics_to_push = []
        for stat in all_stats:
            day_dt = datetime.datetime.strptime(stat["d"], "%d-%m-%Y")
            if end_time and day_dt.date() <= end_time.date():
                _LOGGER.debug("Don't add day which is probably in database already.")
                continue
            day_dt = today.replace(year=day_dt.year, month=day_dt.month, day=day_dt.day)
            _sum, statistics = self._generate_easycontrol_statistics(
                start=day_dt,
                end=day_dt + datetime.timedelta(days=1),
                single_value=round(stat[self._read_attr] / 24, 3),
                init_value=_sum,
            )
            statistics_to_push += statistics
        _LOGGER.debug("Inserting external stats %s.", self.statistic_id)
        self.add_external_stats(stats=statistics_to_push)
