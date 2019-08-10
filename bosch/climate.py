"""Support for Bosch Thermostat Climate."""
import logging

from bosch_thermostat_http.const import (OPERATION_MODE, STATUS,
                                         SYSTEM_BRAND, SYSTEM_TYPE)

from homeassistant.components.climate import ClimateDevice
from homeassistant.components.climate.const import (HVAC_MODE_AUTO,
                                                    HVAC_MODE_HEAT,
                                                    HVAC_MODE_OFF,
                                                    SERVICE_SET_HVAC_MODE,
                                                    SUPPORT_TARGET_TEMPERATURE)
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS, TEMP_FAHRENHEIT

from .const import DOMAIN, GATEWAY, HCS, SIGNAL_CLIMATE_UPDATE_BOSCH

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch thermostat from a config entry."""
    uuid = config_entry.title
    data = hass.data[DOMAIN][uuid]
    data[HCS] = [BoschThermostat(hass, uuid, hc, data[GATEWAY])
                 for hc in data[GATEWAY].heating_circuits]
    async_add_entities(data[HCS])
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
        self._mode = {}
        self._state = None
        self._operation_list = None
        self._uuid = uuid
        self._unique_id = self._name+self._uuid
        self._gateway = gateway
        self._op_modes = {
            HVAC_MODE_AUTO: self._hc.strings.auto,
            HVAC_MODE_HEAT: self._hc.strings.manual
        }
        self._op_modes_inv = {v: k for k, v in self._op_modes.items()}

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
            'sw_version': self._gateway.firmware,
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
        return SUPPORT_TARGET_TEMPERATURE

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

    async def async_set_hvac_mode(self, operation_mode):
        """Set operation mode."""
        _LOGGER.debug("Setting operation mode %s.", operation_mode)
        op_mode = self._op_modes.get(operation_mode)
        if op_mode and op_mode != self._mode.get(self._hc.strings.val):
            self._mode[self._hc.strings.val] = await\
                self._hc.set_operation_mode(op_mode)
            _LOGGER.debug("Set operation mode to %s.",
                          self._mode[self._hc.strings.val])
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
    def hvac_mode(self):
        """Return current operation ie. heat, cool, idle."""
        return self._op_modes_inv.get(self._mode.get(self._hc.strings.val),
                                      HVAC_MODE_OFF)

    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return self._mode.get(self._hc.strings.allowed_values)

    def update(self):
        """Update state of device."""
        _LOGGER.debug("Update of climate component called.")
        if (not self._hc or not self._hc.json_scheme_ready or
                not self._hc.update_initialized):
            return
        self._state = self._hc.get_value(STATUS)
        self._temperature_unit = (TEMP_FAHRENHEIT if self._hc.temp_units == 'F'
                                  else TEMP_CELSIUS)
        # self._holiday_mode = self._hc.get_value(HC_HOLIDAY_MODE)
        self._mode = self._hc.get_property(OPERATION_MODE)
        _LOGGER.debug("Retrieved mode %s", self._mode)
