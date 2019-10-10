"""Constants for the bosch component."""
from homeassistant.const import (
    TEMP_CELSIUS, TEMP_FAHRENHEIT)
# from bosch_thermostat_http.const import (HC_HEATING_STATUS,
#                                          HC_ROOMTEMPERATURE,
#                                          HC_CURRENT_ROOMSETPOINT,
#                                          OPERATION_MODE, HC_HOLIDAY_MODE,
#                                          DHW_CURRENT_WATERTEMP,
#                                          DHW_OFFTEMP_LEVEL,
#                                          DHW_HIGHTTEMP_LEVEL,
#                                          DHW_CURRENT_SETPOINT)

DOMAIN = "bosch"
ACCESS_KEY = "access_key"
UUID = 'uuid'

GATEWAY = 'gateway'
CLIMATE = 'climate'
SENSOR = 'sensor'
WATER_HEATER = 'water_heater'
BOSCH_GW_ENTRY = "BoschGatewayEntry"

SUPPORTED_PLATFORMS = [
    'climate',
    'sensor',
    'water_heater'
]

STORAGE_VERSION = 2
STORAGE_KEY = DOMAIN

# DHW_UPDATE_KEYS = [DHW_CURRENT_WATERTEMP, DHW_OFFTEMP_LEVEL, OPERATION_MODE,
#                    DHW_HIGHTTEMP_LEVEL, DHW_CURRENT_SETPOINT,
#                    "switchProgramsA"]
# HCS_UPDATE_KEYS = [HC_HEATING_STATUS, HC_ROOMTEMPERATURE,
#                    HC_CURRENT_ROOMSETPOINT, HC_HOLIDAY_MODE, OPERATION_MODE]

SIGNAL_CLIMATE_UPDATE_BOSCH = "bosch_climate_update"
SIGNAL_SENSOR_UPDATE_BOSCH = "bosch_sensor_update"
SIGNAL_DHW_UPDATE_BOSCH = "bosch_dhw_update"

DATABASE = "db"
HCS = "hcs"
DHWS = "dhws"
SENSORS = "sensors"

UNITS_CONVERTER = {
    'C': TEMP_CELSIUS,
    'F': TEMP_FAHRENHEIT,
    '%': '%',
    'l/min': 'l/min',
    'l/h': 'l/h',
    'kg/l': 'kg/l',
    'mins': 'mins',
    'kW': 'kW',
    'kWh': 'kWh',
    'Pascal': 'Pascal',
    'bar': 'bar',
    'µA': 'µA',
    ' ': None
}
