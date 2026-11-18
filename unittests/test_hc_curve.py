"""HC curve sensors: device attach, disabled default, getters, poll refcount."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.bosch.const import DOMAIN
from custom_components.bosch.heatpump_diagnostics import (
    CircuitSnapshot,
    HeatpumpSnapshot,
)
from custom_components.bosch.sensor import hc_curve


class _FakeCircuit:
    """Minimal heating circuit object."""

    def __init__(self, circuit_id: str) -> None:
        self.id = circuit_id


class _FakeGateway:
    """Gateway with one heating circuit."""

    def __init__(self, circuits: list[Any]) -> None:
        self._circuits = {"hc": circuits}

    def get_circuits(self, ctype: str) -> list[Any]:
        return self._circuits.get(ctype, [])


class _FakeCoordinator:
    """Coordinator stub for register refcounting."""

    def __init__(self) -> None:
        self.registered: list[Any] = []
        self.unregistered: list[Any] = []
        self.gateway_device_id: str | None = None

    def register_object(self, obj: Any) -> None:
        self.registered.append(obj)

    def unregister_object(self, obj: Any) -> None:
        self.unregistered.append(obj)


def test_build_entities_attach_to_hc_device() -> None:
    """Seven disabled sensors land on the HC climate device id."""
    circuit = _FakeCircuit("hc2")
    gateway = _FakeGateway([circuit])
    coordinator = MagicMock()
    coordinator.gateway_device_id = None
    entities = hc_curve.build_hc_curve_entities(coordinator, gateway, "uuid-1")
    assert len(entities) == 7
    assert all(e.entity_registry_enabled_default is False for e in entities)
    info = entities[0].device_info
    assert info["identifiers"] == {(DOMAIN, "uuid-1_hc2")}


def test_field_getter_reads_circuit_or_none() -> None:
    """Getter returns the circuit field; missing circuit is None."""
    getter = hc_curve._field_getter("hc2", "design_temp")
    snap = HeatpumpSnapshot(
        circuits=[CircuitSnapshot(circuit_id="hc2", design_temp=-10.0)]
    )
    assert getter(snap) == -10.0
    assert hc_curve._field_getter("hc3", "design_temp")(snap) is None


def test_register_refcount_shared() -> None:
    """Two sensors share one circuit poll; last removal unregisters."""
    circuit = _FakeCircuit("hc2")
    gateway = _FakeGateway([circuit])
    coordinator = _FakeCoordinator()
    hc_curve._register_hc_circuits(coordinator, gateway)
    hc_curve._register_hc_circuits(coordinator, gateway)
    assert coordinator.registered == [circuit]
    bucket = getattr(coordinator, hc_curve._HC_CURVE_ATTR)
    assert bucket["refs"] == 2
    hc_curve._unregister_hc_circuits(coordinator)
    assert coordinator.unregistered == []
    assert getattr(coordinator, hc_curve._HC_CURVE_ATTR)["refs"] == 1
    hc_curve._unregister_hc_circuits(coordinator)
    assert coordinator.unregistered == [circuit]
    assert getattr(coordinator, hc_curve._HC_CURVE_ATTR, None) is None
