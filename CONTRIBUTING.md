# Contributing

Contributions are welcome. The workflow is the usual GitHub one.

1. Fork the repository.
2. Create a branch for your change.
3. Make sure it builds for both board families (see below).
4. Open a pull request against `main`, describing what changed and why.

Issues and bug reports are just as useful as code, especially if you are running
this on a board other than the Lolin S2 Mini or the Wemos D1 mini.

## Building

The firmware builds with [PlatformIO](https://platformio.org/). Before opening a
pull request, confirm it still compiles for the ESP32 and the ESP8266, since one
codebase serves both:

```bash
pio run -e s2mini
pio run -e d1mini
```

Flash and try it on real hardware where you can. There is no automated test suite
in this rewrite yet; the CircuitPython line had one, and restoring a
host-compilable equivalent is on the [roadmap](TODO.md).
Until then, changes are validated by building both targets and testing on the
board.

## Style

Match the code around you.

- Keep board-specific code behind the existing abstractions. The DMX transmit
  path lives in `src/dmx/`, split into a common driver and one backend per board;
  WiFi, the web server and MQTT wrap the per-core Arduino APIs. Anything that
  differs between the ESP32 and the ESP8266 belongs behind one of these seams, not
  scattered through `#if defined(ESP8266)` across the codebase.
- Use `ArduinoJson` for config and API payloads, and keep the on-disk JSON shapes
  stable, since the web UI, the MQTT bridge and the `.env` export all depend on
  them.
- Prefer static buffers over churning `String` in hot paths, to avoid heap
  fragmentation over long runs.
- The web UI in `web/` is plain HTML, CSS and JS with no framework and no
  transpiling. `tools/pack_web.py` splices the three files into one page at
  build time, which is packing rather than building: what you write is what
  ships. Keep it that way, and keep `fsdata/` out of your edits, since it is
  generated in full.

## Licensing

The project is under the [PolyForm Noncommercial License 1.0.0](LICENSE).

By opening a pull request you agree that your contribution is licensed under the
same terms. If you want to use this commercially, open an issue and ask.
