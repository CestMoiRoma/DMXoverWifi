// DMX transmit backend for ESP8266.
//
// Thin adapter over the ESPDMX library (Rick, https://github.com/Rickgg/ESP-Dmx),
// pulled in as a lib_deps dependency on the d1mini* environments only. ESPDMX is
// ESP8266-native: output is fixed to Serial1 (UART1 TX = GPIO2) and it cannot
// run on the ESP32.

#if defined(ESP8266)

#include <ESPDMX.h>

#include "dmx_backend.h"

static DMXESPSerial s_dmx;

namespace dmxbackend {

void begin(int /*txPin*/) {
  // ESPDMX is hard-wired to Serial1 (GPIO2); the configured pin is a label only.
  s_dmx.init(512);
}

void sendFrame(const uint8_t* frame, uint16_t len) {
  // frame[0] is the DMX start code, which ESPDMX manages internally; push the
  // channel slots and let the library clock out the frame (break, MAB, data).
  for (uint16_t i = 1; i < len; i++) {
    s_dmx.write(i, frame[i]);
  }
  s_dmx.update();
}

}  // namespace dmxbackend

#endif
