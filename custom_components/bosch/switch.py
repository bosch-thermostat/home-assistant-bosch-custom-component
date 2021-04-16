"""
Support for water heaters connected to Bosch thermostat.

For more details about this platform, please refer to the documentation at...
"""
import logging

from bosch_thermostat_client.const import GATEWAY
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CHARGE, DOMAIN, SIGNAL_BOSCH, SIGNAL_SWITCH, START, STOP, UUID

SWITCH = "switch"
ICON = "mdi:fire"
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Bosch Water heater from a config entry."""
    uuid = config_entry.data[UUID]
    data = hass.data[DOMAIN][uuid]
    data_switch = []
    for dhw in data[GATEWAY].dhw_circuits:
        for sensor in dhw.sensors:
            if sensor.name.lower() == CHARGE:
                data_switch.append(
                    BoschWaterHeaterCharge(uuid, dhw, sensor, data[GATEWAY])
                )
                break
    if data_switch:
        data[SWITCH] = data_switch
        async_add_entities(data[SWITCH])
    async_dispatcher_send(hass, SIGNAL_BOSCH)
    return True


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Bosch Thermostat Platform."""
    pass


class BoschWaterHeaterCharge(SwitchEntity):
    """Representation of a Bosch charge."""

    def __init__(self, uuid, dhw, sensor, gateway):
        """Set up device and add update callback to get data from websocket."""
        self._dhw = dhw
        self._name = self._dhw.name
        self._unique_id = self._dhw.name + sensor.name + uuid
        self._gateway = gateway
        self._domain_name = dhw.name
        self._uuid = uuid
        self.sensor = sensor
        self._cached_state = None
        self._last_updated = None

    @property
    def icon(self):
        return ICON

    @property
    def device_info(self):
        """Get attributes about the device."""
        return {
            "identifiers": self._domain_identifier,
            "manufacturer": self._gateway.device_model,
            "model": self._gateway.device_type,
            "name": "Water heater " + self._name,
            "sw_version": self._gateway.firmware,
            "via_device": (DOMAIN, self._uuid),
        }

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return self._unique_id

    @property
    def is_on(self):
        """Return true if switch is on."""
        return True if self._cached_state == START else False

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_SWITCH, self.async_update
        )

    @property
    def bosch_object(self):
        """Return upstream component. Used for refreshing."""
        return self.sensor

    async def async_turn_on(self, **kwargs):
        """Turn on switch."""
        _LOGGER.debug("Turning on charge switch.")
        await self._dhw.set_service_call(CHARGE, START)
        self._cached_state = "start"
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn off switch."""
        _LOGGER.debug("Turning off charge switch.")
        await self._dhw.set_service_call(CHARGE, STOP)
        self._cached_state = "stop"
        self.async_write_ha_state()

    async def async_update(self):
        _LOGGER.debug("Update of charge switch called.")
        self._cached_state = self.sensor.state
        self.async_write_ha_state()

    @property
    def signal(self):
        return SIGNAL_SWITCH

    @property
    def name(self):
        return self._sensor_name

    @property
    def _sensor_name(self):
        return "Charge switch"

    @property
    def _domain_identifier(self):
        return {(DOMAIN, self._domain_name + self._uuid)}

    @property
    def should_poll(self):
        """Don't poll."""
        return False
