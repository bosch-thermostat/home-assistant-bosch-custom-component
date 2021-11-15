"""Support for Bosch Thermostat Sensor."""

from bosch_thermostat_client.const import RECORDINGS, REGULAR, SENSOR, SENSORS
from bosch_thermostat_client.const.easycontrol import ENERGY
from homeassistant.helpers.dispatcher import async_dispatcher_send

from ..const import CIRCUITS, DOMAIN, GATEWAY, SIGNAL_BOSCH, UUID
from .bosch import BoschSensor
from .circuit import CircuitSensor
from .energy import EnergySensor, EnergySensors
from .recording import RecordingSensor

SensorClass = {RECORDINGS: RecordingSensor, ENERGY: EnergySensor, REGULAR: BoschSensor}
SensorKinds = {RECORDINGS: RECORDINGS, ENERGY: RECORDINGS, REGULAR: SENSOR}


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Thermostat from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    enabled_sensors = config_entry.data.get(SENSORS, [])
    data[SENSOR] = []
    data[RECORDINGS] = []

    def get_sensors(sensor):
        if sensor.kind in (RECORDINGS, REGULAR):
            return (
                SensorKinds[sensor.kind],
                [
                    SensorClass[sensor.kind](
                        hass=hass,
                        uuid=uuid,
                        bosch_object=sensor,
                        gateway=data[GATEWAY],
                        name=sensor.name,
                        attr_uri=sensor.attr_id,
                        is_enabled=sensor.attr_id in enabled_sensors,
                    )
                ],
            )
        elif sensor.kind == ENERGY:
            return (
                SensorKinds[sensor.kind],
                [
                    SensorClass[sensor.kind](
                        hass=hass,
                        uuid=uuid,
                        bosch_object=sensor,
                        gateway=data[GATEWAY],
                        sensor_attributes=energy,
                        attr_uri=sensor.attr_id,
                        is_enabled=sensor.attr_id in enabled_sensors,
                    )
                    for energy in EnergySensors
                ],
            )
        return (None, None)

    for bosch_sensor in data[GATEWAY].sensors:
        (target, sensors) = get_sensors(bosch_sensor)
        if not target:
            continue
        for sensor_entity in sensors:
            data[target].append(sensor_entity)

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
