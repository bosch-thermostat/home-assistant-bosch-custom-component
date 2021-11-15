"""Bosch base entity."""
from homeassistant.const import TEMP_CELSIUS

from .const import DEFAULT_MAX_TEMP, DEFAULT_MIN_TEMP, DOMAIN


class BoschEntity:
    """Bosch base entity class."""

    def __init__(self, **kwargs):
        """Initialize the entity."""
        self.hass = kwargs.get("hass")
        self._bosch_object = kwargs.get("bosch_object")
        self._gateway = kwargs.get("gateway")
        self._uuid = kwargs.get("uuid")

    @property
    def name(self):
        """Return the name of the entity."""
        return self._name

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return self._unique_id

    @property
    def bosch_object(self):
        """Return upstream component. Used for refreshing."""
        return self._bosch_object

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(self.signal, self.update)

    @property
    def device_info(self):
        """Get attributes about the device."""
        return {
            "identifiers": self._domain_identifier,
            "manufacturer": self._gateway.device_model,
            "model": self._gateway.device_type,
            "name": self.device_name,
            "sw_version": self._gateway.firmware,
            "via_hub": (DOMAIN, self._uuid),
        }


class BoschClimateWaterEntity(BoschEntity):
    """Bosch climate and water entities base class."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._name = self._bosch_object.name
        self._temperature_unit = TEMP_CELSIUS
        self._unique_id = self._name + self._uuid
        self._current_temperature = None
        self._state = None
        self._target_temperature = None

    @property
    def _domain_identifier(self):
        return {(DOMAIN, self._unique_id)}

    @property
    def device_name(self):
        """Return name displayed in device_info"""
        return f"{self._name_prefix} {self._name}"

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._temperature_unit

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return (
            self._bosch_object.min_temp
            if self._bosch_object.min_temp
            else DEFAULT_MIN_TEMP
        )

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return (
            self._bosch_object.max_temp
            if self._bosch_object.max_temp
            else DEFAULT_MAX_TEMP
        )
