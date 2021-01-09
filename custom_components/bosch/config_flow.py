"""Config flow to configure esphome component."""
import asyncio
import logging

import voluptuous as vol
from bosch_thermostat_client import gateway_chooser
from bosch_thermostat_client.const import XMPP
from bosch_thermostat_client.const.ivt import HTTP, IVT
from bosch_thermostat_client.const.nefit import NEFIT
from bosch_thermostat_client.exceptions import DeviceException
from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_ADDRESS, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_DEVICE_TYPE, CONF_PROTOCOL

DEVICE_TYPE = [NEFIT, IVT]
PROTOCOLS = [HTTP, XMPP]

from .const import ACCESS_KEY, ACCESS_TOKEN, DOMAIN, UUID

_LOGGER = logging.getLogger(__name__)


@callback
def configured_hosts(hass):
    """Return a set of the configured hosts."""
    """For future to use with discovery!"""
    out = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        out[entry.data[CONF_ADDRESS]] = {
            UUID: entry.data[UUID],
            CONF_ADDRESS: entry.data[CONF_ADDRESS],
            ACCESS_KEY: entry.data[ACCESS_KEY],
            ACCESS_TOKEN: entry.data[ACCESS_TOKEN],
            CONF_DEVICE_TYPE: entry.data[CONF_DEVICE_TYPE],
            CONF_PROTOCOL: entry.data[CONF_PROTOCOL],
        }
    return out


@config_entries.HANDLERS.register(DOMAIN)
class BoschFlowHandler(config_entries.ConfigFlow):
    """Handle a bosch config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
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

    async def async_step_choose_type(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._choose_type = user_input[CONF_DEVICE_TYPE]
            if self._choose_type == IVT:
                return self.async_show_form(
                    step_id="protocol",
                    data_schema=vol.Schema(
                        {
                            vol.Required(CONF_PROTOCOL): vol.All(
                                vol.Upper, vol.In(PROTOCOLS)
                            ),
                        }
                    ),
                    errors=errors,
                )
            elif self._choose_type == NEFIT:
                return await self.async_step_protocol({CONF_PROTOCOL: XMPP})
        return self.async_show_form(
            step_id="choose_type",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_TYPE): vol.All(
                        vol.Upper, vol.In(DEVICE_TYPE)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_protocol(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._protocol = user_input[CONF_PROTOCOL]
            step_name = self._protocol.lower() + "_config"
            return self.async_show_form(
                step_id=step_name,
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_ADDRESS): str,
                        vol.Required(CONF_ACCESS_TOKEN): str,
                        vol.Optional(CONF_PASSWORD): str,
                    }
                ),
                errors=errors,
            )
        return self.async_show_form(
            step_id="protocol",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROTOCOL): vol.All(vol.Upper, vol.In(PROTOCOLS)),
                }
            ),
            errors=errors,
        )

    async def async_step_http_config(self, user_input=None):
        if user_input is not None:
            self._host = user_input[CONF_ADDRESS]
            self._access_token = user_input[CONF_ACCESS_TOKEN]
            self._password = user_input.get(CONF_PASSWORD)
            return await self.configure_gateway(
                device_type=self._choose_type,
                session=async_get_clientsession(self.hass, verify_ssl=False),
                session_type=self._protocol,
                host=self._host,
                access_token=self._access_token,
                password=self._password,
            )

    async def async_step_xmpp_config(self, user_input=None):
        if user_input is not None:
            self._host = user_input[CONF_ADDRESS]
            self._access_token = user_input[CONF_ACCESS_TOKEN]
            self._password = user_input.get(CONF_PASSWORD)
            return await self.configure_gateway(
                device_type=self._choose_type,
                session=self.hass.loop,
                session_type=self._protocol,
                host=self._host,
                access_token=self._access_token,
                password=self._password,
            )

    async def configure_gateway(
        self, device_type, session, session_type, host, access_token, password=None
    ):
        try:
            BoschGateway = gateway_chooser(device_type)
            device = BoschGateway(
                session=session,
                session_type=session_type,
                host=host,
                access_token=access_token,
                password=password,
            )
            uuid = await device.check_connection()
            if uuid:
                return await self._entry_from_gateway(device, uuid)
        except DeviceException as err:
            _LOGGER.error("Wrong IP or credentials at %s - %s", host, err)
            return self.async_abort(reason="faulty_credentials")
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Error connecting Bosch at %s - %s", host, err)

    async def async_step_discovery(self, discovery_info=None):
        """Handle a flow discovery."""
        _LOGGER.debug("Discovered Bosch unit : %s", discovery_info)
        pass

    async def _entry_from_gateway(self, gateway, uuid):
        """Return a config entry from an initialized bridge."""
        # Remove all other entries of hubs with same ID or host
        _LOGGER.debug("Adding entry.")
        host = gateway.host
        device_name = gateway.device_name if gateway.device_name else "Unknown"
        same_gateway_entries = [
            entry.entry_id
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if entry.data[UUID] == uuid
        ]
        if same_gateway_entries:
            await asyncio.wait(
                [
                    self.hass.config_entries.async_remove(entry_id)
                    for entry_id in same_gateway_entries
                ]
            )
        data = {
            CONF_ADDRESS: host,
            UUID: uuid,
            ACCESS_KEY: gateway.access_key,
            ACCESS_TOKEN: gateway.access_token,
            CONF_DEVICE_TYPE: self._choose_type,
            CONF_PROTOCOL: self._protocol,
        }
        return self.async_create_entry(title=device_name, data=data)
