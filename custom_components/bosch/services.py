"""Services used in HA."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.config_validation as cv
from .const import (
    DOMAIN,
    SERVICE_DEBUG,
    SERVICE_UPDATE,
    BOSCH_GATEWAY_ENTRY,
    RECORDING_SERVICE_UPDATE,
    SERVICE_BACKFILL_ENVIRONMENT,
    SERVICE_PUT_STRING,
    SERVICE_PUT_FLOAT,
    SERVICE_GET,
    VALUE,
)

if TYPE_CHECKING:
    from .gateway import BoschGatewayEntry

_LOGGER = logging.getLogger(__name__)

SERVICE_INTEGRATION_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.ensure_list})
SERVICE_GET_SCHEMA = SERVICE_INTEGRATION_SCHEMA.extend({vol.Required("path"): str})
SERVICE_FETCH_RANGE_SCHEMA = SERVICE_INTEGRATION_SCHEMA.extend(
    {
        vol.Required("day"): cv.date,
        vol.Optional("end_date"): cv.date,
        vol.Required("statistic_id"): str,
    }
)
SERVICE_REPAIR_ENERGY_SCHEMA = SERVICE_INTEGRATION_SCHEMA.extend(
    {
        vol.Optional("days", default=7): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=30)
        ),
        vol.Optional("logical_attr", default="all"): vol.In(["ch", "hw", "all"]),
    }
)
SERVICE_CLEAR_ENERGY_SCHEMA = SERVICE_INTEGRATION_SCHEMA.extend(
    {
        vol.Required("statistic_id"): str,
        vol.Optional("reimport", default=False): cv.boolean,
    }
)
SERVICE_BACKFILL_ENVIRONMENT_SCHEMA = SERVICE_INTEGRATION_SCHEMA.extend(
    {
        vol.Required("start_date"): cv.date,
        vol.Required("end_date"): cv.date,
    }
)
SERVICE_PUT_STRING_SCHEMA = SERVICE_GET_SCHEMA.extend({vol.Required(VALUE): str})
SERVICE_PUT_FLOAT_SCHEMA = SERVICE_GET_SCHEMA.extend(
    {vol.Required(VALUE): vol.Or(int, float)}
)


def find_gateway_entry(
    hass: HomeAssistant, devices_id: list[str]
) -> list[BoschGatewayEntry]:
    """Find gateway in config entries."""
    config_entries = list[ConfigEntry]()
    registry = dr.async_get(hass)
    for target in devices_id:
        device = registry.async_get(target)
        if device:
            for entry_id in device.config_entries:
                entry = hass.config_entries.async_get_entry(entry_id)
                if entry and entry.domain == DOMAIN and entry not in config_entries:
                    config_entries.append(entry)
        else:
            _LOGGER.warning(f"Device '{target}' not found in device registry")
    bosch_gateway_entries = []
    for entry in hass.data[DOMAIN].values():
        for config_entry in config_entries:
            if entry[BOSCH_GATEWAY_ENTRY].device_id == config_entry.entry_id:
                bosch_gateway_entries.append(entry[BOSCH_GATEWAY_ENTRY])
    return bosch_gateway_entries


def async_register_debug_service(
    hass: HomeAssistant, entry: BoschGatewayEntry | ConfigEntry
) -> None:
    """Register services."""

    async def async_handle_debug_service(service_call: ServiceCall) -> ServiceResponse:
        """Make bosch scan for debug purposes of thermostat."""
        filename = hass.config.path("www/bosch_scan.json")
        _gateway_entries = find_gateway_entry(
            hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID]
        )
        if not _gateway_entries:
            return {}
        data: list[Any] = []
        for _gateway_entry in _gateway_entries:
            data.append(await _gateway_entry.make_rawscan(filename))
        return {"data": data}

    hass.services.async_register(
        DOMAIN,
        SERVICE_DEBUG,
        async_handle_debug_service,
        schema=SERVICE_INTEGRATION_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


def async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register services."""

    async def async_handle_thermostat_refresh(service_call: ServiceCall) -> None:
        """Request update of gateway manually."""
        _gateway_entries = find_gateway_entry(
            hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID]
        )
        if not _gateway_entries:
            return
        for _gateway_entry in _gateway_entries:
            if _gateway_entry.coordinator:
                await _gateway_entry.coordinator.async_request_refresh()

    async def async_handle_recording_sensor_refresh(service_call: ServiceCall) -> None:
        """Request update of recording sensor manually."""
        _gateway_entries = find_gateway_entry(
            hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID]
        )
        if not _gateway_entries:
            return
        for _gateway_entry in _gateway_entries:
            if _gateway_entry.coordinator:
                await _gateway_entry.coordinator.async_request_refresh()
                _LOGGER.debug(
                    "Performing sensor update on service request. UUID: %s",
                    _gateway_entry.uuid,
                )
                await _gateway_entry.coordinator.async_recording_sensors_update()

    async def async_handle_recording_sensor_fetch_past(service_call: ServiceCall) -> None:
        """Fetch one or more past recording days into statistics (max 30)."""
        statistic_id = service_call.data.get("statistic_id")
        start_date = service_call.data["day"]
        end_date = service_call.data.get("end_date") or start_date
        if end_date < start_date:
            _LOGGER.error("end_date must be on or after day")
            return
        span = (end_date - start_date).days + 1
        if span > 30:
            _LOGGER.error(
                "Range exceeds 30 days (%s); narrow day..end_date",
                span,
            )
            return
        _gateway_entries = find_gateway_entry(
            hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID]
        )
        if not _gateway_entries:
            return
        for _gateway_entry in _gateway_entries:
            if not _gateway_entry.coordinator:
                continue
            for entity in _gateway_entry.coordinator.recording_entities:
                if not entity.enabled or entity.statistic_id != statistic_id:
                    continue
                current = start_date
                while current <= end_date:
                    day = dt_util.start_of_local_day(
                        datetime.combine(current, datetime.min.time())
                    )
                    _LOGGER.debug(
                        "Fetching day by service request. UUID: %s, statistic_id: %s, day: %s",
                        _gateway_entry.uuid,
                        statistic_id,
                        day,
                    )
                    await entity.insert_statistics_range(start_time=day)
                    current += timedelta(days=1)

    async def async_handle_get(service_call: ServiceCall) -> ServiceResponse:
        """Request update of recording sensor manually."""
        _gateway_entries = find_gateway_entry(
            hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID]
        )
        _path = service_call.data.get("path")
        if not _path:
            _LOGGER.error("Path or value not defined.")
            return {"data": ""}

        if not _gateway_entries:
            return {"data": ""}

        data: list[Any] = []
        for _gateway_entry in _gateway_entries:
            single_data = await _gateway_entry.custom_get(path=_path)
            data.append(single_data)
        return {"data": data}

    async def async_handle_put(service_call: ServiceCall) -> ServiceResponse:
        """Request update of recording sensor manually."""
        _gateway_entries = find_gateway_entry(
            hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID]
        )
        if not _gateway_entries:
            return {}
        _path = service_call.data.get("path")
        _value = service_call.data.get(VALUE)
        # 0 and 0.0 are valid values to write; a missing value or an empty
        # string is not.
        if not _path or _value is None or _value == "":
            _LOGGER.error("Path or value not defined.")
            return {}
        data: list[Any] = []
        for _gateway_entry in _gateway_entries:
            await _gateway_entry.custom_put(path=_path, value=_value)
            data.append({"path": _path, "value": _value})
        return {"data": data}
        
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

    async def async_handle_repair_energy(service_call: ServiceCall) -> None:
        """Repair recent EasyControl energy statistics for enabled entities."""
        from .sensor.energy import EnergySensor
        from .statistics_repair import repair_energy_statistics_window

        days = service_call.data.get("days", 7)
        logical = str(service_call.data.get("logical_attr", "all")).upper()
        _gateway_entries = find_gateway_entry(
            hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID]
        )
        for _gateway_entry in _gateway_entries:
            if not _gateway_entry.coordinator:
                continue
            for entity in _gateway_entry.coordinator.recording_entities:
                if not entity.enabled or not isinstance(entity, EnergySensor):
                    continue
                if not entity._uses_external_statistics:
                    continue
                attr = entity._read_attr_to_search
                if logical != "ALL" and attr != logical:
                    continue
                await repair_energy_statistics_window(entity, days=days)

    async def async_handle_clear_energy(service_call: ServiceCall) -> None:
        """Clear one energy statistic series; optionally reimport all history."""
        from .sensor.energy import EnergySensor
        from .statistics_repair import clear_energy_statistics

        statistic_id = service_call.data.get("statistic_id")
        reimport = bool(service_call.data.get("reimport", False))
        _gateway_entries = find_gateway_entry(
            hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID]
        )
        for _gateway_entry in _gateway_entries:
            if not _gateway_entry.coordinator:
                continue
            for entity in _gateway_entry.coordinator.recording_entities:
                if (
                    entity.enabled
                    and isinstance(entity, EnergySensor)
                    and entity.statistic_id == statistic_id
                ):
                    await clear_energy_statistics(entity, reimport=reimport)

    hass.services.async_register(
        DOMAIN,
        "repair_energy_statistics",
        async_handle_repair_energy,
        SERVICE_REPAIR_ENERGY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "clear_energy_statistics",
        async_handle_clear_energy,
        SERVICE_CLEAR_ENERGY_SCHEMA,
    )

    async def async_handle_backfill_environment(service_call: ServiceCall) -> None:
        """Backfill derived environment and HDH from existing recording stats."""
        from .degree_hours import async_backfill_hdh
        from .environment_energy import async_backfill_environment

        start_date = service_call.data["start_date"]
        end_date = service_call.data["end_date"]
        _gateway_entries = find_gateway_entry(
            hass=hass, devices_id=service_call.data[ATTR_DEVICE_ID]
        )
        if not _gateway_entries:
            return
        # Statistic ids are shared; one backfill covers the gateway recording series.
        await async_backfill_environment(
            hass, start_date=start_date, end_date=end_date
        )
        await async_backfill_hdh(hass, start_date=start_date, end_date=end_date)

    hass.services.async_register(
        DOMAIN,
        SERVICE_BACKFILL_ENVIRONMENT,
        async_handle_backfill_environment,
        SERVICE_BACKFILL_ENVIRONMENT_SCHEMA,
    )


def async_remove_services(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Remove the services once the last gateway is unloaded.

    The services are shared by all gateways, so unloading one gateway must
    not take them away from the others.
    """
    if hass.data.get(DOMAIN):
        return
    for service in (
        SERVICE_DEBUG,
        SERVICE_UPDATE,
        RECORDING_SERVICE_UPDATE,
        SERVICE_GET,
        SERVICE_PUT_STRING,
        SERVICE_PUT_FLOAT,
        "fetch_recordings_sensor_range",
        "repair_energy_statistics",
        "clear_energy_statistics",
        SERVICE_BACKFILL_ENVIRONMENT,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
