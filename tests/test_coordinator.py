"""Tests for the hourly recording schedule of the Bosch coordinator."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.bosch.const import DOMAIN, UUID
from custom_components.bosch.coordinator import BoschDataUpdateCoordinator

# The hourly update runs at minute 6, so 10:30 is followed by 11:06.
START = "2026-10-02 10:30:00+00:00"
BEFORE_NEXT_RUN = "2026-10-02 11:05:59+00:00"
NEXT_RUN = "2026-10-02 11:06:00+00:00"


class RecordingEntityStub:
    """Recording entity as the coordinator sees it."""

    statistic_id = "sensor.stub"

    def __init__(self, bosch_object: Any = None) -> None:
        """Initialize the stub."""
        self.enabled = True
        self._bosch_object = bosch_object or MagicMock(update=AsyncMock())
        self.async_update_recording = AsyncMock()

    @property
    def bosch_object(self) -> Any:
        """Bosch object backing the entity."""
        return self._bosch_object


class FlakyRecordingEntity(RecordingEntityStub):
    """Raises an unexpected error the first time its Bosch object is used."""

    def __init__(self) -> None:
        """Initialize the stub."""
        super().__init__()
        self._failed = False

    @property
    def bosch_object(self) -> Any:
        """Fail once, then behave."""
        if not self._failed:
            self._failed = True
            raise RuntimeError("unexpected")
        return self._bosch_object


@pytest.fixture
async def coordinator(hass: HomeAssistant) -> AsyncIterator[BoschDataUpdateCoordinator]:
    """Coordinator for a gateway that is never contacted."""
    entry = MockConfigEntry(domain=DOMAIN, data={UUID: "1"})
    entry.add_to_hass(hass)
    coordinator = BoschDataUpdateCoordinator(
        hass, gateway=MagicMock(), uuid="1", entry=entry
    )
    yield coordinator
    coordinator.async_shutdown_recording()


async def _fire(hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: str) -> None:
    freezer.move_to(when)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_recording_update_runs_hourly(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    coordinator: BoschDataUpdateCoordinator,
) -> None:
    """Recording entities are refreshed now and again at the next minute 6."""
    entity = RecordingEntityStub()
    coordinator.register_recording_entity(entity)
    freezer.move_to(START)

    await coordinator.async_recording_sensors_update()

    entity.bosch_object.update.assert_awaited_once()
    entity.async_update_recording.assert_awaited_once()

    await _fire(hass, freezer, BEFORE_NEXT_RUN)
    assert entity.async_update_recording.await_count == 1

    await _fire(hass, freezer, NEXT_RUN)
    assert entity.async_update_recording.await_count == 2


async def test_recording_update_survives_unexpected_error(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    coordinator: BoschDataUpdateCoordinator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unexpected error must not stop the hourly updates for good."""
    entity = FlakyRecordingEntity()
    coordinator.register_recording_entity(entity)
    freezer.move_to(START)

    await coordinator.async_recording_sensors_update()

    assert "Unexpected error while updating Bosch 1-hour sensors" in caplog.text
    entity.async_update_recording.assert_not_awaited()

    await _fire(hass, freezer, NEXT_RUN)
    entity.async_update_recording.assert_awaited_once()


async def test_cancelled_recording_update_is_not_rescheduled(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    coordinator: BoschDataUpdateCoordinator,
) -> None:
    """Cancelling the update (entry unload) must not leave a timer behind."""
    started = asyncio.Event()
    calls = 0

    async def hang(**kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        started.set()
        await asyncio.sleep(3600)

    entity = RecordingEntityStub(MagicMock(update=hang))
    coordinator.register_recording_entity(entity)
    freezer.move_to(START)

    task = asyncio.ensure_future(coordinator.async_recording_sensors_update())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await _fire(hass, freezer, NEXT_RUN)
    assert calls == 1
