"""Services used in HA."""
from __future__ import annotations
import logging
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.config_validation as cv
from bosch_thermostat_client.const import RECORDING
from .const import (
    DOMAIN,
    SERVICE_DEBUG,
    SERVICE_UPDATE,
    BOSCH_GATEWAY_ENTRY,
    RECORDING_SERVICE_UPDATE,
    SERVICE_PUT_STRING,
    SERVICE_PUT_FLOAT,
    SERVICE_GET,
    VALUE,
)

from .sensor.recording import RecordingSensor

_LOGGER = logging.getLogger(__name__)

SERVICE_INTEGRATION_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.ensure_list})
SERVICE_GET_SCHEMA = SERVICE_INTEGRATION_SCHEMA.extend({vol.Required("path"): str})
SERVICE_FETCH_RANGE_SCHEMA = SERVICE_INTEGRATION_SCHEMA.extend(
    {vol.Required("day"): cv.date, vol.Required("statistic_id"): str}
)
SERVICE_PUT_STRING_SCHEMA = SERVICE_GET_SCHEMA.extend({vol.Required(VALUE): str})
SERVICE_PUT_FLOAT_SCHEMA = SERVICE_GET_SCHEMA.extend(
    {vol.Required(VALUE): vol.Or(int, float)}
)


def find_gateway_entry(hass: HomeAssistant, devices_id: str) -> list[ConfigEntry]:
    """Find gateway in config entries."""
    config_entries = list[ConfigEntry]()
    registry = dr.async_get(hass)
    for target in devices_id:
        device = registry.async_get(target)
        if device:
            device_entries = list[ConfigEntry]()
            for entry_id in device.config_entries:
                entry = hass.config_entries.async_get_entry(entry_id)
                if entry and entry.domain == DOMAIN and entry not in config_entries:
                    device_entries.append(entry)
                if not device_entries:
                    continue
                config_entries.extend(device_entries)
        else:
            _LOGGER.warn(
                f"Device '{target}' not found in device registry"
            )
    bosch_gateway_entries = []
    for entry in hass.data[DOMAIN].values():
        for config_entry in config_entries:
            if entry[BOSCH_GATEWAY_ENTRY].device_id == config_entry.entry_id:
                bosch_gateway_entries.append(entry[BOSCH_GATEWAY_ENTRY])
    return bosch_gateway_entries


def async_register_debug_service(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register services."""

    async def async_handle_debug_service(service_call: ServiceCall) -> ServiceResponse:
        """Make bosch scan for debug purposes of thermostat."""
        filename = hass.config.path("www/bosch_scan.json")
        _gateway_entries = find_gateway_entry(hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID])
        if not _gateway_entries:
            return
        data = []
        for _gateway_entry in _gateway_entries:
            data.append(await _gateway_entry.make_rawscan(filename))
        return {
            "data": data
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_DEBUG,
        async_handle_debug_service,
        schema=SERVICE_INTEGRATION_SCHEMA,
        supports_response=SupportsResponse.ONLY
    )


def async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register services."""

    async def async_handle_thermostat_refresh(service_call: ServiceCall):
        """Request update of thermostat manually."""
        _gateway_entries = find_gateway_entry(hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID])
        if not _gateway_entries:
            return
        for _gateway_entry in _gateway_entries:
            await _gateway_entry.thermostat_refresh()

    async def async_handle_recording_sensor_refresh(service_call: ServiceCall):
        """Request update of recording sensor manually."""
        _gateway_entries = find_gateway_entry(hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID])
        if not _gateway_entries:
            return
        for _gateway_entry in _gateway_entries:
            await _gateway_entry.thermostat_refresh()
        _LOGGER.debug("Performing sensor update on service request. UUID: %s", _gateway_entry.uuid)
        await _gateway_entry.recording_sensors_update()

    async def async_handle_recording_sensor_fetch_past(service_call: ServiceCall):
        """Request update of recording sensor manually."""
        statistic_id = service_call.data.get("statistic_id")
        day = dt_util.start_of_local_day(service_call.data.get("day"))
        _gateway_entries = find_gateway_entry(hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID])
        if not _gateway_entries:
            return
        for _gateway_entry in _gateway_entries:
            recording_entities: list[RecordingSensor] = _gateway_entry.hass.data[DOMAIN][_gateway_entry.uuid].get(RECORDING, [])
            for entity in recording_entities:
                if entity.enabled and entity.statistic_id == statistic_id:
                    _LOGGER.debug("Fetching single day by service request. UUID: %s, statistic_id: %s, day: %s", _gateway_entry.uuid, statistic_id, day)
                    await entity.insert_statistics_range(start_time=day)

    async def async_handle_get(service_call: ServiceCall) -> ServiceResponse:
        """Request update of recording sensor manually."""
        _gateway_entries = find_gateway_entry(hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID])
        if not _gateway_entries:
            data = ""
        _path = service_call.data.get("path")
        if not _path:
            _LOGGER.error("Path or value not defined.")
            data = ""
        else:
            data = []
            for _gateway_entry in _gateway_entries:
                single_data = await _gateway_entry.custom_get(path=_path)
                data.append(single_data)
        return {
            "data": data
        }

    async def async_handle_put(service_call: ServiceCall) -> ServiceResponse:
        """Request update of recording sensor manually."""
        _gateway_entries = find_gateway_entry(hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID])
        if not _gateway_entries:
            return
        _path = service_call.data.get("path")
        _value = service_call.data.get(VALUE)
        if not _path or not _value:
            _LOGGER.error("Path or value not defined.")
            return
        data = []
        for _gateway_entry in _gateway_entries:
            return_value = await _gateway_entry.custom_put(path=_path, value=_value)
            data.append(return_value)
        return {
            "data": data
        }
        
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE,
        async_handle_thermostat_refresh,
        SERVICE_INTEGRATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        RECORDING_SERVICE_UPDATE,
        async_handle_recording_sensor_refresh,
        SERVICE_INTEGRATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET,
        async_handle_get,
        schema=SERVICE_GET_SCHEMA,
        supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PUT_STRING,
        async_handle_put,
        SERVICE_PUT_STRING_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PUT_FLOAT,
        async_handle_put,
        SERVICE_PUT_FLOAT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "fetch_recordings_sensor_range",
        async_handle_recording_sensor_fetch_past,
        SERVICE_FETCH_RANGE_SCHEMA,
    )


def async_remove_services(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Remove services."""
    hass.services.async_remove(DOMAIN, SERVICE_DEBUG)
    hass.services.async_remove(DOMAIN, SERVICE_UPDATE)
