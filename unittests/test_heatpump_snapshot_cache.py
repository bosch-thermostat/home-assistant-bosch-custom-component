"""Unit tests for heat-pump snapshot cache generation (no HA)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO / "custom_components" / "bosch" / "heatpump_snapshot_cache.py"


def _load():
    """Load heatpump_snapshot_cache without package __init__."""
    name = "bosch_heatpump_snapshot_cache_under_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cache = _load()


def test_key_prefers_last_update_success_time() -> None:
    """Timestamp coordinator key wins over id(data)."""
    t0 = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)
    coord = SimpleNamespace(last_update_success_time=t0, data=True)
    assert cache.snapshot_cache_key(coord) == t0


def test_key_fallback_id_true_is_stable() -> None:
    """Constant True data must not invent a new generation each call."""
    coord = SimpleNamespace(data=True)
    # No last_update_success_time attribute.
    first = cache.snapshot_cache_key(coord)
    second = cache.snapshot_cache_key(coord)
    assert first == second == id(True)


def test_get_or_build_hits_same_generation() -> None:
    """Same timestamp returns the identical snapshot object."""
    t0 = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)
    coord = SimpleNamespace(last_update_success_time=t0, data=True)
    builds: list[int] = []

    def build() -> object:
        builds.append(1)
        return object()

    first = cache.get_or_build_snapshot(coord, build)
    second = cache.get_or_build_snapshot(coord, build)
    assert first is second
    assert len(builds) == 1


def test_get_or_build_rebuilds_on_new_timestamp() -> None:
    """Advancing last_update_success_time forces a rebuild."""
    t0 = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 11, 15, 18, 1, tzinfo=timezone.utc)
    coord = SimpleNamespace(last_update_success_time=t0, data=True)
    builds: list[int] = []

    def build() -> object:
        builds.append(1)
        return object()

    first = cache.get_or_build_snapshot(coord, build)
    coord.last_update_success_time = t1
    second = cache.get_or_build_snapshot(coord, build)
    assert first is not second
    assert len(builds) == 2


def test_id_true_alone_does_not_invalidate() -> None:
    """Without a timestamp, id(True) keeps the cached empty-era snapshot."""
    coord = SimpleNamespace(data=True)
    builds: list[int] = []

    def build() -> object:
        builds.append(1)
        return object()

    first = cache.get_or_build_snapshot(coord, build)
    # Simulate another refresh that still returns True and has no timestamp.
    second = cache.get_or_build_snapshot(coord, build)
    assert first is second
    assert len(builds) == 1
