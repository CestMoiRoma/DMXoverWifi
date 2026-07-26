# Serial console

[Wiki index](../../WIKI.md)

The board exposes a text console on its serial port. It is polled from the main
loop, so it stays available while DMX is running and a live rig can be
reconfigured with no browser anywhere.

- On the **ESP32-S2** it is the native USB CDC port (`Serial`).
- On the **ESP8266** it is UART0, through the board's USB-to-serial chip.

DMX output uses a different UART on both, so the console never collides with it.

With WiFi switched off entirely, this is the whole interface. See
[Configuration](configuration.md).

## Opening a session

Any terminal at **115200 baud**. PlatformIO ships one:

```bash
pio device monitor -e s2mini      # or -e d1mini
```

Type a command and press Enter. On the ESP32-S2's native USB port some GUI
terminals need DTR asserted before the port answers; `pio device monitor` does
that for you.

```
> get-status
OK wifi: mode=sta ssid=NoctiIOT ip=192.168.1.98
OK mqtt: enabled=True connected=True broker=192.168.1.20:1883 entities=29 attempts=1
OK system: hostname=ESP-DMX tx_pin=IO4 dir_pin=disabled
OK devices: 3 device(s), 27 channel(s)
OK memory: 101964 bytes free
```

The console prints no banner, no prompt and no boot log. It only ever answers a
command, so silence on connecting is correct rather than a fault.

## Syntax

```
<Command> [subcommand] [key=value ...]
```

- Commands and subcommands are case insensitive.
- Arguments are `key=value`. Values with spaces need quotes, single or double:
  `ssid="Guest Network"`.
- Values are otherwise literal, so nothing needs escaping.
- Passwords accept three spellings: `passwd=`, `psswd=` or `password=`.
- Every output line begins `OK `. Failures come back as one `ERR <reason>` line.

## WiFi

| Command | What it does |
|---|---|
| `Add-Wifi ssid=<ssid> passwd=<password> [priority=<n>]` | Save a network and try to join it now. Higher priority wins at boot. Re-adding an SSID replaces its entry |
| `Set-System wifi-add …` | The same, under `Set-System` |
| `Set-System wifi-del ssid=<ssid>` | Remove a saved network |
| `Set-System wifi-list` | Visible networks with signal strength, saved ones with priority |

```
> Add-Wifi ssid="Venue WiFi" passwd="stage-left-2026" priority=10
OK wifi 'Venue WiFi' saved and connected
```

The reply says `saved` on its own when the network could not be joined, which
usually means out of range or a wrong password. The entry is stored either way.

## MQTT

| Command | What it does |
|---|---|
| `Add-mqtt broker=<host> user=<user> passwd=<password> [port=<n>]` | Enable MQTT, save the broker and connect. Port defaults to 1883 |
| `Set-System mqtt-enable …` | The same, under `Set-System` |
| `Set-System mqtt-disable` | Disable and disconnect |

`get-status mqtt` is where to look when it does not work: it reports the broker,
the entity count, how many attempts have been made and, on a second line, why the
last one ended. See [MQTT](mqtt.md).

## DMX pins

| Command | What it does |
|---|---|
| `Set-System tx-pin=<pin>` | The pin wired to the MAX485 `DI`. Reboot to apply |
| `Set-System dir-pin enable=<true\|false> [pin=<pin>]` | Enable or disable the `DE`/`RE` direction pin and name it. Reboot to apply |

Pins are raw GPIO numbers with an optional cosmetic prefix: `IO4`, `GPIO4` and
`4` are the same pin. `enable=` treats `true`, `1`, `yes` and `on` as true and
anything else as false.

> On the ESP8266 the output is fixed to `Serial1` (GPIO2), so `tx-pin` is stored
> and has no effect there. The direction pin still works.

## Hotspot and USB-only mode

| Command | What it does |
|---|---|
| `Set-System hotspot name=<name> passwd=<password>` | Rename the config access point or change its password. Reboot to apply |
| `Set-System wifi-toggle on\|off` | Turn the radio on or off for the next boot |

Defaults come from [dev.env](../../dev.env): SSID `ESP-DMX`, password `DMX4ALL1`,
address `1.1.1.1`. The hotspot starts whenever no saved network can be joined, so
the UI stays reachable with no infrastructure around.

With WiFi off the radio never comes up, and the web server, mDNS and MQTT never
start with it. A rig driven from a laptop over USB has no reason to broadcast.

## Driving channels

| Command | What it does |
|---|---|
| `Set-Value channel=<name> [device=<name>] value=<0-255>` | Drives every channel with that name, or only the one on the named fixture |
| `Set-Value address=<1-512> value=<0-255>` | Writes a raw DMX slot, bypassing the fixture model |

`address=` is the probe form. It answers "which slot does this projector actually
listen on" without a fixture defined first, which is how you find out what a
fixture really does when its manual disagrees.

## Fixtures and channels

| Command | What it does |
|---|---|
| `Set-device add name=<name> [channel=<start>] [category=<id>]` | Create a fixture. Without `channel=` the start channel lands after the last address in use |
| `Set-device add-channel device=<name> name=<ch> channel=<offset> mode=<mode>` | Add a channel. `channel=` is the offset within the fixture, not the DMX address |
| `Set-device del-channel name=<ch> [device=<name>]` | Remove a channel. Pass `device=` if the name exists on several |
| `Set-device del device=<name>` | Delete a fixture |

`mode=` takes any alias from [Channel types](lite-devices.md#channel-types), and
anything unrecognised falls back to `slider`.

## Status

| Command | What it reports |
|---|---|
| `get-status` or `get-status all` | WiFi, MQTT, pins, fixture and channel counts, free memory |
| `get-status wifi` | Mode (`sta` or `ap`), SSID, address |
| `get-status mqtt` | Enabled, connected, broker, entities, attempts, and why the last attempt ended |
| `get-status devices` | One line per fixture with its start channel and channel count |
| `get-status device name=<name>` | Every channel of one fixture with its live value |
| `get-status channel channel=<ch> [device=<name>]` | One channel's offset, mode and value |
| `get-status mesh` | Stored mesh role and SSID, work in progress |
| `Get-Config` | Fixtures with live values, the label table and the category vocabulary as one line of JSON. For tooling, not for reading |

## Other

| Command | What it does |
|---|---|
| `Set-System mesh role=<none\|parent\|child> [ssid=<>] [passwd=<>]` | Stored only. No parent or child logic exists yet |
| `Reboot` | Restart the board |
| `Help` | The built-in command summary |

## Binary protocol

The text console is fine for configuring a board and hopeless for driving one.
`Set-Value address=4 value=200` is 30 bytes and a string parse for a single DMX
slot, which a dragged fader would send hundreds of times a second. Measured on an
ESP32-S2, 300 updates to one channel:

| | Bytes per update | Updates per second |
|---|---|---|
| `Set-Value` text command | 30 | 81 |
| Binary frame | 7 | 914 |

So binary frames share the same link, told apart by a start byte the text
protocol never begins a line with. A `0x7E` anywhere other than the start of a
line is ordinary text and cannot drag the parser into binary mode mid-sentence.

```
host  -> board   7E <cmd>        <len> <payload...> <crc8>
board -> host    7E <cmd | 0x80> <len> <payload...> <crc8>
```

`crc8` is the classic polynomial `0x07` over the command, the length and the
payload. A frame failing the check is dropped rather than guessed at: a wrong DMX
value is worse than a missing one, and any sender worth the name resends on its
next tick.

| Cmd | Payload | Does |
|---|---|---|
| `0x01` | `addr_hi addr_lo value` | Writes one DMX slot |
| `0x02` | `addr_hi addr_lo count values...` | Writes a run of slots |
| `0x03` | `addr_hi addr_lo count` | Reads a run back, answered on `0x83` |
| `0x10` | none | Ping, answered on `0x90` |

Addresses are 1 to 512 and anything outside is ignored. The length byte caps a
frame at 255 payload bytes, so a full universe takes three block writes.

> On the ESP32-S2 the port is native USB CDC, where the baud rate is a fiction
> both ends ignore. Throughput is the USB link's, so the gain comes from the
> compact frames rather than from any baud setting. On the ESP8266 it is a real
> UART and the baud rate matters.

`tools/dmx_desktop.py` is a Tkinter control surface that speaks this protocol
over USB, and is the worked example.
