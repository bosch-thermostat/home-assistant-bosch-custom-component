"""Unit tests for temperature recording hour parsing (no HA)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO / "custom_components" / "bosch" / "recording_temp_fix.py"


def _load():
    """Load recording_temp_fix without package __init__."""
    name = "bosch_recording_temp_fix_under_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rt = _load()


def test_hour_value_keeps_zero_celsius() -> None:
    """0 °C with samples is kept; empty count is skipped."""
    assert rt.hour_value({"y": 0, "c": 60}) == 0.0
    assert rt.hour_value({"y": 390, "c": 60}) == 6.5
    assert rt.hour_value({"y": 0, "c": 0}) is None


def test_parse_temperature_day_keeps_zero() -> None:
    """Day parse includes 0 °C hours unlike energy client skip."""
    day = datetime(2026, 11, 13)
    payload = {
        "recording": [
            {"y": 0, "c": 60},
            {"y": 390, "c": 60},
            {"y": 1, "c": 0},
        ]
    }
    rows = rt.parse_temperature_day(payload, day=day)
    assert len(rows) == 2
    assert rows[0]["value"] == 0.0
    assert rows[0]["d"].hour == 0
    assert rows[1]["value"] == 6.5
    assert rows[1]["d"].hour == 1


def test_is_temperature_unit() -> None:
    """Recognize °C / C units."""
    assert rt.is_temperature_unit("°C") is True
    assert rt.is_temperature_unit("C") is True
    assert rt.is_temperature_unit("kWh") is False


def test_keep_hour_for_lts_temperature_zero() -> None:
    """0 °C is kept; energy 0 kWh stays omitted unless already recorded."""
    assert rt.keep_hour_for_lts(0.0, is_temperature=True) is True
    assert rt.keep_hour_for_lts(0.0, is_temperature=False) is False
    assert (
        rt.keep_hour_for_lts(0.0, is_temperature=False, already_recorded=True) is True
    )
    assert rt.keep_hour_for_lts(6.5, is_temperature=False) is True
