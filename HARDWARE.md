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
| DMX **input** (read a lighting desk) | ✅ via esp_dmx | ❌ |
| **RDM** (E1.20) | ✅ via esp_dmx | ❌ |
| **Several universes** per board | ✅ one per hardware UART | ❌ single usable TX UART |
| Art-Net / sACN input to DMX out | ✅ | ✅ (output side only) |
| ESP-NOW parent / child mesh | ✅ parent **or** child | ✅ child only |
| Scenes, emergency stop, grand master, profiles | ✅ | ✅ |
| OTA firmware update | ✅ | ✅ |

The DMX-side roadmap (input, RDM, multiple universes) is **ESP32 only**. It is a
chip limit, not a missing library: no ESP8266 library can add it, for the reasons
below.

## Why they differ

| | ESP32-S2 (primary) | ESP32 / S3 | ESP32-C3 | ESP8266 |
|---|---|---|---|---|
| Cores | 1 | 2 | 1 | 1 |
| Clock | 240 MHz | 240 MHz | 160 MHz | 80 / 160 MHz |
| RAM | 320 KB (+2 MB PSRAM on the Mini) | 512 KB | 400 KB | ~80 KB (~50 KB usable heap) |
| Native USB | yes | S3 yes, classic no | yes | no (needs a USB-serial chip) |
| Hardware UARTs | 2 | 3 | 2 | 2, but UART1 is TX-only |
| ESP-IDF RS-485 UART driver | yes | yes | yes | no |

The ESP8266's ceiling comes from three walls that no library gets around:

- **One usable DMX UART.** UART1 has TX only (`GPIO2`), which is the single DMX
  output. UART0's pins are the console and boot log. There is no second clean UART
  for a second universe, and no receive pin free for reliable DMX input.
- **One core, shared with WiFi.** The DMX frame is generated in software on the
  same core that runs the network stack, so it picks up jitter under load. RDM,
  which needs microsecond-tight bus turnaround, is not realistic here.
- **No RS-485 UART driver.** The esp_dmx library is built on the ESP-IDF UART
  driver, which only exists on the ESP32 family. That driver is what lets the
  ESP32 offload DMX break and frame timing to the peripheral instead of the loop.

> [!NOTE]
> The ESP32-S2 is itself **single-core**, so its edge over the ESP8266 is not a
> second core. It is the far larger RAM, native USB, faster clock, and above all
> the hardware UART driver esp_dmx uses to keep DMX timing off the main loop.

## DMX output libraries

DMX transmit is the one place the two chips run different code, each behind the
same `dmxbackend::` facade so nothing else in the firmware notices:

| Chip | Library | Scope in `platformio.ini` |
|---|---|---|
| ESP32 family | [esp_dmx](https://github.com/someweisguy/esp_dmx) (Mitch Weisbrod) | `s2mini*` envs only |
| ESP8266 | [ESPDMX](https://github.com/Rickgg/ESP-Dmx) (Rick) | `d1mini*` envs only |

Each dependency is pinned to its own environments, because esp_dmx does not run
on the ESP8266 and ESPDMX does not run on the ESP32. esp_dmx also carries the
input and RDM support the roadmap needs; ESPDMX is transmit only.

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
