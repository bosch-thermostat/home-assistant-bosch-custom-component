"""Read-back after changing preset, target temperature or HVAC mode.

EasyControl still reports the old value right after a PUT; about one second
later it reports the new one. The climate entity therefore reads the changed
value back once per second until the gateway confirms it (up to
CONFIRM_TIMEOUT) instead of reading it immediately.
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bosch_thermostat_client.exceptions import DeviceException

from custom_components.bosch import climate as climate_mod
from custom_components.bosch.climate import BoschThermostat


class FakeHass:
    """Just enough of HomeAssistant for the read-back."""

    def __init__(self) -> None:
        self.tasks: list[asyncio.Task] = []

    def async_create_background_task(self, coro, name, eager_start=True):
        task = asyncio.ensure_future(coro)
        self.tasks.append(task)
        return task

    async def settle(self) -> None:
        while pending := [t for t in self.tasks if not t.done()]:
            await asyncio.gather(*pending, return_exceptions=True)


@pytest.fixture(autouse=True)
def fast_read_back():
    with patch.object(climate_mod, "CONFIRM_INTERVAL", 0.01):
        yield


def _thermostat(obj: MagicMock) -> BoschThermostat:
    coordinator = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    entity = BoschThermostat(
        coordinator=coordinator, uuid="1", bosch_object=obj, gateway=MagicMock()
    )
    entity.hass = FakeHass()
    entity.entity_id = "climate.living_room"
    entity.async_write_ha_state = MagicMock()
    return entity


def _zone(reads: list[str]) -> MagicMock:
    """Zone whose preset_mode returns ``reads`` one after the other (last one sticks)."""
    obj = MagicMock()
    obj.attr_id = "/zones/zn1"
    obj.set_preset_mode = AsyncMock()
    obj.update_requested_key = AsyncMock()
    obj.update = AsyncMock()
    obj.get_property = MagicMock(return_value={"value": 5})
    values = iter(reads)
    last = {"v": reads[0]}

    def preset() -> str:
        last["v"] = next(values, last["v"])
        return last["v"]

    type(obj).preset_mode = property(lambda self: preset())
    return obj


async def test_preset_confirmed_after_read_back(caplog) -> None:
    """Old program on the first read, new one on the next -> confirmed, then refresh."""
    obj = _zone(["Winter", "Winter free"])
    entity = _thermostat(obj)
    caplog.set_level(logging.INFO)

    await entity.async_set_preset_mode("Winter free")
    assert await entity._confirm_task is True
    await entity.hass.settle()

    obj.set_preset_mode.assert_awaited_once_with("Winter free")
    obj.update_requested_key.assert_awaited()  # only the active program is read
    obj.update.assert_not_awaited()
    entity.async_write_ha_state.assert_called()
    entity.coordinator.async_request_refresh.assert_awaited_once()
    assert "confirmed by the gateway after" in caplog.text


async def test_preset_not_confirmed_warns(caplog) -> None:
    obj = _zone(["Winter"])
    entity = _thermostat(obj)
    with patch.object(climate_mod, "CONFIRM_TIMEOUT", 0.05):
        await entity.async_set_preset_mode("Winter free")
        assert await entity._confirm_task is False
    await entity.hass.settle()
    assert "not confirmed by the gateway" in caplog.text
    entity.async_write_ha_state.assert_called()
    entity.coordinator.async_request_refresh.assert_awaited_once()


async def test_preset_without_program_key_reads_whole_circuit() -> None:
    obj = _zone(["A", "B"])
    obj.get_property = MagicMock(return_value={})
    entity = _thermostat(obj)
    await entity.async_set_preset_mode("B")
    await entity._confirm_task
    obj.update.assert_awaited()
    obj.update_requested_key.assert_not_awaited()


async def test_temperature_confirmed() -> None:
    obj = MagicMock()
    obj.attr_id = "/zones/zn1"
    obj.set_temperature = AsyncMock(return_value=True)
    temps = iter([20.0, 21.5])
    obj.update = AsyncMock(side_effect=lambda: setattr(obj, "target_temperature", next(temps)))
    entity = _thermostat(obj)
    await entity.async_set_temperature(temperature=21.5)
    assert await entity._confirm_task is True
    assert obj.update.await_count == 2


async def test_hvac_mode_confirmed() -> None:
    obj = MagicMock()
    obj.attr_id = "/hc/hc1"
    obj.set_ha_mode = AsyncMock(return_value=1)
    modes = iter(["auto", "heat"])
    obj.update = AsyncMock(side_effect=lambda: setattr(obj, "ha_mode", next(modes)))
    entity = _thermostat(obj)
    assert await entity.async_set_hvac_mode("heat") is True
    assert await entity._confirm_task is True


async def test_read_back_errors_are_tolerated() -> None:
    obj = _zone(["A", "A", "A", "B"])
    obj.update_requested_key = AsyncMock(side_effect=[DeviceException("x"), TypeError("None"), None])
    entity = _thermostat(obj)
    await entity.async_set_preset_mode("B")
    assert await entity._confirm_task is True


async def test_newer_change_supersedes_without_cancelling() -> None:
    """A second change ends the first read-back quietly; nothing is cancelled.

    Cancelling it inside the coordinator refresh at its end would make Home
    Assistant count that refresh as failed and the entity unavailable.
    """
    obj = _zone(["A", "A", "A", "C"])
    entity = _thermostat(obj)
    await entity.async_set_preset_mode("B")
    first = entity._confirm_task
    await entity.async_set_preset_mode("C")
    second = entity._confirm_task
    assert await first is None
    assert await second is True
    await entity.hass.settle()
    assert not first.cancelled()
    entity.coordinator.async_request_refresh.assert_awaited_once()


async def test_refresh_runs_in_its_own_task() -> None:
    """Cancelling the read-back (entity removed) does not cancel a running refresh."""
    obj = _zone(["A", "B"])
    entity = _thermostat(obj)
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_refresh() -> None:
        started.set()
        await release.wait()

    entity.coordinator.async_request_refresh = AsyncMock(side_effect=slow_refresh)
    await entity.async_set_preset_mode("B")
    assert await entity._confirm_task is True
    await started.wait()
    refresh = entity.hass.tasks[-1]
    entity._confirm_task.cancel()
    release.set()
    await refresh
    assert not refresh.cancelled()
