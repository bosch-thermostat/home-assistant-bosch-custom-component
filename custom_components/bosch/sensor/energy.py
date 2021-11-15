"""Bosch sensor for Energy URI in Easycontrol."""
from bosch_thermostat_client.const import UNITS
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

    def update(self):
        """Update state of device."""
        data = self._bosch_object.get_property(self._attr_uri)
        value = data.get(VALUE)
        if not value or self._read_attr not in value:
            self._state = STATE_UNAVAILABLE
            return
        self._state = value.get(self._read_attr)
        self._attr_last_reset = data.get(LAST_RESET)
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()

    @property
    def state_class(self):
        return STATE_CLASS_TOTAL
