# Heating degree-hours (HDH)

Derived **IVT / KM200 recording** statistic. Not a live sensor entity and not part of virtual heat-pump diagnostics.

Statistic id: `recording:rheatingdegreehoursexternal`  
Recorder name: **Stats rHeatingDegreeHours**  
Unit: `°C·h`

## Contents

- [What HDH is](#what-hdh-is)
- [Formula](#formula)
- [Prerequisites](#prerequisites)
- [How to display](#how-to-display)
- [When it updates](#when-it-updates)
- [State vs sum](#state-vs-sum)
- [Backfill](#backfill)
- [Using HDH for efficiency](#using-hdh-for-efficiency)
- [Related series](#related-series)

## What HDH is

Heating degree-hours measure how cold each outdoor hour was relative to a fixed base temperature. One hour at 5 °C with base 15 °C contributes **10 °C·h**. Mild hours at or above the base contribute **0**.

Bosch does not publish an HDH recording. This integration **derives** it from the outdoor hourly recording already stored in Home Assistant long-term statistics.

## Formula

Base temperature is fixed at **15 °C**:

```text
HDH_hour = max(0, 15 − outdoor_hour)
```

| Outdoor (°C) | HDH that hour (°C·h) |
| --- | --- |
| 20 | 0 |
| 15 | 0 |
| 5 | 10 |
| 0 | 15 |
| −5 | 20 |

If the outdoor hour is missing, that hour is **skipped** (no HDH row written for that start).

Source outdoor statistic: `recording:routdoor_t1external` (from gateway path `system/sensors/temperatures/outdoor_t1` / recording export).

## Prerequisites

1. Integration **Configure** → turn on **Use new statistic API** so IVT recordings write into HA long-term statistics.
2. Outdoor recording must exist as `recording:routdoor_t1external` (enable the outdoor recording / let hourly pulls fill it).
3. After outdoor hours exist, HDH is computed automatically on the hourly recording schedule (and can be [backfilled](#backfill)).

Without outdoor hours, HDH stays empty.

## How to display

HDH is an **external statistic**, not a `sensor.*` entity. Use it on cards that accept statistic ids:

1. Add a **Statistics graph** card (or Energy dashboard–style statistic source where applicable).
2. Statistic: `recording:rheatingdegreehoursexternal`
3. Prefer **Sum** for cumulative cold exposure over a period; use **Change** / period delta when you want “degree-hours in this day/week”.

Do **not** chart HDH from a `sensor.*` entity. Graphs use `recording:…external`.

With **Use new statistic API**, recording entities stay at **`-17`** unless **Show last-hour recording values** is on. That option only puts the last settled hour on the entity (for cards / automations). It does not fill the HDH statistic. See [Recording entity values](../README.md#recording-entity-values) in the README.

Example statistics-graph snippet:

```yaml
type: statistics-graph
entities:
  - recording:rheatingdegreehoursexternal
  - recording:rcompressorexternal
stat_types:
  - change
days_to_show: 7
```

(Exact compressor statistic id may differ on your install; pick the compressor / produced recording ids from Developer tools → Statistics.)

## When it updates

After each hourly recording pull (~`:06`), the coordinator:

1. Updates enabled recording entities from the gateway
2. Refreshes the derived environment series
3. Calls `async_update_hdh_tail` — recomputes roughly the last **48 hours** of HDH from outdoor stats and writes them with `async_add_external_statistics`

So new HDH hours appear shortly after outdoor recording hours are written, not on the 60s live scan.

## State vs sum

Each HDH statistic row has:

| Field | Meaning |
| --- | --- |
| `state` | Degree-hours for **that one hour** (`max(0, 15 − outdoor)`) |
| `sum` | Running cumulative total across written hours |

When rewriting a range, the code takes the `sum` of the hour **before** the range as an anchor, then rebuilds `state` + `sum` forward so the cumulative series stays consistent.

## Backfill

If outdoor history already exists but HDH is missing or wrong for past days, run:

```yaml
service: bosch.backfill_environment_energy
target:
  device_id: <your bosch gateway device id>
data:
  start_date: "2024-06-01"
  end_date: "2026-11-13"
```

That service backfills **both**:

- `recording:renvironmentexternal` (environment heat)
- `recording:rheatingdegreehoursexternal` (HDH)

Large date ranges are processed in chunks (hundreds of days) so recorder queries stay bounded. Statistic ids are shared for the gateway recording series; one run covers them.

## Using HDH for efficiency

Chart **compressor kWh** or **produced heat kWh** against HDH over the same period. The slope is roughly **kWh per degree-hour** — a weather-normalized efficiency view (colder weeks need more heat for the same building).

- High kWh / HDH → more energy for the cold exposure (curve too high, backup, short cycles, …)
- Lower kWh / HDH in similar conditions → better weather-normalized performance

This is a derived metric for analysis, not a Bosch certified COP.

### Examples

**One cold hour**

Outdoor = 0 °C → HDH = `max(0, 15 − 0)` = **15 °C·h** for that hour.  
If the compressor used **3 kWh** in the same hour → **0.2 kWh per °C·h** for that hour alone.

**Mild day vs cold day (same house)**

| Day | Rough outdoor | Sum of HDH (24 h) | Compressor kWh | kWh / HDH |
| --- | --- | --- | --- | --- |
| Mild | ~10 °C all day | ~120 °C·h | 12 kWh | 0.10 |
| Cold | ~0 °C all day | ~360 °C·h | 36 kWh | 0.10 |

Same **0.10 kWh/HDH** means weather-normalized demand looks unchanged: the cold day simply had more degree-hours. Raw kWh alone would look “3× worse” without HDH.

**Curve / backup showing up**

Same cold week (~360 °C·h/day), but after raising the heating curve (or heavy backup):

| Week | HDH (day) | Compressor kWh | kWh / HDH |
| --- | --- | --- | --- |
| Before | 360 | 36 | 0.10 |
| After (hotter curve) | 360 | 48 | 0.13 |

HDH was similar; electricity rose → higher kWh/HDH. That is the signal to investigate curve, flow temps, or backup — not “it was colder.”

**How to read a statistics graph**

1. Plot `recording:rheatingdegreehoursexternal` and compressor (or produced) with **period change** (day or week).
2. Mentally (or in a spreadsheet) divide energy change by HDH change for that period.
3. Compare periods with similar outdoor patterns; a rising kWh/HDH trend is more useful than comparing absolute kWh across a warm week and a freeze.

## Related series

| Statistic id | Role |
| --- | --- |
| `recording:routdoor_t1external` | Input outdoor °C per hour |
| `recording:rheatingdegreehoursexternal` | Derived HDH (°C·h) |
| `recording:renvironmentexternal` | Derived `max(0, produced − compressor)` per hour |

Also see [virtual heat-pump sensors](virtual-heatpump-sensors.md) for live COP / mode diagnostics (separate feature).
