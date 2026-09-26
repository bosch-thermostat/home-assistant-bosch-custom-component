"""Platform to control a Bosch IP thermostats units."""
from __future__ import annotations

import logging

from bosch_thermostat_client.version import __version__ as LIBVERSION
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_PASSWORD,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    ACCESS_KEY,
    ACCESS_TOKEN,
    BOSCH_GATEWAY_ENTRY,
    CONF_DEVICE_TYPE,
    CONF_PROTOCOL,
    DOMAIN,
    UUID,
)
from .gateway import BoschGatewayEntry
from .services import (
    async_register_services,
    async_remove_services,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Initialize the Bosch platform."""
    hass.data[DOMAIN] = {}
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Create entry for Bosch thermostat device."""
    _LOGGER.debug("Setting up Bosch component version %s.", LIBVERSION)
    uuid = entry.data[UUID]
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    gateway_entry = BoschGatewayEntry(
        hass=hass,
        uuid=uuid,
        host=entry.data[CONF_ADDRESS],
        protocol=entry.data[CONF_PROTOCOL],
        device_type=entry.data[CONF_DEVICE_TYPE],
        access_key=entry.data[ACCESS_KEY],
        access_token=entry.data[ACCESS_TOKEN],
        password=entry.data.get(CONF_PASSWORD),
        entry=entry,
    )
    hass.data[DOMAIN][uuid] = {BOSCH_GATEWAY_ENTRY: gateway_entry}
    try:
        _init_status: bool = await gateway_entry.async_init()
    except Exception:
        # HA does not unload an entry whose setup raised (e.g. ConfigEntryNotReady
        # retries), so close the connection here to avoid leaking XMPP clients.
        # Deliberately not BaseException: a CancelledError during shutdown must
        # propagate rather than wait on the close.
        await gateway_entry.async_close()
        raise
    if not _init_status:
        await gateway_entry.async_close()
        return _init_status
    async_register_services(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug("Removing entry.")
    uuid = entry.data[UUID]
    bosch = hass.data[DOMAIN].pop(uuid)
    unload_ok = await bosch[BOSCH_GATEWAY_ENTRY].async_reset()
    async_remove_services(hass, entry)
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """Reload entry if options change."""
    _LOGGER.debug("Reloading entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
