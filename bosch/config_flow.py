"""Config flow to configure esphome component."""
import logging
import asyncio

import voluptuous as vol


from homeassistant.core import callback
from homeassistant import config_entries
from bosch_thermostat_http.gateway import Gateway
from bosch_thermostat_http.errors import RequestError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import (
    CONF_ADDRESS, CONF_ACCESS_TOKEN, CONF_PASSWORD)

from .const import DOMAIN, ACCESS_KEY, UUID, SENSORS

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
        # self.bosch_config = {
        #     UUID: None,
        #     CONF_ADDRESS: None,
        #     ACCESS_KEY: None
        # }
        self._host = None
        self._access_token = None
        self._password = None
        self.result = None
        self.device = None

    # @staticmethod
    # @callback
    # def async_get_options_flow(config_entry):
    #     """Get the options flow for this handler."""
    #     return BoschOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle flow initiated by user."""
        return await self.async_step_init(user_input)

    async def async_step_sensors(self, user_input=None):
        if self.device and user_input is not None:
            return await self._entry_from_gateway(self.device, user_input)
        _LOGGER.error('One sensor is mandatory!')
        return self.async_abort(reason='unknown')

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            self.host = self.context["address"] = user_input["address"]
            self.access_token = user_input["access_token"]
            password = user_input[CONF_PASSWORD]
            websession = async_get_clientsession(self.hass, verify_ssl=False)
            try:
                self.device = Gateway(websession, self.host,
                                 self.access_token,
                                 password)
                if await self.device.check_connection():
                    return self.async_show_form(step_id="sensors", 
                        data_schema=vol.Schema({vol.Required(sensor): bool for sensor in self.device.database[SENSORS].keys()}),
                        errors=errors)
                # return await self._entry_from_gateway(device, sensors)
            except RequestError as err:
                _LOGGER.error('Wrong IP or credentials at %s - %s', self.host, err)
                return self.async_abort(reason='faulty_credentials')                
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.error('Error connecting Bosch at %s - %s', self.host, err)

        return self.async_show_form(step_id="init", data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): str,
                vol.Required(CONF_ACCESS_TOKEN): str,
                vol.Required(CONF_PASSWORD): str
            }),errors=errors)

    async def async_step_import(self, user_input=None):
        """Handle a flow import."""
        if (user_input[CONF_ADDRESS] and user_input[CONF_PASSWORD] and
                user_input[CONF_ACCESS_TOKEN]):
            address = user_input[CONF_ADDRESS]
            sensors = user_input.get(SENSORS, [])
            websession = async_get_clientsession(self.hass, verify_ssl=False)
            try:
                device = Gateway(websession, address,
                                 user_input[CONF_ACCESS_TOKEN],
                                 user_input[CONF_PASSWORD])
                return await self._entry_from_gateway(device, sensors)
            except RequestError as err:
                _LOGGER.error('Wrong IP or credentials at %s - %s', address, err)
                return self.async_abort(reason='faulty_credentials')                
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.error('Error connecting Bosch at %s - %s', address, err)
        return self.async_abort(reason='unknown')

    async def async_step_discovery(self, discovery_info=None):
        """Handle a flow discovery."""
        _LOGGER.debug("Discovered Bosch unit : %s", discovery_info)
        self.bosch_config[UUID] = discovery_info['properties'][UUID]
        self.bosch_config[CONF_ADDRESS] = discovery_info['host']
        return await self.async_step_init()

    async def _entry_from_gateway(self, gateway, sensors):
        """Return a config entry from an initialized bridge."""
        # Remove all other entries of hubs with same ID or host
        host = gateway.host
        uuid = await gateway.check_connection()
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
        if isinstance(sensors, list):
            options_sensors = {sensor: (True if sensor in sensors else False) for sensor in gateway.database[SENSORS].keys() }
        else:
            options_sensors = sensors
        return self.async_create_entry(
            title=gateway.device_name,
            data={CONF_ADDRESS: host, UUID: uuid, ACCESS_KEY: gateway.access_key, SENSORS: options_sensors},   
        )

class BoschOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Unifi options."""

    def __init__(self, config_entry):
        """Initialize UniFi options flow."""
        self.config_entry = config_entry
        self._data = config_entry.data
        self.sensors_options = dict(self._data[SENSORS])

    async def async_step_init(self, user_input=None):
        """Manage the UniFi options."""
        return await self.async_step_sensors()

    async def async_step_sensors(self, user_input=None):
        """Manage the device tracker options."""
        return self.async_show_form(step_id="sensors",
                        data_schema=vol.Schema({vol.Required(sensor, default=(value)): bool for sensor, value in self.sensors_options.items()}))
        # updated = False
        # if user_input is not None:
        #     for sensor, value in self.sensors_options.items():
        #         if sensor in user_input:
        #             if user_input[sensor] != value:
        #                 self.sensors_options[sensor] = user_input[sensor]
        #                 updated = True
        #     if updated:
        #         return self.async_create_entry(title="", data=self._data)
        