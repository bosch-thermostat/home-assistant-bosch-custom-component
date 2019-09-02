"""
Support for water heaters connected to Bosch thermostat.

For more details about this platform, please refer to the documentation at...
"""
import logging

from bosch_thermostat_http.const import (
    GATEWAY,
    OPERATION_MODE,
    SYSTEM_BRAND,
    SYSTEM_TYPE,
    CURRENT_TEMP,
    WATER_OFF,
    STATUS,
)

from homeassistant.components.water_heater import (
    STATE_HEAT_PUMP,
    STATE_HIGH_DEMAND,
    STATE_OFF,
    STATE_PERFORMANCE,
    SUPPORT_OPERATION_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    WaterHeaterDevice,
)
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS

from .const import (
    DHWS,
    DOMAIN,
    SIGNAL_DHW_UPDATE_BOSCH,
    UNITS_CONVERTER,
    BOSCH_GW_ENTRY,
)

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS_HEATER = SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE

DEFAULT_MIN_TEMP = 0
DEFAULT_MAX_TEMP = 100


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Water heater from a config entry."""
    uuid = config_entry.title
    data = hass.data[DOMAIN][uuid]
    data[DHWS] = [
        BoschWaterHeater(hass, uuid, dhw, data[GATEWAY])
        for dhw in data[GATEWAY].dhw_circuits
    ]
    async_add_entities(data[DHWS])
    await data[BOSCH_GW_ENTRY].water_heater_refresh()
    return True


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Bosch Thermostat Platform."""
    pass


class BoschWaterHeater(WaterHeaterDevice):
    """Representation of an EcoNet water heater."""

    def __init__(self, hass, uuid, dhw, gateway):
        """Initialize the water heater."""
        self.hass = hass
        self._dhw = dhw
        self._name = self._dhw.name
        self._uuid = uuid
        self._unique_id = self._name + self._uuid
        self._gateway = gateway
        self._mode = None
        self._state = None
        self._target_temperature = None
        self._current_temperature = None
        self._current_setpoint = None
        self._temperature_units = TEMP_CELSIUS
        self._max_temp = DEFAULT_MAX_TEMP
        self._low_temp = DEFAULT_MIN_TEMP
        self._target_temp_off = 0
        self._operation_list = []
        self._hastates, self._hastates_inv = (
            self._dhw.hastates,
            {value: key for key, value in self._dhw.hastates.items()},
        )
        self._update_init = True

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_DHW_UPDATE_BOSCH, self.update
        )

    @property
    def name(self):
        """Return the device name."""
        return self._name

    @property
    def upstream_object(self):
        """Return upstream component. Used for refreshing."""
        return self._dhw

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return self._unique_id

    @property
    def device_info(self):
        """Get attributes about the device."""
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
            "manufacturer": self._gateway.get_info(SYSTEM_BRAND),
            "model": self._gateway.get_info(SYSTEM_TYPE),
            "name": "Water heater " + self._name,
            "sw_version": self._gateway.firmware,
            "via_hub": (DOMAIN, self._uuid),
        }

    @property
    def available(self):
        """Return if the the device is online or not."""
        return True

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._temperature_units

    @property
    def device_state_attributes(self):
        """Return the optional device state attributes."""
        data = {"target_temp_step": 1}
        # data["CALENDAR"] = self._dhw.get_schedule
        # vacations = self.water_heater.get_vacations()
        # if vacations:
        #     data[ATTR_VACATION_START] = vacations[0].start_date
        #     data[ATTR_VACATION_END] = vacations[0].end_date
        # data[ATTR_ON_VACATION] = self.water_heater.is_on_vacation
        # todays_usage = self.water_heater.total_usage_for_today
        # if todays_usage:
        #     data[ATTR_TODAYS_ENERGY_USAGE] = todays_usage
        # data[ATTR_IN_USE] = self.water_heater.in_use

        return data

    @property
    def current_operation(self):
        """
        Return current operation as one of the following.
        ["eco", "heat_pump", "high_demand", "electric_only"]
        """
        return self._mode

    @property
    def operation_list(self):
        """List of available operation modes."""
        return self._operation_list

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS_HEATER

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        target_temp = kwargs.get(ATTR_TEMPERATURE)
        if target_temp and target_temp != self._target_temperature:
            await self._dhw.set_temperature(target_temp)
        else:
            _LOGGER.error("A target temperature must be provided")

    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        op_mode = self._hastates.get(operation_mode)
        _LOGGER.debug(f"Setting operation mode {operation_mode} which is Bosch {op_mode}.")
        if op_mode and operation_mode != self._mode and operation_mode in self._operation_list:
            new_mode = await self._dhw.set_operation_mode(op_mode)
            _LOGGER.debug(f"Set operation mode to {new_mode}.")
        else:
            _LOGGER.error(f"Correct operation mode must be provided. I got {operation_mode}")

    def update(self):
        """Get the latest date."""
        _LOGGER.debug("Updating Bosch water_heater.")
        if (
            not self._dhw
            or not self._dhw.json_scheme_ready
            or not self._dhw.update_initialized
        ):
            return
        self._state = self._dhw.get_value(STATUS)
        curr_temp = self._dhw.get_property(CURRENT_TEMP)
        self._current_temperature = curr_temp.get(self._dhw.strings.val)
        self._temperature_units = UNITS_CONVERTER.get(
            curr_temp.get(self._dhw.strings.units, "C")
        )
        (
            self._target_temperature,
            self._low_temp,
            self._max_temp,
        ) = self._dhw.target_temperature
        # self._holiday_mode = self._dhw.get_value(HC_HOLIDAY_MODE)
        mode = self._dhw.get_property(OPERATION_MODE)
        self._operation_list = self.operation_list_converter(
            mode.get(self._dhw.strings.allowed_values)
        )
        self._mode = self._hastates_inv.get(
            mode.get(self._dhw.strings.val), STATE_OFF)
        self._target_temp_off = self._dhw.get_value(WATER_OFF)
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()

    def operation_list_converter(self, op_list):
        return [self._hastates_inv.get(value) for value in op_list]

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._low_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self._max_temp
