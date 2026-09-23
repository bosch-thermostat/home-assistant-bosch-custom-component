"""Setup failures must reach Home Assistant's retry mechanism."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from custom_components.bosch import async_setup_entry
from custom_components.bosch.const import (
    ACCESS_KEY,
    ACCESS_TOKEN,
    CONF_DEVICE_TYPE,
    CONF_PROTOCOL,
    DOMAIN,
    UUID,
)
from homeassistant.exceptions import ConfigEntryNotReady

from bosch_thermostat_client.exceptions import DeviceException, EncryptionException


class SetupFailureTests(unittest.IsolatedAsyncioTestCase):
    async def call_setup(self, *, result=True, error=None):
        hass = SimpleNamespace(data={DOMAIN: {}})
        entry = Mock()
        entry.data = {
            UUID: "test-gateway",
            "address": "gateway.invalid",
            CONF_PROTOCOL: "HTTP",
            CONF_DEVICE_TYPE: "IVT",
            ACCESS_KEY: "",
            ACCESS_TOKEN: "",
        }
        gateway = Mock()
        gateway.async_init = AsyncMock(return_value=result, side_effect=error)
        with (
            patch("custom_components.bosch.BoschGatewayEntry", return_value=gateway),
            patch("custom_components.bosch.async_register_services") as register,
        ):
            try:
                return await async_setup_entry(hass, entry)
            finally:
                if error is not None or not result:
                    register.assert_not_called()

    async def test_device_failure_requests_setup_retry(self):
        error = DeviceException("Connection timed out")
        error.__cause__ = TimeoutError()
        with self.assertRaises(ConfigEntryNotReady) as caught:
            await self.call_setup(error=error)
        self.assertIs(caught.exception.__cause__, error)

    async def test_other_device_error_not_reclassified(self):
        with self.assertRaises(DeviceException):
            await self.call_setup(error=DeviceException("Optional endpoint"))

    async def test_success_is_unchanged(self):
        self.assertTrue(await self.call_setup())

    async def test_failed_init_is_not_success(self):
        self.assertFalse(await self.call_setup(result=False))

    async def test_encryption_error_not_reclassified(self):
        with self.assertRaises(EncryptionException):
            await self.call_setup(error=EncryptionException("Invalid response"))

    async def test_cancellation_propagates(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.call_setup(error=asyncio.CancelledError())


if __name__ == "__main__":
    unittest.main()
