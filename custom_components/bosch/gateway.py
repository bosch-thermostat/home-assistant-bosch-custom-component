"""Bosch gateway entry config class."""
from __future__ import annotations

import asyncio
import logging
import random
import ssl
from typing import Any, TYPE_CHECKING

from bosch_thermostat_client import easycontrol_ssl_context
from bosch_thermostat_client.const import HTTP, XMPP
from bosch_thermostat_client.const.easycontrol import EASYCONTROL
from bosch_thermostat_client.exceptions import (
    DeviceException,
    EncryptionException,
    FirmwareException,
    UnknownDevice,
)
from homeassistant.components.persistent_notification import (
    async_create as async_create_persistent_notification,
)
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.json import save_json
from homeassistant.helpers.network import get_url
from homeassistant.util.json import load_json
from homeassistant.util.ssl import client_context

from .const import (
    DOMAIN,
    FIRMWARE_SCAN_INTERVAL,
    GATEWAY,
    NOTIFICATION_ID,
    SUPPORTED_PLATFORMS,
)
from .services import async_register_debug_service
from .types import BoschGateway

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from .coordinator import BoschDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

CUSTOM_DB = "custom_bosch_db.json"


def _create_ssl_context(protocol: str, device_type: str) -> ssl.SSLContext | None:
    """Return the SSL context for an XMPP connection (run in the executor).

    Without one, slixmpp builds a default context on the event loop, which HA
    reports as a blocking call (#570). EasyControl pins Bosch's own CA; NEFIT
    and IVT use HA's shared, cached client context. The HTTP connector talks
    plain http:// to the gateway, so it needs none.
    """
    if protocol != XMPP:
        return None
    if device_type == EASYCONTROL:
        # The client caches this, so the CA file is read once per process
        # rather than on every setup attempt and config flow step.
        return easycontrol_ssl_context()
    return client_context()


def create_notification_firmware(hass: HomeAssistant, msg: str | Exception) -> None:
    """Create notification about firmware to the user."""
    async_create_persistent_notification(
        hass,
        title="Bosch info",
        message=(
            "There are problems with config of your thermostat.\n"
            f"{msg}.\n"
            "You can create issue on Github, but first\n"
            "Go to [Developer Tools/Service](/developer-tools/service) and create bosch.debug_scan.\n"
            "[BoschGithub](https://github.com/bosch-thermostat/home-assistant-bosch-custom-component)"
        ),
        notification_id=NOTIFICATION_ID,
    )


class BoschGatewayEntry:
    """Bosch gateway entry config class."""

    def __init__(
        self,
        hass: HomeAssistant,
        uuid: str,
        host: str,
        protocol: str,
        device_type: str,
        access_key: str,
        access_token: str,
        entry: ConfigEntry,
        password: str | None = None,
    ) -> None:
        """Init Bosch gateway entry config class."""
        self.hass = hass
        self.uuid = uuid
        self._host = host
        self._access_key = access_key
        self._access_token = access_token
        self._device_type = device_type
        self._protocol = protocol
        self._password = password
        self.config_entry = entry
        self._debug_service_registered = False
        self.gateway: BoschGateway | None = None
        self._closed = False
        self._stop_unsub: CALLBACK_TYPE | None = None
        self.supported_platforms: list[str] = []
        self._update_lock: asyncio.Lock | None = None
        self.coordinator: BoschDataUpdateCoordinator | None = None

    @property
    def device_id(self) -> str:
        return self.config_entry.entry_id

    async def async_init(self) -> bool:
        """Init async items in entry."""
        import bosch_thermostat_client as bosch

        _LOGGER.debug("Initializing Bosch integration.")
        self._update_lock = asyncio.Lock()

        BoschGatewayClass = bosch.gateway_chooser(device_type=self._device_type)
        # Loading the CA certificate is a blocking call HA flags inside the
        # event loop; build the context in the executor and hand it over.
        ssl_context = await self.hass.async_add_executor_job(
            _create_ssl_context, self._protocol, self._device_type
        )
        session = (
            async_get_clientsession(self.hass, verify_ssl=False)
            if self._protocol == HTTP
            else None
        )
        self.gateway = BoschGatewayClass(
            session=session,
            session_type=self._protocol,
            host=self._host,
            access_key=self._access_key,
            access_token=self._access_token,
            password=self._password,
            ssl_context=ssl_context,
        )

        if await self.async_init_bosch():
            from .coordinator import BoschDataUpdateCoordinator
            from .helpers import async_setup_platforms

            self.coordinator = BoschDataUpdateCoordinator(
                self.hass, self.gateway, self.uuid, self.config_entry
            )

            # Register the gateway device before the platforms so entities can
            # reference it as their parent (via_device_id).
            device_registry = dr.async_get(self.hass)
            gateway_device = device_registry.async_get_or_create(
                config_entry_id=self.config_entry.entry_id,
                identifiers={(DOMAIN, self.uuid)},
                manufacturer=self.gateway.device_model,
                model=self.gateway.device_type,
                name=self.gateway.device_name,
                sw_version=self.gateway.firmware,
            )
            self.coordinator.gateway_device_id = gateway_device.id
            self._async_migrate_device_identifiers(device_registry)

            async def close_connection(event) -> None:
                """Close connection with server on HA shutdown."""
                self._stop_unsub = None  # one-time listener already consumed
                _LOGGER.debug("Closing connection to Bosch")
                await self.async_close()

            self._stop_unsub = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, close_connection
            )
            self.config_entry.async_on_unload(self._async_remove_stop_listener)

            await async_setup_platforms(self, self.config_entry)
            if GATEWAY in self.hass.data[DOMAIN][self.uuid]:
                _LOGGER.debug("Registering debug services.")
                async_register_debug_service(hass=self.hass, entry=self)

            # Entities registered their Bosch objects with the coordinator
            # while the platforms were set up; fetch their data now and start
            # the periodic refresh.
            await self.coordinator.async_refresh()
            # Firmware validity is checked every 4 hours, as before
            self.config_entry.async_on_unload(
                async_track_time_interval(
                    self.hass, self.firmware_refresh, FIRMWARE_SCAN_INTERVAL
                )
            )
            # Recording sensors use their own hourly schedule
            self.config_entry.async_create_background_task(
                self.hass,
                self.coordinator.async_recording_sensors_update(),
                name=f"bosch-{self.uuid}-recording-update",
            )

            _LOGGER.debug(
                "Bosch component registered with platforms %s.",
                self.supported_platforms,
            )
            return True
        return False

    @callback
    def _async_migrate_device_identifiers(
        self, device_registry: dr.DeviceRegistry
    ) -> None:
        """Rewrite legacy (DOMAIN, id, uuid) identifiers to (DOMAIN, f"{uuid}_{id}").

        If a device with the new identifier already exists (downgrade followed
        by an upgrade, or an entry previously run by ha_bosch), the legacy
        device is a stale duplicate: remove it so the entities re-attach to the
        existing one on setup instead of failing the entry. Home Assistant
        restores their entity_id, name and area from its deleted-entity record,
        so their history carries on.
        """
        for device in dr.async_entries_for_config_entry(
            device_registry, self.config_entry.entry_id
        ):
            new_identifiers = {
                (DOMAIN, f"{self.uuid}_{ident[1]}")
                if len(ident) == 3 and ident[0] == DOMAIN and ident[2] == self.uuid
                else ident
                for ident in device.identifiers
            }
            if new_identifiers == device.identifiers:
                continue
            try:
                device_registry.async_update_device(
                    device.id, new_identifiers=new_identifiers
                )
            except dr.DeviceIdentifierCollisionError:
                _LOGGER.warning(
                    "Device %s already exists with identifiers %s; removing the "
                    "legacy duplicate %s",
                    device.name,
                    new_identifiers,
                    device.identifiers,
                )
                # The legacy device belongs to this entry only, so removing it
                # outright is what detaching used to mean. Passing
                # remove_config_entry_id to async_update_device is deprecated
                # in HA 2026.9 and breaks in 2027.8.
                device_registry.async_remove_device(device.id)

    @callback
    def _async_remove_stop_listener(self) -> None:
        """Drop the HA-stop listener if it has not fired yet."""
        if self._stop_unsub is not None:
            self._stop_unsub()
            self._stop_unsub = None

    async def async_close(self) -> None:
        """Close the connection to the gateway (idempotent)."""
        if self.gateway is None or self._closed:
            return
        self._closed = True
        if self.coordinator:
            self.coordinator.async_shutdown_recording()
        try:
            await self.gateway.close()
        except Exception as err:  # noqa: BLE001 - shutdown must not raise
            _LOGGER.debug("Error closing Bosch connection: %s", err)

    async def async_init_bosch(self) -> bool:
        """Initialize Bosch gateway module."""
        _LOGGER.debug("Checking connection to Bosch gateway as %s.", self._host)
        assert self.gateway
        try:
            await self.gateway.check_connection()
        except (FirmwareException) as err:
            create_notification_firmware(hass=self.hass, msg=err)
            _LOGGER.error(err)
            return False
        except (UnknownDevice, EncryptionException) as err:
            _LOGGER.error(
                "Cannot connect to Bosch gateway (%s): %s. Please verify your password and access key.",
                self.uuid,
                err,
            )
            raise ConfigEntryNotReady(
                f"Cannot connect to Bosch gateway, host {self._host} with UUID: {self.uuid}"
            )
        if not self.gateway.uuid:
            raise ConfigEntryNotReady(
                f"Cannot connect to Bosch gateway, host {self._host} with UUID: {self.uuid}"
            )
        _LOGGER.debug("Bosch BUS detected: %s", self.gateway.bus_type)
        if not self.gateway.database:
            custom_db = load_json(self.hass.config.path(CUSTOM_DB), default=None)
            if custom_db:
                _LOGGER.debug("Loading custom db file.")
                assert isinstance(custom_db, dict)
                await self.gateway.custom_initialize(custom_db)
        if self.gateway.database:
            supported_bosch = await self.gateway.get_capabilities()
            _LOGGER.debug("Bosch supported capabilities: %s", supported_bosch)
            for supported in supported_bosch:
                elements = SUPPORTED_PLATFORMS.get(supported, [])
                for element in elements:
                    if element not in self.supported_platforms:
                        self.supported_platforms.append(element)
        self.hass.data[DOMAIN][self.uuid][GATEWAY] = self.gateway
        _LOGGER.debug("Bosch initialized.")
        return True

    async def firmware_refresh(self, event_time: Any = None) -> None:
        """Warn the user when the gateway firmware is no longer supported."""
        assert self.gateway
        _LOGGER.debug("Updating info about Bosch firmware.")
        try:
            await self.gateway.check_firmware_validity()
        except FirmwareException as err:
            create_notification_firmware(hass=self.hass, msg=err)
        except DeviceException as err:
            _LOGGER.debug("Firmware check failed: %s", err)

    async def custom_put(self, path: str, value: Any) -> None:
        """Send PUT directly to gateway without parsing."""
        assert self.gateway
        await self.gateway.raw_put(path=path, value=value)

    async def custom_get(self, path: str) -> Any:
        """Fetch value from gateway."""
        assert self._update_lock
        assert self.gateway
        async with self._update_lock:
            return await self.gateway.raw_query(path=path)

    async def make_rawscan(self, filename: str) -> dict:
        """Create rawscan from service."""
        rawscan = {}
        assert self._update_lock
        assert self.gateway
        async with self._update_lock:
            _LOGGER.debug("Starting rawscan of Bosch component")
            async_create_persistent_notification(
                self.hass,
                title="Bosch scan",
                message=("Starting rawscan"),
                notification_id=NOTIFICATION_ID,
            )
            rawscan = await self.gateway.rawscan()
            try:
                save_json(filename, rawscan)
            except (FileNotFoundError, OSError) as err:
                _LOGGER.error("Can't create file. %s", err)
                if rawscan:
                    return rawscan
            url = "{}{}{}".format(
                get_url(self.hass),
                "/local/bosch_scan.json?v",
                random.randint(0, 5000),
            )
            _LOGGER.debug("Rawscan success. Your URL: %s", url)
            async_create_persistent_notification(
                self.hass,
                title="Bosch scan",
                message=f"[{url}]({url})",
                notification_id=NOTIFICATION_ID,
            )
        return rawscan

    async def async_reset(self) -> bool:
        """Reset this device to default state."""
        _LOGGER.debug("Unloading Bosch module for UUID: %s", self.uuid)
        await self.async_close()

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(
                    self.hass.config_entries.async_forward_entry_unload(
                        self.config_entry, platform
                    )
                )
                for platform in self.supported_platforms
            ]
        return all(task.result() for task in tasks)
