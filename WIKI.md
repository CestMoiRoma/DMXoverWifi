# DMX over WiFi: wiki

Reference for everything you drive from a keyboard: the serial console, the HTTP
API, the MQTT bridge and the config files.

See [README.md](README.md) for hardware, wiring, build environments and
first-time setup.

- [Serial console](#serial-console)
  - [Opening a session](#opening-a-session)
  - [Command syntax](#command-syntax)
  - [Command reference](#command-reference)
- [Binary serial protocol](#binary-serial-protocol)
- [Channel types](#channel-types)
- [Categories](#categories)
- [Labels](#labels)
- [API access control](#api-access-control)
- [HTTP API](#http-api)
- [WebSocket](#websocket)
- [MQTT and Home Assistant](#mqtt-and-home-assistant)
- [Timing and latency](#timing-and-latency)
- [Configuration files](#configuration-files)
- [Exporting config](#exporting-config)
- [Reseeding config from `.env`](#reseeding-config-from-env)
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

#### USB-only mode

| Command | What it does |
|---|---|
| `Set-System wifi-toggle on\|off` | Turns the radio on or off for the next boot |

With WiFi off the board never brings the radio up, and the web server, mDNS and
MQTT never start with it. The serial console becomes the entire interface, which
is the point: a rig driven from a laptop over USB has no reason to broadcast.
Turn it back on from the console, or set `WIFI_ENABLED` in `.env` and reflash.

#### Driving channels

| Command | What it does |
|---|---|
| `Set-Value channel=<name> [device=<name>] value=<0-255>` | Drives every channel with that name, or only the one on the named fixture |
| `Set-Value address=<1-512> value=<0-255>` | Writes a raw DMX slot, bypassing the fixture model |

`address=` is the probe form: it answers "which slot does this projector
actually listen on" without needing a fixture defined first.

#### Fixtures and channels

| Command | What it does |
|---|---|
| `Set-device add name=<name> [channel=<start>] [category=<id>]` | Create a fixture. Without `channel=` the start channel lands right after the last address currently in use. `category=` takes an id from [Categories](#categories) and defaults to `other`. |
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
| `Get-Config` | Fixtures with their live values, the label table and the category vocabulary, as one line of JSON. Meant for tooling, not for reading |
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

## Binary serial protocol

The text console is fine for configuring a board and hopeless for driving one.
`Set-Value address=4 value=200` is 30 bytes and a string parse for a single DMX
slot, which a dragged fader would send hundreds of times a second. Measured on
an ESP32-S2, 300 updates to one channel:

| | Bytes per update | Updates per second |
|---|---|---|
| `Set-Value` text command | 30 | 81 |
| Binary frame | 7 | 914 |

So binary frames share the same link, told apart by a start byte the text
protocol never begins a line with. A `0x7E` anywhere other than the start of a
line is ordinary text, so it cannot drag the parser into binary mode
mid-sentence.

```
host  -> board   7E <cmd>        <len> <payload...> <crc8>
board -> host    7E <cmd | 0x80> <len> <payload...> <crc8>
```

`crc8` is the classic polynomial `0x07` over the command, the length and the
payload. A frame that fails the check is dropped rather than guessed at: a wrong
DMX value is worse than a missing one, and any sender worth the name resends on
its next tick.

| Cmd | Payload | Does |
|---|---|---|
| `0x01` | `addr_hi addr_lo value` | Writes one DMX slot |
| `0x02` | `addr_hi addr_lo count values...` | Writes a run of slots |
| `0x03` | `addr_hi addr_lo count` | Reads a run back, answered on `0x83` |
| `0x10` | none | Ping, answered on `0x90` |

Addresses are 1 to 512 and anything outside is ignored. The length byte caps one
frame at 255 payload bytes, so a full universe takes three block writes.

> On the ESP32-S2 the port is native USB CDC, where the baud rate is a fiction
> both ends ignore. Throughput is the USB link's, so the gain comes from the
> compact frames rather than from any baud setting. On the ESP8266 it is a real
> UART and the baud rate does matter.

`Get-Config` is the companion on the text side: one line of JSON with every
fixture and its live values, the label table and the category vocabulary, so
tooling never has to scrape the human-readable status lines.

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

## Categories

Every fixture has exactly one category, chosen when it is created and editable
afterwards. Unlike labels, the list is **fixed in the firmware** and not
user-editable:

| id | Shown as |
|---|---|
| `par` | PAR |
| `bar` | LED bar |
| `lyre` | Moving head |
| `scanner` | Scanner |
| `strobe` | Strobe |
| `blinder` | Blinder |
| `laser` | Laser |
| `smoke` | Smoke and haze |
| `dimmer` | Dimmer pack |
| `effect` | Effect |
| `other` | Other |

The split is deliberate. A label answers "where is this in my rig" and is yours
to invent; a category answers "what kind of machine is this", which the firmware
and the UI can both reason about. That is why the vocabulary is closed: later
work on the fixture editor keys off it, and it cannot key off names nobody has
agreed on.

Unknown ids fall back to `other` on load rather than being kept, so a
hand-edited config cannot file a fixture under something nothing can filter.
Adding a category means editing `src/categories.h` and reflashing; the list is
served at `/api/categories` so the UI never duplicates it.

`GET /api/categories` returns the table, `DEVICE_n_CATEGORY` sets it from `.env`,
and `Set-device add name=<name> category=<id>` sets it from the console.

## Labels

Labels are colour-coded tags stored in `labels.json`, each with an `id`, a
`name` and a `color`. A fixture references them by id in its own `labels` array,
and carries as many as you like, so one PAR can be both **Face** and **PAR**.

The Devices page turns them into chips. Selecting several **widens** the
selection rather than narrowing it: **Face** plus **Contre** shows every fixture
carrying either, which is what a rig usually wants. The count on each chip is
how many fixtures carry that label.

Deleting a label strips its id from every fixture that referenced it, so nothing
is left filtering under a chip that no longer exists. The fixtures themselves,
and their channels, are untouched.

In `.env` the relationship travels by **name** rather than by id, since that file
is meant to stay readable: `LABEL_1_NAME` declares one, and `DEVICE_1_LABELS`
takes a comma-separated list of those names. A name matching no label is dropped
rather than invented, so a typo shows up as a missing chip.

## API access control

The served web UI is trusted and needs no key. Every other caller of `/api/*`
needs two things: the **HTTP API module** switched on, and a valid key in an
`X-API-Key` header or an `api_key` query parameter.

| Caller | HTTP API on | HTTP API off |
|---|---|---|
| The UI served by the board | allowed | allowed |
| Anything else, with the right key | allowed | `403` |
| Anything else, wrong or missing key | `401` | `403` |

"The UI" means a request whose `Origin` or `Referer` points back at this board.
Browsers set those and will not let a page forge them, so it does keep a random
web page from driving your rig. It is **not** a defence against a hand-rolled
client: `curl` sets any header it likes. Treat the key, not the origin check, as
the thing actually gating scripted access, and treat the whole arrangement as
suited to a trusted LAN rather than the open internet.

The key is 64 hex characters, minted on first boot and stored in `api.json`. It
is never seeded from `.env`, so flashing one checkout onto several boards does
not give them all the same key. Regenerating it from **Settings**, **API**
immediately invalidates the old one.

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
| `GET` | `/api/devices` | Every fixture with its channels, each carrying its live `value` |
| `POST` | `/api/devices` | `{"name":…, "start_channel":…, "channels":[{"offset":…,"name":…,"type":…}], "labels":[…]}`, returns the created fixture |
| `PUT` | `/api/devices/<device_id>` | Any of `name`, `start_channel`, `channels`, `labels`, returns the updated fixture or `404` |
| `DELETE` | `/api/devices/<device_id>` | `{"ok": true}` or `{"ok": false}` |
| `POST` | `/api/devices/<device_id>/channel/<offset>` | `{"value": 0-255}`, returns `{"ok": true}` or `404` |

Setting a channel writes the DMX buffer straight away and mirrors the value to
MQTT. Values are clamped to 0 through 255. A missing `value` is treated as 0.

### WiFi

| Method | Route | |
|---|---|---|
| `GET` | `/api/wifi` | Saved networks, highest priority first, each with its own addressing |
| `POST` | `/api/wifi` | `{"ssid":…, "password":…, "priority":…}`, adds or updates one entry |
| `PUT` | `/api/wifi` | Replaces the whole list from an ordered array. The order **is** the priority: first is highest |
| `DELETE` | `/api/wifi/<ssid>` | Returns the updated list |
| `GET` | `/api/wifi/scan` | Visible networks, as `[{"ssid":…, "rssi":…}]` |

`POST /api/wifi` saves without connecting, unlike the serial `Add-Wifi`.

On `PUT`, an entry with **no** `password` key keeps the password it already had,
so reordering the list or editing an address cannot wipe a credential the caller
never mentioned. An explicit `"password": ""` still sets an open network.

Each entry carries its own addressing, since the same rig meets DHCP at one
venue and a fixed address at the next:

```json
{
  "ssid": "Venue WiFi",
  "password": "…",
  "ip_mode": "static",
  "static_ip": "192.168.1.100",
  "static_netmask": "255.255.255.0",
  "static_gateway": "192.168.1.1",
  "static_dns": "1.1.1.1"
}
```

A `static` entry whose address or gateway does not parse falls back to DHCP
rather than dropping the board off the network.

### Configuration

| Method | Route | |
|---|---|---|
| `GET` and `POST` | `/api/mqtt` | Read or merge the MQTT config. A `POST` also restarts the client |
| `GET` and `POST` | `/api/system` | Read or merge `system.json`: pins, hostname, hotspot, static IP |
| `GET` and `POST` | `/api/mesh` | Read or merge `mesh.json`, work in progress, stored only |
| `GET` | `/api/info` | Version, board, mDNS hostname, author, repository and wiki links |
| `GET` | `/api/categories` | The fixed category vocabulary, as `[{"id":…, "name":…}]` |
| `GET` | `/api/labels` | Every label, as `[{"id":…, "name":…, "color":…}]` |
| `POST` | `/api/labels` | `{"name":…, "color":…}`, returns the created label |
| `PUT` | `/api/labels/<label_id>` | Any of `name`, `color`, returns the updated label or `404` |
| `DELETE` | `/api/labels/<label_id>` | Removes it and strips it from every fixture that carried it |
| `GET` and `POST` | `/api/modules` | Read or merge the module switches. `GET` also returns `api_key`, but only to the UI |
| `POST` | `/api/modules/key` | Mints a fresh API key and returns it, revoking the old one |
| `POST` | `/api/reboot` | Answers, then restarts the board |
| `GET` | `/api/config` | The whole live config as a `.json` download |
| `POST` | `/api/config` | Restores a config file. Sections absent from the body are left alone |
| `GET` | `/api/export-env` | The board's whole live config as a `.env` file, served as a download |

`POST` merges into the existing config, so you can send a single key.

```bash
curl http://192.168.1.98/api/devices
curl -X POST http://192.168.1.98/api/devices/dev-a1b2c3/channel/1 \
     -H "Content-Type: application/json" -d '{"value":128}'
```

## WebSocket

Live channel control and state fan-out, on **port 81**. The Arduino web server
cannot share port 80 with a socket upgrade, hence the second port.

It exists because a fader dragged across its travel emits values far faster than
one HTTP request each can carry: the headers and the connection setup would cost
more than the DMX. It also lets every open client watch the rig move, which
polling cannot do without hammering the board.

Unlike the HTTP API, the socket has **no origin exemption**. A WebSocket is just
as reachable from a script as from the UI, so every client presents the key:

```
ws://esp-dmx.local:81/?api_key=<key>
```

A connection without a valid key is closed immediately, with no frame sent.

Frames are JSON, since the traffic is small and readability is worth more here
than the bytes.

| Direction | Frame | Meaning |
|---|---|---|
| in | `{"t":"set","d":"<deviceId>","o":<offset>,"v":<0-255>}` | Drive a fixture's channel |
| in | `{"t":"seta","a":<1-512>,"v":<0-255>}` | Drive a raw DMX slot |
| out | `{"t":"hello","clients":<n>}` | Sent once on connect |
| out | `{"t":"val","d":"<deviceId>","o":<offset>,"v":<0-255>}` | A channel changed |

`val` goes out for changes from **any** source, so a fader moved over HTTP, over
the socket or from the serial console shows up in every open browser.

The web UI coalesces writes per channel and flushes them every 30 ms, so a drag
costs one message per channel per interval rather than one per pixel, with the
release always sending the final value. When the module is off or the socket
drops it falls back to `POST /api/devices/…/channel/…` on the same schedule and
keeps retrying the socket in the background. **Settings**, **Info** shows which
transport is actually in use.

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

`/api/info` reports `loop_per_sec` and `loop_max_us`, which is the honest way to
see whether the board is actually keeping up rather than inferring it from a
browser error. A healthy idle board runs around a thousand passes a second with
a worst pass under 20 ms; serving the page pushes the worst pass to roughly
85 ms, which is the transfer itself, written synchronously.

> A 513-slot frame takes about 23 ms on the wire. The transmit backend used to
> wait for it *after* sending, which parked the main loop for 23 ms out of every
> 25 and left the board answering the network about forty times a second.
> Waiting for the *previous* frame before writing the next one costs nothing,
> since the refresh comes round long after the UART has finished, and the loop
> now runs some twenty-five times more often.

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
| `wifi_networks.json` | `[{ssid, password, priority, ip_mode, static_ip, static_netmask, static_gateway, static_dns}]`, highest priority first |
| `devices.json` | `[{id, name, category, start_channel, channels[], labels[]}]` |
| `labels.json` | `[{id, name, color}]` |
| `mqtt.json` | `enabled`, `host`, `port`, `username`, `password`, `base_topic`, `discovery_prefix` |
| `api.json` | `http_api_enabled`, `websocket_enabled`, `mqtt_enabled`, `api_key` |
| `system.json` | `wifi_enabled`, `dmx_tx_pin`, `dmx_dir_pin_enabled`, `dmx_dir_pin`, `hostname`, `ap_ssid`, `ap_password`, `ap_ip` |
| `mesh.json` | `role`, `ssid`, `password` (work in progress) |

Shipping defaults: DMX TX on `IO4` (ESP32) or fixed `GPIO2` (ESP8266), direction
pin disabled on `IO18`, hostname and hotspot SSID `ESP-DMX`, hotspot password
`DMX4ALL1`, hotspot address `1.1.1.1`, DHCP, MQTT disabled with base topic
`dmxwifi`.

Addressing moved out of `system.json` and into each WiFi entry. The board-wide
`sta_ip_mode` and `sta_static_*` keys are gone, along with the `STA_*` keys in
`.env`: a rig that tours meets DHCP at one venue and a fixed address at the
next, and the answer belongs to the network rather than to the board. Static is
applied when joining, and only when both an address and a gateway parse.

`hostname` is handed to the radio and announced over mDNS, so the board answers
on `<hostname>.local` as well as on whatever address the router gave it. It is
sanitised first, since DNS labels allow only letters, digits and hyphens:
anything else folds to a hyphen, and an empty result falls back to `esp-dmx`. A
change takes effect on the next reboot, when the radio comes up again.

To wipe a setting back to defaults, delete its `/data/*.json` file (for example
by reflashing the LittleFS image, or over a future OTA) and reboot.

## Exporting config

Two formats, answering two different questions.

**Settings**, **Config**, **Save .json**, or `GET /api/config`, hands back the
whole live config in one file: system, mesh, saved networks, MQTT, labels and
every fixture. **Load .json** on the same page posts it back and applies it
immediately, section by section. A file missing a section leaves that section
alone, so a partial config is a valid patch rather than a wipe. Pin changes need
a reboot, since the DMX driver reads them once at startup.

**Export .env** on the same page, or `GET /api/export-env`, hands back the same
config as a readable `.env` file: saved networks, MQTT, the system group
including static IP, mesh settings, labels, and every fixture with its channels.

Reach for the `.json` to snapshot a working board before experimenting, or to
clone one board onto another. Reach for the `.env` when you want the config to
survive a reflash, since that is the one the build reads.

## Reseeding config from `.env`

The export round-trips. Drop the file next to `platformio.ini` as `.env` and
`tools/env_to_fsdata.py`, wired in as a `pre:` extra script, turns it back into
`data/*.json` inside the LittleFS image before `buildfs` packs it. Flashing with
`pio run -e <env> -t uploadfs` then puts the whole config back on the board.
`.env.example` documents every key.

Two things follow from this being a build step rather than a live import:

- `.env` is the source of truth for the image. It is regenerated from scratch on
  every build, so removing a group removes it from the image, and no `.env` at
  all means the firmware falls back to its own defaults.
- `uploadfs` writes the whole partition, so it erases anything the board saved
  at runtime. Export first if that matters.

Both `.env` and the generated `fsdata/data/` are gitignored, since they carry
WiFi and MQTT passwords in clear text.

## Troubleshooting

**Build pulls the wrong DMX backend, or a link error mentions Serial1**
Each backend file is guarded by an `ESP8266` / ESP32 macro, and PlatformIO
selects the toolchain from the environment. Build with an explicit environment,
for example `pio run -e s2mini`, rather than mixing artifacts.

**The web UI is blank or 404s, but the API works**
The assets were not flashed. Run `pio run -e <env> -t uploadfs` to write the
LittleFS image. A firmware upload alone does not include it.

**The page loads unstyled, and the stylesheet request shows a connection reset**
It should no longer be possible. The UI ships as **one** file: `tools/pack_web.py`
splices `web/style.css` and `web/app.js` into `web/index.html` at build time and
writes the result to the image, so a page load is a single request with nothing
left to race. The board answers one HTTP client at a time, and a subresource
that lost that race used to take the styling of the whole page with it.

`/style.css` and `/app.js` therefore return `404`: those files are not on the
board at all. Edit them in `web/` as usual and rebuild.

**Serial port opens but nothing answers**
The console is silent by design: it prints no banner, no prompt and no boot log,
and only ever replies to a command. Send `Help` and press Enter before
concluding it is dead. Beyond that, pick the board's own USB serial device rather
than a Bluetooth COM port, use 115200 baud, and make sure your terminal asserts
DTR on the ESP32-S2's native USB CDC port. `pio device monitor` does.

Note that the port number follows the firmware on the ESP32-S2, because the USB
PID changes with it. A board that was on one COM port under a different firmware
comes back on another one here.

**Opening the port fails with "access denied" / `PermissionError(13)`**
Something else already holds it, and COM ports are exclusive. The usual culprits
are a serial monitor left running in another terminal, or an editor extension
that reopens the port by itself, which is invisible in a process list because it
runs inside the editor. Stop every monitor, and unplug and replug the board if
that does not free it. The same clash makes `upload` and `uploadfs` fail, so
close the monitor before flashing.

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
