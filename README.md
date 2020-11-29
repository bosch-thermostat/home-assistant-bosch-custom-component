# home-assistant-bosch-custom-component
HA custom component for Bosch thermostat

**It will only work with Home Assistant 0.109 and higher.**

It is @alpha version of Bosch thermostat component.
Supported protocols:
- XMPP -> connect to bosch cloud!
- HTTP -> connect locally - not available for many devices.

Supported types of devices:
- IVT (HTTP/XMPP):
  - RC300
- NEFIT(XMPP only):
  - Junkers CT100
  - Bosch Remote room controller CT100

** Not working with CT200 **
Help to get Magic key from Bosch app appreciated.

## Configuration

### Integration.

Go to integration page, add Bosch component and follow on going screens.
By default all sensors are disabled!
Go to integration device `Bosch sensors` and enable sensor you'd like to see.

# Help

Any help appreciated.
Open PR or issue.

Always attach debugscan if you have any troubles or something is missing.
To make debugscan go to HA developer tools -> Services and choose
**bosch.debug_scan** .

Download `json` file and attach it somewhere. The `json` file is stored under <hass-config>/www/bosch_scan.json. Please make sure the www folder exists prior to running the scan.

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

Bug reported in HA Lovelace - https://github.com/home-assistant/home-assistant-polymer/issues/3195

# First config help needed.
Come to Discord channel https://discord.gg/WeWQGNR and let's try to figure out if you have unknown device for us or if there is issue with component.
