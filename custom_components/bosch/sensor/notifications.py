"""Bosch NEFIT notification sensor."""
from .bosch import BoschSensor


class NotificationSensor(BoschSensor):
    """Representation of a Notification sensor for NEFIT notifications."""

    async def async_update(self):
        self._state = self._bosch_object.state
        data = {
            "displayCode": self._bosch_object.get_value(self._attr_uri, ""),
            "cause": self._bosch_object.get_value("cause", 0),
        }
        self.attrs_write(data=data, units=None)
