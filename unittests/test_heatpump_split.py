"""Unit tests for compressor runtime split (no HA)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO / "custom_components" / "bosch" / "heatpump_split.py"


def _load_module():
    """Load heatpump_split without importing package __init__."""
    name = "bosch_heatpump_split_under_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


split = _load_module()


def _snap(**kwargs):
    """Minimal snapshot-like object."""
    base = {
        "compressor_on": True,
        "dhw_charging": False,
        "requesting_circuits": [],
        "pool_heating": False,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_sinks_skip_hc1_when_other_requests() -> None:
    """Buffer hc1 follows; non-hc1 leads when both request."""
    assert split.sinks_from_snapshot(
        _snap(requesting_circuits=["hc1", "hc2"], dhw_charging=True)
    ) == ["dhw", "hc2"]
    assert split.sinks_from_snapshot(_snap(requesting_circuits=["hc1"])) == ["hc1"]
    assert split.sinks_from_snapshot(_snap(requesting_circuits=[])) == ["other"]
    assert split.sinks_from_snapshot(_snap(compressor_on=False)) == []


def test_equal_split_and_shares() -> None:
    """Concurrent sinks split the tick equally; minutes and % follow."""
    acc = split.HeatpumpSplitAccumulator()
    t0 = datetime(2026, 11, 11, 10, 0, 0)
    acc.add_tick(_snap(requesting_circuits=["hc2"]), t0)
    acc.add_tick(
        _snap(requesting_circuits=["hc2"], dhw_charging=True),
        t0 + timedelta(seconds=60),
    )
    assert acc.seconds["hc2"] == 30.0
    assert acc.seconds["dhw"] == 30.0
    assert acc.minutes("hc2") == 0.5
    assert acc.share_percent("hc2") == 50.0
    assert acc.share_percent("dhw") == 50.0
    assert acc.minutes("hc1") == 0.0
    assert acc.share_percent("hc3") == 0.0


def test_midnight_reset() -> None:
    """Local date change clears seconds."""
    acc = split.HeatpumpSplitAccumulator()
    t0 = datetime(2026, 11, 11, 23, 58, 0)
    acc.add_tick(_snap(requesting_circuits=["hc1"]), t0)
    acc.add_tick(_snap(requesting_circuits=["hc1"]), t0 + timedelta(seconds=60))
    assert acc.minutes("hc1") == 1.0
    next_day = datetime(2026, 11, 12, 0, 0, 30)
    acc.add_tick(_snap(requesting_circuits=["hc2"]), next_day)
    assert acc.day == next_day.date()
    assert acc.seconds == {}
    acc.add_tick(_snap(requesting_circuits=["hc2"]), next_day + timedelta(seconds=120))
    assert acc.minutes("hc2") == 2.0
    assert acc.share_percent("hc1") == 0.0


def test_dt_cap_and_roundtrip() -> None:
    """Long gaps are capped; Store dict round-trips."""
    acc = split.HeatpumpSplitAccumulator()
    t0 = datetime(2026, 11, 11, 10, 0, 0)
    acc.add_tick(_snap(requesting_circuits=["hc1"]), t0)
    acc.add_tick(
        _snap(requesting_circuits=["hc1"]),
        t0 + timedelta(seconds=900),
    )
    assert acc.seconds["hc1"] == split.MAX_TICK_SECONDS
    restored = split.HeatpumpSplitAccumulator.from_dict(acc.to_dict())
    assert restored.day == acc.day
    assert restored.seconds == acc.seconds
    assert restored.last_tick == acc.last_tick
    assert split.HeatpumpSplitAccumulator.from_dict(None).seconds == {}


def test_shares_unknown_without_runtime() -> None:
    """No compressor seconds yet → share/minutes are None."""
    acc = split.HeatpumpSplitAccumulator()
    assert acc.share_percent("hc1") is None
    assert acc.minutes("hc1") is None
