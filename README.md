# home-assistant-bosch-custom-component

HA custom component for Bosch thermostats.
If you like this component consider sponsoring my work: [:heart: Sponsor](https://github.com/sponsors/pszafer)

**Second maintainer needed!**

**Hi, I'm looking for help to make this component better**
https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/issues/414

**Latest version will only work with Home Assistant 2025.7 and Python >=3.12.**
For older HA look into release notes.

If possible and if it's ok with you please enable Home Assistant Analytics so I can see how many people uses this integration.

## Currently supported
### Supported protocols

- XMPP -> connect to bosch cloud!
- HTTP -> connect locally - available only for IVT devices.

### Supported types of devices

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
  - Buderus Logamatic TC100.2

## Installation
## Install using HACS (recommended)
If you do not have HACS installed yet visit https://hacs.xyz for installation instructions.

To add the this repository to HACS in your Home Assistant instance, use this My button:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=home-assistant-bosch-custom-component&owner=pszafer&category=Integration)

After installation, please restart Home Assistant. To add Dynamic Energy Cost to your Home Assistant instance, use this My button:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=home-assistant-bosch-custom-component)

To add the this repository to HACS in your Home Assistant instance, use this My button:
Please find an [installation guide](https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/wiki/Home-Assistant-Installation-Guide) in the wiki and further information.

<details>
<summary><b> Manual configuration steps</b></summary>

### Semi-Manual Installation with HACS

1. In Home Assistant go to HACS integrations section.
2. Click on the 3 dots in the top right corner.
3. Select "Custom repositories".
4. Add the URL (https://github.com/bosch-thermostat/home-assistant-bosch-custom-component) to the repository.
5. Select the integration category.
6. Click the "ADD" button.
7. Now you are able to download the integration.

### Manual Installation

1. Download the [latest release of home-assistant-bosch-custom-component](https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/releases/latest) and extract its contents.
2. Copy the `home-assistant-bosch-custom-component` folder into the `custom_components` directory located typically at `/config/custom_components/` in your Home Assistant directory.
3. Restart Home Assistant to recognize the newly added custom component.  
  <a href="https://my.home-assistant.io/redirect/developer_call_service/?service=homeassistant%2Erestart" target="_blank" rel="noreferrer noopener"><img src="https://my.home-assistant.io/badges/developer_call_service.svg" alt="Open your Home Assistant instance and show your service developer tools with a specific action selected." /></a>

### Add Integration

1. Navigate to Settings > Devices & Services.
2. Click Add Integration and search for "Bosch thermostat".
3. Select the Dynamic Energy Cost integration to initiate setup.

</details>

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

In case of a working integration within Home Assistant you may find issues in the way the Bosch environment is visible within HA. To identify the root cause, a debug log is helpful. To obtain these log, please follow the guidenance in the [wiki](https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/wiki/Home-Assistant-Obtain-Debug-Logs).

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

Detailed guidance can be found [here](https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/wiki/Trace-File-of-Communication-with-Bosch-Device-(Dev-Raw-Scan)).

**bosch.debug_scan** .

Download `json` file and attach it somewhere. The `json` file is stored under <hass-config>/www/bosch_scan.json. Please make sure the www folder exists prior to running the scan.

# First config help needed.

Come to [Discord channel](https://discord.gg/WeWQGNR) and let's try to figure out if you have unknown device for us or if there is issue with component.
