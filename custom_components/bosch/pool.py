"""KM200 pool path helpers (no Home Assistant import)."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

POOL_STATUS_PATH = "heatSources/poolStatus"
POOL_TEMP_PATH = "heatSources/poolTemperature"
POOL_SETPOINT_PATH = "heatSources/poolSetpointTemperature"

POOL_PATHS = (POOL_STATUS_PATH, POOL_TEMP_PATH, POOL_SETPOINT_PATH)

POOL_STATUS_ON = "on"
POOL_STATUS_OFF = "off"

HVAC_HEAT = "heat"
HVAC_OFF = "off"

DEFAULT_MIN_TEMP = 8.0
DEFAULT_MAX_TEMP = 40.0
DEFAULT_TEMP_STEP = 0.5


def normalize_path(path: str | None) -> str:
    """Strip leading slashes for path comparison."""
    return str(path or "").lstrip("/")


def path_matches(path: str | None, suffix: str) -> bool:
    """True when path equals or ends with the pool suffix."""
    norm = normalize_path(path)
    clean = normalize_path(suffix)
    return bool(norm) and (norm == clean or norm.endswith(clean))


def is_pool_path(path: str | None) -> bool:
    """True when path is one of the three pool URIs."""
    return any(path_matches(path, suffix) for suffix in POOL_PATHS)


def status_to_hvac(status: str | None) -> str:
    """Map gateway poolStatus to HVAC mode."""
    if status is None or str(status).strip().lower() in ("", "off"):
        return HVAC_OFF
    return HVAC_HEAT


def hvac_to_status(hvac_mode: str) -> str:
    """Map HVAC mode to gateway poolStatus write value."""
    if str(hvac_mode).lower() == HVAC_OFF:
        return POOL_STATUS_OFF
    return POOL_STATUS_ON


def as_float(value: Any) -> float | None:
    """Parse float or return None."""
    if value in (None, "", "unavailable", "invalid"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_scalar(obj: Any) -> Any:
    """Scalar value from a Bosch sensor or raw_query payload."""
    if obj is None:
        return None
    if isinstance(obj, (int, float, str, bool)):
        return obj
    if isinstance(obj, dict):
        if "value" in obj and not isinstance(obj["value"], (list, dict)):
            return obj["value"]
        result = obj.get("result")
        if isinstance(result, dict) and "value" in result:
            return result["value"]
        return None
    attr = getattr(obj, "attr_id", None) or getattr(obj, "path", None)
    if hasattr(obj, "get_value") and attr:
        try:
            val = obj.get_value(attr)
        except Exception:  # noqa: BLE001
            val = None
        if val not in (None, "", "unavailable", "invalid"):
            return val
    if hasattr(obj, "get_property") and attr:
        try:
            prop = obj.get_property(attr)
        except Exception:  # noqa: BLE001
            prop = None
        if isinstance(prop, dict) and "value" in prop:
            return prop["value"]
        if prop is not None and not isinstance(prop, dict):
            return prop
    state = getattr(obj, "state", None)
    if state not in (None, "", "unavailable", "invalid"):
        return state
    return None


def _object_path(obj: Any) -> str:
    """API path or attr id for matching."""
    return str(getattr(obj, "path", None) or getattr(obj, "attr_id", None) or "")


def iter_gateway_sensors(gateway: Any) -> list[Any]:
    """List sensor objects without touching circuits."""
    sensors = getattr(gateway, "sensors", None)
    if isinstance(sensors, dict):
        return [o for o in sensors.values() if o is not None]
    if not sensors:
        return []
    try:
        return [o for o in list(sensors) if o is not None]
    except TypeError:
        return []


def find_pool_sensors(gateway: Any) -> dict[str, Any]:
    """Map pool path suffix → existing gateway sensor object."""
    found: dict[str, Any] = {}
    for obj in iter_gateway_sensors(gateway):
        path = _object_path(obj)
        for suffix in POOL_PATHS:
            if path_matches(path, suffix) and suffix not in found:
                found[suffix] = obj
    return found


def gateway_has_pool_sensors(gateway: Any) -> bool:
    """True when any pool sensor object is already on the gateway."""
    return bool(find_pool_sensors(gateway))


async def probe_pool_status(gateway: Any) -> bool:
    """True when a one-shot raw_query of poolStatus succeeds."""
    raw_query = getattr(gateway, "raw_query", None)
    if not callable(raw_query):
        return False
    for candidate in (f"/{POOL_STATUS_PATH}", POOL_STATUS_PATH):
        try:
            result = await raw_query(candidate)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Pool probe %s failed: %s", candidate, err)
            continue
        value = extract_scalar(result)
        if value is not None:
            return True
    return False


async def async_pool_available(gateway: Any) -> bool:
    """True when pool climate should be created."""
    if gateway_has_pool_sensors(gateway):
        return True
    return await probe_pool_status(gateway)


class PoolPoller:
    """Coordinator-backed poller for the three pool paths.

    Prefer existing gateway.sensors objects (shared with diagnostics via
    refcount). Otherwise fetch via gateway.raw_query.
    """

    def __init__(self, gateway: Any) -> None:
        """Bind to gateway and resolve sensor objects."""
        self.gateway = gateway
        self.name = "Pool"
        self._sensors = find_pool_sensors(gateway)
        self.status: str | None = None
        self.current_temp: float | None = None
        self.target_temp: float | None = None
        self.min_temp = DEFAULT_MIN_TEMP
        self.max_temp = DEFAULT_MAX_TEMP
        self._apply_limits_from_setpoint_object()

    def _apply_limits_from_setpoint_object(self) -> None:
        """Use setpoint object min/max when present."""
        obj = self._sensors.get(POOL_SETPOINT_PATH)
        if obj is None:
            return
        min_v = as_float(getattr(obj, "min_temp", None) or getattr(obj, "min_value", None))
        max_v = as_float(getattr(obj, "max_temp", None) or getattr(obj, "max_value", None))
        if min_v is not None:
            self.min_temp = min_v
        if max_v is not None:
            self.max_temp = max_v

    @property
    def sensor_objects(self) -> list[Any]:
        """Bosch objects that should be registered with the coordinator."""
        return list(self._sensors.values())

    def uses_raw_query(self) -> bool:
        """True when no sensor objects cover all three paths."""
        return len(self._sensors) < len(POOL_PATHS)

    def _store(self, path: str, value: Any) -> None:
        """Update cached field from a path/value pair."""
        if path_matches(path, POOL_STATUS_PATH):
            if value is None:
                self.status = None
            else:
                self.status = str(value)
        elif path_matches(path, POOL_TEMP_PATH):
            self.current_temp = as_float(value)
        elif path_matches(path, POOL_SETPOINT_PATH):
            self.target_temp = as_float(value)

    async def update(self, _time: Any = None) -> None:
        """Refresh pool values from sensors and/or raw_query."""
        for path, obj in self._sensors.items():
            try:
                await obj.update()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Pool sensor update %s failed: %s", path, err)
            self._store(path, extract_scalar(obj))

        missing = [p for p in POOL_PATHS if p not in self._sensors]
        raw_query = getattr(self.gateway, "raw_query", None)
        if missing and callable(raw_query):
            for path in missing:
                try:
                    result = await raw_query(f"/{path}")
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Pool raw_query /%s failed: %s", path, err)
                    continue
                self._store(path, extract_scalar(result))

    async def async_set_status(self, status: str) -> None:
        """Write poolStatus via raw_put."""
        await self.gateway.raw_put(path=f"/{POOL_STATUS_PATH}", value=status)

    async def async_set_temperature(self, temperature: float) -> None:
        """Write poolSetpointTemperature via raw_put."""
        await self.gateway.raw_put(path=f"/{POOL_SETPOINT_PATH}", value=temperature)
