# DMX over WiFi: wiki

Reference for everything you drive from a keyboard: the serial console, the
deploy workflow, the HTTP API, the MQTT bridge and the test suite.

See [README.md](README.md) for hardware, wiring and first-time setup.

- [Serial console](#serial-console)
  - [Opening a session](#opening-a-session)
  - [Command syntax](#command-syntax)
  - [Command reference](#command-reference)
- [Deploying](#deploying)
- [The .env file](#the-env-file)
- [Filesystem write access](#filesystem-write-access)
- [Channel types](#channel-types)
- [HTTP API](#http-api)
- [MQTT and Home Assistant](#mqtt-and-home-assistant)
- [Timing and latency](#timing-and-latency)
- [Test suite](#test-suite)
- [Configuration files](#configuration-files)
- [Troubleshooting](#troubleshooting)

## Serial console

The board exposes a text console on its USB serial port. It is polled from the
main loop, so it stays available while DMX is running and you can reconfigure a
live rig without a browser.

### Opening a session

`tools/serial_console.py` is a small cross-platform terminal built for this
board. It exists because it forces DTR and RTS on, which GUI terminals such as
the VS Code Serial Monitor and PuTTY have been unreliable about with this
device's native USB CDC port.

It needs [pyserial](https://pypi.org/project/pyserial/):

```bash
pip install pyserial
python tools/serial_console.py
```

Run it with no arguments and it lists the serial ports it can see, then asks
which one to use:

```
Detected serial ports:
  1. COM4 - Standard Serial over Bluetooth link (COM4)
  2. COM5 - Standard Serial over Bluetooth link (COM5)
  3. COM9 - USB Serial Device (COM9)
Pick a number, or type a device path:
```

Pick the USB serial device. Bluetooth ports show up in the same list and will
just sit there silently. You can also pass the port, and a baud rate, directly:

```bash
python tools/serial_console.py COM9                     # Windows
python tools/serial_console.py /dev/ttyACM0             # Linux
python tools/serial_console.py /dev/tty.usbmodem14201   # macOS
python tools/serial_console.py COM9 115200              # explicit baud
```

Both arguments are positional and optional. Baud defaults to `115200` and is
ignored by USB CDC anyway, but the API wants a value.

#### Using it

```
Connected to COM9 at 115200 baud. Type a command and press Enter.
Type 'exit' to quit this terminal (does not reset the board).

> get-status
OK wifi: mode=sta ssid=NoctiIOT ip=192.168.1.98
OK mqtt: enabled=False connected=False broker=
OK system: hostname=ESP-DMX tx_pin=D4 dir_pin=disabled
OK devices: 0 device(s), 0 channel(s)
OK memory: 1946528 bytes free
> exit
Disconnected.
```

The terminal waits about half a second after sending, then prints whatever came
back. `exit` closes the terminal only, and the board keeps running.

> The board also exposes a `CIRCUITPY` mass-storage volume. That is a different
> interface from the serial port. The drive letter and the COM port are
> unrelated, and ejecting the drive does not close the console.

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

The pin is a CircuitPython `board` attribute name such as `D4` or `IO7`, not a
number. `enable=` treats `true`, `1`, `yes` and `on` as true, and anything else
as false.

Leave the direction pin disabled if `DE` and `RE` are tied to VCC. That is the
default, and it matches the reference wiring.

```
> Set-System tx-pin=D4
OK dmx tx pin set to 'D4' (reboot to apply)
> Set-System dir-pin enable=true pin=D3
OK dir pin enabled (pin=D3) (reboot to apply)
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

#### Filesystem and reboots

| Command | What it does |
|---|---|
| `Set-System reboot-config` | Arm config mode and reset. The board comes back with the filesystem writable from the PC. This is what `deploy.py` uses. |
| `Set-System unlock-write` | Hand write access to the host without rebooting. Requires the host to have ejected the drive first. |
| `Reboot` | Restart the board. |

See [Filesystem write access](#filesystem-write-access).

#### Parent and child mesh, work in progress

| Command | What it does |
|---|---|
| `Set-System mesh role=<none\|parent\|child> [ssid=<>] [passwd=<>]` | Stores the settings only. No parent or child radio logic exists yet. |

#### Other

| Command | What it does |
|---|---|
| `Help` | Print the built-in command summary |

## Deploying

`tools/deploy.py` copies the firmware from this repo onto the board's
`CIRCUITPY` volume. Python only, and the same command on every OS.

```bash
python tools/deploy.py                            # asks where the drive is
python tools/deploy.py E:/ --port COM9 --force    # Windows, nothing to answer
python tools/deploy.py /Volumes/CIRCUITPY         # macOS
python tools/deploy.py /media/$USER/CIRCUITPY     # Linux
```

The script finds the repo from its own location, so it does not care what
directory you run it from. `python deploy.py E:/ --port COM9 --force` from inside
`tools/` is the same command.

It syncs `boot.py`, `code.py`, `src/`, `www/` and `lib/`, so the vendored
CircuitPython libraries land on the board too and there is nothing to copy by
hand. It also drops a copy of `WIKI.md` into `www/wiki.md`, which is what the
Info page's offline wiki link serves.

It never touches `data/`, your saved config, so deploying does not wipe your
WiFi credentials or fixtures.

Directories are wiped on the target before being copied, so files you deleted in
the repo really disappear instead of lingering.

### Unlocking happens automatically

After the firmware has run once, the board owns the filesystem and `CIRCUITPY`
is read-only from the PC. `deploy.py` notices and handles it:

1. Asks which serial port the board is on, unless you passed `--port`.
2. Ejects the drive from the host.
3. Sends `Set-System reboot-config`, which resets the board into config mode.
4. Waits for the drive to come back writable, then copies.
5. Sends `Reboot`, so the board returns to normal mode running the new code.

If the board is running firmware old enough not to know `reboot-config`, the
script falls back to arming the marker through the raw REPL.

The final reboot happens whether or not the script did the unlocking, because a
drive that was already writable usually means a previous run left the board in
config mode. It needs a port to do that, so passing `--port` is worth it even
when the drive is unlocked. Without one the script says so and leaves the board
alone, which is harmless on a first flash since CircuitPython starts the new code
by itself.

Pass `--no-reboot` to leave the board in config mode after the copy, which is
handy when you are about to deploy again.

### Options

| Flag | Effect |
|---|---|
| `--port PORT` | Serial port, only needed when the drive is locked |
| `--no-reboot` | Skip the final reboot and stay in config mode |
| `--force` (also `--reset-config`) | Overwrite `data/*.json` from `.env` instead of only filling in what is missing |

### Preloading settings

`deploy.py` can seed the board's config from a `.env` file at the repo root, so a
freshly flashed box comes up already knowing your networks, your broker and your
fixtures. See [The .env file](#the-env-file) for the full reference.

## The .env file

`.env` lives at the repo root, next to `tools/`. It is **gitignored**, because it
holds passwords in clear text. `.env.example` is the committed template.

Two ways to get one:

- Copy `.env.example` and fill it in by hand.
- Configure a board through the web UI, then press **Export .env** under
  **Settings**, **Configuration**. That writes every key the board knows about,
  which is the reliable way to get a complete file.

### Syntax

```
# comments start with a hash
KEY=value
QUOTED="value with spaces"
```

The parser is deliberately small:

- One `KEY=value` per line.
- Blank lines and lines starting with `#` are ignored, as is any line with no
  `=` in it.
- A single or double quote pair around the value is stripped. Quotes are only
  needed for values with leading or trailing spaces.
- Everything after the first `=` is the value, so `MQTT_PASSWORD=a=b=c` works.
- No variable expansion, no `export` prefix, no multi-line values. A `#` partway
  through a line is part of the value, not a comment.

### Numbered groups

WiFi networks and fixtures repeat, so they carry a number: `WIFI_1_*`,
`WIFI_2_*`, and `DEVICE_1_*`, `DEVICE_2_*`. Channels are numbered inside their
fixture: `DEVICE_1_CHANNEL_1_*`.

The numbers only group keys together and order them. They do not have to start
at 1 or be contiguous, and they sort numerically, so `WIFI_10` comes after
`WIFI_2` rather than after `WIFI_1`.

A WiFi group with no `SSID` is dropped, as is a device group with no `NAME`.

### WiFi

| Key | Default | Meaning |
|---|---|---|
| `WIFI_<n>_SSID` | required | Network name. Without it the whole group is skipped |
| `WIFI_<n>_PASSWORD` | empty | Leave empty for an open network |
| `WIFI_<n>_PRIORITY` | `0` | Higher wins when the board picks a network at boot. Anything not a number counts as 0 |

### MQTT

Present only if at least one `MQTT_` key is in the file. Otherwise `mqtt.json` is
not touched at all.

| Key | Default | Meaning |
|---|---|---|
| `MQTT_ENABLED` | `false` | Whether the bridge starts. Only runs once the board is on a real network |
| `MQTT_HOST` | empty | Broker address. Empty means the bridge stays off whatever `MQTT_ENABLED` says |
| `MQTT_PORT` | `1883` | |
| `MQTT_USERNAME` | empty | |
| `MQTT_PASSWORD` | empty | |
| `MQTT_BASE_TOPIC` | `dmxwifi` | Prefix for the `set` and `state` topics |
| `MQTT_DISCOVERY_PREFIX` | `homeassistant` | Where Home Assistant looks for discovery configs |

### DMX, hotspot and static IP

These all live in `system.json`, so they are one group. Naming any one of them
means the whole file gets written.

| Key | Default | Meaning |
|---|---|---|
| `DMX_TX_PIN` | `D4` | CircuitPython `board` pin wired to the MAX485 `DI` |
| `DMX_DIR_PIN_ENABLED` | `false` | Leave off when `DE` and `RE` are tied to VCC |
| `DMX_DIR_PIN` | `D3` | Pin driving `DE` and `RE`, used only when the above is on |
| `HOSTNAME` | `ESP-DMX` | |
| `AP_SSID` | `ESP-DMX` | Config hotspot name |
| `AP_PASSWORD` | `DMX4ALL1` | Empty makes the hotspot open |
| `AP_IP` | `1.1.1.1` | Address the board serves the UI on in hotspot mode |
| `STA_IP_MODE` | `dhcp` | `dhcp` or `static` |
| `STA_STATIC_IP` | empty | Only used when the mode is `static` |
| `STA_STATIC_NETMASK` | `255.255.255.0` | |
| `STA_STATIC_GATEWAY` | empty | Required for static mode, along with the address |
| `STA_STATIC_DNS` | `1.1.1.1` | Optional |

A static address is applied after joining a network, and only when the mode is
`static` **and** both an address and a gateway are set. Values that do not parse
are ignored and the board stays on DHCP, so a typo costs you a fixed address but
never the network.

### Parent and child mesh

Stored only, no behaviour yet.

| Key | Default |
|---|---|
| `MESH_ROLE` | `none`, or `parent` or `child` |
| `MESH_SSID` | empty |
| `MESH_PASSWORD` | empty |

### Fixtures

| Key | Default | Meaning |
|---|---|---|
| `DEVICE_<n>_NAME` | required | Fixture name. Without it the group is skipped |
| `DEVICE_<n>_START_CHANNEL` | `1` | First DMX address of the fixture |
| `DEVICE_<n>_CHANNEL_<m>_OFFSET` | `<m>` | Offset inside the fixture, so the DMX address is `START_CHANNEL + OFFSET - 1` |
| `DEVICE_<n>_CHANNEL_<m>_NAME` | `Channel <m>` | Label shown on the Home page |
| `DEVICE_<n>_CHANNEL_<m>_TYPE` | `slider` | One of `slider`, `button`, `button-momentary`, `button-switch` |

Channel types here are the exact stored names, not the serial console's
shorthands. `toggle` will not work, `button-switch` will.

```
DEVICE_1_NAME=Studio Par
DEVICE_1_START_CHANNEL=1
DEVICE_1_CHANNEL_1_OFFSET=1
DEVICE_1_CHANNEL_1_NAME=Dimmer
DEVICE_1_CHANNEL_1_TYPE=slider
DEVICE_1_CHANNEL_2_OFFSET=2
DEVICE_1_CHANNEL_2_NAME=Heater
DEVICE_1_CHANNEL_2_TYPE=button-switch
```

### What a deploy does with it

Default behaviour is deliberately cautious:

- **WiFi entries are merged.** New SSIDs are appended, and ones the board already
  knows are left exactly as they are, password and priority included.
- **Every other group is only written when its file is missing**, so redeploying
  does not undo changes you made through the UI.
- **A group with no keys in `.env` is never written**, with or without `--force`.
  An `.env` holding only `WIFI_` entries cannot touch your fixtures.

`--force` overrides the first two and rewrites from `.env`.

> [!WARNING]
> **`--force` resets keys your `.env` never mentions.** Each group is written
> whole. As soon as one `MQTT_` key, one system key or one `MESH_` key is
> present, the entire file is rebuilt and anything absent from `.env` goes back
> to its shipping default instead of staying as it is on the board.
>
> The usual way to get bitten: an `.env` that sets `DMX_TX_PIN` and `AP_SSID` but
> no `STA_` keys. Deploy with `--force` and a board you had pinned to a static
> address quietly returns to DHCP, so it comes up on a different address.
>
> If you deploy with `--force` habitually, keep `.env` complete. Press
> **Export .env** and use that file.

### Exporting from a board

**Settings**, **Configuration**, **Export .env**, or fetch `/api/export-env`
directly. Drop the result next to `tools/deploy.py` as `.env` and the next flash
starts from exactly that state, which makes it a quick way to clone a working box
or to snapshot one before experimenting.

The export covers saved networks, MQTT, the whole system group including static
IP, mesh settings and every fixture with its channels. It writes the keys
`deploy.py` reads, and the suite checks that round trip, so nothing is lost on
the way back.

## Filesystem write access

CircuitPython lets exactly one side write to the filesystem, the microcontroller
or the USB host, never both. After a normal boot `boot.py` calls
`storage.remount("/", readonly=False)`, which gives write access to the board so
it can persist your WiFi, fixture and MQTT config as JSON. The consequence is
that `CIRCUITPY` is read-only from the PC.

The board decides which mode to boot into from a marker byte in
`microcontroller.nvm`:

| | Normal boot | Config mode |
|---|---|---|
| How you get there | Power up or reset | `Set-System reboot-config`, or `deploy.py` doing it for you |
| `CIRCUITPY` from the PC | Read-only | Writable |
| Board saves its own config | Yes | No |
| WiFi | Joins a saved network, hotspot as fallback | Starts the hotspot immediately |
| Lasts | Until the next reset | One boot, the marker is consumed |

Every step is wrapped in a fallback, so a failure in mode detection cannot brick
the board. A board whose partition table has no NVM region simply always boots
normally.

> [!WARNING]
> In config mode the board **cannot save its own config**. Anything you change
> through the web UI or the console in that window is lost on the next boot.
> Deploy, then reboot.

### Doing it by hand

You should not need to, since `deploy.py` handles it, but the two commands are
there:

```
> Set-System reboot-config
OK entering config mode via reset
```

The board resets and comes back with the drive writable.

```
> Set-System unlock-write
OK filesystem is now PC-writable; CircuitPython can no longer save config until the next reboot
```

This one remounts live, without a reset, and it fails if the host still has the
volume mounted:

```
> Set-System unlock-write
ERR Cannot remount '/' when visible via USB.
```

Eject the drive first, then send it again. On Windows the volume then stays
absent until something rescans, so use *Device Manager*, *Action*, *Scan for
hardware changes*, or `rescan` in an elevated `diskpart`. This is exactly the
awkwardness `reboot-config` exists to avoid.

### On a fresh CircuitPython install

Before this firmware has ever run there is no `boot.py` to claim the filesystem,
so `CIRCUITPY` is writable straight away and the first deploy needs none of the
above.

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

### Pages

| Method | Route | |
|---|---|---|
| `GET` | `/` | The single-page web UI |
| `GET` | `/wiki.md` | This document, as served from the board |

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
| Main loop | `code.py` polls HTTP, MQTT, the DMX refresh and the serial console in one `while True`. No preemption and no priorities, so a slow request delays the next frame |
| CircuitPython | Interpreted, with a garbage collector that can pause the loop at any point |
| DMX frame | `FRAME_INTERVAL` is 25 ms, checked from the loop with `time.monotonic()` rather than driven by a timer interrupt. The break is generated by reopening the UART at 83333 baud, so its width depends on how fast that call returns |

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

## Test suite

`test/` holds scripts that check the firmware works **before it goes on the
board**. Nothing there ships to the ESP32 and nothing needs hardware.

This suite is under constant development. It grows with the firmware, so every
feature that lands should arrive with the tests that prove it, and every bug that
gets fixed should leave a test behind so it cannot come back. Expect it to look
different in a month.

### Running it

```bash
docker compose -f test/docker-compose.yml run --rm tests
```

| Service | Runs |
|---|---|
| `tests` | Everything, firmware and browser |
| `unit` | Firmware only, no browser, fast enough to run while editing `src/` |
| `ui` | The browser tests only |
| `screenshots` | Rewrites `docs/images/ui-*.png` from the mock board |

Without Docker, on Python 3.11 or newer:

```bash
pip install -r test/requirements.txt
playwright install chromium        # only for the browser tests
python -m pytest test -v
```

Without playwright the browser tests skip and everything else still runs.

### The fake ESP32

`test/fake_esp32/` provides stand-ins for the CircuitPython modules the firmware
imports: `board`, `busio`, `digitalio`, `microcontroller`, `storage`, `usb_cdc`,
`wifi`, `socketpool`, `adafruit_httpserver` and `adafruit_minimqtt`. Putting that
directory on `sys.path` makes `import board` resolve there instead of failing, so
`src/` runs unmodified on a desktop Python.

They are not emulators. They record what the firmware did to them and let a test
feed values back in. The fake radio, for example, is told which networks exist
and with what password, so the priority ordering and the hotspot fallback are
exercised for real rather than mocked out.

Real standard library modules are deliberately not stubbed. `os`, `json`, `time`
and `ipaddress` all exist on CPython with the API the firmware uses.

### What it covers

| File | Area |
|---|---|
| `test_settings_store.py` | JSON config under `/data`, defaults, recovery from a corrupt file |
| `test_dmx_driver.py` | Buffer, clamping, break and mark-after-break, refresh rate, direction pin |
| `test_devices.py` | Fixtures, all four channel types, DMX address mapping, persistence |
| `test_wifi_manager.py` | Saved networks, priority ordering, static IP, hotspot fallback |
| `test_mqtt_manager.py` | Connection lifecycle, discovery payloads, command handling |
| `test_serial_console.py` | Every serial command, its arguments and its error paths |
| `test_web_api.py` | Every HTTP route the web UI calls |
| `test_boot.py` | Which side owns the filesystem after boot |
| `test_integration.py` | The whole stack wired the way `code.py` wires it |
| `test_deploy_tool.py` | `.env` parsing and seeding in `tools/deploy.py`, the shipped `.env.example`, and the per-platform eject commands |
| `test_serial_tool.py` | The port picker in `tools/serial_console.py` |
| `test_ui.py` | The real web UI in a real browser, against a mock board |

The deploy tests matter more than they look. That script decides what lands in
`data/*.json` on the target, so a regression there either wipes a saved config or
silently fails to seed a fresh flash, and neither shows up until the board is in
your hands. They also assert that the keys `deploy.py` writes are exactly the
keys `settings_store` expects, so the two cannot drift apart.

### The mock board

`test/ui/mock_server.py` serves the real `www/` files backed by a fake API with
demo fixtures covering every channel type. Run it on its own to poke at the UI in
a browser with no hardware attached:

```bash
python test/ui/mock_server.py --port 8000
```

`test/ui/screenshot_ui.py` drives the same mock board to regenerate the
screenshots in `docs/images/`. They therefore always show a populated UI and
never leak a real WiFi list.

### One trap worth knowing about

The repo root holds `code.py`, the firmware entry point. On CPython that name
shadows the standard library's `code` module, which `pdb` imports, which pytest
imports at startup. Left alone, starting pytest runs the firmware and hangs in
its main loop. `test/conftest.py` drops the repo root from the front of
`sys.path`, pins the real module, and only then puts the repo root back at the
end. If you ever see pytest produce no output at all, that guard is the first
thing to check.

### Adding to it

New firmware feature: add its tests next to the module they cover, and if it
touches the web UI add a browser test too.

New CircuitPython import in `src/`: add a stub in `test/fake_esp32/`. Keep it as
thin as the firmware needs but no thinner, since a stub that accepts calls the
real hardware would reject makes the suite lie.

## Configuration files

The board writes its state as JSON under `/data` on `CIRCUITPY`. The directory is
gitignored, because it contains WiFi and MQTT passwords in clear text. Missing
files are recreated from defaults on first read, and a corrupt file is replaced
rather than left to fail again on the next boot.

| File | Holds |
|---|---|
| `wifi_networks.json` | `[{ssid, password, priority}]` |
| `devices.json` | `[{id, name, start_channel, channels[]}]` |
| `mqtt.json` | `enabled`, `host`, `port`, `username`, `password`, `base_topic`, `discovery_prefix` |
| `system.json` | `dmx_tx_pin`, `dmx_dir_pin_enabled`, `dmx_dir_pin`, `hostname`, `ap_ssid`, `ap_password`, `ap_ip`, `sta_ip_mode`, `sta_static_ip`, `sta_static_netmask`, `sta_static_gateway`, `sta_static_dns` |
| `mesh.json` | `role`, `ssid`, `password` (work in progress) |

Shipping defaults: DMX TX on `D4`, direction pin disabled on `D3`, hostname and
hotspot SSID `ESP-DMX`, hotspot password `DMX4ALL1`, hotspot address `1.1.1.1`,
DHCP, MQTT disabled with base topic `dmxwifi`.

Static IP is applied after joining a network, and only when `sta_ip_mode` is
`static` and both an address and a gateway are set. If the values do not parse,
the board stays on DHCP rather than dropping off the network.

To wipe a setting back to defaults, delete its file while the filesystem is
unlocked, then reboot. Or set it in `.env` and deploy with `--reset-config`.

## Troubleshooting

**pytest produces no output and never finishes**
See [the trap above](#one-trap-worth-knowing-about). Something put the repo root
early on `sys.path` and pytest is running the firmware.

**`deploy.py` cannot unlock the drive**
It needs pyserial and the right serial port. Pass `--port` explicitly. If the
board is running very old firmware, the raw REPL fallback needs the board to be
at the REPL rather than running `code.py`.

**`ERR Cannot remount '/' when visible via USB`**
`Set-System unlock-write` was sent while the volume was still mounted. Eject it
first, or just use `Set-System reboot-config` instead.

**The drive never comes back after ejecting it**
Windows leaves the media absent until something rescans. Use *Device Manager*,
*Action*, *Scan for hardware changes*, or `rescan` in an elevated `diskpart`. A
`Reboot` over serial also brings it back, though that re-locks the filesystem.

**Serial port opens but nothing answers**
Make sure you picked the board's USB serial device rather than a Bluetooth COM
port, and that you are using `tools/serial_console.py`, which forces DTR and RTS.

**A pin change had no effect**
`tx-pin` and `dir-pin` are only read at startup. Reboot.

**`ERR` on a pin name**
It must be a CircuitPython `board` attribute for your board, such as `D4` or
`IO7`. A wrong name raises at boot, inside the `DmxDriver` constructor.

**Config changes do not survive a reboot**
The board is in config mode, or the filesystem was unlocked with
`unlock-write`, so CircuitPython has no write access. Reboot first, then change
settings.

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
