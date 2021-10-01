"""Bosch sensor for Energy URI in Easycontrol."""
from .bosch import BoschSensor
from bosch_thermostat_client.const import UNITS
from homeassistant.const import (
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_TEMPERATURE,
    STATE_UNAVAILABLE,
    ENERGY_KILO_WATT_HOUR,
    TEMP_CELSIUS,
)
from homeassistant.components.sensor import STATE_CLASS_MEASUREMENT

from ..const import SIGNAL_ENERGY_UPDATE_BOSCH, VALUE

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

    def __init__(
        self,
        hass,
        uuid,
        bosch_object,
        gateway,
        sensor_attributes,
        attr_uri,
        is_enabled=False,
    ):
        self._read_attr = sensor_attributes.get("attr")
        self._unit_of_measurement = sensor_attributes.get(UNITS)
        self._attr_device_class = (
            DEVICE_CLASS_TEMPERATURE
            if self._unit_of_measurement == TEMP_CELSIUS
            else DEVICE_CLASS_ENERGY
        )

        super().__init__(
            hass,
            uuid,
            bosch_object,
            gateway,
            sensor_attributes.get("name"),
            attr_uri,
            circuit_type=None,
            is_enabled=is_enabled,
        )

    def update(self):
        """Update state of device."""
        data = self._bosch_object.get_property(self._attr_uri)
        value = data.get(VALUE)
        if not value or self._read_attr not in value:
            self._state = STATE_UNAVAILABLE
            return
        self._state = value.get(self._read_attr)
        self._attr_last_reset = data.get("last_reset")
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()

    @property
    def state_class(self):
        return STATE_CLASS_MEASUREMENT
