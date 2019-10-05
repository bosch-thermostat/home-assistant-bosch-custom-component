"""Platform to control a Bosch IP thermostats units."""
import json
import logging
import random
from datetime import timedelta

import voluptuous as vol
from bosch_thermostat_http.const import DHW, HC, SYSTEM_BRAND, SYSTEM_TYPE, SYSTEM_INFO
from bosch_thermostat_http.errors import SensorNoLongerAvailable

import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (ATTR_ENTITY_ID, CONF_ACCESS_TOKEN,
                                 CONF_ADDRESS, CONF_PASSWORD)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from .config_flow import BoschFlowHandler
from .const import (ACCESS_KEY, CLIMATE, DATABASE, DHWS, DOMAIN, GATEWAY, HCS,
                    SENSOR, SENSORS, SIGNAL_CLIMATE_UPDATE_BOSCH,
                    SIGNAL_DHW_UPDATE_BOSCH, SIGNAL_SENSOR_UPDATE_BOSCH,
                    STORAGE_KEY, STORAGE_VERSION, WATER_HEATER, BOSCH_GW_ENTRY)

SCAN_INTERVAL = timedelta(seconds=30)

SERVICE_DEBUG = 'debug_scan'
SERVICE_UPDATE = 'update_thermostat'
SERVICE_REINIT_DB = "reinit_bosch_schema_db"

SERVICE_DEBUG_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTITY_ID): cv.string,
})

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_ACCESS_TOKEN): cv.string,
    }),
    }, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistantType, config: ConfigType):
    """Initialize the Bosch platform."""
    hass.data[DOMAIN] = {}
    config = config.get(DOMAIN)
    if config and not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(hass.config_entries.flow.async_init(
            DOMAIN, context={'source': config_entries.SOURCE_IMPORT},
            data=config
        ))
    return True


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry):
    """Create entry for Bosch thermostat device."""
    _LOGGER.debug("Setting up Bosch component.")
    uuid = entry.title
    if entry.data[CONF_ADDRESS] and entry.data[ACCESS_KEY]:
        gateway = BoschGatewayEntry(hass, uuid, entry)
        return await gateway.async_init()
    return False


class BoschGatewayEntry():
    """Bosch gateway entry config class."""

    def __init__(self, hass, uuid, entry):
        """Init Bosch gateway entry config class."""
        self.hass = hass
        self.uuid = uuid
        self.entry = entry
        self.address = entry.data[CONF_ADDRESS]
        self.access_key = entry.data[ACCESS_KEY]
        self.websession = async_get_clientsession(self.hass, verify_ssl=False)
        self.gateway = None
        self.prefs = None
        self.supported_platforms = []
        self.store = self.hass.helpers.storage.Store(STORAGE_VERSION,
                                                     STORAGE_KEY)

    async def async_init(self):
        """Init async items in entry."""
        import bosch_thermostat_http as bosch
        self.gateway = bosch.Gateway(self.websession, self.address,
                                     self.access_key)
        if await self.async_init_bosch():
            for component in self.supported_platforms:
                self.hass.async_create_task(
                    self.hass.config_entries.async_forward_entry_setup(
                        self.entry, component))
            device_registry = (
                await self.hass.helpers.device_registry.async_get_registry())
            device_registry.async_get_or_create(
                config_entry_id=self.entry.entry_id,
                identifiers={(DOMAIN, self.uuid)},
                manufacturer=self.gateway.get_info(SYSTEM_BRAND),
                model=self.gateway.get_info(SYSTEM_TYPE),
                name=self.gateway.device_name,
                sw_version=self.gateway.firmware)
            self.register_services()
            await self.register_update()
            _LOGGER.debug("Bosch component registered.")
            return True
        return False

    async def get_database(self):
        """Get database from store."""
        prefs = await self.store.async_load()
        return {} if prefs is None else prefs

    async def async_init_bosch(self):
        """Initialize Bosch gateway module."""
        self.prefs = await self.get_database()
        database = self.prefs.get(self.uuid, {}).get(DATABASE, None)
        _LOGGER.debug("Checking connection to Bosch gateway.")
        if not await self.gateway.check_connection(database):
            _LOGGER.error(
                "Cannot connect to Bosch gateway, host %s with UUID: %s",
                self.address, self.uuid)
            return False
        if await self.gateway.initialize_circuits(HC):
            self.supported_platforms.append(CLIMATE)
        if await self.gateway.initialize_circuits(DHW):
            self.supported_platforms.append(WATER_HEATER)
        if await self.gateway.initialize_sensors():
            self.supported_platforms.append(SENSOR)
        if not database:
            await self.init_database()
        self.hass.data[DOMAIN][self.uuid] = {
            GATEWAY: self.gateway,
            BOSCH_GW_ENTRY: self
        }
        return True

    async def init_database(self, database=None):
        database = self.gateway.database if database is None else database
        self.prefs = {
            self.uuid: {
                DATABASE: database
            }
        }
        await self.store.async_save(self.prefs)

    def register_services(self):
        """Register service to use in HA."""
        self.hass.services.async_register(
            DOMAIN, SERVICE_DEBUG, self.async_handle_debug_service,
            SERVICE_DEBUG_SCHEMA)
        self.hass.services.async_register(
            DOMAIN, SERVICE_UPDATE, self.thermostat_refresh,
            SERVICE_DEBUG_SCHEMA)
        self.hass.services.async_register(
            DOMAIN, SERVICE_REINIT_DB, self.reinit_database,
            SERVICE_DEBUG_SCHEMA)

    async def register_update(self):
        """Register interval auto update."""
        # await self.thermostat_refresh(False)
        # Repeat running every 30 seconds.
        async_track_time_interval(
            self.hass, self.thermostat_refresh, SCAN_INTERVAL)

    async def water_heater_refresh(self):
        """Update data from DHW."""
        data = self.hass.data[DOMAIN][self.uuid].get(DHWS)
        if WATER_HEATER in self.supported_platforms and data:
            await self.circuit_update(data)
            dispatcher_send(self.hass, SIGNAL_DHW_UPDATE_BOSCH)
            _LOGGER.debug("Bosch water heater entitites updated.")
            return True
        return False

    async def climate_refresh(self):
        """Update data from HC."""
        data = self.hass.data[DOMAIN][self.uuid].get(HCS)
        if CLIMATE in self.supported_platforms and data:
            await self.circuit_update(data)
            dispatcher_send(self.hass, SIGNAL_CLIMATE_UPDATE_BOSCH)
            _LOGGER.debug("Bosch climate entitites updated.")
            return True
        return False

    async def sensors_refresh(self):
        """Update data from Sensors."""
        data = self.hass.data[DOMAIN][self.uuid].get(SENSORS)
        if SENSOR in self.supported_platforms and data:
            await self.sensors_update(data)
            dispatcher_send(self.hass, SIGNAL_SENSOR_UPDATE_BOSCH)
            _LOGGER.debug("Bosch sensor entitites updated.")
            return True
        return False

    async def reinit_database(self, event_time):
        _LOGGER.info("Reinitializing Bosch db.")
        from bosch_thermostat_http.db import get_db_of_firmware
        db = get_db_of_firmware(self.gateway.firmware)
        print(db)
        await self.init_database(db)

    async def thermostat_refresh(self, event_time):
        """Call Bosch to refresh information."""
        _LOGGER.debug("Updating Bosch thermostat entitites.")
        await self.climate_refresh()
        await self.water_heater_refresh()
        await self.sensors_refresh()

    async def async_handle_debug_service(self, service_call):
        """Make bosch scan for debug purposes of thermostat."""
        filename = self.hass.config.path("www/bosch_scan.json")

        def _write_to_filr(to_file, rawscan):
            """Executor helper to write image."""
            with open(to_file, 'w') as logfile:
                json.dump(rawscan, logfile, indent=4)
            url = "{}{}".format(self.hass.config.api.base_url,
                                "/local/bosch_scan.json")
            _LOGGER.info("Rawscan success. Your URL: {}?v{}".format(
                url, random.randint(0, 5000)))
        try:
            _LOGGER.info("Starting rawscan of Bosch component")
            rawscan = await self.gateway.rawscan()
            await self.hass.async_add_executor_job(_write_to_filr, filename,
                                                   rawscan)
        except OSError as err:
            _LOGGER.error("Can't write image to file: %s", err)

    async def circuit_update(self, circuits):
        """Update upstream circuit."""
        for circuit in circuits:
            await circuit.upstream_object.update()

    async def sensors_update(self, sensors):
        """Update upstream sensor."""
        for sensor in sensors:
            try:
                await sensor.upstream_object.update()
            except SensorNoLongerAvailable:
                _LOGGER.warning("Sensor %s is no longer available.",
                                sensor.name)
