"""Platform to control a Bosch IP thermostats units."""
from __future__ import annotations
import asyncio
import logging
import random
from datetime import timedelta
from collections.abc import Awaitable
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from bosch_thermostat_client.const import (
    DHW,
    HC,
    HTTP,
    NUMBER,
    SC,
    RECORDING,
    SELECT,
    SENSOR,
    ZN,
)
from bosch_thermostat_client.const.easycontrol import DV
from bosch_thermostat_client.exceptions import (
    DeviceException,
    FirmwareException,
    EncryptionException,
    UnknownDevice,
)
from bosch_thermostat_client.version import __version__ as LIBVERSION
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ADDRESS,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_utc_time,
    async_track_time_interval,
)
from homeassistant.helpers.network import get_url
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util
from homeassistant.util.json import load_json, save_json

from custom_components.bosch.switch import SWITCH

from .const import (
    ACCESS_KEY,
    ACCESS_TOKEN,
    BINARY_SENSOR,
    CONF_DEVICE_TYPE,
    CONF_PROTOCOL,
    DOMAIN,
    FIRMWARE_SCAN_INTERVAL,
    FW_INTERVAL,
    GATEWAY,
    INTERVAL,
    NOTIFICATION_ID,
    RECORDING_INTERVAL,
    SCAN_INTERVAL,
    SIGNAL_BINARY_SENSOR_UPDATE_BOSCH,
    SIGNAL_BOSCH,
    SIGNAL_CLIMATE_UPDATE_BOSCH,
    SIGNAL_DHW_UPDATE_BOSCH,
    SIGNAL_NUMBER,
    SIGNAL_SENSOR_UPDATE_BOSCH,
    SIGNAL_SOLAR_UPDATE_BOSCH,
    SIGNAL_SWITCH,
    SIGNAL_SELECT,
    SOLAR,
    UUID,
    WATER_HEATER,
    CLIMATE,
    BOSCH_GATEWAY_ENTRY,
)
from .services import (
    async_register_services,
    async_register_debug_service,
    async_remove_services,
)

SIGNALS = {
    CLIMATE: SIGNAL_CLIMATE_UPDATE_BOSCH,
    WATER_HEATER: SIGNAL_DHW_UPDATE_BOSCH,
    SENSOR: SIGNAL_SENSOR_UPDATE_BOSCH,
    BINARY_SENSOR: SIGNAL_BINARY_SENSOR_UPDATE_BOSCH,
    SOLAR: SIGNAL_SOLAR_UPDATE_BOSCH,
    SWITCH: SIGNAL_SWITCH,
    SELECT: SIGNAL_SELECT,
    NUMBER: SIGNAL_NUMBER,
}

SUPPORTED_PLATFORMS = {
    HC: [CLIMATE],
    DHW: [WATER_HEATER],
    SWITCH: [SWITCH],
    SELECT: [SELECT],
    NUMBER: [NUMBER],
    SC: [SENSOR],
    SENSOR: [SENSOR, BINARY_SENSOR],
    ZN: [CLIMATE],
    DV: [SENSOR],
}


CUSTOM_DB = "custom_bosch_db.json"
SERVICE_DEBUG_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids})
SERVICE_INTEGRATION_SCHEMA = vol.Schema({vol.Required(UUID): int})

TASK = "task"

DATA_CONFIGS = "bosch_configs"

_LOGGER = logging.getLogger(__name__)

HOUR = timedelta(hours=1)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Initialize the Bosch platform."""
    hass.data[DOMAIN] = {}
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Create entry for Bosch thermostat device."""
    _LOGGER.info(f"Setting up Bosch component version {LIBVERSION}.")
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
        entry=entry,
    )
    hass.data[DOMAIN][uuid] = {BOSCH_GATEWAY_ENTRY: gateway_entry}
    _init_status: bool = await gateway_entry.async_init()
    if not _init_status:
        return _init_status
    async_register_services(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug("Removing entry.")
    uuid = entry.data[UUID]
    data = hass.data[DOMAIN][uuid]

    def remove_entry(key):
        value = data.pop(key, None)
        if value:
            value()

    remove_entry(INTERVAL)
    remove_entry(FW_INTERVAL)
    remove_entry(RECORDING_INTERVAL)
    bosch = hass.data[DOMAIN].pop(uuid)
    unload_ok = await bosch[BOSCH_GATEWAY_ENTRY].async_reset()
    async_remove_services(hass, entry)
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """Reload entry if options change."""
    _LOGGER.debug("Reloading entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


def create_notification_firmware(hass: HomeAssistant, msg):
    """Create notification about firmware to the user."""
    hass.components.persistent_notification.async_create(
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
        self, hass, uuid, host, protocol, device_type, access_key, access_token, entry
    ) -> None:
        """Init Bosch gateway entry config class."""
        self.hass = hass
        self.uuid = uuid
        self._host = host
        self._access_key = access_key
        self._access_token = access_token
        self._device_type = device_type
        self._protocol = protocol
        self.config_entry = entry
        self._debug_service_registered = False
        self.gateway = None
        self.prefs = None
        self._initial_update = False
        self._signal_registered = False
        self.supported_platforms = []
        self._update_lock = None

    @property
    def device_id(self) -> str:
        return self.config_entry.entry_id

    async def async_init(self) -> bool:
        """Init async items in entry."""
        import bosch_thermostat_client as bosch

        _LOGGER.debug("Initializing Bosch integration.")
        self._update_lock = asyncio.Lock()
        BoschGateway = bosch.gateway_chooser(device_type=self._device_type)
        self.gateway = BoschGateway(
            session=async_get_clientsession(self.hass, verify_ssl=False)
            if self._protocol == HTTP
            else None,
            session_type=self._protocol,
            host=self._host,
            access_key=self._access_key,
            access_token=self._access_token,
        )

        async def close_connection(event) -> None:
            """Close connection with server."""
            _LOGGER.debug("Closing connection to Bosch")
            await self.gateway.close()

        if await self.async_init_bosch():
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, close_connection)
            self.hass.helpers.dispatcher.async_dispatcher_connect(
                SIGNAL_BOSCH, self.get_signals
            )
            for component in self.supported_platforms:
                if component == SOLAR:
                    continue
                asyncio.run_coroutine_threadsafe(
                    self.hass.config_entries.async_forward_entry_setup(
                        self.config_entry, component
                    ),
                    self.hass.loop
                )
            device_registry = dr.async_get(self.hass)
            device_registry.async_get_or_create(
                config_entry_id=self.config_entry.entry_id,
                identifiers={(DOMAIN, self.uuid)},
                manufacturer=self.gateway.device_model,
                model=self.gateway.device_type,
                name=self.gateway.device_name,
                sw_version=self.gateway.firmware,
            )
            if GATEWAY in self.hass.data[DOMAIN][self.uuid]:
                _LOGGER.debug("Registering debug services.")
                async_register_debug_service(hass=self.hass, entry=self)
            _LOGGER.debug(
                "Bosch component registered with platforms %s.",
                self.supported_platforms,
            )
            return True
        return False

    def get_signals(self) -> None:
        """Prepare update after all entities are loaded."""
        if not self._signal_registered and all(
            k in self.hass.data[DOMAIN][self.uuid] for k in self.supported_platforms
        ):
            _LOGGER.debug("Registering thermostat update interval.")
            self._signal_registered = True
            self.hass.data[DOMAIN][self.uuid][INTERVAL] = async_track_time_interval(
                self.hass, self.thermostat_refresh, SCAN_INTERVAL
            )
            self.hass.data[DOMAIN][self.uuid][FW_INTERVAL] = async_track_time_interval(
                self.hass,
                self.firmware_refresh,
                FIRMWARE_SCAN_INTERVAL,  # SCAN INTERVAL FV
            )
            async_call_later(self.hass, 5, self.thermostat_refresh)
            asyncio.run_coroutine_threadsafe(self.recording_sensors_update(),
                self.hass.loop
            )

    async def async_init_bosch(self) -> bool:
        """Initialize Bosch gateway module."""
        _LOGGER.debug("Checking connection to Bosch gateway as %s.", self._host)
        try:
            await self.gateway.check_connection()
        except (FirmwareException) as err:
            create_notification_firmware(hass=self.hass, msg=err)
            _LOGGER.error(err)
            return False
        except (UnknownDevice, EncryptionException) as err:
            _LOGGER.error(err)
            _LOGGER.error("You might need to check your password.")
            raise ConfigEntryNotReady(
                "Cannot connect to Bosch gateway, host %s with UUID: %s",
                self._host,
                self.uuid,
            )
        if not self.gateway.uuid:
            raise ConfigEntryNotReady(
                "Cannot connect to Bosch gateway, host %s with UUID: %s",
                self._host,
                self.uuid,
            )
        _LOGGER.debug("Bosch BUS detected: %s", self.gateway.bus_type)
        if not self.gateway.database:
            custom_db = load_json(self.hass.config.path(CUSTOM_DB), default=None)
            if custom_db:
                _LOGGER.info("Loading custom db file.")
                self.gateway.custom_initialize(custom_db)
        if self.gateway.database:
            supported_bosch = await self.gateway.get_capabilities()
            for supported in supported_bosch:
                elements = SUPPORTED_PLATFORMS[supported]
                for element in elements:
                    if element not in self.supported_platforms:
                        self.supported_platforms.append(element)
        self.hass.data[DOMAIN][self.uuid][GATEWAY] = self.gateway
        _LOGGER.info("Bosch initialized.")
        return True

    async def recording_sensors_update(self, now=None) -> bool | None:
        """Update of 1-hour sensors.

        It suppose to be called only once an hour
        so sensor get's average data from Bosch.
        """
        entities = self.hass.data[DOMAIN][self.uuid].get(RECORDING, [])
        if not entities:
            return
        recording_callback = self.hass.data[DOMAIN][self.uuid].pop(
            RECORDING_INTERVAL, None
        )
        if recording_callback is not None:
            recording_callback()
            recording_callback = None
        updated = False
        signals = []
        now = dt_util.now()
        for entity in entities:
            if entity.enabled:
                try:
                    _LOGGER.debug("Updating component 1-hour Sensor by %s", id(self))
                    await entity.bosch_object.update(time=now)
                    updated = True
                    if entity.signal not in signals:
                        signals.append(entity.signal)
                except DeviceException as err:
                    _LOGGER.warning(
                        "Bosch object of entity %s is no longer available. %s",
                        entity.name,
                        err,
                    )

        def rounder(t):
            matching_seconds = [0]
            matching_minutes = [6]  # 6
            matching_hours = dt_util.parse_time_expression("*", 0, 23)
            return dt_util.find_next_time_expression_time(
                t, matching_seconds, matching_minutes, matching_hours
            )

        nexti = rounder(now + timedelta(seconds=1))
        self.hass.data[DOMAIN][self.uuid][
            RECORDING_INTERVAL
        ] = async_track_point_in_utc_time(
            self.hass, self.recording_sensors_update, nexti
        )
        _LOGGER.debug("Next update of 1-hour sensors scheduled at: %s", nexti)
        if updated:
            _LOGGER.debug("Bosch 1-hour entitites updated.")
            for signal in signals:
                async_dispatcher_send(self.hass, signal)
            return True

    async def custom_put(self, path: str, value: Any) -> None:
        """Send PUT directly to gateway without parsing."""
        await self.gateway.raw_put(path=path, value=value)

    async def custom_get(self, path) -> str:
        """Fetch value from gateway."""
        async with self._update_lock:
            return await self.gateway.raw_query(path=path)

    async def component_update(self, component_type=None, event_time=None):
        """Update data from HC, DHW, ZN, Sensors, Switch."""
        if component_type in self.supported_platforms:
            updated = False
            entities = self.hass.data[DOMAIN][self.uuid][component_type]
            for entity in entities:
                if entity.enabled:
                    try:
                        _LOGGER.debug(
                            "Updating component %s %s by %s",
                            component_type,
                            entity.entity_id,
                            id(self),
                        )
                        await entity.bosch_object.update()
                        updated = True
                    except DeviceException as err:
                        _LOGGER.warning(
                            "Bosch object of entity %s is no longer available. %s",
                            entity.name,
                            err,
                        )
            if updated:
                _LOGGER.debug(f"Bosch {component_type   } entitites updated.")
                async_dispatcher_send(self.hass, SIGNALS[component_type])
                return True
        return False

    async def thermostat_refresh(self, event_time=None):
        """Call Bosch to refresh information."""
        if self._update_lock.locked():
            _LOGGER.debug("Update already in progress. Not updating.")
            return
        _LOGGER.debug("Updating Bosch thermostat entitites.")
        async with self._update_lock:
            await self.component_update(SENSOR, event_time)
            await self.component_update(BINARY_SENSOR, event_time)
            await self.component_update(CLIMATE, event_time)
            await self.component_update(WATER_HEATER, event_time)
            await self.component_update(SWITCH, event_time)
            await self.component_update(NUMBER, event_time)
            _LOGGER.debug("Finish updating entities. Waiting for next scheduled check.")

    async def firmware_refresh(self, event_time=None):
        """Call Bosch to refresh firmware info."""
        if self._update_lock.locked():
            _LOGGER.debug("Update already in progress. Not updating.")
            return
        _LOGGER.debug("Updating info about Bosch firmware.")
        try:
            async with self._update_lock:
                await self.gateway.check_firmware_validity()
        except FirmwareException as err:
            create_notification_firmware(hass=self.hass, msg=err)

    async def make_rawscan(self, filename: str) -> dict:
        """Create rawscan from service."""
        rawscan = {}
        async with self._update_lock:
            _LOGGER.info("Starting rawscan of Bosch component")
            self.hass.components.persistent_notification.async_create(
                title="Bosch scan",
                message=(f"Starting rawscan"),
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
            _LOGGER.info(f"Rawscan success. Your URL: {url}")
            self.hass.components.persistent_notification.async_create(
                title="Bosch scan",
                message=(f"[{url}]({url})"),
                notification_id=NOTIFICATION_ID,
            )
        return rawscan

    async def async_reset(self) -> bool:
        """Reset this device to default state."""
        _LOGGER.warn("Unloading Bosch module.")
        _LOGGER.debug("Closing connection to gateway.")
        tasks: list[Awaitable] = [
            self.hass.config_entries.async_forward_entry_unload(
                self.config_entry, platform
            )
            for platform in self.supported_platforms
        ]
        unload_ok = await asyncio.gather(*tasks)
        await self.gateway.close(force=False)
        return all(unload_ok)
