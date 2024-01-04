"""Constants for the bosch component."""
from datetime import timedelta

import voluptuous as vol
from bosch_thermostat_client.const import DHW, HC, SC, ZN
from bosch_thermostat_client.const.easycontrol import DV
from homeassistant.const import UnitOfEnergy, UnitOfTemperature

DOMAIN = "bosch"
BOSCH_GATEWAY_ENTRY = "BoschGatewayEntry"
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
SIGNAL_BINARY_SENSOR_UPDATE_BOSCH = "bosch_binarysensor_update"
SIGNAL_DHW_UPDATE_BOSCH = "bosch_dhw_update"
SIGNAL_SOLAR_UPDATE_BOSCH = "bosch_solar_update"
SIGNAL_RECORDING_UPDATE_BOSCH = "bosch_recording_update"
SIGNAL_ENERGY_UPDATE_BOSCH = "bosch_energy_update"
SIGNAL_SWITCH = "bosch_switch_update"
SIGNAL_SELECT = "bosch_select_update"
SIGNAL_NUMBER = "bosch_number_update"
BOSCH_STATE = "bosch_state"

START = "start"
STOP = "stop"
SERVICE_CHARGE_SCHEMA = {vol.Optional(VALUE): vol.In([START, STOP])}

SERVICE_CHARGE_START = "set_dhw_charge"
SERVICE_PUT_STRING = "send_custom_put_string"
SERVICE_PUT_FLOAT = "send_custom_put_float"
SERVICE_GET = "send_custom_get"
SERVICE_DEBUG = "debug_scan"
SERVICE_UPDATE = "update_thermostat"
RECORDING_SERVICE_UPDATE = "update_recordings_sensor"
SERVICE_MOVE_OLD_DATA = "move_old_statistic_data"

SENSORS = "sensors"
SWITCHPOINT = "switchPoint"
CHARGE = "charge"
MINS = "mins"
SWITCH = "switch"


UNITS_CONVERTER = {
    "C": UnitOfTemperature.CELSIUS,
    UnitOfTemperature.CELSIUS: UnitOfTemperature.CELSIUS,
    "F": UnitOfTemperature.FAHRENHEIT,
    UnitOfTemperature.FAHRENHEIT: UnitOfTemperature.FAHRENHEIT,
    "%": "%",
    "l/min": "l/min",
    "l/h": "l/h",
    "kg/l": "kg/l",
    "mins": MINS,
    "kW": "kW",
    "kWh": UnitOfEnergy.KILO_WATT_HOUR,
    "Wh": "Wh",
    "Pascal": "Pascal",
    "bar": "bar",
    "µA": "µA",
    " ": None,
}

NOTIFICATION_ID = "bosch_notification"
SCAN_INTERVAL = timedelta(seconds=60)
FIRMWARE_SCAN_INTERVAL = timedelta(hours=4)
SCAN_SENSOR_INTERVAL = timedelta(seconds=120)
INTERVAL = "interval"
FW_INTERVAL = "fw_interval"
RECORDING_INTERVAL = "recording_interval"

CIRCUITS = [DHW, HC, SC, ZN, DV]
CIRCUITS_SENSOR_NAMES = {
    DHW: "Water heater",
    HC: "Heating circuit",
    SC: "Solar circuit",
    ZN: "Zone circuit",
    DV: "Device",
}

BINARY_SENSOR = "binary_sensor"
LAST_RESET = "last_reset"
