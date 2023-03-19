"""Bosch statistic helper for Recording/Energy sensor."""
from __future__ import annotations
import logging
from typing import Any
from datetime import datetime
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    timestamp_to_datetime_or_none,
)
from sqlalchemy.exc import IntegrityError
from homeassistant.util import dt as dt_util

try:
    from homeassistant.components.recorder.db_schema import StatisticsMeta
except ImportError:
    from homeassistant.components.recorder.models import StatisticsMeta
from homeassistant.components.recorder.util import session_scope
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.components.recorder import get_instance
from .base import BoschBaseSensor

_LOGGER = logging.getLogger(__name__)


class StatisticHelper(BoschBaseSensor):
    """Statistic helper class."""

    def __init__(self, new_stats_api: bool = False, **kwargs):
        """Initialize statistic helper."""
        self._short_id = None
        self._new_stats_api = new_stats_api
        super().__init__(**kwargs)

    async def move_old_entity_data_to_new(self, event_time=None) -> None:
        """Rename old entity_id in statistic table. Not working currently."""
        old_entity_id = self.entity_id
        _LOGGER.debug("Moving entity id statistic data to new format.")
        try:
            with session_scope(hass=self.hass) as session:
                session.query(StatisticsMeta).filter(
                    (StatisticsMeta.statistic_id == old_entity_id)
                    & (StatisticsMeta.source == "recorder")
                ).update(
                    {
                        StatisticsMeta.statistic_id: self.statistic_id,
                        StatisticsMeta.source: self._domain_name.lower(),
                        StatisticsMeta.name: self._name,
                    }
                )
        except IntegrityError as err:
            _LOGGER.error("Can't move entity id. It already exists. %s", err)

    @property
    def statistic_id(self) -> str:
        """External API statistic ID."""
        raise NotImplementedError()

    @property
    def statistic_metadata(self) -> StatisticMetaData:
        """Statistic Metadata recorder model class."""
        return StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=self._name,
            source=self._domain_name.lower(),
            statistic_id=self.statistic_id,
            unit_of_measurement=self._unit_of_measurement,
        )

    async def get_last_stat(self) -> dict[str, list[dict[str, Any]]]:
        return await get_instance(self.hass).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.statistic_id,
            True,
            {"state", "sum"},
        )

    async def get_stats(
        self, start_time: datetime, end_time: datetime
    ) -> dict[str, list[dict[str, Any]]]:
        """Get stats during period."""
        return await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start_time,
            end_time,
            [self.statistic_id],
            "hour",
            None,
            {"state", "sum"},
        )

    def add_external_stats(self, stats: list[StatisticData]) -> None:
        """Add external statistics."""
        self._state = -17
        if not stats:
            return
        async_add_external_statistics(self.hass, self.statistic_metadata, stats)

    def get_last_stats_before_date(
        self, last_stats: dict[str, list[dict[str, Any]]], day: datetime
    ):
        print("przeszukaj", last_stats)
        for stat in last_stats[self.statistic_id]:
            tstmp = timestamp_to_datetime_or_none(stat["start"])
            print(
                "tstsm",
                tstmp,
                day,
                tstmp < day,
                stat["start"],
                dt_util.as_timestamp(day),
            )
            if tstmp and tstmp < day:
                _LOGGER.debug("Last stat found %s", stat)
                return stat
        return last_stats[self.statistic_id][0]
