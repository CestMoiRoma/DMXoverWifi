#include "dmx_driver.h"

#include "dmx_backend.h"

void DmxDriver::begin(int txPin, int dirPin) {
  _dirPin = dirPin;
  if (_dirPin >= 0) {
    pinMode(_dirPin, OUTPUT);
    digitalWrite(_dirPin, HIGH);  // transmit-enabled; output-only, never toggled
  }
  dmxbackend::begin(txPin);
}

void DmxDriver::setChannel(uint16_t address, int value) {
  if (address < 1 || address > DMX_CHANNELS) return;
  if (value < 0) value = 0;
  if (value > 255) value = 255;
  // Only a real change counts as dirty. A fader held still resends the same
  // value forty times a second, and treating that as a change would keep the
  // save-guard permanently about to write.
  if (_buffer[address] == (uint8_t)value) return;
  _buffer[address] = (uint8_t)value;
  _dirty = true;
}

uint8_t DmxDriver::getChannel(uint16_t address) const {
  if (address < 1 || address > DMX_CHANNELS) return 0;
  return _buffer[address];
}

void DmxDriver::sendFrame() {
  dmxbackend::sendFrame(_buffer, DMX_CHANNELS + 1);
}

void DmxDriver::refreshIfDue() {
  // Every pass, not only when a frame is due: a backend that clocks the frame
  // out itself gets the loop back here to feed the next chunk of it.
  dmxbackend::poll();

  uint32_t now = millis();
  if (now - _lastSend >= FRAME_INTERVAL_MS) {
    sendFrame();
    _lastSend = now;
  }
}
