"""Support for Bosch Thermostat Binary Sensor."""
from __future__ import annotations
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import BoschDataUpdateCoordinator

from bosch_thermostat_client.const import BINARY, ON, USED
from homeassistant.components.binary_sensor import BinarySensorEntity

from .bosch_entity import BoschEntity
from .const import (
    BINARY_SENSOR,
    DOMAIN,
    BOSCH_GATEWAY_ENTRY,
    UUID,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Thermostat from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    entry = data[BOSCH_GATEWAY_ENTRY]
    coordinator = entry.coordinator
    enabled_sensors = config_entry.data.get(BINARY_SENSOR, [])
    
    entities = []

    for bosch_sensor in entry.gateway.sensors:
        if bosch_sensor.kind == BINARY:
            entities.append(
                BoschBinarySensor(
                    coordinator=coordinator,
                    uuid=uuid,
                    bosch_object=bosch_sensor,
                    gateway=entry.gateway,
                    name=bosch_sensor.name,
                    attr_uri=bosch_sensor.attr_id,
                    is_enabled=bosch_sensor.attr_id in enabled_sensors,
                )
            )

    async_add_entities(entities)
    return True


class BoschBinarySensor(BoschEntity, BinarySensorEntity):
    """Bosch binary sensor class."""

    _domain_name = "Sensors"

    def __init__(
        self,
        coordinator: BoschDataUpdateCoordinator,
        uuid: str,
        bosch_object: Any,
        gateway: Any,
        name: str,
        attr_uri: str,
        is_enabled: bool = False,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            uuid=uuid,
            bosch_object=bosch_object,
            gateway=gateway,
        )

        self._attr_name = name
        self._attr_uri = attr_uri
        self._state = None
        self._update_init = True

        self._attr_unique_id = f"{self._domain_name}{self._attr_name}{self._uuid}"
        self._attrs = {}
        self._attr_entity_registry_enabled_default = is_enabled

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        if self._bosch_object.state.lower() == ON:
            return True
        elif (
            self._bosch_object.get_value(USED, "true").lower() == "true"
            and self._bosch_object.state.lower() == USED
        ):
            return True
        return False

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        data = self._bosch_object.get_property(self._attr_uri)
        return {
            **data,
            "stateExtra": self._bosch_object.state_message,
        }

    @property
    def device_name(self):
        """Return name displayed in device_info."""
        return "Bosch sensors"

