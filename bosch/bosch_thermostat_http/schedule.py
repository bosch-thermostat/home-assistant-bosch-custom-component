"""Logic to converse schedule."""
import logging
from datetime import datetime

from .const import (
    GET,
    DAYOFWEEK,
    MODE,
    START,
    STOP,
    SETPOINT,
    TIME,
    VALUE,
    TEMP,
    AUTO,
    SETPOINT_PROP,
    SWITCH_POINTS,
    SWITCHPROGRAM,
    MIDNIGHT,
    DAYS,
    DAYS_INT,
)
from .errors import ResponseError

_LOGGER = logging.getLogger(__name__)


class Schedule:
    """Scheduler logic."""

    def __init__(self, requests, circuit_name, current_time):
        """Initialize schedule handling of Bosch gateway."""
        self._requests = requests
        self._active_program = None
        self._schedule = None
        self._circuit_name = circuit_name
        self._setpoints_temp = {}
        self._active_setpoint = None
        self._active_program_uri = None
        self._time = None
        self._time_retrieve = current_time

    async def update_schedule(self, active_program):
        """Update schedule from Bosch gateway."""
        self._active_program = active_program
        self._active_program_uri = SWITCHPROGRAM.format(
            self._circuit_name, active_program
        )
        try:
            self._time = await self._time_retrieve()
            result = await self._requests[GET](self._active_program_uri)
            self._schedule = await self._retrieve_schedule(
                result.get(SWITCH_POINTS), result.get(SETPOINT_PROP)
            )
        except ResponseError:
            pass

    @property
    def time(self):
        """Get current time of Gateway."""
        return self._time

    @property
    def active_program(self):
        """Get active program."""
        return self._active_program

    def cache_temp_for_mode(self, temp, mode_type, active_setpoint=None):
        """Save active program for cache."""
        if mode_type == AUTO:
            active_setpoint = self.get_temp_in_schedule()[MODE]
        if active_setpoint in self._setpoints_temp:
            self._setpoints_temp[active_setpoint] = temp

    async def _get_setpoint_temp(self, setpointProperty, setpoint):
        """Download temp for setpoint."""
        try:
            result = await self._requests[GET](f'{setpointProperty["id"]}/{setpoint}')
        except ResponseError:
            pass
        return result.get(VALUE, 0)

    async def _retrieve_schedule(self, switchPoints, setpointProperty):
        """Convert Bosch schedule to dict format."""
        schedule = {k: [] for k in DAYS.values()}
        for switch in switchPoints:
            if switch[SETPOINT] not in self._setpoints_temp:
                self._setpoints_temp[switch[SETPOINT]] = 0
            day = DAYS[switch[DAYOFWEEK]]
            current_day = schedule[day]
            current_day.append(
                {MODE: switch[SETPOINT], START: switch[TIME], STOP: MIDNIGHT}
            )
            if len(current_day) > 1:
                current_day[-2][STOP] = switch[TIME] - 1
        for setpoint in self._setpoints_temp:
            self._setpoints_temp[setpoint] = await self._get_setpoint_temp(
                setpointProperty, setpoint
            )
        return schedule

    def get_temp_for_mode(self, mode):
        """This is working only in manual for RC35 where op_mode == setpoint."""
        return self._setpoints_temp.get(mode, 0)

    def get_temp_in_schedule(self):
        """Find temp in schedule for current date."""
        if self._time:
            bosch_date = datetime.strptime(self._time, "%Y-%m-%dT%H:%M:%S")
            day_of_week = DAYS[DAYS_INT[bosch_date.weekday()]]
            if self._schedule and day_of_week in self._schedule:
                mins = self._get_minutes_since_midnight(bosch_date)
                for setpoint in self._schedule[day_of_week]:
                    if mins > setpoint[START] and mins < setpoint[STOP]:
                        return {
                            MODE: setpoint[MODE],
                            TEMP: self._setpoints_temp[setpoint[MODE]],
                        }

    def _get_minutes_since_midnight(self, date):
        """Retrieve minutes since midnight."""
        return (
            date - date.replace(hour=0, minute=0, second=0, microsecond=0)
        ).total_seconds() / 60

