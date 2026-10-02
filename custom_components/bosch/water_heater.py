"""
Support for water heaters connected to Bosch thermostat.

For more details about this platform, please refer to the documentation at...
"""
from __future__ import annotations
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import BoschDataUpdateCoordinator

from bosch_thermostat_client.const import SETPOINT
from homeassistant.components.water_heater import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    STATE_OFF,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.helpers import entity_platform

from .bosch_entity import BoschClimateWaterEntity
from .const import (
    BOSCH_STATE,
    CHARGE,
    DOMAIN,
    BOSCH_GATEWAY_ENTRY,
    SERVICE_CHARGE_SCHEMA,
    SERVICE_CHARGE_START,
    SWITCHPOINT,
    UNITS_CONVERTER,
    UUID,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities) -> bool:
    """Set up the Bosch Water heater from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    entry = data[BOSCH_GATEWAY_ENTRY]
    coordinator = entry.coordinator
    
    entities = [
        BoschWaterHeater(coordinator, uuid, dhw, entry.gateway)
        for dhw in entry.gateway.dhw_circuits
    ]
    async_add_entities(entities)
    platform = entity_platform.current_platform.get()
    platform.async_register_entity_service(
        SERVICE_CHARGE_START, SERVICE_CHARGE_SCHEMA, "service_charge"
    )
    return True


class BoschWaterHeater(BoschClimateWaterEntity, WaterHeaterEntity):
    """Representation of an EcoNet water heater."""

    def __init__(
        self, 
        coordinator: BoschDataUpdateCoordinator, 
        uuid: str, 
        bosch_object: Any, 
        gateway: Any
    ) -> None:
        """Initialize the water heater."""
        self._name_prefix = "Water heater"

        super().__init__(
            coordinator=coordinator, uuid=uuid, bosch_object=bosch_object, gateway=gateway
        )

    async def service_charge(self, value) -> None:
        """Set charge of DHW device.

        Upstream lib doesn't check if value is proper!
        """
        _LOGGER.info("Setting %s %s with value %s", self._attr_name, CHARGE, value)
        await self._bosch_object.set_service_call(CHARGE, value)
        await self.coordinator.async_request_refresh()

    @property
    def state_attributes(self):
        data = super().state_attributes
        data.pop(ATTR_TARGET_TEMP_HIGH, None)
        data.pop(ATTR_TARGET_TEMP_LOW, None)
        data[SETPOINT] = self._bosch_object.setpoint
        if self._bosch_object.schedule:
            data[SWITCHPOINT] = self._bosch_object.schedule.active_program
        data[BOSCH_STATE] = self._bosch_object.state
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
        return self._bosch_object.ha_mode

    @property
    def operation_list(self):
        """List of available operation modes."""
        return self._bosch_object.ha_modes

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._bosch_object.current_temp

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._bosch_object.target_temperature

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return UNITS_CONVERTER.get(
            self._bosch_object.temp_units, UnitOfTemperature.CELSIUS
        )

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
        if target_temp is None:
            _LOGGER.error("A target temperature must be provided")
            return
        await self._bosch_object.set_temperature(target_temp)
        await self.coordinator.async_request_refresh()

    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        _LOGGER.debug(f"Setting operation mode of {self._attr_name} to {operation_mode}.")
        status = await self._bosch_object.set_ha_mode(operation_mode)
        if status > 0:
            await self.coordinator.async_request_refresh()
            return True
        return False

