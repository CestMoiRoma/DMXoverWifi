# Wiring

[Wiki index](../../WIKI.md)

DMX is RS-485 on an XLR connector. The board speaks UART, so a MAX485 sits
between them and does the level conversion. That is the whole circuit.

![MAX485 wiring for a DMX output](../images/wiring-espdmx.png)

The photograph is a Wemos D1 mini. The RS-485 side is identical on any board:
take the data signal from the board's DMX TX pin and wire the transceiver as
below.

## Connections

| Microcontroller | MAX485 | Notes |
|---|---|---|
| DMX TX pin | `DI` | `IO4` on the ESP32 and configurable, `GPIO2` on the ESP8266 and fixed |
| `5V` | `VCC` | The MAX485 wants 5 V. Its `A` and `B` outputs are differential and the fixture does not care what the logic side runs at |
| `GND` | `GND` | |
| not wired | `DE` + `RE` | Tied together to VCC here, so the transceiver always transmits |
| not wired | `RO` | Transmit only, so there is nothing to receive |

| MAX485 | XLR pin | DMX signal |
|---|---|---|
| `GND` | 1 | Shield and common |
| `B` | 2 | Data minus |
| `A` | 3 | Data plus |

Pin 2 is minus and pin 3 is plus. Swapping them is the single most common
wiring mistake, and it does not damage anything: the fixture simply never
responds. If a rig is dead and the electronics look right, try the two data
lines the other way round before suspecting the board.

## The DE/RE pin

`DE` (driver enable) and `RE` (receiver enable) decide which direction the
transceiver faces. This firmware only ever transmits, so tying both to VCC is
correct and costs a GPIO less. That is the default, with `dmx_dir_pin_enabled`
set to `false`.

If your board or a ready-made module routes them to a GPIO instead, enable the
direction pin and name it:

- in the UI, under **Settings**, **Config**, **DMX output**
- over serial, with `Set-System dir-pin enable=true pin=IO18`

Reboot afterwards. The DMX driver reads its pins once, at startup.

While the pin is disabled the UI hides the field entirely rather than showing a
setting with no effect.

## Pin labels

Pin names are cosmetic and only the digits are read: `IO4`, `GPIO4` and `4` all
mean GPIO 4. The defaults live in [dev.env](../../dev.env) and are compiled in,
so a build for different hardware changes them in one place.

On the ESP8266 the output is fixed to `Serial1`, which is GPIO 2, by the
transmit backend. The tx pin setting is stored there and has no effect. The
direction pin still works as an ordinary GPIO.

## Powering it

USB is fine for a board driving a few fixtures, and it is what the console and
the flashing process use anyway. The MAX485 draws almost nothing.

The DMX line itself carries no power. Every fixture has its own supply, and the
shield is a shield rather than a ground return: connect it at pin 1 and leave
the fixture end to the fixture's own arrangements.

## A terminator, and when to bother

A proper DMX chain ends in a 120 ohm resistor across pins 2 and 3 of the last
fixture. On a short run of two or three fixtures on a bench you will usually get
away without one. On a long run, or one that behaves differently depending on
what is plugged in, fit it: reflections on an unterminated line look exactly
like an intermittent firmware fault and will cost you an evening.
