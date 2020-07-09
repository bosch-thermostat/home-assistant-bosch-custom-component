"""Platform to control a Bosch IP thermostats units."""
import asyncio
import logging
import random
from datetime import timedelta

import voluptuous as vol
from bosch_thermostat_client.const import (
    DHW,
    HC,
    SC,
    XMPP,
    SENSOR,
    SENSORS
)
from bosch_thermostat_client import gateway_chooser
from bosch_thermostat_client.exceptions import DeviceException
from bosch_thermostat_client.version import __version__ as LIBVERSION

import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ACCESS_TOKEN,
    CONF_ADDRESS,
    CONF_PASSWORD,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, HomeAssistantType
from homeassistant.util.json import load_json, save_json

from .config_flow import configured_hosts
from .const import (
    ACCESS_KEY,
    CLIMATE,
    DOMAIN,
    GATEWAY,
    # SENSOR,
    # SENSORS,
    SIGNAL_BOSCH,
    SIGNAL_CLIMATE_UPDATE_BOSCH,
    SIGNAL_DHW_UPDATE_BOSCH,
    SIGNAL_SENSOR_UPDATE_BOSCH,
    SIGNAL_SOLAR_UPDATE_BOSCH,
    SOLAR,
    UUID,
    WATER_HEATER,
    CONF_PROTOCOL,
    CONF_DEVICE_TYPE,
    ACCESS_TOKEN
)

SCAN_INTERVAL = timedelta(seconds=60)
SCAN_SENSOR_INTERVAL = timedelta(seconds=120)

SERVICE_DEBUG = "debug_scan"
SERVICE_UPDATE = "update_thermostat"
SIGNALS = {
    CLIMATE: SIGNAL_CLIMATE_UPDATE_BOSCH,
    WATER_HEATER: SIGNAL_DHW_UPDATE_BOSCH,
    SENSOR: SIGNAL_SENSOR_UPDATE_BOSCH,
    SOLAR: SIGNAL_SOLAR_UPDATE_BOSCH,
}

SUPPORTED_PLATFORMS = {HC: CLIMATE, DHW: WATER_HEATER, SC: SENSOR, SENSOR: SENSOR}

CUSTOM_DB = "custom_bosch_db.json"
SERVICE_DEBUG_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTITY_ID): cv.string})
BOSCH_GATEWAY_ENTRY = "BoschGatewayEntry"
TASK = "task"
INTERVAL = "interval"
DATA_CONFIGS = "bosch_configs"

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistantType, config: ConfigType):
    """Initialize the Bosch platform."""
    hass.data[DOMAIN] = {}
    return True


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry):
    """Create entry for Bosch thermostat device."""
    _LOGGER.info(f"Setting up Bosch component version {LIBVERSION}.")
    uuid = entry.data[UUID]
    gateway_entry = BoschGatewayEntry(
        hass=hass,
        uuid=uuid,
        host=entry.data[CONF_ADDRESS],
        protocol=entry.data[CONF_PROTOCOL],
        device_type=entry.data[CONF_DEVICE_TYPE],
        access_key=entry.data[ACCESS_KEY],
        access_token=entry.data[ACCESS_TOKEN],
        entry=entry
    )
    hass.data[DOMAIN][uuid] = {BOSCH_GATEWAY_ENTRY: gateway_entry}
    return await gateway_entry.async_init()


async def async_unload_entry(hass: HomeAssistantType, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug("Removing entry.")
    uuid = entry.data[UUID]
    remove_listener = hass.data[DOMAIN][uuid].pop(INTERVAL)
    remove_listener()
    bosch = hass.data[DOMAIN].pop(uuid)
    await bosch[BOSCH_GATEWAY_ENTRY].async_reset()
    return True


class BoschGatewayEntry:
    """Bosch gateway entry config class."""

    def __init__(self, hass, uuid, host, protocol, device_type, access_key, access_token, entry):
        """Init Bosch gateway entry config class."""
        self.hass = hass
        self.uuid = uuid
        self._host = host
        self._access_key = access_key
        self._access_token = access_token
        self._device_type = device_type
        self._protocol = protocol
        self.config_entry = entry
        if protocol == XMPP:
            self._session = self.hass.loop
        else:
            self._session = async_get_clientsession(self.hass, verify_ssl=False)
        self._debug_service_registered = False
        self.gateway = None
        self.prefs = None
        self._initial_update = False
        self._signal_registered = False
        self.supported_platforms = []
        self._update_lock = None

    async def async_init(self):
        """Init async items in entry."""
        import bosch_thermostat_client as bosch

        self._update_lock = asyncio.Lock()
        BoschGateway = bosch.gateway_chooser(device_type=self._device_type)
        self.gateway = BoschGateway(
            session=self._session,
            session_type=self._protocol,
            host=self._host,
            access_key=self._access_key,
            access_token=self._access_token)
        if await self.async_init_bosch():
            self.hass.helpers.dispatcher.async_dispatcher_connect(
                SIGNAL_BOSCH, self.get_signals
            )
            for component in self.supported_platforms:
                if component == SOLAR:
                    continue
                self.hass.async_create_task(
                    self.hass.config_entries.async_forward_entry_setup(
                        self.config_entry, component
                    )
                )
            device_registry = (
                await self.hass.helpers.device_registry.async_get_registry()
            )
            device_registry.async_get_or_create(
                config_entry_id=self.config_entry.entry_id,
                identifiers={(DOMAIN, self.uuid)},
                manufacturer=self.gateway.device_model,
                model=self.gateway.device_type,
                name=self.gateway.device_name,
                sw_version=self.gateway.firmware,
            )
            if GATEWAY in self.hass.data[DOMAIN][self.uuid]:
                self.register_service(True, False)
            _LOGGER.debug(
                "Bosch component registered with platforms %s.",
                self.supported_platforms,
            )
            return True
        return False

    def get_signals(self):
        if all(
            k in self.hass.data[DOMAIN][self.uuid] for k in self.supported_platforms
        ) and not self._signal_registered:
            _LOGGER.debug("Registering service debug and service update interval.")
            # self.hass.async_create_task(self.thermostat_refresh(event_time=781))
            self._signal_registered = True
            self.register_update()
            self.register_service(True, True)

    async def async_reset(self):
        _LOGGER.debug("Removing service debug and service update interval.")
        self.hass.services.async_remove(DOMAIN, SERVICE_DEBUG)
        self.hass.services.async_remove(DOMAIN, SERVICE_UPDATE)

    async def async_init_bosch(self):
        """Initialize Bosch gateway module."""
        _LOGGER.debug("Checking connection to Bosch gateway as %s.", self._host)
        if not await self.gateway.check_connection():
            _LOGGER.error(
                "Cannot connect to Bosch gateway, host %s with UUID: %s",
                self._host,
                self.uuid,
            )
            return False
        _LOGGER.debug("Bosch BUS detected: %s", self.gateway.bus_type)
        if not self.gateway.database:
            custom_db = load_json(self.hass.config.path(CUSTOM_DB), default=None)
            if custom_db:
                _LOGGER.info("Loading custom db file.")
                self.gateway.custom_initialize(custom_db)
        if self.gateway.database:
            supported_bosch = await self.gateway.get_capabilities()
            for supported in supported_bosch:
                element = SUPPORTED_PLATFORMS[supported]
                if element not in self.supported_platforms:
                    self.supported_platforms.append(element)
        self.hass.data[DOMAIN][self.uuid][GATEWAY] = self.gateway
        _LOGGER.info("Bosch initialized.")
        return True

    def register_service(self, debug=False, update=False):
        """Register service to use in HA."""
        if debug and not self._debug_service_registered:
            self.hass.services.async_register(
                DOMAIN,
                SERVICE_DEBUG,
                self.async_handle_debug_service,
                SERVICE_DEBUG_SCHEMA,
            )
            self._debug_service_registered = True
        if update:
            self.hass.services.async_register(
                DOMAIN, SERVICE_UPDATE, self.thermostat_refresh, SERVICE_DEBUG_SCHEMA
            )

    def register_update(self):
        """Register interval auto update."""
        self.hass.data[DOMAIN][self.uuid][INTERVAL] = async_track_time_interval(self.hass, self.thermostat_refresh, SCAN_INTERVAL)

    async def component_update(self, component_type=None, event_time=None):
        """Update data from DHW."""
        if component_type in self.supported_platforms:
            updated = False
            entities = self.hass.data[DOMAIN][self.uuid][component_type]
            for entity in entities:
                if entity.enabled:
                    try:
                        _LOGGER.debug("Updating component %s by %s", component_type, id(self))
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
            await self.component_update(CLIMATE, event_time)
            await self.component_update(WATER_HEATER, event_time)

    async def async_handle_debug_service(self, service_call):
        """Make bosch scan for debug purposes of thermostat."""
        filename = self.hass.config.path("www/bosch_scan.json")
        try:
            async with self._update_lock:
                _LOGGER.info("Starting rawscan of Bosch component")
                rawscan = await self.gateway.rawscan()
                save_json(filename, rawscan)
                url = "{}{}".format(self.hass.config.api.base_url, "/local/bosch_scan.json")
                _LOGGER.info(
                    "Rawscan success. Your URL: {}?v{}".format(url, random.randint(0, 5000))
                )
        except OSError as err:
            _LOGGER.error("Can't write image to file: %s", err)


    async def async_reset(self):
        """Reset this device to default state."""
        unload_ok = all(
            await asyncio.gather(
                *[
                    self.hass.config_entries.async_forward_entry_unload(
                        self.config_entry, component
                    )
                    for component in self.supported_platforms
                ]
            )
        )
        if not unload_ok:
            _LOGGER.debug("Unload failed!")
            return False

        return True