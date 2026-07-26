# Groups

[Wiki index](../../WIKI.md)

A group is a set of channels driven as one. Six PARs on a bar should dim
together, and a group is how one fader does that instead of six.

Groups drive; they do not remember. A [scene](scenes.md) stores values, a group
stores which channels move together.

## Two shapes

**A lite group** is a single control writing the same value to every channel it
holds. That is what grouping channels means, and it is what a bar of PARs wants
when they should all dim together.

**An EZ group** picks a [kind](ez-devices.md) and gives each role a *set* of
channels rather than one. A colour wheel driving the reds of six fixtures, the
greens of six, the blues of six. The card is the same card a single fixture gets;
only what it points at differs.

## Building one

**+** on the Groups page, then lite or EZ.

A lite group is one long list of every channel in the rig with a search bar; tick
the ones that belong together.

An EZ group is a wizard: page one picks the control type, then one page per role,
each showing every channel with a search bar. It walks through the roles until
there are none left to fill. That shape exists because picking eighteen channels
for six fixtures on a single page was unusable.

Every group control states how many channels it is about to move. A widget that
silently drives eight fixtures is a trap.

## What a group stores

```json
{
  "id": "grp-7c1e02",
  "name": "Face bar",
  "card": "ez",
  "kind": "rgb",
  "roles": {
    "red":   ["ch-env1-2", "ch-env2-2"],
    "green": ["ch-env1-3", "ch-env2-3"],
    "blue":  ["ch-env1-4", "ch-env2-4"]
  },
  "members": [],
  "settings": {},
  "labels": []
}
```

A lite group uses `members` and leaves `roles` empty. Both hold channel uids, for
the same reason [scenes](scenes.md) do: a fixture readdressed or edited
underneath a group does not turn it into something else.

## Driving one over HTTP

```bash
curl -X POST http://esp-dmx.local/api/groups/grp-7c1e02/apply \
  -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  -d '{"role":"red","value":255}'
```

Omit `role` for a lite group. The answer carries a `missing` array of uids this
board does not hold, on the same terms as a scene.

## What groups are not

Groups are not published to MQTT. Home Assistant has its own grouping, applied to
the entities the board already publishes, and a second mechanism on this side
would only be something else to keep in step.

Deleting a fixture drops its channels from every group that held them.
