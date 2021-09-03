from .base import BoschBaseSensor

from ..const import (
    CIRCUITS_SENSOR_NAMES,
    SIGNAL_SOLAR_UPDATE_BOSCH,
)


class CircuitSensor(BoschBaseSensor):
    """Representation of a Bosch sensor."""

    @property
    def _sensor_name(self):
        return CIRCUITS_SENSOR_NAMES[self._circuit_type] + " " + self._domain_name

    @property
    def signal(self):
        return SIGNAL_SOLAR_UPDATE_BOSCH
