# home-assistant-bosch-custom-component

HA custom component for Bosch thermostats.
If you like this component consider sponsoring my work: [:heart: Sponsor](https://github.com/sponsors/pszafer)

**Second maintainer needed!**

**Hi, I'm looking for help to make this component better**
https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/issues/414

**Latest version targets Home Assistant 2026.11 (minimum HACS: 2026.8.0) and Python >=3.12.**
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
  - Buderus Logamatic TC100.2

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

Device **Configure** options:

- **Use new statistic API** — write EasyControl energy and IVT recordings into Home Assistant long-term statistics (Energy dashboard). Entities show `-17` by default; use `recording:…external` (not `sensor.*`) on the Energy dashboard and statistics-graph cards.
- **Show last-hour recording values** — optional display only; last settled hour on entities instead of `-17`. Does not replace `recording:…external` for graphs. Default off.
- **Energy stats repair days** — auto-reimport window (0–30, default 7, 0 disables) after EasyControl energy JSON keys change (`eCH` → `gCh`). Does not clean already-wrong data by itself.
- **Virtual heat-pump diagnostics** — register **experimental** derived IVT heat-pump sensors. Every entity stays **disabled** until you enable it.

## Energy statistics and repair (EasyControl CT200)

EasyControl `/energy/history` is **one daily total per day** (`gCh`/`gHw`, older `eCH`/`eHW`). History on the thermostat is about **2–3 months**. Today is never imported.

IVT / KM200 uses a different export (`/recordings/…?interval=YYYY-M-D`, 24 hourly slots, about **4 months**). The energy repair services below do **not** apply to IVT recordings.

If heating kWh was stored on the hot-water statistic (or the reverse), new imports go to the correct series. To rewrite recent days, Developer tools → Actions:

```yaml
action: bosch.repair_energy_statistics
target:
  device_id: YOUR_BOSCH_DEVICE_ID
data:
  days: 7
  logical_attr: all
```

The gateway is queried first. If any requested day is missing, repair **aborts and does not clear** Home Assistant. `logical_attr` can be `all`, `ch`, or `hw`.

Leftover wrong series are not deleted. Rebind Energy dashboard if needed, or wipe one id:

```yaml
action: bosch.clear_energy_statistics
target:
  device_id: YOUR_BOSCH_DEVICE_ID
data:
  statistic_id: energy:gchenergy_central_heatingexternal
  reimport: true
```

Bosch does not publish an “environment” recording. The integration derives:

`recording:renvironmentexternal` = `max(0, outputProduced − compressor)` per hour

It also derives heating degree-hours from the outdoor recording (base 15 °C):

`recording:rheatingdegreehoursexternal` = `max(0, 15 − outdoor_hour)` per hour (`°C·h`)

Chart compressor or produced against HDH; the slope is roughly **kWh per degree-hour** (weather-normalized efficiency).

Optional backfill of past days from existing statistics (environment + HDH; long ranges are chunked automatically):

```yaml
service: bosch.backfill_environment_energy
target:
  device_id: <your bosch gateway device id>
data:
  start_date: "2024-06-01"
  end_date: "2026-11-13"
```

IVT recordings: `bosch.fetch_recordings_sensor_range` with the recording `statistic_id` and a date.

## Pool climate (IVT / KM200)

When the gateway exposes `heatSources/poolStatus`, `poolTemperature`, and `poolSetpointTemperature`, the integration creates a **Pool** climate entity (heat/off + target temperature) as a child device of the gateway. No extra option. Reload after update. Setpoint writes need installer/write access on the gateway.

## Virtual heat-pump sensors (IVT / HTTP)

**Experimental.** Derived from gateway paths, not certified Bosch diagnostics. Mode, requestors, and the efficiency hint can be wrong. Enable only if you accept that.

Only when **Virtual heat-pump diagnostics** is on and protocol is **HTTP** (local KM200, not cloud XMPP). Entities live on the child device **Heat pump diagnostics** and are **disabled** by default.

Live mode/delta/circuit sensors fill on the next 60s refresh. **COP / last-hour / efficiency hint** read gateway `energyMonitoring` (not HA history) and stay `Unknown` until the next hourly pull (~`:06`). If the COP today more-info chart stays empty while the state is numeric, remove the old null-unit statistic once under **Developer tools → Statistics**.

Full reference (mode states, requestors, COP, efficiency hint, compressor split): [docs/virtual-heatpump-sensors.md](docs/virtual-heatpump-sensors.md).

# Help

Any help appreciated.
Open PR or issue.

Always attach debugscan if you have any troubles or something is missing.
To make debugscan go to HA developer tools -> Services and choose

## Setup fails with "Unable to decrypt" or "Wrong IP or credentials"

If the credentials look correct but setup still fails with a decryption error, the usual
cause on **Buderus KM100 / KM200** gateways is that the device password was never actually
written to the gateway.

The **MyBuderus** app pairs via the QR code on the device and does not need the device
password — but it still prompts you to set one, and does not save it. The separate
**Buderus MyDevice** app connects locally and does set it.

Also note the device password is neither your SingleKey ID nor your MyBuderus account
password.

Full walkthrough, including a command to verify the password before retrying in Home
Assistant: [Setting the device password on Buderus gateways](https://github.com/bosch-thermostat/home-assistant-bosch-custom-component/wiki/Home-Assistant-Installation-Guide#setting-the-device-password-on-buderus-gateways-km100-km200)

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
