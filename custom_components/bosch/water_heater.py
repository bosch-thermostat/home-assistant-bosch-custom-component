"""
Support for water heaters connected to Bosch thermostat.

For more details about this platform, please refer to the documentation at...
"""
from __future__ import annotations
import logging

from bosch_thermostat_client.const import GATEWAY, SETPOINT
from homeassistant.components.water_heater import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    STATE_OFF,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.helpers import entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .bosch_entity import BoschClimateWaterEntity
from .const import (
    BOSCH_STATE,
    CHARGE,
    DOMAIN,
    SERVICE_CHARGE_SCHEMA,
    SERVICE_CHARGE_START,
    SIGNAL_BOSCH,
    SIGNAL_DHW_UPDATE_BOSCH,
    SWITCHPOINT,
    UNITS_CONVERTER,
    UUID,
    WATER_HEATER,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities) -> bool:
    """Set up the Bosch Water heater from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    data[WATER_HEATER] = [
        BoschWaterHeater(hass, uuid, dhw, data[GATEWAY])
        for dhw in data[GATEWAY].dhw_circuits
    ]
    async_add_entities(data[WATER_HEATER])
    async_dispatcher_send(hass, SIGNAL_BOSCH)
    platform = entity_platform.current_platform.get()
    platform.async_register_entity_service(
        SERVICE_CHARGE_START, SERVICE_CHARGE_SCHEMA, "service_charge"
    )
    return True


class BoschWaterHeater(BoschClimateWaterEntity, WaterHeaterEntity):
    """Representation of an EcoNet water heater."""

    signal = SIGNAL_DHW_UPDATE_BOSCH

    def __init__(self, hass, uuid, bosch_object, gateway) -> None:
        """Initialize the water heater."""
        self._name_prefix = "Water heater"
        self._mode = None
        self._current_setpoint = None
        self._target_temp_off = 0
        self._operation_list = []

        super().__init__(
            hass=hass, uuid=uuid, bosch_object=bosch_object, gateway=gateway
        )

    async def service_charge(self, value) -> None:
        """Set charge of DHW device.

        Upstream lib doesn't check if value is proper!
        """
        _LOGGER.info("Setting %s %s with value %s", self._name, CHARGE, value)
        await self._bosch_object.set_service_call(CHARGE, value)

    @property
    def state_attributes(self):
        data = super().state_attributes
        data.pop(ATTR_TARGET_TEMP_HIGH, None)
        data.pop(ATTR_TARGET_TEMP_LOW, None)
        data[SETPOINT] = self._bosch_object.setpoint
        if self._bosch_object.schedule:
            data[SWITCHPOINT] = self._bosch_object.schedule.active_program
        data[BOSCH_STATE] = self._state
        return data

    @property
    def extra_state_attributes(self):
        """Return the optional device state attributes."""
        data = {"target_temp_step": 1}
        return data

    @property
    def current_operation(self):
        """Return current operation as one of the following.

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
        if (
            self._bosch_object.ha_mode == STATE_OFF
            or self._bosch_object.setpoint == STATE_OFF
            or not self._bosch_object.support_target_temp
        ):
            return WaterHeaterEntityFeature.OPERATION_MODE
        return (
            WaterHeaterEntityFeature.TARGET_TEMPERATURE
            | WaterHeaterEntityFeature.OPERATION_MODE
        )

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        target_temp = kwargs.get(ATTR_TEMPERATURE)
        if target_temp and target_temp != self._target_temperature:
            await self._bosch_object.set_temperature(target_temp)
        else:
            _LOGGER.error("A target temperature must be provided")

    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        _LOGGER.debug(f"Setting operation mode of {self._name} to {operation_mode}.")
        status = await self.bosch_object.set_ha_mode(operation_mode)
        if status > 0:
            return True
        return False

    async def async_update(self):
        """Get the latest date."""
        _LOGGER.debug("Updating Bosch water_heater.")
        if not self._bosch_object or not self._bosch_object.update_initialized:
            return
        self._temperature_unit = UNITS_CONVERTER.get(
            self._bosch_object.temp_units if self._bosch_object.temp_units else "C"
        )
        if (
            self._state != self._bosch_object.state
            or self._operation_list == self._bosch_object.ha_modes
            or self._current_temperature != self._bosch_object.current_temp
        ):
            self._state = self._bosch_object.state
            self._target_temperature = self._bosch_object.target_temperature
            self._current_temperature = self._bosch_object.current_temp
            self._operation_list = self._bosch_object.ha_modes
            self._mode = self._bosch_object.ha_mode
            self.async_schedule_update_ha_state()
