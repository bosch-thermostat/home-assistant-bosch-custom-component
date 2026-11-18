"""Helpers for Bosch integration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bosch_thermostat_client.const import HTTP

from .const import BINARY_SENSOR, CLIMATE, CONF_PROTOCOL, SENSOR, SOLAR
from .pool import async_pool_available

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from .gateway import BoschGatewayEntry

_LOGGER = logging.getLogger(__name__)

async def async_setup_platforms(
    gateway_entry: BoschGatewayEntry, 
    config_entry: ConfigEntry
) -> None:
    """Set up platforms for Bosch gateway."""
    extra = []
    protocol = str(config_entry.data.get(CONF_PROTOCOL, "")).lower()
    if config_entry.options.get("virtual_heatpump_diagnostics") and protocol in (
        str(HTTP).lower(),
        "http",
    ):
        extra = [SENSOR, BINARY_SENSOR]
    platforms = [
        platform
        for platform in list(gateway_entry.supported_platforms) + extra
        if platform != SOLAR
    ]
    # Pool climate when KM200 has pool paths even without HC capability.
    if (
        CLIMATE not in platforms
        and gateway_entry.gateway is not None
        and await async_pool_available(gateway_entry.gateway)
    ):
        platforms.append(CLIMATE)
    # Keep order, drop duplicates.
    seen: set[str] = set()
    platforms = [p for p in platforms if not (p in seen or seen.add(p))]
    
    if not platforms:
        _LOGGER.debug("No supported platforms found for Bosch gateway %s", gateway_entry.uuid)
        return

    _LOGGER.debug(
        "Forwarding entry setup for Bosch platforms: %s",
        platforms,
    )
    
    await gateway_entry.hass.config_entries.async_forward_entry_setups(
        config_entry,
        platforms,
    )
