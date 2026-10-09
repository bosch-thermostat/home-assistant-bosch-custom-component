# Testing

The suite runs Home Assistant (via `pytest-homeassistant-custom-component`)
against the **real** `bosch-thermostat-client` gateway classes. Only the
transport is replaced: `tests/simulator.py` answers every connector `get`/`put`
from a captured `rawscan()`, so database lookup, device detection and entity
building are exercised exactly as on a real gateway.

## Running

```bash
python3.14 -m venv .venv && . .venv/bin/activate
pip install -r tests/requirements.txt
pytest
pytest --snapshot-update   # after an intended change to entity states
```

## Adding a device from a rawscan

A rawscan posted in an issue can become a regression test:

1. Get the scan: `bosch.debug_scan` in Home Assistant, or
   `bosch_cli scan ... -o scan.json` (see the README).
2. Redact what the client does not mask already. The client masks `uuid`, user
   and location fields as `-1`; these have to be done by hand:

   | Field | Where | Why |
   |---|---|---|
   | serial numbers | `/heatSources/info` → `No` | identifies the appliance |
   | `sgtin` | `/devices/dev*` entries | per-device factory serial |
   | `dlk` | `/devices/dev*` entries | HomematicIP link key, a shared secret |
   | zone/room names | `/zones/zn*/name`, and **base64** in `/zones/list` and `/zones/deviceTypeAllowed` | names your home |

   Names appear twice: plain under `/zones/zn*/name` and base64-encoded in the
   list endpoints, so grep for both (`echo -n 'Name' | base64`).

   Older scans, including several in the `scans/` folder of
   [bosch_thermostat_http_simulator](https://github.com/bosch-thermostat/bosch_thermostat_http_simulator),
   predate parts of the client's masking. They can carry the real gateway
   uuid (in `value` *and* `allowedValues`), `remoteServicesPassword`,
   `identificationKey`, the serial number or coordinates. Mask those as `-1`
   too. `tests/test_fixtures_privacy.py` fails on any fixture where a path in
   the client's `CONFIDENTIAL_URI` or a key in `CONFIDENTIAL_KEYS` still holds
   data. It doesn't cover the boiler serial or the zone names from the table
   above; check those by hand.
3. Save it as `tests/fixtures/rawscans/<name>.json`. Don't reuse the CLI's
   default file name: `bosch_cli scan` names it `rawscan_<uuid>.json`.

   ```json
   {"device_type": "EASYCONTROL", "protocol": "XMPP", "source": "model, firmware", "rawscan": [...]}
   ```

4. Run `pytest --snapshot-update`; `test_entities[<name>]` records every
   entity the integration builds for that device.

A rawscan only holds the newest energy history page; the simulator answers
older pages as empty.
