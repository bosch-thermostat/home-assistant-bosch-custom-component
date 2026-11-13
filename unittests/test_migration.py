"""Config entry migration, one fixture per starting point.

The three entries below are the three ways a `bosch` config entry can reach
this integration (issue #592):

  * version 1, XMPP/HTTP  - written by this integration before VERSION moved
  * version 1, POINTTAPI  - written by an early ha_bosch
  * version 11, POINTTAPI - written by current ha_bosch

The one that matters most is the first. Every step in the chain is guarded on
the POINTTAPI protocol, so an XMPP entry has to come out the other side at the
current version with its registries untouched. Before those guards existed, the
10 -> 11 step created an empty "Heating Zone" device under every gateway.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.bosch.config_flow import BoschFlowHandler
from custom_components.bosch.const import CONF_PROTOCOL, POINTTAPI, UUID
from custom_components.bosch.migration import async_migrate_entry

CURRENT_VERSION = BoschFlowHandler.VERSION

XMPP_V1 = {CONF_PROTOCOL: "xmpp", UUID: "aabbccddeeff", "address": "10.0.0.5"}
POINTTAPI_V1 = {
    CONF_PROTOCOL: POINTTAPI,
    UUID: "101171114",
    "access_token": "redacted",
    "refresh_token": "redacted",
    "device_id": "101171114",
}
POINTTAPI_V11 = dict(POINTTAPI_V1)


def _entry(data: dict, version: int) -> SimpleNamespace:
    return SimpleNamespace(data=dict(data), version=version, entry_id="entry1")


def _hass(entry: SimpleNamespace) -> MagicMock:
    """A hass whose async_update_entry really moves the entry's version."""
    hass = MagicMock()

    def _update(target, **kwargs):
        if "version" in kwargs:
            target.version = kwargs["version"]

    hass.config_entries.async_update_entry = MagicMock(side_effect=_update)
    return hass


@pytest.fixture
def registries():
    """Patch both registries, so any write attempt is visible to the test."""
    device_registry = MagicMock()
    device_registry.devices.values.return_value = []
    device_registry.async_get_device.return_value = None
    device_registry.async_get_device_by_identifier.return_value = None
    entity_registry = MagicMock()
    entity_registry.entities.values.return_value = []
    with patch(
        "custom_components.bosch.migration.dr.async_get",
        return_value=device_registry,
    ), patch(
        "homeassistant.helpers.entity_registry.async_get",
        return_value=entity_registry,
    ):
        yield SimpleNamespace(device=device_registry, entity=entity_registry)


@pytest.mark.asyncio
async def test_xmpp_v1_reaches_current_version_without_touching_registries(registries):
    """The case this chain must not break: an entry this repo wrote itself."""
    entry = _entry(XMPP_V1, 1)
    assert await async_migrate_entry(_hass(entry), entry) is True
    assert entry.version == CURRENT_VERSION
    registries.device.async_get_or_create.assert_not_called()
    registries.entity.async_update_entity.assert_not_called()
    registries.entity.async_remove.assert_not_called()


@pytest.mark.asyncio
async def test_xmpp_v1_keeps_entry_data_untouched(registries):
    """No step may rewrite entry.data; credentials must keep their shape."""
    entry = _entry(XMPP_V1, 1)
    await async_migrate_entry(_hass(entry), entry)
    assert entry.data == XMPP_V1


@pytest.mark.asyncio
async def test_pointtapi_v1_reaches_current_version(registries):
    """An early ha_bosch entry runs the chain and lands on the current version."""
    entry = _entry(POINTTAPI_V1, 1)
    assert await async_migrate_entry(_hass(entry), entry) is True
    assert entry.version == CURRENT_VERSION
    assert entry.data == POINTTAPI_V1


@pytest.mark.asyncio
async def test_pointtapi_v11_is_a_bump_only(registries):
    """11 -> 12 is reserved for convergence work and currently does nothing."""
    entry = _entry(POINTTAPI_V11, 11)
    hass = _hass(entry)
    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == CURRENT_VERSION
    registries.device.async_get_or_create.assert_not_called()
    registries.entity.async_update_entity.assert_not_called()
    registries.entity.async_remove.assert_not_called()
    assert hass.config_entries.async_update_entry.call_count == 1


@pytest.mark.asyncio
async def test_already_current_is_a_noop(registries):
    """An entry already at the current version short-circuits."""
    entry = _entry(POINTTAPI_V1, CURRENT_VERSION)
    hass = _hass(entry)
    assert await async_migrate_entry(hass, entry) is True
    hass.config_entries.async_update_entry.assert_not_called()
