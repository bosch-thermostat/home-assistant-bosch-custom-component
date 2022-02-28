"""Bosch sensor for Energy URI in Easycontrol."""
import datetime
import logging

import homeassistant.util.dt as dt_util
from bosch_thermostat_client.const import UNITS
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.components.sensor import STATE_CLASS_TOTAL
from homeassistant.const import (
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_TEMPERATURE,
    ENERGY_KILO_WATT_HOUR,
    STATE_UNAVAILABLE,
    TEMP_CELSIUS,
)

from ..const import LAST_RESET, SIGNAL_ENERGY_UPDATE_BOSCH, VALUE
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


class EnergySensor(BoschSensor):
    """Representation of Energy Sensor."""

    signal = SIGNAL_ENERGY_UPDATE_BOSCH
    _domain_name = "Sensors"

    def __init__(self, sensor_attributes, **kwargs):

        super().__init__(name=sensor_attributes.get("name"), **kwargs)

        self._read_attr = sensor_attributes.get("attr")
        self._unit_of_measurement = sensor_attributes.get(UNITS)
        self._attr_device_class = (
            DEVICE_CLASS_TEMPERATURE
            if self._unit_of_measurement == TEMP_CELSIUS
            else DEVICE_CLASS_ENERGY
        )

    async def async_update(self):
        """Update state of device."""
        data = self._bosch_object.get_property(self._attr_uri)
        value = data.get(VALUE)
        if not value or self._read_attr not in value:
            self._state = STATE_UNAVAILABLE
            return
        self._state = value.get(self._read_attr)
        self._attr_last_reset = data.get(LAST_RESET)
        if self._unit_of_measurement == ENERGY_KILO_WATT_HOUR:
            await self._insert_statistics(
                value=self._state, last_reset=self._attr_last_reset
            )
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()

    async def _insert_statistics(self, value, last_reset):
        """Insert some fake statistics."""
        last_reset_start = last_reset.replace(hour=0, minute=0, second=0, microsecond=0)

        def _generate_easycontrol_statistics(start, end, single_value, init_value):
            statistics = []
            now = start
            sum_ = init_value
            while now < end:
                sum_ = sum_ + single_value
                statistics.append(
                    {
                        "start": now,
                        "sum": sum_,
                    }
                )
                now = now + datetime.timedelta(hours=1)

            return statistics

        sum_ = 0
        statistic_id = f"{self._domain_name}:{self._read_attr}external".lower()
        last_stats = await self.hass.async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, True
        )
        if statistic_id in last_stats:
            last_stats_row = last_stats[statistic_id][0]
            end = last_stats_row["end"]
            end_time = datetime.datetime.strptime(end, "%Y-%m-%dT%H:%M:%S%z")
            if last_reset.date() == end_time.date():
                _LOGGER.debug("Skip re-adding day which already exists in database.")
                return
            sum_ = last_stats_row["sum"] or 0
        metadata = {
            "source": self._domain_name.lower(),
            "statistic_id": statistic_id,
            "unit_of_measurement": ENERGY_KILO_WATT_HOUR,
            "has_mean": False,
            "has_sum": True,
        }
        statistics = _generate_easycontrol_statistics(
            last_reset_start,
            last_reset_start + datetime.timedelta(days=1),
            single_value=round(value / 24, 1),
            init_value=sum_,
        )
        async_add_external_statistics(self.hass, metadata, statistics)

    @property
    def state_class(self):
        return STATE_CLASS_TOTAL
