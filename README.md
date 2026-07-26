# DMX over WiFi (Mark II)

[![license: PolyForm Noncommercial](https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue)](LICENSE)

A standalone DMX512 transmitter you configure and drive from a web browser. It
runs on an ESP32 or ESP8266 board, serves its own web UI, remembers several WiFi
networks, falls back to its own hotspot when none are in range, and can expose
every DMX channel to Home Assistant over MQTT.

> [!NOTE]
> **This is the C++ / PlatformIO rewrite of the Mark II.** The Mark II firmware
> was previously written in CircuitPython; it has been ported to C++ on the
> Arduino framework so it runs natively, uses far less RAM, keeps steadier DMX
> timing, and now builds for the **ESP8266** as well as the ESP32. The original
> [ESPDMX](https://github.com/CestMoiRoma/ESPDMX) was an Arduino/ESP8266
> WebSocket controller; this project is its successor.

This page covers what the box is and how to get one running. Everything else has
its own page: **[WIKI.md](WIKI.md)** is the index.

## What it does

| | |
|---|---|
| **DMX output** | A full 512-channel universe, refreshed roughly 40 times a second, generated over UART with a proper break and mark-after-break |
| **Two board families** | One codebase builds for the ESP32-S2 (primary) and the ESP8266, with the transmit path behind a small hardware abstraction layer |
| **Web UI** | Four pages served off the board: Devices, Scenes, Groups and Settings |
| **Fixtures, two ways** | A [lite fixture](docs/wiki/lite-devices.md) is one control per channel. An [EZ fixture](docs/wiki/ez-devices.md) adds a control that understands what its channels mean: a colour wheel instead of three faders, a joystick instead of Pan and Tilt |
| **Scenes and groups** | [Scenes](docs/wiki/scenes.md) store a look and put it back, including one captured from the live rig. [Groups](docs/wiki/groups.md) drive a chosen set of channels from one control |
| **Emergency stop** | One press, every channel to nought. No latch, no restore |
| **Save-guard** | The look survives a power cut, written only after the rig has been still for ten seconds |
| **Multi-network WiFi** | Several networks with priorities, DHCP or a fixed address per network, and a config hotspot when none answer |
| **MQTT and Home Assistant** | Optional. Auto-discovery, so every channel and scene turns up as an entity |
| **Serial console** | A full command set over USB, plus a binary protocol for channel values. Enough to run the box with the radio switched off |
| **Over-the-air updates** | One press. The board downloads the release itself and refuses any image whose sha256 does not match what GitHub published. Settings and fixtures are untouched |
| **Headless option** | A build flag drops the served UI and keeps the REST API, MQTT, WiFi and DMX |
| **Parent and child mesh** | Present in the UI and the settings store. **Work in progress: stored only, no radio behaviour yet** |

## Hardware

- **An ESP32 or ESP8266 board.** Developed and tested on a **Wemos / Lolin S2
  Mini** (ESP32-S2, 4 MB flash). Also builds for the **Wemos D1 mini** (ESP8266),
  which is **beta**: it compiles, and nothing since the rewrite has run on it.
- **A MAX485 or similar RS-485 breakout**, the common blue module with
  `RO DI DE RE` down one side and `VCC A B GND` down the other.
- **A 3-pin or 5-pin female XLR** for the DMX output.
- A USB cable, and 5 V for the MAX485.

Output only for now. `RO` stays unconnected, so there is no DMX input and no RDM.
Changing that is [batch 10](TODO.md).

**[Wiring](docs/wiki/wiring.md)** has the schematic, the connection tables, the
DE/RE pin, powering and termination. **[HARDWARE.md](HARDWARE.md)** is the chip
comparison: what the ESP32 family and the ESP8266 can each do here, today and
later.

> [!NOTE]
> **ESP32 vs ESP8266.** On the ESP32 the DMX data pin is a configurable GPIO
> (`IO4` by default). On the ESP8266 the output is fixed to `Serial1`
> (UART1 TX = **GPIO2**), so the tx-pin setting is only a label there. The
> ESP8266 is single-core and shares its CPU with the WiFi stack, which can add
> jitter to the DMX frame under network load; the ESP32 is the safer target for
> timing-sensitive rigs.

## Getting started

### 1. Install PlatformIO

The firmware builds with [PlatformIO](https://platformio.org/). Install the CLI
(`pip install platformio`) or the VS Code extension. It downloads the toolchains
and the libraries on the first build; nothing else needs installing by hand.

### 2. Get the code

```bash
git clone https://github.com/CestMoiRoma/DMXoverWifi.git
cd DMXoverWifi
```

### 3. Flash

One upload. The web UI lives **inside the firmware**, so there is nothing else to
write:

```bash
pio run -e s2mini -t upload
```

`tools/pack_web.py` splices `web/style.css` and `web/app.js` into
`web/index.html`, gzips the result and emits it as C arrays in
`src/web_assets.cpp` before anything is compiled. 172 KB of source becomes a
45 KB page delivered in one request, which matters because the board answers one
HTTP client at a time and writes each response synchronously. Edit the three
files in `web/` normally; the packing happens at build time.

There is a second target, `uploadfs`, and it is **not** part of a normal flash.
It builds a LittleFS image from `.env` and writes it whole, which **erases
everything the board had stored**. Use it only to seed a fresh board, and export
the config first if the board holds anything you want. See
[Configuration](docs/wiki/configuration.md) for the `.env` keys and
[Updates](docs/wiki/updates.md) for how to update a board that is already in
service.

### 4. Get it on the network

With no saved network the board starts its own hotspot:

| | |
|---|---|
| SSID | `ESP-DMX` |
| Password | `DMX4ALL1` |
| Address | <http://1.1.1.1> |

Join it, open the page, go to **Settings**, **Network**, press **Scan**, add your
network and reboot. The serial console does the same in one line:

```
Add-Wifi ssid="My Network" passwd="hunter2" priority=10
```

Or put the network in `.env` before flashing and skip the hotspot entirely.

### 5. Add a fixture

Press the round **+** button. Pick **Lite** for one control per channel, or **EZ**
for a widget that knows what the channels mean. Give it a name and a DMX start
address, and its controls appear on **Devices**.

![Devices page](docs/images/ui-home.png)

## Build environments

`platformio.ini` defines four:

| Environment | Board | Web UI | Use |
|---|---|---|---|
| `s2mini` | ESP32-S2 | yes | Primary target |
| `s2mini_headless` | ESP32-S2 | no | REST API + MQTT + DMX only |
| `d1mini` | ESP8266 | yes | Range extension, beta |
| `d1mini_headless` | ESP8266 | no | Tightest RAM and flash footprint, beta |

The `_headless` builds set `-D WITH_WEBUI=0`. They stop serving the page and keep
the REST API, MQTT, WiFi and DMX, so the box stays controllable. That trade is
most useful on the ESP8266, where RAM is tight. It is chosen at the flash, not at
runtime.

The default environment is `s2mini`. Flash another with
`pio run -e <name> -t upload`.

## Driving it without a network

`Set-System wifi-toggle off`, or `WIFI_ENABLED=false` in `.env`, stops the board
bringing the radio up at all: no web server, no mDNS, no MQTT. A rig driven from a
laptop at front of house has no reason to broadcast, and this is how you say so.

The control surface then comes from the desktop app:

```bash
python tools/dmx_desktop.py            # finds the board's port itself
```

It needs `pyserial` and Tkinter, which ships with CPython on Windows and macOS and
is usually a separate `python3-tk` package on Linux. PlatformIO's own bundled
Python has no Tkinter, so run it with your system Python.

Two protocols share the one link because they want opposite things. Configuration
is read once as a line of JSON, where readability matters and speed does not.
Channel values go out as
[binary frames](docs/wiki/serial-console.md#binary-protocol), which measured about
eleven times the update rate of the equivalent text command. Both are documented
in [Serial console](docs/wiki/serial-console.md).

## Latency, and what not to use this for

> [!WARNING]
> **Latency is not guaranteed.** The delay between moving a fader and the fixture
> reacting varies, and it can spike well past what feels acceptable for live work.
> Do not use this box where a late or dropped cue matters: pyro, moving trusses,
> anything safety related, or a show that has to hit an exact musical beat.

What is dependable is the other half: once a value reaches the DMX buffer it keeps
going out at roughly 40 frames a second, so fixtures hold their state and do not
flicker. It is the *arrival* of a new value that has no deadline.

[Timing and latency](docs/wiki/timing.md) explains where the jitter comes from,
how to measure it with `loop_per_sec` and `loop_max_us`, and every blocking call
that has been found and fixed in this loop so far.

## Repository layout

```
platformio.ini          Four build environments, and the three pre-build scripts
dev.env                 Committed. The version and every factory default
.env.example            Every key the config seeding understands

src/
  main.cpp              Wiring-up and the main loop
  config.h              Build flags, and a fallback for every dev.env default
  version.h             Firmware version fallback
  dmx/                  512-channel buffer and the per-board transmit backends
  devices.{h,cpp}       Fixture and channel model, lite and EZ, persistence
  scenes, groups, labels, categories, ids
  save_guard.{h,cpp}    The look that survives a power cut
  web_server.{h,cpp}    HTTP routes: the page plus the JSON API
  ws_server.{h,cpp}     The live-control WebSocket, on port 81
  web_assets.{h,cpp}    Generated: the gzipped page, compiled into the firmware
  wifi_manager, ethernet_manager, mqtt_manager, serial_console
  modules.{h,cpp}       The subsystem switches and the API key
  updater.{h,cpp}       Over-the-air updates into the spare app partition
  settings_store.{h,cpp} JSON config files on LittleFS, with defaults

web/                    The UI as you edit it: index.html, style.css, app.js
  i18n/                 Four languages, inlined into the page at build time

tools/
  dev_env.py            dev.env into -D defines
  pack_web.py           web/ into one gzipped page, as C arrays
  env_to_fsdata.py      .env into fsdata/data/*.json
  dmx_desktop.py        Tkinter control surface over USB

docs/wiki/              The reference, one page per subject
docs/images/            Wiring schematic and UI screenshots
fsdata/                 Build output, gitignored. Nothing but the seeded config
```

Runtime config lives in `/data/*.json` on the board's LittleFS and holds nothing
else, which is what makes an update safe: the page travels in the firmware, so
writing new firmware cannot disturb the settings. A plain `upload` leaves that
partition alone; `uploadfs` replaces it.

## Documentation

**[WIKI.md](WIKI.md)** is the index. One page per subject:

| Building a rig | Driving it | Looking after it |
|---|---|---|
| [Wiring](docs/wiki/wiring.md) | [Serial console](docs/wiki/serial-console.md) | [Configuration](docs/wiki/configuration.md) |
| [Lite fixtures](docs/wiki/lite-devices.md) | [HTTP API](docs/wiki/http-api.md) | [Updates](docs/wiki/updates.md) |
| [EZ fixtures](docs/wiki/ez-devices.md) | [WebSocket](docs/wiki/websocket.md) | [Timing and latency](docs/wiki/timing.md) |
| [Scenes](docs/wiki/scenes.md) and [Groups](docs/wiki/groups.md) | [MQTT](docs/wiki/mqtt.md) | [Troubleshooting](docs/wiki/troubleshooting.md) |

**[HARDWARE.md](HARDWARE.md)** compares the chips. **[TODO.md](TODO.md)** is the
roadmap and the work in progress. **[CONTRIBUTING.md](CONTRIBUTING.md)** covers
the pull request workflow.

## License

[PolyForm Noncommercial 1.0.0](LICENSE), with one
[additional permission](ADDITIONAL-PERMISSION.md). In plain terms:

- **Noncommercial use is free**, including by schools, charities and public
  bodies.
- **Paid work with the box is free too.** Live events, installations, rentals
  and consulting are permitted, which is what the
  [additional permission](ADDITIONAL-PERMISSION.md) is for.
- **Forks and modifications are welcome**, as long as the licence, that
  permission and the copyright notice travel with them, so credit stays
  attached.
- **Selling hardware with the firmware on it needs an agreement**, as does
  anything else the permission does not cover. Open an issue and ask.

Contributions go through pull requests, are licensed under the same terms, and
are covered by the [contributor licence agreement](CLA.md). See
[CONTRIBUTING.md](CONTRIBUTING.md).

## No warranty, and where not to use this

> [!WARNING]
> The software comes as is, with no warranty of any kind, and the licensor is
> not liable for any damage arising from using it. That covers your fixtures,
> your rig, your venue and the people standing in it.

The reason is not boilerplate. Timing here is best effort: a command travels over
WiFi into a single-threaded loop, so the delay before a fixture reacts varies and
can spike, and a cue can land late or not at all.
[Timing and latency](docs/wiki/timing.md) explains exactly why, and what the
board does guarantee.

So do not drive anything that can hurt someone or break something when a command
is late: pyrotechnics, flame, hoists, moving trusses, winches, lasers, or any
machine where a missed cue has a physical consequence. Use a real desk on a wired
Art-Net or sACN network for that. If you use this firmware there anyway, that is
your decision and your responsibility.

## Credits

Successor to [ESPDMX](https://github.com/CestMoiRoma/ESPDMX) by
[CestMoiRoma](https://github.com/CestMoiRoma). The wiring diagram comes from that
project. DMX output is driven by the
[esp_dmx](https://github.com/someweisguy/esp_dmx) library by Mitch Weisbrod on
the ESP32, and the [ESPDMX](https://github.com/Rickgg/ESP-Dmx) library by Rick on
the ESP8266.
