"""Bosch sensor for Recording sensor in IVT."""

from __future__ import annotations
import logging
from datetime import timedelta, datetime
from typing import Any, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from ..coordinator import BoschDataUpdateCoordinator
    from ..types import BoschObject, BoschGateway

from .statistic_helper import StatisticHelper

from ..const import VALUE
from ..recording_temp_fix import is_temperature_unit, parse_temperature_day
from homeassistant.components.recorder.models import (
    StatisticData,
    timestamp_to_datetime_or_none,
)
from homeassistant.components.sensor import SensorStateClass
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# Gateways with a processing lag still get a value, up to this age.
_MAX_RECORDING_LAG = timedelta(hours=6)


class RecordingSensor(StatisticHelper):
    """Representation of Recording Sensor."""

    _domain_name = "Recording"

    def __init__(
        self,
        coordinator: BoschDataUpdateCoordinator,
        uuid: str,
        bosch_object: BoschObject,
        gateway: BoschGateway,
        name: str,
        attr_uri: str,
        is_enabled: bool = False,
        new_stats_api: bool = False,
        recording_shifted_state: bool = False,
    ) -> None:
        """Initialize Recording sensor."""
        super().__init__(
            coordinator=coordinator,
            uuid=uuid,
            bosch_object=bosch_object,
            gateway=gateway,
            name=name,
            attr_uri=attr_uri,
            is_enabled=is_enabled,
            new_stats_api=new_stats_api,
        )
        self._recording_shifted_state = recording_shifted_state
        self._unit_of_measurement = bosch_object.unit_of_measurement
        self._stale_logged = False
        self._non_numeric_stat_logged = False
        # Display-only when external recording:* LTS is used; avoid sensor.* LTS.
        if new_stats_api:
            self._attr_state_class = None

    @property
    def device_name(self) -> str:
        """Device name."""
        return "Recording sensors"

    @property
    def statistic_id(self) -> str:
        """External API statistic ID."""
        return f"{self._domain_name}:{self._ensure_short_id()}external".lower()

    @staticmethod
    def _last_full_hour() -> datetime:
        return (dt_util.now() - timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0
        )

    @property
    def _show_shifted_state(self) -> bool:
        """Whether entity shows last-hour values (vs -17 with new stats API)."""
        return (not self._new_stats_api) or self._recording_shifted_state

    @property
    def last_reset(self) -> datetime | None:
        """Start of the hour; only for state_class total (HA forbids otherwise)."""
        if self.state_class != SensorStateClass.TOTAL:
            return None
        if not self._show_shifted_state:
            return None
        row = self._current_row()
        return row["d"] if row else self._last_full_hour()

    def _current_row(self) -> dict[str, Any] | None:
        """Row for the last full hour, or the latest completed row up to 6 h old.

        Some gateways (e.g. KM100) publish recordings with a 2-3 hour lag,
        so the last full hour is often missing. The latest available row is
        used instead; last_reset follows its hour, so a row that is shown
        again in the next hour is not counted twice. Only completed hours
        count: the running hour (and rows from a gateway clock running
        ahead) are ignored. Hours without consumption have no row, so the
        shown value can be up to 6 h old; it belongs to the hour named by
        last_reset, not to the current one. Rows that are skipped while the
        lag shrinks, and the last hours of a day, are not shown; the external
        statistics (new_stats_api) import every row.
        """
        data = self._bosch_object.get_property(self._attr_uri)
        if not data or not data.get(VALUE):
            return None

        last_hour = self._last_full_hour()
        rows = [row for row in data[VALUE] if row.get("d") and row["d"] <= last_hour]
        for row in rows:
            if row["d"] == last_hour:
                self._stale_logged = False
                return row
        if not rows:
            return None

        latest = max(rows, key=lambda row: row["d"])
        age = dt_util.now() - latest["d"]
        if age <= _MAX_RECORDING_LAG:
            _LOGGER.debug(
                "Recording %s: %s missing, using latest row from %s (age %s)",
                self.unique_id,
                last_hour,
                latest["d"],
                age,
            )
            self._stale_logged = False
            return latest
        # Hours without consumption have no row at all, so old data is not
        # always a gateway problem: log it once at info level.
        if not self._stale_logged:
            self._stale_logged = True
            _LOGGER.info(
                "Recording %s: latest data from %s is %s old (no consumption "
                "since then, or the gateway lags or its clock is off).",
                self.unique_id,
                latest["d"],
                age,
            )
        return None

    def _native_value(self) -> Any:
        """Return last-hour value, or -17 when new stats API hides entity state."""
        if not self._show_shifted_state:
            return -17
        row = self._current_row()
        return row.get(VALUE) if row else None

    @property
    def _is_temperature_recording(self) -> bool:
        """Whether this recording is temperature (°C), not energy."""
        return is_temperature_unit(self._unit_of_measurement)

    def _recording_path(self) -> str | None:
        """Gateway recordings path for interval queries."""
        path = getattr(self._bosch_object, "path", None)
        return str(path) if path else None

    async def _async_fetch_temp_day(self, day: datetime) -> list[dict[str, Any]]:
        """Fetch one day of temperature hours, keeping valid 0 °C."""
        path = self._recording_path()
        if not path:
            return []
        local_day = dt_util.start_of_local_day(day)
        interval = local_day.strftime("%Y-%m-%d")
        uri = f"{path}?interval={interval}"
        payload: Any = None
        try:
            payload = await self._gateway.raw_query(path=uri)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Temp recording fetch failed for %s (%s): %s",
                self.statistic_id,
                uri,
                err,
            )
            return []
        if not isinstance(payload, dict):
            _LOGGER.warning(
                "Temp recording bad payload for %s: %s",
                self.statistic_id,
                type(payload).__name__,
            )
            return []
        return parse_temperature_day(payload, day=local_day)

    def _set_temperature_hours(self, rows: list[dict[str, Any]]) -> bool:
        """Write hour rows into the client object RESULT (state setter is RO)."""
        attr = getattr(self._bosch_object, "attr_id", None) or self._attr_uri
        data = getattr(self._bosch_object, "_data", None)
        if not isinstance(data, dict) or attr not in data:
            _LOGGER.warning(
                "Cannot store temp hours for %s (missing client _data)",
                self.statistic_id,
            )
            return False
        bucket = data[attr]
        if not isinstance(bucket, dict):
            return False
        result = bucket.setdefault("result", {})
        result[VALUE] = rows
        return True

    async def _async_refresh_temperature_hours(self) -> None:
        """Replace client-skipped 0 °C hours with a full day parse."""
        now = dt_util.now()
        rows = await self._async_fetch_temp_day(now)
        if not rows:
            _LOGGER.warning(
                "No temperature hours for %s (path=%s)",
                self.statistic_id,
                self._recording_path(),
            )
            return
        if self._set_temperature_hours(rows):
            _LOGGER.debug(
                "Loaded %s temperature hours for %s",
                len(rows),
                self.statistic_id,
            )

    async def async_update_recording(self) -> None:
        """Refresh temp hours (keep 0 °C), then stats + entity state."""
        if self._is_temperature_recording:
            await self._async_refresh_temperature_hours()
        await super().async_update_recording()

    async def fetch_past_data(
        self, start_time: datetime, stop_time: datetime
    ) -> dict[Any, Any]:
        """Fetch range; temperature keeps 0 °C hours (energy unchanged)."""
        if not self._is_temperature_recording:
            return await super().fetch_past_data(
                start_time=start_time, stop_time=stop_time
            )
        start_time = dt_util.start_of_local_day(start_time)
        out: dict[Any, Any] = {}
        current = start_time
        while current < stop_time:
            for row in await self._async_fetch_temp_day(current):
                stamp = row["d"]
                if start_time <= stamp <= stop_time:
                    out[stamp] = row
            current += timedelta(days=1)
        return out

    async def _upsert_past_statistics(
        self, start: datetime, stop: datetime
    ) -> None:
        now = dt_util.now()
        diff = now - start
        if now.day == start.day:
            _LOGGER.warning("Can't upsert today date. Try again tomorrow.")
            return
        if diff > timedelta(days=60):
            _LOGGER.warning(
                "Update more than 60 days might take some time! Component will try to do that anyway!"
            )
        stats = await self.fetch_past_data(
            start_time=start, stop_time=start + timedelta(hours=26)
        )  # return list of objects {'d': datetime with timezone, 'value': 'used kWh in last hour'}
        if not stats:
            _LOGGER.debug("No stats found. Exiting.")
            return
        stats_dict = {
            dt_util.as_timestamp(stat["d"]): stat for stat in stats.values()
        }
        # get stats from HA database
        last_stats = await self.get_stats_from_ha_db(
            start_time=start - timedelta(hours=1), end_time=now
        )
        last_stat = last_stats.get(self.statistic_id)
        _sum: float = cast(float, last_stat[0].get("sum", 0.0)) if last_stat else 0.0
        out: dict[float, StatisticData] = {}
        current_time = start
        while current_time <= stop:
            current_ts = dt_util.as_timestamp(current_time)
            if current_ts in stats_dict:
                stat = stats_dict[current_ts]
                try:
                    _state = float(stat["value"])
                except (TypeError, ValueError):
                    if not getattr(self, "_non_numeric_stat_logged", False):
                        self._non_numeric_stat_logged = True
                        _LOGGER.warning(
                            "Recording %s skipped non-numeric value %r",
                            self.statistic_id,
                            stat.get("value"),
                        )
                    out[current_ts] = StatisticData(
                        start=current_time,
                        state=0.0,
                        sum=_sum,
                    )
                    current_time += timedelta(hours=1)
                    continue
                _sum += _state  # increase sum
                _LOGGER.debug(
                    "Putting past state to statistic table with id: %s. Date: %s, state: %s, sum: %s.",
                    self.statistic_id,
                    current_time,
                    _state,
                    _sum,
                )
                out[current_ts] = StatisticData(
                    start=current_time,
                    state=_state,
                    sum=_sum,
                )
                stats_dict[current_ts] = None
            else:
                out[current_ts] = StatisticData(
                    start=current_time,
                    state=0.0,
                    sum=_sum,
                )
            current_time += timedelta(hours=1)

        if last_stat:
            start_ts = dt_util.as_timestamp(start)
            for stat in last_stat:
                _start = cast(float, stat["start"])
                if _start in out or start_ts > _start:
                    continue
                _state = cast(float, stat.get("state", 0.0))
                _sum += _state
                out[_start] = StatisticData(
                    start=dt_util.utc_from_timestamp(_start),
                    state=_state,
                    sum=_sum,
                )
        self.add_external_stats(stats=list(out.values()))

    def append_statistics(
        self, stats: list[Any] | None, sum: float, now: datetime
    ) -> float:
        """Append hourly recording rows as external statistics (initial import)."""
        statistics_to_push: list[StatisticData] = []
        if not stats:
            return sum
        for stat in stats:
            _date: datetime = stat["d"]
            raw = stat.get("value")
            try:
                _state = float(raw)
            except (TypeError, ValueError):
                if not getattr(self, "_non_numeric_stat_logged", False):
                    self._non_numeric_stat_logged = True
                    _LOGGER.warning(
                        "Recording %s skipped non-numeric value %r",
                        self.statistic_id,
                        raw,
                    )
                continue
            if _state == 0:
                continue
            sum += _state
            _LOGGER.debug(
                "Appending day to statistic table with id: %s. Date: %s, state: %s, sum: %s.",
                self.statistic_id,
                _date,
                _state,
                sum,
            )
            statistics_to_push.append(
                StatisticData(
                    start=_date,
                    state=_state,
                    sum=sum,
                )
            )
        self.add_external_stats(stats=statistics_to_push)
        self._last_reset = now
        return sum

    async def async_upsert_statistics(
        self, stats: list[Any] | None, now: datetime
    ) -> None:
        """Upsert hourly rows and recompute cumulative sums from the first change."""
        from ..recording_merge import (
            anchor_sum_before,
            first_changed_hour,
            merge_hour_states,
            recompute_hourly_tail,
            rows_to_maps,
        )

        if not stats:
            return
        incoming: dict[float, float] = {}
        starts: dict[float, datetime] = {}
        for stat in stats:
            _date: datetime = stat["d"]
            raw = stat.get("value")
            try:
                _state = float(raw)
            except (TypeError, ValueError):
                if not getattr(self, "_non_numeric_stat_logged", False):
                    self._non_numeric_stat_logged = True
                    _LOGGER.warning(
                        "Recording %s skipped non-numeric value %r",
                        self.statistic_id,
                        raw,
                    )
                continue
            ts = float(dt_util.as_timestamp(_date))
            starts[ts] = _date
            incoming[ts] = _state
        if not incoming:
            return
        first_ts = min(incoming)
        existing = await self.get_stats_from_ha_db(
            start_time=dt_util.utc_from_timestamp(first_ts) - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
        existing_states, existing_sums = rows_to_maps(existing.get(self.statistic_id))
        # New zero hours stay omitted; revisions to an existing hour keep zeros.
        trimmed = {
            ts: state
            for ts, state in incoming.items()
            if state != 0 or ts in existing_states
        }
        if not trimmed:
            return
        change_ts = first_changed_hour(existing_states, trimmed)
        if change_ts is None:
            return
        merged = merge_hour_states(existing_states, trimmed)
        anchor = anchor_sum_before(existing_sums, change_ts)
        tail = recompute_hourly_tail(merged, from_ts=change_ts, anchor_sum=anchor)
        statistics_to_push = [
            StatisticData(
                start=starts.get(ts) or dt_util.utc_from_timestamp(ts),
                state=state,
                sum=total,
            )
            for ts, state, total in tail
        ]
        self.add_external_stats(stats=statistics_to_push)
        self._last_reset = now

    async def _insert_statistics(self) -> None:
        """Insert external statistics."""
        async with self._statistic_import_lock:
            _sum: float = 0.0
            now = dt_util.now()
            last_stat = await self.get_last_stat()
            if not last_stat or self.statistic_id not in last_stat or len(last_stat[self.statistic_id]) == 0:
                _LOGGER.debug(
                    "Last stats not exist. Trying to fetch last 30 days of data."
                )
                all_stats = await self.fetch_past_data(
                    start_time=now - timedelta(days=30), stop_time=now
                )
                if not all_stats:
                    _LOGGER.warning("Stats not found.")
                    return
                self.append_statistics(
                    stats=list(all_stats.values()), sum=_sum, now=now
                )
                return

            start_of_day = dt_util.start_of_local_day()
            last_stat_row = last_stat[self.statistic_id][0]
            last_stat_start = timestamp_to_datetime_or_none(
                last_stat_row.get("start")
            )

            async def get_last_stats_in_ha() -> dict[str, list[Any]]:
                if not last_stat_start:
                    return {}
                start_time = dt_util.start_of_local_day(
                    last_stat_start
                ) - timedelta(hours=24)
                return await self.get_stats_from_ha_db(
                    start_time=start_time,
                    end_time=now,
                )

            last_stats = await get_last_stats_in_ha()

            async def get_last_stats_from_bosch_api() -> tuple[list[Any], float]:
                if self.statistic_id in last_stats and last_stats[self.statistic_id]:
                    last_stats_row = self.get_last_stats_before_date(
                        last_stats=last_stats, day=start_of_day
                    )
                else:
                    last_stats_row = last_stat_row
                start_time_raw = last_stats_row.get("start")
                _sum = cast(float, last_stats_row.get("sum", 0.0))

                start_time: datetime | None = None
                if isinstance(start_time_raw, (int, float)):
                    start_time = timestamp_to_datetime_or_none(start_time_raw)

                if not start_time:
                    _LOGGER.debug(
                        "Start time not found. %s found %s",
                        self.statistic_id,
                        start_time,
                    )
                elif start_time and start_time.date() < now.date() - timedelta(days=1):
                    diff = now - start_time
                    _LOGGER.debug(
                        "Last row of statistic %s found %s, missing %s with current sum %s",
                        self.statistic_id,
                        start_time,
                        diff,
                        _sum,
                    )
                    bosch_data = await self.fetch_past_data(
                        start_time=start_time, stop_time=now
                    )
                    return (
                        [
                            row
                            for row in bosch_data.values()
                            if row["d"] > start_time
                        ],
                        _sum,
                    )
                _LOGGER.debug(
                    "Returning state to put to statistic table %s",
                    self._bosch_object.state,
                )
                state = self._bosch_object.state or []
                if state and self.statistic_id in last_stats:
                    first_date_from_state = state[0]
                    last_stats_row = self.get_last_stats_before_date(
                        last_stats=last_stats, day=first_date_from_state["d"]
                    )
                    _sum = cast(float, last_stats_row.get("sum", 0.0))
                return list(state), _sum

            # Upsert when we have a last row, even if the window query is empty.
            bosch_stats, _sum = await get_last_stats_from_bosch_api()
            await self.async_upsert_statistics(stats=bosch_stats, now=now)

