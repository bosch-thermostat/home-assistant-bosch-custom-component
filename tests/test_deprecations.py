"""The integration's modules use no API Home Assistant reports as deprecated."""
import importlib.util
import logging
import sys
from pathlib import Path

import pytest
from homeassistant import config_entries
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.water_heater import WaterHeaterEntity

import custom_components.bosch
from custom_components.bosch.climate import BoschThermostat
from custom_components.bosch.const import DOMAIN
from custom_components.bosch.water_heater import BoschWaterHeater

NATIVE_API = hasattr(ClimateEntity, "native_temperature_unit") and hasattr(
    WaterHeaterEntity, "native_temperature_unit"
)
NEEDS_NATIVE_API = pytest.mark.skipif(
    not NATIVE_API, reason="Home Assistant before the native temperature API"
)


@pytest.mark.parametrize(
    "module_name",
    [
        pytest.param("climate", marks=NEEDS_NATIVE_API),
        pytest.param("water_heater", marks=NEEDS_NATIVE_API),
        "config_flow",
    ],
)
def test_no_deprecation_reported_on_import(
    module_name: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Executing the module logs no deprecation report.

    Home Assistant reports a deprecated entity member once, when the class is
    defined, and patches the class on that report; a deprecated constant is
    reported when it is read. The module is executed again under a scratch name
    so both checks run on fresh code.
    """
    name = f"custom_components.bosch._probe_{module_name}"
    path = Path(custom_components.bosch.__file__).parent / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    handler = config_entries.HANDLERS.get(DOMAIN)
    sys.modules[name] = module
    try:
        with caplog.at_level(logging.WARNING):
            spec.loader.exec_module(module)
    finally:
        del sys.modules[name]
        # config_flow registers its handler on import; keep the real one
        if handler is None:
            config_entries.HANDLERS.pop(DOMAIN, None)
        else:
            config_entries.HANDLERS[DOMAIN] = handler
    assert [r.getMessage() for r in caplog.records if "deprecated" in r.getMessage()] == []


@pytest.mark.parametrize("entity_class", [BoschThermostat, BoschWaterHeater])
def test_platform_classes_define_native_temperature_members(entity_class: type) -> None:
    """The platform classes define the native_* members themselves.

    Home Assistant decides by the most derived class providing either name, so
    an old name defined here would be reported. Runs on every Home Assistant
    version, unlike the import check.
    """
    names = ("temperature_unit", "current_temperature", "target_temperature")
    assert {f"native_{n}" for n in names} <= vars(entity_class).keys()
    assert not set(names) & vars(entity_class).keys()
