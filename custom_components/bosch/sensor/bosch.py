"""Bosch regular sensor."""
from ..const import SIGNAL_SENSOR_UPDATE_BOSCH
from .base import BoschBaseSensor


class BoschSensor(BoschBaseSensor):
    """Representation of a Bosch sensor."""

    signal = SIGNAL_SENSOR_UPDATE_BOSCH
    _domain_name = "Sensors"

    @property
    def device_name(self):
        return "Bosch sensors"
