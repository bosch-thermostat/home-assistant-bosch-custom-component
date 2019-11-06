"""Sensors of Bosch thermostat."""
from .const import GET, PATH, ID, NAME
from .helper import BoschSingleEntity, BoschEntities
from .errors import ResponseError, Response404Error, SensorNoLongerAvailable


class Sensors(BoschEntities):
    """Sensors object containing multiple Sensor objects."""

    def __init__(self, requests, sensors=None, sensors_db=None, str_obj=None):
        """
        Initialize sensors.

        :param dict requests: { GET: get function, SUBMIT: submit function}
        """
        super().__init__(requests)
        self._items = {}
        for sensor_id in sensors:
            sensor = sensors_db.get(sensor_id)
            if sensor and sensor_id not in self._items:
                self._items[sensor_id] = Sensor(
                    self._requests, sensor_id, sensor[NAME], sensor[ID], str_obj
                )

    @property
    def sensors(self):
        """Get sensor list."""
        return self.get_items().values()


class Sensor(BoschSingleEntity):
    """Single sensor object."""

    def __init__(self, requests, attr_id, name, path, str_obj):
        """
        Single sensor init.

        :param dics requests: { GET: get function, SUBMIT: submit function}
        :param str name: name of the sensors
        :param str path: path to retrieve data from sensor.
        """
        self._requests = requests
        super().__init__(name, attr_id, str_obj, path)
        self._type = "sensor"

    @property
    def json_scheme(self):
        """Get json scheme of sensor."""
        return {NAME: self._main_data[NAME], ID: self._main_data[ID]}

    async def update(self):
        """Update sensor data."""
        try:
            result = await self._requests[GET](self._main_data[PATH])
            self.process_results(result)
            self._updated_initialized = True
        except Response404Error:
            raise SensorNoLongerAvailable("This sensor is no available.")
        except ResponseError:
            self._data = None
