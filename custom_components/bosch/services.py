"""Services used in HA."""
from __future__ import annotations
import logging
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
import homeassistant.helpers.config_validation as cv
from bosch_thermostat_client.const import RECORDING
from .const import (
    DOMAIN,
    SERVICE_DEBUG,
    SERVICE_UPDATE,
    UUID,
    BOSCH_GATEWAY_ENTRY,
    RECORDING_SERVICE_UPDATE,
    SERVICE_PUT,
    SERVICE_GET,
    VALUE,
)

from .sensor.recording import RecordingSensor

_LOGGER = logging.getLogger(__name__)

SERVICE_INTEGRATION_SCHEMA = vol.Schema({vol.Required(UUID): str})
SERVICE_GET_SCHEMA = SERVICE_INTEGRATION_SCHEMA.extend({vol.Required("path"): str})
SERVICE_FETCH_RANGE_SCHEMA = SERVICE_INTEGRATION_SCHEMA.extend(
    {vol.Required("day"): cv.date, vol.Required("statistic_id"): str}
)
SERVICE_PUT_SCHEMA = SERVICE_GET_SCHEMA.extend({vol.Required(VALUE): str})


def find_gateway_entry(hass: HomeAssistant, data: str) -> ConfigEntry | None:
    """Find gateway in config entries."""
    _gateway_entry = hass.data[DOMAIN].get(data)
    if _gateway_entry:
        return _gateway_entry
    _LOGGER.error("Could not find a Bosch device with UUID %s", data)


def async_register_debug_service(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register services."""

    async def async_handle_debug_service(service_call: ServiceCall):
        """Make bosch scan for debug purposes of thermostat."""
        filename = hass.config.path("www/bosch_scan.json")
        _gateway_entry = find_gateway_entry(hass=hass, data=service_call.data.get(UUID))
        if not _gateway_entry:
            return
        await _gateway_entry[BOSCH_GATEWAY_ENTRY].make_rawscan(filename)

    hass.services.async_register(
        DOMAIN,
        SERVICE_DEBUG,
        async_handle_debug_service,
        schema=SERVICE_INTEGRATION_SCHEMA,
    )


def async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register services."""

    async def async_handle_thermostat_refresh(service_call: ServiceCall):
        """Request update of thermostat manually."""
        _gateway_entry = find_gateway_entry(hass=hass, data=service_call.data.get(UUID))
        if not _gateway_entry:
            return
        await _gateway_entry[BOSCH_GATEWAY_ENTRY].thermostat_refresh()

    async def async_handle_recording_sensor_refresh(service_call: ServiceCall):
        """Request update of recording sensor manually."""
        uuid = service_call.data.get(UUID)
        _gateway_entry = find_gateway_entry(hass=hass, data=uuid)
        if not _gateway_entry:
            return
        _LOGGER.debug("Performing sensor update on service request. UUID: %s", uuid)
        await _gateway_entry[BOSCH_GATEWAY_ENTRY].recording_sensors_update()

    async def async_handle_recording_sensor_fetch_past(service_call: ServiceCall):
        """Request update of recording sensor manually."""
        uuid = service_call.data.get(UUID)
        statistic_id = service_call.data.get("statistic_id")
        day = dt_util.start_of_local_day(service_call.data.get("day"))
        _gateway_entry = find_gateway_entry(hass=hass, data=uuid)
        if not _gateway_entry:
            return
        recording_entities: list[RecordingSensor] = _gateway_entry.get(RECORDING, [])
        for entity in recording_entities:
            if entity.enabled and entity.statistic_id == statistic_id:
                await entity.insert_statistics_range(start_time=day)
        _LOGGER.debug("Performing sensor update on service request. UUID: %s", uuid)
        await _gateway_entry[BOSCH_GATEWAY_ENTRY].recording_sensors_update()

    async def async_handle_get(service_call: ServiceCall):
        """Request update of recording sensor manually."""
        _gateway_entry = find_gateway_entry(hass=hass, data=service_call.data.get(UUID))
        if not _gateway_entry:
            return
        _path = service_call.data.get("path")
        if not _path:
            _LOGGER.error("Path or value not defined.")
            return
        return await _gateway_entry[BOSCH_GATEWAY_ENTRY].custom_get(path=_path)

    async def async_handle_put(service_call: ServiceCall):
        """Request update of recording sensor manually."""
        _gateway_entry = find_gateway_entry(hass=hass, data=service_call.data.get(UUID))
        if not _gateway_entry:
            return
        _path = service_call.data.get("path")
        _value = service_call.data.get(VALUE)
        if not _path or not _value:
            _LOGGER.error("Path or value not defined.")
            return
        await _gateway_entry[BOSCH_GATEWAY_ENTRY].custom_put(path=_path, value=_value)

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
        SERVICE_GET_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PUT,
        async_handle_put,
        SERVICE_PUT_SCHEMA,
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
