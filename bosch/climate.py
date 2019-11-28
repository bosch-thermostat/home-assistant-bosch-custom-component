"""Support for Bosch Thermostat Climate."""
import logging
from datetime import timedelta
from bosch_thermostat_http.const import (
    OPERATION_MODE,
    STATUS,
    SYSTEM_BRAND,
    SYSTEM_TYPE,
    ALLOWED_VALUES,
    MANUAL_SETPOINT
)
import time

from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.components.climate import ClimateDevice
from homeassistant.components.climate.const import (
    HVAC_MODE_AUTO,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    SERVICE_SET_PRESET_MODE,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
)
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS, TEMP_FAHRENHEIT
from homeassistant.helpers.event import async_track_point_in_time
import homeassistant.util.dt as dt_util

from .const import DOMAIN, GATEWAY, HCS, SIGNAL_CLIMATE_UPDATE_BOSCH, UUID, CLIMATE, UNITS_CONVERTER

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch thermostat from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    data[CLIMATE] = ([BoschThermostat(hass, uuid, hc, data[GATEWAY])
                                          for hc in data[GATEWAY].heating_circuits])
    async_add_entities(data[CLIMATE])
    async_dispatcher_send(hass, "climate_signal")
    return True


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Bosch Thermostat Platform."""
    pass


class BoschThermostat(ClimateDevice):
    """Representation of a Bosch thermostat."""

    def __init__(self, hass, uuid, hc, gateway):
        """Initialize the thermostat."""
        self.hass = hass

        self._hc = hc
        self._name = self._hc.name
        self._temperature_unit = TEMP_CELSIUS
        self._mode = {}
        self._uuid = uuid
        self._unique_id = self._name + self._uuid
        self._gateway = gateway

        self._current_temperature = None
        self._state = None
        self._target_temperature = None
        self._hvac_modes = []
        self._hvac_mode = None
        

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_CLIMATE_UPDATE_BOSCH, self.update
        )

    @property
    def device_info(self):
        """Get attributes about the device."""
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
            "manufacturer": self._gateway.get_info(SYSTEM_BRAND),
            "model": self._gateway.get_info(SYSTEM_TYPE),
            "name": "Heating circuit " + self._name,
            "sw_version": self._gateway.firmware,
            "via_hub": (DOMAIN, self._uuid),
        }

    @property
    def bosch_object(self):
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
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    async def async_purge(self, now):
        _LOGGER.error("This is not needed for RC35, but probably needed for Rc300. We need to download manual uri if switched to manual.")
    # is_value_updated = await self._hc.update()
        # if is_value_updated:
            # dispatcher_send(self.hass, SIGNAL_CLIMATE_UPDATE_BOSCH)


    async def async_set_hvac_mode(self, hvac_mode):
        """Set operation mode."""
        _LOGGER.debug(f"Setting operation mode {hvac_mode}.")
        status = await self._hc.set_ha_mode(hvac_mode)
        if status == 2:
            async_track_point_in_time(
                self.hass, self.async_purge, dt_util.utcnow() + timedelta(seconds=1)
        )
        if status > 0:
            return True
        return False

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        _LOGGER.debug(f"Setting target temperature {temperature}.")
        await self._hc.set_temperature(temperature)

    @property
    def hvac_mode(self):
        """Return current operation ie. heat, cool, idle."""
        return self._hvac_mode

    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return self._hvac_modes

    def update(self):
        """Update state of device."""
        _LOGGER.debug("Update of climate %s component called.", self._name)
        if (
            not self._hc
            or not self._hc.update_initialized
        ):
            return
        self._temperature_units = UNITS_CONVERTER.get(self._hc.temp_units)
        if (
            self._state != self._hc.state or 
            self._target_temperature != self._hc.target_temperature or
            self._current_temperature != self._hc.current_temp or
            self._hvac_modes != self._hc.ha_modes or
            self._hvac_mode != self._hc.ha_mode
        ):
            self._state = self._hc.state
            self._target_temperature = self._hc.target_temperature
            self._current_temperature = self._hc.current_temp
            self._hvac_modes = self._hc.ha_modes
            self._hvac_mode = self._hc.ha_mode
            self.async_schedule_update_ha_state()