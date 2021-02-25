"""Support for Bosch Thermostat Climate."""
import logging

from bosch_thermostat_client.const import SETPOINT
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import SUPPORT_TARGET_TEMPERATURE
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    BOSCH_STATE,
    CLIMATE,
    DOMAIN,
    GATEWAY,
    SIGNAL_BOSCH,
    SIGNAL_CLIMATE_UPDATE_BOSCH,
    SWITCHPOINT,
    UNITS_CONVERTER,
    UUID,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch thermostat from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    data[CLIMATE] = [
        BoschThermostat(hass, uuid, hc, data[GATEWAY])
        for hc in data[GATEWAY].heating_circuits
    ]
    async_add_entities(data[CLIMATE])
    async_dispatcher_send(hass, SIGNAL_BOSCH)
    return True


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Bosch Thermostat Platform."""
    pass


class BoschThermostat(ClimateEntity):
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
            "manufacturer": self._gateway.device_model,
            "model": self._gateway.device_type,
            "name": "Heating circuit " + self._name,
            "sw_version": self._gateway.firmware,
            "via_hub": (DOMAIN, self._uuid),
        }

    @property
    def state_attributes(self):
        data = super().state_attributes
        try:
            data[SETPOINT] = self._hc.setpoint
            data[SWITCHPOINT] = self._hc.schedule.active_program
            data[BOSCH_STATE] = self._state
        except NotImplementedError:
            pass
        return data

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

    async def async_set_hvac_mode(self, hvac_mode):
        """Set operation mode."""
        _LOGGER.debug(f"Setting operation mode {hvac_mode}.")
        status = await self._hc.set_ha_mode(hvac_mode)
        # if status == 2:
        #     async_track_point_in_time(
        #         self.hass, self.async_purge, dt_util.utcnow() + timedelta(seconds=1)
        #     )
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

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._hc.min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self._hc.max_temp

    def update(self):
        """Update state of device."""
        _LOGGER.debug("Update of climate %s component called.", self._name)
        if not self._hc or not self._hc.update_initialized:
            return
        self._temperature_units = UNITS_CONVERTER.get(self._hc.temp_units)
        if (
            self._state != self._hc.state
            or self._target_temperature != self._hc.target_temperature
            or self._current_temperature != self._hc.current_temp
            or self._hvac_modes != self._hc.ha_modes
            or self._hvac_mode != self._hc.ha_mode
        ):
            self._state = self._hc.state
            self._target_temperature = self._hc.target_temperature
            self._current_temperature = self._hc.current_temp
            self._hvac_modes = self._hc.ha_modes
            self._hvac_mode = self._hc.ha_mode
            self.async_schedule_update_ha_state()
