"""Heating Circuits module of Bosch thermostat."""
import logging
from .const import (
    SUBMIT,
    HC,
    GET,
    AUTO,
    MANUAL,
    OPERATION_MODE,
    PRESETS,
    OFF,
    ACTIVE_PROGRAM,
    TEMP,
    MODE_TO_SETPOINT,
    READ,
    WRITE,
)
from .circuit import Circuit
from .errors import ResponseError

_LOGGER = logging.getLogger(__name__)


class HeatingCircuit(Circuit):
    """Single Heating Circuits object."""

    def __init__(self, requests, attr_id, db, str_obj, current_date):
        """
        Initialize heating circuit.

        :param obj get_request:    function to retrieve data from thermostat.
        :param obj submit_request: function to send data to thermostat.
        :param str hc_name: name of heating circuit.
        """
        super().__init__(requests, attr_id, db, str_obj, HC, current_date)
        self._presets = self._db.get(PRESETS)
        self._mode_to_setpoint = self._db.get(MODE_TO_SETPOINT)
        self._updated_initialized = False

    @property
    def update_initialized(self):
        return self._updated_initialized

    @property
    def temp_read(self):
        """Get temp read property."""
        return self._temp_setpoint(READ)

    @property
    def temp_write(self):
        """Get temp write property."""
        return self._temp_setpoint(WRITE)

    def _temp_setpoint(self, key):
        """Check which temp property to use. Key READ or WRITE"""
        return self._mode_to_setpoint.get(self.current_mode, {}).get(key)

    async def update(self):
        """Update info about Circuit asynchronously."""
        _LOGGER.debug("Updating HC %s", self.name)
        is_updated = False
        for key in self._data:
            if key in (AUTO, MANUAL) and self.operation_mode_type != key:
                continue
            try:
                result = await self._requests[GET](self._circuits_path[key])
                if self.process_results(result, key):
                    is_updated = True
                if key == ACTIVE_PROGRAM:
                    await self._schedule.update_schedule(self.get_value(key))
            except ResponseError:
                pass
        self._updated_initialized = True
        return is_updated

    async def set_temperature(self, temperature):
        """Set temperature of Circuit."""
        target_temp = self.target_temperature
        if target_temp and temperature != target_temp:
            result = await self._requests[SUBMIT](
                self._circuits_path[self.temp_write], temperature
            )
            _LOGGER.debug("Set temperature for HC %s with result %s", self.name, result)
            if result:
                if self.temp_read:
                    self._data[self.temp_read][self._str.val] = temperature
                else:
                    self.schedule.cache_temp_for_mode(
                        temperature,
                        self.operation_mode_type,
                        self.get_value(OPERATION_MODE),
                    )
                return True
        return False

    @property
    def target_temperature(self):
        """Get target temperature of Circtuit. Temporary or Room set point."""
        temp_read = self.temp_read
        if temp_read:
            target_temp = self.get_value(self.temp_read, 0)
            if target_temp > 0:
                return target_temp
        if self.operation_mode_type == MANUAL:
            ###RC300 should never reach this in MANUAL...
            return self.schedule.get_temp_for_mode(self.get_value(OPERATION_MODE))
        elif self._schedule.time:
            cache = self.schedule.get_temp_in_schedule()
            if cache:
                return cache.get(TEMP, 0)

    @property
    def operation_mode_type(self):
        """Check if operation mode type is manual or auto."""
        if self.current_mode in self._presets.get(MANUAL):
            return MANUAL
        if self.current_mode in self._presets.get(AUTO):
            return AUTO

    @property
    def hvac_modes(self):
        """Retrieve HVAC modes."""
        return [
            key
            for key, value in self.hastates.items()
            if value in self.available_operation_modes
        ]

    @property
    def hvac_mode(self):
        """Retrieve current mode in HVAC terminology."""
        for _k, _v in self.hastates.items():
            if _v == self.current_mode:
                return _k
        return OFF

    async def set_hvac_mode(self, hvac_mode):
        """Helper to set operation mode."""
        c_temp_read = self.temp_read
        c_temp_write = self.temp_write
        old_mode = self.current_mode
        new_mode = await self.set_operation_mode(self.hastates.get(hvac_mode))
        if (self.temp_read != c_temp_read) or (self.temp_write != c_temp_write):
            return 2
        if new_mode != old_mode:
            return 1
        return 0
