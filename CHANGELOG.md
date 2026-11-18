# Changelog

Changes in this fork since [bosch-thermostat/home-assistant-bosch-custom-component](https://github.com/bosch-thermostat/home-assistant-bosch-custom-component) `master` (`7a27f76`).

## [Unreleased]

### Added

- Virtual heat-pump diagnostics (HTTP, experimental, disabled by default). See [docs/virtual-heatpump-sensors.md](docs/virtual-heatpump-sensors.md).
- HC curve/supply sensors on each heating-circuit device (disabled by default; only paths the heat pump exports). See [docs/hc-curve-sensors.md](docs/hc-curve-sensors.md).
- Pool climate when the gateway exposes pool paths.
- Derived `recording:renvironmentexternal` and HDH `recording:rheatingdegreehoursexternal`. See [docs/heating-degree-hours.md](docs/heating-degree-hours.md).
- `bosch.backfill_environment_energy`, `bosch.repair_energy_statistics`, `bosch.clear_energy_statistics`.
- Configure: show last-hour recording values; energy stats repair days.
- Fetch recordings by date range.

### Changed

- New statistic API keeps recording entity state at `-17`; graphs use `recording:…external`.

### Fixed

- Recording LTS **upsert**: supports late or corrected hourly values by rewriting changed rows and recomputing cumulative `sum` from the first change. This avoids permanently retaining an incorrect first sample.
- Energy `0` kWh hours stay omitted until Bosch revises them; temperature recordings **keep real 0 °C** hours (client used to drop them) via day re-fetch / `recording_temp_fill`.
- Recording entities set `last_reset` only when `state_class` is `total` (HA rejects it otherwise, e.g. temperature recordings); temperature recording fetches log and skip bad payloads instead of failing the hourly update.
- Virtual snapshot cache uses `TimestampDataUpdateCoordinator` so `last_update_success_time` advances each refresh; without that the cache key stayed frozen and diagnostic sensors stopped updating after setup.
