"""DataUpdateCoordinator for Bosch integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Protocol

from bosch_thermostat_client.exceptions import DeviceConnectionError, DeviceException
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .types import BoschGateway, BoschObject

_LOGGER = logging.getLogger(__name__)

# Sentinel: the gateway itself could not be reached, as opposed to a single
# object failing to update.
_UNREACHABLE = object()


class RecordingEntity(Protocol):
    """Entity that is refreshed on the hourly recording schedule."""

    enabled: bool
    bosch_object: BoschObject
    statistic_id: str

    async def async_update_recording(self) -> None:
        """Push the freshly fetched recording data to HA."""

    async def insert_statistics_range(self, start_time: datetime) -> None:
        """Import a single day of past data."""


class BoschDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Bosch data.

    Entities register the Bosch object backing them when they are added to HA
    and unregister on removal, so only objects with an enabled entity are
    polled - the same behaviour as the pre-coordinator update loop. Recording
    and energy sensors are kept on a separate hourly schedule.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        gateway: BoschGateway,
        uuid: str,
        entry: Any,
    ) -> None:
        """Initialize the coordinator."""
        self.gateway = gateway
        self.uuid = uuid
        self.entry = entry
        # registry id of the gateway device; entities link to it via_device_id
        self.gateway_device_id: str | None = None
        # keyed by id() with a refcount, as several entities can share one Bosch object
        self._objects: dict[int, BoschObject] = {}
        self._object_refs: dict[int, int] = {}
        self._recording_entities: list[RecordingEntity] = []
        self._recording_unsub: CALLBACK_TYPE | None = None

        # Requests are serialised by the library connectors' own lock, so the
        # updates below run concurrently without extra throttling here.
        scan_interval = entry.options.get("scan_interval", 60)

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"Bosch {uuid}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def async_shutdown(self) -> None:
        """Cancel the hourly recording schedule along with the regular refresh."""
        self.async_shutdown_recording()
        await super().async_shutdown()

    @property
    def recording_entities(self) -> list[RecordingEntity]:
        """Recording/energy entities currently added to HA."""
        return list(self._recording_entities)

    def register_object(self, obj: BoschObject) -> None:
        """Poll ``obj`` on every regular refresh."""
        key = id(obj)
        self._objects[key] = obj
        self._object_refs[key] = self._object_refs.get(key, 0) + 1

    def unregister_object(self, obj: BoschObject) -> None:
        """Stop polling ``obj`` once no entity uses it anymore."""
        key = id(obj)
        refs = self._object_refs.get(key, 0) - 1
        if refs > 0:
            self._object_refs[key] = refs
            return
        self._object_refs.pop(key, None)
        self._objects.pop(key, None)

    def register_recording_entity(self, entity: RecordingEntity) -> None:
        """Refresh ``entity`` on the hourly recording schedule."""
        if entity not in self._recording_entities:
            self._recording_entities.append(entity)

    def unregister_recording_entity(self, entity: RecordingEntity) -> None:
        """Remove ``entity`` from the hourly recording schedule."""
        if entity in self._recording_entities:
            self._recording_entities.remove(entity)

    def async_shutdown_recording(self) -> None:
        """Cancel the scheduled hourly recording update."""
        if self._recording_unsub is not None:
            self._recording_unsub()
            self._recording_unsub = None

    async def _async_update_data(self):
        """Fetch data from Bosch."""
        _LOGGER.debug("Updating Bosch thermostat entities via coordinator.")

        objects = list(self._objects.values())
        if objects:
            # The client absorbs an ordinary DeviceException inside update()
            # (a single missing endpoint must not fail the whole refresh) but
            # re-raises DeviceConnectionError. On XMPP that also means one
            # request timed out twice, and some paths time out on some models
            # every time, so a single object reporting it says nothing about
            # the gateway. Only when every object does is the gateway treated
            # as unreachable: UpdateFailed, and entities go unavailable
            # instead of keeping a stale value.
            async with asyncio.TaskGroup() as tg:
                tasks = [
                    tg.create_task(self._async_update_object(obj)) for obj in objects
                ]
            if all(task.result() is _UNREACHABLE for task in tasks):
                raise UpdateFailed(f"Bosch gateway {self.uuid} is unreachable")

        _LOGGER.debug("Bosch update completed successfully")
        return True

    async def _async_update_object(self, obj: BoschObject, **kwargs: Any) -> object:
        """Update a single Bosch object.

        Returns ``_UNREACHABLE`` when the gateway could not be reached at all,
        otherwise whether the update succeeded.
        """
        try:
            _LOGGER.debug("Updating Bosch object: %s", obj.name)
            await obj.update(**kwargs)
        except DeviceConnectionError as err:
            _LOGGER.debug(
                "Bosch gateway unreachable while updating %s: %s", obj.name, err
            )
            return _UNREACHABLE
        except DeviceException as err:
            _LOGGER.warning("Bosch object %s is not available: %s", obj.name, err)
            return False
        except Exception as err:
            _LOGGER.warning("Unexpected error updating %s: %s", obj.name, err)
            return False
        return True

    async def _async_push_recording_entity(self, entity: RecordingEntity) -> None:
        """Hand the freshly fetched recording data to the entity."""
        try:
            await entity.async_update_recording()
        except Exception as err:
            _LOGGER.warning(
                "Unexpected error updating recording entity %s: %s",
                entity.bosch_object.name,
                err,
            )

    async def async_recording_sensors_update(self, now: datetime | None = None) -> None:
        """Update of 1-hour sensors.

        It suppose to be called only once an hour
        so sensor get's average data from Bosch.
        """
        self.async_shutdown_recording()
        entities = [entity for entity in self._recording_entities if entity.enabled]
        now = dt_util.now()
        if entities:
            _LOGGER.debug("Updating %d Bosch 1-hour sensors.", len(entities))
            # Several entities can share one Bosch object (the three energy
            # sensors read one library object), so fetch each object once.
            objects = {
                id(entity.bosch_object): entity.bosch_object for entity in entities
            }
            # Recording/energy sensors fetch the data of the given (local)
            # time; the library's own default must not be relied on.
            async with asyncio.TaskGroup() as tg:
                for obj in objects.values():
                    tg.create_task(self._async_update_object(obj, time=now))
            async with asyncio.TaskGroup() as tg:
                for entity in entities:
                    tg.create_task(self._async_push_recording_entity(entity))
            _LOGGER.debug("Bosch 1-hour entitites updated.")

        def rounder(t):
            matching_seconds = [0]
            matching_minutes = [6]  # 6
            matching_hours = dt_util.parse_time_expression("*", 0, 23)
            return dt_util.find_next_time_expression_time(
                t, matching_seconds, matching_minutes, matching_hours
            )

        nexti = rounder(now + timedelta(seconds=1))
        self._recording_unsub = async_track_point_in_utc_time(
            self.hass, self.async_recording_sensors_update, nexti
        )
        _LOGGER.debug("Next update of 1-hour sensors scheduled at: %s", nexti)
