"""Constants for the bosch component."""
from datetime import timedelta

import voluptuous as vol
from homeassistant.const import TEMP_CELSIUS, TEMP_FAHRENHEIT
from datetime import timedelta

DOMAIN = "bosch"
ACCESS_KEY = "access_key"
ACCESS_TOKEN = "access_token"
UUID = "uuid"

CONF_PROTOCOL = "http_xmpp"
CONF_DEVICE_TYPE = "device_type"

GATEWAY = "gateway"
CLIMATE = "climate"
# SENSOR = "sensor"
SOLAR = "solar"
WATER_HEATER = "water_heater"
VALUE = "value"

SIGNAL_BOSCH = "bosch_signal"
DEFAULT_MIN_TEMP = 0
DEFAULT_MAX_TEMP = 100

SIGNAL_CLIMATE_UPDATE_BOSCH = "bosch_climate_update"
SIGNAL_SENSOR_UPDATE_BOSCH = "bosch_sensor_update"
SIGNAL_DHW_UPDATE_BOSCH = "bosch_dhw_update"
SIGNAL_SOLAR_UPDATE_BOSCH = "bosch_solar_update"
BOSCH_STATE = "bosch_state"

SERVICE_CHARGE_SCHEMA = {vol.Optional(VALUE): vol.In(["start", "stop"])}

SERVICE_CHARGE_START = "set_dhw_charge"
SERVICE_DEBUG = "debug_scan"
SERVICE_UPDATE = "update_thermostat"

SENSORS = "sensors"
SWITCHPOINT = "switchPoint"
CHARGE = "charge"

UNITS_CONVERTER = {
    "C": TEMP_CELSIUS,
    "F": TEMP_FAHRENHEIT,
    "%": "%",
    "l/min": "l/min",
    "l/h": "l/h",
    "kg/l": "kg/l",
    "mins": "mins",
    "kW": "kW",
    "kWh": "kWh",
    "Wh": "Wh",
    "Pascal": "Pascal",
    "bar": "bar",
    "µA": "µA",
    " ": None,
}

NOTIFICATION_ID = "bosch_notification"
SCAN_INTERVAL = timedelta(seconds=30)
FIRMWARE_SCAN_INTERVAL = timedelta(hours=4)
SCAN_SENSOR_INTERVAL = timedelta(seconds=120)
INTERVAL = "interval"
FW_INTERVAL = "fw_interval"
