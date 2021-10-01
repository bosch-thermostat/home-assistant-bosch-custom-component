# home-assistant-bosch-custom-component

HA custom component for Bosch thermostats.
If you like this component consider sponsoring my work: [:heart: Sponsor](https://github.com/sponsors/pszafer)

**It will only work with at least Home Assistant 2021.9.x and and Python >=3.8.**

Supported protocols:

- XMPP -> connect to bosch cloud!
- HTTP -> connect locally - available only for IVT devices.

Supported types of devices:

- IVT (HTTP/XMPP):
  - RC300
  - RC200
- NEFIT(XMPP only):
  - Junkers CT100
  - Bosch Remote room controller CT100
- EASYCONTROL(XMPP only):
  - Bosch CT200

## Installation

## Manually

Download this repository into your configuration directory.

## HACS

Preferred way. Go to https://hacs.xyz/ and learn more about installation of custom components.

## Configuration

### Integration.

Go to integration page, add Bosch component and follow on going screens.
By default all sensors are disabled!
Go to integration device `Bosch sensors` and enable sensor you'd like to see.
If you have troubles, go to **wiki** and read more detailed installation instructions.

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
    bosch_thermostat_client: debug
```

# First config help needed.

Come to Discord channel https://discord.gg/WeWQGNR and let's try to figure out if you have unknown device for us or if there is issue with component.
