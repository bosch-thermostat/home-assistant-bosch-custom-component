"""Platform to control a Bosch IP thermostats units."""
import json
import logging
import random
from datetime import timedelta

import voluptuous as vol
from bosch_thermostat_http.const import DHW, HC, SYSTEM_BRAND, SYSTEM_TYPE
from bosch_thermostat_http.errors import SensorNoLongerAvailable

import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (ATTR_ENTITY_ID, CONF_ACCESS_TOKEN,
                                 CONF_ADDRESS, CONF_PASSWORD)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.event import (async_call_later,
                                         async_track_time_interval)
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from .config_flow import BoschFlowHandler
from .const import (ACCESS_KEY, CLIMATE, DATABASE, DHWS, DOMAIN, GATEWAY, HCS,
                    SENSOR, SENSORS, SIGNAL_CLIMATE_UPDATE_BOSCH,
                    SIGNAL_DHW_UPDATE_BOSCH, SIGNAL_SENSOR_UPDATE_BOSCH,
                    STORAGE_KEY, STORAGE_VERSION, WATER_HEATER)

SCAN_INTERVAL = timedelta(seconds=30)

SERVICE_DEBUG = 'debug_scan'

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
    import bosch_thermostat_http as bosch
    _LOGGER.debug("Setting up Bosch component.")
    SUPPORTED_PLATFORMS = []
    websession = async_get_clientsession(hass, verify_ssl=False)
    uuid = entry.title
    if entry.data[CONF_ADDRESS] and entry.data[ACCESS_KEY]:
        gateway = bosch.Gateway(websession,
                                entry.data[CONF_ADDRESS],
                                entry.data[ACCESS_KEY])
        store = hass.helpers.storage.Store(STORAGE_VERSION, STORAGE_KEY)
        prefs = await store.async_load()
        prefs = {} if prefs is None else {}
        database = prefs.get(uuid, {}).get(DATABASE, None)
        _LOGGER.debug("Checking connection to Bosch gateway.")
        if not await gateway.check_connection(database):
            _LOGGER.error(
                "Cannot connect to Bosch gateway, host %s with UUID: %s",
                entry.data[CONF_ADDRESS], uuid)
            return False
        if await gateway.initialize_circuits(HC):
            SUPPORTED_PLATFORMS.append(CLIMATE)
        if await gateway.initialize_circuits(DHW):
            SUPPORTED_PLATFORMS.append(WATER_HEATER)
        if await gateway.initialize_sensors():
            SUPPORTED_PLATFORMS.append(SENSOR)
        if not database:
            prefs = {
                uuid: {
                    DATABASE: gateway.database
                }
            }
            await store.async_save(prefs)
        hass.data[DOMAIN][uuid] = {
            GATEWAY: gateway
        }
        for component in SUPPORTED_PLATFORMS:
            hass.async_create_task(
                hass.config_entries.async_forward_entry_setup(entry,
                                                              component))
        device_registry = (await
                           hass.helpers.device_registry.async_get_registry())
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, uuid)},
            manufacturer=gateway.get_info(SYSTEM_BRAND),
            model=gateway.get_info(SYSTEM_TYPE),
            name="Gateway iCom_Low_NSC_v1",
            sw_version=gateway.firmware)
        _LOGGER.debug("Bosch component registered.")

    async def thermostat_refresh(event_time):
        """Call Bosch to refresh information."""
        _LOGGER.debug("Updating Bosch thermostat entitites.")
        data = hass.data[DOMAIN][uuid]
        updated = False
        if CLIMATE in SUPPORTED_PLATFORMS:
            await circuit_update(data[HCS])
            dispatcher_send(hass, SIGNAL_CLIMATE_UPDATE_BOSCH)
            updated = True
        if WATER_HEATER in SUPPORTED_PLATFORMS:
            await circuit_update(data[DHWS])
            dispatcher_send(hass, SIGNAL_DHW_UPDATE_BOSCH)
            updated = True
        if SENSOR in SUPPORTED_PLATFORMS:
            await sensors_update(data[SENSORS])
            dispatcher_send(hass, SIGNAL_SENSOR_UPDATE_BOSCH)
            updated = True
        if updated:
            _LOGGER.debug("Bosch thermostat entitites updated.")

    async def async_handle_debug_service(service_call):
        filename = hass.config.path("www/bosch_scan.json")

        def _write_to_filr(to_file, rawscan):
            """Executor helper to write image."""
            with open(to_file, 'w') as logfile:
                json.dump(rawscan, logfile, indent=4)
            url = "{}{}".format(hass.config.api.base_url,
                                "/local/bosch_scan.json")
            _LOGGER.info("Rawscan success. Your URL: {}?v{}".format(
                url, random.randint(0, 5000)))
        try:
            _LOGGER.info("Starting rawscan of Bosch component")
            rawscan = await gateway.rawscan()
            await hass.async_add_executor_job(_write_to_filr, filename,
                                              rawscan)
        except OSError as err:
            _LOGGER.error("Can't write image to file: %s", err)

    # hass.services.register(DOMAIN, 'update', thermostat_refresh)
    hass.services.async_register(
        DOMAIN, SERVICE_DEBUG, async_handle_debug_service,
        SERVICE_DEBUG_SCHEMA)
    # Repeat running every 30 seconds.
    async_track_time_interval(hass, thermostat_refresh, SCAN_INTERVAL)
    return True


async def circuit_update(circuits):
    """Update upstream circuit."""
    for circuit in circuits:
        await circuit.upstream_object.update()


async def sensors_update(sensors):
    """Update upstream sensor."""
    for sensor in sensors:
        try:
            await sensor.upstream_object.update()
        except SensorNoLongerAvailable:
            _LOGGER.warning("Sensor %s is no longer available.",
                            sensor.name)
