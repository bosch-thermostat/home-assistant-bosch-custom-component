"""Support for Bosch Thermostat Sensor."""
import logging

from bosch_thermostat_client.const import (
    DHW,
    HC,
    RECORDINGS,
    SC,
    SENSOR,
    SENSORS,
    UNITS,
    VALUE,
    ZN,
)
from bosch_thermostat_client.const.ivt import INVALID
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import Entity
from datetime import timedelta, datetime
from .const import (
    DOMAIN,
    GATEWAY,
    SIGNAL_BOSCH,
    SIGNAL_RECORDING_UPDATE_BOSCH,
    SIGNAL_SENSOR_UPDATE_BOSCH,
    SIGNAL_SOLAR_UPDATE_BOSCH,
    UNITS_CONVERTER,
    UUID,
    MINS,
)

_LOGGER = logging.getLogger(__name__)

CIRCUITS = [DHW, HC, SC, ZN]
CIRCUITS_SENSOR_NAMES = {
    DHW: "Water heater ",
    HC: "Heating circuit ",
    SC: "Solar circuit ",
    ZN: "Zone circuit",
}


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Bosch Thermostat Sensor Platform."""
    pass


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Thermostat from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    enabled_sensors = config_entry.data.get(SENSORS, [])
    data[SENSOR] = []
    data[RECORDINGS] = []

    def get_target_sensor(sensor_kind):
        if sensor_kind == RECORDINGS:
            return (RECORDINGS, RecordingSensor, "Recording")
        return (SENSOR, BoschSensor, "Sensors")

    for sensor in data[GATEWAY].sensors:
        (target, SensorClass, domain_name) = get_target_sensor(sensor.kind)
        data[target].append(
            SensorClass(
                hass=hass,
                uuid=uuid,
                bosch_object=sensor,
                gateway=data[GATEWAY],
                name=sensor.name,
                attr_uri=sensor.attr_id,
                domain_name=domain_name,
                is_enabled=sensor.attr_id in enabled_sensors,
            )
        )

    for circ_type in CIRCUITS:
        circuits = data[GATEWAY].get_circuits(circ_type)
        for circuit in circuits:
            for sensor in circuit.sensors:
                data[SENSOR].append(
                    CircuitSensor(
                        hass=hass,
                        uuid=uuid,
                        bosch_object=sensor,
                        gateway=data[GATEWAY],
                        name=sensor.name,
                        attr_uri=sensor.attr_id,
                        domain_name=circuit.name,
                        circuit_type=circ_type,
                        is_enabled=sensor.attr_id in enabled_sensors,
                    )
                )
    async_add_entities(data[SENSOR])
    async_add_entities(data[RECORDINGS])
    async_dispatcher_send(hass, SIGNAL_BOSCH)
    return True


class BoschBaseSensor(Entity):
    def __init__(
        self,
        hass,
        uuid,
        bosch_object,
        gateway,
        name,
        attr_uri,
        domain_name,
        circuit_type=None,
        is_enabled=False,
    ):
        """Initialize the sensor."""
        self.hass = hass
        self._bosch_object = bosch_object
        self._gateway = gateway
        self._domain_name = domain_name
        self._name = (domain_name + " " + name) if domain_name != "Sensors" else name
        self._attr_uri = attr_uri
        self._state = None
        self._update_init = True
        self._unit_of_measurement = None
        self._uuid = uuid
        self._unique_id = self._domain_name + self._name + self._uuid
        self._attrs = {}
        self._circuit_type = circuit_type
        self._is_enabled = is_enabled

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            self.signal, self.async_update
        )

    @property
    def _domain_identifier(self):
        return {(DOMAIN, self._domain_name + self._uuid)}

    @property
    def _sensor_name(self):
        raise NotImplementedError

    @property
    def signal(self):
        raise NotImplementedError

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return self._unique_id

    @property
    def bosch_object(self):
        """Return upstream component. Used for refreshing."""
        return self._bosch_object

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement

    @property
    def device_state_attributes(self):
        """Return the state attributes of the sensor."""
        return self._attrs

    @property
    def entity_registry_enabled_default(self):
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._is_enabled

    @property
    def device_info(self):
        """Get attributes about the device."""
        return {
            "identifiers": self._domain_identifier,
            "manufacturer": self._gateway.device_model,
            "model": self._gateway.device_type,
            "name": self._sensor_name,
            "sw_version": self._gateway.firmware,
            "via_hub": (DOMAIN, self._uuid),
        }

    async def async_update(self):
        """Update state of device."""
        _LOGGER.debug("Update of sensor %s called.", self.unique_id)
        data = self._bosch_object.get_property(self._attr_uri)

        def get_units():
            if not isinstance(data, list):
                return UNITS_CONVERTER.get(data.get(UNITS))
            return None

        units = get_units()
        if units == MINS and data:
            self.time_sensor_data(data)
        else:
            self._state = data.get(VALUE, INVALID)
            self._attrs = {}
            self._attrs["stateExtra"] = self._bosch_object.state
            if not data:
                if not self._bosch_object.update_initialized:
                    self._state = self._bosch_object.state
                    self._attrs["stateExtra"] = self._bosch_object.state_message
                return
            self.attrs_write(data=data, units=units)

    def time_sensor_data(self, data):
        value = data.get(VALUE, INVALID)
        self._state = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(minutes=value)
        data["device_class"] = "timestamp"
        self.attrs_write(data=data, units=None)

    def attrs_write(self, data, units):
        self._attrs = data
        self._unit_of_measurement = units
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()


class BoschSensor(BoschBaseSensor):
    """Representation of a Bosch sensor."""

    @property
    def _sensor_name(self):
        return "Bosch sensors"

    @property
    def signal(self):
        return SIGNAL_SENSOR_UPDATE_BOSCH


class CircuitSensor(BoschBaseSensor):
    """Representation of a Bosch sensor."""

    @property
    def _sensor_name(self):
        return CIRCUITS_SENSOR_NAMES[self._circuit_type] + " " + self._domain_name

    @property
    def signal(self):
        return SIGNAL_SOLAR_UPDATE_BOSCH


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
        if self._update_init:
            self._update_init = False
            self.async_schedule_update_ha_state()
