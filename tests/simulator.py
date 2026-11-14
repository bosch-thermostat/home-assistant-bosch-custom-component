"""Replay a captured ``rawscan()`` through the real bosch-thermostat-client.

The real gateway class runs unchanged (database lookup, device detection,
circuit/sensor building); only the connector's transport is replaced so
``get``/``put`` answer from the scan. Any rawscan from an issue can become a
regression test by dropping it into ``tests/fixtures/rawscans/``.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

from bosch_thermostat_client.connectors.http import HttpConnector
from bosch_thermostat_client.connectors.xmpp import XMPPBaseConnector
from bosch_thermostat_client.exceptions import DeviceConnectionError, DeviceException

RAWSCANS = Path(__file__).parent / "fixtures" / "rawscans"


def iter_responses(rawscan: list[Any]) -> Iterator[dict[str, Any]]:
    """Yield every response dict of a rawscan (list of per-root lists)."""
    for root in rawscan:
        # a root the gateway doesn't have is recorded as {"/root": "not found"}
        if isinstance(root, list):
            yield from (resp for resp in root if isinstance(resp, dict))


def index_rawscan(rawscan: list[Any]) -> dict[str, dict[str, Any]]:
    """Map request path -> response, as the gateway would answer."""
    responses: dict[str, dict[str, Any]] = {}
    for resp in iter_responses(rawscan):
        path = resp.get("id")
        if not path:
            continue
        # rawscan stores energy pages as ?entry=<float>; the client asks ?entry=<int>
        if "?entry=" in path and path.endswith(".0"):
            path = path[:-2]
        # recording intervals are fetched as <id>?interval=<value>
        if "interval" in resp and "?" not in path:
            responses[f"{path}?interval={resp['interval']}"] = resp
            responses.setdefault(path, resp)
        else:
            responses[path] = resp
    return responses


@dataclass
class GatewaySimulator:
    """Answers connector requests from a rawscan and records them."""

    responses: dict[str, dict[str, Any]]
    requests: list[str] = field(default_factory=list)
    puts: list[tuple[str, Any]] = field(default_factory=list)
    closed: int = 0
    offline: bool = False
    unreachable: bool = False
    # paths that time out while the rest of the gateway answers
    timeout_paths: set[str] = field(default_factory=set)

    async def get(self, path: str) -> dict[str, Any]:
        self.requests.append(path)
        if self.unreachable or path in self.timeout_paths:
            # what the connectors raise when a request gets no answer (on
            # XMPP: timed out twice), as opposed to one endpoint being absent
            raise DeviceConnectionError(f"Connection timed out for {path}.")
        if self.offline:
            raise DeviceException(f"Gateway unreachable ({path})")
        if path in self.responses:
            return copy.deepcopy(self.responses[path])
        base, _, query = path.partition("?")
        if query.startswith("entry=") and any(
            key.startswith(f"{base}?entry=") for key in self.responses
        ):
            # rawscan keeps only the newest energy history page; older pages
            # the client walks through are answered as empty
            return {"id": path, "type": "energyRecordings", "value": []}
        raise DeviceException(f"URI {path} does not exist")

    async def put(self, path: str, value: Any) -> bool:
        self.puts.append((path, value))
        if path in self.responses:
            self.responses[path]["value"] = value
        return True

    async def close(self, force: bool = False) -> None:
        self.closed += 1


@contextmanager
def simulate(rawscan: list[Any]) -> Iterator[GatewaySimulator]:
    """Route every HTTP and XMPP connector through a simulator."""
    sim = GatewaySimulator(index_rawscan(rawscan))

    async def get(_self, path):
        return await sim.get(path)

    async def put(_self, path, value):
        return await sim.put(path, value)

    async def close(_self, force=False):
        await sim.close(force)

    with ExitStack() as stack:
        for connector in (HttpConnector, XMPPBaseConnector):
            stack.enter_context(patch.object(connector, "get", get))
            stack.enter_context(patch.object(connector, "put", put))
            stack.enter_context(patch.object(connector, "close", close))
        yield sim


def load_rawscan(name: str) -> tuple[dict[str, Any], list[Any]]:
    """Return (metadata, rawscan) for ``tests/fixtures/rawscans/<name>.json``.

    The file holds ``{"device_type": ..., "protocol": ..., "rawscan": [...]}``.
    """
    data = json.loads((RAWSCANS / f"{name}.json").read_text())
    meta = {key: value for key, value in data.items() if key != "rawscan"}
    return meta, data["rawscan"]


def rawscan_names() -> list[str]:
    return sorted(path.stem for path in RAWSCANS.glob("*.json"))
