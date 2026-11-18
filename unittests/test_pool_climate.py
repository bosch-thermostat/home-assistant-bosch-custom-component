"""Unit tests for pool climate helpers (no Home Assistant)."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO / "custom_components" / "bosch" / "pool.py"


def _load_module():
    """Load pool.py without importing package __init__."""
    name = "bosch_pool_under_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pool = _load_module()


class FakeSensor:
    """Minimal Bosch sensor stub."""

    def __init__(
        self,
        path: str,
        value: Any = None,
        *,
        min_temp: float | None = None,
        max_temp: float | None = None,
    ) -> None:
        self.path = path
        self.attr_id = path
        self.name = path.split("/")[-1]
        self.state = value
        self.min_temp = min_temp
        self.max_temp = max_temp
        self.updates = 0

    async def update(self, _time: Any = None) -> None:
        """Count update calls."""
        self.updates += 1


class FakeGateway:
    """Gateway with sensors and optional raw_query/raw_put."""

    def __init__(
        self,
        sensors: list[Any] | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.sensors = sensors or []
        self.raw = {k.lstrip("/"): v for k, v in (raw or {}).items()}
        self.puts: list[tuple[str, Any]] = []

    async def raw_query(self, path: str) -> Any:
        """Return fixture value or raise."""
        key = path.lstrip("/")
        if key not in self.raw:
            raise LookupError(path)
        return self.raw[key]

    async def raw_put(self, path: str, value: Any) -> None:
        """Record write."""
        self.puts.append((path.lstrip("/"), value))


def test_status_to_hvac_mapping() -> None:
    """off/empty → off; anything else → heat."""
    assert pool.status_to_hvac("off") == pool.HVAC_OFF
    assert pool.status_to_hvac("OFF") == pool.HVAC_OFF
    assert pool.status_to_hvac(None) == pool.HVAC_OFF
    assert pool.status_to_hvac("") == pool.HVAC_OFF
    assert pool.status_to_hvac("on") == pool.HVAC_HEAT
    assert pool.status_to_hvac("auto") == pool.HVAC_HEAT


def test_hvac_to_status_mapping() -> None:
    """heat → on; off → off."""
    assert pool.hvac_to_status(pool.HVAC_HEAT) == "on"
    assert pool.hvac_to_status(pool.HVAC_OFF) == "off"
    assert pool.hvac_to_status("HEAT") == "on"


def test_path_match_with_or_without_slash() -> None:
    """Leading slash is ignored."""
    assert pool.path_matches("/heatSources/poolStatus", pool.POOL_STATUS_PATH)
    assert pool.path_matches("heatSources/poolStatus", pool.POOL_STATUS_PATH)
    assert pool.is_pool_path("/heatSources/poolTemperature")
    assert not pool.is_pool_path("heatSources/actualModulation")


def test_find_pool_sensors_from_gateway() -> None:
    """Detect pool sensors by path suffix."""
    sensors = [
        FakeSensor("heatSources/actualModulation", 0),
        FakeSensor("/heatSources/poolStatus", "off"),
        FakeSensor("heatSources/poolTemperature", 29.3),
        FakeSensor("heatSources/poolSetpointTemperature", 29),
    ]
    gw = FakeGateway(sensors=sensors)
    found = pool.find_pool_sensors(gw)
    assert set(found) == set(pool.POOL_PATHS)
    assert pool.gateway_has_pool_sensors(gw)


def test_detect_fails_closed_without_pool() -> None:
    """No pool sensors → not detected."""
    gw = FakeGateway(sensors=[FakeSensor("heatSources/actualModulation", 0)])
    assert not pool.gateway_has_pool_sensors(gw)


def test_probe_pool_status_via_raw_query() -> None:
    """Probe succeeds when raw_query returns a status."""
    gw = FakeGateway(raw={"heatSources/poolStatus": "off"})
    assert asyncio.run(pool.probe_pool_status(gw)) is True
    assert asyncio.run(pool.async_pool_available(gw)) is True


def test_probe_fails_closed() -> None:
    """Probe fails when path is missing."""
    gw = FakeGateway(raw={})
    assert asyncio.run(pool.probe_pool_status(gw)) is False
    assert asyncio.run(pool.async_pool_available(gw)) is False


def test_poller_reads_sensors() -> None:
    """Poller updates from sensor objects."""
    sensors = [
        FakeSensor("heatSources/poolStatus", "off"),
        FakeSensor("heatSources/poolTemperature", 29.3),
        FakeSensor(
            "heatSources/poolSetpointTemperature",
            29,
            min_temp=10,
            max_temp=35,
        ),
    ]
    gw = FakeGateway(sensors=sensors)
    poller = pool.PoolPoller(gw)
    assert poller.min_temp == 10
    assert poller.max_temp == 35
    asyncio.run(poller.update())
    assert poller.status == "off"
    assert poller.current_temp == 29.3
    assert poller.target_temp == 29.0
    assert all(s.updates == 1 for s in sensors)


def test_poller_raw_query_fallback() -> None:
    """Missing sensors are filled via raw_query."""
    gw = FakeGateway(
        sensors=[],
        raw={
            "heatSources/poolStatus": {"value": "on"},
            "heatSources/poolTemperature": 28.5,
            "heatSources/poolSetpointTemperature": 30,
        },
    )
    poller = pool.PoolPoller(gw)
    assert poller.uses_raw_query()
    asyncio.run(poller.update())
    assert poller.status == "on"
    assert poller.current_temp == 28.5
    assert poller.target_temp == 30.0
    assert pool.status_to_hvac(poller.status) == pool.HVAC_HEAT


def test_poller_writes() -> None:
    """Status and setpoint writes use raw_put paths."""
    gw = FakeGateway()
    poller = pool.PoolPoller(gw)
    asyncio.run(poller.async_set_status("on"))
    asyncio.run(poller.async_set_temperature(31.5))
    assert gw.puts == [
        ("heatSources/poolStatus", "on"),
        ("heatSources/poolSetpointTemperature", 31.5),
    ]


def test_extract_scalar_variants() -> None:
    """Scalars from state, dict, and nested result."""
    assert pool.extract_scalar(SimpleNamespace(state="off", attr_id="x")) == "off"
    assert pool.extract_scalar({"value": 29}) == 29
    assert pool.extract_scalar({"result": {"value": "on"}}) == "on"
    assert pool.extract_scalar(None) is None
