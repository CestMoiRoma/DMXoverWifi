# DMX over WiFi — Mark II

A standalone DMX512 transmitter that you configure and drive from a web browser.
It runs **CircuitPython on an ESP32 board**, serves its own web UI, remembers
several WiFi networks, falls back to its own hotspot when none are in range, and
can expose every DMX channel to Home Assistant over MQTT.

> **This is a full rewrite of my earlier ESPDMX project**
> ([CestMoiRoma/ESPDMX](https://github.com/CestMoiRoma/ESPDMX)), the "MKII" that
> was on that project's roadmap. Nothing of the old Arduino/ESP8266 firmware is
> reused: the WebSocket-only control scheme is gone, replaced by a web UI, a REST
> API, an MQTT bridge and a serial console. Only the electrical design carries
> over.

---

## Table of contents

- [What it does](#what-it-does)
- [Hardware](#hardware)
- [Wiring](#wiring)
- [Getting started](#getting-started)
- [Web UI](#web-ui)
- [Timing and latency](#timing-and-latency)
- [Repository layout](#repository-layout)
- [Documentation](#documentation)

---

## What it does

| | |
|---|---|
| **DMX output** | Full 512-channel universe, refreshed every 25 ms (~40 fps), bit-banged over UART with a proper break/MAB |
| **Web UI** | Three pages — live control, device/channel editor, settings — served straight from the board |
| **Devices & channels** | Group DMX addresses into named fixtures; each channel is a `slider` (0-255) or a `button` (fire 255) |
| **Multi-network WiFi** | Save several SSIDs with priorities, so the same box works at home, at the venue and on tour |
| **Config hotspot** | No known network in range? It starts its own AP (`ESP-DMX` / `1.1.1.1`) so you can still reach the UI |
| **MQTT + Home Assistant** | Optional. Publishes auto-discovery configs so every channel shows up as a `number` or `button` entity |
| **Serial console** | Full text command set over USB CDC — config, status, reboot — no browser needed |
| **Parent/Child mesh** | Placeholder in the UI and settings store. **WIP: stored only, no radio behaviour yet.** |

---

## Hardware

- **An ESP32-family board that runs CircuitPython.** Developed and tested on a
  **Wemos / Lolin S2 Mini** (ESP32-S2, CircuitPython board id `lolin_s2_mini`,
  4 MB flash / 2 MB PSRAM).
- **A MAX485 / RS-485 breakout** (the common blue module with `RO DI DE RE` on one
  side and `VCC A B GND` on the other).
- **A 3-pin or 5-pin XLR female** connector for the DMX out.
- USB cable, and 5 V for the MAX485.

Output only, `RO` stays unconnected, so there is no DMX input and no RDM. (at the moment).

---

## Wiring

![MAX485 wiring for a DMX output](docs/images/wiring-espdmx.png)

> [!IMPORTANT]
> **The board in this picture is a Wemos D1 Mini (ESP8266)** — it comes from the
> original ESPDMX project and is kept here because the RS-485 side of the circuit
> is identical. **This repository does not run on an ESP8266.** It needs an
> **ESP32 board running CircuitPython** (see [Hardware](#hardware)). Wire the
> MAX485 exactly as shown, but take the signals from your ESP32's pins and set the
> matching pin names in the UI or over serial.

### Connections

| Microcontroller | MAX485 | Notes |
|---|---|---|
| `D4` (configurable) | `DI` | The DMX data line. This is the **DMX TX pin** setting; default `D4` |
| `5V` | `VCC` | |
| `GND` | `GND` | |
| — | `DE` + `RE` | Tied together **to VCC** in this schematic → permanently transmit-enabled |
| — | `RO` | Not connected |

| MAX485 | XLR (female) | DMX signal |
|---|---|---|
| `GND` | pin 1 | Shield / common |
| `B` | pin 2 | Data − |
| `A` | pin 3 | Data + |

### About the DE/RE pin

The schematic above ties `DE` and `RE` straight to VCC, so the transceiver always
transmits and the microcontroller has nothing to drive. That is the **default**
in this firmware: `dmx_dir_pin_enabled` is `false`.

If your wiring instead routes `DE`+`RE` to a GPIO, enable the direction pin and
name it:

- in the UI: *Settings → System → **Enable DE/RE direction pin*** + *DE/RE pin*
- over serial: `Set-System dir-pin enable=true pin=D3`

Either way, **reboot the board** for a pin change to take effect.

---

## Getting started

### 1. Flash CircuitPython

Install CircuitPython on your ESP32 board (for the Lolin S2 Mini: hold `0`, tap
`RST`, drop the `.uf2` on the bootloader drive). The board then shows up as a
`CIRCUITPY` mass-storage volume.

### 2. Get the code

```bash
git clone https://github.com/CestMoiRoma/DMXoverWifi.git
cd DMXoverWifi
```

The tooling needs Python 3 and [pyserial](https://pypi.org/project/pyserial/) on
your PC (`pip install pyserial`) — nothing else, no build step.

### 3. Deploy the firmware

`tools/deploy.py` copies everything the board needs — `boot.py`, `code.py`, `src/`,
`www/` and the vendored `lib/` — onto the `CIRCUITPY` volume. It leaves `data/`
(your saved config) alone.

On a **fresh CircuitPython install** the volume is already writable, so you can
run it straight away:

```bash
python tools/deploy.py E:\        # omit the path and it asks
```

Once the firmware is running, the board takes write access for itself and the
volume becomes read-only from the PC. To deploy again, unlock it over serial —
see [Unlocking the filesystem](#unlocking-the-filesystem-for-a-deploy) below.

Reboot the board when the copy finishes.

### 4. Connect it to WiFi

Fresh out of the box there is no saved network, so the board starts its config
hotspot:

| | |
|---|---|
| SSID | `ESP-DMX` |
| Password | `DMX4ALL1` |
| Address | <http://1.1.1.1> |

Join it, open the page, go to **Settings → WiFi**, hit **Scan**, add your network
and reboot. From then on it joins that network on boot and the UI lives at
whatever IP your router hands out.

You can do the same thing over USB instead:

```
Add-Wifi ssid="My Network" passwd="hunter2" priority=10
```

See the [wiki](WIKI.md) for the serial console.

### 5. Add a fixture

**Device Manager → New device**: give it a name, a DMX start channel, then add
channels. A channel's *offset* is relative to the start channel, so a fixture at
start channel 10 with offset 3 drives DMX address 12. Sliders and buttons then
show up on **Home**.

### Unlocking the filesystem for a deploy

CircuitPython gives filesystem write access to exactly one side — the board or the
USB host, never both. After a normal boot the **board** owns it, so `CIRCUITPY`
shows up read-only on your PC and `deploy.py` refuses to run.

Hand write access back over the serial console:

1. **Eject / safely remove** the `CIRCUITPY` volume. Leave the USB cable in — the
   serial port stays alive. (`unlock-write` refuses while the volume is still
   mounted: *`ERR Cannot remount '/' when visible via USB`*.)
2. Send `Set-System unlock-write`.
3. Let the OS pick the volume back up. Linux and macOS usually remount on their
   own; on Windows you may need *Device Manager → Action → Scan for hardware
   changes*, or `rescan` in an elevated `diskpart`.
4. Run `python tools/deploy.py`.
5. Send `Reboot` — the board takes write access back and runs the new code.

While unlocked the board **cannot save its own config**, so don't change settings
through the UI in that window; step 5 puts everything back to normal.

---

## Web UI

### Home — live control

Every configured fixture, with a slider or a trigger button per channel. Moving a
slider writes the DMX buffer immediately.

![Home page](docs/images/ui-home.png)

### Device Manager — fixtures and channels

Create, inspect and delete fixtures; add channels with an offset, a name and a
type (`slider` or `button`).

![Device Manager page](docs/images/ui-devices.png)

### Settings — WiFi, MQTT, system, mesh

Saved networks with priorities and a scanner, the full MQTT/Home-Assistant
configuration, the DMX pin assignments and hotspot credentials, and the
work-in-progress Parent/Child section.

![Settings page](docs/images/ui-settings.png)

> Screenshots taken from a live board; the two fixtures shown are demo entries.

---

## Timing and latency

> [!WARNING]
> **Latency is not guaranteed.** The delay between moving a slider (or publishing
> an MQTT message) and the fixture reacting is variable, and it can occasionally
> spike well past what feels acceptable for live work. Do not use this box where a
> late or dropped cue matters — pyro, moving trusses, anything safety-related, or
> a show that has to hit an exact musical beat.

Where the jitter comes from:

- **WiFi is best-effort.** Retries, interference, a busy access point, a client
  roaming — any of it adds tens or hundreds of milliseconds, unpredictably. Add a
  broker and Home Assistant on top and the tail gets longer.
- **One cooperative loop.** `code.py` polls the HTTP server, the MQTT client, the
  DMX refresh and the serial console in a single `while True`. There is no
  pre-emption and no priority: a slow HTTP request or an MQTT reconnect delays the
  next DMX frame.
- **CircuitPython is interpreted**, with a garbage collector that can pause the
  loop at any moment.
- **The DMX frame itself is software-timed.** The break is generated by
  reconfiguring the UART, and the ~25 ms refresh is "whenever the loop next comes
  round and enough time has passed", not a timer interrupt.

What *is* reasonably solid: once a value is in the DMX buffer it keeps being sent
out at roughly 40 fps, so fixtures hold their state and don't flicker. It is the
*arrival* of a new value that has no deadline.

If you need deterministic timing, drive your rig from a real DMX desk or an
Art-Net/sACN node on a wired network.

---

## Repository layout

```
boot.py                 Filesystem mount mode selection at boot
code.py                 Wiring-up and the main loop
settings.toml           CircuitPython environment (empty by default)

src/
  dmx_driver.py         512-channel buffer, break/MAB generation, 40 fps refresh
  devices.py            Device/Channel model, persistence, DMX address mapping
  web_server.py         HTTP routes: static UI + JSON API
  wifi_manager.py       Saved-network DB, priority connect, AP fallback
  mqtt_manager.py       MQTT client + Home Assistant auto-discovery
  serial_console.py     USB CDC command interpreter
  settings_store.py     JSON config files under /data with defaults

www/                    The web UI (plain HTML/CSS/JS, no build step)
lib/                    Vendored CircuitPython libraries
data/                   Runtime config written by the board (git-ignored)

tools/
  deploy.py             Sync firmware + lib/ onto CIRCUITPY
  serial_console.py     Serial terminal (needs pyserial)

docs/images/            Wiring schematic and UI screenshots
```

Config lives in `/data/*.json` on the board and is **git-ignored** — it holds your
WiFi and MQTT passwords in clear text.

---

## Documentation

**[WIKI.md](WIKI.md)** — the full reference:

- every serial command, with arguments and examples
- how to open a serial session and how to deploy
- how filesystem write access works
- the HTTP JSON API
- MQTT topics and Home Assistant discovery
- troubleshooting

---

## Status & roadmap

Working: DMX output, web UI, device model, multi-network WiFi, AP fallback, MQTT
with HA discovery, serial console, deploy tooling.

Planned:

- **DMX input.** Wire `RO` and a direction pin so the board can *receive* a
  universe from a real lighting desk instead of only generating one. The point is
  the parent role below: one box patched into the desk, reading DMX and relaying
  it over WiFi to the child nodes, which output it locally. That turns the whole
  thing into a wireless DMX distribution system rather than a standalone
  controller.
- **Parent/Child mesh.** The UI, the serial command and the stored settings exist,
  but nothing acts on them yet — no parent/child radio logic.
- **Authentication.** There is none on the web UI or the API today. Keep the board
  on a network you trust.

---

## Credits

Successor to [ESPDMX](https://github.com/CestMoiRoma/ESPDMX). The wiring diagram is
taken from that project.
