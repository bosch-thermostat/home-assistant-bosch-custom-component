"""Module to control string from db json."""
# pylint: disable=invalid-name

import logging

from .const import (
    ALLOWED_VALUES,
    AUTO,
    HCPROGRAM,
    MAX,
    MIN,
    OPEN,
    MANUAL,
    OWNPROGRAM,
    SHORT,
    STATE,
    UNITS,
    VALUE,
    INVALID,
    OFF,
    ON,
)

_LOGGER = logging.getLogger(__name__)


class Strings:
    """String for Bosch."""

    def __init__(self, dictionary, _type=None):
        self._dict = dictionary
        self.__init_shared()

    def __init_shared(self):
        self.val = self._dict.get(VALUE, VALUE)
        self.min = self._dict.get(MIN, MIN)
        self.max = self._dict.get(MAX, MAX)
        self.allowed_values = self._dict.get(ALLOWED_VALUES, ALLOWED_VALUES)
        self.units = self._dict.get(UNITS, UNITS)
        self.state = self._dict.get(STATE, STATE)
        self.open = self._dict.get(OPEN, OPEN)
        self.short = self._dict.get(SHORT, SHORT)
        self.auto = self._dict.get(AUTO, AUTO)
        self.manual = self._dict.get(MANUAL, MANUAL)
        self.off = self._dict.get(OFF, OFF)
        self.on = self._dict.get(ON, ON)
        self.ownprogram = self._dict.get(OWNPROGRAM, OWNPROGRAM)
        self.hcprogram = self._dict.get(HCPROGRAM, HCPROGRAM)
        self.invalid = self._dict.get(INVALID, INVALID)

    def get(self, prop):
        return getattr(self, prop, None)
