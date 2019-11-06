"""HTTP connector class to Bosch thermostat."""
import logging
from aiohttp import client_exceptions
from asyncio import TimeoutError

from .const import HTTP_HEADER
from .errors import RequestError, Response404Error, ResponseError

_LOGGER = logging.getLogger(__name__)


class HttpConnector:
    """HTTP connector to Bosch thermostat."""

    def __init__(self, host, websession):
        """Init of HTTP connector."""
        self._host = host
        self._websession = websession
        self._request_timeout = 10

    async def request(self, path):
        """Make a get request to the API."""
        _LOGGER.debug("Sending request to %s", path)
        try:
            async with self._websession.get(
                self._format_url(path),
                headers=HTTP_HEADER,
                timeout=self._request_timeout,
                skip_auto_headers=["Accept-Encoding", "Accept"],
            ) as res:
                if res.status == 200:
                    if res.content_type != "application/json":
                        raise ResponseError(f"Invalid content type: {res.content_type}")
                    else:
                        data = await res.text()
                        _LOGGER.debug("Retrieve data for %s - %s", path, data)
                        return data
                elif res.status == 404:
                    raise Response404Error(f"URI not exists: {path}")
                else:
                    raise ResponseError(f"Invalid response code: {res.status}")
        except (
            client_exceptions.ClientError,
            client_exceptions.ClientConnectorError,
            TimeoutError,
        ) as err:
            raise RequestError(f"Error requesting data from {path}: {err}") from err

    async def submit(self, path, data):
        """Make a put request to the API."""
        try:
            _LOGGER.debug("Sending request to %s with %s", path, data)
            async with self._websession.put(
                self._format_url(path),
                data=data,
                headers=HTTP_HEADER,
                timeout=self._request_timeout,
            ) as req:
                data = await req.text()
                if not data and req.status == 204:
                    return True
                return data
        except (client_exceptions.ClientError, TimeoutError) as err:
            raise RequestError(
                f"Error putting data to {self._host}, path: {path}, message: {err}"
            )

    def _format_url(self, path):
        """Format URL to make requests to gateway."""
        return f"http://{self._host}{path}"

    def set_timeout(self, timeout=10):
        """Set timeout for API calls."""
        self._request_timeout = timeout
