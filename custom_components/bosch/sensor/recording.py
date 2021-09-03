from .base import BoschBaseSensor

from ..const import (
    SIGNAL_RECORDING_UPDATE_BOSCH,
)


class RecordingSensor(BoschBaseSensor):
    """Representation of Recording Sensor."""

    @property
    def _sensor_name(self):
        return "Recording sensors"

    @property
    def signal(self):
        return SIGNAL_RECORDING_UPDATE_BOSCH

    def attrs_write(self, data, **kwargs):
        self._unit_of_measurement = self._bosch_object.unit_of_measurement
        self._attrs = data
        self._attr_last_reset = data.get("last_reset")
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()
