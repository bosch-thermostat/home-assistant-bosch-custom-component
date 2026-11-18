"""Unit tests for recording merge / environment formula (no HA)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO / "custom_components" / "bosch" / "recording_merge.py"


def _load():
    """Load recording_merge without package __init__."""
    name = "bosch_recording_merge_under_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rm = _load()


def test_environment_kwh() -> None:
    """Environment is max(0, produced − compressor)."""
    assert rm.environment_kwh(7.0, 2.0) == 5.0
    assert rm.environment_kwh(4.0, 4.0) == 0.0
    assert rm.environment_kwh(4.0, None) == 4.0
    assert rm.environment_kwh(None, 2.0) is None


def test_degree_hours() -> None:
    """HDH is max(0, base − outdoor); missing outdoor is None."""
    assert rm.degree_hours(20.0) == 0.0
    assert rm.degree_hours(5.0) == 10.0
    assert rm.degree_hours(None) is None
    assert rm.degree_hours(-5.0, base_c=15.0) == 20.0


def test_recompute_hourly_tail_delta() -> None:
    """Changing one hour rewrites that hour and later sums."""
    states = {100.0: 2.0, 200.0: 4.0, 300.0: 1.0}
    # Revise hour 200 from 4 → 0
    states[200.0] = 0.0
    tail = rm.recompute_hourly_tail(states, from_ts=200.0, anchor_sum=2.0)
    assert tail == [
        (200.0, 0.0, 2.0),
        (300.0, 1.0, 3.0),
    ]


def test_first_changed_hour_and_anchor() -> None:
    """Detect earliest change and anchor sum before it."""
    existing = {100.0: 2.0, 200.0: 4.0}
    incoming = {200.0: 0.0, 300.0: 1.0}
    assert rm.first_changed_hour(existing, incoming) == 200.0
    sums = {100.0: 2.0, 200.0: 6.0}
    assert rm.anchor_sum_before(sums, 200.0) == 2.0
    assert rm.anchor_sum_before(sums, 100.0) == 0.0


def test_merge_hour_states() -> None:
    """Incoming overrides existing keys."""
    merged = rm.merge_hour_states({1.0: 1.0, 2.0: 2.0}, {2.0: 9.0, 3.0: 3.0})
    assert merged == {1.0: 1.0, 2.0: 9.0, 3.0: 3.0}
