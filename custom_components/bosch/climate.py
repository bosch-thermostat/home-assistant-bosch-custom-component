"""Support for Bosch Thermostat Climate."""
from __future__ import annotations
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import BoschDataUpdateCoordinator

from bosch_thermostat_client.const import HVAC_HEAT, HVAC_OFF, SETPOINT
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACAction,
    HVACMode,
    ClimateEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .bosch_entity import BoschClimateWaterEntity
from .const import (
    BOSCH_STATE,
    DOMAIN,
    BOSCH_GATEWAY_ENTRY,
    SWITCHPOINT,
    UNITS_CONVERTER,
    UUID,
)
from .pool import (
    DEFAULT_TEMP_STEP,
    HVAC_HEAT as POOL_HEAT,
    HVAC_OFF as POOL_OFF,
    PoolPoller,
    async_pool_available,
    hvac_to_status,
    status_to_hvac,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch thermostat from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    entry = data[BOSCH_GATEWAY_ENTRY]
    coordinator = entry.coordinator
    optimistic_mode = config_entry.options.get("optimistic_mode", False)

    entities: list[ClimateEntity] = [
        BoschThermostat(
            coordinator=coordinator,
            uuid=uuid,
            bosch_object=hc,
            gateway=entry.gateway,
            optimistic_mode=optimistic_mode,
        )
        for hc in entry.gateway.heating_circuits
    ]
    if await async_pool_available(entry.gateway):
        entities.append(
            BoschPoolClimate(
                coordinator=coordinator,
                uuid=uuid,
                gateway=entry.gateway,
                optimistic_mode=optimistic_mode,
            )
        )
    async_add_entities(entities)
    return True


class BoschThermostat(BoschClimateWaterEntity, ClimateEntity):
    """Representation of a Bosch thermostat."""

    def __init__(
        self, 
        coordinator: BoschDataUpdateCoordinator, 
        uuid: str, 
        bosch_object: Any, 
        gateway: Any, 
        optimistic_mode: bool = False
    ) -> None:
        """Initialize the thermostat."""
        self._name_prefix = (
            "Zone circuit " if "/zones" in bosch_object.attr_id else "Heating circuit "
        )
        self._mode = {}
        self._optimistic_mode = optimistic_mode
        # Values shown until the next coordinator refresh confirms them
        self._optimistic_hvac_mode: str | None = None
        self._optimistic_target_temperature: float | None = None
        self._is_enabled = True

        super().__init__(
            coordinator=coordinator, uuid=uuid, bosch_object=bosch_object, gateway=gateway
        )

    @property
    def state_attributes(self) -> dict[str, Any]:
        """Attributes of entity."""
        data = super().state_attributes
        try:
            data[SETPOINT] = self._bosch_object.setpoint
            if self._bosch_object.schedule:
                data[SWITCHPOINT] = self._bosch_object.schedule.active_program
            data[BOSCH_STATE] = self._bosch_object.state
            if self._bosch_object.extra_state_attributes:
                data = {**data, **self._bosch_object.extra_state_attributes}
        except NotImplementedError:
            pass
        return data

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return ClimateEntityFeature.TARGET_TEMPERATURE | (
            ClimateEntityFeature.PRESET_MODE
            if self._bosch_object.support_presets
            else 0
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Drop optimistic values once real data arrives."""
        self._optimistic_hvac_mode = None
        self._optimistic_target_temperature = None
        super()._handle_coordinator_update()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set operation mode."""
        _LOGGER.debug(f"Setting operation mode {hvac_mode}.")

        if self._optimistic_mode:
            self._optimistic_hvac_mode = hvac_mode
            self.async_write_ha_state()
        status = await self._bosch_object.set_ha_mode(hvac_mode)
        if status > 0:
            await self._async_refresh_after_set()
            return True
        if self._optimistic_mode:
            # Setting failed, revert to the mode reported by the gateway.
            self._optimistic_hvac_mode = None
            self.async_write_ha_state()
        return False

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        _LOGGER.debug(f"Setting target temperature {temperature}.")
        if self._optimistic_mode:
            self._optimistic_target_temperature = temperature
            self.async_write_ha_state()
        await self._bosch_object.set_temperature(temperature)
        await self._async_refresh_after_set()

    async def _async_refresh_after_set(self) -> None:
        """Read the new state back, unless optimistic mode shows it already.

        Some gateways (e.g. EasyControl) report the old value for a while
        after a change; an immediate refresh would overwrite the optimistic
        value with it, so optimistic mode waits for the next scheduled poll.
        """
        if not self._optimistic_mode:
            await self.coordinator.async_request_refresh()

    @property
    def hvac_mode(self):
        """Return current operation ie. heat, cool, idle."""
        if self._optimistic_hvac_mode is not None:
            return self._optimistic_hvac_mode
        return self._bosch_object.ha_mode

    @property
    def hvac_action(self):
        """Hvac action."""
        hvac_action = self._bosch_object.hvac_action
        if hvac_action == HVAC_HEAT:
            return HVACAction.HEATING
        if hvac_action == HVAC_OFF:
            return HVACAction.IDLE

    @property
    def hvac_modes(self) -> list:
        """List of available operation modes."""
        return self._bosch_object.ha_modes

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._bosch_object.current_temp

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if self._optimistic_target_temperature is not None:
            return self._optimistic_target_temperature
        return self._bosch_object.target_temperature

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return UNITS_CONVERTER.get(
            self._bosch_object.temp_units, UnitOfTemperature.CELSIUS
        )

    @property
    def preset_modes(self):
        """Return available preset modes."""
        return self._bosch_object.preset_modes

    @property
    def preset_mode(self):
        """Return current preset mode."""
        return self._bosch_object.preset_mode

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        await self._bosch_object.set_preset_mode(preset_mode)
        await self.coordinator.async_request_refresh()


class BoschPoolClimate(CoordinatorEntity, ClimateEntity):
    """KM200 pool as heat/off climate."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = DEFAULT_TEMP_STEP
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: BoschDataUpdateCoordinator,
        uuid: str,
        gateway: Any,
        optimistic_mode: bool = False,
    ) -> None:
        """Initialize pool climate from gateway paths."""
        super().__init__(coordinator)
        self._uuid = uuid
        self._gateway = gateway
        self._poller = PoolPoller(gateway)
        self._optimistic_mode = optimistic_mode
        self._optimistic_hvac_mode: str | None = None
        self._optimistic_target_temperature: float | None = None
        self._attr_unique_id = f"{uuid}pool"

    @property
    def device_info(self) -> DeviceInfo:
        """Child Pool device under the gateway."""
        info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._uuid}_pool")},
            name="Pool",
            manufacturer=self._gateway.device_model,
            model=self._gateway.device_type,
            sw_version=self._gateway.firmware,
            hw_version=self._uuid,
        )
        if self.coordinator.gateway_device_id:
            info["via_device_id"] = self.coordinator.gateway_device_id
        return info

    async def async_added_to_hass(self) -> None:
        """Register poller and seed values."""
        await super().async_added_to_hass()
        self.coordinator.register_object(self._poller)
        await self._poller.update()

    async def async_will_remove_from_hass(self) -> None:
        """Unregister poller."""
        self.coordinator.unregister_object(self._poller)
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Drop optimistic values once real data arrives."""
        self._optimistic_hvac_mode = None
        self._optimistic_target_temperature = None
        super()._handle_coordinator_update()

    async def _async_refresh_after_set(self) -> None:
        """Refresh unless optimistic mode waits for the next poll."""
        if not self._optimistic_mode:
            await self.coordinator.async_request_refresh()

    @property
    def min_temp(self) -> float:
        """Minimum pool setpoint."""
        return self._poller.min_temp

    @property
    def max_temp(self) -> float:
        """Maximum pool setpoint."""
        return self._poller.max_temp

    @property
    def current_temperature(self) -> float | None:
        """Current pool water temperature."""
        return self._poller.current_temp

    @property
    def target_temperature(self) -> float | None:
        """Pool setpoint temperature."""
        if self._optimistic_target_temperature is not None:
            return self._optimistic_target_temperature
        return self._poller.target_temp

    @property
    def hvac_mode(self) -> HVACMode:
        """Heat when pool status is not off."""
        if self._optimistic_hvac_mode is not None:
            mode = self._optimistic_hvac_mode
        else:
            mode = status_to_hvac(self._poller.status)
        return HVACMode.HEAT if mode == POOL_HEAT else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """Heating while on; off while off."""
        if self.hvac_mode == HVACMode.HEAT:
            return HVACAction.HEATING
        return HVACAction.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Write poolStatus on/off."""
        mode = POOL_HEAT if hvac_mode == HVACMode.HEAT else POOL_OFF
        status = hvac_to_status(mode)
        _LOGGER.debug("Setting pool status to %s", status)
        if self._optimistic_mode:
            self._optimistic_hvac_mode = mode
            self.async_write_ha_state()
        try:
            await self._poller.async_set_status(status)
        except Exception:
            _LOGGER.exception("Failed to set pool status to %s", status)
            if self._optimistic_mode:
                self._optimistic_hvac_mode = None
                self.async_write_ha_state()
            return
        await self._async_refresh_after_set()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write pool setpoint."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        _LOGGER.debug("Setting pool target temperature %s", temperature)
        if self._optimistic_mode:
            self._optimistic_target_temperature = temperature
            self.async_write_ha_state()
        try:
            await self._poller.async_set_temperature(float(temperature))
        except Exception:
            _LOGGER.exception("Failed to set pool temperature to %s", temperature)
            if self._optimistic_mode:
                self._optimistic_target_temperature = None
                self.async_write_ha_state()
            return
        await self._async_refresh_after_set()

    async def async_turn_on(self) -> None:
        """Turn pool heating on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn pool heating off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
