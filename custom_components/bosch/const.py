"""Constants for the bosch component."""
import voluptuous as vol
from homeassistant.const import TEMP_CELSIUS, TEMP_FAHRENHEIT

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
