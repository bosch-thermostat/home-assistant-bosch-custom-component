"""Main circuit object."""
import logging
from .const import (
    GET,
    ID,
    HEATING_CIRCUITS,
    DHW_CIRCUITS,
    HC,
    CURRENT_TEMP,
    OPERATION_MODE,
    SUBMIT,
    REFS,
    HA_STATES,
    STATUS
)
from .helper import BoschSingleEntity
from .errors import ResponseError
from .schedule import Schedule

_LOGGER = logging.getLogger(__name__)


class Circuit(BoschSingleEntity):
    """Parent object for circuit of type HC or DHW."""

    def __init__(self, requests, attr_id, db, str_obj, _type, current_date):
        """Initialize circuit with requests and id from gateway."""
        self._circuits_path = {}
        self._references = None
        self._requests = requests
        name = attr_id.split("/").pop()
        self._type = _type
        self._state = False
        if self._type == HC:
            self._db = db[HEATING_CIRCUITS]
        else:
            self._db = db[DHW_CIRCUITS]
        self._schedule = Schedule(requests, name, current_date)
        super().__init__(name, attr_id, str_obj)

    @property
    def db_json(self):
        """Give simple json scheme of circuit."""
        return self._db

    @property
    def schedule(self):
        """Retrieve schedule of HC/DHW."""
        return self._schedule

    @property
    def hastates(self):
        return self._db.get(HA_STATES, None)

    @property
    def current_mode(self):
        return self.get_value(OPERATION_MODE)

    @property
    def available_operation_modes(self):
        """Get Bosch operations modes."""
        return self.get_property(OPERATION_MODE).get(self.strings.allowed_values, {})

    async def initialize(self):
        """Check each uri if return json with values."""
        for key, value in self._db[REFS].items():
            uri = value[ID].format(self.name)
            self._circuits_path[key] = uri
            self._data[key] = {}
        self._json_scheme_ready = True
        await self.update_requested_key(STATUS)

    async def update(self):
        """Update info about Circuit asynchronously."""
        _LOGGER.debug("Updating circuit %s", self.name)
        is_updated = False
        try:
            for key in self._data:
                result = await self._requests[GET](self._circuits_path[key])
                if self.process_results(result, key):
                    is_updated = True
            self._updated_initialized = True
            self._state = True
        except ResponseError:
            self._state = False
        return is_updated

    async def update_requested_key(self, key):
        """Update info about Circuit asynchronously."""
        if key in self._data:
            try:
                result = await self._requests[GET](self._circuits_path[key])
                self.process_results(result, key)
                self._state = True
            except ResponseError:
                self._state = False

    async def set_operation_mode(self, new_mode):
        """Set operation_mode of Heating Circuit."""
        if self.current_mode == new_mode:
            _LOGGER.warning("Trying to set mode which is already set %s", new_mode)
            return None
        if new_mode in self.available_operation_modes:
            await self._requests[SUBMIT](self._circuits_path[OPERATION_MODE], new_mode)
            self._data[OPERATION_MODE][self._str.val] = new_mode
            return new_mode
        _LOGGER.warning(
            "You wanted to set %s, but it is not allowed %s",
            new_mode,
            self.available_operation_modes,
        )

    @property
    def state(self):
        """Retrieve state of the circuit."""
        if self._state:
            return self.get_value(STATUS)

    @property
    def current_temp(self):
        """Give current temperature of circuit."""
        _LOGGER.debug("Current temp is %s", self.get_property(CURRENT_TEMP))
        temp = self.parse_float_value(self.get_property(CURRENT_TEMP))
        if temp > 0 and temp < 120:
            return temp

    @property
    def temp_units(self):
        """Return units of temperature."""
        return self.get_property(CURRENT_TEMP).get(self._str.units)

    def parse_float_value(self, val, single_value=True, minmax_obliged=False):
        """Parse if value is between min and max."""
        state = val.get(self._str.state, {})
        value = val.get(self._str.val, False)
        _min = val.get(self._str.min, -1)
        _max = val.get(self._str.max, -1)
        if not value:
            return None
        for k in state:
            if (self._str.open in k and k[self._str.open] == val) or (
                self._str.short in k and k[self._str.short] == val
            ):
                return None
        if all(k in val for k in (self._str.val, self._str.min, self._str.max)):
            if _min <= value <= _max:
                return value if single_value else val
            return None
        if not minmax_obliged:
            return value if single_value else val
        return None
