# EZ fixtures

[Wiki index](../../WIKI.md)

An EZ fixture is the same fixture as a [lite one](lite-devices.md) with a
control on top that understands what its channels mean. A colour wheel instead
of three faders labelled Red, Green and Blue; a joystick instead of Pan and
Tilt.

Nothing is hidden by it. The card carries a button that flips it to the lite
view, one control per channel, for the nights when a fixture misbehaves and the
widget is in the way.

## How a card is bound

A kind has **roles**. Creating the card means saying which channel offset fills
each one. The offsets are within the fixture, exactly as for a lite channel, so
`red = 2` on a fixture starting at 4 drives DMX address 5.

Roles marked optional are genuinely optional. Left blank, the role is unbound
and its part of the display does not appear at all; nothing is ever written to a
channel the fixture never claimed. Fill it in later and the display grows.

Because roles store offsets rather than addresses, moving the fixture's start
channel moves the whole card with it.

The dialog refuses to close on a role pointing at a channel that does not exist,
rather than saving something that cannot work.

## The eight kinds

| Kind | Required roles | Optional roles | What the card shows |
|---|---|---|---|
| `dimmer` | `level` | | A flat fader with a percentage row |
| `strobe` | `strobe` | | The same, for a fixture whose whole job is flashing |
| `mono` | `level` | `strobe` | A fader per bound role |
| `rgb` | `red`, `green`, `blue` | `dimmer`, `strobe` | Colour wheel, with the bound faders standing beside it |
| `rgbw` | `red`, `green`, `blue`, `white` | `dimmer`, `strobe` | As `rgb`. White carries whatever the three colours have in common, which is cleaner and usually brighter than mixing it |
| `cwww` | `warm`, `cold` | `dimmer`, `strobe` | A vertical warm-to-cold crossfade, in the spirit of the Home Assistant light entity |
| `smoke` | `output` | | On and off, or a pump fader, plus timed bursts |
| `motion` | `horizontal`, `vertical` | `horizontal_fine`, `vertical_fine`, `speed` | A joystick, a Move/Fine switch and the bound faders |

The layout is the same everywhere: the widget on the left, its faders standing
to the right, presets underneath. Cards that are nothing but a fader lie it flat
across the card instead, because a lone vertical slider in a wide card is all
margin and no control.

## Colour

Click anywhere on the wheel to take that hue and saturation. Clicking also
raises the master dimmer if one is bound and sitting at zero, since a colour
picked on a dark fixture otherwise does nothing and looks broken.

The percentage row under a fader is always 0, 25, 50, 75, 100.

## Motion

The joystick is a gamepad, not a map. Deflection sets a **rate**: a small push
steps the channel by one, a full push by whatever **fastest step** is set to, and
it keeps stepping while held. That is what makes both a slow follow and a quick
reposition possible on one control.

| Setting | Does |
|---|---|
| Invert horizontal, invert vertical | For a fixture hung upside down, which half of them are |
| Invert horizontal fine, invert vertical fine | For a fixture whose fine channel counts the other way from its coarse one |
| Fastest step at full deflection | Default 10. A small push always steps by one whatever this is |
| Keyboard arrow step | Default 5. How far one arrow key press moves, unrelated to the stick's rate |
| Reverse the speed channel | For fixtures where 0 is fastest and 255 slowest, which is common enough to catch you out |
| What the card's Fine position does | Movement and fine together, or the fine channels alone |

The **Move / Fine** switch on the card picks which channels the stick drives.
Move is always the coarse pair. Fine does whatever that last setting says.

Arrow keys nudge while the card has focus. Double-click the joystick to recentre
it.

## Smoke

| Setting | Does |
|---|---|
| Control | On and off only, or a variable pump fader |
| Auto-off after (seconds) | 0 disables it |

Bursts of 1, 3 and 5 seconds sit under the control, plus one with the duration
typed in. **The timer lives on the board, not in the browser.** A tab that
closes, a laptop that sleeps or a client that loses WiFi mid-burst cannot leave
a machine pumping. Everything is capped at 30 seconds regardless.

Auto-off is optional rather than a rule, because some jobs really do want a long
continuous run and a cap that cannot be turned off is its own kind of failure.

## Presets

Every card can save what it is currently showing under a name and put it back
later with one press. On a colour card that stores a colour, on a motion card a
position, but it is one mechanism: capture the values currently bound to the
card's roles, name them, restore them on demand.

The argument is repeatability. A wheel or a joystick lands somewhere slightly
different every time it is aimed at; a named preset is identical today and next
month.

Nothing is shipped pre-populated. Right-click a preset to delete it.

Presets live in the fixture's own `ez` block, so they travel with it through the
JSON export, the config backup and `.env` seeding without any of those learning a
new concept:

```json
"ez": {
  "kind": "rgbw",
  "roles": {"red": 2, "green": 3, "blue": 4, "white": 5, "dimmer": 1},
  "settings": {},
  "presets": [
    {"name": "Warm wash", "values": {"red": 255, "green": 140, "blue": 40, "white": 0}}
  ]
}
```

A small number per fixture, since this rides inside a config that is sent whole
on every read.

## Seeding one from `.env`

```
DEVICE_1_CARD=ez
DEVICE_1_EZ_KIND=rgbw
DEVICE_1_EZ_ROLE_DIMMER=1
DEVICE_1_EZ_ROLE_RED=2
DEVICE_1_EZ_ROLE_GREEN=3
DEVICE_1_EZ_ROLE_BLUE=4
DEVICE_1_EZ_ROLE_WHITE=5
DEVICE_1_EZ_SET_MAX_STEP=10
```

Presets are not seeded: they are made live and travel in the `.json` backup.

## The same widgets over a whole rig

An [EZ group](groups.md) gives each role a **set** of channels instead of one,
so a single colour wheel drives the reds of six fixtures at once. The card looks
and behaves identically; only what it is pointed at differs.
