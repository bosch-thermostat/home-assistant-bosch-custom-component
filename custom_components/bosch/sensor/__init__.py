"""Support for Bosch Thermostat Sensor."""

from bosch_thermostat_client.const import (
    ECUS_RECORDING,
    RECORDING,
    REGULAR,
    SENSOR,
    SENSORS,
)
from bosch_thermostat_client.const.easycontrol import ENERGY
from homeassistant.helpers import entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send

from ..const import CIRCUITS, DOMAIN, GATEWAY, SERVICE_MOVE_OLD_DATA, SIGNAL_BOSCH, UUID
from .bosch import BoschSensor
from .circuit import CircuitSensor
from .energy import EcusRecordingSensors, EnergySensor, EnergySensors
from .notifications import NotificationSensor
from .recording import RecordingSensor

SensorClass = {
    RECORDING: RecordingSensor,
    ENERGY: EnergySensor,
    ECUS_RECORDING: EnergySensor,
    REGULAR: BoschSensor,
    "notification": NotificationSensor,
}
SensorKinds = {
    RECORDING: RECORDING,
    ENERGY: RECORDING,
    ECUS_RECORDING: RECORDING,
    REGULAR: SENSOR,
    "notification": SENSOR,
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Thermostat from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    enabled_sensors = config_entry.data.get(SENSORS, [])

    new_stats_api = config_entry.options.get("new_stats_api", False)
    gateway = data[GATEWAY]
    data[SENSOR] = []
    data[RECORDING] = []

    def get_sensors(sensor):
        if sensor.kind in (RECORDING, REGULAR, "notification"):
            kwargs = (
                {
                    "new_stats_api": new_stats_api,
                }
                if sensor.kind == RECORDING
                else {}
            )
            return (
                SensorKinds[sensor.kind],
                [
                    SensorClass[sensor.kind](
                        hass=hass,
                        uuid=uuid,
                        bosch_object=sensor,
                        gateway=gateway,
                        name=sensor.name,
                        attr_uri=sensor.attr_id,
                        is_enabled=sensor.attr_id in enabled_sensors,
                        **kwargs
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
                        gateway=gateway,
                        sensor_attributes=energy,
                        attr_uri=sensor.attr_id,
                        new_stats_api=new_stats_api,
                        is_enabled=sensor.attr_id in enabled_sensors,
                    )
                    for energy in EnergySensors
                ],
            )
        elif sensor.kind == ECUS_RECORDING:
            return (
                SensorKinds[sensor.kind],
                [
                    SensorClass[sensor.kind](
                        hass=hass,
                        uuid=uuid,
                        bosch_object=sensor,
                        gateway=gateway,
                        sensor_attributes=energy,
                        attr_uri=sensor.attr_id,
                        new_stats_api=new_stats_api,
                        is_enabled=sensor.attr_id in enabled_sensors,
                    )
                    for energy in EcusRecordingSensors
                ],
            )
        return (None, None)

    for bosch_sensor in gateway.sensors:
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
    async_add_entities(data[RECORDING])
    if data[RECORDING]:
        platform = entity_platform.async_get_current_platform()

        # This will register add possibility via service to move old data to new format.
        platform.async_register_entity_service(
            SERVICE_MOVE_OLD_DATA,
            {},
            "move_old_entity_data_to_new",
        )
    async_dispatcher_send(hass, SIGNAL_BOSCH)
    return True
