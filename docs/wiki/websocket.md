# WebSocket

[Wiki index](../../WIKI.md)

Live channel control and state fan-out, on **port 81**. The Arduino web server
cannot share port 80 with a socket upgrade, hence the second port.

It exists because a fader dragged across its travel emits values far faster than
one HTTP request each can carry: the headers and the connection setup would cost
more than the DMX. It also lets every open client watch the rig move, which
polling cannot do without hammering the board.

## Connecting

Unlike the HTTP API, the socket has **no origin exemption**. A WebSocket is as
reachable from a script as from the UI, so every client presents the key:

```
ws://esp-dmx.local:81/?api_key=<key>
```

A connection without a valid key is closed immediately, with no frame sent.

## Frames

JSON, since the traffic is small and readability is worth more here than the
bytes.

| Direction | Frame | Meaning |
|---|---|---|
| in | `{"t":"set","d":"<deviceId>","o":<offset>,"v":<0-255>}` | Drive a fixture's channel |
| in | `{"t":"seta","a":<1-512>,"v":<0-255>}` | Drive a raw DMX slot |
| out | `{"t":"hello","clients":<n>}` | Sent once on connect |
| out | `{"t":"val","d":"<deviceId>","o":<offset>,"v":<0-255>}` | A channel changed |

`val` goes out for changes from **any** source, so a fader moved over HTTP, over
the socket, from MQTT or from the serial console shows up in every open browser.

## How the UI uses it

Writes are coalesced per channel and flushed every 30 ms, so a drag costs one
message per channel per interval rather than one per pixel, with the release
always sending the final value.

When the module is off or the socket drops, it falls back to
`POST /api/devices/…/channel/…` on the same schedule and keeps retrying the
socket in the background. **Settings**, **Info** shows which transport is
actually in use.

## The echo problem, and why there is a delay

A client that has just moved a fader will receive its own `val` frame back a
moment later, along with everyone else's. Applying it blindly is how a control
snaps backwards: the board's echo of an older value arrives after a newer local
one and undoes it.

The UI therefore ignores echoes for a channel it wrote to in the last 500 ms and
trusts its own value in that window. Beyond it, the board is the authority. This
matters if you write your own client: treat `val` as authoritative except for
what you have just sent yourself.

## Minimal client

```python
import json, websocket   # pip install websocket-client

ws = websocket.create_connection("ws://esp-dmx.local:81/?api_key=" + KEY)
print(ws.recv())  # {"t":"hello","clients":1}

ws.send(json.dumps({"t": "set", "d": "dev-a1b2c3", "o": 1, "v": 255}))
ws.send(json.dumps({"t": "seta", "a": 4, "v": 128}))

while True:
    print(ws.recv())
```

## When to use HTTP instead

Anything that fires once. A scene, a blackout, a fixture edit, a burst: those are
single events with a meaningful answer, and the socket carries neither replies
nor errors. Use the socket for streams of values and the
[HTTP API](http-api.md) for everything else.
