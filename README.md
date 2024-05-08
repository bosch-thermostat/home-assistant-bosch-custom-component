# home-assistant-bosch-custom-component

HA custom component for Bosch thermostats.
If you like this component consider sponsoring my work: [:heart: Sponsor](https://github.com/sponsors/pszafer)

**Latest version will only work with Home Assistant 2024.4 and Python >=3.12.**
For older HA look into release notes.

If possible and if it's ok with you please enable Home Assistant Analytics so I can see how many people uses this integration.

Supported protocols:

- XMPP -> connect to bosch cloud!
- HTTP -> connect locally - available only for IVT devices.

Supported types of devices:

- IVT (HTTP/XMPP):
  - RC300
  - RC200
  - RC35
  - RC30
  - RC20
- NEFIT(XMPP only):
  - Junkers CT100
  - Bosch Remote room controller CT100
- EASYCONTROL(XMPP only):
  - Bosch CT200

## Installation

Please find an installation guide (https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/wiki/Home-Assistant-Installation-Guide) in the wiki and further information.

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

## Home Assistant debugging log

In case of a working integration within Home Assistant you may find issues in the way the Bosch environment is visible within HA. To identify the root cause, a debug log is helpful. To obtain these log, please follow the guidenance in the wiki https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/wiki/Home-Assistant-Obtain-Debug-Logs.

Example logger config for debugging:

```
logger:
  default: warning
  logs:
    custom_components.bosch: debug
    bosch_thermostat_client: debug
```

## Bosch system scan via raw scan

The integration allows a raw scan of the connected Bosch devices via Home Assistant or Linux system. This is useful, if your installation fails or does not show devices or sensors you know to be existing.

Detailed guidance can be found at https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/wiki/Trace-File-of-Communication-with-Bosch-Device-(Dev-Raw-Scan)

**bosch.debug_scan** .

Download `json` file and attach it somewhere. The `json` file is stored under <hass-config>/www/bosch_scan.json. Please make sure the www folder exists prior to running the scan.

# First config help needed.

Come to Discord channel https://discord.gg/WeWQGNR and let's try to figure out if you have unknown device for us or if there is issue with component.
