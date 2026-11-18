"""Recording append and last-hour display option guards."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components.sensor import SensorStateClass

from custom_components.bosch.const import VALUE
from custom_components.bosch.sensor.recording import RecordingSensor


def test_append_statistics_skips_unavailable() -> None:
    """float('unavailable') must not raise; hour is skipped."""
    entity = RecordingSensor.__new__(RecordingSensor)
    entity._short_id = "test"
    entity._unit_of_measurement = "kWh"
    entity._non_numeric_stat_logged = False
    entity.add_external_stats = MagicMock()
    entity._last_reset = None

    stats = [
        {"d": datetime(2026, 11, 10, 10, 0), "value": "unavailable"},
        {"d": datetime(2026, 11, 10, 11, 0), "value": 1.5},
    ]
    total = entity.append_statistics(stats=stats, sum=0.0, now=datetime.now())
    assert total == 1.5
    entity.add_external_stats.assert_called_once()
    pushed = entity.add_external_stats.call_args.kwargs["stats"]
    assert len(pushed) == 1
    row = pushed[0]
    state = row["state"] if isinstance(row, dict) else row.state
    assert state == 1.5


def test_native_value_is_minus_17_without_shifted_state() -> None:
    """New statistic API keeps entity state at -17 unless shifted display is on."""
    entity = RecordingSensor.__new__(RecordingSensor)
    entity._new_stats_api = True
    entity._recording_shifted_state = False
    entity._attr_state_class = SensorStateClass.TOTAL
    assert entity._native_value() == -17
    assert entity.last_reset is None


def test_shifted_state_shows_hour_without_last_reset_for_measurement() -> None:
    """Shifted display shows the hour; last_reset stays None unless total."""
    hour = datetime(2026, 11, 10, 10, 0)
    entity = RecordingSensor.__new__(RecordingSensor)
    entity._new_stats_api = True
    entity._recording_shifted_state = True
    entity._attr_state_class = SensorStateClass.MEASUREMENT
    entity._current_row = MagicMock(return_value={"d": hour, VALUE: 2.5})
    assert entity._native_value() == 2.5
    assert entity.last_reset is None


def test_shifted_state_last_reset_only_for_total() -> None:
    """last_reset follows the row hour only when state_class is total."""
    hour = datetime(2026, 11, 10, 10, 0)
    entity = RecordingSensor.__new__(RecordingSensor)
    entity._new_stats_api = True
    entity._recording_shifted_state = True
    entity._attr_state_class = SensorStateClass.TOTAL
    entity._current_row = MagicMock(return_value={"d": hour, VALUE: 2.5})
    assert entity._native_value() == 2.5
    assert entity.last_reset == hour
