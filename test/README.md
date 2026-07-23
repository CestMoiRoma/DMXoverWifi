# Test suite

Checks that the firmware works **before** it goes on the board. Everything here
runs on a normal PC: `fake_esp32/` stands in for the ESP32, and `ui/mock_server.py`
stands in for a running board, so nothing needs hardware and nothing touches a
live rig.

This suite grows with the firmware. Every feature that lands should arrive with
the tests that prove it, and every bug that gets fixed should leave a test behind
so it cannot come back.

## Running it

```bash
docker compose -f test/docker-compose.yml run --rm tests
```

Or locally, with Python 3.11 or newer:

```bash
pip install -r test/requirements.txt
playwright install chromium        # only needed for the browser tests
python -m pytest test -v
```

Without playwright the browser tests skip and the rest still runs.

## Layout

| Path | What it covers |
|------|----------------|
| `fake_esp32/` | Stand-ins for `board`, `busio`, `digitalio`, `microcontroller`, `storage`, `usb_cdc`, `wifi`, `socketpool`, `adafruit_httpserver`, `adafruit_minimqtt` |
| `conftest.py` | Path setup, per-test board reset, ready-wired firmware objects |
| `test_settings_store.py` | JSON config under `/data`, defaults, recovery from a corrupt file |
| `test_dmx_driver.py` | 512-channel buffer, clamping, break and MAB generation, refresh rate, DE/RE pin |
| `test_devices.py` | Fixtures, all four channel types, DMX address mapping, persistence |
| `test_wifi_manager.py` | Saved networks, priority ordering, access point fallback |
| `test_mqtt_manager.py` | Connection lifecycle, Home Assistant discovery, command handling |
| `test_serial_console.py` | Every serial command, its arguments and its error paths |
| `test_web_api.py` | Every HTTP route the web UI calls |
| `test_boot.py` | Which side owns the filesystem after boot |
| `test_integration.py` | The whole stack wired the way `code.py` wires it |
| `test_deploy_tool.py` | `.env` parsing and seeding in `tools/deploy.py` |
| `test_ui.py` | The real web UI in a real browser, against the mock board |
| `ui/mock_server.py` | Serves `www/` with a fake API and demo fixtures |
| `ui/screenshot_ui.py` | Rewrites `docs/images/ui-*.png` |

## Screenshots

```bash
docker compose -f test/docker-compose.yml run --rm screenshots
```

Shots come from the mock board, so they always show a populated UI and never
leak a real wifi list.

## Adding to it

New firmware feature: add its tests next to the module they cover, and if it
touches the web UI add a browser test too.

New CircuitPython import in `src/`: add a stub in `fake_esp32/`. Keep it as thin
as the firmware needs, but no thinner, since a stub that accepts calls the real
hardware would reject makes the suite lie.

See [../WIKI.md](../WIKI.md#test-suite) for the longer version.
