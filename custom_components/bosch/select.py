"""
Support for water heaters connected to Bosch thermostat.

For more details about this platform, please refer to the documentation at...
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import BoschDataUpdateCoordinator

from .bosch_entity import BoschEntity
from .const import (
    DOMAIN,
    BOSCH_GATEWAY_ENTRY,
    SELECT,
    UUID,
)
from homeassistant.components.select import SelectEntity


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Select from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    entry = data[BOSCH_GATEWAY_ENTRY]
    coordinator = entry.coordinator
    enabled = config_entry.data.get(SELECT, [])
    
    entities = [
        BoschSelect(
            coordinator=coordinator,
            uuid=uuid,
            bosch_object=select,
            gateway=entry.gateway,
            name=select.name,
            attr_uri=select.attr_id,
            domain_name="Select",
            is_enabled=select.attr_id in enabled,
        )
        for select in (entry.gateway.select_switches or [])
    ]
    async_add_entities(entities)
    return True


class BoschSelect(BoschEntity, SelectEntity):
    """Representation of a Bosch switch."""

    def __init__(
        self,
        coordinator: BoschDataUpdateCoordinator,
        uuid: str,
        bosch_object: Any,
        gateway: Any,
        name: str,
        attr_uri: str,
        domain_name: str,
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
        self._attr_unique_id = f"{self._domain_name}{self._attr_name}{self._uuid}"
        self._attrs = {}
        self._attr_entity_registry_enabled_default = is_enabled

    @property
    def device_name(self):
        """Return device name."""
        return "Bosch selects"

    @property
    def current_option(self) -> str:
        """Return current selected option."""
        return self._bosch_object.state

    @property
    def options(self) -> list[str]:
        """Options list."""
        return self._bosch_object.options or []

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self._bosch_object.set_value(value=option)
        await self.coordinator.async_request_refresh()

