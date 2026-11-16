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


def _setpoint_circuit(reported: list[float], step: float | None = 0.5) -> MagicMock:
    """Circuit whose setpoint key reports ``reported`` one read after the other."""
    obj = MagicMock()
    obj.attr_id = "/heatingCircuits/hc1"
    obj.set_temperature = AsyncMock(return_value=True)
    obj._op_mode.temp_setpoint_read = MagicMock(return_value="manualTemperatureHeating")
    prop = {"value": reported[0]}
    if step is not None:
        prop["stepSize"] = step
    obj.get_property = MagicMock(side_effect=lambda key: prop if key == "manualTemperatureHeating" else {})
    values = iter(reported)

    async def read_key(key: str) -> None:
        obj.target_temperature = next(values, obj.target_temperature)

    obj.target_temperature = None
    obj.update_requested_key = AsyncMock(side_effect=read_key)
    obj.update = AsyncMock()
    return obj


async def test_temperature_reads_only_the_setpoint() -> None:
    obj = _setpoint_circuit([20.0, 21.5])
    entity = _thermostat(obj)
    await entity.async_set_temperature(temperature=21.5)
    assert await entity._confirm_task is True
    obj.update_requested_key.assert_awaited_with("manualTemperatureHeating")
    obj.update.assert_not_awaited()


async def test_temperature_rounded_by_the_gateway_is_confirmed() -> None:
    """21.3 sent, the gateway stores 21.5 (stepSize 0.5) -> confirmed, no 15 s wait."""
    obj = _setpoint_circuit([20.0, 21.5])
    entity = _thermostat(obj)
    await entity.async_set_temperature(temperature=21.3)
    assert await entity._confirm_task is True


async def test_temperature_step_size_from_the_gateway() -> None:
    """With stepSize 1 a deviation of 0.5 is still the same step."""
    obj = _setpoint_circuit([20.0, 22.0], step=1)
    entity = _thermostat(obj)
    await entity.async_set_temperature(temperature=21.5)
    assert await entity._confirm_task is True


async def test_temperature_off_by_a_full_step_is_not_confirmed() -> None:
    obj = _setpoint_circuit([20.0, 22.0])
    entity = _thermostat(obj)
    with patch.object(climate_mod, "CONFIRM_TIMEOUT", 0.05):
        await entity.async_set_temperature(temperature=21.3)
        assert await entity._confirm_task is False


async def test_temperature_without_setpoint_key_reads_whole_circuit() -> None:
    obj = _setpoint_circuit([20.0, 21.5])
    obj._op_mode.temp_setpoint_read = MagicMock(return_value=None)
    del obj._temp_setpoint
    temps = iter([20.0, 21.5])
    obj.update = AsyncMock(side_effect=lambda: setattr(obj, "target_temperature", next(temps)))
    entity = _thermostat(obj)
    await entity.async_set_temperature(temperature=21.5)
    assert await entity._confirm_task is True
    obj.update_requested_key.assert_not_awaited()


@pytest.mark.parametrize("result", [None, False])
async def test_failed_preset_is_not_read_back(result) -> None:
    obj = _zone(["Winter"])
    obj.set_preset_mode = AsyncMock(return_value=result)
    entity = _thermostat(obj)
    await entity.async_set_preset_mode("Winter free")
    assert entity._confirm_task is None
    obj.update_requested_key.assert_not_awaited()
    entity.coordinator.async_request_refresh.assert_awaited_once()


async def test_preset_with_empty_http_answer_is_read_back() -> None:
    """The HTTP connector answers a successful PUT with its (possibly empty) text."""
    obj = _zone(["A", "B"])
    obj.set_preset_mode = AsyncMock(return_value="")
    entity = _thermostat(obj)
    await entity.async_set_preset_mode("B")
    assert await entity._confirm_task is True


async def test_no_attempt_starts_after_the_timeout() -> None:
    """No read-back attempt starts after CONFIRM_TIMEOUT, even with slow requests.

    Fake clock: every request takes 3.75 s. After the third one 14.25 s have
    passed; one more interval would start the next attempt at 15.25 s, past
    the timeout, so the read-back ends there.
    """
    clock = {"now": 0.0}
    starts: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        clock["now"] += delay
        await real_sleep(0)

    async def slow_read(key: str) -> None:
        starts.append(clock["now"])
        clock["now"] += 3.75

    obj = _zone(["A"])
    obj.update_requested_key = AsyncMock(side_effect=slow_read)
    entity = _thermostat(obj)
    with (
        patch.object(climate_mod, "CONFIRM_INTERVAL", 1.0),
        patch.object(climate_mod, "CONFIRM_TIMEOUT", 15.0),
        patch.object(climate_mod.time, "monotonic", lambda: clock["now"]),
        patch.object(climate_mod.asyncio, "sleep", fake_sleep),
    ):
        await entity.async_set_preset_mode("B")
        assert await entity._confirm_task is False
    assert starts == [1.0, 5.75, 10.5]


async def test_optimistic_value_kept_during_read_back() -> None:
    """A scheduled poll inside the read-back window keeps the optimistic value."""
    obj = _setpoint_circuit([20.0, 20.0, 20.0, 21.5])
    obj.target_temperature = 20.0
    entity = _thermostat(obj)
    entity._optimistic_mode = True
    gate = asyncio.Event()
    original = obj.update_requested_key.side_effect

    async def gated(key: str) -> None:
        await original(key)
        gate.set()

    obj.update_requested_key.side_effect = gated
    with patch(
        "homeassistant.helpers.update_coordinator.CoordinatorEntity._handle_coordinator_update"
    ):
        await entity.async_set_temperature(temperature=21.5)
        await asyncio.wait_for(gate.wait(), 2)
        entity._handle_coordinator_update()  # scheduled poll, gateway still old
        assert entity.target_temperature == 21.5
        assert await entity._confirm_task is True
        assert entity._optimistic_target_temperature is None
        entity._handle_coordinator_update()
    assert entity.target_temperature == 21.5


def _zone_with_setpoint(programs: list[str], setpoints: list[float]) -> MagicMock:
    """Zone in auto mode: program and the setpoint read key report one after the other."""
    obj = _zone(programs)
    obj._op_mode.temp_setpoint_read = MagicMock(return_value="targetTemp")
    obj.get_property = MagicMock(side_effect=lambda key: {"value": 1})
    obj.target_temperature = setpoints[0]
    values = iter(setpoints[1:])

    async def read_key(key: str) -> None:
        if key == "targetTemp":
            obj.target_temperature = next(values, obj.target_temperature)

    obj.update_requested_key = AsyncMock(side_effect=read_key)
    return obj


async def test_setpoint_of_new_program_is_followed(caplog) -> None:
    """The program is confirmed first; its setpoint arrives two reads later."""
    obj = _zone_with_setpoint(["Wohnzimmer Winter", "Buero Winter"], [17.0, 17.0, 17.0, 21.0])
    entity = _thermostat(obj)
    caplog.set_level(logging.INFO)
    await entity.async_set_preset_mode("Buero Winter")
    assert await entity._confirm_task is True
    await entity.hass.settle()
    assert obj.target_temperature == 21.0
    assert "setpoint 21.0 of the new program reported" in caplog.text
    keys = [c.args[0] for c in obj.update_requested_key.await_args_list]
    assert keys.count("targetTemp") == 3
    entity.coordinator.async_request_refresh.assert_awaited_once()


async def test_unchanged_setpoint_ends_quietly(caplog) -> None:
    obj = _zone_with_setpoint(["A", "B"], [21.0])
    entity = _thermostat(obj)
    with patch.object(climate_mod, "SETPOINT_FOLLOW_TIMEOUT", 0.05):
        await entity.async_set_preset_mode("B")
        assert await entity._confirm_task is True
    await entity.hass.settle()
    assert "WARNING" not in caplog.text
    entity.coordinator.async_request_refresh.assert_awaited_once()


async def test_newer_change_ends_the_setpoint_follow() -> None:
    obj = _zone_with_setpoint(["A", "B", "B", "B", "B", "C"], [17.0])
    entity = _thermostat(obj)
    with patch.object(climate_mod, "SETPOINT_FOLLOW_TIMEOUT", 0.3):
        await entity.async_set_preset_mode("B")
        first = entity._confirm_task
        async def following() -> None:  # program confirmed, setpoint being read
            while obj.update_requested_key.await_count < 3:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(following(), 2)
        await entity.async_set_preset_mode("C")
        assert await first is None
        await entity._confirm_task
    await entity.hass.settle()
    entity.coordinator.async_request_refresh.assert_awaited_once()


async def test_no_setpoint_follow_without_setpoint_key() -> None:
    obj = _zone(["A", "B"])
    entity = _thermostat(obj)
    await entity.async_set_preset_mode("B")
    assert await entity._confirm_task is True
    await entity.hass.settle()
    keys = {c.args[0] for c in obj.update_requested_key.await_args_list}
    assert keys == {climate_mod.ACTIVE_PROGRAM}  # only the program, no setpoint follow
