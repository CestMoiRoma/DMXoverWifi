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
  _buffer[address] = (uint8_t)value;
}

uint8_t DmxDriver::getChannel(uint16_t address) const {
  if (address < 1 || address > DMX_CHANNELS) return 0;
  return _buffer[address];
}

void DmxDriver::sendFrame() {
  dmxbackend::sendFrame(_buffer, DMX_CHANNELS + 1);
}

void DmxDriver::refreshIfDue() {
  uint32_t now = millis();
  if (now - _lastSend >= FRAME_INTERVAL_MS) {
    sendFrame();
    _lastSend = now;
  }
}
