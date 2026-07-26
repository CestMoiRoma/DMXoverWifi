// DMX transmit backend for ESP32 / ESP32-S2.
//
// Thin adapter over the esp_dmx library (someweisguy/esp_dmx, v4), pulled in as
// a lib_deps dependency on the s2mini* environments only. esp_dmx drives the
// break and mark-after-break in the hardware UART driver, so the timing does not
// depend on how fast a software call returns, and there is nothing for poll() to
// do here. The ESP8266 has no such driver and clocks its own frames out.

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
  // Wait for the *previous* frame here rather than for this one at the end.
  //
  // A 513-slot frame takes about 23 ms on the wire, and the driver refreshes
  // every 25 ms. Waiting after dmx_send meant the main loop sat in this call for
  // 23 ms out of every 25, so the board spent over ninety percent of its life
  // doing nothing while HTTP connections queued up behind it and were reset.
  // Waiting first costs nothing instead: by the time the next refresh comes
  // round the UART has long finished, and the loop gets those 23 ms back.
  dmx_wait_sent(DMX_PORT, DMX_TIMEOUT_TICK);

  // frame[0] is the DMX start code, frame[1..512] the slots: exactly the layout
  // esp_dmx expects.
  dmx_write(DMX_PORT, frame, len);
  dmx_send(DMX_PORT);
}

void poll() {
  // esp_dmx clocks the frame out of the hardware driver; nothing to feed.
}

}  // namespace dmxbackend

#endif
