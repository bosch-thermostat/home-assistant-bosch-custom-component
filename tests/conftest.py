"""Fixtures: a real Home Assistant with the gateway replayed from a rawscan."""
from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

from custom_components.bosch.const import (
    ACCESS_KEY,
    ACCESS_TOKEN,
    CONF_DEVICE_TYPE,
    CONF_PROTOCOL,
    DOMAIN,
    UUID,
)
from tests.simulator import GatewaySimulator, load_rawscan, simulate

# The rawscan masks /gateway/uuid as "-1", which is what the client reports.
SCAN_UUID = "-1"


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """HA's snapshot extension (tests/snapshots/).

    Defined here so it doesn't depend on whether syrupy's or the HA plugin's
    `snapshot` fixture is registered last, which varies with install order.
    """
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def entity_registry_enabled_by_default() -> Iterator[None]:
    """Enable all entities, including the ones disabled by default."""
    with patch.object(
        Entity,
        "entity_registry_enabled_default",
        new_callable=PropertyMock,
        return_value=True,
    ):
        yield


@pytest.fixture
def rawscan_name() -> str:
    """Rawscan under tests/fixtures/rawscans/ used by the simulator."""
    return "easycontrol_ct200"


@pytest.fixture
async def scan_time_zone(hass: HomeAssistant, freezer):
    """Put HA on the day after the scan so 'yesterday' has energy data."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-09-22T09:30:00+02:00")


@pytest.fixture
def simulator(rawscan_name: str, scan_time_zone) -> Iterator[GatewaySimulator]:
    _, rawscan = load_rawscan(rawscan_name)
    with simulate(rawscan) as sim:
        yield sim


@pytest.fixture
def config_entry(rawscan_name: str) -> MockConfigEntry:
    meta, _ = load_rawscan(rawscan_name)
    return MockConfigEntry(
        domain=DOMAIN,
        title="Bosch",
        data={
            CONF_ADDRESS: "101000000",
            UUID: SCAN_UUID,
            ACCESS_KEY: "0123456789abcdef" * 4,
            ACCESS_TOKEN: "abcdefghijklmnop",
            CONF_DEVICE_TYPE: meta["device_type"],
            CONF_PROTOCOL: meta["protocol"],
        },
    )


@pytest.fixture
async def setup_integration(hass, simulator, config_entry):
    """Set up the entry against the simulator; unload it while still simulated."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    yield config_entry
    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
