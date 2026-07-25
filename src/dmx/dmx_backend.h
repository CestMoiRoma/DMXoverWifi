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
void sendFrame(const uint8_t* frame, uint16_t len);

}  // namespace dmxbackend
