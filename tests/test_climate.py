"""Climate entity behaviour against the simulated gateway."""
from datetime import timedelta

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

ENTITY = "climate.zone_circuit_zone_1_zone_1"


async def test_set_temperature_writes_and_refreshes(hass, setup_integration, simulator, monkeypatch):
    # The new value is read back in a background task (one attempt per
    # CONFIRM_INTERVAL) until the gateway confirms it, because EasyControl
    # still reports the old value right after the PUT. CONFIRM_TIMEOUT = 0
    # limits this to one attempt; moving the clock on lets it run.
    monkeypatch.setattr("custom_components.bosch.climate.CONFIRM_TIMEOUT", 0)
    simulator.requests.clear()
    await hass.services.async_call(
        CLIMATE_DOMAIN, "set_temperature", {"entity_id": ENTITY, "temperature": 19.5}, blocking=True
    )
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()
    assert any(value == 19.5 for _, value in simulator.puts)
    assert simulator.requests  # state is read back after the PUT


async def test_optimistic_mode_keeps_value_until_next_poll(hass, simulator, config_entry):
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options={"optimistic_mode": True})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    simulator.requests.clear()
    await hass.services.async_call(
        CLIMATE_DOMAIN, "set_temperature", {"entity_id": ENTITY, "temperature": 19.5}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["temperature"] == 19.5
    assert not simulator.requests  # no immediate refresh overwriting it
    await hass.config_entries.async_unload(config_entry.entry_id)
