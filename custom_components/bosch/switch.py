"""
Support for water heaters connected to Bosch thermostat.

For more details about this platform, please refer to the documentation at...
"""
from __future__ import annotations
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import BoschDataUpdateCoordinator

from .bosch_entity import BoschEntity
from .const import (
    CIRCUITS,
    CIRCUITS_SENSOR_NAMES,
    DOMAIN,
    BOSCH_GATEWAY_ENTRY,
    SWITCH,
    UUID,
)
from homeassistant.components.switch import SwitchEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Switch from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    entry = data[BOSCH_GATEWAY_ENTRY]
    coordinator = entry.coordinator
    enabled_switches = config_entry.data.get(SWITCH, [])
    
    entities = []
    for switch in entry.gateway.regular_switches:
        entities.append(
            BoschSwitch(
                coordinator=coordinator,
                uuid=uuid,
                bosch_object=switch,
                gateway=entry.gateway,
                name=switch.name,
                attr_uri=switch.attr_id,
                domain_name="Switches",
                is_enabled=switch.attr_id in enabled_switches,
            )
        )
    for circ_type in CIRCUITS:
        circuits = entry.gateway.get_circuits(circ_type)
        for circuit in circuits:
            for switch in circuit.regular_switches:
                entities.append(
                    CircuitSwitch(
                        coordinator=coordinator,
                        uuid=uuid,
                        bosch_object=switch,
                        gateway=entry.gateway,
                        name=switch.name,
                        attr_uri=switch.attr_id,
                        domain_name=circuit.name,
                        circuit_type=circ_type,
                        is_enabled=switch.attr_id in enabled_switches,
                    )
                )
    async_add_entities(entities)
    return True


class BoschBaseSwitch(BoschEntity, SwitchEntity):
    """Representation of a Bosch charge."""

    def __init__(
        self,
        coordinator: BoschDataUpdateCoordinator,
        uuid: str,
        bosch_object: Any,
        gateway: Any,
        name: str,
        attr_uri: str,
        domain_name: str,
        circuit_type: str | None = None,
        is_enabled: bool = False,
    ) -> None:
        """Set up device and add update callback to get data from websocket."""
        super().__init__(
            coordinator=coordinator,
            uuid=uuid,
            bosch_object=bosch_object,
            gateway=gateway,
            domain_name=domain_name,
        )
        self._attr_name = name
        self._attr_uri = attr_uri
        self._attr_unique_id = self._domain_name + self._attr_name + self._uuid
        self._attrs = {}
        self._circuit_type = circuit_type
        self._attr_entity_registry_enabled_default = is_enabled

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._bosch_object.state

    async def async_turn_on(self, **kwargs):
        """Turn on switch."""
        _LOGGER.debug("Turning on %s switch.", self._attr_name)
        await self._bosch_object.turn_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn off switch."""
        _LOGGER.debug("Turning off %s switch.", self._attr_name)
        await self._bosch_object.turn_off()
        await self.coordinator.async_request_refresh()



class BoschSwitch(BoschBaseSwitch):
    """Representation of a Bosch switch."""

    @property
    def device_name(self):
        return "Bosch switches"


class CircuitSwitch(BoschBaseSwitch):
    """Representation of a Bosch circuit switch."""

    @property
    def device_name(self):
        return CIRCUITS_SENSOR_NAMES[self._circuit_type] + " " + self._domain_name
