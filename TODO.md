# Roadmap and work in progress

The plan for this project, in the repository on purpose: a console scrollback is
not a place to keep one. This file is the **only** roadmap. The README used to
carry a second one and no longer does.

Two halves. **Batches** are agreed work, in order. **Later** is everything wanted
but not scheduled, where nothing is a promise and the order is rough. Below that,
what has been settled *against*, so it stops being proposed again.

Batches 1 to 7 have shipped and are not listed, so the work starts at 8. What the
finished batches built is described in [WIKI.md](WIKI.md), and what was decided
along the way is in the git log.

## Batch 8, the two switches the confirmation pass found

### Headless at runtime

Headless exists, but it is a decision taken at the flash: `WITH_WEBUI=0`, two of
the four PlatformIO environments, and `tools/pack_web.py` does not even emit the
page's C arrays. A board carrying the full UI has no way to stop serving it, and
neither of the neighbouring switches does the job. `http_api_enabled=false` never
touches the UI, because the same-origin exemption is tested first;
`wifi_enabled=false` takes the API and MQTT down with the page, which is the
opposite of headless.

To build: a `webui_enabled` flag in `api.json` beside the other module switches,
tested in `DmxWebServer::serveIndex()`, answering 404 when off, with every
`/api/*` route left alone. The way back has to exist before the switch does: the
serial console, and the API with its key. A `WITH_WEBUI=0` build ignores the flag,
since there is no page in the binary to withhold.

### The WebSocket switch does nothing at runtime

`wsServer.begin()` runs once in `setup()` and returns early when the module is
off, and nothing ever calls a stop. So unchecking the box leaves the socket
listening on port 81 and still accepting any client holding the key, and checking
it leaves the socket absent. Only the UI reacts, and only after a reload, because
it reads `websocket_enabled` from `/api/info`.

Either make it real, starting and stopping from the `/api/modules` POST, or put
"reboot to apply" on the label the way the DMX pin fields do. The first is the
honest one, given the paragraph above those checkboxes says each subsystem can be
switched off entirely.

## Batch 9, the EZ cards that were never revisited

Motion and the colour wheel have each had a pass and stay as they are. The rest
were built once and not touched since:

- `cwww`, the warm-to-cold vertical crossfade
- `smoke`, on/off or pump fader, with its bursts
- `dimmer`
- `strobe`
- `mono`

What each of those should become is still to be written down. Worth deciding
before touching code, because "rework" on its own will produce five cards that
do not agree with each other. The two that were polished are the reference for
layout, for how a bound optional role appears, and for where the presets sit.

## Batch 10, DMX in

Deliberately ahead of batch 11: the argument for input is the parent role, one box
patched into a real desk and relaying what it reads to the children. That turns
the project into wireless DMX distribution rather than a standalone controller.

- Rework the DE/RE pin handling.
- Add the MAX485's RO, the receiver output, so the board can read a universe as
  well as write one.
- A DMX reception page showing what is arriving, per channel.

Already settled elsewhere, so not worth re-deciding: this is **ESP32 only**, per
the capability matrix in [HARDWARE.md](HARDWARE.md), because the ESP8266 has no
receive pin free and its transmit UART has no RX line at all. `esp_dmx` already
does receive, so the library is in place.

Genuinely open. A half-duplex MAX485 cannot transmit and receive at once, which
is what DE/RE exists to arbitrate, so the two directions have to take turns
inside a 25 ms frame budget or the wiring needs a second transceiver. And the
board has to know what it is for: monitoring only, merging with what it
generates, or passing straight through.

## Batch 11, Parent/Child over ESP-NOW

ESP-NOW is the right transport for relaying a live universe: connectionless, no
access point in the path, far less latency and jitter than an HTTP or MQTT round
trip, and it keeps working when the venue WiFi does not. The shape is ESP-NOW for
the universe stream and the existing WiFi stack for configuration.

A parent controls the children. A child is an executant and stores nothing beyond
its ESP-NOW config, its WiFi config if it was given one, and its save-guard.

- **A Receiver field on every card.** Card creation asks which output drives it:
  OnBoard first, meaning the parent's own MAX485, then each child.
- **Naming.** A child names itself `Child-XXXXXX` at first boot, so two of them
  on a bar can be told apart without reading MAC addresses off a label. The
  parent can rename it afterwards, over ESP-NOW or over the WiFi fallback.
- **WiFi fallback.** A child sitting on the same network as its parent can take
  its orders over WiFi when ESP-NOW does not get through.
- **Network settings handed down.** The parent gives its children a backup copy
  of the WiFi it knows: every SSID and password, plus the fly-away network from
  batch 12. Nothing else travels.

What exists to build on: `mesh.json` stores `role`, `ssid` and `password`,
`/api/mesh` reads and writes it, the Parent/Child panel in the UI edits it and
`Set-System mesh` sets it from the console. All four are labelled "stored only, no
effect yet", which is accurate: nothing acts on the role. The plumbing is there
and the behaviour is not.

One hardware constraint from HARDWARE.md that shapes the UI: an ESP32 can be
parent **or** child, an ESP8266 can only be a child. The role selector should say
so rather than offering a parent role the board cannot fill.

## Batch 12, fly-away mode

Switchable on only once it has been configured, and it overrides the hotspot:
when no known network answers, this is what comes up instead.

- A custom SSID, and a password that has to be chosen. No shipped default.
- It is also the fallback network for whichever children were given it.

Why not simply keep using the hotspot: the hotspot ships with a known name and a
known password, and a nomadic install whose owner forgot to change either is an
open door. Fly-away mode refuses to turn on until it has its own.

When enabled it becomes the new entry point for configuring WiFi.

## Batch 13, grow the desktop application

Not a new build. `tools/dmx_desktop.py` already exists, a Tkinter control surface
over USB from commit `908181d`, and it is minimal. The transport it should keep
using is the **binary serial protocol** shipped alongside it: `0x7E`-framed,
crc8 per frame, four commands (write a slot, write a run, read a run back, ping),
sharing the link with the text console and told apart by a start byte the text
protocol never begins a line with. Measured at 914 updates a second against 81
for the equivalent text command, so nothing here should fall back to text for
values.

The parts already in place, and not to be rebuilt: `Get-Config` answers with one
line of JSON so the client never scrapes human-readable status, writes are
coalesced per channel on the same 30 ms window as the web UI, and consecutive
addresses ride in one block frame, which is exactly the shape of a colour fade
across R, G and B.

So the batch is what the surface should grow into: the EZ widgets, scenes, groups
and the emergency stop, rather than the bare fader grid it is now. Worth
listing per feature before starting, as for batch 9.

One packaging note that already bit once: PlatformIO's bundled Python has no
Tkinter, so the app runs on the system Python. Anything shipped to a user needs
its own answer to that.

# Later

Wanted, not scheduled, and not promised. Items marked **carried over** were
already on the [ESPDMX](https://github.com/CestMoiRoma/ESPDMX) roadmap. The
capability matrix in [HARDWARE.md](HARDWARE.md) says which chip can host which of
these; the DMX-side ones are ESP32 only, and that is a chip limit rather than a
missing library.

## Getting DMX in and out

- **Several universes per board.** More than one MAX485 on the same ESP32, each on
  its own TX pin, each with its own 512-channel buffer. The fixture model already
  addresses channels within a device, so it mostly needs a universe field and a
  driver instance per output. Watch the frame budget: the loop has to clock out
  every universe inside the same 25 ms window. Worth doing before the config
  format calcifies further, since it touches everything that assumes one universe.
- **Art-Net and sACN input.** Accept a universe over the network from QLC+,
  Resolume, a grandMA on PC or anything else speaking the standard protocols, and
  put it on the wire. The shortest path to the box being useful alongside software
  people already run, and it shares most of its plumbing with batch 10.
- **RDM (E1.20).** Discovery and remote addressing over the same pair. `esp_dmx`
  supports it, so it becomes reachable once batch 10 lands, but it needs a timing
  discipline the current transmit loop does not have.

## Hardware

- **A PCB version.** **Carried over.** ESP32 module, MAX485, XLR and power on one
  board instead of a breakout and jumper wires. Worth doing after the
  multi-universe work, so the board is laid out for the final number of outputs
  rather than redone later. Isolated RS-485 earns its extra parts on anything
  that leaves the workshop.

## Control and interface

- **A grand master.** The emergency stop shipped; a global dimmer scaling every
  channel did not, and is the other half of what a desk gives you. It is not the
  same feature as the panic button and should not be bolted onto it: the stop is a
  dry zero with nothing remembered, on purpose.
- **Fixture profiles, imported rather than hand-built.** Picking a profile and a
  start address beats typing eleven channels. Building a library by hand is a
  permanent maintenance chore, so the better shape is a parser: QLC+ `.qxf` files
  or Open Fixture Library JSON into a device plus its EZ roles, which arrives with
  thousands of fixtures already defined. The EZ cards took some of the sting out
  of this already, since binding five roles is quicker than naming eleven
  channels.
- **Gang by label.** One card driving every fixture that shares a label, so a new
  fixture joins the Face bar simply by being tagged. Deferred out of batch 3 and
  never picked up. Groups do most of it now by holding a chosen set of channels,
  so what is left is the convenience. Needs a clear statement of what a control is
  about to move, because a widget that silently drives eight fixtures is a trap.
- **Identify a fixture.** A button that flashes one fixture so you can tell which
  physical unit a card drives. Trivial next to everything else here, and worth
  more than it looks the first time you patch a bar of eight identical PARs.
- **Protected channels.** A channel flagged do-not-touch, skipped by the emergency
  stop, by scenes and by groups. The stop is a dry zero over all 512 slots, and on
  a fixture whose first channel selects a mode rather than a level, zeroing it
  does not darken the fixture, it changes what every other channel means.
- **A MIDI surface.** WebMIDI in the browser mapped onto faders and presets, so a
  cheap controller drives the rig. Entirely browser side, no firmware.

## Reliability and operations

- **A watchdog.** If the main loop wedges, the rig freezes on its last frame and
  nothing recovers it. The hardware watchdog would reset the board instead.
- **Bring back the off-board test suite.** The CircuitPython line had 320 tests
  that ran the firmware on a PC against a fake ESP32. That harness was not carried
  into the rewrite, and there is no test suite at all today. A host-compilable
  equivalent, a `native` PlatformIO environment with the hardware behind the
  existing abstraction layers, would restore it. It would pay for itself the
  moment batch 9 starts rewriting cards.
- **A factory image.** Bootloader, partition table and application in one file, so
  a first flash does not need PlatformIO installed. Left over from batch 5.
- **A preview before a config restore.** Loading a `.json` applies system, WiFi,
  MQTT, mesh, labels and fixtures in one movement with nothing shown first. A diff
  against what is on the board would make it a decision instead of a leap.
- **Board discovery.** Once parents, children and fly-away mode exist there will be
  several of these on one network. mDNS is already answered, so a scan that lists
  the boards it finds costs little, in the web UI and in the desktop app both.
- **Something better than an API key.** The key gates the API and the websocket,
  and the served UI is trusted because a browser will not let a page forge its own
  `Origin`. That is the usual bargain for a device on a trusted LAN and it is no
  defence against anything already on the same network: no user accounts, no TLS,
  no rate limiting.

# Settled against

Not oversights. Each of these was considered and rejected for a reason that is
still true, so anything heading this way has to argue with the reason rather than
around it.

- **Fades, chases and an on-board effects engine.**
  [Timing and latency](docs/wiki/timing.md) is the argument: no preemption in the
  loop, and a frame interval checked with `millis()` rather than driven by a timer,
  so a fade streamed from this box would be visibly uneven. The documented
  position is that chases and effects belong to the fixture's own programs, and
  that deterministic timing means a real desk or a wired Art-Net node.
- **A board that updates itself.** Decided in batch 5. It needs a certificate
  bundle in flash, which goes stale and costs another 65 KB, and skipping the
  check means accepting firmware from anything able to sit in the middle of that
  connection. The browser fetches the release instead, and the UI says as much: a
  board with no laptop nearby cannot update itself.

# Loose ends

- **The release CI needs watching on its first run.** Until batch 7 it had never
  executed once: the branch was local and the repository carried no tags. It is
  now manual, owner-only, and composes its own `DD-MM-YYYY-VX.Y.Z` tag from
  `dev.env`, so what wants confirming on the first run is the whole chain rather
  than one step: four builds green, each image reporting the version it claims,
  the tag pushed, and four `firmware-<target>.bin` assets under it with the names
  the updater looks for. Read the run rather than assuming it.
- `src/version.h` still falls back to `0.2.0` while `dev.env` says `0.3.0`. That is
  by design, since the `-D` from `dev.env` always wins and the header exists for a
  build without it, but the two do drift apart with every release and a reader
  will eventually take the stale one for the truth.
- **The UI screenshots are stale.** Everything in `docs/images/` was captured on
  23 and 24 July 2026, before EZ cards, scenes, groups and the renamed Network
  panel existed, so `ui-home.png` shows a navigation bar that no longer matches
  the product. `ui-devices.png`, `ui-settings.png` and `ui-info.png` are unused
  and equally old. Needs retaking on a real board, at which point the README can
  show more than one.
- `.env` still labels the DMX pins `D4` and `D3`, left over from the
  CircuitPython line. They work, since only the digits are read, but the labels
  lie on an S2 Mini. Should be `IO4` and `IO18`.
- `PAR 2` and `Lyre` sit on addresses 24 and 50 with channels inherited from a
  duplication. Placeholders, not a real patch.
- The ESP8266 targets are **beta**. They compile, and nothing since the C++
  rewrite has run on the hardware. RAM is at 51% before a client connects, so the
  websocket and several browsers at once are what to watch first. Its OTA path is
  written but untried, and unlike the ESP32 it has no room for two full
  application images unless the flash layout is changed.
