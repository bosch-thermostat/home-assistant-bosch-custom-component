"""Pure heat-pump diagnostics from IVT/KM200 gateway paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

# Room sensor sentinel / impossible reading (e.g. -3276.8).
INVALID_ROOM_TEMP = -50.0
SUPPLY_MARGIN_C = 1.0
PUMP_CIRCULATION_PCT = 5.0
BACKUP_SHARE_WARN = 0.20
MIN_KWH_FOR_HINT = 1.0


@dataclass
class CircuitSnapshot:
    """One heating circuit snapshot."""

    circuit_id: str
    status: str | None = None
    pump_modulation: float | None = None
    supply_setpoint: float | None = None
    supply_actual: float | None = None
    room_temperature: float | None = None

    def matches_appliance_supply(self, appliance_supply: float | None) -> bool:
        """True when this circuit is receiving the appliance supply.

        Prefer actual circuit supply (buffer/AKU charge). Fall back to flow
        setpoint when actual is missing. Pump speed is not a heat request.
        Setpoint 0 means the circuit is off.
        """
        if (self.status or "").upper() != "ACTIVE":
            return False
        if (
            appliance_supply is None
            or self.supply_setpoint is None
            or self.supply_setpoint <= 0
        ):
            return False
        target = (
            self.supply_actual
            if self.supply_actual is not None
            else self.supply_setpoint
        )
        return abs(appliance_supply - target) <= SUPPLY_MARGIN_C

    @property
    def pump_running(self) -> bool:
        """Circuit pump at or above circulation threshold."""
        return (self.pump_modulation or 0) >= PUMP_CIRCULATION_PCT

    @property
    def room_sensor_fault(self) -> bool:
        """Room temperature looks like a gateway sentinel."""
        return (
            self.room_temperature is not None
            and self.room_temperature <= INVALID_ROOM_TEMP
        )


@dataclass
class HeatpumpSnapshot:
    """Normalized gateway values for classification."""

    hs_type: str | None = None
    actual_modulation: float = 0.0
    hs1_modulation: float = 0.0
    appliance_supply_temp: float | None = None
    supply_temp: float | None = None
    return_temp: float | None = None
    outdoor_temp: float | None = None
    dhw_charge: str | None = None
    dhw_actual: float | None = None
    dhw_setpoint: float | None = None
    pool_status: str | None = None
    pool_temp: float | None = None
    pool_setpoint: float | None = None
    circuits: list[CircuitSnapshot] = field(default_factory=list)
    consumed_today: float | None = None
    consumed_month: float | None = None
    consumed_year: float | None = None
    produced_today: float | None = None
    produced_month: float | None = None
    produced_year: float | None = None
    eheater_today: float | None = None
    eheater_month: float | None = None
    eheater_year: float | None = None
    compressor_today: float | None = None
    produced_last_24h: float | None = None
    compressor_last_24h: float | None = None
    last_hour_electricity: float | None = None
    last_hour_heat: float | None = None
    last_hour_eheater: float | None = None
    last_hour_compressor: float | None = None

    @property
    def is_heatpump(self) -> bool:
        """Whether heat source type is Heatpump."""
        return (self.hs_type or "").lower() == "heatpump"

    @property
    def compressor_on(self) -> bool:
        """Compressor active from modulation."""
        return self.actual_modulation > 0 or self.hs1_modulation > 0

    @property
    def dhw_charging(self) -> bool:
        """DHW charge active (charge path only)."""
        return (self.dhw_charge or "").lower() == "start"

    @property
    def dhw_requested(self) -> bool:
        """Water heating is requested while the DHW setpoint is not zero."""
        return self.dhw_setpoint is not None and self.dhw_setpoint != 0

    @property
    def pool_requested(self) -> bool:
        """Pool heating is requested while pool status is not off."""
        status = (self.pool_status or "").lower()
        return status not in ("", "off")

    @property
    def pool_heating(self) -> bool:
        """Pool requested and compressor running."""
        return self.pool_requested and self.compressor_on

    @property
    def dhw_gap(self) -> float | None:
        """Setpoint minus actual DHW temperature."""
        if self.dhw_setpoint is None or self.dhw_actual is None:
            return None
        return round(self.dhw_setpoint - self.dhw_actual, 2)

    @property
    def pool_gap(self) -> float | None:
        """Setpoint minus pool temperature."""
        if self.pool_setpoint is None or self.pool_temp is None:
            return None
        return round(self.pool_setpoint - self.pool_temp, 2)

    @property
    def heat_source_delta(self) -> float | None:
        """Supply minus return; appliance supply if heat-source supply missing."""
        supply = (
            self.supply_temp
            if self.supply_temp is not None
            else self.appliance_supply_temp
        )
        if supply is None or self.return_temp is None:
            return None
        return round(supply - self.return_temp, 2)

    @property
    def lead_supply_temp(self) -> float | None:
        """Appliance flow used to match requesting circuits."""
        if self.appliance_supply_temp is not None:
            return self.appliance_supply_temp
        return self.supply_temp

    @property
    def requesting_circuits(self) -> list[str]:
        """Circuits whose actual supply matches the appliance supply.

        Only while the compressor is on. A leftover supply temperature
        during circulation is not a heat request.
        """
        if not self.compressor_on:
            return []
        lead = self.lead_supply_temp
        return [
            c.circuit_id
            for c in self.circuits
            if c.matches_appliance_supply(lead)
        ]

    @property
    def heat_requestors(self) -> list[str]:
        """DHW, heating circuits, and pool. Any combination can be active.

        A circuit is included only while the compressor is on and the
        appliance supply matches that circuit's actual supply. More than
        one circuit can match; usually it is one.
        """
        names: list[str] = []
        if self.dhw_requested:
            names.append("dhw")
        names.extend(self.requesting_circuits)
        if self.pool_requested:
            names.append("pool")
        return names

    @property
    def space_heating_active(self) -> bool:
        """Any circuit requests heat."""
        return bool(self.requesting_circuits)

    @property
    def primary_circuit(self) -> str | None:
        """Leading heat demand circuit, else highest pump modulation.

        Prefer circuits whose actual supply matches the appliance. hc1 is
        often a buffer/tank that follows another circuit's flow; if any
        non-hc1 circuit is also requesting, pick among those instead.
        """
        requesting = self.requesting_circuits
        if requesting:
            by_id = {c.circuit_id: c for c in self.circuits}
            matched = [by_id[cid] for cid in requesting if cid in by_id]
            leaders = [c for c in matched if c.circuit_id != "hc1"]
            pool = leaders if leaders else matched
            if pool:
                best = max(
                    pool,
                    key=lambda c: (
                        c.pump_modulation if c.pump_modulation is not None else -1.0
                    ),
                )
                return best.circuit_id
        if not self.circuits:
            return None
        best = max(
            self.circuits,
            key=lambda c: c.pump_modulation if c.pump_modulation is not None else -1.0,
        )
        if best.pump_modulation is None:
            return None
        return best.circuit_id

    @property
    def circulation(self) -> bool:
        """Any circuit pump running while compressor is off."""
        return (not self.compressor_on) and any(c.pump_running for c in self.circuits)

    def _ratio(self, num: float | None, den: float | None) -> float | None:
        if num is None or den is None or den <= 0:
            return None
        return round(num / den, 2)

    def cop(self, period: str) -> float | None:
        """COP for today/last_24h/month/year.

        Today and last 24h use compressor kWh (IVA heat-pump slice). Month/year
        still use consumed electricity (no compressor period totals).
        """
        if period == "today":
            return self._ratio(self.produced_today, self.compressor_today)
        if period == "last_24h":
            return self._ratio(self.produced_last_24h, self.compressor_last_24h)
        mapping = {
            "month": (self.produced_month, self.consumed_month),
            "year": (self.produced_year, self.consumed_year),
        }
        produced, consumed = mapping[period]
        return self._ratio(produced, consumed)

    def backup_share(self, period: str) -> float | None:
        """E-heater share of consumed electricity (0-1)."""
        mapping = {
            "today": (self.eheater_today, self.consumed_today),
            "month": (self.eheater_month, self.consumed_month),
            "year": (self.eheater_year, self.consumed_year),
        }
        eheater, consumed = mapping[period]
        return self._ratio(eheater, consumed)


def classify_heatpump_mode(snapshot: HeatpumpSnapshot) -> str:
    """Classify operating mode from a snapshot."""
    pool = snapshot.pool_heating
    dhw = snapshot.dhw_charging
    space = snapshot.space_heating_active
    compressor = snapshot.compressor_on

    if compressor and pool and (dhw or space):
        return "pool_and_heating"
    if compressor and pool:
        return "pool"
    if compressor and dhw and space:
        return "dhw_and_heating"
    if compressor and dhw:
        return "dhw"
    if compressor and space:
        return "space_heating"
    if compressor:
        return "compressor"
    if snapshot.circulation:
        return "circulation"
    return "idle"


def _cop_min_for_outdoor(outdoor: float | None) -> float:
    """Minimum acceptable COP for outdoor temperature."""
    if outdoor is None:
        return 2.3
    if outdoor >= 5:
        return 2.8
    if outdoor >= 0:
        return 2.3
    if outdoor >= -7:
        return 1.8
    return 1.5


def classify_efficiency_hint(snapshot: HeatpumpSnapshot) -> tuple[str, dict[str, Any]]:
    """Return efficiency hint and diagnostic attributes."""
    cop_today = snapshot.cop("today")
    backup = snapshot.backup_share("today")
    outdoor = snapshot.outdoor_temp
    cop_min = _cop_min_for_outdoor(outdoor)
    spread = snapshot.heat_source_delta
    attrs = {
        "cop_today": cop_today,
        "backup_share": backup,
        "outdoor": outdoor,
        "cop_min": cop_min,
        "spread": spread,
    }
    consumed = snapshot.consumed_today
    if consumed is None or consumed < MIN_KWH_FOR_HINT or snapshot.produced_today is None:
        return "unknown", attrs
    if backup is not None and backup >= BACKUP_SHARE_WARN:
        return "check_backup", attrs
    if cop_today is not None and cop_today < cop_min:
        return "check_cop", attrs
    if (
        snapshot.compressor_on
        and spread is not None
        and abs(spread) < SUPPLY_MARGIN_C
    ):
        return "check_spread", attrs
    return "ok", attrs


def _as_float(value: Any) -> float | None:
    """Parse float or return None."""
    if value in (None, "", "unavailable"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _is_scalar(value: Any) -> bool:
    """True for a live reading (not a recording list/dict payload)."""
    return value is not None and not isinstance(value, (list, dict, bool))


def _path_value(index: dict[str, Any], *suffixes: str) -> Any:
    """Return matching scalar; suffixes are tried in priority order."""
    for suffix in suffixes:
        clean = suffix.lstrip("/")
        exact_recording: Any = None
        suffix_live: Any = None
        for path, value in index.items():
            if not _is_scalar(value):
                continue
            norm = path.lstrip("/")
            recording = norm.startswith("recordings/")
            if norm == clean:
                if recording:
                    if exact_recording is None:
                        exact_recording = value
                else:
                    return value
            elif norm.endswith(clean) and not recording:
                if suffix_live is None:
                    suffix_live = value
        if suffix_live is not None:
            return suffix_live
        if exact_recording is not None:
            return exact_recording
    return None


def _latest_hour_value(value: Any) -> float | None:
    """Latest numeric hourly recording row ({d, value} or {d, y})."""
    rows: list[Any] | None = None
    if isinstance(value, list):
        rows = value
    elif isinstance(value, dict) and isinstance(value.get("value"), list):
        rows = value["value"]
    if not rows:
        return None
    best_num: float | None = None
    best_stamp: Any = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = row.get("value", row.get("y"))
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        stamp = row.get("d")
        if best_num is None or (
            stamp is not None and (best_stamp is None or stamp > best_stamp)
        ):
            best_num = number
            best_stamp = stamp
    return best_num


def _recording_hour(index: dict[str, Any], marker: str) -> float | None:
    """Latest hour from a recording series, ignoring Today/Month/Year totals."""
    for path, value in index.items():
        if marker not in path:
            continue
        if any(token in path for token in ("Today", "ThisMonth", "ThisYear")):
            continue
        found = _latest_hour_value(value)
        if found is not None:
            return found
    return None


def build_snapshot_from_path_map(
    path_values: dict[str, Any],
    *,
    now: datetime | None = None,
) -> HeatpumpSnapshot:
    """Build snapshot from path → raw value map (tests and gateway adapter)."""
    path_values = _with_recording_today_totals(path_values, now=now)
    index = {p.lstrip("/"): v for p, v in path_values.items()}

    circuits: list[CircuitSnapshot] = []
    circuit_ids: set[str] = set()
    for path in index:
        if "/heatingCircuits/" in f"/{path}" or path.startswith("heatingCircuits/"):
            parts = path.split("/")
            try:
                idx = parts.index("heatingCircuits")
                circuit_ids.add(parts[idx + 1])
            except (ValueError, IndexError):
                continue
    for cid in sorted(circuit_ids):
        prefix = f"heatingCircuits/{cid}"
        room = _as_float(_path_value(index, f"{prefix}/roomtemperature"))
        circuits.append(
            CircuitSnapshot(
                circuit_id=cid,
                status=_path_value(index, f"{prefix}/status"),
                pump_modulation=_as_float(
                    _path_value(index, f"{prefix}/pumpModulation")
                ),
                supply_setpoint=_as_float(
                    _path_value(index, f"{prefix}/supplyTemperatureSetpoint")
                ),
                supply_actual=_as_float(
                    _path_value(index, f"{prefix}/actualSupplyTemperature")
                ),
                room_temperature=room,
            )
        )

    return HeatpumpSnapshot(
        hs_type=_path_value(index, "heatSources/hs1/type"),
        actual_modulation=_as_float(
            _path_value(index, "heatSources/actualModulation")
        )
        or 0.0,
        appliance_supply_temp=_as_float(
            _path_value(
                index,
                "heatSources/applianceSupplyTemperature",
                "system/appliance/actualSupplyTemperature",
            )
        ),
        hs1_modulation=_as_float(
            _path_value(index, "heatSources/hs1/actualModulation")
        )
        or 0.0,
        supply_temp=_as_float(
            _path_value(
                index,
                "system/appliance/actualSupplyTemperature",
                "heatSources/actualSupplyTemperature",
                "system/sensors/temperatures/supply_t1",
            )
        ),
        return_temp=_as_float(
            _path_value(
                index,
                "system/sensors/temperatures/return",
                "heatSources/returnTemperature",
            )
        ),
        outdoor_temp=_as_float(
            _path_value(index, "system/sensors/temperatures/outdoor_t1")
        ),
        dhw_charge=_path_value(index, "dhwCircuits/dhw1/charge"),
        dhw_actual=_as_float(_path_value(index, "dhwCircuits/dhw1/actualTemp")),
        dhw_setpoint=_as_float(
            _path_value(index, "dhwCircuits/dhw1/currentSetpoint")
        ),
        pool_status=_path_value(index, "heatSources/poolStatus"),
        pool_temp=_as_float(_path_value(index, "heatSources/poolTemperature")),
        pool_setpoint=_as_float(
            _path_value(index, "heatSources/poolSetpointTemperature")
        ),
        circuits=circuits,
        consumed_today=_as_float(
            _path_value(
                index,
                "recordings/heatSources/total/energyMonitoring/consumedEnergy_Today_kWh",
            )
        ),
        consumed_month=_as_float(
            _path_value(
                index,
                "recordings/heatSources/total/energyMonitoring/consumedEnergy_ThisMonth_kWh",
            )
        ),
        consumed_year=_as_float(
            _path_value(
                index,
                "recordings/heatSources/total/energyMonitoring/consumedEnergy_ThisYear_kWh",
            )
        ),
        produced_today=_as_float(
            _path_value(
                index,
                "recordings/heatSources/total/energyMonitoring/outputProduced_Today_kWh",
            )
        ),
        produced_month=_as_float(
            _path_value(
                index,
                "recordings/heatSources/total/energyMonitoring/outputProduced_ThisMonth_kWh",
            )
        ),
        produced_year=_as_float(
            _path_value(
                index,
                "recordings/heatSources/total/energyMonitoring/outputProduced_ThisYear_kWh",
            )
        ),
        eheater_today=_as_float(
            _path_value(
                index,
                "recordings/heatSources/total/energyMonitoring/eheater_Today_kWh",
            )
        ),
        eheater_month=_as_float(
            _path_value(
                index,
                "recordings/heatSources/total/energyMonitoring/eheater_ThisMonth_kWh",
            )
        ),
        eheater_year=_as_float(
            _path_value(
                index,
                "recordings/heatSources/total/energyMonitoring/eheater_ThisYear_kWh",
            )
        ),
        compressor_today=_as_float(
            _path_value(
                index,
                "recordings/heatSources/total/energyMonitoring/compressor_Today_kWh",
            )
        ),
        produced_last_24h=_as_float(
            _path_value(
                index,
                "recordings/heatSources/total/energyMonitoring/outputProduced_Last24h_kWh",
            )
        ),
        compressor_last_24h=_as_float(
            _path_value(
                index,
                "recordings/heatSources/total/energyMonitoring/compressor_Last24h_kWh",
            )
        ),
        last_hour_electricity=_recording_hour(index, "consumedEnergy"),
        last_hour_heat=_recording_hour(index, "outputProduced"),
        last_hour_eheater=_recording_hour(index, "eheater"),
        last_hour_compressor=_recording_hour(index, "compressor"),
    )


_MISSING_STRINGS = ("unavailable", "invalid")
_RECORDING_KINDS = ("recording", "energy", "ecus_recording")
_SOURCE_MARKERS = (
    "hs1/type",
    "actualModulation",
    "applianceSupplyTemperature",
    "actualSupplyTemperature",
    "returnTemperature",
    "temperatures/return",
    "outdoor_t1",
    "dhw1/charge",
    "dhw1/actualTemp",
    "dhw1/currentSetpoint",
    "poolStatus",
    "poolTemperature",
    "poolSetpointTemperature",
    "energyMonitoring",
)


def _is_missing(value: Any) -> bool:
    """True when a Bosch object has no usable reading yet."""
    if value is None or value == "":
        return True
    if isinstance(value, bool):
        return True
    if isinstance(value, str) and value.lower() in _MISSING_STRINGS:
        return True
    return False


def _obj_data(obj: Any) -> dict[str, Any] | None:
    """Library ``get_data`` dict (property or method) or ``_data``."""
    data = getattr(obj, "get_data", None)
    if callable(data):
        try:
            data = data()
        except Exception:  # noqa: BLE001
            data = None
    if isinstance(data, dict):
        return data
    data = getattr(obj, "_data", None)
    return data if isinstance(data, dict) else None


def _obj_value(obj: Any) -> Any:
    """Scalar value from a Bosch sensor or circuit object."""
    attr = getattr(obj, "attr_id", None) or getattr(obj, "path", None)
    if hasattr(obj, "get_value") and attr:
        try:
            val = obj.get_value(attr)
        except Exception:  # noqa: BLE001
            val = None
        if not _is_missing(val):
            return val
    if hasattr(obj, "get_property") and attr:
        try:
            prop = obj.get_property(attr)
        except Exception:  # noqa: BLE001
            prop = None
        if isinstance(prop, dict) and "value" in prop:
            val = prop["value"]
            if not _is_missing(val):
                return val
        if prop is not None and not isinstance(prop, dict) and not _is_missing(prop):
            return prop
    state = getattr(obj, "state", None)
    if not _is_missing(state):
        return state
    return None


def _property_recording_rows(obj: Any) -> list[Any] | None:
    """Hour rows from ``get_property``, same path RecordingSensor uses."""
    attr = getattr(obj, "attr_id", None) or getattr(obj, "path", None)
    if not attr or not hasattr(obj, "get_property"):
        return None
    try:
        prop = obj.get_property(attr)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(prop, dict):
        return _recording_hour_rows(prop.get("value"))
    return _recording_hour_rows(prop)


def _obj_path_values(obj: Any) -> dict[str, Any]:
    """URI → value map from one Bosch object, including circuit children."""
    out: dict[str, Any] = {}
    path = getattr(obj, "path", None) or getattr(obj, "attr_id", None)
    data = _obj_data(obj)
    if data:
        base = str(path or "").rstrip("/")
        for key, item in data.items():
            if not isinstance(item, dict):
                continue
            result = item.get("result")
            val = result.get("value") if isinstance(result, dict) else None
            if _is_missing(val) and hasattr(obj, "get_value"):
                try:
                    val = obj.get_value(key)
                except Exception:  # noqa: BLE001
                    val = None
            if _is_missing(val):
                continue
            uri = item.get("uri") or item.get("id")
            if not uri:
                uri = f"{base}/{key}" if base else key
            out[str(uri)] = val
    if path:
        path_key = str(path)
        # RecordingSensor stores hours under get_property; _data may lack them
        # or only hold a non-list value. Prefer the property hour list when
        # this path has no rows yet so COP can sum after the hourly pull.
        if _recording_hour_rows(out.get(path_key)) is None:
            rows = _property_recording_rows(obj)
            if rows is not None:
                out[path_key] = rows
        if path_key not in out:
            val = _obj_value(obj)
            if not _is_missing(val):
                out[path_key] = val
    return _with_recording_today_totals(out)


def _recording_hour_rows(value: Any) -> list[Any] | None:
    """Hourly recording rows, or None when value is not a list payload."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("value"), list):
        return value["value"]
    return None


def _stamp_datetime(stamp: Any) -> datetime | None:
    """Parse a recording stamp to datetime."""
    if isinstance(stamp, datetime):
        return stamp
    if stamp is None:
        return None
    text = str(stamp).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _day_key(stamp: Any) -> str | None:
    """YYYY-MM-DD for a recording stamp."""
    parsed = _stamp_datetime(stamp)
    if parsed is not None:
        return parsed.date().isoformat()
    text = str(stamp)
    return text[:10] if len(text) >= 10 else None


def _hour_cutoff(now: datetime) -> datetime:
    """Start of the current wall-clock hour (still incomplete)."""
    cutoff = now.replace(minute=0, second=0, microsecond=0)
    if cutoff.tzinfo is None and now.tzinfo is not None:
        cutoff = cutoff.replace(tzinfo=now.tzinfo)
    return cutoff


def _sum_hour_rows_local_today(
    value: Any,
    *,
    now: datetime | None = None,
) -> float | None:
    """Sum numeric hourly rows for local today, excluding the current hour.

    Returns 0.0 when a list exists but today has no settled numeric rows.
    Returns None when value is not an hourly list.
    """
    rows = _recording_hour_rows(value)
    if rows is None:
        return None
    clock = now or datetime.now().astimezone()
    today = clock.date().isoformat()
    cutoff = _hour_cutoff(clock)
    total = 0.0
    found = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        stamp = row.get("d")
        if stamp is None or _day_key(stamp) != today:
            continue
        parsed = _stamp_datetime(stamp)
        if parsed is not None:
            if parsed.tzinfo is None and cutoff.tzinfo is not None:
                parsed = parsed.replace(tzinfo=cutoff.tzinfo)
            if parsed >= cutoff:
                continue
        number = _as_float(row.get("value", row.get("y")))
        if number is None:
            continue
        total += number
        found = True
    return round(total, 2) if found else 0.0


def _sum_hour_rows_last_hours(
    value: Any,
    *,
    hours: int = 24,
    now: datetime | None = None,
) -> float | None:
    """Sum numeric hourly rows in [now-hours, current hour).

    Returns 0.0 when a list exists but the window has no settled numeric rows.
    Returns None when value is not an hourly list.
    """
    rows = _recording_hour_rows(value)
    if rows is None:
        return None
    clock = now or datetime.now().astimezone()
    cutoff = _hour_cutoff(clock)
    window_start = cutoff - timedelta(hours=hours)
    total = 0.0
    found = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = _stamp_datetime(row.get("d"))
        if parsed is None:
            continue
        if parsed.tzinfo is None and cutoff.tzinfo is not None:
            parsed = parsed.replace(tzinfo=cutoff.tzinfo)
        if parsed < window_start or parsed >= cutoff:
            continue
        number = _as_float(row.get("value", row.get("y")))
        if number is None:
            continue
        total += number
        found = True
    return round(total, 2) if found else 0.0


def _sum_hour_rows_latest_day(value: Any) -> float | None:
    """Sum numeric hourly rows for the latest calendar day only."""
    rows = _recording_hour_rows(value)
    if not rows:
        return None
    latest_day: str | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = _day_key(row.get("d"))
        if day is None:
            continue
        if latest_day is None or day > latest_day:
            latest_day = day
    if latest_day is None:
        return None
    total = 0.0
    found = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _day_key(row.get("d")) != latest_day:
            continue
        number = _as_float(row.get("value", row.get("y")))
        if number is None:
            continue
        total += number
        found = True
    return round(total, 2) if found else None


def _with_recording_today_totals(
    path_values: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Expose hourly energy lists as ``*_Today_kWh`` and ``*_Last24h_kWh``.

    When an hourly list exists it wins over a scalar ``*_Today_kWh`` so a
    stale Bosch daily total cannot override an empty new local day.
    """
    extra: dict[str, Any] = {}
    for path, value in path_values.items():
        if "Today" in path or "Last24h" in path:
            continue
        if "energyMonitoring" not in path:
            continue
        if _recording_hour_rows(value) is None:
            continue
        today_total = _sum_hour_rows_local_today(value, now=now)
        if today_total is not None:
            extra[f"{path}_Today_kWh"] = today_total
        roll_total = _sum_hour_rows_last_hours(value, hours=24, now=now)
        if roll_total is not None:
            extra[f"{path}_Last24h_kWh"] = roll_total
    if extra:
        return {**path_values, **extra}
    return path_values


def merge_energy_monitoring_hours(
    previous: Any,
    current: Any,
    *,
    now: datetime | None = None,
) -> Any:
    """Merge yesterday+today hourly rows so rolling 24h survives day roll.

    Same-stamp numeric current wins; previous numeric kept when current is
    unavailable. Rows older than 48h before the current hour are dropped.
    Returns ``current`` unchanged when it is not an hourly list shape.
    """
    prev_rows = _recording_hour_rows(previous)
    curr_rows = _recording_hour_rows(current)
    if curr_rows is None and prev_rows is None:
        return current
    if curr_rows is None:
        return previous if prev_rows is not None else current
    if not prev_rows:
        return current

    clock = now or datetime.now().astimezone()
    cutoff = _hour_cutoff(clock)
    keep_after = cutoff - timedelta(hours=48)

    merged: dict[str, dict[str, Any]] = {}

    def _ingest(rows: list[Any], *, prefer_numeric: bool) -> None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            stamp = row.get("d")
            if stamp is None:
                continue
            key = str(stamp)
            parsed = _stamp_datetime(stamp)
            if parsed is not None:
                if parsed.tzinfo is None and cutoff.tzinfo is not None:
                    parsed = parsed.replace(tzinfo=cutoff.tzinfo)
                if parsed < keep_after:
                    continue
            number = _as_float(row.get("value", row.get("y")))
            existing = merged.get(key)
            if existing is None:
                merged[key] = dict(row)
                continue
            if prefer_numeric and number is not None:
                merged[key] = dict(row)
            elif (
                prefer_numeric
                and number is None
                and _as_float(existing.get("value", existing.get("y"))) is not None
            ):
                continue
            elif not prefer_numeric and number is not None:
                if _as_float(existing.get("value", existing.get("y"))) is None:
                    merged[key] = dict(row)

    _ingest(prev_rows, prefer_numeric=False)
    _ingest(curr_rows, prefer_numeric=True)

    out_rows = sorted(merged.values(), key=lambda r: str(r.get("d")))
    if isinstance(current, list):
        return out_rows
    if isinstance(current, dict):
        return {**current, "value": out_rows}
    if isinstance(previous, list):
        return out_rows
    if isinstance(previous, dict):
        return {**previous, "value": out_rows}
    return out_rows


def _object_path(obj: Any) -> str:
    """API path or attr id for matching."""
    return str(getattr(obj, "path", None) or getattr(obj, "attr_id", None) or "")


def is_recording_source(obj: Any) -> bool:
    """True when the object is fetched on the hourly recording schedule."""
    kind = str(getattr(obj, "kind", "") or "").lower()
    return kind in _RECORDING_KINDS


def object_matches_heatpump_source(obj: Any) -> bool:
    """True when this object is needed to build a heat-pump snapshot."""
    path = _object_path(obj).lower()
    if not path:
        return False
    return any(marker.lower() in path for marker in _SOURCE_MARKERS)


def heatpump_source_objects(gateway: Any) -> list[Any]:
    """Bosch sensors the virtual snapshot must poll.

    Heating and DHW circuits are already polled by climate / water heater.
    Do not register those objects here — one circuit update fetches every
    child URI and would stall startup.
    """
    objs: list[Any] = []
    seen: set[int] = set()
    sensors = getattr(gateway, "sensors", None)
    if isinstance(sensors, dict):
        sensor_iter = sensors.values()
    else:
        try:
            sensor_iter = list(sensors or [])
        except TypeError:
            sensor_iter = []
    for obj in sensor_iter:
        if obj is None or not object_matches_heatpump_source(obj):
            continue
        key = id(obj)
        if key in seen:
            continue
        seen.add(key)
        objs.append(obj)
    return objs


def _iter_gateway_objects(gateway: Any) -> list[Any]:
    """Sensors plus circuit objects from a live gateway."""
    objs: list[Any] = []
    sensors = getattr(gateway, "sensors", None)
    if isinstance(sensors, dict):
        objs.extend(sensors.values())
    elif sensors:
        try:
            objs.extend(list(sensors))
        except TypeError:
            pass
    getter = getattr(gateway, "get_circuits", None)
    if not getter:
        return objs
    for ctype in ("hc", "dhw", "sc", "zn", "dv"):
        try:
            circuits = getter(ctype) or []
        except Exception:  # noqa: BLE001
            continue
        for circuit in circuits:
            objs.append(circuit)
            circ_sensors = getattr(circuit, "sensors", None)
            if isinstance(circ_sensors, dict):
                objs.extend(circ_sensors.values())
            elif circ_sensors:
                try:
                    objs.extend(list(circ_sensors))
                except TypeError:
                    continue
    return objs


def heating_circuit_ids(gateway: Any, snapshot: HeatpumpSnapshot | None = None) -> list[str]:
    """Heating circuit ids from the gateway, then from a snapshot."""
    ids: list[str] = []
    getter = getattr(gateway, "get_circuits", None)
    if getter:
        try:
            for circuit in getter("hc") or []:
                raw = (
                    getattr(circuit, "id", None)
                    or getattr(circuit, "attr_id", None)
                    or getattr(circuit, "name", None)
                )
                if not raw:
                    continue
                cid = str(raw).rstrip("/").split("/")[-1]
                if cid and cid not in ids:
                    ids.append(cid)
        except Exception:  # noqa: BLE001
            pass
    if snapshot:
        for circuit in snapshot.circuits:
            if circuit.circuit_id not in ids:
                ids.append(circuit.circuit_id)
    return ids


def build_snapshot_from_gateway(gateway: Any) -> HeatpumpSnapshot:
    """Collect path values from gateway sensors/circuits into a snapshot."""
    path_values: dict[str, Any] = {}
    for obj in _iter_gateway_objects(gateway):
        path_values.update(_obj_path_values(obj))
    return build_snapshot_from_path_map(path_values)
