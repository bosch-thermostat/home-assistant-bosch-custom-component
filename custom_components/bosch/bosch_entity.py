"""Bosch base entity."""
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import BOSCH_GATEWAY_ENTRY, DEFAULT_MAX_TEMP, DEFAULT_MIN_TEMP, DOMAIN
from homeassistant.helpers.entity import DeviceInfo


class BoschEntity:
    """Bosch base entity class."""

    def __init__(self, **kwargs):
        """Initialize the entity."""
        if not hasattr(self, "_domain_name"):
            self._domain_name = kwargs.get("domain_name")
        self.hass = kwargs.get("hass")
        self._bosch_object = kwargs.get("bosch_object")
        self._gateway = kwargs.get("gateway")
        self._uuid = kwargs.get("uuid")

    @property
    def bosch_object(self):
        """Return upstream component. Used for refreshing."""
        return self._bosch_object

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self.signal, self.async_update)
        )

    @property
    def _domain_identifier(self):
        if self._bosch_object.parent_id:
            return {(DOMAIN, f"{self._uuid}_{self._bosch_object.parent_id}")}
        return {(DOMAIN, f"{self._uuid}_{self._domain_name}")}

    @property
    def device_info(self) -> DeviceInfo:
        """Get attributes about the device."""
        device_info = DeviceInfo(
            identifiers=self._domain_identifier,
            manufacturer=self._gateway.device_model,
            model=self._gateway.device_type,
            name=self.device_name,
            sw_version=self._gateway.firmware,
            hw_version=self._uuid,
        )
        # The gateway device is registered before the platforms are set up.
        gateway_entry = self.hass.data[DOMAIN][self._uuid][BOSCH_GATEWAY_ENTRY]
        if gateway_entry.gateway_device_id:
            device_info["via_device_id"] = gateway_entry.gateway_device_id
        return device_info


class BoschClimateWaterEntity(BoschEntity):
    """Bosch climate and water entities base class."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._attr_name = self._bosch_object.name
        self._temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_unique_id = f"{self._uuid}{self._bosch_object.id}"
        self._current_temperature = None
        self._state = None
        self._target_temperature = None

    @property
    def _domain_identifier(self):
        return {(DOMAIN, f"{self._uuid}_{self._bosch_object.id}")}

    @property
    def device_name(self):
        """Return name displayed in device_info."""
        return f"{self._name_prefix} {self._attr_name}"

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
