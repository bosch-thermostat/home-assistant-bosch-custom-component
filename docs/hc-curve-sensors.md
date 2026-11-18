# Heating circuit curve sensors (HC)

**Not experimental.** These register whenever the gateway has heating circuits. They do **not** need **Virtual heat-pump diagnostics**. They are separate from the “Heat pump diagnostics” child device.

## Why they exist

They expose supply, pump, and heating-curve settings into Home Assistant history so an AI (or you) can tune the **heating cycle** and the **weather-compensated curve** from outdoor / room / flow data over time. Without these series in HA, curve tuning has little structured input beyond comfort complaints.

## Gateway support

Values only appear when the **heat pump / controller exports that path**. Many IVT setups behind a **KM200 do not export** curve parameters (`designTemp`, `heatCurveMax`, `roomInfluence`, `roomTempOffset`); those entities stay **Unknown**. Live supply / pump paths are more often present, but still depend on the appliance.

## Contents

- [Why they exist](#why-they-exist)
- [Gateway support](#gateway-support)
- [Where they live / how to show them](#where-they-live--how-to-show-them)
- [How it works](#how-it-works)
- [Supply setpoint](#supply-setpoint)
- [Supply actual](#supply-actual)
- [Pump modulation](#pump-modulation)
- [Design temperature](#design-temperature)
- [Heat curve max](#heat-curve-max)
- [Room influence](#room-influence)
- [Room temperature offset](#room-temperature-offset)

Quick links: [Supply setpoint](#supply-setpoint) · [Supply actual](#supply-actual) · [Pump modulation](#pump-modulation) · [Design temperature](#design-temperature) · [Heat curve max](#heat-curve-max) · [Room influence](#room-influence) · [Room temperature offset](#room-temperature-offset)

## Where they live / how to show them

Each sensor is attached to the **same device as that circuit’s climate entity** (e.g. Heating circuit hc2), not to Heat pump diagnostics.

1. **Settings → Devices & services → Bosch thermostat**
2. Open the heating circuit device (`hc1`, `hc2`, …)
3. Enable **Show disabled entities**
4. Enable the curve / supply sensors you want

Values update on the normal coordinator scan (~60s) once at least one of these sensors is enabled (that registers the HC objects for polling; climate already does the same when the climate entity is on).

## How it works

On each refresh the integration builds a circuit snapshot from paths under `heatingCircuits/{hcN}/…` when the gateway provides them. Live supply/pump fields are the same data used for heat-request detection; curve fields are controller settings when exported.

| Sensor | Path | Unit |
| --- | --- | --- |
| [Supply setpoint](#supply-setpoint) | `supplyTemperatureSetpoint` | °C |
| [Supply actual](#supply-actual) | `actualSupplyTemperature` | °C |
| [Pump modulation](#pump-modulation) | `pumpModulation` | % |
| [Design temperature](#design-temperature) | `designTemp` | °C |
| [Heat curve max](#heat-curve-max) | `heatCurveMax` | °C |
| [Room influence](#room-influence) | `roomInfluence` | % |
| [Room temperature offset](#room-temperature-offset) | `roomTempOffset` | °C |

## Supply setpoint

Flow temperature the weather-compensated curve currently asks for (`heatingCircuits/{hcN}/supplyTemperatureSetpoint`, °C). Compare to [supply actual](#supply-actual) and outdoor / room history to judge whether the curve is too high or too low.

## Supply actual

Measured circuit supply / flow temperature (`actualSupplyTemperature`, °C). Used with appliance supply to decide which circuit is requesting heat.

## Pump modulation

Circuit pump effort (`pumpModulation`, %). Low values with the compressor off are circulation; higher values mean that circuit’s pump is working harder.

## Design temperature

Heating-curve design outdoor temperature (`designTemp`, °C). Controller setting; often **not exported** via KM200.

## Heat curve max

Maximum supply temperature on the heating curve (`heatCurveMax`, °C). Controller setting; often **not exported** via KM200.

## Room influence

How strongly room temperature pulls the curve (`roomInfluence`, %). Controller setting; often **not exported** via KM200.

## Room temperature offset

Room setpoint offset applied to the circuit (`roomTempOffset`, °C). Controller setting; often **not exported** via KM200.
