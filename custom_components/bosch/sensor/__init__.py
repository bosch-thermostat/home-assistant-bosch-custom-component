"""Support for Bosch Thermostat Sensor."""

from bosch_thermostat_client.const import RECORDINGS, REGULAR, SENSOR, SENSORS
from bosch_thermostat_client.const.easycontrol import ENERGY
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers import config_validation as cv, entity_platform
import voluptuous as vol
from ..const import CIRCUITS, DOMAIN, GATEWAY, SERVICE_MOVE_OLD_DATA, SIGNAL_BOSCH, UUID
from .bosch import BoschSensor
from .circuit import CircuitSensor
from .energy import EnergySensor, EnergySensors
from .notifications import NotificationSensor
from .recording import RecordingSensor

SensorClass = {
    RECORDINGS: RecordingSensor,
    ENERGY: EnergySensor,
    REGULAR: BoschSensor,
    "notification": NotificationSensor,
}
SensorKinds = {
    RECORDINGS: RECORDINGS,
    ENERGY: RECORDINGS,
    REGULAR: SENSOR,
    "notification": SENSOR,
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Thermostat from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    enabled_sensors = config_entry.data.get(SENSORS, [])

    new_stats_api = config_entry.options.get("new_stats_api", False)
    fetch_past_days = config_entry.options.get("fetch_past_days", False)
    data[SENSOR] = []
    data[RECORDINGS] = []

    def get_sensors(sensor):
        if sensor.kind in (RECORDINGS, REGULAR, "notification"):
            kwargs = (
                {
                    "new_stats_api": new_stats_api,
                    "fetch_past_days": fetch_past_days,
                }
                if sensor.kind == RECORDINGS
                else {}
            )
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
                        gateway=data[GATEWAY],
                        sensor_attributes=energy,
                        attr_uri=sensor.attr_id,
                        new_stats_api=new_stats_api,
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
    if data[RECORDINGS]:
        platform = entity_platform.async_get_current_platform()

        # This will call Entity.set_sleep_timer(sleep_time=VALUE)
        platform.async_register_entity_service(
            SERVICE_MOVE_OLD_DATA,
            {},
            "move_old_entity_data_to_new",
        )
        platform.async_register_entity_service(
            "fetch_past_data",
            {
                vol.Required("start_time"): cv.datetime,
                vol.Required("stop_time"): cv.datetime,
            },
            "fetch_past_data",
        )
    async_dispatcher_send(hass, SIGNAL_BOSCH)
    return True
