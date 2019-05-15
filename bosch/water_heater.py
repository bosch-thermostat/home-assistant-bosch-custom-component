"""
Support for water heaters connected to Bosch thermostat.

For more details about this platform, please refer to the documentation at...
"""
import logging
from homeassistant.components.water_heater import (
    STATE_ECO, STATE_ELECTRIC, STATE_GAS,
    STATE_HEAT_PUMP, STATE_HIGH_DEMAND, STATE_OFF, STATE_PERFORMANCE,
    SUPPORT_OPERATION_MODE, SUPPORT_TARGET_TEMPERATURE, WaterHeaterDevice)

from .const import DOMAIN, SIGNAL_DHW_UPDATE_BOSCH

from homeassistant.const import (
    TEMP_CELSIUS, ATTR_TEMPERATURE, TEMP_FAHRENHEIT)

from bosch_thermostat_http.const import (OPERATION_MODE,
                                         DHW_CURRENT_WATERTEMP,
                                         DHW_CURRENT_SETPOINT,
                                         SYSTEM_BRAND, FIRMWARE_VERSION,
                                         SYSTEM_TYPE, VALUE, ALLOWED_VALUES,
                                         UNITS, DHW_HIGHTTEMP_LEVEL,
                                         DHW_OFFTEMP_LEVEL, MAXVALUE, MINVALUE)


_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS_HEATER = (SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE)

DEFAULT_MIN_TEMP = 0
DEFAULT_MAX_TEMP = 100

HA_STATE_TO_BOSCH = {
    STATE_HEAT_PUMP: 'hcprogram',
    STATE_HIGH_DEMAND: 'ownprogram',
    STATE_OFF:  'off',
    STATE_PERFORMANCE: 'high'
}


BOSCH_STATE_TO_HA = {value: key for key, value in HA_STATE_TO_BOSCH.items()}


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Water heater from a config entry."""
    uuid = config_entry.title
    data = hass.data[DOMAIN][uuid]
    data['dhws'] = [BoschWaterHeater(hass, uuid, dhw, data['gateway'])
                    for dhw in data['gateway'].dhw_circuits]
    async_add_entities(data['dhws'])
    return True


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
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
        self._unique_id = self._name+self._uuid
        self._gateway = gateway
        self._mode = None
        self._state = None
        self._target_temperature = None
        self._current_temperature = None
        self._temperature_units = TEMP_CELSIUS
        self._max_temp = DEFAULT_MAX_TEMP
        self._low_temp = DEFAULT_MIN_TEMP
        self._operation_list = []
        # self.hass.helpers.dispatcher.dispatcher_connect(
        #     SIGNAL_UPDATE_BOSCH, self.update)

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_DHW_UPDATE_BOSCH, self.update)

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
            'identifiers': {
                (DOMAIN, self._unique_id)
            },
            'manufacturer': self._gateway.get_info(SYSTEM_BRAND),
            'model': self._gateway.get_info(SYSTEM_TYPE),
            'name': 'Water heater ' + self._name,
            'sw_version': self._gateway.get_info(FIRMWARE_VERSION),
            'via_hub': (DOMAIN, self._uuid)
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
        data = {}
        data["CALENDAR"] = self._dhw.get_schedule
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
        if self._mode:
            return self._mode[VALUE]
        return None

    @property
    def operation_list(self):
        """List of available operation modes."""
        if self._mode:
            return self._mode.get(ALLOWED_VALUES)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS_HEATER

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        return
        target_temp = kwargs.get(ATTR_TEMPERATURE)
        if target_temp is not None:
            self.water_heater.set_target_set_point(target_temp)
        else:
            _LOGGER.error("A target temperature must be provided")

    def set_operation_mode(self, operation_mode):
        """Set operation mode."""
        return
        op_mode_to_set = HA_STATE_TO_ECONET.get(operation_mode)
        if op_mode_to_set is not None:
            self.water_heater.set_mode(op_mode_to_set)
        else:
            _LOGGER.error("An operation mode must be provided")

    def update(self):
        """Get the latest date."""
        if (not self._dhw or not self._dhw.json_scheme_ready or
                not self._dhw.update_initialized):
            return
        # self._state = self._dhw.get_value(HC_HEATING_STATUS)
        current_temperature = self._dhw.get_property(DHW_CURRENT_WATERTEMP)
        if current_temperature:
            self._current_temperature = current_temperature[VALUE]
            if (UNITS in current_temperature and
                    current_temperature[UNITS] == 'F'):
                self._temperature_units = TEMP_FAHRENHEIT
        (self._target_temperature, self._low_temp, self._max_temp) =\
            self._dhw.target_temperature
        # self._holiday_mode = self._dhw.get_value(HC_HOLIDAY_MODE)
        self._mode = self._dhw.get_property(OPERATION_MODE)

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
