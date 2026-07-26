# Lite fixtures

[Wiki index](../../WIKI.md)

A lite fixture is the plain one: a list of channels, one control each, no
interpretation. It is what to reach for when a fixture does something unusual,
when its manual disagrees with reality, or when a rig is misbehaving and you
want to see the raw numbers. Every EZ fixture can be flipped to this view with
the icon on its card, so the raw channels are never more than one click away.

## Addressing

A fixture has a **start channel** and each of its channels has an **offset**.
The DMX address actually driven is:

```
address = start_channel + offset - 1
```

So a fixture starting at 10 with a channel at offset 1 drives address 10, not
11. Move the fixture's start channel and every channel follows, which is the
point of storing it this way: repatching in the UI matches repatching on the
fixture.

Offsets start at 1 because that is how fixture manuals count. A manual that
lists "channel 1: dimmer" means offset 1.

> Fixture manuals lie more often than you would expect, particularly about the
> personality a fixture is currently in. If a channel does not do what the table
> says, drive raw addresses one at a time from the serial console with
> `Set-Value address=<n> value=255` and write down what actually lights up.

## Channel types

| Type | Control on the card | Sends | Home Assistant entity | Serial aliases |
|---|---|---|---|---|
| `slider` | A 0 to 255 fader | The value as you drag, and again on release | `number`, min 0, max 255 | `slider` |
| `button` | A **Trigger** button | 255 on each press | `button` | `button`, `btn`, `trigger`, `bool`, `boolean` |
| `button-momentary` | A **Hold** button | 255 on press, 0 on release | `button` | `momentary`, `hold`, `btn-momentary`, `button-momentary` |
| `button-switch` | An **On** and **Off** toggle | 255 or 0, latching | `switch` | `switch`, `toggle`, `btn-switch`, `button-switch` |

`button-momentary` responds to touch as well as the mouse, so it works from a
phone at the lighting position.

Only `slider` and `button-switch` publish state to MQTT. The other two are
stateless on purpose: a trigger has nothing to report between presses.

## Channel uids

Every channel carries a uid, minted when it is created and never reissued.
Scenes and groups point at channels by uid rather than by fixture and offset, so
a fixture can be readdressed, reordered or edited without a scene silently
lighting the wrong lamp afterwards. You never need to see one, but they are
visible in the JSON exports and are what a scene missing a channel is complaining
about.

## Categories

Every fixture has exactly one category. Unlike labels, the list is **fixed in
the firmware**:

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

The split from labels is deliberate. A label answers "where is this in my rig"
and is yours to invent; a category answers "what kind of machine is this", which
the firmware and the UI can both reason about. That is why the vocabulary is
closed: the fixture editor keys off it, and it cannot key off names nobody has
agreed on.

An unknown id falls back to `other` on load rather than being kept, so a
hand-edited config cannot file a fixture under something nothing can filter.
Adding one means editing `src/categories.h` and reflashing. The list is served
at `/api/categories` so the UI never holds a second copy.

## Labels

Labels are colour-coded tags with an `id`, a `name` and a `color`. A fixture
references them by id and carries as many as you like, so one PAR can be both
**Face** and **PAR**.

The sort and filter column turns them into chips. Selecting several **widens**
the selection rather than narrowing it: **Face** plus **Contre** shows every
fixture carrying either, which is what a rig usually wants when you are trying
to find something.

Deleting a label strips its id from every fixture that referenced it, so nothing
is left filtering under a chip that no longer exists. The fixtures and their
channels are untouched.

In `.env` the relationship travels by **name** rather than by id, since that
file is meant to stay readable: `LABEL_1_NAME` declares one and
`DEVICE_1_LABELS` takes a comma-separated list. A name matching no label is
dropped rather than invented, so a typo shows up as a missing chip instead of a
phantom label.

## Creating one

Press **+** on the Devices page and choose **Lite**. Name it, give it a start
channel and a category, then add a row per channel: offset, name, type.

Or over serial:

```
> Set-device add name="PAR LED" channel=4 category=par
OK device 'PAR LED' added (start channel 4)
> Set-device add-channel device="PAR LED" name=Dimmer channel=1 mode=slider
OK channel 'Dimmer' added to 'PAR LED' (offset 1, slider)
```

Or over HTTP, which is what the UI does:

```bash
curl -X POST http://esp-dmx.local/api/devices \
  -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  -d '{"name":"PAR LED","start_channel":4,"category":"par",
       "channels":[{"offset":1,"name":"Dimmer","type":"slider"}]}'
```

## Editing, duplicating and exporting

Each card carries three icons: a gear to edit, a plus to duplicate and a bin to
delete. Duplicating is how a bar of identical PARs gets patched quickly: copy,
change the start channel, done.

The up arrow saves that one fixture as `.json`, which is the file to keep beside
a rig plan or send to somebody with the same fixture. Restoring one is the third
option in the **+** dialog.

Deleting a fixture also drops the scene steps and group members that pointed at
its channels, rather than leaving references to nothing behind, and withdraws
its Home Assistant entities.
