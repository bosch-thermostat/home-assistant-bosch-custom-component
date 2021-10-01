import logging
from datetime import datetime, timedelta

from bosch_thermostat_client.const import UNITS, VALUE, NAME
from bosch_thermostat_client.const.ivt import INVALID
from homeassistant.components.sensor import (
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from homeassistant.const import DEVICE_CLASS_ENERGY

from ..const import DOMAIN, MINS, UNITS_CONVERTER
from ..bosch_entity import BoschEntity

_LOGGER = logging.getLogger(__name__)


class BoschBaseSensor(BoschEntity, SensorEntity):
    """Base class for all sensor entities."""

    def __init__(
        self,
        hass,
        uuid,
        bosch_object,
        gateway,
        name,
        attr_uri,
        domain_name=None,
        circuit_type=None,
        is_enabled=False,
    ):
        """Initialize the sensor."""
        super().__init__(
            hass=hass, uuid=uuid, bosch_object=bosch_object, gateway=gateway
        )
        if domain_name:
            self._domain_name = domain_name
        self._name = (
            (self._domain_name + " " + name) if self._domain_name != "Sensors" else name
        )
        self._attr_uri = attr_uri
        self._state = None
        self._update_init = True
        self._unit_of_measurement = None
        self._uuid = uuid
        self._unique_id = self._domain_name + self._name + self._uuid
        self._attrs = {}
        self._circuit_type = circuit_type
        self._is_enabled = is_enabled

    @property
    def _domain_identifier(self):
        return {(DOMAIN, self._domain_name + self._uuid)}

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement

    @property
    def device_state_attributes(self):
        """Return the state attributes of the sensor."""
        return self._attrs

    @property
    def entity_registry_enabled_default(self):
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._is_enabled

    def update(self):
        """Update state of device."""
        _LOGGER.debug("Update of sensor %s called.", self.unique_id)
        data = self._bosch_object.get_property(self._attr_uri)

        def get_units():
            if not isinstance(data, list):
                return UNITS_CONVERTER.get(data.get(UNITS))
            return None

        def detect_device_class():
            if self._bosch_object.device_class == DEVICE_CLASS_ENERGY:
                self._attr_device_class = DEVICE_CLASS_ENERGY
            if self._bosch_object.state_class == STATE_CLASS_MEASUREMENT:
                self._attr_state_class = STATE_CLASS_MEASUREMENT
            elif self._bosch_object.state_class == STATE_CLASS_TOTAL_INCREASING:
                self._attr_state_class = STATE_CLASS_TOTAL_INCREASING

        def check_name():
            if data.get(NAME, "") != self._name:
                self._name = data.get(NAME)

        units = get_units()
        if not hasattr(self, "_attr_device_class"):
            detect_device_class()

        if units == MINS and data:
            self.time_sensor_data(data)
        else:
            if data.get(INVALID, False):
                self._state = INVALID
            else:
                self._state = data.get(VALUE, INVALID)
                check_name()

            self._attrs = {}
            self._attrs["stateExtra"] = self._bosch_object.state
            if not data:
                if not self._bosch_object.update_initialized:
                    self._state = self._bosch_object.state
                    self._attrs["stateExtra"] = self._bosch_object.state_message
                return
            self.attrs_write(data=data, units=units)

    def time_sensor_data(self, data):
        value = data.get(VALUE, INVALID)
        now = datetime.now()
        next_from_midnight = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(minutes=value)
        if now >= next_from_midnight:
            self._state = next_from_midnight + timedelta(days=1)
        else:
            self._state = next_from_midnight
        data["device_class"] = "timestamp"
        self.attrs_write(data=data, units=None)

    def attrs_write(self, data, units):
        self._attrs = data
        if self._state != INVALID:
            self._unit_of_measurement = units
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()
