# home-assistant-bosch-custom-component
HA custom component for Bosch thermostat

It is @alpha version of Bosch thermostat component.
Toghether with [@moustic999](https://github.com/moustic999) we developed library to communicate with Bosch gateway.
Bosch gateways are used by Buderus as well.

As Home Assistant is still missing some functions (scheduler, calendar, smarter water heater), 
Bosch component will be available as custom component.

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
```

### Integration.

HA doesn't support configuring custom_components through integration yet.
It will be available soon.

# Help

Any help appreciated.
Open PR or issue.

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
* click in lovelace thermostat card on active mode switching to idle even though Bosch doesn't support idle.
Bug reported in HA Lovelace - https://github.com/home-assistant/home-assistant-polymer/issues/3195
