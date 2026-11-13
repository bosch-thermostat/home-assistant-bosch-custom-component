"""Setup must be retried when a slow gateway times out during startup.

Older HTTP gateways (KM200 and friends) regularly stall for a minute or more.
The client swallows the timeouts it hits while initializing, so the
integration only sees their effects:

  * the firmware request timed out  -> FirmwareException for firmware ``None``
  * a circuit request timed out     -> the circuit is missing from the gateway

Both used to end in a setup that Home Assistant never retries (or a setup
without the circuit's entities). Both must now raise ConfigEntryNotReady.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bosch_thermostat_client.exceptions import FirmwareException
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.bosch import gateway as gateway_module
from custom_components.bosch.gateway import BoschGatewayEntry

UUID = "955360973"


def _registry_entry(domain: str, circuit_id: str, disabled_by=None) -> SimpleNamespace:
    return SimpleNamespace(
        domain=domain, unique_id=f"{UUID}{circuit_id}", disabled_by=disabled_by
    )


def _entry(*, firmware="05.03.01", circuits=None, registered=()) -> BoschGatewayEntry:
    entry = BoschGatewayEntry.__new__(BoschGatewayEntry)
    entry.hass = SimpleNamespace(data={"bosch": {UUID: {}}}, config=MagicMock())
    entry.uuid = UUID
    entry._host = "192.0.2.10"
    entry.config_entry = SimpleNamespace(entry_id="entry1")
    entry.supported_platforms = []
    circuits = circuits if circuits is not None else {"hc": ["hc1"], "dhw": ["dhw1"]}
    entry.gateway = MagicMock(
        firmware=firmware,
        uuid=UUID,
        database={"db": True},
        circuit_types={"hc": "heatingCircuits", "dhw": "dhwCircuits"},
        get_capabilities=AsyncMock(return_value=[]),
        check_connection=AsyncMock(),
    )
    entry.gateway.get_circuits.side_effect = lambda ctype: [
        SimpleNamespace(id=cid) for cid in circuits.get(ctype, [])
    ]
    entry._registered = list(registered)
    return entry


async def _init(entry: BoschGatewayEntry) -> bool:
    with (
        patch.object(gateway_module.er, "async_get"),
        patch.object(
            gateway_module.er,
            "async_entries_for_config_entry",
            return_value=entry._registered,
        ),
        patch.object(gateway_module, "create_notification_firmware") as notify,
    ):
        entry._notify = notify
        return await entry.async_init_bosch()


async def test_firmware_timeout_is_retried() -> None:
    entry = _entry(firmware=None)
    entry.gateway.check_connection.side_effect = FirmwareException(
        "You might have unsupported firmware version None"
    )
    with pytest.raises(ConfigEntryNotReady):
        await _init(entry)
    entry._notify.assert_not_called()


async def test_unsupported_firmware_still_fails_with_notification() -> None:
    entry = _entry(firmware="99.99.99")
    entry.gateway.check_connection.side_effect = FirmwareException(
        "You might have unsupported firmware version 99.99.99"
    )
    assert await _init(entry) is False
    entry._notify.assert_called_once()


async def test_missing_known_circuit_is_retried() -> None:
    entry = _entry(
        circuits={"hc": [], "dhw": ["dhw1"]},
        registered=[
            _registry_entry("climate", "hc1"),
            _registry_entry("water_heater", "dhw1"),
        ],
    )
    with pytest.raises(ConfigEntryNotReady, match="hc1"):
        await _init(entry)


async def test_all_known_circuits_present_sets_up() -> None:
    entry = _entry(
        registered=[
            _registry_entry("climate", "hc1"),
            _registry_entry("water_heater", "dhw1"),
            _registry_entry("sensor", "hc1_pump_modulation"),
        ],
    )
    assert await _init(entry) is True


async def test_first_setup_without_registered_entities_sets_up() -> None:
    entry = _entry(circuits={"hc": [], "dhw": []})
    assert await _init(entry) is True


async def test_disabled_circuit_entity_is_not_awaited() -> None:
    entry = _entry(
        circuits={"hc": ["hc1"], "dhw": []},
        registered=[
            _registry_entry("climate", "hc1"),
            _registry_entry("climate", "hc2", disabled_by="user"),
        ],
    )
    assert await _init(entry) is True
