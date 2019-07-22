"""Constants for the bosch component."""
from bosch_thermostat_http.const import (HC_HEATING_STATUS,
                                         HC_ROOMTEMPERATURE,
                                         HC_CURRENT_ROOMSETPOINT,
                                         OPERATION_MODE, HC_HOLIDAY_MODE,
                                         DHW_CURRENT_WATERTEMP,
                                         DHW_OFFTEMP_LEVEL,
                                         DHW_HIGHTTEMP_LEVEL,
                                         DHW_CURRENT_SETPOINT)

DOMAIN = "bosch"
ACCESS_KEY = "access_key"
UUID = 'uuid'

GATEWAY = 'gateway'
CLIMATE = 'climate'
SENSOR = 'sensor'
WATER_HEATER = 'water_heater'

SUPPORTED_PLATFORMS = [
    'climate',
    'sensor',
    'water_heater'
]

STORAGE_VERSION = 1
STORAGE_KEY = DOMAIN

DHW_UPDATE_KEYS = [DHW_CURRENT_WATERTEMP, DHW_OFFTEMP_LEVEL, OPERATION_MODE,
                   DHW_HIGHTTEMP_LEVEL, DHW_CURRENT_SETPOINT,
                   "switchProgramsA"]
HCS_UPDATE_KEYS = [HC_HEATING_STATUS, HC_ROOMTEMPERATURE,
                   HC_CURRENT_ROOMSETPOINT, HC_HOLIDAY_MODE, OPERATION_MODE]

SIGNAL_CLIMATE_UPDATE_BOSCH = "bosch_climate_update"
SIGNAL_SENSOR_UPDATE_BOSCH = "bosch_sensor_update"
SIGNAL_DHW_UPDATE_BOSCH = "bosch_dhw_update"
