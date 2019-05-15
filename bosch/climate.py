"""Support for Bosch Thermostat Climate."""
import logging


from bosch_thermostat_http.const import (OPERATION_MODE,
                                         HC_HOLIDAY_MODE,
                                         HC_HEATING_STATUS,
                                         SYSTEM_BRAND, FIRMWARE_VERSION,
                                         SYSTEM_TYPE, VALUE, ALLOWED_VALUES)
from homeassistant.components.climate import ClimateDevice
from homeassistant.components.climate.const import (
    STATE_MANUAL, STATE_IDLE, STATE_AUTO, SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_OPERATION_MODE)
from homeassistant.const import (
    TEMP_CELSIUS, TEMP_FAHRENHEIT, ATTR_TEMPERATURE, STATE_OFF)

from .const import DOMAIN, SIGNAL_CLIMATE_UPDATE_BOSCH

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch thermostat from a config entry."""
    uuid = config_entry.title
    data = hass.data[DOMAIN][uuid]
    data['hcs'] = [BoschThermostat(hass, uuid, hc, data['gateway'])
                   for hc in data['gateway'].heating_circuits]
    async_add_entities(data['hcs'])
    return True


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the Bosch Thermostat Platform."""
    pass


class BoschThermostat(ClimateDevice):
    """Representation of a Bosch thermostat."""

    def __init__(self, hass, uuid, hc, gateway):
        """Initialize the thermostat."""
        self.hass = hass

        self._hc = hc
        self._name = self._hc.name
        self._current_temperature = None
        self._temperature_unit = TEMP_CELSIUS
        self._holiday_mode = None
        self._mode = None
        self._state = None
        self._operation_list = None
        self._uuid = uuid
        self._unique_id = self._name+self._uuid
        self._gateway = gateway
        self._possible_operations = {
            'ACTIVE': STATE_MANUAL
        }
        self._support_flags = (SUPPORT_TARGET_TEMPERATURE |
                               SUPPORT_OPERATION_MODE)
        # self.hass.helpers.dispatcher.dispatcher_connect(
        #     SIGNAL_UPDATE_BOSCH, self.update)

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_CLIMATE_UPDATE_BOSCH, self.update)

    @property
    def device_info(self):
        """Get attributes about the device."""
        return {
            'identifiers': {
                (DOMAIN, self._unique_id)
            },
            'manufacturer': self._gateway.get_info(SYSTEM_BRAND),
            'model': self._gateway.get_info(SYSTEM_TYPE),
            'name': 'Heating circuit ' + self._name,
            'sw_version': self._gateway.get_info(FIRMWARE_VERSION),
            'via_hub': (DOMAIN, self._uuid)
        }

    @property
    def upstream_object(self):
        """Return upstream component. Used for refreshing."""
        return self._hc

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the thermostat, if any."""
        return self._name

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support_flags

    @property
    def temperature_unit(self):
        """Return the unit of measurement which this thermostat uses."""
        return self._temperature_unit

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._hc.current_temp

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._hc.target_temperature

    @property
    def holiday_mode(self):
        """Return the holiday mode state."""
        return self._holiday_mode

    @property
    def working_state(self):
        """Return the holiday mode state."""
        return self._holiday_mode

    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        _LOGGER.debug("Setting operation mode %s.", operation_mode)
        if self._mode and operation_mode in (STATE_AUTO, STATE_MANUAL):
            self._mode[VALUE] = await\
                self._hc.set_operation_mode(operation_mode)
            _LOGGER.debug("Set operation mode to %s.", self._mode[VALUE])
            return True
        self._mode = self._hc.get_property(OPERATION_MODE)
        return False

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if self._hc.target_temperature:
            temperature = kwargs.get(ATTR_TEMPERATURE)
            if temperature is None:
                return
            if temperature != self._hc.target_temperature:
                await self._hc.set_temperature(temperature)
            await self.async_update_ha_state()

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        if self._mode:
            if not self._mode[VALUE]:
                return STATE_IDLE
            if self._mode[VALUE] == STATE_AUTO:
                return STATE_AUTO
            if self._mode[VALUE] == STATE_MANUAL:
                return STATE_MANUAL
        return STATE_OFF

    @property
    def operation_list(self):
        """List of available operation modes."""
        if self._mode:
            return self._mode.get(ALLOWED_VALUES)

    def update(self):
        """Update state of device."""
        _LOGGER.debug("Update of climate component called.")
        if (not self._hc or not self._hc.json_scheme_ready or
                not self._hc.update_initialized):
            return
        self._state = self._hc.get_value(HC_HEATING_STATUS)
        self._temperature_unit = (TEMP_FAHRENHEIT if self._hc.temp_units == 'F'
                                  else TEMP_CELSIUS)
        self._holiday_mode = self._hc.get_value(HC_HOLIDAY_MODE)
        self._mode = self._hc.get_property(OPERATION_MODE)
        _LOGGER.debug("Retrieved mode %s", self._mode)
