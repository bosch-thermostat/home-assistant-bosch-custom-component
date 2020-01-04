"""Support for Bosch Thermostat Sensor."""
import logging

from bosch_thermostat_http.const import SYSTEM_BRAND, SYSTEM_TYPE, STATUS, VALUE
from homeassistant.helpers.entity import Entity

from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import (
    DOMAIN,
    SIGNAL_SENSOR_UPDATE_BOSCH,
    SIGNAL_SOLAR_UPDATE_BOSCH,
    GATEWAY,
    SENSORS,
    UNITS_CONVERTER,
    UUID,
    SENSOR,
    SOLAR,
    SIGNAL_BOSCH
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Bosch Thermostat Sensor Platform."""
    pass


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Thermostat from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    enabled_sensors = config_entry.data.get(SENSORS, [])
    enabled_solars = config_entry.data.get(SOLAR, [])
    data[SENSOR] = [
        BoschSensor(
            hass, uuid, sensor, data[GATEWAY], sensor.name, sensor.attr_id in enabled_sensors
        )
        for sensor in data[GATEWAY].sensors
    ]
    for circuit in data[GATEWAY].solar_circuits:
        data[SOLAR] = [
            CircuitSensor(
                hass, uuid, circuit, data[GATEWAY], circuit_sensor, circuit_sensor in enabled_solars
            )
            for circuit_sensor in circuit.get_all_properties
        ]
    async_add_entities(data[SENSOR])
    async_add_entities(data[SOLAR])
    async_dispatcher_send(hass, SIGNAL_BOSCH)
    return True


class BoschBaseSensor(Entity):

    def __init__(self, hass, uuid, bosch_object, gateway, name, is_enabled=False):
        """Initialize the sensor."""
        self.hass = hass
        self._bosch_object = bosch_object
        self._str = self._bosch_object.strings
        self._gateway = gateway
        self._name = name
        self._state = None
        self._update_init = True
        self._unit_of_measurement = None
        self._uuid = uuid
        self._unique_id = self._name + self._uuid
        self._attrs = {}
        self._is_enabled = is_enabled

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
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
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
            "manufacturer": self._gateway.get_info(SYSTEM_BRAND),
            "model": self._gateway.get_info(SYSTEM_TYPE),
            "name": self._sensor_name,
            "sw_version": self._gateway.firmware,
            "via_hub": (DOMAIN, self._uuid),
        }


class BoschSensor(BoschBaseSensor):
    """Representation of a Bosch sensor."""

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_SENSOR_UPDATE_BOSCH, self.async_update
        )

    @property
    def _domain_identifier(self):
        return {(DOMAIN, "Sensors" + self._uuid)}

    @property
    def _sensor_name(self):
        return "Bosch sensors"

    async def async_update(self):
        """Update state of device."""
        _LOGGER.debug("Update of sensor %s called.", self._name)
        # await self._sensor.update()
        data = self._bosch_object.get_all_values()
        self._state = data.get(self._str.val, self._str.invalid)
        self._attrs["stateExtra"] = self._state
        if not data:
            if not self._bosch_object.update_initialized:
                self._state = -1
                self._attrs["stateExtra"] = self._bosch_object.state_message
            return
        state = data.get(self._str.state, {})
        self._unit_of_measurement = UNITS_CONVERTER.get(data.get(self._str.units))
        if self._str.min in data:
            self._attrs[self._str.min] = data[self._str.min]
        if self._str.max in data:
            self._attrs[self._str.max] = data[self._str.max]
        if self._str.allowed_values in data:
            self._attrs[self._str.allowed_values] = data[self._str.allowed_values]
        if self._str.open in state:
            self._attrs["{}_{}".format(self._str.state, self._str.open)] = state[
                self._str.open
            ]
        if self._str.short in state:
            self._attrs["{}_{}".format(self._str.state, self._str.short)] = state[
                self._str.short
            ]
        if self._str.invalid in state:
            self._attrs["{}_{}".format(self._str.state, self._str.invalid)] = state[
                self._str.invalid
            ]
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()


class CircuitSensor(BoschBaseSensor):
    """Representation of a Bosch sensor."""

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_SOLAR_UPDATE_BOSCH, self.async_update
        )

    @property
    def _domain_identifier(self):
        return {(DOMAIN, "Circuit sensors" + self._uuid)}

    @property
    def _sensor_name(self):
        return "Circuit sensors"

    async def async_update(self):
        """Update state of device."""
        _LOGGER.debug("Update of sensor %s called.", self._name)
        # await self._sensor.update()
        data = self._bosch_object.get_property(self._name)
        value = data.get(self._str.val)
        if not value or not self._bosch_object.state:
            if not self._bosch_object.update_initialized:
                self._state = self._bosch_object.get_value(STATUS)
                self._attrs["stateExtra"] = self._bosch_object.state_message
            return
        self._state = value
        self._unit_of_measurement = UNITS_CONVERTER.get(data.get(self._str.units))
        if self._str.min in data:
            self._attrs[self._str.min] = data[self._str.min]
        if self._str.max in data:
            self._attrs[self._str.max] = data[self._str.max]
        if self._str.allowed_values in data:
            self._attrs[self._str.allowed_values] = data[self._str.allowed_values]
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()
