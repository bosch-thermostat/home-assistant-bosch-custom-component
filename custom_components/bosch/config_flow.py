"""Config flow to configure Bosch component."""

from __future__ import annotations

import logging

import voluptuous as vol
from bosch_thermostat_client import gateway_chooser
from bosch_thermostat_client.const import HTTP, XMPP
from bosch_thermostat_client.const.easycontrol import EASYCONTROL
from bosch_thermostat_client.const.ivt import IVT, IVT_MBLAN
from bosch_thermostat_client.const.nefit import NEFIT
from bosch_thermostat_client.exceptions import (
    DeviceException,
    EncryptionException,
    FirmwareException,
    UnknownDevice,
)

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_ADDRESS,
    CONF_PASSWORD,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import create_notification_firmware
from .const import (
    ACCESS_KEY,
    ACCESS_TOKEN,
    CONF_DEVICE_TYPE,
    CONF_PROTOCOL,
    DOMAIN,
    UUID,
)

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE = [NEFIT, IVT, EASYCONTROL, IVT_MBLAN]
PROTOCOLS = [HTTP, XMPP]


class BoschFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a Bosch config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize Bosch flow."""
        self._choose_type = None
        self._host = None
        self._access_token = None
        self._password = None
        self._protocol = None
        self._device_type = None

    async def async_step_user(self, user_input=None):
        """Handle flow initiated by user."""
        return await self.async_step_choose_type(user_input)

    # resten af filen uændret ...

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry):
        """Get option flow."""
        return OptionsFlowHandler(entry)


class OptionsFlowHandler(OptionsFlow):
    """Options flow handler."""

    def __init__(self, entry: ConfigEntry):
        """Initialize options flow."""
        self.entry = entry

    async def async_step_init(self, user_input=None):
        """Display option dialog."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        new_stats_api = self.entry.options.get("new_stats_api", False)
        optimistic_mode = self.entry.options.get("optimistic_mode", False)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "new_stats_api",
                        default=new_stats_api,
                    ): bool,
                    vol.Optional(
                        "optimistic_mode",
                        default=optimistic_mode,
                    ): bool,
                }
            ),
        )
