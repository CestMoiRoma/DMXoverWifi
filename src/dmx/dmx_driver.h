#pragma once

#include <Arduino.h>

// Board-independent DMX universe: holds the channel buffer, throttles the frame
// rate, and delegates the actual break-and-shift to the per-board backend.
// DeviceManager reads and writes channels through this class alone.
class DmxDriver {
 public:
  static const uint16_t DMX_CHANNELS = 512;

  // dirPin is optional (pass -1): some MAX485 boards tie DE+RE straight to VCC
  // instead of a GPIO, so there is nothing for the MCU to drive.
  void begin(int txPin, int dirPin = -1);

  void setChannel(uint16_t address, int value);   // address 1..512
  uint8_t getChannel(uint16_t address) const;      // address 1..512

  // True once a write has actually changed something. The one place every
  // write passes through, whatever drove it: the UI, MQTT, the websocket, the
  // serial console, the binary protocol or a blackout. Anything watching for
  // changes hooks here rather than trying to catch them at each source.
  bool dirty() const { return _dirty; }
  void clearDirty() { _dirty = false; }

  void refreshIfDue();
  void sendFrame();

 private:
  static const uint32_t FRAME_INTERVAL_MS = 25;    // ~40 Hz

  uint8_t _buffer[DMX_CHANNELS + 1] = {0};          // [0] is the DMX start code
  int _dirPin = -1;
  uint32_t _lastSend = 0;
  bool _dirty = false;
};
