// DMX transmit backend for ESP8266.
//
// Derived from ESPDMX by Rick <ricardogg95@gmail.com> (GNU-style license,
// https://github.com/Rickgg/ESP-Dmx), the library that lives natively on the
// ESP8266. Output is fixed to Serial1 (UART1 TX = GPIO2); the break is made by
// switching the UART to a slower baudrate for a single 0x00 byte, which is
// reliable on the 8266's UART1 (unlike on the ESP32-S2).

#if defined(ESP8266)

#include "dmx_backend.h"

static const uint32_t DMX_SPEED = 250000;    // 8N2
static const uint32_t BREAK_SPEED = 83333;   // 8N1, one 0x00 ~ 88us of low line

namespace dmxbackend {

void begin(int /*txPin*/) {
  // ESP8266 DMX is hard-wired to Serial1 (GPIO2); the configured pin is a label
  // only. See config.h.
  Serial1.begin(DMX_SPEED, SERIAL_8N2);
}

void sendFrame(const uint8_t* frame, uint16_t len) {
  // Break + mark after break.
  Serial1.begin(BREAK_SPEED, SERIAL_8N1);
  Serial1.write((uint8_t)0);
  Serial1.flush();
  delayMicroseconds(120);

  // Data.
  Serial1.begin(DMX_SPEED, SERIAL_8N2);
  Serial1.write(frame, len);
  Serial1.flush();
}

}  // namespace dmxbackend

#endif
