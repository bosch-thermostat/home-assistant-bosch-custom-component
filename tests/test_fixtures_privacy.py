"""Every rawscan fixture is masked the way the client masks a fresh scan.

Older scans, such as those in bosch_thermostat_http_simulator, predate parts
of the client's masking and can still carry a real gateway uuid, sometimes
only in ``allowedValues``. This check keeps such a scan out of the repo.
"""
from __future__ import annotations

from typing import Any

import pytest
from bosch_thermostat_client.helper import CONFIDENTIAL_KEYS, CONFIDENTIAL_URI

from tests.simulator import iter_responses, load_rawscan, rawscan_names

MASKED = {"-1", ""}


def _unmasked_keys(value: Any) -> list[str]:
    """Confidential keys nested in ``value`` that still hold data."""
    found = []
    if isinstance(value, list):
        for item in value:
            found += _unmasked_keys(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in CONFIDENTIAL_KEYS:
                # the client writes "-1"; zeroing by hand keeps the length
                if str(item) not in MASKED and set(str(item)) != {"0"}:
                    found.append(key)
            else:
                found += _unmasked_keys(item)
    return found


@pytest.mark.parametrize("rawscan_name", rawscan_names())
def test_rawscan_is_masked(rawscan_name):
    _, rawscan = load_rawscan(rawscan_name)
    leaks = []
    for resp in iter_responses(rawscan):
        path = resp.get("id")
        if path in CONFIDENTIAL_URI:
            if "value" in resp and str(resp["value"]) not in MASKED:
                leaks.append(f"{path} value")
            allowed = resp.get("allowedValues") or []
            if not isinstance(allowed, list):  # some firmwares send a bare value
                allowed = [allowed]
            if any(str(v) not in MASKED for v in allowed):
                leaks.append(f"{path} allowedValues")
        leaks += [f"{path} {key}" for key in _unmasked_keys(resp.get("value"))]
    assert not leaks, f"unmasked in {rawscan_name}: {leaks}"
