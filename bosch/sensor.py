"""Support for Bosch Thermostat Sensor."""
import logging

from bosch_thermostat_http.const import (VALUE, UNITS, MINVALUE, MAXVALUE,
                                         STATE, OPEN, SHORT, INVALID,
                                         ALLOWED_VALUES, SYSTEM_BRAND,
                                         SYSTEM_TYPE, FIRMWARE_VERSION)
from homeassistant.helpers.entity import Entity
from homeassistant.const import (
    TEMP_CELSIUS, TEMP_FAHRENHEIT)

from .const import DOMAIN, SIGNAL_SENSOR_UPDATE_BOSCH, GATEWAY

UNITS_CONVERTER = {
    'C': TEMP_CELSIUS,
    'F': TEMP_FAHRENHEIT,
    '%': '%',
    'l/min': 'l/min',
    'l/h': 'l/h',
    'kg/l': 'kg/l',
    'mins': 'mins',
    'kW': 'kW',
    'kWh': 'kWh',
    'Pascal': 'Pascal',
    'bar': 'bar',
    'µA': 'µA',
    ' ': None
}

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the Bosch Thermostat Sensor Platform."""
    pass


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Thermostat from a config entry."""
    uuid = config_entry.title
    data = hass.data[DOMAIN][uuid]
    data['sensors'] = [BoschSensor(hass, uuid, sensor, data[GATEWAY])
                       for sensor in data[GATEWAY].sensors]
    async_add_entities(data['sensors'])
    return True


class BoschSensor(Entity):
    """Representation of a Bosch sensor."""

    def __init__(self, hass, uuid, sensor, gateway):
        """Initialize the sensor."""
        self.hass = hass
        self._sensor = sensor
        self._gateway = gateway
        self._name = self._sensor.name
        self._state = None
        self._unit_of_measurement = None
        self._uuid = uuid
        self._unique_id = self._name+self._uuid
        self._attrs = {}
        # self.hass.helpers.dispatcher.dispatcher_connect(
        #     SIGNAL_UPDATE_BOSCH, self.update)

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_SENSOR_UPDATE_BOSCH, self.async_update)

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
            'sw_version': self._gateway.get_info(FIRMWARE_VERSION),
            'via_hub': (DOMAIN, self._uuid)
        }

    @property
    def upstream_object(self):
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
        if not data:
            self._state = "Invalid"
            return
        self._state = data[VALUE] if VALUE in data else 0
        if UNITS in data and data[UNITS] in UNITS_CONVERTER:
            self._unit_of_measurement = UNITS_CONVERTER[data[UNITS]]
        if MINVALUE in data:
            self._attrs[MINVALUE] = data[MINVALUE]
        if MAXVALUE in data:
            self._attrs[MAXVALUE] = data[MAXVALUE]
        if ALLOWED_VALUES in data:
            self._attrs[ALLOWED_VALUES] = data[ALLOWED_VALUES]
        if STATE in data:
            if OPEN in data[STATE]:
                self._attrs['{}_{}'.format(STATE, OPEN)] = data[STATE][OPEN]
            if SHORT in data[STATE]:
                self._attrs['{}_{}'.format(STATE, SHORT)] = data[STATE][SHORT]
            if INVALID in data[STATE]:
                self._attrs['{}_{}'.format(STATE,
                                           INVALID)] = data[STATE][INVALID]
