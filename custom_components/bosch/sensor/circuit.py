"""Bosch sensor of circuit/zones entities."""

from ..const import CIRCUITS_SENSOR_NAMES, SIGNAL_SOLAR_UPDATE_BOSCH
from .base import BoschBaseSensor


class CircuitSensor(BoschBaseSensor):
    """Representation of a Bosch sensor."""

    signal = SIGNAL_SOLAR_UPDATE_BOSCH

    @property
    def device_name(self):
        """Device name."""
        return (
            CIRCUITS_SENSOR_NAMES[self._circuit_type] + " " + self._domain_name
        )
