"""Heating Circuits module of Bosch thermostat."""
from .const import SUBMIT, VALUE, WATER_HIGH, AUTO_SETPOINT, DHW, OPERATION_MODE

from .circuit import Circuit


class DHWCircuit(Circuit):
    """Single Heating Circuits object."""

    def __init__(self, requests, attr_id, db, str_obj, current_date):
        """
        Initialize single circuit.

        :param obj get_request:    function to retrieve data from thermostat.
        :param obj submit_request: function to send data to thermostat.
        :param str hc_name: name of heating circuit.
        """
        super().__init__(requests, attr_id, db, str_obj, DHW, current_date)

    async def set_temperature(self, temp):
        """Set temperature of Circuit."""
        (t_temp, min_temp, max_temp) = self.target_temperature
        op_mode = self.get_value(OPERATION_MODE)
        if min_temp < temp < max_temp and op_mode and t_temp != temp:
            await self._requests[SUBMIT](self._circuits_path[WATER_HIGH], temp)
            self._data[WATER_HIGH][self._str.val] = temp
            return True
        return False

    @property
    def target_temperature(self):
        """Get target temperature of Circtuit. Temporary or Room set point."""
        temp_levels_high = self.get_property(WATER_HIGH)
        temp = self.parse_float_value(temp_levels_high, False, True)
        if temp:
            return (
                float(temp[VALUE]),
                float(temp[self._str.min]),
                float(temp[self._str.max]),
            )
        setpoint_temp = self.get_value(AUTO_SETPOINT, -1)
        if all(k in temp_levels_high for k in (self._str.min, self._str.max)):
            return (
                float(setpoint_temp),
                float(temp[self._str.min]),
                float(temp[self._str.max]),
            )
        return (setpoint_temp, 0, 99)
