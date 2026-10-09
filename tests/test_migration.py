"""Legacy (DOMAIN, id, uuid) device identifiers are migrated at setup."""
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.bosch.const import DOMAIN
from tests.conftest import SCAN_UUID

ZONE = "zn1"
# BoschClimateWaterEntity: f"{uuid}{bosch_object.id}"
CLIMATE_UNIQUE_ID = f"{SCAN_UUID}{ZONE}"


async def _setup(hass, config_entry):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_legacy_identifiers_migrated(hass, simulator, config_entry):
    config_entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    legacy = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, ZONE, SCAN_UUID)},
    )
    await _setup(hass, config_entry)

    device = registry.async_get(legacy.id)
    assert device.identifiers == {(DOMAIN, f"{SCAN_UUID}_{ZONE}")}
    # the zone's climate entity kept the migrated device (same device id)
    assert registry.async_get_devices(
        identifiers={(DOMAIN, f"{SCAN_UUID}_{ZONE}")},
        config_entry_id=config_entry.entry_id,
    ) == [device]
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_identifier_collision_keeps_entity_id(hass, simulator, config_entry):
    """If the new identifier exists already (ha_bosch, downgrade), drop the duplicate.

    The legacy device holds the zone's climate entity here, which is the case
    users notice: the device is removed, but HA restores the entity's entity_id
    from its deleted-entity record, so its history carries on.
    """
    config_entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    legacy = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, ZONE, SCAN_UUID)},
    )
    climate = entity_registry.async_get_or_create(
        "climate",
        DOMAIN,
        CLIMATE_UNIQUE_ID,
        config_entry=config_entry,
        device_id=legacy.id,
        suggested_object_id="bosch_zone_legacy",
    )
    assert climate.entity_id == "climate.bosch_zone_legacy"
    current = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, f"{SCAN_UUID}_{ZONE}")},
    )
    await _setup(hass, config_entry)

    assert config_entry.state.name == "LOADED"
    assert registry.async_get(legacy.id) is None
    assert registry.async_get(current.id) is not None

    # the climate entity survived the removal, under the device that was kept
    migrated = entity_registry.async_get_entity_id(
        "climate", DOMAIN, CLIMATE_UNIQUE_ID
    )
    assert migrated == "climate.bosch_zone_legacy"
    assert entity_registry.async_get(migrated).device_id == current.id
    assert hass.states.get(migrated) is not None
    await hass.config_entries.async_unload(config_entry.entry_id)
