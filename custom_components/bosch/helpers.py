"""Helpers for Bosch integration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .const import SOLAR

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from .gateway import BoschGatewayEntry

_LOGGER = logging.getLogger(__name__)

async def async_setup_platforms(
    gateway_entry: BoschGatewayEntry, 
    config_entry: ConfigEntry
) -> None:
    """Set up platforms for Bosch gateway."""
    platforms = [
        platform
        for platform in gateway_entry.supported_platforms
        if platform != SOLAR
    ]
    
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
