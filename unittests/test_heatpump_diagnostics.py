"""Unit tests for IVT heat-pump diagnostics (no gateway / no HA)."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO / "custom_components" / "bosch" / "heatpump_diagnostics.py"


def _load_module():
    """Load heatpump_diagnostics without importing package __init__."""
    name = "bosch_heatpump_diagnostics_under_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hp = _load_module()
FIXTURE = Path(__file__).parent / "fixtures" / "km200_snapshot_standby.json"


def _standby() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_standby_snapshot_mode_and_metrics() -> None:
    """KM200 standby scan classifies as circulation with COP and backup share."""
    snap = hp.build_snapshot_from_path_map(_standby())
    assert snap.is_heatpump
    assert hp.classify_heatpump_mode(snap) == "circulation"
    assert snap.compressor_on is False
    assert snap.dhw_charging is False
    assert snap.dhw_requested is True
    assert snap.heat_requestors == ["dhw"]
    assert snap.dhw_gap == 3.9
    assert snap.pool_heating is False
    assert snap.pool_gap == -0.3
    assert len(snap.requesting_circuits) == 0
    assert snap.primary_circuit == "hc2"
    assert any(c.circuit_id == "hc1" and c.room_sensor_fault for c in snap.circuits)
    assert snap.heat_source_delta == -0.1
    assert snap.cop("today") == 3.3
    assert snap.backup_share("today") == 0.17
    assert (snap.eheater_today or 0) > 0
    hint, attrs = hp.classify_efficiency_hint(snap)
    assert hint == "ok"
    assert attrs["cop_min"] == 2.8


def test_pool_mode_requires_compressor() -> None:
    """poolStatus on with compressor selects pool / pool_and_heating."""
    data = _standby()
    data["heatSources/poolStatus"] = "on"
    data["heatSources/actualModulation"] = 40
    data["heatSources/applianceSupplyTemperature"] = 10.0
    snap = hp.build_snapshot_from_path_map(data)
    assert hp.classify_heatpump_mode(snap) == "pool"

    data["heatingCircuits/hc2/supplyTemperatureSetpoint"] = 30
    data["heatingCircuits/hc2/actualSupplyTemperature"] = 30.2
    data["heatSources/applianceSupplyTemperature"] = 30.4
    snap = hp.build_snapshot_from_path_map(data)
    assert snap.space_heating_active
    assert hp.classify_heatpump_mode(snap) == "pool_and_heating"

    data["heatSources/poolStatus"] = "off"
    snap = hp.build_snapshot_from_path_map(data)
    assert hp.classify_heatpump_mode(snap) != "pool"


def test_circuit_requestor_matches_appliance_supply() -> None:
    """The circuit whose actual supply matches appliance supply is requesting."""
    data = _standby()
    data["heatSources/actualModulation"] = 40
    data["heatSources/applianceSupplyTemperature"] = 24.4
    data["heatingCircuits/hc1/actualSupplyTemperature"] = 40.2
    snap = hp.build_snapshot_from_path_map(data)
    assert snap.requesting_circuits == ["hc2"]
    assert hp.classify_heatpump_mode(snap) == "space_heating"

    data["heatSources/actualModulation"] = 0
    snap = hp.build_snapshot_from_path_map(data)
    assert snap.requesting_circuits == []
    assert hp.classify_heatpump_mode(snap) == "circulation"


def test_aku_buffer_matches_actual_not_setpoint() -> None:
    """AKU/hc1 actual supply matches appliance; setpoint alone does not."""
    data = _standby()
    data["heatSources/actualModulation"] = 60
    data["heatSources/applianceSupplyTemperature"] = 44.4
    data["heatSources/actualSupplyTemperature"] = 44.4
    data["heatSources/returnTemperature"] = 40.5
    data["heatingCircuits/hc1/supplyTemperatureSetpoint"] = 32
    data["heatingCircuits/hc1/actualSupplyTemperature"] = 44.5
    data["heatingCircuits/hc2/supplyTemperatureSetpoint"] = 30
    data["heatingCircuits/hc2/actualSupplyTemperature"] = 29.9
    data["heatingCircuits/hc2/pumpModulation"] = 100
    snap = hp.build_snapshot_from_path_map(data)
    assert snap.requesting_circuits == ["hc1"]
    assert snap.heat_requestors == ["dhw", "hc1"]
    assert snap.primary_circuit == "hc1"
    assert snap.heat_source_delta == 3.9
    # charge=stop: requestors include dhw, mode uses charging only
    assert hp.classify_heatpump_mode(snap) == "space_heating"


def test_primary_prefers_non_hc1_when_both_request() -> None:
    """hc1 buffer follows; non-hc1 with same supply match is primary."""
    data = _standby()
    data["heatSources/actualModulation"] = 60
    data["heatSources/applianceSupplyTemperature"] = 30.0
    data["heatingCircuits/hc1/supplyTemperatureSetpoint"] = 32
    data["heatingCircuits/hc1/actualSupplyTemperature"] = 30.1
    data["heatingCircuits/hc1/pumpModulation"] = 0
    data["heatingCircuits/hc2/supplyTemperatureSetpoint"] = 30
    data["heatingCircuits/hc2/actualSupplyTemperature"] = 29.9
    data["heatingCircuits/hc2/pumpModulation"] = 100
    snap = hp.build_snapshot_from_path_map(data)
    assert set(snap.requesting_circuits) == {"hc1", "hc2"}
    assert snap.primary_circuit == "hc2"


def test_ivt_system_appliance_supply_path() -> None:
    """RC300 uses system/appliance/actualSupplyTemperature, not heatSources/."""
    data = _standby()
    del data["heatSources/applianceSupplyTemperature"]
    del data["heatSources/actualSupplyTemperature"]
    data["heatSources/actualModulation"] = 60
    data["system/appliance/actualSupplyTemperature"] = 46.6
    data["system/sensors/temperatures/return"] = 41.6
    data["heatingCircuits/hc1/supplyTemperatureSetpoint"] = 31
    data["heatingCircuits/hc1/actualSupplyTemperature"] = 46.7
    data["heatingCircuits/hc2/supplyTemperatureSetpoint"] = 30
    data["heatingCircuits/hc2/actualSupplyTemperature"] = 28.2
    data["heatingCircuits/hc2/pumpModulation"] = 100
    snap = hp.build_snapshot_from_path_map(data)
    assert snap.lead_supply_temp == 46.6
    assert snap.requesting_circuits == ["hc1"]
    assert snap.primary_circuit == "hc1"
    assert snap.heat_source_delta == 5.0


def test_requestors_can_overlap() -> None:
    """DHW setpoint, matching circuits, and pool are independent requestors."""
    data = _standby()
    data["heatSources/actualModulation"] = 40
    data["heatSources/applianceSupplyTemperature"] = 10.0
    data["dhwCircuits/dhw1/currentSetpoint"] = 0
    data["heatSources/poolStatus"] = "off"
    snap = hp.build_snapshot_from_path_map(data)
    assert snap.dhw_requested is False
    assert snap.heat_requestors == []

    data["dhwCircuits/dhw1/currentSetpoint"] = 51
    data["heatSources/applianceSupplyTemperature"] = 22.0
    data["heatingCircuits/hc1/supplyTemperatureSetpoint"] = 22.2
    data["heatingCircuits/hc1/actualSupplyTemperature"] = 22.1
    data["heatingCircuits/hc2/actualSupplyTemperature"] = 22.0
    data["heatSources/poolStatus"] = "on"
    snap = hp.build_snapshot_from_path_map(data)
    assert snap.heat_requestors == ["dhw", "hc1", "hc2", "pool"]
    assert hp.classify_heatpump_mode(snap) == "pool_and_heating"


def test_dhw_mode() -> None:
    """DHW charge with compressor selects dhw."""
    data = _standby()
    data["heatSources/actualModulation"] = 40
    data["heatSources/applianceSupplyTemperature"] = 10.0
    data["dhwCircuits/dhw1/charge"] = "start"
    snap = hp.build_snapshot_from_path_map(data)
    assert hp.classify_heatpump_mode(snap) == "dhw"


def test_efficiency_hint_branches() -> None:
    """Hint cutoffs for backup, COP, spread, and unknown."""
    data = _standby()
    data["recordings/heatSources/total/energyMonitoring/eheater_Today_kWh"] = 6.0
    hint, _ = hp.classify_efficiency_hint(hp.build_snapshot_from_path_map(data))
    assert hint == "check_backup"

    data = _standby()
    data["recordings/heatSources/total/energyMonitoring/outputProduced_Today_kWh"] = 46.0
    hint, _ = hp.classify_efficiency_hint(hp.build_snapshot_from_path_map(data))
    assert hint == "check_cop"

    data = _standby()
    data["heatSources/actualModulation"] = 40
    data["heatSources/actualSupplyTemperature"] = 40.1
    data["heatSources/returnTemperature"] = 40.0
    hint, _ = hp.classify_efficiency_hint(hp.build_snapshot_from_path_map(data))
    assert hint == "check_spread"

    data = _standby()
    data["recordings/heatSources/total/energyMonitoring/consumedEnergy_Today_kWh"] = 0.4
    hint, _ = hp.classify_efficiency_hint(hp.build_snapshot_from_path_map(data))
    assert hint == "unknown"


def test_last_hour_from_recording_rows() -> None:
    """Latest hourly row is used; day totals come from local today hours."""
    data = _standby()
    data["recordings/heatSources/total/energyMonitoring/consumedEnergy"] = [
        {"d": "2026-11-10T17:00:00", "value": 1.2},
        {"d": "2026-11-10T18:00:00", "value": "unavailable"},
        {"d": "2026-11-10T16:00:00", "value": 0.4},
    ]
    # 19:00 → last full hour 18:00 excluded; 16+17 settle.
    now = datetime(2026, 11, 10, 19, 0, 0)
    snap = hp.build_snapshot_from_path_map(data, now=now)
    assert snap.last_hour_electricity == 1.2
    assert snap.consumed_today == 1.6


def test_hourly_list_overrides_stale_today_scalar() -> None:
    """Hourly list for local today wins over a stale *_Today_kWh scalar."""
    data = _standby()
    data["recordings/heatSources/total/energyMonitoring/consumedEnergy"] = [
        {"d": "2026-11-10T10:00:00", "value": 5.0},
        {"d": "2026-11-10T11:00:00", "value": 5.0},
    ]
    data["recordings/heatSources/total/energyMonitoring/outputProduced"] = [
        {"d": "2026-11-10T10:00:00", "value": 20.0},
        {"d": "2026-11-10T11:00:00", "value": 20.0},
    ]
    data["recordings/heatSources/total/energyMonitoring/compressor"] = [
        {"d": "2026-11-10T10:00:00", "value": 5.0},
        {"d": "2026-11-10T11:00:00", "value": 5.0},
    ]
    now = datetime(2026, 11, 10, 13, 0, 0)
    snap = hp.build_snapshot_from_path_map(data, now=now)
    assert snap.consumed_today == 10.0
    assert snap.produced_today == 40.0
    assert snap.compressor_today == 10.0
    assert snap.cop("today") == 4.0


def test_hourly_sums_local_today_with_provisional_hour() -> None:
    """Local today only; current incomplete hour is excluded."""
    data = {
        "recordings/heatSources/total/energyMonitoring/consumedEnergy": [
            {"d": "2026-11-09T10:00:00", "value": 10.0},
            {"d": "2026-11-10T10:00:00", "value": 1.5},
            {"d": "2026-11-10T11:00:00", "value": 2.5},
        ],
        "recordings/heatSources/total/energyMonitoring/outputProduced": [
            {"d": "2026-11-09T10:00:00", "value": 40.0},
            {"d": "2026-11-10T10:00:00", "value": 5.0},
            {"d": "2026-11-10T11:00:00", "value": 7.0},
        ],
        "recordings/heatSources/total/energyMonitoring/compressor": [
            {"d": "2026-11-09T10:00:00", "value": 10.0},
            {"d": "2026-11-10T10:00:00", "value": 1.5},
            {"d": "2026-11-10T11:00:00", "value": 2.5},
        ],
    }
    # 12:06 → current hour 12:00 excluded; 10:00 and 11:00 settle.
    now = datetime(2026, 11, 10, 12, 6, 0)
    snap = hp.build_snapshot_from_path_map(data, now=now)
    assert snap.consumed_today == 4.0
    assert snap.produced_today == 12.0
    assert snap.compressor_today == 4.0
    assert snap.cop("today") == 3.0

    # Still both hours; current hour remains excluded.
    later = datetime(2026, 11, 10, 13, 6, 0)
    snap2 = hp.build_snapshot_from_path_map(data, now=later)
    assert snap2.consumed_today == 4.0
    assert snap2.produced_today == 12.0
    assert snap2.compressor_today == 4.0
    assert snap2.cop("today") == 3.0


def test_delta_skips_recording_list_and_uses_appliance() -> None:
    """Recording lists are ignored; appliance supply fills missing supply."""
    data = _standby()
    del data["heatSources/actualSupplyTemperature"]
    data["recordings/heatSources/actualSupplyTemperature"] = [
        {"d": "2026-11-10T10:00:00", "value": 99.0}
    ]
    data["heatSources/applianceSupplyTemperature"] = 44.4
    data["heatSources/returnTemperature"] = 40.5
    snap = hp.build_snapshot_from_path_map(data)
    assert snap.supply_temp is None
    assert snap.heat_source_delta == 3.9


def test_water_flow_does_not_mean_charging() -> None:
    """charge=stop keeps dhw_charging false regardless of flow."""
    data = _standby()
    data["dhwCircuits/dhw1/waterFlow"] = 5
    data["dhwCircuits/dhw1/charge"] = "stop"
    snap = hp.build_snapshot_from_path_map(data)
    assert snap.dhw_charging is False
    assert snap.dhw_requested is True


class _FakeObj:
    """Bosch-like object with path, get_property, and nested _data."""

    def __init__(
        self,
        path: str,
        attr_id: str,
        *,
        value=None,
        nested=None,
        kind: str = "regular",
        name: str = "x",
    ):
        self.path = path
        self.attr_id = attr_id
        self.kind = kind
        self.name = name
        self.sensors = []
        if nested is not None:
            self._data = nested
            self.state = False
        else:
            result = {"value": value} if value is not None else {}
            self._data = {attr_id: {"result": result, "uri": path, "type": kind}}
            self.state = "unavailable" if value is None else value

    def get_property(self, name):
        return self._data.get(name, {}).get("result", {})

    def get_value(self, name, default=None):
        return self.get_property(name).get("value", default)

    @property
    def get_data(self):
        return self._data


class _FakeGw:
    """Gateway with sensors list and get_circuits."""

    def __init__(self, sensors, circuits=None):
        self.sensors = sensors
        self._circuits = circuits or {}

    def get_circuits(self, ctype):
        return self._circuits.get(ctype, [])


def test_unupdated_type_is_not_heatpump() -> None:
    """Empty RESULT / unavailable state must not be treated as hs type."""
    sensor = _FakeObj("/heatSources/hs1/type", "type")
    snap = hp.build_snapshot_from_gateway(_FakeGw([sensor]))
    assert snap.hs_type is None
    assert snap.is_heatpump is False


def test_gateway_flattens_circuit_properties() -> None:
    """Circuit child keys become heatingCircuits/hc2/... snapshot fields."""
    circuit = _FakeObj(
        "/heatingCircuits/hc2",
        "hc2",
        nested={
            "status": {
                "result": {"value": "ACTIVE"},
                "uri": "/heatingCircuits/hc2/status",
                "type": "regular",
            },
            "pumpModulation": {
                "result": {"value": 100},
                "uri": "/heatingCircuits/hc2/pumpModulation",
                "type": "regular",
            },
            "supplyTemperatureSetpoint": {
                "result": {"value": 22},
                "uri": "/heatingCircuits/hc2/supplyTemperatureSetpoint",
                "type": "regular",
            },
        },
    )
    type_sensor = _FakeObj("/heatSources/hs1/type", "type", value="Heatpump")
    mod = _FakeObj("/heatSources/actualModulation", "actualModulation", value=40)
    supply = _FakeObj(
        "/heatSources/applianceSupplyTemperature",
        "applianceSupplyTemperature",
        value=22.4,
    )
    snap = hp.build_snapshot_from_gateway(
        _FakeGw([type_sensor, mod, supply], {"hc": [circuit]})
    )
    assert snap.is_heatpump
    assert snap.requesting_circuits == ["hc2"]
    assert snap.primary_circuit == "hc2"


def test_recording_hours_become_today_total() -> None:
    """Hourly recording lists are summed as consumedEnergy_Today_kWh."""
    rec = _FakeObj(
        "/recordings/heatSources/total/energyMonitoring/consumedEnergy",
        "consumedEnergy",
        value=[
            {"d": "2026-11-11T10:00:00", "value": 1.5},
            {"d": "2026-11-11T11:00:00", "value": 2.5},
        ],
        kind="recording",
    )
    # Freeze "now" via path map (gateway helper has no now arg).
    path_values = {
        rec.path: [
            {"d": "2026-11-11T10:00:00", "value": 1.5},
            {"d": "2026-11-11T11:00:00", "value": 2.5},
        ]
    }
    snap = hp.build_snapshot_from_path_map(
        path_values, now=datetime(2026, 11, 11, 13, 0, 0)
    )
    assert snap.consumed_today == 4.0
    assert snap.last_hour_electricity == 2.5


def test_cop_today_uses_compressor_not_consumed() -> None:
    """COP today divides produced by compressor kWh."""
    data = _standby()
    data["recordings/heatSources/total/energyMonitoring/compressor_Today_kWh"] = 2.0
    data["recordings/heatSources/total/energyMonitoring/outputProduced_Today_kWh"] = 7.0
    data["recordings/heatSources/total/energyMonitoring/consumedEnergy_Today_kWh"] = 1.0
    snap = hp.build_snapshot_from_path_map(data)
    assert snap.cop("today") == 3.5
    assert snap.compressor_today == 2.0


def test_empty_today_hours_are_zero_not_yesterday() -> None:
    """Yesterday-only hours yield today totals of 0.0."""
    data = {
        "recordings/heatSources/total/energyMonitoring/outputProduced": [
            {"d": "2026-11-12T22:00:00", "value": 8.0},
        ],
        "recordings/heatSources/total/energyMonitoring/compressor": [
            {"d": "2026-11-12T22:00:00", "value": 2.0},
        ],
    }
    snap = hp.build_snapshot_from_path_map(
        data, now=datetime(2026, 11, 13, 1, 6, 0)
    )
    assert snap.produced_today == 0.0
    assert snap.compressor_today == 0.0
    assert snap.cop("today") is None


def test_cop_today_includes_midnight_hour_at_0106() -> None:
    """Numeric today 00:00 settles by 01:06 (no extra closed-hour hold)."""
    data = {
        "recordings/heatSources/total/energyMonitoring/outputProduced": [
            {"d": "2026-11-13T00:00:00", "value": 7.0},
        ],
        "recordings/heatSources/total/energyMonitoring/compressor": [
            {"d": "2026-11-13T00:00:00", "value": 2.0},
        ],
    }
    snap = hp.build_snapshot_from_path_map(
        data, now=datetime(2026, 11, 13, 1, 6, 0)
    )
    assert snap.produced_today == 7.0
    assert snap.compressor_today == 2.0
    assert snap.cop("today") == 3.5


def test_cop_last_24h_spans_yesterday_and_today() -> None:
    """Rolling 24h sums settled hours across the day boundary."""
    data = {
        "recordings/heatSources/total/energyMonitoring/outputProduced": [
            {"d": "2026-11-12T00:00:00", "value": 1.0},  # outside 24h at 01:06
            {"d": "2026-11-12T22:00:00", "value": 8.0},
            {"d": "2026-11-13T00:00:00", "value": 7.0},
        ],
        "recordings/heatSources/total/energyMonitoring/compressor": [
            {"d": "2026-11-12T00:00:00", "value": 1.0},
            {"d": "2026-11-12T22:00:00", "value": 2.0},
            {"d": "2026-11-13T00:00:00", "value": 2.0},
        ],
    }
    # Window [2026-11-12 01:00, 2026-11-13 01:00)
    snap = hp.build_snapshot_from_path_map(
        data, now=datetime(2026, 11, 13, 1, 6, 0)
    )
    assert snap.produced_last_24h == 15.0
    assert snap.compressor_last_24h == 4.0
    assert snap.cop("last_24h") == 3.75
    assert snap.produced_today == 7.0
    assert snap.cop("today") == 3.5


def test_merge_energy_monitoring_hours_keeps_yesterday() -> None:
    """Day-roll merge retains yesterday numeric hours beside today."""
    previous = [
        {"d": "2026-11-12T22:00:00", "value": 8.0},
        {"d": "2026-11-12T23:00:00", "value": 3.0},
    ]
    current = [
        {"d": "2026-11-13T00:00:00", "value": 7.0},
        {"d": "2026-11-13T01:00:00", "value": "unavailable"},
    ]
    merged = hp.merge_energy_monitoring_hours(
        previous, current, now=datetime(2026, 11, 13, 1, 6, 0)
    )
    assert isinstance(merged, list)
    by_d = {row["d"]: row["value"] for row in merged}
    assert by_d["2026-11-12T22:00:00"] == 8.0
    assert by_d["2026-11-12T23:00:00"] == 3.0
    assert by_d["2026-11-13T00:00:00"] == 7.0


def test_unavailable_today_stubs_sum_to_zero() -> None:
    """Today rows that are only unavailable still count as empty today."""
    data = {
        "recordings/heatSources/total/energyMonitoring/outputProduced": [
            {"d": "2026-11-12T22:00:00", "value": 8.0},
            {"d": "2026-11-13T00:00:00", "value": "unavailable"},
            {"d": "2026-11-13T01:00:00", "value": "unavailable"},
        ],
        "recordings/heatSources/total/energyMonitoring/compressor": [
            {"d": "2026-11-12T22:00:00", "value": 2.0},
            {"d": "2026-11-13T00:00:00", "value": "unavailable"},
            {"d": "2026-11-13T01:00:00", "value": "unavailable"},
        ],
    }
    snap = hp.build_snapshot_from_path_map(
        data, now=datetime(2026, 11, 13, 1, 30, 0)
    )
    assert snap.produced_today == 0.0
    assert snap.compressor_today == 0.0
    assert snap.last_hour_heat == 8.0
    assert snap.last_hour_compressor == 2.0


def test_source_objects_skip_circuits_and_noise() -> None:
    """Poll matching sensors only; climate already updates circuits."""
    outdoor = _FakeObj(
        "/system/sensors/temperatures/outdoor_t1", "outdoor_t1", value=5
    )
    noise = _FakeObj("/gateway/uuid", "uuid", value="x")
    circuit = _FakeObj("/heatingCircuits/hc1", "hc1", nested={})
    child = _FakeObj(
        "/heatingCircuits/hc1/pumpModulation", "pumpModulation", value=10
    )
    circuit.sensors = [child]
    rec = _FakeObj(
        "/recordings/heatSources/total/energyMonitoring/consumedEnergy",
        "consumedEnergy",
        kind="recording",
    )
    gw = _FakeGw([outdoor, noise, rec], {"hc": [circuit]})
    sources = hp.heatpump_source_objects(gw)
    paths = {obj.path for obj in sources}
    assert outdoor.path in paths
    assert rec.path in paths
    assert circuit.path not in paths
    assert noise.path not in paths
    assert child.path not in paths
    assert hp.is_recording_source(rec)
