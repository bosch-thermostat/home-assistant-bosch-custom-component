"""Unit tests for HDH hour building via recording_merge (no HA)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO / "custom_components" / "bosch" / "recording_merge.py"


def _load():
    """Load recording_merge without package __init__."""
    name = "bosch_hdh_merge_under_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rm = _load()


def test_hdh_hours_from_outdoor() -> None:
    """Per-hour HDH matches max(0, 15 − outdoor); missing outdoor skipped."""
    outdoor = {1.0: 20.0, 2.0: 5.0, 3.0: -1.0, 4.0: None}
    hdh_states: dict[float, float] = {}
    for ts, temp in outdoor.items():
        value = rm.degree_hours(temp)
        if value is None:
            continue
        hdh_states[ts] = value
    assert hdh_states == {1.0: 0.0, 2.0: 10.0, 3.0: 16.0}
    assert 4.0 not in hdh_states


def test_hdh_backfill_tail_sums() -> None:
    """Backfill rebuilds cumulative HDH sums from an anchor."""
    hdh_states = {100.0: 0.0, 200.0: 10.0, 300.0: 16.0}
    rows = rm.recompute_hourly_tail(hdh_states, from_ts=100.0, anchor_sum=50.0)
    assert rows[0] == (100.0, 0.0, 50.0)
    assert rows[1] == (200.0, 10.0, 60.0)
    assert rows[2] == (300.0, 16.0, 76.0)
