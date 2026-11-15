# Virtual heat-pump sensors (IVT / HTTP)

**Experimental.** Derived from gateway paths, not certified Bosch diagnostics. Mode, requestors, and the efficiency hint can be wrong. Enable only if you accept that.

## Enable

1. Integration **Configure** → turn on **Virtual heat-pump diagnostics**.
2. Protocol must be **HTTP** (local KM200 / similar). Cloud XMPP is not supported. Saving Configure reloads the integration.
3. Open the child device:

   **Settings → Devices & services → Bosch thermostat → Heat pump diagnostics**

4. All entities are **disabled** by default. Enable **Show disabled entities**, then turn on the ones you want.

Live sensors fill on the next coordinator refresh. **COP**, **backup share**, and **last-hour** kWh wait for the hourly recording pull (up to about an hour, or the next `:06`).

## Contents

- [Operation](#operation)
- [Who is asking for heat](#who-is-asking-for-heat)
- [Efficiency](#efficiency)
- [Last hour](#last-hour)
- [Compressor time split](#compressor-time-split)
- [Faults](#faults)

## Operation

### Heat pump mode

Enum sensor. First matching rule wins (highest priority first):

| State | Meaning |
| --- | --- |
| `pool_and_heating` | Compressor on, pool heating, and DHW charging or a circuit requesting |
| `pool` | Compressor on and pool heating |
| `dhw_and_heating` | Compressor on, DHW charging, and a circuit requesting |
| `dhw` | Compressor on and DHW charging (`charge=start`) |
| `space_heating` | Compressor on and at least one circuit requesting |
| `compressor` | Compressor on, no pool / DHW charge / circuit match |
| `circulation` | Compressor off, at least one circuit pump ≥ 5% |
| `idle` | Otherwise |

### Compressor active

Binary. On when heat-source or hs1 modulation is above 0.

### Heat source delta

Supply minus return (°C). Uses appliance supply when heat-source supply is missing.

## Who is asking for heat

Requestors can overlap. Pump running alone is **circulation**, not a heat request.

### Heat requestors

Text sensor: comma-separated list, for example `dhw,hc2,pool`.

| Token | Rule |
| --- | --- |
| `dhw` | DHW setpoint is not 0 |
| `hcN` | Compressor on, circuit status `ACTIVE`, setpoint &gt; 0, and appliance supply within 1 °C of that circuit’s **actual** supply (setpoint used only if actual is missing) |
| `pool` | Pool status is not `off` |

Usually one heating circuit matches; more than one is possible.

### Primary heating circuit

Among circuits that are requesting:

- If `hc1` (often a buffer) and another circuit both match, prefer the non-`hc1` set.
- Then pick the highest pump modulation.

If none are requesting, the circuit with the highest pump modulation (or unknown if none have modulation).

### Space heating active

Binary. On when at least one circuit is in the requesting set.

### Heating circuits requesting

Count of matching circuits (`circuits` unit).

### hcN requesting heat

One binary sensor per heating circuit. On when that circuit id is in the requesting set.

### DHW requested

Binary. On when the hot-water setpoint is not 0.

### DHW charging

Binary. On only when `dhwCircuits/dhw1/charge` is `start`.

### DHW temperature gap

Setpoint minus tank temperature (°C).

### Pool requested

Binary. On when pool status is present and not `off`.

### Pool temperature gap

Pool setpoint minus pool temperature (°C).

## Efficiency

### COP today

Produced heat / compressor electricity for the **local calendar day**, excluding the current incomplete hour. Gateway hourly values typically arrive with about a **1 hour** delay, so early morning can stay empty until ~01:06.

Attributes:

- `produced_kwh`
- `compressor_kwh`

### COP last 24h

Same ratio over the previous **24 settled hours** (rolling window, current incomplete hour excluded). Attributes: `produced_kwh`, `compressor_kwh`.

After a fresh install the window may be short until enough hourly rows have been retained across midnight.

### COP month / year

Produced heat / **consumed** electricity from Bosch period totals (no compressor month/year series). Attributes: `produced_kwh`, `consumed_kwh`.

### Backup heater share today / month / year

E-heater / consumed electricity, shown as **percent**.

### Backup heater used today

Binary. On when e-heater energy today is above 0.

### Heat pump efficiency hint

Coarse daily check, **not a fault code**. First matching state wins.

Attributes (always present when the entity has data):

| Attribute | Meaning |
| --- | --- |
| `cop_today` | Same ratio as COP today |
| `backup_share` | E-heater / consumed as a fraction 0–1 |
| `outdoor` | Outdoor temperature (°C), if available |
| `cop_min` | Outdoor-based COP floor used for `check_cop` |
| `spread` | Heat source delta (°C) |

States:

| State | Rule |
| --- | --- |
| `unknown` | Consumed today under 1 kWh, or produced missing |
| `check_backup` | `backup_share` ≥ 0.20 |
| `check_cop` | COP today below `cop_min` |
| `check_spread` | Compressor on and \|spread\| &lt; 1 °C |
| `ok` | None of the above |

Outdoor → `cop_min`:

| Outdoor | Floor |
| --- | --- |
| ≥ 5 °C | 2.8 |
| ≥ 0 °C | 2.3 |
| ≥ −7 °C | 1.8 |
| colder | 1.5 |
| unknown | 2.3 |

#### If the hint is not `ok`

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
- Confirm `produced_kwh` / `compressor_kwh` on the COP today sensor against the app (Heat pump + Environment = Sum); wrong series would fake a bad COP.
- Typical causes: high flow temperature, frequent short cycles, heavy DHW, icing/defrost, or backup already in the mix (often with `check_backup`).
- Overlapping demand can hurt COP: DHW charge + several HCs / pool at once forces higher power and less efficient operating points. Prefer fewer concurrent requestors when possible.
- Lower supply setpoints / heating curve if comfort allows; avoid repeated manual boosts.

**`check_spread`**

- Compressor is on but supply and return are almost equal (|ΔT| &lt; 1 °C) — little heat is being delivered to the system.
- Often a **configuration / hydraulics** issue, not a broken compressor: wrong pump curves, mixer always open, parallel circuits stealing flow, buffer bypass, or flow rate set too high/low for the heat pump.
- Check circulation: pumps running, valves/mixers open to the circuit that is supposed to take heat, filters/strainers, air in the loop.
- For buffer/AKU setups, confirm the heat pump is actually charging the tank (primary / requesting circuit) and not only circulating on mixers.
- Brief spikes during mode changes are possible; a persistent low spread with modulation &gt; 0 needs installer attention (flow rate / controller config / hydraulics).

## Last hour

Latest completed hourly kWh from recording series (not provisional current hour):

| Sensor | Source |
| --- | --- |
| Last hour electricity | `consumedEnergy` |
| Last hour heat | `outputProduced` |
| Last hour backup heater | `eheater` |

## Compressor time split

Not a Bosch per-circuit kWh meter. While the compressor is on, elapsed time between coordinator ticks is split **equally** across active sinks, then stored for the local calendar day (resets at midnight).

Sinks:

- Requesting heating circuits (`hc1` skipped when another circuit also requests — buffer follows)
- `dhw` while DHW is charging
- `pool` while pool heating is active (only created when the gateway exposes pool)

Per sink:

| Sensor | Meaning |
| --- | --- |
| `{sink} compressor minutes today` | Attributed minutes |
| `{sink} compressor share today` | Percent of today’s attributed compressor-on time |

Attribute on both: `compressor_seconds` (raw seconds for that sink).

## Faults

### hcN room sensor fault

One binary sensor per heating circuit. On when room temperature is at or below **−50 °C** (gateway sentinel / impossible reading).
