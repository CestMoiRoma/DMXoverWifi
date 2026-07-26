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

The project is under the [PolyForm Noncommercial License 1.0.0](LICENSE), widened
by one [additional permission](ADDITIONAL-PERMISSION.md) that allows paid work
with the box: live events, installations, rentals and consulting. Distributing
hardware preloaded with the firmware, or sold as being for it, still needs
written permission. Ask in an issue.

Contributions are licensed under those same terms, and are covered by the
[contributor licence agreement](CLA.md). Read it once before your first pull
request. The short version:

- **You keep the copyright in everything you write.** Nothing is transferred.
- You grant the maintainer a licence broad enough to relicense the project later
  without having to track down every contributor, since one holdout would
  otherwise freeze the terms forever.
- **Opening a pull request records your acceptance**, for that contribution and
  every one after it. There is nothing to sign and nothing to email.
- Nothing can be merged before acceptance is recorded.

If your employer holds rights over what you write at work, sort that out before
you submit, not after.

## Safety

This firmware has no timing guarantee. A command crosses WiFi into a
single-threaded loop, so it can arrive late or not at all, which
[Timing and latency](docs/wiki/timing.md) sets out in detail. It comes with no
warranty, and neither the maintainer nor any contributor can be held liable for
damage to equipment, property or people arising from its use.

Keep it that way when you contribute. Do not add features that invite it near
pyrotechnics, hoists, moving trusses, lasers or anything else where a late cue
becomes a physical hazard, and do not soften the warnings that say so. If a
change affects timing, say so in the pull request and put the numbers from
`/api/info` next to it.
