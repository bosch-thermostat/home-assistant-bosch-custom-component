"""Support for Bosch Thermostat Sensor."""
import logging

from bosch_thermostat_http.const import (SYSTEM_BRAND, SYSTEM_TYPE)
from homeassistant.helpers.entity import Entity

from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import (DOMAIN, SIGNAL_SENSOR_UPDATE_BOSCH, GATEWAY, SENSORS,
                    UNITS_CONVERTER, UUID, SENSOR)

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the Bosch Thermostat Sensor Platform."""
    pass


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Thermostat from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    enabled_sensors = config_entry.data.get(SENSORS, [])
    data[SENSOR] = [BoschSensor(hass, uuid, sensor, data[GATEWAY], sensor.attr_id in enabled_sensors)
                        for sensor in data[GATEWAY].sensors]
    async_add_entities(data[SENSOR])
    async_dispatcher_send(hass, "climate_signal")
    return True


class BoschSensor(Entity):
    """Representation of a Bosch sensor."""

    def __init__(self, hass, uuid, sensor, gateway, is_enabled=False):
        """Initialize the sensor."""
        self.hass = hass
        self._sensor = sensor
        self._str = self._sensor.strings
        self._gateway = gateway
        self._name = self._sensor.name
        self._state = None
        self._update_init = True
        self._unit_of_measurement = None
        self._uuid = uuid
        self._unique_id = self._name+self._uuid
        self._attrs = {}
        self._is_enabled = is_enabled

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_SENSOR_UPDATE_BOSCH, self.async_update)

    @property
    def entity_registry_enabled_default(self):
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._is_enabled

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def device_info(self):
        """Get attributes about the device."""
        return {
            'identifiers': {
                (DOMAIN, 'Sensors'+self._uuid)
            },
            'manufacturer': self._gateway.get_info(SYSTEM_BRAND),
            'model': self._gateway.get_info(SYSTEM_TYPE),
            'name': 'Bosch sensors',
            'sw_version': self._gateway.firmware,
            'via_hub': (DOMAIN, self._uuid)
        }

    @property
    def bosch_object(self):
        """Return upstream component. Used for refreshing."""
        return self._sensor

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return self._unique_id

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

    async def async_update(self):
        """Update state of device."""
        # await self._sensor.update()
        data = self._sensor.get_all_properties()
        self._state = data.get(self._str.val, self._str.invalid)
        self._attrs["stateExtra"] = self._state
        if not data:
            if not self._sensor.update_initialized:
                self._state = -1
                self._attrs["stateExtra"] = "Waiting to fetch data"
            return
        state = data.get(self._str.state, {})
        self._unit_of_measurement = UNITS_CONVERTER.get(
            data.get(self._str.units))
        if self._str.min in data:
            self._attrs[self._str.min] = data[self._str.min]
        if self._str.max in data:
            self._attrs[self._str.max] = data[self._str.max]
        if self._str.allowed_values in data:
            self._attrs[self._str.allowed_values] = \
                data[self._str.allowed_values]
        if self._str.open in state:
            self._attrs['{}_{}'.format(
                self._str.state, self._str.open)] = state[self._str.open]
        if self._str.short in state:
            self._attrs['{}_{}'.format(
                self._str.state,
                self._str.short)] = state[self._str.short]
        if self._str.invalid in state:
            self._attrs['{}_{}'.format(
                self._str.state,
                self._str.invalid)] = state[self._str.invalid]
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()
