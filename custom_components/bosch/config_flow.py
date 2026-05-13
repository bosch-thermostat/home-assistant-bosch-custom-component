"""Config flow to configure esphome component."""
import logging

import voluptuous as vol
from bosch_thermostat_client import gateway_chooser
from bosch_thermostat_client.const import HTTP, XMPP
from bosch_thermostat_client.const.easycontrol import EASYCONTROL
from bosch_thermostat_client.const.ivt import IVT, IVT_MBLAN
from bosch_thermostat_client.const.nefit import NEFIT
from bosch_thermostat_client.connectors.oauth2 import Oauth2Connector
from bosch_thermostat_client.exceptions import (
    DeviceException,
    EncryptionException,
    FirmwareException,
    UnknownDevice,
)
from homeassistant import config_entries
from homeassistant.core import callback

from homeassistant.const import CONF_ACCESS_TOKEN, CONF_ADDRESS, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import create_notification_firmware
from .const import (
    ACCESS_KEY,
    ACCESS_TOKEN,
    CONF_DEVICE_TYPE,
    CONF_PROTOCOL,
    DOMAIN,
    REFRESH_TOKEN,
    TOKEN_EXPIRES_AT,
    UUID,
)

DEVICE_TYPE = [NEFIT, IVT, EASYCONTROL, IVT_MBLAN]
PROTOCOLS = [HTTP, XMPP]


_LOGGER = logging.getLogger(__name__)


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
        self._refresh_token = None
        self._token_expires_at = None
        self._password = None
        self._protocol = None
        self._device_type = None
        self._oauth_connector = None

    async def async_step_user(self, user_input=None):
        """Handle flow initiated by user."""
        return await self.async_step_choose_type(user_input)

    async def async_step_choose_type(self, user_input=None):
        """Choose if setup is for IVT, IVT/MBLAN, NEFIT or EASYCONTROL."""
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
            elif self._choose_type == EASYCONTROL:
                return self.async_show_form(
                    step_id="easycontrol_serial",
                    data_schema=vol.Schema(
                        {vol.Required(CONF_ADDRESS): str}
                    ),
                    errors=errors,
                )
            elif self._choose_type in (NEFIT, IVT_MBLAN):
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
            return self.async_show_form(
                step_id=f"{self._protocol.lower()}_config",
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
            if "127.0.0.1" in user_input[CONF_ADDRESS]:
                return await self.configure_gateway(
                    device_type=self._choose_type,
                    session=async_get_clientsession(self.hass, verify_ssl=False),
                    session_type=HTTP,
                    host=self._host,
                    access_token=self._access_token,
                    password=self._password,
                )
            return await self.configure_gateway(
                device_type=self._choose_type,
                session_type=self._protocol,
                host=self._host,
                access_token=self._access_token,
                password=self._password,
            )

    async def async_step_easycontrol_serial(self, user_input=None):
        """Step 1 of EasyControl POINTT OAuth: enter device serial number."""
        errors = {}
        if user_input is not None:
            self._host = user_input[CONF_ADDRESS].strip()
            session = async_get_clientsession(self.hass)
            self._oauth_connector = Oauth2Connector(
                host=self._host,
                access_token="",
                loop=session,
            )
            auth_url = self._oauth_connector.build_auth_url()
            return self.async_show_form(
                step_id="easycontrol_oauth",
                data_schema=vol.Schema({vol.Required("redirect_url"): str}),
                description_placeholders={"auth_url": auth_url},
                errors=errors,
            )
        return self.async_show_form(
            step_id="easycontrol_serial",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}),
            errors=errors,
        )

    async def async_step_easycontrol_oauth(self, user_input=None):
        """Step 2 of EasyControl POINTT OAuth: paste redirect URL, exchange code."""
        errors = {}
        if user_input is not None:
            redirect_url = user_input.get("redirect_url", "").strip()
            code = self._oauth_connector.extract_code_from_url(redirect_url)
            if not code:
                errors["redirect_url"] = "invalid_redirect_url"
                return self.async_show_form(
                    step_id="easycontrol_oauth",
                    data_schema=vol.Schema({vol.Required("redirect_url"): str}),
                    description_placeholders={
                        "auth_url": self._oauth_connector.build_auth_url()
                    },
                    errors=errors,
                )

            success = await self._oauth_connector.exchange_code_for_tokens(code)
            if not success:
                errors["base"] = "cannot_connect"
                return self.async_show_form(
                    step_id="easycontrol_oauth",
                    data_schema=vol.Schema({vol.Required("redirect_url"): str}),
                    description_placeholders={
                        "auth_url": self._oauth_connector.build_auth_url()
                    },
                    errors=errors,
                )

            self._access_token = self._oauth_connector._access_token
            self._refresh_token = self._oauth_connector._refresh_token
            self._token_expires_at = self._oauth_connector._token_expires_at

            # Check if the gateway is already claimed
            session = async_get_clientsession(self.hass)
            try:
                from aiohttp import ClientTimeout
                url = f"{Oauth2Connector.POINTTAPI_BASE_URL}"
                headers = {"Authorization": f"Bearer {self._access_token}"}
                async with session.get(url, headers=headers, timeout=ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        gateways = await resp.json()
                        device_ids = [gw.get("deviceId") for gw in gateways]
                        if self._host in device_ids:
                            _LOGGER.debug("Gateway %s already claimed", self._host)
                            return await self._easycontrol_create_entry()
            except Exception as err:
                _LOGGER.debug("Gateway list check failed: %s", err)

            # Gateway not claimed — ask for credentials to claim it
            return self.async_show_form(
                step_id="easycontrol_claim",
                data_schema=vol.Schema({
                    vol.Required("access_code"): str,
                    vol.Required("user_password"): str,
                }),
                errors=errors,
            )

        # Should not normally reach here (redirected from easycontrol_serial)
        return self.async_abort(reason="unknown")

    async def async_step_easycontrol_claim(self, user_input=None):
        """Step 3 of EasyControl POINTT OAuth: claim the gateway."""
        errors = {}
        if user_input is not None:
            import json as json_mod
            session = async_get_clientsession(self.hass)
            claim_url = f"{Oauth2Connector.POINTTAPI_BASE_URL}"
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "deviceId": self._host,
                "gatewayPassword": user_input["access_code"],
                "userPassword": user_input["user_password"],
            }

            try:
                from aiohttp import ClientTimeout
                async with session.post(
                    claim_url,
                    headers=headers,
                    json=payload,
                    timeout=ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 201:
                        _LOGGER.info("Successfully claimed gateway %s", self._host)
                        return await self._easycontrol_create_entry()
                    else:
                        body = await resp.text()
                        _LOGGER.error(
                            "Gateway claiming failed: HTTP %s - %s", resp.status, body
                        )
                        errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.error("Gateway claiming error: %s", err)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="easycontrol_claim",
            data_schema=vol.Schema({
                vol.Required("access_code"): str,
                vol.Required("user_password"): str,
            }),
            errors=errors,
        )

    async def _easycontrol_create_entry(self):
        """Create config entry after successful OAuth + claiming."""
        from bosch_thermostat_client.gateway.oauth2 import Oauth2Gateway

        access_token = self._access_token
        refresh_token = self._refresh_token
        token_expires_at = self._token_expires_at

        try:
            gateway = Oauth2Gateway(
                session=async_get_clientsession(self.hass),
                device_type=EASYCONTROL,
                host=self._host,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=(
                    token_expires_at.isoformat() if token_expires_at else None
                ),
            )
            try:
                uuid = await gateway.check_connection()
            except (FirmwareException, UnknownDevice) as err:
                create_notification_firmware(hass=self.hass, msg=err)
                uuid = gateway.uuid
        except (DeviceException, EncryptionException) as err:
            _LOGGER.error("Cannot connect to EasyControl %s: %s", self._host, err)
            return self.async_abort(reason="faulty_credentials")
        except Exception as err:
            _LOGGER.error("Unexpected error connecting EasyControl %s: %s", self._host, err)
            return self.async_abort(reason="unknown")

        if uuid:
            await self.async_set_unique_id(str(uuid))
            self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=gateway.device_name or "Bosch EasyControl",
            data={
                CONF_ADDRESS: self._host,
                UUID: uuid,
                ACCESS_KEY: "",
                ACCESS_TOKEN: access_token,
                REFRESH_TOKEN: refresh_token,
                TOKEN_EXPIRES_AT: (
                    token_expires_at.isoformat() if token_expires_at else None
                ),
                CONF_DEVICE_TYPE: EASYCONTROL,
                CONF_PROTOCOL: HTTP,
            },
        )

    async def configure_gateway(
        self, device_type, session_type, host, access_token, password=None, session=None
    ):
        try:
            BoschGateway = gateway_chooser(device_type)
            device = BoschGateway(
                session_type=session_type,
                host=host,
                access_token=access_token,
                password=password,
                session=session,
            )
            try:
                uuid = await device.check_connection()
            except (FirmwareException, UnknownDevice) as err:
                create_notification_firmware(hass=self.hass, msg=err)
                uuid = device.uuid
            if uuid:
                await self.async_set_unique_id(uuid)
                self._abort_if_unique_id_configured()
        except (DeviceException, EncryptionException) as err:
            _LOGGER.error("Wrong IP or credentials at %s - %s", host, err)
            return self.async_abort(reason="faulty_credentials")
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Error connecting Bosch at %s - %s", host, err)
        else:
            _LOGGER.debug("Adding Bosch entry.")
            return self.async_create_entry(
                title=device.device_name or "Unknown model",
                data={
                    CONF_ADDRESS: device.host,
                    UUID: uuid,
                    ACCESS_KEY: device.access_key,
                    ACCESS_TOKEN: device.access_token,
                    CONF_DEVICE_TYPE: self._choose_type,
                    CONF_PROTOCOL: session_type,
                },
            )

    async def async_step_discovery(self, discovery_info=None):
        """Handle a flow discovery."""
        _LOGGER.debug("Discovered Bosch unit : %s", discovery_info)

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        """Get option flow."""
        return OptionsFlowHandler(entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow handler for new API."""

    def __init__(self, entry: config_entries.ConfigEntry):
        """Initialize option."""
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
                    vol.Optional("new_stats_api", default=new_stats_api): bool,
                    vol.Optional("optimistic_mode", default=optimistic_mode): bool,
                }
            ),
        )
