"""Config and options flow against the simulated gateway."""
from unittest.mock import patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_ADDRESS, CONF_PASSWORD

from custom_components.bosch.const import CONF_DEVICE_TYPE, CONF_PROTOCOL, DOMAIN, UUID
from tests.conftest import SCAN_UUID


async def _start_xmpp_flow(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # EasyControl is XMPP only, so the protocol step is skipped
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_TYPE: "EASYCONTROL"}
    )
    assert result["step_id"] == "xmpp_config"
    return result


async def test_create_entry(hass, simulator):
    result = await _start_xmpp_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ADDRESS: "101000000",
            CONF_ACCESS_TOKEN: "abcd-efgh-ijkl-mnop",
            CONF_PASSWORD: "password",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][UUID] == SCAN_UUID
    assert result["data"][CONF_DEVICE_TYPE] == "EASYCONTROL"
    assert result["data"][CONF_PROTOCOL] == "XMPP"
    # the flow's test connection is closed again
    assert simulator.closed >= 1
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)


async def _submit_offline(hass, simulator):
    simulator.offline = True
    result = await _start_xmpp_flow(hass)
    # only the flow's own test connection is of interest here
    with patch("custom_components.bosch.async_setup_entry", return_value=True):
        return await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ADDRESS: "101000000", CONF_ACCESS_TOKEN: "abcd-efgh-ijkl-mnop", CONF_PASSWORD: "x"},
        )


async def test_unreachable_gateway_closes_test_connection(hass, simulator):
    await _submit_offline(hass, simulator)
    assert simulator.closed == 1


@pytest.mark.xfail(
    strict=True,
    reason="existing behaviour: an unreadable gateway still creates an "
    "'Unknown model' entry without uuid (see #554)",
)
async def test_unreachable_gateway_aborts(hass, simulator):
    result = await _submit_offline(hass, simulator)
    assert result["type"] == data_entry_flow.FlowResultType.ABORT


async def test_options_flow(hass, setup_integration):
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"new_stats_api": True, "optimistic_mode": True, "scan_interval": 120},
    )
    await hass.async_block_till_done()  # entry reloads with the new options
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert setup_integration.options == {
        "new_stats_api": True,
        "optimistic_mode": True,
        "scan_interval": 120,
    }
