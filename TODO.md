# Work in progress

Scratch list for work agreed but not yet done. Lives in the repo on purpose: a
console scrollback is not a place to keep a plan.

## Batch 3

| # | Item | Status |
|---|---|---|
| 1 | New-device pre-popup: Lite, EZ Control, Restore from JSON | done |
| 2 | Up arrow on each card, saving the fixture as JSON | done |
| 3 | EZ Control widgets | done, never yet driven against a real fixture |
| 4 | Sort and search column on the left | done |
| 5 | Network page: rename, W5500 Ethernet, Beta tags | done, Ethernet never run against hardware |
| — | Config: hide the DE/RE pin field when disabled | done in `803707b` |
| — | EZ card data model and board-side burst timing | done in `8a3a994` |

## EZ Control spec

The shorthand is the one it was written in: **A** is what the creation dialog
asks for, **D** is what the card then displays.

Two rules run through all of it:

- **The percentage row is 0 / 25 / 50 / 75 / 100** everywhere it appears.
- **Optional channels are genuinely optional.** Left blank at creation, the role
  is not bound and its part of the display does not appear at all. Filled in, the
  display grows to match. Nothing is written to a channel the fixture never
  claimed.

| Kind | A, asked at creation | D, shown on the card |
|---|---|---|
| `dimmer` | Channel | Slider + percentage row |
| `strobe` | Channel | Slider + percentage row |
| `mono` | Channel. Optional: strobe | Slider + percentage row. Optional strobe slider + percentage row |
| `rgb` | Red, green, blue. Optional: dimmer, strobe | Colour wheel. Optional master fader, optional strobe slider, each with its percentage row |
| `rgbw` | Red, green, blue, white. Optional: dimmer, strobe | As `rgb` |
| `cwww` | Cold white, warm white. Optional: dimmer, strobe | Whites wheel, cold to warm. Optional master fader and strobe |
| `smoke` | Mode (`onoff` or `slider`), and the channel | On/off button, or a slider in slider mode, plus burst 1 s, 3 s, 5 s and burst *n* s with *n* typed in |
| `motion` | Vertical, horizontal. Optional: vertical fine, horizontal fine, speed | Joystick, a mode selector (Move / Fine tune), and where a speed channel is bound, a speed slider + percentage row |

### The dimmer on the light cards

Carried over from the proposals as an **optional** role on `rgb`, `rgbw` and
`cwww`, on the same terms as strobe: blank means unbound and nothing is drawn.

It is there because a colour wheel alone cannot set intensity. Pulling the red
down changes the hue, not the brightness, so on a fixture with a master dimmer,
a wheel with no dimmer beside it can reach a colour but not a level. The
reference PAR is exactly that shape: dimmer on offset 1, RGBW on 2 to 5.

`dimmer` and `strobe` also exist as cards in their own right, for a fixture whose
whole job is one of those.

### Settled

- **Raw channels stay reachable.** Every EZ card carries a button that flips it
  to the lite view, one control per channel, for the nights a rig misbehaves and
  the widget is in the way.
- **The joystick is a gamepad, not a map.** Deflection nudges: left steps the
  value down by one, right steps it up, likewise vertical, repeating while held
  rather than jumping to an absolute position. Two settings per card invert the
  horizontal and the vertical independently, since half the moving heads on a
  bar are hung upside down.
- **Fine tune is a per-card setting**, offering "control movement and fine tune"
  or "fine tune only".

- **Roles follow the fixture.** Nothing to build: roles store offsets, and the
  DMX address is `start_channel + offset - 1`, so moving a fixture's address
  moves every role with it. What does need building is the dialog refusing to
  close on a broken binding, warning and holding the popup open until the role
  points at a channel that exists.
- **The whites control is a vertical slider**, warm at the top and cold at the
  bottom, in the spirit of the Home Assistant light entity. `cwww` is for
  fixtures that mix their own warm and cold white.
- **The smoke auto-off is optional**, a per-card setting rather than a rule.
  Some jobs really do want a long continuous run, and a cap that cannot be
  turned off is its own kind of failure.
- **Joystick deflection sets the rate.** A small push steps by one, full travel
  steps by more, with the maximum step configurable per card.

### Deferred to batch 4

- **Gang by label.** One card drives every fixture sharing a label, so the whole
  Face bar takes a colour at once. Needs a clear indication of what a control is
  about to move, because a widget that silently drives eight fixtures is a trap.

### User presets, one mechanism for two jobs

Nothing is shipped pre-populated. A card can **save what it is currently showing
under a name**, and recall it later with one press. On a light card that stores
a colour, on a motion card a position, but it is the same feature: capture the
values currently bound to the card's roles, name them, put them back on demand.

The argument is repeatability. A wheel or a joystick lands somewhere slightly
different every time it is aimed at; a named preset is identical today and next
month.

Storage lives in the fixture's own `ez` block, so a preset travels with its
fixture through the JSON export, the config backup and the `.env` seeding
without any of them learning a new concept:

```json
"ez": { "kind": "rgbw", "roles": {…},
        "presets": [ {"name": "Warm wash", "values": {"red": 255, "green": 140, "blue": 40}} ] }
```

Capped at a small number per fixture, since this rides inside a config that is
sent whole on every read.

### Motion extras, settled

- **Arrow keys** nudge while the card has focus.
- **Double-click the joystick** to centre, rather than a separate button.
- **Saved positions** are the preset mechanism above.

## Batch 4

### Header

- **Blackout**, a red button: every channel to zero.
- **Save-guard**: keep the channel state so a reboot or a power cut comes back
  to the values that were live.

### Scenes, a new page

- The same sort and filter column as Devices.
- **New Scene** behind the same three-way pre-popup: pick fixtures, pick
  channels, type the values. A description field.
- The scene card carries its name, a play button, a gear to edit and a bin.

### Groups, a new page

- Group channels together.
- **New Group** behind a pre-popup: Group Lite or Group EZ.
- Lite shows the group in the lite format; EZ in the EZ format, with the channel
  choice laid out per fixture and picked by checkbox.

### EZ motion

- **Reverse speed**, for fixtures where 0 is fastest and 255 slowest.

### Network

- ~~The WiFi scan does not work.~~ Done: it was blocking the loop for seven
  seconds and hiding its results in a datalist. Async now, with a visible list.

### UI

- Everything is centred and the cards are narrow. Pin the filter column to the
  left edge of the page instead.
- **i18n**, one JSON per language: FR, EN, DE, ES.
- MQTT: the Enable is duplicated. Hide it when the bridge is disabled, and ship
  MQTT disabled by default.
- Prettier cards: the switch-to-lite becomes a small icon like the bin and the
  gear; EZ sliders go vertical with 0/25/50 stacked vertically on their left;
  Save look stays at the bottom.
- Clicking a colour on the wheel takes the dimmer to full.
- Double-click the wheel recentres it, as the joystick does.
- **Lite cards are not to be touched.**

### MQTT

- Scenes must be triggerable from MQTT, so they go to Home Assistant like the
  devices do. Groups do not need to.

### Decisions taken

- **Blackout is a dry zero.** One press, every channel to nought, nothing
  remembered. No latch, no restore.
- **All four languages ride inside the page.** They are inlined at build time,
  so switching is instant and offline and the page stays one request. Costs
  roughly 3 KB gzipped on a 29 KB page.
- **A group is a chosen set of channels**, ticked per fixture and driven
  together, not a set of whole fixtures.
- **Every device and every channel carries a stable uid.** Scenes and groups
  reference channels by uid, so a fixture being readdressed, reordered or edited
  does not disturb them: the scene looks the channel up rather than remembering
  where it sat. The same applies to saving and restoring groups. The "cancel or
  continue without this device" prompt is then only needed for a file brought in
  from another board, where a uid genuinely does not exist here.

### Saving and restoring scenes and groups

Open question as posed: a device's config can change underneath a saved scene.
Either it cannot be done, or every device carries a UUID and a restore that
cannot find one asks: cancel, or continue without that device.

## Batch 5

- **Over-the-air update**, in the spirit of ESPHome, leaving the data intact.
- If possible, updating straight from a GitHub release, plus a CI pipeline that
  builds the `.bin`.

## Batch 6

A real wiki, one Markdown file per subject: serial, websocket, HTTP, MQTT, lite
devices, EZ devices, scenes, groups, wiring.

## Batch 7

Confirmation phase first, then merge to `main` and release the ESP32 binary for
the GitHub updater.

## Loose ends

- `.env` still labels the DMX pins `D4` and `D3`, left from the CircuitPython
  line. They work, since only the digits are read, but the labels lie on an
  S2 Mini. Should be `IO4` and `IO18`.
- `PAR 2` and `Lyre` are on addresses 24 and 50 with channels inherited from a
  duplication. Placeholders, not a real patch.
- MQTT has never been pointed at a broker.
- The ESP8266 targets are **beta**. They compile again, after two real bugs
  found by finally building them, but nothing since the C++ rewrite has run on
  the hardware. RAM is at 48.8% before a client connects, so the websocket and
  several browsers at once are what to watch first.
- The README roadmap still asks for a websocket and still says there is no
  authentication. Both shipped.
