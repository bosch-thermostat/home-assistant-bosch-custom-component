"""Bosch sensor of circuit/zones entities."""

from ..const import CIRCUITS_SENSOR_NAMES
from .base import BoschBaseSensor


class CircuitSensor(BoschBaseSensor):
    """Representation of a Bosch sensor."""

    @property
    def device_name(self) -> str:
        """Device name."""
        if not self._circuit_type or not self._domain_name:
            return super().device_name
        return (
            CIRCUITS_SENSOR_NAMES.get(self._circuit_type, self._circuit_type)
            + " "
            + self._domain_name
        )

