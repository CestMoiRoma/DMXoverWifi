# DMX over WiFi — Wiki

Reference for everything you drive from a keyboard: the serial console, the deploy
workflow, the HTTP API and the MQTT bridge.

See [README.md](README.md) for hardware, wiring and first-time setup.

- [Serial console](#serial-console)
  - [Opening a session](#opening-a-session)
  - [Command syntax](#command-syntax)
  - [Command reference](#command-reference)
- [Deploying](#deploying)
- [Filesystem write access](#filesystem-write-access)
- [HTTP API](#http-api)
- [MQTT and Home Assistant](#mqtt-and-home-assistant)
- [Timing and latency](#timing-and-latency)
- [Configuration files](#configuration-files)
- [Troubleshooting](#troubleshooting)

---

## Serial console

The board exposes a text console on its USB CDC serial port. It is polled from the
main loop, so it stays available while DMX is running — you can reconfigure a live
rig without a browser.

### Opening a session

`tools/serial_console.py` is a small cross-platform terminal built for this board.
It exists because it forces **DTR and RTS on**: GUI terminals (VS Code Serial
Monitor, PuTTY) have been unreliable with this device's native USB CDC port.

It needs [pyserial](https://pypi.org/project/pyserial/):

```bash
pip install pyserial
python tools/serial_console.py
```

Run with no arguments and it **lists the serial ports it can see and asks which
one to use**:

```
Detected serial ports:
  1. COM4 - Lien série sur Bluetooth standard (COM4)
  2. COM5 - Lien série sur Bluetooth standard (COM5)
  3. COM9 - Périphérique série USB (COM9)
Pick a number, or type a device path:
```

Pick the *USB serial device* — Bluetooth COM ports show up in the same list and
will just sit there silently. You can also pass the port (and baud rate) directly:

```bash
python tools/serial_console.py COM9                     # Windows
python tools/serial_console.py /dev/ttyACM0             # Linux
python tools/serial_console.py /dev/tty.usbmodem14201   # macOS
python tools/serial_console.py COM9 115200              # explicit baud
```

Both arguments are positional and optional: `serial_console.py [PORT] [BAUD]`.
Baud defaults to `115200` and is ignored by USB CDC anyway, but the API wants a
value.

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

The terminal waits ~500 ms after sending, then prints whatever came back. `exit`
closes the terminal only — the board keeps running.

> The board also exposes a **CIRCUITPY** mass-storage volume. That is a different
> interface from the serial port — the drive letter (`E:`) and the COM port
> (`COM9`) are unrelated, and ejecting the drive does not close the console.

### Command syntax

```
<Command> [subcommand] [key=value ...]
```

- **Commands and subcommands are case-insensitive** — `get-status`, `Get-Status`
  and `GET-STATUS` are the same.
- Arguments are `key=value`. **Values with spaces must be quoted**, single or
  double: `ssid="Guest Network"`.
- Values are otherwise taken literally, so no escaping is needed for `!`, `$`, etc.
- Passwords accept three spellings: `passwd=`, `psswd=` or `password=`.
- Every output line is prefixed with `OK `; failures come back as a single
  `ERR <reason>` line.

### Command reference

Type `Help` on the board for the built-in summary.

#### WiFi

| Command | What it does |
|---|---|
| `Add-Wifi ssid=<ssid> passwd=<password> [priority=<n>]` | Save a network **and immediately try to connect**. Higher priority wins at boot. Re-adding an SSID replaces its entry. |
| `Set-System wifi-add ssid=<ssid> passwd=<password> [priority=<n>]` | Same thing, under `Set-System`. |
| `Set-System wifi-del ssid=<ssid>` | Remove a saved network. |
| `Set-System wifi-list` | List visible networks (with RSSI) and saved ones (with priority). |

```
> Add-Wifi ssid="Venue WiFi" passwd="stage-left-2024" priority=10
OK wifi 'Venue WiFi' saved and connected
```

#### MQTT

| Command | What it does |
|---|---|
| `Add-mqtt broker=<host> user=<user> passwd=<password> [port=<n>]` | Enable MQTT, save the broker and connect. Port defaults to `1883`. |
| `Set-System mqtt-enable broker=<host> user=<u> passwd=<p> [port=<n>]` | Same thing, under `Set-System`. |
| `Set-System mqtt-disable` | Disable MQTT and disconnect. |

```
> Add-mqtt broker=192.168.1.20 user=dmx passwd=secret
OK mqtt enabled, broker=192.168.1.20
```

#### DMX pins

| Command | What it does |
|---|---|
| `Set-System tx-pin=<pin>` | Set the pin wired to the MAX485 `DI`. **Reboot to apply.** |
| `Set-System dir-pin enable=<true\|false> [pin=<pin>]` | Enable/disable the `DE`+`RE` direction pin and name it. **Reboot to apply.** |

The pin is a **CircuitPython `board` attribute name** (`D4`, `IO7`, …), not a
number. `enable=` accepts `true/1/yes/on` as true, anything else as false.

Leave the direction pin **disabled** if `DE`+`RE` are tied to VCC — that is the
default and matches the reference wiring.

```
> Set-System tx-pin=D4
OK dmx tx pin set to 'D4' (reboot to apply)
> Set-System dir-pin enable=true pin=D3
OK dir pin enabled (pin=D3) (reboot to apply)
```

#### Hotspot

| Command | What it does |
|---|---|
| `Set-System hotspot name=<name> passwd=<password>` | Rename the config AP / change its password. **Reboot to apply.** |

Defaults: SSID `ESP-DMX`, password `DMX4ALL1`, address `1.1.1.1`. The AP starts
automatically whenever no saved network can be joined, so the UI stays reachable
even with no infrastructure around.

#### Devices and channels

| Command | What it does |
|---|---|
| `Set-device add name=<name>` | Create a fixture. The **start channel is assigned automatically**, right after the last channel currently in use. |
| `Set-device add-channel device=<name> name=<ch> channel=<offset> mode=<slider\|bool>` | Add a channel to a fixture. `channel=` is the **offset within the fixture**, not the DMX address. |
| `Set-device del-channel name=<ch> [device=<name>]` | Remove a channel. If the name exists on several fixtures you must pass `device=`. |
| `Set-device del device=<name>` | Delete a fixture. |

`mode=` accepts `slider` (0-255 fader) or `bool` / `button` / `btn` / `boolean`
(fire-and-forget, sends 255). Anything else falls back to `slider`.

The DMX address actually driven is `start_channel + offset - 1`.

```
> Set-device add name="PAR LED"
OK device 'PAR LED' added (start channel 1)
> Set-device add-channel device="PAR LED" name=Dimmer channel=1 mode=slider
OK channel 'Dimmer' added to 'PAR LED' (offset 1, slider)
> Set-device add-channel device="PAR LED" name=Red channel=2 mode=slider
OK channel 'Red' added to 'PAR LED' (offset 2, slider)
```

#### Status

| Command | What it reports |
|---|---|
| `get-status` or `get-status all` | WiFi, MQTT, system pins, device/channel counts, free memory |
| `get-status wifi` | Mode (`sta`/`ap`), SSID, IP |
| `get-status mqtt` | Enabled, connected, broker |
| `get-status devices` | One line per fixture: start channel and channel count |
| `get-status device name=<name>` | Every channel of one fixture with its **current DMX value** |
| `get-status channel channel=<ch> [device=<name>]` | One channel's offset, mode and live value |
| `get-status mesh` | Stored mesh role and SSID (WIP) |

```
> get-status device name="PAR LED"
OK   1: Dimmer (slider) = 255
OK   2: Red (slider) = 200
```

#### Parent/Child mesh — WIP

| Command | What it does |
|---|---|
| `Set-System mesh role=<none\|parent\|child> [ssid=<>] [passwd=<>]` | **Stores the settings only.** No parent/child radio logic is implemented yet. |

#### Maintenance

| Command | What it does |
|---|---|
| `Help` | Print the built-in command summary |
| `Reboot` | Restart the board |
| `Set-System unlock-write` | Hand filesystem write access back to the PC until the next reboot — see below |

---

## Deploying

`tools/deploy.py` copies the firmware from this repo onto the board's `CIRCUITPY`
volume. Python only, no PowerShell, same command on every OS.

```bash
python tools/deploy.py E:\                        # Windows
python tools/deploy.py /Volumes/CIRCUITPY         # macOS
python tools/deploy.py /media/$USER/CIRCUITPY     # Linux
```

Run it **with no argument** and it asks where the volume is mounted, with a hint
for your platform:

```
Path to the CIRCUITPY drive (e.g. E:\ or L:\):
```

**It syncs** `boot.py`, `code.py`, `src/`, `www/` **and `lib/`** — so the vendored
CircuitPython libraries land on the board too and there is nothing to copy by
hand.

**It never touches `data/`**, your saved config, so deploying does not wipe your
WiFi credentials or fixtures.

Directories are wiped on the target before being copied, so files you deleted in
the repo really disappear instead of lingering. The script first writes a probe
file and **aborts with a clear message if the volume is read-only**.

Reboot the board when it finishes — CircuitPython does not reload from a host-side
copy on its own here. `Reboot` over serial does it without touching the hardware.

---

## Filesystem write access

CircuitPython lets exactly one side write to the filesystem — the microcontroller
or the USB host, never both. After a normal boot `boot.py` calls
`storage.remount("/", readonly=False)`, which gives write access **to the board**
so it can persist your WiFi, device and MQTT config as JSON. The flip side is that
`CIRCUITPY` is read-only from the PC, and `deploy.py` will refuse to run.

### Unlocking it for a deploy

The serial console is the way to hand write access back:

1. **Eject / safely remove** the `CIRCUITPY` volume. Keep the USB cable plugged —
   the console stays up. This step is not optional:

   ```
   > Set-System unlock-write
   ERR Cannot remount '/' when visible via USB.
   ```

2. Now unlock:

   ```
   > Set-System unlock-write
   OK filesystem is now PC-writable; CircuitPython can no longer save config until the next reboot
   ```

3. **Let the OS pick the volume back up.** Linux and macOS usually remount it on
   their own. On Windows the media stays "not present" after an eject, so trigger
   a rescan: *Device Manager → Action → Scan for hardware changes*, or `rescan` in
   an elevated `diskpart`.

4. `python tools/deploy.py`

5. `Reboot` over serial. The board comes back in its normal mode, owns the
   filesystem again, and runs the new code.

> [!WARNING]
> While unlocked, the board **cannot save its own config**. Anything you change
> through the web UI or the console in that window is lost on the next boot. Keep
> the unlock window short — unlock, deploy, reboot.

### On a fresh CircuitPython install

Before this firmware has ever run there is no `boot.py` to claim the filesystem,
so `CIRCUITPY` is writable straight away and you can deploy without unlocking
anything.

---

## HTTP API

Served on port 80 alongside the UI. JSON in, JSON out. **No authentication** —
keep the board on a network you trust.

### Devices

| Method | Route | Body / result |
|---|---|---|
| `GET` | `/api/devices` | List all fixtures with their channels |
| `POST` | `/api/devices` | `{"name":…, "start_channel":…, "channels":[{"offset":…,"name":…,"type":"slider"\|"button"}]}` → the created fixture |
| `PUT` | `/api/devices/<device_id>` | Any of `name`, `start_channel`, `channels` → the updated fixture, or `404` |
| `DELETE` | `/api/devices/<device_id>` | `{"ok": true\|false}` |
| `POST` | `/api/devices/<device_id>/channel/<offset>` | `{"value": 0-255}` → `{"ok": true}`, or `404` |

Setting a channel writes the DMX buffer straight away and mirrors the value to
MQTT. Values are clamped to 0-255.

### WiFi

| Method | Route | |
|---|---|---|
| `GET` | `/api/wifi` | Saved networks |
| `POST` | `/api/wifi` | `{"ssid":…, "password":…, "priority":…}` → updated list |
| `DELETE` | `/api/wifi/<ssid>` | → updated list |
| `GET` | `/api/wifi/scan` | Visible networks: `[{"ssid":…, "rssi":…}]` |

`POST /api/wifi` saves without connecting — unlike the serial `Add-Wifi`.

### MQTT, system, mesh

| Method | Route | |
|---|---|---|
| `GET` / `POST` | `/api/mqtt` | Read / merge MQTT config; a `POST` also restarts the client |
| `GET` / `POST` | `/api/system` | Read / merge `system.json` (pins, hostname, hotspot) |
| `GET` / `POST` | `/api/mesh` | Read / merge `mesh.json` (**WIP, stored only**) |

`POST` merges into the existing config, so you can send a single key.

```bash
curl http://192.168.1.98/api/devices
curl -X POST http://192.168.1.98/api/devices/dev-a1b2c3/channel/1 \
     -H "Content-Type: application/json" -d '{"value":128}'
```

---

## MQTT and Home Assistant

MQTT is optional and **only starts when the board is on a real network** (station
mode) — not on its own hotspot.

| Setting | Default |
|---|---|
| `base_topic` | `dmxwifi` |
| `discovery_prefix` | `homeassistant` |
| `port` | `1883` |

Every channel gets a unique id of `<device_id>_<offset>`, e.g. `dev-a1b2c3_1`.

### Topics

| Topic | Direction | Payload |
|---|---|---|
| `<base_topic>/<uid>/set` | in | Slider: a number `0`-`255`. Button: **any payload fires 255**. |
| `<base_topic>/<uid>/state` | out | Current value, sliders only |

### Discovery

On connect — and whenever fixtures change — the board publishes **retained**
discovery configs:

| Channel type | Discovery topic | Entity |
|---|---|---|
| `slider` | `<discovery_prefix>/number/<uid>/config` | `number`, min 0, max 255, step 1 |
| `button` | `<discovery_prefix>/button/<uid>/config` | `button` |

All channels of a fixture share one `device` block (identified by the device id,
manufacturer `DIY`, model `DMX-over-WiFi`), so Home Assistant groups them as one
device.

---

## Timing and latency

> [!WARNING]
> **The delay between a command and the fixture reacting is not guaranteed.** It
> varies, and it can spike. Don't put this box anywhere a late or dropped cue
> matters.

The chain is `browser or MQTT → WiFi → HTTP/MQTT handler → DMX buffer → next DMX
frame`, and only the last hop has anything like a fixed cost.

| Stage | Behaviour |
|---|---|
| WiFi | Best-effort. Retries, interference, a busy AP or a roaming client add tens to hundreds of ms, unpredictably |
| MQTT | Adds a broker round-trip; a reconnect blocks the loop while it happens |
| Main loop | `code.py` polls HTTP, MQTT, the DMX refresh and the serial console in one `while True`. No pre-emption, no priorities — a slow request delays the next frame |
| CircuitPython | Interpreted, and the garbage collector can pause the loop at any point |
| DMX frame | `FRAME_INTERVAL = 0.025` is checked from the loop with `time.monotonic()`, not driven by a timer interrupt. The break is generated by re-opening the UART at 83333 baud, so its width depends on how fast that call returns |

What *is* dependable: once a value is in the buffer it keeps going out at roughly
40 fps, so fixtures hold state and don't flicker. It is the *arrival* of a new
value that has no deadline.

Practical consequences:

- Fine for setting levels, static looks, colour changes, house lights, ambience.
- Not for anything that has to land on a beat, and not for pyro, moving trusses or
  anything safety-related.
- Chases and effects should be generated **on the fixture** (built-in programs)
  rather than streamed channel-by-channel from a browser.

If you need deterministic timing, drive the rig from a real DMX desk or an
Art-Net/sACN node on a wired network.

---

## Configuration files

The board writes its state as JSON under `/data` on `CIRCUITPY`. The directory is
**git-ignored** — it contains WiFi and MQTT passwords in clear text. Missing files
are recreated from defaults on first read.

| File | Holds | Default |
|---|---|---|
| `wifi_networks.json` | `[{ssid, password, priority}]` | `[]` |
| `devices.json` | `[{id, name, start_channel, channels[]}]` | `[]` |
| `mqtt.json` | `enabled, host, port, username, password, base_topic, discovery_prefix` | disabled, `dmxwifi` / `homeassistant` |
| `system.json` | `dmx_tx_pin, dmx_dir_pin_enabled, dmx_dir_pin, hostname, ap_ssid, ap_password, ap_ip` | `D4`, direction pin off, `D3`, `ESP-DMX`, `ESP-DMX`, `DMX4ALL1`, `1.1.1.1` |
| `mesh.json` | `role, ssid, password` | `none` (**WIP**) |

To wipe a setting back to defaults, delete its file while the filesystem is
unlocked, then reboot.

---

## Troubleshooting

**`deploy.py` says the target is read-only**
The board owns the filesystem. Follow
[Unlocking it for a deploy](#unlocking-it-for-a-deploy).

**`ERR Cannot remount '/' when visible via USB`**
`Set-System unlock-write` was sent while the `CIRCUITPY` volume was still mounted.
Eject it first, then send the command again.

**The drive never comes back after ejecting it**
Windows leaves the media "not present" until something rescans. *Device Manager →
Action → Scan for hardware changes*, or `rescan` in an elevated `diskpart`. A
`Reboot` over serial also brings it back, but that re-locks the filesystem.

**Serial port opens but nothing answers**
Make sure you picked the board's USB CDC port (`COM9`-style *USB serial device*,
not a Bluetooth COM port) and that you are using `tools/serial_console.py` — it
forces DTR/RTS, which some terminals don't.

**Pin change had no effect**
`tx-pin` and `dir-pin` are only read at startup. Reboot.

**`ERR` on a pin name**
It must be a CircuitPython `board` attribute for your board (`D4`, `IO7`, …).
A wrong name raises at boot, in the `DmxDriver` constructor.

**Config changes don't survive a reboot**
The filesystem was unlocked with `unlock-write`, so CircuitPython has no write
access. Reboot first, then change settings.

**A cue arrived late, or a slider felt sluggish**
Expected — see [Timing and latency](#timing-and-latency). There are no delivery or
timing guarantees.

**Can't reach the UI**
Check `get-status wifi` over serial. `mode=ap` means it fell back to its hotspot:
join `ESP-DMX` and browse to <http://1.1.1.1>.

**Fixture responds on the wrong DMX address**
The address is `start_channel + offset - 1`. A fixture at start channel 10 with a
channel at offset 1 drives DMX address 10, not 11.

**MQTT never connects**
It only starts in station mode, and only if `enabled` is set with a non-empty
host. Check with `get-status mqtt`.
