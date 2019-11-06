"""Gateway module connecting to Bosch thermostat."""
import asyncio
import json
import logging

from .circuits import Circuits
from .const import (
    DHW,
    DICT,
    GATEWAY,
    GET,
    HC,
    ROOT_PATHS,
    SENSORS,
    SUBMIT,
    UUID,
    VALUE,
    MODELS,
    VALUES,
    SYSTEM_INFO,
    NAME,
    DATE,
    FIRMWARE_VERSION,
    DEFAULT_SENSORS,
)
from .encryption import Encryption
from .errors import RequestError, Response404Error, ResponseError
from .helper import deep_into
from .sensors import Sensors
from .strings import Strings

_LOGGER = logging.getLogger(__name__)


class Gateway:
    """Gateway to Bosch thermostat."""

    def __init__(self, session, host, access_key, password=None):
        """
        Initialize gateway.

        :param access_key:
        :param password:
        :param host:
        """
        if type(session).__name__ == "ClientSession":
            from .http_connector import HttpConnector

            self._connector = HttpConnector(host, session)
        else:
            return
        self._host = host
        self._encryption = None
        self._lock = asyncio.Lock()
        if password:
            access_token = access_key.replace("-", "")
            self._encryption = Encryption(access_token, password)
        else:
            self._encryption = Encryption(access_key)
        self._data = {GATEWAY: {}, HC: None, DHW: None, SENSORS: None}
        self._requests = {GET: self.get, SUBMIT: self.set_value}
        self._firmware_version = None
        self._device = None
        self._db = None
        self._str = None
        self._initialized = None

    async def initialize(self):
        """Initialize gateway asynchronously."""
        from .db import get_db_of_firmware, get_initial_db

        initial_db = get_initial_db()
        self._str = Strings(initial_db[DICT])
        await self._update_info(initial_db.get(GATEWAY))
        self._firmware_version = self._data[GATEWAY].get(FIRMWARE_VERSION)
        self._device = await self.get_device_type(initial_db)
        self._db = get_db_of_firmware(self._device[VALUE], self.firmware)
        if self._db and self._device:
            initial_db.pop(MODELS, None)
            self._db.update(initial_db)
            self._initialized = True

    async def get_device_type(self, _db):
        """Find device model."""
        system_info = self._data[GATEWAY].get(SYSTEM_INFO)
        model_scheme = _db[MODELS]
        for info in system_info:
            model = model_scheme.get(info.get("Id", -1))
            if model:
                return model

    async def _update_info(self, initial_db):
        """Update gateway info from Bosch device."""
        for name, uri in initial_db.items():
            response = await self.get(uri)
            if self._str.val in response:
                self._data[GATEWAY][name] = response[self._str.val]
            elif name == SYSTEM_INFO:
                self._data[GATEWAY][SYSTEM_INFO] = response.get(VALUES, [])

    @property
    def host(self):
        return self._host

    @property
    def device_name(self):
        """Device friendly name based on model."""
        return self._device[NAME]

    def get_items(self, data_type):
        """Get items on types like Sensors, Heating Circuits etc."""
        return self._data[data_type].get_items()

    async def current_date(self):
        """Find current datetime of gateway."""
        response = await self.get(self._db[GATEWAY].get(DATE))
        val = response.get(self._str.val)
        self._data[GATEWAY][DATE] = val
        return val

    @property
    def database(self):
        """Retrieve db scheme."""
        return self._db

    def set_timeout(self, timeout):
        """Set timeout for API calls."""
        self._connector.set_timeout(timeout)

    @property
    def access_key(self):
        """Return key to store in config entry."""
        return self._encryption.key

    @property
    def heating_circuits(self):
        """Get circuit list."""
        return self._data[HC].circuits

    def get_circuits(self, ctype):
        """Get circuit list."""
        return self._data[ctype].circuits if ctype in self._data else None

    @property
    def dhw_circuits(self):
        """Get circuit list."""
        return self._data[DHW].circuits

    @property
    def sensors(self):
        """Get sensors list."""
        return self._data[SENSORS].sensors

    @property
    def firmware(self):
        """Get firmware."""
        return self._firmware_version

    def get_info(self, key):
        """Get gateway info given key."""
        if key in self._data[GATEWAY]:
            return self._data[GATEWAY][key]
        return None

    async def initialize_circuits(self, circ_type):
        """Initialize circuits objects of given type (dhw/hcs)."""
        self._data[circ_type] = Circuits(self._requests, circ_type)
        await self._data[circ_type].initialize(self._db, self._str, self.current_date)
        return self.get_circuits(circ_type)

    def initialize_sensors(self, choosed_sensors=None):
        """Initialize sensors objects."""
        if not choosed_sensors:
            choosed_sensors = self._db.get(DEFAULT_SENSORS, [])
        self._data[SENSORS] = Sensors(
            self._requests, choosed_sensors, self._db[SENSORS], self._str
        )
        return self.sensors

    async def rawscan(self):
        """Print out all info from gateway."""
        rawlist = []
        for root in ROOT_PATHS:
            rawlist.append(await deep_into(root, [], self.get))
        return rawlist

    async def smallscan(self):
        """Print out all info from gateway from HC2 only for now."""
        rawlist = []
        paths = [
            "/heatingCircuits/hc1/roomtemperature",
            "/heatingCircuits/hc1/operationMode",
            "/heatingCircuits/hc1/currentRoomSetpoint",
            "/heatingCircuits/hc1/manualRoomSetpoint",
            "/heatingCircuits/hc1/temperatureRoomSetpoint",
            "/heatingCircuits/hc1/status",
            "/heatingCircuits/hc1/activeSwitchProgram",
            "/heatingCircuits/hc1/temporaryRoomSetpoint",
        ]
        for root in paths:
            rawlist.append(await deep_into(root, [], self.get))
        return rawlist

    async def check_connection(self):
        """Check if we are able to connect to Bosch device and return UUID."""
        try:
            if not self._initialized:
                await self.initialize()
            else:
                response = await self.get(self._db[GATEWAY][UUID])
                if self._str.val in response:
                    self._data[GATEWAY][UUID] = response[self._str.val]
            uuid = self.get_info(UUID)
            return uuid
        except RequestError:
            return False

    async def get(self, path):
        """Get message from API with given path."""
        async with self._lock:
            try:
                encrypted = await self._connector.request(path)
                result = self._encryption.decrypt(encrypted)
                jsondata = json.loads(result)
                return jsondata
            except json.JSONDecodeError as err:
                raise ResponseError(f"Unable to decode Json response : {err}")
            except Response404Error:
                raise ResponseError(f"Path does not exist : {path}")

    async def _set(self, path, data):
        """Send message to API with given path."""
        async with self._lock:
            encrypted = self._encryption.encrypt(data)
            result = await self._connector.submit(path, encrypted)
            return result

    async def set_value(self, path, value):
        """Set value for thermostat."""
        data = json.dumps({"value": value})
        result = await self._set(path, data)
        return result
