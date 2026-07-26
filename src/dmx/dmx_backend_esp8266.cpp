// DMX transmit backend for ESP8266.
//
// Our own UART1 driver. It replaces the ESPDMX library (Rick,
// https://github.com/Rickgg/ESP-Dmx), which is GPL-3.0-or-later: linking it made
// a combined work that cannot be handed out under this project's licence, so no
// ESP8266 image could be published. None of it survives here; what follows is
// written against the ESP8266 UART registers and the DMX512 timings.
//
// UART1 transmits and does not receive, and its TX is GPIO2 and nothing else, so
// the configured pin is a label on this chip. A frame is:
//
//   BREAK  92 us low at least, which the UART can hold on its own
//   MAB    12 us high at least, the mark after break
//   DATA   up to 513 slots at 250000 baud, 8N2, the first being the start code
//
// 513 slots at 44 us each is about 22.6 ms of wire time, and the driver asks for
// a frame every 25 ms. Writing all of it in one call would park the loop for as
// long as the 128-byte FIFO takes to drain, which is exactly the fault the ESP32
// backend was fixed for and which docs/wiki/timing.md tells the story of. On the
// ESP8266 it would also be sharing that time with the WiFi stack.
//
// So the frame is clocked out as a state machine: sendFrame() sends the break and
// returns, poll() tops up the FIFO with whatever room it reports, and the loop
// runs in between. Only the break and the mark block, and together they are under
// 200 us.
//
// Feeding in chunks is not something the wire minds. DMX allows up to a second of
// mark between slots, so a late pass leaves a longer gap and nothing worse. The
// one thing that must not slip is the break, which is why it is timed inline
// rather than spread across passes.

#if defined(ESP8266)

#include <Arduino.h>
#include <esp8266_peri.h>

#include "dmx_backend.h"

namespace {

constexpr int UART = 1;              // Serial1
constexpr uint32_t DMX_BAUD = 250000;
constexpr uint16_t MAX_FRAME = 513;  // start code + 512 slots

// Over the 92 us and 12 us the standard asks of a transmitter. Both are minima
// with a one second ceiling, so the margin costs nothing and an interrupt landing
// in the middle of either only ever makes it longer.
constexpr uint16_t BREAK_US = 120;
constexpr uint16_t MAB_US = 16;

// One slot at 250000 baud with two stop bits is 11 bits, so 44 us. Waited out
// once the FIFO reports empty, because the byte already handed to the shift
// register is no longer counted there and the break would cut it in half.
constexpr uint16_t SLOT_US = 44;

enum class Phase : uint8_t {
  Idle,   // nothing in flight
  Drain,  // waiting for the previous frame to leave the UART
  Data,   // break sent, feeding slots
};

Phase s_phase = Phase::Idle;
uint8_t s_frame[MAX_FRAME];
uint16_t s_len = 0;
uint16_t s_sent = 0;

// What the FIFO still holds. The core reads the same field for its own accounting.
inline uint8_t fifoUsed() {
  return (USS(UART) >> USTXC) & 0xff;
}

// UCBRK holds TX low for as long as it is set, which is a DMX break with no
// baud-rate games and no byte written to fake one.
void breakAndMark() {
  USC0(UART) |= (1 << UCBRK);
  delayMicroseconds(BREAK_US);
  USC0(UART) &= ~(1 << UCBRK);
  delayMicroseconds(MAB_US);
}

}  // namespace

namespace dmxbackend {

void begin(int /*txPin*/) {
  Serial1.begin(DMX_BAUD, SERIAL_8N2);
  s_phase = Phase::Idle;
  s_len = 0;
  s_sent = 0;
}

void sendFrame(const uint8_t* frame, uint16_t len) {
  // The last frame is still going out. Dropping this one is the right answer
  // rather than queueing it: the driver refreshes from the same buffer 25 ms
  // later, so the wire gets the current values instead of a stale copy.
  if (s_phase != Phase::Idle) return;

  if (len > MAX_FRAME) len = MAX_FRAME;
  memcpy(s_frame, frame, len);
  s_len = len;
  s_sent = 0;
  s_phase = Phase::Drain;

  // Break now if the wire is already clear, rather than a pass from now.
  poll();
}

void poll() {
  switch (s_phase) {
    case Phase::Idle:
      return;

    case Phase::Drain:
      if (fifoUsed() > 0) return;
      delayMicroseconds(SLOT_US);
      breakAndMark();
      s_phase = Phase::Data;
      [[fallthrough]];  // there is a whole FIFO free, so start filling it

    case Phase::Data: {
      // The core spins when the FIFO is full and calls it full at 127 of its
      // 128 bytes, so stop one short of the room it reports and this never
      // blocks.
      int room = Serial1.availableForWrite() - 1;
      if (room <= 0) return;
      uint16_t left = s_len - s_sent;
      uint16_t n = ((uint16_t)room < left) ? (uint16_t)room : left;
      Serial1.write(s_frame + s_sent, n);
      s_sent += n;
      if (s_sent >= s_len) s_phase = Phase::Idle;
      return;
    }
  }
}

}  // namespace dmxbackend

#endif
