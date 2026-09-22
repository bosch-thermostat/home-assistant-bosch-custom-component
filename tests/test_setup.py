"""Integration setup against a gateway replayed from captured rawscans."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest
from bosch_thermostat_client.exceptions import DeviceConnectionError
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.json import JSONEncoder
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from syrupy.assertion import SnapshotAssertion

from custom_components.bosch.const import BOSCH_GATEWAY_ENTRY, DOMAIN
from tests.conftest import SCAN_UUID
from tests.simulator import rawscan_names

# attributes whose value depends on the HA release, not on this integration
UNSTABLE_ATTRIBUTES = {"friendly_name"}


@pytest.mark.parametrize("rawscan_name", rawscan_names())
async def test_entities(
    hass, entity_registry_enabled_by_default, setup_integration, snapshot: SnapshotAssertion
):
    """Every entity built from the rawscan, keyed by unique_id."""
    registry = er.async_get(hass)
    entities = {}
    for entry in er.async_entries_for_config_entry(registry, setup_integration.entry_id):
        state = hass.states.get(entry.entity_id)
        entities[entry.unique_id] = {
            "domain": entry.domain,
            "state": state.state if state else None,
            # plain JSON values: enum/flag reprs differ between Python releases
            "attributes": json.loads(
                json.dumps(
                    {
                        key: value
                        for key, value in (state.attributes.items() if state else ())
                        if key not in UNSTABLE_ATTRIBUTES
                    },
                    cls=JSONEncoder,
                    sort_keys=True,
                )
            ),
        }
    assert dict(sorted(entities.items())) == snapshot


async def test_devices(hass, setup_integration):
    """Child devices hang off the gateway device via via_device_id."""
    registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(registry, setup_integration.entry_id)
    gateway = registry.async_get_device_by_identifier((DOMAIN, SCAN_UUID), setup_integration.entry_id)
    assert gateway is not None
    children = [device for device in devices if device.id != gateway.id]
    assert children
    for device in children:
        assert device.via_device_id == gateway.id
        ((domain, identifier),) = device.identifiers
        assert domain == DOMAIN and identifier.startswith(f"{SCAN_UUID}_")


async def test_energy_reads_yesterday(hass, entity_registry_enabled_by_default, setup_integration):
    """Energy sensors are updated with the current time (the day before is reported)."""
    state = hass.states.get("sensor.energy_sensors_energy_central_heating")
    assert state is not None
    assert float(state.state) == 129.17  # gCh of 21-09-2026 in the scan


async def test_polling(hass, entity_registry_enabled_by_default, setup_integration, simulator):
    """Enabled entities are polled every scan interval; energy stays hourly."""
    simulator.requests.clear()
    async_fire_time_changed(hass, hass_now(hass) + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert "/system/sensors/temperatures/outdoor_t1" in simulator.requests
    assert not [path for path in simulator.requests if path.startswith("/energy")]


async def test_polling_only_enabled_entities(hass, setup_integration, simulator):
    """Objects of entities disabled by default are not polled."""
    simulator.requests.clear()
    async_fire_time_changed(hass, hass_now(hass) + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert "/system/sensors/temperatures/outdoor_t1" not in simulator.requests
    assert simulator.requests  # climate/water heater are enabled by default


async def test_firmware_check(hass, setup_integration, simulator):
    """Firmware validity is checked again every 4 hours."""
    simulator.requests.clear()
    async_fire_time_changed(hass, hass_now(hass) + timedelta(hours=4, seconds=1))
    await hass.async_block_till_done()
    assert "/gateway/versionFirmware" in simulator.requests


async def test_unreachable_gateway_marks_entities_unavailable(
    hass, entity_registry_enabled_by_default, setup_integration, simulator
):
    """A DeviceConnectionError during a refresh raises UpdateFailed.

    The client absorbs an ordinary DeviceException inside update() (one
    missing endpoint must not fail the refresh) and re-raises only
    DeviceConnectionError, which means the gateway itself is unreachable.
    ``async_refresh`` is the call the scheduled update makes.
    """
    coordinator = hass.data[DOMAIN][SCAN_UUID][BOSCH_GATEWAY_ENTRY].coordinator
    entity_id = "sensor.bosch_sensors_outdoor_temperature"
    assert hass.states.get(entity_id).state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)

    simulator.unreachable = True
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # and it recovers once the gateway answers again
    simulator.unreachable = False
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert hass.states.get(entity_id).state != STATE_UNAVAILABLE


async def test_missing_endpoint_does_not_fail_the_refresh(
    hass, entity_registry_enabled_by_default, setup_integration, simulator
):
    """An ordinary DeviceException must not take every entity unavailable.

    Only a gateway that cannot be reached at all does that; a single absent
    endpoint is normal on these devices.
    """
    coordinator = hass.data[DOMAIN][SCAN_UUID][BOSCH_GATEWAY_ENTRY].coordinator
    entity_id = "sensor.bosch_sensors_outdoor_temperature"

    simulator.offline = True  # plain DeviceException on every get
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert hass.states.get(entity_id).state != STATE_UNAVAILABLE


async def test_one_timing_out_path_does_not_fail_the_refresh(
    hass, entity_registry_enabled_by_default, setup_integration, simulator
):
    """One path timing out while the rest answer keeps every entity available.

    On XMPP a DeviceConnectionError also means a single request timed out
    twice, and some paths time out on some models every time. Only a gateway
    where every polled object reports it is unreachable, so repeated refreshes
    with one permanently timing-out path must all succeed.
    """
    coordinator = hass.data[DOMAIN][SCAN_UUID][BOSCH_GATEWAY_ENTRY].coordinator
    timing_out = "/system/sensors/temperatures/outdoor_t1"
    simulator.timeout_paths = {timing_out}
    entity_ids = [
        entry.entity_id
        for entry in er.async_entries_for_config_entry(
            er.async_get(hass), setup_integration.entry_id
        )
    ]
    assert entity_ids

    for _ in range(3):
        simulator.requests.clear()
        await coordinator.async_refresh()
        assert timing_out in simulator.requests
        assert len(set(simulator.requests)) > 1  # the rest were polled and answered
        assert coordinator.last_update_success
        assert [
            entity_id
            for entity_id in entity_ids
            if hass.states.get(entity_id).state == STATE_UNAVAILABLE
        ] == []


async def test_every_polled_object_reports_an_unreachable_gateway(
    hass, entity_registry_enabled_by_default, setup_integration, simulator
):
    """Every object the coordinator polls re-raises DeviceConnectionError.

    The coordinator raises UpdateFailed only when every object reports it, so
    a single object that swallowed the error would keep an unreachable gateway
    from ever being noticed: sensors, circuits and the four switch types each
    have their own ``update()`` implementation in the client. A plain
    DeviceException must still be absorbed by all of them.
    """
    coordinator = hass.data[DOMAIN][SCAN_UUID][BOSCH_GATEWAY_ENTRY].coordinator
    objects = list(coordinator._objects.values())
    assert objects

    simulator.unreachable = True
    raised = []
    for obj in objects:
        try:
            await obj.update()
        except DeviceConnectionError:
            raised.append(obj)
    assert len(raised) == len(objects), (
        "these did not re-raise: "
        f"{sorted({type(o).__name__ for o in objects} - {type(o).__name__ for o in raised})}"
    )

    simulator.unreachable = False
    simulator.offline = True  # a 404-style DeviceException
    for obj in objects:
        await obj.update()  # must not raise


async def test_stop_closes_connection_once(hass, setup_integration, simulator):
    """HA stop closes the connection; the later unload does not close it again."""
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert simulator.closed == 1
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    assert simulator.closed == 1


async def test_failed_setup_closes_connection(hass, simulator, config_entry):
    """A setup that fails (and is retried) does not leak the connection."""
    simulator.offline = True
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state.name == "SETUP_RETRY"
    assert simulator.closed == 1
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_services(hass, setup_integration):
    assert hass.services.has_service(DOMAIN, "update_thermostat")
    assert hass.services.has_service(DOMAIN, "debug_scan")
    assert not hass.services.has_service(DOMAIN, "move_old_statistic_data")


def hass_now(hass):
    return dt_util.utcnow()
