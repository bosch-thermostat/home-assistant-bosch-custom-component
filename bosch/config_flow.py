"""Config flow to configure esphome component."""
import logging
import asyncio

import voluptuous as vol


from homeassistant.core import callback
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import (
    CONF_ADDRESS, CONF_ACCESS_TOKEN, CONF_PASSWORD)

from .const import DOMAIN, ACCESS_KEY, UUID

_LOGGER = logging.getLogger(__name__)


@callback
def configured_hosts(hass):
    """Return a set of the configured hosts."""
    out = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        out[entry.data[UUID]] = {
            'id': entry.entry_id,
            CONF_ADDRESS: entry.data[CONF_ADDRESS],
            ACCESS_KEY: entry.data[ACCESS_KEY]
        }
    return out


@config_entries.HANDLERS.register(DOMAIN)
class BoschFlowHandler(config_entries.ConfigFlow):
    """Handle a bosch config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
        """Initialize Bosch flow."""
        self.bosch_config = {
            UUID: None,
            CONF_ADDRESS: None,
            ACCESS_KEY: None
        }

    async def async_step_user(self, user_input=None):
        """Handle flow initiated by user."""
        return await self.async_step_init(user_input)

    async def async_step_init(self, user_input=None):
        """Get initial info from the user."""
        errors = {}
        websession = async_get_clientsession(self.hass, verify_ssl=False)
        found_uuid = self.bosch_config[UUID]
        hosts = configured_hosts(self.hass)
        if found_uuid and found_uuid in hosts:
            present_host = hosts[found_uuid]
            if self.bosch_config[CONF_ADDRESS] == present_host[CONF_ADDRESS]:
                return self.async_abort(reason='already_configured')
            self.bosch_config[ACCESS_KEY] = present_host[ACCESS_KEY]
            await asyncio.wait([self.hass.config_entries.async_remove(
                present_host['id'])])
            return await self.re_setup_device(errors, websession)

        if user_input is not None:
            return await self.setup_new_device(user_input, errors, websession)

        ip_address = (self.bosch_config[CONF_ADDRESS]
                      if self.bosch_config and self.bosch_config[CONF_ADDRESS]
                      else None)
        return self.show_form(errors, ip_address)

    def show_form(self, errors, ip_address=''):
        """Show config form."""
        return self.async_show_form(
            step_id='init',
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS, default=ip_address): str,
                vol.Required(CONF_ACCESS_TOKEN): str,
                vol.Required(CONF_PASSWORD): str
            }),
            errors=errors
        )

    async def re_setup_device(self, errors, websession):
        """Re setup of the device."""
        from bosch_thermostat_http.gateway import Gateway
        from bosch_thermostat_http.errors import RequestError
        try:
            device = Gateway(websession,
                             self.bosch_config[CONF_ADDRESS],
                             self.bosch_config[ACCESS_KEY])
            uuid = await device.check_connection()
            access_key = device.access_key
            if uuid and access_key:
                return self.save_entry(uuid, self.bosch_config[CONF_ADDRESS],
                                       access_key)
        except RequestError:
            errors['base'] = 'Bad IP or Credentials'
            return self.show_form(errors, self.bosch_config[CONF_ADDRESS])
        except Exception:  # pylint: disable=broad-except
            _LOGGER.error(
                'Unknown error connecting with Bosch thermostat at %s',
                self.bosch_config[CONF_ADDRESS])
            return self.async_abort(reason='unknown')

    def save_entry(self, uuid, address, access_key):
        return self.async_create_entry(title=uuid,
                                       data={
                                           UUID: uuid,
                                           CONF_ADDRESS: address,
                                           ACCESS_KEY: access_key
                                       })

    async def setup_new_device(self, user_input, errors, websession):
        """Handle adding new device."""
        self.bosch_config[CONF_ADDRESS] = user_input[CONF_ADDRESS]
        result = add_device(self.bosch_config[CONF_ADDRESS],
                            user_input[CONF_PASSWORD],
                            user_input[CONF_ACCESS_TOKEN],
                            websession)
        if result['status'] == 1:
            return self.save_entry(result.uuid,
                                   self.bosch_config[CONF_ADDRESS],
                                   result.access_key)
        elif result['status'] == -1:
            errors['base'] = result.error
            return self.show_form(errors, user_input[CONF_ADDRESS])
        else:
            return self.async_abort(reason='unknown')

    async def async_step_import(self, user_input=None):
        """Handle a flow import."""
        if (user_input[CONF_ADDRESS] and user_input[CONF_PASSWORD] and 
                user_input[CONF_ACCESS_TOKEN]):
            websession = async_get_clientsession(self.hass, verify_ssl=False)
            result = await add_device(user_input[CONF_ADDRESS],
                                      user_input[CONF_PASSWORD],
                                      user_input[CONF_ACCESS_TOKEN],
                                      websession)
            if result['status'] == 1:
                return self.save_entry(result[UUID],
                                       user_input[CONF_ADDRESS],
                                       result[ACCESS_KEY])
        return self.async_abort(reason='unknown')

    async def async_step_discovery(self, discovery_info=None):
        """Handle a flow discovery."""
        _LOGGER.debug("Discovered Bosch unit : %s", discovery_info)
        self.bosch_config[UUID] = discovery_info['properties'][UUID]
        self.bosch_config[CONF_ADDRESS] = discovery_info['host']
        return await self.async_step_init()


async def add_device(address, password, token, websession):
    """Handle adding new device."""
    from bosch_thermostat_http.gateway import Gateway
    from bosch_thermostat_http.errors import RequestError
    try:
        device = Gateway(websession, address, token, password)
        uuid = await device.check_connection()
        access_key = device.access_key
        if uuid and access_key:
            return {
                "status": 1,
                UUID: uuid,
                ACCESS_KEY: access_key
            }
    except RequestError:
        return {
            "status": -1,
            "error": 'Bad IP or Credentials'
        }
    except Exception:  # pylint: disable=broad-except
        _LOGGER.error(
            'Unknown error connecting with Bosch thermostat at %s',
            address)
        return {
            "status": -2,
            "base": 'Unknown error'
        }
