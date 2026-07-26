# Roadmap

What is planned, in order. Nothing here is a promise, and anything under **Later**
has no place in the queue at all yet.

Batches 1 to 7 have shipped and are not listed. What they built is described in
[WIKI.md](WIKI.md).

## Batch 8, two module switches that do not switch anything

Both toggles under **Settings**, **API** promise more than they deliver.

- **Headless is chosen at the flash, not at runtime.** `WITH_WEBUI=0` is a build
  flag, so a board carrying the UI has no way to stop serving it. Wants a
  `webui_enabled` flag beside the other module switches, with the serial console
  and the API as the way back in.
- **The WebSocket switch only takes effect at boot.** The server starts once and
  nothing ever stops it, so unticking the box leaves the socket listening. Either
  make it start and stop for real, or label it "reboot to apply" as the DMX pin
  fields are.

## Batch 9, the EZ cards that were never revisited

Motion and the colour wheel have each had a pass. `cwww`, `smoke`, `dimmer`,
`strobe` and `mono` were built once and not touched since.

Each wants a specification before any code, in the shape the original EZ spec
used: what the creation dialog asks, against what the card then shows. Reworking
five cards without one produces five cards that disagree with each other.

## Batch 10, DMX in

- Rework the DE/RE pin handling.
- Wire the MAX485's `RO`, so a board can read a universe as well as write one.
- A reception page showing what is arriving, per channel.

The point is the parent role: one box patched into a real desk, relaying what it
reads to the children. That makes the project wireless DMX distribution rather
than a standalone controller, which is why it comes before batch 11.

ESP32 first, since `esp_dmx` already receives. Two things need settling. A
half-duplex transceiver cannot send and receive at once, so either the directions
take turns inside the 25 ms frame budget or the board carries a second one. And
the feature has to know what it is for: monitoring, merging with what the board
generates, or passing straight through.

## Batch 11, Parent/Child over ESP-NOW

A parent controls the children. A child is an executant and stores nothing beyond
its ESP-NOW config, its WiFi config if it was given one, and its save-guard.
ESP-NOW carries the universe, the existing WiFi stack carries configuration.

- **A Receiver field on every card**, asking which output drives it: the parent's
  own MAX485 first, then each child.
- **Naming.** A child calls itself `Child-XXXXXX` at first boot and the parent can
  rename it, so nodes are told apart without reading MAC addresses off labels.
- **WiFi fallback**, for when ESP-NOW does not get through.
- **Network settings handed down.** The parent gives its children a copy of the
  WiFi it knows, plus the fly-away network from batch 12. Nothing else travels.
- **A child is a way in as well as a way out.** USB into any child drives the whole
  rig, by relaying its serial link up to the parent. The parent is usually the box
  in the least reachable place.

`mesh.json`, `/api/mesh`, the Parent/Child settings panel and `Set-System mesh`
already exist and are labelled "stored only, no effect yet". The plumbing is
there; nothing acts on the role.

An ESP32 can be parent or child, an ESP8266 only a child, so the role selector
should say so rather than offering something the board cannot do.

## Batch 12, fly-away mode

A configured access point that replaces the built-in hotspot: when no known
network answers, this comes up instead.

- A custom SSID and a password that has to be chosen. No shipped default, and it
  cannot be switched on until it has one.
- It is also the fallback network for whichever children were given it.
- Once enabled it becomes the entry point for configuring WiFi.

The hotspot ships with a known name and a known password, and a touring rig whose
owner forgot to change either is an open door.

## Batch 13, grow the desktop application

`tools/dmx_desktop.py` already exists and is minimal: a Tkinter surface driving
the board over USB, on the binary serial protocol shipped with it. The batch is
what it should grow into, which is the EZ widgets, scenes, groups and the
emergency stop rather than the bare fader grid it is now. Worth listing per
feature first, as for batch 9.

Values must keep going out as binary frames rather than text commands, which is
what makes a dragged fader usable over a serial link.

## Batch 14, the child firmware

A build that is only ever a child: everything belonging to the brain trimmed out,
the role locked rather than defaulted, and a page that covers configuration and
nothing else. A headless variant beside it.

The ESP8266 is what makes it necessary, since RAM there is half spent before a
browser connects and no partition change helps with heap. It is built for the
ESP32 too, because batch 15 wants that chip's pin count, and because somebody
running one parent and six children should not carry the brain firmware on all
seven boards.

**Kept:** DMX out, the child side of the mesh, USB direct control, WiFi with DHCP
or a static address, W5500 Ethernet, the serial console, OTA and updates from a
release, and the save-guard.

**Trimmed:** fixtures lite and EZ, scenes, groups, labels, categories, the MQTT
bridge, and the live-control websocket. A child holds a 512 slot buffer that
somebody else writes into and has no opinion about what a fixture is.

Also in scope:

- **Updates relayed by the parent**, so a rig of children updates in one press
  rather than one USB cable at a time. The parent already verifies a release
  against the checksum GitHub publishes and can pass the verified bytes on.
- **A status light**, carrying powered, parent reachable, and DMX moving. A node
  in a truss has no other way to speak.
- **Link quality per child** in the parent's UI. A wireless distribution system
  that cannot show which node is struggling is not one to trust twice.
- **A self-test pattern**, so a box can be commissioned on the ground.
- **Adoption instead of MAC addresses**, with a pairing window on both sides.

Open questions:

- **What a child does when the parent disappears.** Holding the last frame, fading
  out and going dark are each right in a different room. It should be a setting
  with a stated default rather than whatever the code happens to do.
- **Eight release assets.** Child and child-headless on both families doubles the
  artefacts, and `FW_TARGET` names the asset the updater looks for. Each build
  needs its own name, and the image should carry it so the updater can refuse one
  meant for a different board.

## Batch 15, on-board GPIO on a child (stalled)

A child uses two pins for DMX and leaves the rest of the header idle. The idea is
to put them to work driving relays, buttons and contact closures from a board
already hanging in the truss with power and a link to the parent, and to let a
child report what it reads back upward rather than only receiving orders.

Recorded here because it is the reason batch 14 builds a child for the ESP32 as
well as the ESP8266. Nothing below the idea is settled and no work is scheduled.

# Later

Wanted, not scheduled, not promised. Items marked **carried over** were already on
the [ESPDMX](https://github.com/CestMoiRoma/ESPDMX) roadmap.
[HARDWARE.md](HARDWARE.md) says which chip can host which of these.

## Getting DMX in and out

- **Several universes per board.** One MAX485 per TX pin on an ESP32, each with
  its own buffer. Mostly needs a universe field and a driver instance per output,
  and an eye on clocking every universe inside the same 25 ms window. Worth doing
  before the config format calcifies further.
- **Art-Net and sACN input.** Accept a universe from QLC+, Resolume, a grandMA on
  PC or anything else speaking the standard protocols. The shortest path to being
  useful alongside software people already run, and it shares most of its plumbing
  with batch 10.
- **RDM (E1.20).** Discovery and remote addressing over the same pair. Reachable
  once batch 10 lands, but it needs tighter bus timing than the transmit loop has.

## Hardware

- **A PCB version.** **Carried over.** ESP32, MAX485, XLR and power on one board
  instead of a breakout and jumper wires. Best done after the multi-universe work,
  so it is laid out for the final number of outputs. Isolated RS-485 earns its
  parts on anything that leaves the workshop.

## Control and interface

- **A grand master.** The emergency stop shipped; a global dimmer scaling every
  channel did not. Not the same feature as the panic button, which is a dry zero
  with nothing remembered, on purpose.
- **Fixture profiles, imported rather than hand-built.** A parser for QLC+ `.qxf`
  or Open Fixture Library JSON arrives with thousands of fixtures already defined,
  where a hand-built library is a permanent chore.
- **Gang by label.** One card driving every fixture sharing a label, so a new
  fixture joins the Face bar by being tagged. Needs a clear statement of what a
  control is about to move, because a widget that silently drives eight fixtures
  is a trap.
- **Identify a fixture.** A button that flashes one, to tell which physical unit a
  card drives. Worth more than it looks the first time somebody patches a bar of
  eight identical PARs.
- **Protected channels.** A channel flagged do-not-touch, skipped by the emergency
  stop, scenes and groups. On a fixture whose first channel selects a mode rather
  than a level, zeroing it changes what every other channel means.
- **A MIDI surface.** WebMIDI mapped onto faders and presets. Browser side only.

## Reliability and operations

- **A watchdog.** If the main loop wedges the rig freezes on its last frame and
  nothing recovers it.
- **Bring back the off-board test suite.** The CircuitPython line had 320 tests
  running against a fake ESP32. Nothing replaced them. A `native` PlatformIO
  environment would pay for itself the moment batch 9 starts rewriting cards.
- **A factory image.** Bootloader, partition table and application in one file, so
  a first flash does not need PlatformIO.
- **A preview before a config restore.** Loading a `.json` applies everything at
  once with nothing shown first. A diff would make it a decision rather than a leap.
- **Board discovery.** With parents, children and fly-away there will be several
  boards on one network. mDNS is already answered, so listing them costs little.
- **Something better than an API key.** No user accounts, no TLS, no rate limiting.
  That is the usual bargain for a device on a trusted LAN, and it is no defence
  against anything already on that LAN.

# Settled against

Considered and rejected for reasons that still hold, so anything heading this way
has to argue with the reason rather than around it.

- **Fades, chases and an on-board effects engine.** See
  [Timing and latency](docs/wiki/timing.md): nothing preempts the main loop and
  the frame interval is checked rather than driven by a timer, so a fade streamed
  from this box would be visibly uneven. Chases and effects belong to the
  fixture's own programs, and deterministic timing means a real desk or a wired
  Art-Net node.

# Loose ends

- The ESP8266 targets are **beta**. They compile, and nothing has run on the
  hardware since the C++ rewrite. RAM sits near half full before a client
  connects, so the websocket and several browsers at once are what to watch first.
  Its update path is written and untried.
- **The UI screenshots are stale.** Everything in `docs/images/` predates EZ cards,
  scenes, groups and the renamed Network panel, so the navigation bar shown no
  longer matches the product. They need retaking on a real board.
- `.env` still labels the DMX pins `D4` and `D3`, left from the CircuitPython
  line. They work, since only the digits are read, but the labels lie on an S2
  Mini. Should be `IO4` and `IO18`.
- `src/version.h` still falls back to an old version while `dev.env` carries the
  real one. Harmless, since the build always defines it, but the two drift apart
  with every release.
- `PAR 2` and `Lyre` sit on addresses 24 and 50 with channels inherited from a
  duplication. Placeholders, not a real patch.
