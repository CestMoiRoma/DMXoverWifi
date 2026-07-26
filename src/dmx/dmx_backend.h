#pragma once

#include <Arduino.h>

// Board-specific DMX transmit backend. Exactly one implementation compiles per
// build (guarded by ESP8266 / ESP32 macros). The rest of the firmware only ever
// talks to DmxDriver, never to these functions directly.
namespace dmxbackend {

// Bring up the UART used for DMX. On ESP8266 the pin is ignored (output is
// fixed to Serial1 / GPIO2); on ESP32 it is a real GPIO.
void begin(int txPin);

// Shift out one DMX frame: a break, a mark-after-break, then `len` bytes of
// `frame` (frame[0] is the DMX start code, frame[1..512] the channel data).
// A backend may return before the frame has finished, and finish it in poll().
void sendFrame(const uint8_t* frame, uint16_t len);

// Called from the main loop on every pass, for a backend that clocks a frame out
// itself rather than handing it to a hardware driver. The ESP8266 one feeds the
// UART here, a chunk per pass, so a 22.6 ms frame does not become 22.6 ms of
// blocked loop. On the ESP32 esp_dmx owns the transmission and this does nothing.
void poll();

}  // namespace dmxbackend
