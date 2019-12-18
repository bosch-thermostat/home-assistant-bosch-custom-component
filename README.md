# home-assistant-bosch-custom-component
HA custom component for Bosch thermostat

**It will only work with Home Assistant 0.100 and higher.**

It is @alpha version of Bosch thermostat component.
Toghether with [@moustic999](https://github.com/moustic999) we developed library to communicate with Bosch gateway.
Bosch gateways are used by Buderus as well.

As Home Assistant is still missing some functions (scheduler, calendar, smarter water heater) Bosch component will be available as custom component.

What should work:
* configuring bosch thermostat
* importing Heating Circuits, domestic hot water and sensors
* setting temperature
* switching between programs.

## Configuration

### Files

```
bosch:
  address: <IP ADDRESS>
  password: "YOUR GATEWAY PASSWORD"
  access_key: "Access key to your gateway"
  sensors:
      - hotWater_t2
```

Full list of sensors in WIKI.

### Integration.

Go to integration page, add Bosch component and follow on going screens.
Screens and more instructions in WIKI.

PS. Autodiscovery not available for custom components.

# Help

Any help appreciated.
Open PR or issue.

Always attach debugscan if you have any troubles or something is missing.
To make debugscan go to HA developer tools -> Services and choose
**bosch.debug_scan** .

Download json file and attach it somewhere.

## Debugging
Example logger config for debugging:

```
logger:
  default: warning
  logs:
    custom_components.bosch: debug
    bosch_thermostat_http: debug
```

# Known bugs.
* initial loading takes about one minute.
* on RC300 DHW/water_heater it is supported only on Bosch ownprogram mode.

Bug reported in HA Lovelace - https://github.com/home-assistant/home-assistant-polymer/issues/3195

# First config help needed.
Come to Discord channel https://discord.gg/uWnWnx and let's try to figure out if you have unknown device for us or if there is issue with component.
