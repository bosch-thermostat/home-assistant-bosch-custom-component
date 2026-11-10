"""Support for Bosch Thermostat Climate."""
from __future__ import annotations
import asyncio
from collections.abc import Awaitable, Callable
import logging
import time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import BoschDataUpdateCoordinator

from bosch_thermostat_client.const import ACTIVE_PROGRAM, HVAC_HEAT, HVAC_OFF, SETPOINT
from bosch_thermostat_client.exceptions import DeviceException
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACAction,
    ClimateEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import callback

from .bosch_entity import BoschClimateWaterEntity
from .const import (
    BOSCH_STATE,
    DOMAIN,
    BOSCH_GATEWAY_ENTRY,
    SWITCHPOINT,
    UNITS_CONVERTER,
    UUID,
)

_LOGGER = logging.getLogger(__name__)

# After a change the gateway is read back until it reports the new value.
# Reading right after the PUT returns the old value for a moment (seen with
# EasyControl: the program switched back in HA for one scan interval).
CONFIRM_TIMEOUT = 15.0
CONFIRM_INTERVAL = 1.0


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch thermostat from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    entry = data[BOSCH_GATEWAY_ENTRY]
    coordinator = entry.coordinator
    optimistic_mode = config_entry.options.get("optimistic_mode", False)
    
    entities = [
        BoschThermostat(
            coordinator=coordinator,
            uuid=uuid,
            bosch_object=hc,
            gateway=entry.gateway,
            optimistic_mode=optimistic_mode,
        )
        for hc in entry.gateway.heating_circuits
    ]
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
        self._confirm_task: asyncio.Task | None = None
        self._confirm_generation = 0
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
            self._async_start_confirm(
                "hvac mode",
                hvac_mode,
                lambda: self._bosch_object.ha_mode,
                self._bosch_object.update,
            )
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
        if await self._bosch_object.set_temperature(temperature):
            self._async_start_confirm(
                "target temperature",
                temperature,
                lambda: self._bosch_object.target_temperature,
                self._bosch_object.update,
            )
        else:
            await self._async_refresh_after_set()

    def _async_start_confirm(
        self,
        what: str,
        expected: Any,
        reader: Callable[[], Any],
        refresher: Callable[[], Awaitable[Any]],
    ) -> None:
        """Read the gateway back in the background until it reports ``expected``.

        The service call returns at once; the entity is updated as soon as the
        gateway confirms the change (or after CONFIRM_TIMEOUT with what it
        reports then).
        """
        # A newer change supersedes a running read-back. It is not cancelled:
        # cancelling it inside a coordinator refresh would mark the refresh as
        # failed (entities unavailable), and the library swallows cancellation
        # inside its requests anyway. The old read-back stops at its next step.
        self._confirm_generation += 1
        self._confirm_task = self.hass.async_create_background_task(
            self._async_confirm(what, expected, reader, refresher, self._confirm_generation),
            name=f"bosch confirm {what} {self.entity_id}",
        )

    async def _async_confirm(
        self,
        what: str,
        expected: Any,
        reader: Callable[[], Any],
        refresher: Callable[[], Awaitable[Any]],
        generation: int | None = None,
    ) -> bool | None:
        """Poll the changed value until the gateway reports it.

        Returns True/False (confirmed or not), None if a newer change took over.
        """
        if generation is None:
            generation = self._confirm_generation
        start = time.monotonic()
        confirmed = False
        while True:
            await asyncio.sleep(CONFIRM_INTERVAL)
            if generation != self._confirm_generation:
                return None
            try:
                await refresher()
            except DeviceException as err:
                _LOGGER.debug("Reading back %s of %s failed: %s", what, self.entity_id, err)
            except Exception as err:  # noqa: BLE001 - library errors must not end the read-back
                _LOGGER.debug("Reading back %s of %s raised %r", what, self.entity_id, err)
            if generation != self._confirm_generation:
                return None
            elapsed = time.monotonic() - start
            if reader() == expected:
                confirmed = True
                _LOGGER.info(
                    "%s: %s %r confirmed by the gateway after %.1f s",
                    self.entity_id, what, expected, elapsed,
                )
                break
            if elapsed >= CONFIRM_TIMEOUT:
                _LOGGER.warning(
                    "%s: %s %r not confirmed by the gateway within %.0f s (it reports %r)",
                    self.entity_id, what, expected, CONFIRM_TIMEOUT, reader(),
                )
                break
        self._optimistic_hvac_mode = None
        self._optimistic_target_temperature = None
        self.async_write_ha_state()
        # Values depending on the change (e.g. setpoint of a new program). Own
        # task: must not run inside this one, which may still be cancelled on
        # removal - a cancelled refresh counts as failed.
        self.hass.async_create_background_task(
            self.coordinator.async_request_refresh(),
            name=f"bosch refresh after {what} {self.entity_id}",
        )
        return confirmed

    async def async_will_remove_from_hass(self) -> None:
        """Stop a running read-back."""
        if self._confirm_task and not self._confirm_task.done():
            self._confirm_task.cancel()
        await super().async_will_remove_from_hass()

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
        obj = self._bosch_object

        async def refresh_program() -> None:
            # only the active program, not the whole circuit
            if obj.get_property(ACTIVE_PROGRAM):
                await obj.update_requested_key(ACTIVE_PROGRAM)
            else:
                await obj.update()

        self._async_start_confirm(
            "preset", preset_mode, lambda: obj.preset_mode, refresh_program
        )
