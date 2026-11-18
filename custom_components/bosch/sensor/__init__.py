"""Support for Bosch Thermostat Sensor."""

from bosch_thermostat_client.const import (
    ECUS_RECORDING,
    RECORDING,
    REGULAR,
    SENSOR,
    SENSORS,
)
from bosch_thermostat_client.const.easycontrol import ENERGY
from ..const import CIRCUITS, DOMAIN, BOSCH_GATEWAY_ENTRY, UUID
from .bosch import BoschSensor
from .circuit import CircuitSensor
from .energy import EcusRecordingSensors, EnergySensor, EnergySensors
from .heatpump_virtual import (
    HeatpumpBinarySensor,
    get_heatpump_virtual_entities,
    should_register_heatpump_virtual,
)
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
    entry = data[BOSCH_GATEWAY_ENTRY]
    coordinator = entry.coordinator
    enabled_sensors = config_entry.data.get(SENSORS, [])

    new_stats_api = config_entry.options.get("new_stats_api", False)
    recording_shifted_state = config_entry.options.get(
        "recording_shifted_state", False
    )
    gateway = entry.gateway
    
    sensor_entities = []
    recording_entities = []

    def get_sensors(sensor):
        if sensor.kind in (RECORDING, REGULAR, "notification"):
            kwargs = (
                {
                    "new_stats_api": new_stats_api,
                    "recording_shifted_state": recording_shifted_state,
                }
                if sensor.kind == RECORDING
                else {}
            )
            return (
                SensorKinds[sensor.kind],
                [
                    SensorClass[sensor.kind](
                        coordinator=coordinator,
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
                        coordinator=coordinator,
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
                        coordinator=coordinator,
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
            if target == RECORDING:
                recording_entities.append(sensor_entity)
            else:
                sensor_entities.append(sensor_entity)

    for circ_type in CIRCUITS:
        circuits = gateway.get_circuits(circ_type)
        for circuit in circuits:
            for sensor in circuit.sensors:
                sensor_entities.append(
                    CircuitSensor(
                        coordinator=coordinator,
                        uuid=uuid,
                        bosch_object=sensor,
                        gateway=gateway,
                        name=sensor.name,
                        attr_uri=sensor.attr_id,
                        domain_name=circuit.name,
                        circuit_type=circ_type,
                        is_enabled=sensor.attr_id in enabled_sensors,
                    )
                )
    # Optional IVT heat-pump virtual diagnostics (each disabled by default).
    if should_register_heatpump_virtual(config_entry):
        virtual = get_heatpump_virtual_entities(
            coordinator=coordinator, gateway=gateway, uuid=uuid
        )
        sensor_entities.extend(
            e for e in virtual if not isinstance(e, HeatpumpBinarySensor)
        )

    # Recording/energy entities put themselves on the coordinator's hourly
    # schedule when added; regular sensors join the per-scan refresh.
    async_add_entities(sensor_entities + recording_entities)
    return True
