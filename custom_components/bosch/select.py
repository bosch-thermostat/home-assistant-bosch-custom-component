"""
Support for water heaters connected to Bosch thermostat.

For more details about this platform, please refer to the documentation at...
"""
from __future__ import annotations
from bosch_thermostat_client.const import GATEWAY, SELECT
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .bosch_entity import BoschEntity
from .const import (
    DOMAIN,
    SIGNAL_BOSCH,
    SIGNAL_SELECT,
    UUID,
)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Select from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    enabled = config_entry.data.get(SELECT, [])
    data[SELECT] = []
    selects = data[GATEWAY].switches.selects
    for select in selects:
        data[SELECT].append(
            BoschSelect(
                hass=hass,
                uuid=uuid,
                bosch_object=select,
                gateway=data[GATEWAY],
                name=select.name,
                attr_uri=select.attr_id,
                domain_name="Select",
                is_enabled=select.attr_id in enabled,
            )
        )
    async_add_entities(data[SELECT])
    async_dispatcher_send(hass, SIGNAL_BOSCH)
    return True


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Bosch Thermostat Platform."""
    pass


class BoschSelect(BoschEntity, SelectEntity):
    """Representation of a Bosch switch."""

    signal = SIGNAL_SELECT

    def __init__(
        self,
        hass,
        uuid,
        bosch_object,
        gateway,
        name,
        attr_uri,
        domain_name,
        is_enabled=False,
    ):
        """Set up device and add update callback to get data from websocket."""
        super().__init__(
            hass=hass, uuid=uuid, bosch_object=bosch_object, gateway=gateway
        )
        self._domain_name = domain_name
        self._name = name
        self._attr_uri = attr_uri
        self._state = bosch_object.state
        self._update_init = True
        self._attr_unique_id = f"{self._domain_name}{self._name}{self._uuid}"
        self._attrs = {}
        self._attr_entity_registry_enabled_default = is_enabled

    @property
    def device_name(self):
        """Return device name."""
        return "Bosch selects"

    @property
    def current_option(self) -> str:
        """Return current selected option."""
        return self._state

    @property
    def options(self) -> list[str]:
        """Options list."""
        return self._bosch_object.options or []

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self._bosch_object.set_value(value=option)

    async def async_update(self) -> None:
        """Update entity state."""
        if self._state != self._bosch_object.state:
            self._state = self._bosch_object.state
            self.schedule_update_ha_state()

    @property
    def should_poll(self):
        """Don't poll."""
        return False
