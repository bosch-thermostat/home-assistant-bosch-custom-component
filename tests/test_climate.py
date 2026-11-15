"""Climate entity behaviour against the simulated gateway."""
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN

ENTITY = "climate.zone_circuit_zone_1_zone_1"


async def test_set_temperature_writes_and_refreshes(hass, setup_integration, simulator):
    simulator.requests.clear()
    await hass.services.async_call(
        CLIMATE_DOMAIN, "set_temperature", {"entity_id": ENTITY, "temperature": 19.5}, blocking=True
    )
    await hass.async_block_till_done()
    assert any(value == 19.5 for _, value in simulator.puts)
    assert simulator.requests  # state is read back right away


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
