# Hardware support

The firmware builds from one codebase for two chip families: the **ESP32 family**
(the primary target) and the **ESP8266** (a lighter, cheaper option). The
board-specific DMX transmit path sits behind a small hardware abstraction layer,
so the web UI, the REST API, the MQTT bridge and the serial console behave
identically on both.

The two families are **not** equal in what they can do, and this page is the
honest map of that. See [README.md](README.md) for the build steps,
[Wiring](docs/wiki/wiring.md) for the circuit, and [TODO.md](TODO.md) for the
roadmap the second table below refers to.

## Supported boards

| Board | Chip | PlatformIO env | Role |
|---|---|---|---|
| Wemos / Lolin S2 Mini | ESP32-S2 | `s2mini`, `s2mini_headless` | Primary, full capability |
| Wemos D1 mini | ESP8266 | `d1mini`, `d1mini_headless` | Lightweight output node |

Any ESP32-family board (ESP32, S2, S3, C3) works with the esp32 code path: add an
environment in `platformio.ini` pointing at your board. Any ESP8266 board works
with the esp8266 path, with DMX output fixed to GPIO2.

## What each chip can do in this firmware

### Working today

| Feature | ESP32 family | ESP8266 |
|---|---|---|
| DMX output, one universe | ✅ | ✅ |
| Served web UI | ✅ | ✅ (RAM is tighter) |
| Headless build (`WITH_WEBUI=0`) | ✅ | ✅ (recommended when RAM is tight) |
| REST API | ✅ | ✅ |
| MQTT + Home Assistant discovery | ✅ | ✅ |
| Multi-network WiFi + hotspot fallback | ✅ | ✅ |
| Static IP | ✅ | ✅ |
| Serial console | ✅ (native USB) | ✅ (UART0) |
| Configurable DMX TX pin | ✅ | ❌ fixed to `GPIO2` |
| DMX direction pin (DE/RE on a GPIO) | ✅ | ✅ |

### On the roadmap (what the chip can support)

| Feature | ESP32 family | ESP8266 |
|---|---|---|
| DMX **input** (read a lighting desk) | ✅ via esp_dmx | ⚠️ possible, but it costs the serial console. See below |
| **RDM** (E1.20) | ✅ via esp_dmx | ❌ |
| **Several universes** per board | ✅ one per hardware UART | ❌ single usable TX UART |
| Art-Net / sACN input to DMX out | ✅ | ✅ (output side only) |
| ESP-NOW parent / child mesh | ✅ parent **or** child | ✅ child only |
| Scenes, emergency stop, grand master, profiles | ✅ | ✅ |
| OTA firmware update | ✅ | ✅ |

RDM and multiple universes are **ESP32 only**, and that is a chip limit rather
than a missing library: no ESP8266 library can add them, for the reasons below.
**DMX input is the exception.** The ESP8266 can receive DMX, and what stands in
the way is a design choice about the serial console rather than the silicon. That
is spelled out below too, because the difference decides whether it is worth
attempting.

## Why they differ

| | ESP32-S2 (primary) | ESP32 / S3 | ESP32-C3 | ESP8266 |
|---|---|---|---|---|
| Cores | 1 | 2 | 1 | 1 |
| Clock | 240 MHz | 240 MHz | 160 MHz | 80 / 160 MHz |
| RAM | 320 KB (+2 MB PSRAM on the Mini) | 512 KB | 400 KB | ~80 KB (~50 KB usable heap) |
| Native USB | yes | S3 yes, classic no | yes | no (needs a USB-serial chip) |
| Hardware UARTs | 2 | 3 | 2 | 2, but UART1 is TX-only |
| ESP-IDF RS-485 UART driver | yes | yes | yes | no |

Two of the ESP8266's limits are walls that no library gets around:

- **One core, shared with WiFi.** The DMX frame is generated in software on the
  same core that runs the network stack, so it picks up jitter under load. RDM,
  which needs microsecond-tight bus turnaround, is not realistic here.
- **No RS-485 UART driver.** The esp_dmx library is built on the ESP-IDF UART
  driver, which only exists on the ESP32 family. That driver is what lets the
  ESP32 offload DMX break and frame timing to the peripheral instead of the loop.

The third is not a wall, and calling it one would be wrong:

- **Two UARTs, one of which is the console.** UART1 has TX only (`GPIO2`), and that
  is the DMX output. Everything else the chip has to offer lives on UART0, which is
  where the console and the boot log are, so a second universe has nowhere to go.
  **DMX input, however, is a different question.** UART0's receiver is perfectly
  capable of it: the ESP8266 has a hardware break detector, the `UIBD` bit in the
  `U0IS` interrupt status register, and
  [LXESP8266DMX](https://github.com/claudeheintz/LXESP8266DMX) uses exactly that to
  read a universe at 250 kbaud 8N2 on `GPIO3`, output on UART1 and input on UART0
  running at the same time.

What DMX input costs on that chip is the console, and that part is real. The D1
mini reaches its USB-serial chip over `GPIO1` and `GPIO3`, and a UART has one baud
divider for both directions, so pointing UART0 at DMX takes the console with it.
Output can still be read on a terminal set to 250000, but nothing can be typed
back, because that wire is carrying DMX. An ESP8266 that reads DMX is an ESP8266
configured over WiFi and nothing else.

**A software UART does not rescue this, and it is the obvious next thought.**
[EspSoftwareSerial](https://github.com/plerup/espsoftwareserial) tops out at
115200 baud and is only dependable nearer 19200, because interrupt timing on this
chip drifts under WiFi load. DMX wants 250000, held steady across 23 ms of
back-to-back slots, with an 88 µs break measured rather than read from a flag, and
no checksum or retransmission to hide a dropped bit. It is the wrong tool for that
signal.

The reverse is sound, though, if the console is what has to survive: `Serial.swap()`
moves UART0 to `GPIO13`/`GPIO15`, leaving DMX input on hardware at `GPIO13`, DMX
output on UART1 at `GPIO2`, and `GPIO1`/`GPIO3` free for a software console at
19200 that still reaches the onboard USB chip. Input needs only RX, so nothing need
hang off `GPIO15`, which has to stay low at boot. The costs are a slower console, a
74880 baud ROM boot log that looks like noise, and the odd typed character lost to
the DMX interrupt while a universe is flowing.

> [!NOTE]
> The ESP32-S2 is itself **single-core**, so its edge over the ESP8266 is not a
> second core. It is the far larger RAM, native USB, faster clock, and above all
> the hardware UART driver esp_dmx uses to keep DMX timing off the main loop.

## DMX output drivers

DMX transmit is the one place the two chips run different code, each behind the
same `dmxbackend::` facade so nothing else in the firmware notices:

| Chip | Driver | Where |
|---|---|---|
| ESP32 family | [esp_dmx](https://github.com/someweisguy/esp_dmx) (Mitch Weisbrod) | `lib_deps` on the `s2mini*` envs only |
| ESP8266 | Ours | [src/dmx/dmx_backend_esp8266.cpp](src/dmx/dmx_backend_esp8266.cpp) |

esp_dmx does not run on the ESP8266, which is why the dependency is pinned to its
own environments. It also carries the input and RDM support the roadmap needs, and
it hands the frame to a hardware UART driver, so the timing does not depend on how
soon the main loop comes back.

The ESP8266 has no such driver, so the backend is our own UART1 code: it holds TX
low with the UART's break bit, then feeds the FIFO a chunk per loop pass rather
than writing 513 slots in one blocking call. Only the break and the mark block,
around 200 µs of the 22.6 ms a frame spends on the wire. Chunking is invisible to
a receiver, since DMX allows up to a second of mark between slots.

It replaced [ESPDMX](https://github.com/Rickgg/ESP-Dmx) (Rick), which is
**GPL-3.0-or-later**. Linking it made a combined work that the GPL requires to be
redistributable under the GPL, which [the licence here](LICENSE) is not, so no
ESP8266 binary could be published. Writing the transmit path ourselves settled
that rather than working around it.

**It transmits and does not receive**, and on this chip that is structural: UART1
has no RX pin at all. An ESP8266 that has to read a universe needs UART0, the one
the serial console sits on. [LXESP8266DMX](https://github.com/claudeheintz/LXESP8266DMX)
(BSD-3-Clause) does exactly that split and would sit behind the same facade.

## Choosing a board

- **Cheapest single-universe output node:** ESP8266 (D1 mini). It does everything
  in the "working today" table and nothing in the roadmap table.
- **Full capability (DMX input, RDM, several universes, mesh parent):** an ESP32
  family board. The S2 Mini is the tested default.
- **ESP8266 size and price with ESP32 capability:** the **ESP32-C3**. It is as
  small and cheap as an ESP8266 but part of the ESP32 family, so esp_dmx runs on
  it and it clears the whole roadmap. It uses the existing esp32 code path
  unchanged; adding it is just a new environment in `platformio.ini`.

The parent / child mesh on the roadmap maps straight onto this: a **parent** (patched
into a desk, reading DMX, relaying it) should be an ESP32 family board, while
**children** that only put one universe on the wire can be cheap ESP8266s.

## Pin reference

| | ESP32-S2 | ESP8266 |
|---|---|---|
| DMX TX (`DI` on the MAX485) | `IO4`, configurable | `GPIO2`, fixed (Serial1) |
| DMX direction (`DE`+`RE`) | `IO18`, configurable, disabled by default | configurable GPIO, disabled by default |
| Serial console | native USB (CDC) | UART0, through the USB-serial chip |

Leave the direction pin disabled when `DE` and `RE` are tied to VCC, which is the
reference wiring. See [README.md](README.md#about-the-de-re-pin).
