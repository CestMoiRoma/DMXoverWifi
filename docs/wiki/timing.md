# Timing and latency

[Wiki index](../../WIKI.md)

> [!WARNING]
> The delay between a command and the fixture reacting is not guaranteed. It
> varies, and it can spike. Do not put this box anywhere a late or dropped cue
> matters.

The chain is browser or MQTT, then WiFi, then the HTTP or MQTT handler, then the
DMX buffer, then the next DMX frame. Only the last hop has anything like a fixed
cost.

| Stage | Behaviour |
|---|---|
| WiFi | Best effort. Retries, interference, a busy access point or a roaming client add tens to hundreds of milliseconds, unpredictably |
| MQTT | Adds a broker round trip |
| Main loop | `loop()` polls HTTP, the websocket, MQTT, the DMX refresh and the serial console in turn. No preemption and no priorities, so a slow request delays the next frame. On the ESP8266 the single core is shared with the WiFi stack too |
| DMX frame | The refresh interval is 25 ms, checked from the loop with `millis()` rather than driven by a timer interrupt. The break is generated in software around each frame |

## What is dependable

Once a value is in the buffer it keeps going out at roughly 40 frames a second,
so fixtures hold their state and do not flicker. It is the **arrival** of a new
value that has no deadline.

In practice:

- Fine for setting levels, static looks, colour changes, house lights and
  ambience.
- Not for anything that has to land on a beat, and not for pyro, moving trusses
  or anything safety related.
- Chases and effects should be generated on the fixture, using its built-in
  programs, rather than streamed channel by channel from a browser.

If you need deterministic timing, drive the rig from a real lighting desk or an
Art-Net or sACN node on a wired network.

## Measuring it

`/api/info` reports `loop_per_sec` and `loop_max_us`. That is the honest way to
see whether the board is keeping up, rather than inferring it from a browser
error.

A healthy idle board runs around a thousand passes a second with a worst pass
under 5 ms. Serving the page pushes the worst pass up for the duration of the
transfer, which is written synchronously.

## Things that have blocked this loop

Every one of these was found by watching `loop_max_us` rather than by reasoning
about the code, and each is worth knowing about if you add something that talks
to the network.

**The DMX transmit backend, 23 ms out of every 25.** A 513-slot frame takes about
23 ms on the wire, and the backend used to wait for it *after* sending. The board
answered the network about forty times a second and reset most connections.
Waiting for the *previous* frame before writing the next one costs nothing, since
the refresh comes round long after the UART has finished. The loop got some
twenty-five times faster.

**A WiFi scan, 7 seconds.** Synchronous scans block everything. It is
asynchronous now: the first call starts it and answers `{"scanning":true}`.

**An MQTT connect to a broker that was not there, 4.5 seconds per attempt.**
PubSubClient's own connect has a fifteen second default and no way to shorten the
TCP part alone. The TCP connection is now made separately with a 250 ms deadline
and handed over already open, and failures back off from 5 seconds to a minute. A
dead broker now costs a 2 ms pass.

The pattern is the same each time: a library call that blocks for as long as the
network takes, inside a loop that also has to feed DMX every 25 ms. If you add
one, give it a deadline.
