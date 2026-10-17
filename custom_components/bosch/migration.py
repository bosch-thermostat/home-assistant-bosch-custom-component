"""Config entry migration.

The chain exists so that a config entry written by the ha_bosch fork
(https://github.com/CaseyRo/ha_bosch), which reached entry version 11, loads
here without the user removing and re-adding the integration. See issue #592.

Every step below is guarded on ``entry.data[CONF_PROTOCOL] == POINTTAPI``.
Entries created by this integration are XMPP/HTTP, so they fall through all ten
steps untouched and land on the current version as a plain bump. Nothing in the
chain reads or writes anything but the entity and device registries; no step
touches ``entry.data``, so stored credentials keep their shape.

``11 -> 12`` is deliberately a bump with no work. It is reserved for whatever
the convergence itself has to change, for example aligning unique_ids or device
identifiers between the two codebases. If that step ever does real work, the
final ha_bosch release has to perform the identical work before declaring 12,
otherwise an entry ha_bosch bumped to 12 would skip it and be accepted here as
already migrated. Until that is decided, ha_bosch stays at 11.

Later non-breaking changes should move ``MINOR_VERSION`` in config_flow.py, so
the major version only moves when something genuinely breaks.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_PROTOCOL, DOMAIN, POINTTAPI, UUID

_LOGGER = logging.getLogger(__name__)


def _device_by_identifier(
    device_registry: dr.DeviceRegistry, identifier: tuple[str, str], config_entry_id: str
) -> dr.DeviceEntry | None:
    """Find one of this entry's devices on either side of HA 2026.9.

    2026.9 deprecated ``async_get_device`` (it breaks in 2027.8) in favour of
    ``async_get_device_by_identifier``, which older releases don't have.
    """
    if hasattr(dr.DeviceRegistry, "async_get_device_by_identifier"):
        return device_registry.async_get_device_by_identifier(identifier, config_entry_id)
    return device_registry.async_get_device(identifiers={identifier})


def _via_device_kwargs(
    device_registry: dr.DeviceRegistry, parent_device: Any, uuid: str
) -> dict[str, Any]:
    """Link a child device to the gateway on either side of HA 2026.8.

    2026.8 added ``via_device_id`` and deprecated ``via_device``; older
    releases reject ``via_device_id`` with a TypeError.
    """
    if parent_device is None:
        return {}
    if "via_device_id" in inspect.signature(
        device_registry.async_get_or_create
    ).parameters:
        return {"via_device_id": parent_device.id}
    return {"via_device": (DOMAIN, uuid)}


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate POINTTAPI entry versions.

    Every step only touches POINTTAPI entries; XMPP/HTTP entries (including
    ones arriving from upstream at version 1) pass through as version bumps.

        - v1 -> v2: entity_id renames (device-partition scheme)
        - v2 -> v3: unique_id rename for boost switch (per-zone unique_id)
        - v3 -> v4: remove stale per-zone Boost registry entries so HA recreates
            them with the corrected entity name
        - v4 -> v5: clear custom Boost switch names so HA uses translations
        - v5 -> v6: move the regular thermostat child-lock switch to zone 1
        - v6 -> v7: clear all legacy and current Boost switch registry names
        - v7 -> v8: refresh Boost entity naming metadata
        - v8 -> v9: remove obsolete POINTTAPI Boost switch entities
        - v9 -> v10: move away-mode switch to heating installation settings
        - v10 -> v11: move thermostat-specific gateway switches to zone 1
        - v11 -> v12: reserved for convergence changes; currently a bump only
    """
    if entry.version >= 12:
        return True

    if entry.version < 2:
        if entry.data.get(CONF_PROTOCOL) == POINTTAPI:
            from homeassistant.helpers import entity_registry as er
            registry = er.async_get(hass)
            renames = {
                # solar_solar_* doubled prefix cleanup
                "sensor.solar_solar_collector_temperature": "sensor.solar_collector_temperature",
                "sensor.solar_solar_storage_temperature": "sensor.solar_storage_temperature",
                "sensor.solar_solar_pump_modulation": "sensor.solar_pump_modulation",
                "sensor.solar_total_solar_gain": "sensor.solar_total_gain",
                # water_heater rename
                "water_heater.water_heater": "water_heater.hot_water_tank",
            }
            renamed = 0
            for old_id, new_id in renames.items():
                try:
                    if registry.async_get(old_id) and not registry.async_get(new_id):
                        registry.async_update_entity(old_id, new_entity_id=new_id)
                        renamed += 1
                except Exception as err:  # noqa: BLE001 - best-effort registry migration; one bad entity must not abort setup
                    _LOGGER.warning(
                        "Migration could not rename %s -> %s: %s", old_id, new_id, err
                    )
            _LOGGER.info(
                "Migrated POINTTAPI entry from version 1 to 2 (%d entity_ids renamed)",
                renamed,
            )
        hass.config_entries.async_update_entry(entry, version=2)

    if entry.version < 3:
        if entry.data.get(CONF_PROTOCOL) == POINTTAPI:
            from homeassistant.helpers import entity_registry as er
            registry = er.async_get(hass)
            old_unique_id = f"{entry.entry_id}_pointtapi_boost"
            new_unique_id = f"{entry.entry_id}_pointtapi_boost_zone_1"
            try:
                entity_id = registry.async_get_entity_id("switch", DOMAIN, old_unique_id)
                if entity_id:
                    registry.async_update_entity(entity_id, new_unique_id=new_unique_id)
                    _LOGGER.info(
                        "Migrated POINTTAPI boost switch unique_id %s -> %s for entity %s",
                        old_unique_id, new_unique_id, entity_id,
                    )
            except Exception as err:  # noqa: BLE001 - best-effort registry migration; one bad entity must not abort setup
                _LOGGER.warning(
                    "Migration could not update unique_id %s: %s", old_unique_id, err
                )
        hass.config_entries.async_update_entry(entry, version=3)

    if entry.version < 4:
        if entry.data.get(CONF_PROTOCOL) == POINTTAPI:
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(hass)
            prefix = f"{entry.entry_id}_pointtapi_boost_zone_"
            removed = 0
            for entity in list(registry.entities.values()):
                if (
                    entity.config_entry_id == entry.entry_id
                    and entity.domain == "switch"
                    and entity.unique_id.startswith(prefix)
                ):
                    try:
                        registry.async_remove(entity.entity_id)
                        removed += 1
                    except Exception as err:  # noqa: BLE001 - best-effort registry migration; one bad entity must not abort setup
                        _LOGGER.warning(
                            "Migration could not remove stale Boost entity %s: %s",
                            entity.entity_id,
                            err,
                        )
            _LOGGER.info(
                "Migrated POINTTAPI entry from version 3 to 4 (%d stale Boost entities removed)",
                removed,
            )
        hass.config_entries.async_update_entry(entry, version=4)

    if entry.version < 5:
        if entry.data.get(CONF_PROTOCOL) == POINTTAPI:
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(hass)
            prefix = f"{entry.entry_id}_pointtapi_boost_zone_"
            cleared = 0
            for entity in list(registry.entities.values()):
                if (
                    entity.config_entry_id == entry.entry_id
                    and entity.domain == "switch"
                    and entity.unique_id.startswith(prefix)
                    and (
                        getattr(entity, "name", None) is not None
                        or getattr(entity, "original_name", None) is not None
                    )
                ):
                    try:
                        registry.async_update_entity(
                            entity.entity_id,
                            name=None,
                            original_name=None,
                        )
                        cleared += 1
                    except Exception as err:  # noqa: BLE001 - best-effort registry migration; one bad entity must not abort setup
                        _LOGGER.warning(
                            "Migration could not clear Boost entity name %s: %s",
                            entity.entity_id,
                            err,
                        )
            _LOGGER.info(
                "Migrated POINTTAPI entry from version 4 to 5 (%d Boost names cleared)",
                cleared,
            )
        hass.config_entries.async_update_entry(entry, version=5)

    if entry.version < 6:
        if entry.data.get(CONF_PROTOCOL) == POINTTAPI:
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(hass)
            device_registry = dr.async_get(hass)
            uuid = entry.data.get(UUID)
            parent_device = _device_by_identifier(
                device_registry, (DOMAIN, uuid), entry.entry_id
            )
            zone_device_kwargs = {
                "config_entry_id": entry.entry_id,
                "identifiers": {(DOMAIN, f"{uuid}_zn1")},
                "name": "Heating Zone",
                "manufacturer": "Bosch",
            }
            zone_device_kwargs.update(
                _via_device_kwargs(device_registry, parent_device, uuid)
            )
            zone_device = device_registry.async_get_or_create(
                **zone_device_kwargs,
            )
            child_lock_suffix = (
                "_pointtapi_switch_devices_device1_thermostat_childLock_enabled"
            )
            moved = 0
            for entity in list(registry.entities.values()):
                if (
                    entity.config_entry_id == entry.entry_id
                    and entity.domain == "switch"
                    and entity.unique_id.endswith(child_lock_suffix)
                    and entity.device_id != zone_device.id
                ):
                    try:
                        registry.async_update_entity(
                            entity.entity_id,
                            device_id=zone_device.id,
                        )
                        moved += 1
                    except Exception as err:  # noqa: BLE001 - best-effort registry migration; one bad entity must not abort setup
                        _LOGGER.warning(
                            "Migration could not move child-lock entity %s: %s",
                            entity.entity_id,
                            err,
                        )
            _LOGGER.info(
                "Migrated POINTTAPI entry from version 5 to 6 (%d child-lock entities moved)",
                moved,
            )
        hass.config_entries.async_update_entry(entry, version=6)

    if entry.version < 7:
        if entry.data.get(CONF_PROTOCOL) == POINTTAPI:
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(hass)
            prefix = f"{entry.entry_id}_pointtapi_boost"
            cleared = 0
            for entity in list(registry.entities.values()):
                if (
                    entity.config_entry_id == entry.entry_id
                    and entity.domain == "switch"
                    and entity.unique_id.startswith(prefix)
                    and (
                        getattr(entity, "name", None) is not None
                        or getattr(entity, "original_name", None) is not None
                    )
                ):
                    try:
                        registry.async_update_entity(
                            entity.entity_id,
                            name=None,
                            original_name=None,
                        )
                        cleared += 1
                    except Exception as err:  # noqa: BLE001 - best-effort registry migration; one bad entity must not abort setup
                        _LOGGER.warning(
                            "Migration could not clear legacy Boost name %s: %s",
                            entity.entity_id,
                            err,
                        )
            _LOGGER.info(
                "Migrated POINTTAPI entry from version 6 to 7 (%d Boost names cleared)",
                cleared,
            )
        hass.config_entries.async_update_entry(entry, version=7)

    if entry.version < 8:
        if entry.data.get(CONF_PROTOCOL) == POINTTAPI:
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(hass)
            prefix = f"{entry.entry_id}_pointtapi_boost"
            cleared = 0
            for entity in list(registry.entities.values()):
                if (
                    entity.config_entry_id == entry.entry_id
                    and entity.domain == "switch"
                    and entity.unique_id.startswith(prefix)
                ):
                    try:
                        registry.async_update_entity(
                            entity.entity_id,
                            name=None,
                            original_name=None,
                        )
                        cleared += 1
                    except Exception as err:  # noqa: BLE001 - best-effort registry migration; one bad entity must not abort setup
                        _LOGGER.warning(
                            "Migration could not refresh Boost name %s: %s",
                            entity.entity_id,
                            err,
                        )
            _LOGGER.info(
                "Migrated POINTTAPI entry from version 7 to 8 (%d Boost names refreshed)",
                cleared,
            )
        hass.config_entries.async_update_entry(entry, version=8)

    if entry.version < 9:
        if entry.data.get(CONF_PROTOCOL) == POINTTAPI:
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(hass)
            prefix = f"{entry.entry_id}_pointtapi_boost"
            removed = 0
            for entity in list(registry.entities.values()):
                if (
                    entity.config_entry_id == entry.entry_id
                    and entity.domain == "switch"
                    and entity.unique_id.startswith(prefix)
                ):
                    try:
                        registry.async_remove(entity.entity_id)
                        removed += 1
                    except Exception as err:  # noqa: BLE001 - best-effort registry migration; one bad entity must not abort setup
                        _LOGGER.warning(
                            "Migration could not remove obsolete Boost switch %s: %s",
                            entity.entity_id,
                            err,
                        )
            _LOGGER.info(
                "Migrated POINTTAPI entry from version 8 to 9 (%d obsolete Boost switches removed)",
                removed,
            )
        hass.config_entries.async_update_entry(entry, version=9)

    if entry.version < 10:
        if entry.data.get(CONF_PROTOCOL) == POINTTAPI:
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(hass)
            away_unique_id = (
                f"{entry.entry_id}_pointtapi_switch_system_awayMode_enabled"
            )
            away_entity_id = registry.async_get_entity_id(
                "switch", DOMAIN, away_unique_id
            )
            if away_entity_id:
                device_registry = dr.async_get(hass)
                uuid = entry.data.get(UUID)
                parent_device = _device_by_identifier(
                    device_registry, (DOMAIN, uuid), entry.entry_id
                )
                device_kwargs = {
                    "config_entry_id": entry.entry_id,
                    "identifiers": {(DOMAIN, f"{uuid}_heating_installation_hc1")},
                    "name": "Heating Installation Settings",
                    "manufacturer": "Bosch",
                    "model": "EasyControl",
                }
                device_kwargs.update(
                    _via_device_kwargs(device_registry, parent_device, uuid)
                )
                installation_device = device_registry.async_get_or_create(
                    **device_kwargs,
                )
                try:
                    registry.async_update_entity(
                        away_entity_id,
                        device_id=installation_device.id,
                    )
                except Exception as err:  # noqa: BLE001 - best-effort registry migration; one bad entity must not abort setup
                    _LOGGER.warning(
                        "Migration could not move away-mode entity %s: %s",
                        away_entity_id,
                        err,
                    )
        hass.config_entries.async_update_entry(entry, version=10)

    if entry.version < 11:
        if entry.data.get(CONF_PROTOCOL) == POINTTAPI:
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(hass)
            device_registry = dr.async_get(hass)
            uuid = entry.data.get(UUID)
            parent_device = _device_by_identifier(
                device_registry, (DOMAIN, uuid), entry.entry_id
            )
            device_kwargs = {
                "config_entry_id": entry.entry_id,
                "identifiers": {(DOMAIN, f"{uuid}_zn1")},
                "name": "Heating Zone",
                "manufacturer": "Bosch",
                "model": "EasyControl",
            }
            device_kwargs.update(
                _via_device_kwargs(device_registry, parent_device, uuid)
            )
            zone_device = device_registry.async_get_or_create(**device_kwargs)
            suffixes = (
                "_pointtapi_switch_gateway_pirSensitivity",
                "_pointtapi_switch_gateway_notificationLight_enabled",
            )
            for entity in list(registry.entities.values()):
                if (
                    entity.config_entry_id == entry.entry_id
                    and entity.domain == "switch"
                    and entity.unique_id.endswith(suffixes)
                ):
                    try:
                        registry.async_update_entity(
                            entity.entity_id,
                            device_id=zone_device.id,
                        )
                    except Exception as err:  # noqa: BLE001 - best-effort registry migration; one bad entity must not abort setup
                        _LOGGER.warning(
                            "Migration could not move thermostat switch %s: %s",
                            entity.entity_id,
                            err,
                        )
        hass.config_entries.async_update_entry(entry, version=11)

    if entry.version < 12:
        # Reserved for convergence changes. See the module docstring before
        # putting real work here.
        hass.config_entries.async_update_entry(entry, version=12)

    return True
