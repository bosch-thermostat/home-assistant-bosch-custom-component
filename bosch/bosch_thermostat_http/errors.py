"""Bosch Themrostat errors."""


class BoschException(Exception):
    """Base error for bosch_Thermostat."""


class RequestError(BoschException):
    """
    Invalid request.

    Unable to fulfill request.
    Raised when host or API cannot be reached.
    """


class ResponseError(BoschException):
    """Invalid response."""


class Response404Error(BoschException):
    """Invalid response."""


class SensorNoLongerAvailable(BoschException):
    """Invalid response."""


class EncryptionError(BoschException):
    """Unable to decrypt."""
