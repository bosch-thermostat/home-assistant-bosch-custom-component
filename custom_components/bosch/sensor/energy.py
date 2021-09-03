from .base import BoschBaseSensor
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
    TEMP_CELSIUS,
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_TEMPERATURE,
)
from ..const import (
    SIGNAL_ENERGY_UPDATE_BOSCH,
    VALUE,
)
from bosch_thermostat_client.const import UNITS

EnergySensors = [
    {"name": "energy temperature", "attr": "T", "unitOfMeasure": TEMP_CELSIUS},
    {
        "name": "energy central heating",
        "attr": "eCH",
        "unitOfMeasure": ENERGY_KILO_WATT_HOUR,
    },
    {"name": "energy hot water", "attr": "eHW", "unitOfMeasure": ENERGY_KILO_WATT_HOUR},
]


class EnergySensor(BoschBaseSensor):
    """Representation of Energy Sensor."""

    def __init__(
        self,
        hass,
        uuid,
        bosch_object,
        gateway,
        sensor_attributes,
        attr_uri,
        domain_name,
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
            domain_name,
            circuit_type=None,
            is_enabled=is_enabled,
        )

    @property
    def _sensor_name(self):
        return "Energy sensors"

    async def async_update(self):
        """Update state of device."""
        data = self._bosch_object.get_property(self._attr_uri)
        self._state = data.get(VALUE).get(self._read_attr)
        self._attr_last_reset = data.get("last_reset")
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()

    @property
    def signal(self):
        return SIGNAL_ENERGY_UPDATE_BOSCH
