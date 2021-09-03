from ..const import SIGNAL_SENSOR_UPDATE_BOSCH
from .base import BoschBaseSensor


class BoschSensor(BoschBaseSensor):
    """Representation of a Bosch sensor."""

    @property
    def _sensor_name(self):
        return "Bosch sensors"

    @property
    def signal(self):
        return SIGNAL_SENSOR_UPDATE_BOSCH
