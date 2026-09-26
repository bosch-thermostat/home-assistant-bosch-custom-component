"""Bosch Thermostat Number Entities."""

from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import BoschDataUpdateCoordinator

from .bosch_entity import BoschEntity
from .const import (
    CIRCUITS,
    CIRCUITS_SENSOR_NAMES,
    DOMAIN,
    BOSCH_GATEWAY_ENTRY,
    NUMBER,
    UNITS_CONVERTER,
    UUID,
)
from homeassistant.components.number import NumberEntity
from homeassistant.components.number.const import NumberMode


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Number from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    entry = data[BOSCH_GATEWAY_ENTRY]
    coordinator = entry.coordinator
    enabled_switches = config_entry.data.get(NUMBER, [])
    
    entities = []
    for switch in entry.gateway.number_switches:
        entities.append(
            BoschNumber(
                coordinator=coordinator,
                uuid=uuid,
                bosch_object=switch,
                gateway=entry.gateway,
                name=switch.name,
                attr_uri=switch.attr_id,
                domain_name="Switches",
                is_enabled=switch.attr_id in enabled_switches,
            )
        )
    for circ_type in CIRCUITS:
        circuits = entry.gateway.get_circuits(circ_type)
        for circuit in circuits:
            for switch in circuit.number_switches:
                entities.append(
                    CircuitNumber(
                        coordinator=coordinator,
                        uuid=uuid,
                        bosch_object=switch,
                        gateway=entry.gateway,
                        name=switch.name,
                        attr_uri=switch.attr_id,
                        domain_name=circuit.name,
                        circuit_type=circ_type,
                        is_enabled=switch.attr_id in enabled_switches,
                    )
                )
    async_add_entities(entities)
    return True


class BoschNumber(BoschEntity, NumberEntity):
    """Bosch number class represents HA Number entity."""

    _attr_mode: NumberMode = NumberMode.BOX

    def __init__(
        self,
        coordinator: BoschDataUpdateCoordinator,
        uuid: str,
        bosch_object: Any,
        gateway: Any,
        name: str,
        attr_uri: str,
        domain_name: str,
        circuit_type: str | None = None,
        is_enabled: bool = False,
    ) -> None:
        """Set up device and add update callback to get data from websocket."""
        super().__init__(
            coordinator=coordinator,
            uuid=uuid,
            bosch_object=bosch_object,
            gateway=gateway,
            domain_name=domain_name,
        )
        self._attr_name = name
        self._attr_uri = attr_uri
        self._attr_unique_id = f"{self._domain_name}{self._attr_name}{self._uuid}"
        self._attrs = {}
        self._circuit_type = circuit_type
        self._attr_entity_registry_enabled_default = is_enabled

    @property
    def device_name(self) -> str:
        """Return device name."""
        return "Bosch switches"

    @property
    def native_min_value(self) -> float:
        """Return the minimum value."""
        if self._bosch_object.min_value is None:
            return 0
        return float(self._bosch_object.min_value)

    @property
    def native_max_value(self) -> float:
        """Return the maximum value."""
        if self._bosch_object.max_value is None:
            return 255
        return float(self._bosch_object.max_value)

    @property
    def native_value(self) -> float | None:
        """Return the entity value."""
        if self._bosch_object.state is None:
            return None
        return float(self._bosch_object.state)

    @property
    def native_step(self) -> float:
        """Return the entity value."""
        return self._bosch_object.step

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of this entity, if any."""
        if self._bosch_object.unit_of_measurement is None:
            return None
        return str(
            UNITS_CONVERTER.get(
                self._bosch_object.unit_of_measurement,
                self._bosch_object.unit_of_measurement,
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        await self._bosch_object.set_value(value)
        await self.coordinator.async_request_refresh()



class CircuitNumber(BoschNumber):
    """Representation of a Bosch circuit number."""

    @property
    def device_name(self):
        return CIRCUITS_SENSOR_NAMES[self._circuit_type] + " " + self._domain_name
