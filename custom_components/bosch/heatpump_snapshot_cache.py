"""Per-refresh heat-pump snapshot cache keyed by coordinator generation."""

from __future__ import annotations

from typing import Any, Callable


SNAPSHOT_ATTR = "_hp_snapshot_cache"


def snapshot_cache_key(coordinator: Any) -> Any:
    """Opaque key that changes after each successful coordinator refresh.

    Prefer last_update_success_time (TimestampDataUpdateCoordinator). Fall
    back to id(coordinator.data) only before the first successful refresh.
    """
    gen = getattr(coordinator, "last_update_success_time", None)
    if gen is not None:
        return gen
    return id(coordinator.data)


def get_or_build_snapshot(
    coordinator: Any,
    build_fn: Callable[[], Any],
    *,
    attr: str = SNAPSHOT_ATTR,
) -> Any:
    """Return cached snapshot for the current generation, or build and store."""
    gen = snapshot_cache_key(coordinator)
    cache = getattr(coordinator, attr, None)
    if isinstance(cache, tuple) and len(cache) == 2 and cache[0] == gen:
        return cache[1]
    snap = build_fn()
    setattr(coordinator, attr, (gen, snap))
    return snap
