""" CONST which are not used and maybe not needed, but don't wont to lost it yet."""



DHEATING_WATER_CIRCUIT_LIST = {
    DHW_CURRENT_WATERTEMP: DHW+'/dhw{}/actualTemp',
    DHW_CURRENT_SETPOINT: DHW+'/dhw{}/currentSetpoint',
    DHW_WATERFLOW: DHW+'/dhw{}/waterFlow',
    DHW_WORKINGTIME: DHW+'/dhw{}/workingTime',
}


#
# _HEATING_CIRCUIT_LIST = {
#     _HC_CURRENT_ROOMSETPOINT: HC+'/{}/currentRoomSetpoint',
#     _HC_MANUAL_ROOMSETPOINT: HC+'/{}/manualRoomSetpoint',
#     OPERATION_MODE: HC+'/{}/operationMode',
#     _HC_SETPOINT_ROOMTEMPERATURE: HC+'/{}/temperatureRoomSetpoint',
#     _HC_CURRENT_ROOMTEMPERATURE: HC+'/{}/roomtemperature'
# }

SENSORS_CAPABILITIES = [
    '/system/sensors/temperatures/outdoor_t1',
    '/system/sensors/temperatures/supply_t1_setpoint',
    '/system/sensors/temperatures/supply_t1',
    '/system/sensors/temperatures/hotWater_t2',
    '/system/sensors/temperatures/return',
    '/heatSources/actualPower',
    '/heatSources/actualModulation',
    '/heatSources/burnerModulationSetpoint',
    '/heatSources/burnerPowerSetpoint',
    '/heatSources/flameStatus',
    '/heatSources/CHpumpModulation',
    '/heatSources/systemPressure',
    '/heatSources/flameCurrent',
    '/heatSources/workingTime',
    '/heatSources/numberOfStarts'
]

DHW_WATERFLOW = "waterFlow"
DHW_WORKINGTIME = "workingTime"
DHW_OFFTEMP_LEVEL = "temperatureLevelsoff"

DETAILED_CAPABILITIES = {
    HC_CAPABILITY :  ['/heatingCircuits/{}/currentRoomSetpoint',
                          '/heatingCircuits/{}/operationMode',
                          '/heatingCircuits/{}/roomtemperature'],
    DHW_CAPABILITY : ['/dhwCircuits/{}/currentSetpoint',
              '/dhwCircuits/{}/operationMode',
              '/dhwCircuits/{}/actualTemp'],
    SOLAR_CAPACITY :[]
    }

TYPE_INFO = "info"
TYPE_SENSOR = "sensor"
TYPE_HEATING = "heating"

""" Section of sensor friendly names. To be used in future. """
SENSOR_FRIENDLY_NAMES = {
    'outdoor_t1': 'outdoor Temp',
    'supply_t1_setpoint': 'supply Temp Setpoint',
    'supply_t1': 'supply Temp',
    'return': 'return Temp',
    'hotWater_t2': 'hotWater'
}


SENSOR_NAME = "sensor_name"
SENSOR_VALUE = "sensor_value"
SENSOR_TYPE = "sensor_type"
SENSOR_UNIT = "sensor_unit_of_measurment"



HC_CAPABILITY = 'heatingCircuit'
DHW_CAPABILITY = 'hotWater'
SOLAR_CAPACITY = 'solar'
SENSOR_CAPACITY = 'sensor'
