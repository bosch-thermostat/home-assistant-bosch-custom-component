"""Platform to control a Bosch IP thermostats units."""
from datetime import timedelta
import logging
import voluptuous as vol

from bosch_thermostat_http.const import (
    DHW, FIRMWARE_VERSION, HC, SYSTEM_BRAND, SYSTEM_TYPE)
from bosch_thermostat_http.db import bosch_sensors
from bosch_thermostat_http.errors import SensorNoLongerAvailable

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS, CONF_PASSWORD, CONF_ACCESS_TOKEN)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.event import (
    async_track_time_interval, async_call_later)
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from .config_flow import BoschFlowHandler
from .const import (
    ACCESS_KEY, DHW_UPDATE_KEYS, DOMAIN, HCS_UPDATE_KEYS, STORAGE_KEY,
    STORAGE_VERSION, SUPPORTED_PLATFORMS, SIGNAL_SENSOR_UPDATE_BOSCH,
    SIGNAL_DHW_UPDATE_BOSCH, SIGNAL_CLIMATE_UPDATE_BOSCH)

SCAN_INTERVAL = timedelta(seconds=30)


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
    websession = async_get_clientsession(hass, verify_ssl=False)
    uuid = entry.title
    if entry.data[CONF_ADDRESS] and entry.data[ACCESS_KEY]:
        gateway = bosch.Gateway(websession,
                                entry.data[CONF_ADDRESS],
                                entry.data[ACCESS_KEY])
        store = hass.helpers.storage.Store(STORAGE_VERSION, STORAGE_KEY)
        prefs = await store.async_load()
        _LOGGER.debug("Checking connection to Bosch gateway.")
        if not await gateway.check_connection():
            _LOGGER.error(
                "Cannot connect to Bosch gateway, host %s with UUID: %s",
                entry.data[CONF_ADDRESS], uuid)
            return False
        current_firmware = gateway.get_info(FIRMWARE_VERSION)
        if prefs is None:
            prefs = {uuid: {"uuid": uuid, FIRMWARE_VERSION: current_firmware}}
        prefs[uuid], need_saving1 = (await initialize_component(
            HC, uuid, prefs[uuid], gateway))
        prefs[uuid], need_saving2 = (await initialize_component(
            DHW, uuid, prefs[uuid], gateway))
        (await initialize_component(
            "sensors", uuid, bosch_sensors(current_firmware), gateway))
        hass.data[DOMAIN][uuid] = {'gateway': gateway}
        if need_saving1 or need_saving2:
            await store.async_save(prefs)
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
            sw_version=current_firmware)
        _LOGGER.debug("Bosch component registered.")

    async def thermostat_refresh(event_time):
        """Call Bosch to refresh information."""
        _LOGGER.debug("Updating Bosch thermostat entitites.")
        data = hass.data[DOMAIN][uuid]
        await circuit_update(data['hcs'], HCS_UPDATE_KEYS)
        dispatcher_send(hass, SIGNAL_CLIMATE_UPDATE_BOSCH)
        await circuit_update(data['dhws'], DHW_UPDATE_KEYS)
        dispatcher_send(hass, SIGNAL_DHW_UPDATE_BOSCH)
        await sensors_update(data['sensors'])
        dispatcher_send(hass, SIGNAL_SENSOR_UPDATE_BOSCH)
        _LOGGER.debug("Bosch thermostat entitites updated.")

    # hass.services.register(DOMAIN, 'update', thermostat_refresh)

    # Repeat running every 30 seconds.
    async_track_time_interval(hass, thermostat_refresh, SCAN_INTERVAL)
    return True


async def circuit_update(circuits, keys_to_update):
    """Update upstream circuit."""
    for circuit in circuits:
        for dest in keys_to_update:
            await circuit.upstream_object.update_requested_key(dest)


async def sensors_update(sensors):
    """Update upstream sensor."""
    for sensor in sensors:
        try:
            await sensor.upstream_object.update()
        except SensorNoLongerAvailable:
            _LOGGER.warning("Sensor %s is no longer available.",
                            sensor.name)


async def initialize_component(component_type, uuid, components, gateway):
    """Initialize component."""
    equal_firmware = (gateway.get_info(FIRMWARE_VERSION) ==
                      components[FIRMWARE_VERSION])
    components[component_type] = ([] if component_type not in components or
                                  not equal_firmware
                                  else components[component_type])
    if component_type == "sensors":
        await gateway.initialize_sensors(components[component_type])
        component_list = gateway.sensors
    else:
        await gateway.initialize_circuits(component_type,
                                          components[component_type])
        component_list = gateway.get_circuits(component_type)
    need_saving = False
    if not components[component_type]:
        for component in component_list:
            if component_type == "sensors":
                components[component_type].append({"id": component.attr_id})
            else:
                components[component_type].append({
                    "id": component.attr_id,
                    "references": component.json_scheme
                })
        need_saving = True
    return components, need_saving
