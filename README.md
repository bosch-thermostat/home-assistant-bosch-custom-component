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

Only when **Virtual heat-pump diagnostics** is on and protocol is **HTTP** (local KM200, not cloud XMPP). Saving Configure reloads the integration.

They belong to the **Bosch thermostat** integration as a child device of the gateway:

**Settings → Devices & services → Bosch thermostat → Heat pump diagnostics**

All entities are **disabled**. On that device, enable **Show disabled entities**, then turn on the ones you want. After a reload they fill with the integration’s first refresh. COP, backup share, and last-hour kWh wait for the hourly recording pull (up to about an hour, or the next `:06`).

Requestors can overlap. `dhw` when DHW setpoint is not 0; a circuit when the compressor is on and appliance supply is within 1 °C of that circuit’s actual supply (setpoint used only if actual is missing; usually one); `pool` when pool status is not `off`. Pump running alone is circulation, not a heat request. Efficiency hint is a coarse cutoff, not a fault.

- **Heat pump mode** — `idle`, `circulation`, `compressor`, `space_heating`, `dhw`, `dhw_and_heating`, `pool`, `pool_and_heating`
- **Compressor active** — modulation above 0
- **DHW requested** — hot-water setpoint not 0
- **DHW charging** — `charge=start` only
- **DHW temperature gap** — setpoint minus tank temperature (°C)
- **Pool requested** — pool status not `off`
- **Pool temperature gap** — pool setpoint minus pool temperature (°C)
- **Space heating active** — at least one circuit requests heat
- **Heating circuits requesting** — count of matching circuits
- **Heat requestors** — comma list, e.g. `dhw,hc2,pool`
- **Primary heating circuit** — requesting circuit (appliance supply match); if hc1 (buffer) and another HC both match, prefer the non-hc1; else highest pump modulation
- **hcN requesting heat** — one binary sensor per heating circuit
- **hcN room sensor fault** — room temperature at or below −50 °C (one per circuit)
- **Heat source delta** — supply minus return (°C)
- **COP today** — produced heat / compressor electricity. Attributes: `produced_kwh`, `compressor_kwh`
- **COP last 24h** — rolling 24h produced / compressor (settled hours only). Attributes: `produced_kwh`, `compressor_kwh`
- **COP month / year** — produced heat / consumed electricity (no compressor period totals)
- **Backup heater share today / month / year** — e-heater / consumed electricity (%)
- **Backup heater used today** — e-heater today above 0
- **Last hour electricity / heat / backup heater** — latest completed hourly kWh (`consumedEnergy` / `outputProduced` / `eheater`)
- **hcN / dhw / pool compressor minutes today** — compressor-on time attributed to that sink
- **hcN / dhw / pool compressor share today** — % of compressor-on time (not a Bosch per-circuit kWh meter)
- **Heat pump efficiency hint** — coarse daily check (not a fault). Attributes include `cop_today`, `backup_share`, `outdoor`, `cop_min`, `spread`. States:
  - `unknown` — not enough data yet (consumed today under 1 kWh, or produced missing)
  - `check_backup` — e-heater is ≥ 20% of today's electricity
  - `check_cop` — COP today below the outdoor-based floor (≥5 °C → 2.8; ≥0 °C → 2.3; ≥−7 °C → 1.8; colder → 1.5; unknown outdoor → 2.3)
  - `check_spread` — compressor on but |supply − return| under 1 °C
  - `ok` — none of the above

### If the efficiency hint is not `ok`

These are hints for investigation, not Bosch error codes. Compare with the Bosch / MyBuderus app and outdoor weather before changing settings.

**`unknown`**
- Wait until the hourly recording pull has run (about an hour, or after `:06`) and today has ≥ 1 kWh consumed.
- Confirm energy monitoring / recording sensors are enabled and updating.
- Early morning or after a reload with empty day totals is normal.

**`check_backup`**
- Backup (e-heater) is covering a large share of electricity — expensive and expected in deep cold, less so in mild weather.
- Check whether DHW or space setpoints force high flow temps the compressor cannot meet alone.
- Look at quiet hours / “boost” / legionella or forced electric modes on the controller.
- If outdoor is mild and backup keeps running, check defrost cycles, low refrigerant symptoms (via installer), or oversized DHW demand.

**`check_cop`**
- Today’s produced/compressor ratio is below the outdoor floor in the entity attributes (`cop_today` vs `cop_min`).
- Confirm `produced_kwh` / `compressor_kwh` on the COP today sensor app (Heat pump + Environment = Sum); wrong series would fake a bad COP.
- Typical causes: high flow temperature, frequent short cycles, heavy DHW, icing/defrost, or backup already in the mix (often with `check_backup`).
- Overlapping demand can hurt COP: DHW charge + several HCs / pool at once forces higher power and less efficient operating points. Prefer fewer concurrent requestors when possible.
- Lower supply setpoints / heating curve if comfort allows; avoid repeated manual boosts.

**`check_spread`**
- Compressor is on but supply and return are almost equal (|ΔT| &lt; 1 °C) — little heat is being delivered to the system.
- Often a **configuration / hydraulics** issue, not a broken compressor: wrong pump curves, mixer always open, parallel circuits stealing flow, buffer bypass, or flow rate set too high/low for the heat pump.
- Check circulation: pumps running, valves/mixers open to the circuit that is supposed to take heat, filters/strainers, air in the loop.
- For buffer/AKU setups, confirm the heat pump is actually charging the tank (primary / requesting circuit) and not only circulating on mixers.
- Brief spikes during mode changes are possible; a persistent low spread with modulation &gt; 0 needs installer attention (flow rate / controller config / hydraulics).

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
