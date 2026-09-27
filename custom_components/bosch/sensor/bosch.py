"""Bosch regular sensor."""
from .base import BoschBaseSensor


class BoschSensor(BoschBaseSensor):
    """Representation of a Bosch sensor."""

    _domain_name = "Sensors"

    @property
    def device_name(self) -> str:
        return "Bosch sensors"

