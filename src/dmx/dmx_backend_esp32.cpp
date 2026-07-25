// DMX transmit backend for ESP32 / ESP32-S2.
//
// Thin adapter over the esp_dmx library (someweisguy/esp_dmx, v4), pulled in as
// a lib_deps dependency on the s2mini* environments only. esp_dmx drives the
// break and mark-after-break in the hardware UART driver, so the timing does not
// depend on how fast a software call returns. ESPDMX is ESP8266-only and is not
// used here.

#if !defined(ESP8266)

#include <esp_dmx.h>

#include "dmx_backend.h"

static const dmx_port_t DMX_PORT = DMX_NUM_1;

namespace dmxbackend {

void begin(int txPin) {
  dmx_config_t config = DMX_CONFIG_DEFAULT;
  dmx_personality_t personalities[] = {{512, "DMX over WiFi"}};
  dmx_driver_install(DMX_PORT, &config, personalities, 1);
  // tx only: no rx, and no RTS/direction pin (DmxDriver holds DE/RE high itself,
  // or it is tied to VCC in hardware).
  dmx_set_pin(DMX_PORT, txPin, -1, -1);
}

void sendFrame(const uint8_t* frame, uint16_t len) {
  // frame[0] is the DMX start code, frame[1..512] the slots: exactly the layout
  // esp_dmx expects.
  dmx_write(DMX_PORT, frame, len);
  dmx_send(DMX_PORT);
  dmx_wait_sent(DMX_PORT, DMX_TIMEOUT_TICK);
}

}  // namespace dmxbackend

#endif
