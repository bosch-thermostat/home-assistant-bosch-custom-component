from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class BoschDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Central coordinator for Bosch integration updates."""

    def __init__(self, hass, gateway_entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"bosch_{gateway_entry.uuid}",
            update_interval=SCAN_INTERVAL,
        )
        self._gateway_entry = gateway_entry

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all Bosch data in one coordinated cycle."""
        try:
            await self._gateway_entry.async_refresh_all_components()
            return {"ok": True}
        except Exception as err:
            raise UpdateFailed(f"Bosch refresh failed: {err}") from err
