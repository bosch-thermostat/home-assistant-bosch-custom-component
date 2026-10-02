"""Bosch NEFIT notification sensor."""
from .bosch import BoschSensor


class NotificationSensor(BoschSensor):
    """Representation of a Notification sensor for NEFIT notifications."""

    @property
    def native_value(self):
        return self._bosch_object.state

    @property
    def extra_state_attributes(self):
        return {
            "displayCode": self._bosch_object.get_value(self._attr_uri, ""),
            "cause": self._bosch_object.get_value("cause", 0),
        }

