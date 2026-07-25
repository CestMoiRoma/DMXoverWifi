// DMX transmit backend for ESP32 / ESP32-S2.
//
// Mirrors the method validated on the Wemos S2 Mini under CircuitPython: drive
// the break by hand on the TX pin rather than by switching the UART baudrate.
// Baudrate-switching was unreliable on the S2 because UART writes return before
// the FIFO drains, so the break byte shifted out at the wrong rate and fell
// under the 88us DMX minimum.

#if !defined(ESP8266)

#include "dmx_backend.h"

static const uint32_t DMX_BAUD = 250000;   // 8N2
static const uint32_t BREAK_US = 250;      // spec minimum 88us, kept generous
static const uint32_t MAB_US = 30;         // mark after break, spec minimum 8us

static int s_txPin = -1;

namespace dmxbackend {

void begin(int txPin) {
  s_txPin = txPin;
  // Serial1 is free on the S2 (USB CDC is the console). rx unused.
  Serial1.begin(DMX_BAUD, SERIAL_8N2, -1, s_txPin);
}

void sendFrame(const uint8_t* frame, uint16_t len) {
  if (s_txPin < 0) return;

  Serial1.flush();
  Serial1.end();

  pinMode(s_txPin, OUTPUT);
  digitalWrite(s_txPin, LOW);   // break: hold TX low
  delayMicroseconds(BREAK_US);
  digitalWrite(s_txPin, HIGH);  // mark after break: idle high
  delayMicroseconds(MAB_US);

  Serial1.begin(DMX_BAUD, SERIAL_8N2, -1, s_txPin);
  Serial1.write(frame, len);
  Serial1.flush();
}

}  // namespace dmxbackend

#endif
