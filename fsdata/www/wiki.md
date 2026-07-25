# DMX over WiFi: wiki

Reference for everything you drive from a keyboard: the serial console, the HTTP
API, the MQTT bridge and the config files.

See [README.md](README.md) for hardware, wiring, build environments and
first-time setup.

- [Serial console](#serial-console)
  - [Opening a session](#opening-a-session)
  - [Command syntax](#command-syntax)
  - [Command reference](#command-reference)
- [Channel types](#channel-types)
- [HTTP API](#http-api)
- [MQTT and Home Assistant](#mqtt-and-home-assistant)
- [Timing and latency](#timing-and-latency)
- [Configuration files](#configuration-files)
- [Exporting config](#exporting-config)
- [Troubleshooting](#troubleshooting)

## Serial console

The board exposes a text console on its serial port. It is polled from the main
loop, so it stays available while DMX is running and you can reconfigure a live
rig without a browser.

- On the **ESP32-S2** the console is the native USB CDC port (`Serial`).
- On the **ESP8266** it is UART0, reached through the board's USB-to-serial chip.

DMX output uses a different UART on both boards, so the console never collides
with it.

### Opening a session

Any serial terminal at **115200 baud** works. PlatformIO ships one:

```bash
pio device monitor -e s2mini      # or -e d1mini
```

Type a command and press Enter. On the ESP32-S2's native USB CDC port some GUI
terminals need DTR asserted before the port answers; `pio device monitor` handles
that. Send a plain newline at the end of each line.

```
> get-status
OK wifi: mode=sta ssid=NoctiIOT ip=192.168.1.98
OK mqtt: enabled=False connected=False broker=
OK system: hostname=ESP-DMX tx_pin=IO4 dir_pin=disabled
OK devices: 0 device(s), 0 channel(s)
OK memory: 214128 bytes free
```

### Command syntax

```
<Command> [subcommand] [key=value ...]
```

- Commands and subcommands are case insensitive, so `get-status`, `Get-Status`
  and `GET-STATUS` are the same.
- Arguments are `key=value`. Values containing spaces must be quoted, with
  single or double quotes: `ssid="Guest Network"`.
- Values are otherwise taken literally, so nothing needs escaping.
- Passwords accept three spellings: `passwd=`, `psswd=` or `password=`.
- Every output line is prefixed with `OK `. Failures come back as a single
  `ERR <reason>` line.

### Command reference

Type `Help` on the board for the built-in summary.

#### WiFi

| Command | What it does |
|---|---|
| `Add-Wifi ssid=<ssid> passwd=<password> [priority=<n>]` | Save a network and immediately try to join it. Higher priority wins at boot. Re-adding an SSID replaces its entry. |
| `Set-System wifi-add ssid=<ssid> passwd=<password> [priority=<n>]` | The same thing, under `Set-System`. |
| `Set-System wifi-del ssid=<ssid>` | Remove a saved network. |
| `Set-System wifi-list` | List visible networks with their signal strength, and saved ones with their priority. |

```
> Add-Wifi ssid="Venue WiFi" passwd="stage-left-2026" priority=10
OK wifi 'Venue WiFi' saved and connected
```

The reply says `saved` on its own when the network could not be joined, which
usually means it is out of range or the password is wrong. The entry is still
stored either way.

#### MQTT

| Command | What it does |
|---|---|
| `Add-mqtt broker=<host> user=<user> passwd=<password> [port=<n>]` | Enable MQTT, save the broker and connect. Port defaults to `1883`. |
| `Set-System mqtt-enable broker=<host> user=<u> passwd=<p> [port=<n>]` | The same thing, under `Set-System`. |
| `Set-System mqtt-disable` | Disable MQTT and disconnect. |

```
> Add-mqtt broker=192.168.1.20 user=dmx passwd=secret
OK mqtt enabled, broker=192.168.1.20
```

#### DMX pins

| Command | What it does |
|---|---|
| `Set-System tx-pin=<pin>` | Set the pin wired to the MAX485 `DI`. Reboot to apply. |
| `Set-System dir-pin enable=<true\|false> [pin=<pin>]` | Enable or disable the `DE` and `RE` direction pin, and name it. Reboot to apply. |

The pin is a raw GPIO number, optionally with an `IO`/`GPIO` prefix that is
cosmetic: `IO4`, `GPIO4` and `4` all mean GPIO4. `enable=` treats `true`, `1`,
`yes` and `on` as true, and anything else as false.

> On the ESP8266 the DMX output is fixed to `Serial1` (GPIO2), so `tx-pin` is
> stored but has no effect there. The direction pin still works as a normal GPIO.

Leave the direction pin disabled if `DE` and `RE` are tied to VCC. That is the
default, and it matches the reference wiring.

```
> Set-System tx-pin=IO4
OK dmx tx pin set to 'IO4' (reboot to apply)
> Set-System dir-pin enable=true pin=IO18
OK dir pin enabled (pin=IO18) (reboot to apply)
```

#### Hotspot

| Command | What it does |
|---|---|
| `Set-System hotspot name=<name> passwd=<password>` | Rename the config access point, or change its password. Reboot to apply. |

Defaults are SSID `ESP-DMX`, password `DMX4ALL1`, address `1.1.1.1`. The hotspot
starts automatically whenever no saved network can be joined, so the UI stays
reachable with no infrastructure around.

#### Fixtures and channels

| Command | What it does |
|---|---|
| `Set-device add name=<name>` | Create a fixture. The start channel is assigned automatically, right after the last address currently in use. |
| `Set-device add-channel device=<name> name=<ch> channel=<offset> mode=<mode>` | Add a channel. `channel=` is the offset within the fixture, not the DMX address. |
| `Set-device del-channel name=<ch> [device=<name>]` | Remove a channel. If the name exists on several fixtures you must pass `device=`. |
| `Set-device del device=<name>` | Delete a fixture. |

`mode=` takes any of the aliases in [Channel types](#channel-types). Anything
unrecognised falls back to `slider`.

The DMX address actually driven is `start_channel + offset - 1`.

```
> Set-device add name="PAR LED"
OK device 'PAR LED' added (start channel 1)
> Set-device add-channel device="PAR LED" name=Dimmer channel=1 mode=slider
OK channel 'Dimmer' added to 'PAR LED' (offset 1, slider)
> Set-device add-channel device="PAR LED" name=Lamp channel=2 mode=toggle
OK channel 'Lamp' added to 'PAR LED' (offset 2, button-switch)
```

#### Status

| Command | What it reports |
|---|---|
| `get-status` or `get-status all` | WiFi, MQTT, system pins, fixture and channel counts, free memory |
| `get-status wifi` | Mode (`sta` or `ap`), SSID, address |
| `get-status mqtt` | Enabled, connected, broker |
| `get-status devices` | One line per fixture, with its start channel and channel count |
| `get-status device name=<name>` | Every channel of one fixture, with its live DMX value |
| `get-status channel channel=<ch> [device=<name>]` | One channel's offset, mode and live value |
| `get-status mesh` | Stored mesh role and SSID (work in progress) |

```
> get-status device name="PAR LED"
OK   1: Dimmer (slider) = 255
OK   2: Lamp (button-switch) = 0
```

#### Parent and child mesh, work in progress

| Command | What it does |
|---|---|
| `Set-System mesh role=<none\|parent\|child> [ssid=<>] [passwd=<>]` | Stores the settings only. No parent or child radio logic exists yet. |

#### Other

| Command | What it does |
|---|---|
| `Reboot` | Restart the board |
| `Help` | Print the built-in command summary |

## Channel types

| Type | Home page control | Sends | Home Assistant entity | Serial aliases |
|---|---|---|---|---|
| `slider` | A 0 to 255 fader | The fader value on release | `number`, min 0, max 255 | `slider` |
| `button` | A **Trigger** button | 255 on each press | `button` | `button`, `btn`, `trigger`, `bool`, `boolean` |
| `button-momentary` | A **Hold** button | 255 on press, 0 on release | `button` | `momentary`, `hold`, `btn-momentary`, `button-momentary` |
| `button-switch` | An **On** and **Off** toggle | 255 or 0, latching | `switch` | `switch`, `toggle`, `btn-switch`, `button-switch` |

`button-momentary` also responds to touch, so it works from a phone at the
lighting position.

Only `slider` and `button-switch` publish state back to MQTT. The other two are
stateless by design, since a trigger has nothing to report between presses.

## HTTP API

Served on port 80 alongside the UI. JSON in, JSON out. There is no
authentication, so keep the board on a network you trust.

A headless build (`WITH_WEBUI=0`) drops the page routes below but keeps every
`/api/*` route, so the box stays controllable over HTTP with no served UI.

### Pages

| Method | Route | |
|---|---|---|
| `GET` | `/` | The single-page web UI |
| `GET` | `/wiki.md` | This document, served from the board's LittleFS |

### Fixtures

| Method | Route | Body and result |
|---|---|---|
| `GET` | `/api/devices` | Every fixture with its channels |
| `POST` | `/api/devices` | `{"name":…, "start_channel":…, "channels":[{"offset":…,"name":…,"type":…}]}`, returns the created fixture |
| `PUT` | `/api/devices/<device_id>` | Any of `name`, `start_channel`, `channels`, returns the updated fixture or `404` |
| `DELETE` | `/api/devices/<device_id>` | `{"ok": true}` or `{"ok": false}` |
| `POST` | `/api/devices/<device_id>/channel/<offset>` | `{"value": 0-255}`, returns `{"ok": true}` or `404` |

Setting a channel writes the DMX buffer straight away and mirrors the value to
MQTT. Values are clamped to 0 through 255. A missing `value` is treated as 0.

### WiFi

| Method | Route | |
|---|---|---|
| `GET` | `/api/wifi` | Saved networks |
| `POST` | `/api/wifi` | `{"ssid":…, "password":…, "priority":…}`, returns the updated list |
| `DELETE` | `/api/wifi/<ssid>` | Returns the updated list |
| `GET` | `/api/wifi/scan` | Visible networks, as `[{"ssid":…, "rssi":…}]` |

`POST /api/wifi` saves without connecting, unlike the serial `Add-Wifi`.

### Configuration

| Method | Route | |
|---|---|---|
| `GET` and `POST` | `/api/mqtt` | Read or merge the MQTT config. A `POST` also restarts the client |
| `GET` and `POST` | `/api/system` | Read or merge `system.json`: pins, hostname, hotspot, static IP |
| `GET` and `POST` | `/api/mesh` | Read or merge `mesh.json`, work in progress, stored only |
| `GET` | `/api/info` | Version, author, repository and wiki links, for the Info page |
| `GET` | `/api/export-env` | The board's whole live config as a `.env` file, served as a download |

`POST` merges into the existing config, so you can send a single key.

```bash
curl http://192.168.1.98/api/devices
curl -X POST http://192.168.1.98/api/devices/dev-a1b2c3/channel/1 \
     -H "Content-Type: application/json" -d '{"value":128}'
```

## MQTT and Home Assistant

MQTT is optional and only starts when the board is on a real network, not on its
own hotspot.

| Setting | Default |
|---|---|
| `base_topic` | `dmxwifi` |
| `discovery_prefix` | `homeassistant` |
| `port` | `1883` |

Every channel gets a unique id of `<device_id>_<offset>`, for example
`dev-a1b2c3_1`.

### Topics

| Topic | Direction | Payload |
|---|---|---|
| `<base_topic>/<uid>/set` | in | Slider: a number from 0 to 255. Switch: `ON`, `OFF`, `TRUE`, `FALSE`, `1`, `0`, `255`. Trigger and momentary: any payload fires 255. |
| `<base_topic>/<uid>/state` | out | The current value, for sliders and switches only |

### Discovery

On connect, and whenever fixtures change, the board publishes retained discovery
configs:

| Channel type | Discovery topic | Entity |
|---|---|---|
| `slider` | `<discovery_prefix>/number/<uid>/config` | `number`, min 0, max 255, step 1 |
| `button-switch` | `<discovery_prefix>/switch/<uid>/config` | `switch`, on 255, off 0 |
| `button` and `button-momentary` | `<discovery_prefix>/button/<uid>/config` | `button` |

All channels of a fixture share one `device` block, identified by the device id,
so Home Assistant groups them as a single device.

## Timing and latency

> [!WARNING]
> The delay between a command and the fixture reacting is not guaranteed. It
> varies, and it can spike. Do not put this box anywhere a late or dropped cue
> matters.

The chain is browser or MQTT, then WiFi, then the HTTP or MQTT handler, then the
DMX buffer, then the next DMX frame. Only the last hop has anything like a fixed
cost.

| Stage | Behaviour |
|---|---|
| WiFi | Best effort. Retries, interference, a busy access point or a roaming client add tens to hundreds of milliseconds, unpredictably |
| MQTT | Adds a broker round trip, and a reconnect blocks the loop while it happens |
| Main loop | `loop()` polls HTTP, MQTT, the DMX refresh and the serial console in turn. No preemption and no priorities, so a slow request delays the next frame. On the ESP8266 the single core is shared with the WiFi stack too |
| DMX frame | The refresh interval is 25 ms, checked from the loop with `millis()` rather than driven by a timer interrupt. The break is generated in software around each frame |

The native C++ build removed the CircuitPython interpreter and its
garbage-collector pauses, so the loop runs far tighter and the DMX frame is
steadier than on the previous firmware. It did not make WiFi arrival
deterministic.

What is dependable: once a value is in the buffer it keeps going out at roughly
40 frames a second, so fixtures hold state and do not flicker. It is the arrival
of a new value that has no deadline.

In practice:

- Fine for setting levels, static looks, colour changes, house lights and
  ambience.
- Not for anything that has to land on a beat, and not for pyro, moving trusses
  or anything safety related.
- Chases and effects should be generated on the fixture, using its built-in
  programs, rather than streamed channel by channel from a browser.

If you need deterministic timing, drive the rig from a real lighting desk or an
Art-Net or sACN node on a wired network.

## Configuration files

The board writes its state as JSON under `/data` on its LittleFS filesystem. This
is runtime data, separate from the flashed firmware and web-asset image, so a
firmware re-upload leaves it alone. Missing files are recreated from defaults on
first read, and a corrupt file is replaced rather than left to fail again on the
next boot. Each save is written to a sibling `.tmp` file and renamed, so an
interrupted write cannot truncate the live file.

| File | Holds |
|---|---|
| `wifi_networks.json` | `[{ssid, password, priority}]` |
| `devices.json` | `[{id, name, start_channel, channels[]}]` |
| `mqtt.json` | `enabled`, `host`, `port`, `username`, `password`, `base_topic`, `discovery_prefix` |
| `system.json` | `dmx_tx_pin`, `dmx_dir_pin_enabled`, `dmx_dir_pin`, `hostname`, `ap_ssid`, `ap_password`, `ap_ip`, `sta_ip_mode`, `sta_static_ip`, `sta_static_netmask`, `sta_static_gateway`, `sta_static_dns` |
| `mesh.json` | `role`, `ssid`, `password` (work in progress) |

Shipping defaults: DMX TX on `IO4` (ESP32) or fixed `GPIO2` (ESP8266), direction
pin disabled on `IO18`, hostname and hotspot SSID `ESP-DMX`, hotspot password
`DMX4ALL1`, hotspot address `1.1.1.1`, DHCP, MQTT disabled with base topic
`dmxwifi`.

Static IP is applied when joining a network, and only when `sta_ip_mode` is
`static` and both an address and a gateway are set. If the values do not parse,
the board stays on DHCP rather than dropping off the network.

> [!NOTE]
> `hostname` is stored, editable in Settings, exported to `.env` and reported by
> `get-status`, but nothing hands it to the radio yet, so it currently has no
> effect on the network. Applying it and announcing `esp-dmx.local` over mDNS is
> on the [roadmap](README.md#reliability-and-operations).

To wipe a setting back to defaults, delete its `/data/*.json` file (for example
by reflashing the LittleFS image, or over a future OTA) and reboot.

## Exporting config

**Settings**, **Configuration**, **Export .env**, or fetch `/api/export-env`
directly, hands the board's whole live config back as a readable `.env` file:
saved networks, MQTT, the system group including static IP, mesh settings, and
every fixture with its channels.

It is a human-readable backup and a way to snapshot a working board before
experimenting. There is no importer in this firmware; restore by re-entering
values through the UI or the serial console.

## Troubleshooting

**Build pulls the wrong DMX backend, or a link error mentions Serial1**
Each backend file is guarded by an `ESP8266` / ESP32 macro, and PlatformIO
selects the toolchain from the environment. Build with an explicit environment,
for example `pio run -e s2mini`, rather than mixing artifacts.

**The web UI is blank or 404s, but the API works**
The assets were not flashed. Run `pio run -e <env> -t uploadfs` to write the
`fsdata/www/` LittleFS image. A firmware upload alone does not include them.

**Serial port opens but nothing answers**
Pick the board's own USB serial device rather than a Bluetooth COM port, use
115200 baud, and make sure your terminal asserts DTR on the ESP32-S2's native USB
CDC port. `pio device monitor` does.

**A pin change had no effect**
`tx-pin` and `dir-pin` are only read at startup. Reboot.

**A DMX pin setting is ignored on the ESP8266**
Expected. The ESP8266 DMX output is fixed to `Serial1` (GPIO2); only the ESP32
honours a configurable tx pin. The direction pin still works.

**Cannot reach the UI**
Check `get-status wifi` over serial. `mode=ap` means it fell back to its hotspot,
so join `ESP-DMX` and browse to <http://1.1.1.1>.

**A fixture responds on the wrong DMX address**
The address is `start_channel + offset - 1`. A fixture starting at 10 with a
channel at offset 1 drives DMX address 10, not 11.

**MQTT never connects**
It only starts in station mode, and only if `enabled` is set with a non-empty
host. Check with `get-status mqtt`.

**A cue arrived late, or a fader felt sluggish**
Expected. See [Timing and latency](#timing-and-latency). There are no delivery or
timing guarantees.
