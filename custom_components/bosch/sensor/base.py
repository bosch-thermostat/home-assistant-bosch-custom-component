import logging
from datetime import datetime, timedelta
from homeassistant.components.sensor import (
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from bosch_thermostat_client.const import UNITS, VALUE
from bosch_thermostat_client.const.ivt import INVALID

from ..const import (
    DOMAIN,
    MINS,
    UNITS_CONVERTER,
)


from homeassistant.const import (
    DEVICE_CLASS_ENERGY,
)

_LOGGER = logging.getLogger(__name__)


class BoschBaseSensor(SensorEntity):
    def __init__(
        self,
        hass,
        uuid,
        bosch_object,
        gateway,
        name,
        attr_uri,
        domain_name,
        circuit_type=None,
        is_enabled=False,
    ):
        """Initialize the sensor."""
        self.hass = hass
        self._bosch_object = bosch_object
        self._gateway = gateway
        self._domain_name = domain_name
        self._name = (domain_name + " " + name) if domain_name != "Sensors" else name
        self._attr_uri = attr_uri
        self._state = None
        self._update_init = True
        self._unit_of_measurement = None
        self._uuid = uuid
        self._unique_id = self._domain_name + self._name + self._uuid
        self._attrs = {}
        self._circuit_type = circuit_type
        self._is_enabled = is_enabled

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            self.signal, self.async_update
        )

    @property
    def _domain_identifier(self):
        return {(DOMAIN, self._domain_name + self._uuid)}

    @property
    def _sensor_name(self):
        raise NotImplementedError

    @property
    def signal(self):
        raise NotImplementedError

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return self._unique_id

    @property
    def bosch_object(self):
        """Return upstream component. Used for refreshing."""
        return self._bosch_object

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

    @property
    def device_info(self):
        """Get attributes about the device."""
        return {
            "identifiers": self._domain_identifier,
            "manufacturer": self._gateway.device_model,
            "model": self._gateway.device_type,
            "name": self._sensor_name,
            "sw_version": self._gateway.firmware,
            "via_hub": (DOMAIN, self._uuid),
        }

    async def async_update(self):
        """Update state of device."""
        _LOGGER.debug("Update of sensor %s called.", self.unique_id)
        data = self._bosch_object.get_property(self._attr_uri)

        def get_units():
            if not isinstance(data, list):
                return UNITS_CONVERTER.get(data.get(UNITS))
            return None

        units = get_units()

        if self._bosch_object.device_class == DEVICE_CLASS_ENERGY:
            self._attr_device_class = DEVICE_CLASS_ENERGY
        if self._bosch_object.state_class == STATE_CLASS_MEASUREMENT:
            self._attr_state_class = STATE_CLASS_MEASUREMENT
        elif self._bosch_object.state_class == STATE_CLASS_TOTAL_INCREASING:
            self._attr_state_class = STATE_CLASS_TOTAL_INCREASING
        if units == MINS and data:
            self.time_sensor_data(data)
        else:
            if data.get(INVALID, False):
                self._state = INVALID
            else:
                self._state = data.get(VALUE, INVALID)
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
