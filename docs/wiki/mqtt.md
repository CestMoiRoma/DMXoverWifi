# MQTT and Home Assistant

[Wiki index](../../WIKI.md)

The bridge publishes every channel, every scene and an emergency stop to a broker
with Home Assistant discovery, and applies anything sent back.

It is optional, off by default, and only runs when the board is on a real network
rather than its own hotspot. It speaks over WiFi, so a board on the wired link
alone cannot reach a broker.

## Setting it up

1. **Settings**, **API**, tick **MQTT bridge**.
2. Fill in the broker host and port, the username and password if it wants them,
   and press **Save**.

The status line above the form then says what actually happened, which is the
part worth reading:

| Line | Means |
|---|---|
| Connected to 192.168.1.20:1883 | Working. The detail line counts the entities published and how long it has been up |
| nothing answered on that host and port | Wrong address, wrong port, or the broker is not running |
| the broker refused the username or password | Credentials |
| the broker rejected the client id | Another board with the same chip id, which should not happen |
| that broker name did not resolve | A hostname your DNS does not know |
| that .local name did not answer on mDNS | An mDNS name nothing replied to. ESP8266 builds cannot ask mDNS at all and need an address |
| the board is not on a WiFi network | It is on its hotspot, or the radio is off |
| the MQTT bridge is switched off under Modules | The module, not the broker |

**Connect now** forces an attempt immediately and answers with the outcome, which
beats waiting for the backoff. The board retries on its own at 5 seconds, then
doubling to a minute, so a broker that is down costs a fraction of a second a
minute rather than stalling the DMX loop.

`get-status mqtt` on the [serial console](serial-console.md) prints the same
thing, including the reason.

| Setting | Default |
|---|---|
| `base_topic` | `dmxwifi` |
| `discovery_prefix` | `homeassistant` |
| `port` | `1883` |

Defaults come from [dev.env](../../dev.env).

## Availability

The board registers a last will on `<base_topic>/status` and publishes `online`
there on connect. If it drops off, the broker publishes `offline` on its behalf
and Home Assistant marks every entity unavailable, rather than showing the last
value it happened to hear from a board that is no longer there.

## Channels

Every channel gets a unique id of `<device_id>_<offset>`, for example
`dev-a1b2c3_1`.

| Topic | Direction | Payload |
|---|---|---|
| `<base>/<uid>/set` | in | Slider: 0 to 255. Switch: `ON`, `OFF`, `TRUE`, `FALSE`, `1`, `0`, `255`. Trigger and momentary: any payload fires 255 |
| `<base>/<uid>/state` | out | The current value, retained, for sliders and switches only |

| Channel type | Discovery topic | Entity |
|---|---|---|
| `slider` | `<prefix>/number/<uid>/config` | `number`, min 0, max 255, step 1 |
| `button-switch` | `<prefix>/switch/<uid>/config` | `switch`, on 255, off 0 |
| `button`, `button-momentary` | `<prefix>/button/<uid>/config` | `button` |

All the channels of a fixture share one `device` block, so Home Assistant groups
them as one device.

State is published on connect as well as on change. A broker that has just met
this board knows nothing about a rig that has been lit for an hour, and a value
published only when it changes would leave Home Assistant showing zero until
somebody moved a fader. It is retained, so a Home Assistant that restarts reads
the rig from the broker.

## Scenes

Each [scene](scenes.md) is published as a `scene` entity:

| Topic | Direction | Payload |
|---|---|---|
| `<base>/scene/<scene_id>/set` | in | Anything. Home Assistant sends `ON` |

Stateless by nature: a scene is something you fire, not something that is on, so
there is no state topic.

## Emergency stop

| Topic | Direction | Payload |
|---|---|---|
| `<base>/estop/set` | in | Anything |

Every channel to zero. Published as a `button` entity, so it is one press from a
phone in another room. A panic button that argues about its argument is not a
panic button, hence any payload.

Scenes and the emergency stop hang off a single device named for the board,
rather than scattering loose entities through the integration.

## Groups are not published

Home Assistant has its own grouping, applied to the entities already published. A
second mechanism on this side would be one more thing to keep in step. See
[Groups](groups.md).

## Removing things

Discovery is retained, which means it outlives whatever published it. Deleting a
fixture or a scene therefore withdraws its configs explicitly, with an empty
retained payload, before the thing itself goes. Without that, Home Assistant
would keep showing a fixture that no longer exists on a board that never mentions
it again.

## Driving it by hand

```bash
mosquitto_pub -h 192.168.1.20 -t 'dmxwifi/dev-a1b2c3_1/set' -m 255
mosquitto_pub -h 192.168.1.20 -t 'dmxwifi/scene/scn-a8d2f9/set' -m ON
mosquitto_pub -h 192.168.1.20 -t 'dmxwifi/estop/set' -m PRESS

mosquitto_sub -h 192.168.1.20 -t 'dmxwifi/#' -v
```

## In a Home Assistant automation

```yaml
- alias: House lights down when the film starts
  trigger:
    - platform: state
      entity_id: media_player.projector
      to: playing
  action:
    - service: scene.turn_on
      target:
        entity_id: scene.house_down
```

Scenes published by the board appear as ordinary scene entities, so nothing here
is specific to this project.
