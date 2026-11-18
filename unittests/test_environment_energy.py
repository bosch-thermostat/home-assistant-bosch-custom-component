"""Unit tests for environment hour building via recording_merge (no HA)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO / "custom_components" / "bosch" / "recording_merge.py"


def _load():
    """Load recording_merge without package __init__."""
    name = "bosch_env_merge_under_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rm = _load()


def test_environment_hours_match_iva_stack() -> None:
    """compressor + environment equals produced for settled hours."""
    produced = {1.0: 7.0, 2.0: 4.1, 3.0: 4.0}
    compressor = {1.0: 2.0, 2.0: 1.0, 3.0: 4.0}
    env_states = {
        ts: rm.environment_kwh(prod, compressor.get(ts))
        for ts, prod in produced.items()
    }
    assert env_states[1.0] == 5.0
    assert abs(env_states[2.0] - 3.1) < 1e-9
    assert env_states[3.0] == 0.0
    for ts, prod in produced.items():
        assert abs(compressor.get(ts, 0) + env_states[ts] - prod) < 1e-9


def test_environment_backfill_tail_sums() -> None:
    """Backfill rebuilds cumulative sums from an anchor."""
    env_states = {100.0: 5.0, 200.0: 3.1, 300.0: 0.0}
    rows = rm.recompute_hourly_tail(env_states, from_ts=100.0, anchor_sum=10.0)
    assert rows[0] == (100.0, 5.0, 15.0)
    assert abs(rows[1][2] - 18.1) < 1e-9
    assert rows[2] == (300.0, 0.0, 18.1)
