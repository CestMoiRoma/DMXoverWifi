#pragma once

#include <Arduino.h>

// Build-time web UI toggle. A headless build keeps the REST API, MQTT, WiFi and
// DMX but drops the served HTML/JS/CSS, saving flash and RAM. Pick it at flash
// time by choosing the *_headless PlatformIO environment.
#ifndef WITH_WEBUI
#define WITH_WEBUI 1
#endif

// Per-board DMX defaults.
//
// On ESP8266 the DMX output is fixed to Serial1 (UART1 TX = GPIO2) by the
// ESPDMX-derived backend, so the tx pin is only a label there. The ESP32
// backend honours the configured pin as a real GPIO.
#if defined(ESP8266)
  #define DEFAULT_DMX_TX_PIN "GPIO2"
  #define BOARD_NAME "esp8266"
#else
  #define DEFAULT_DMX_TX_PIN "IO4"
  #define BOARD_NAME "esp32"
#endif
#define DEFAULT_DMX_DIR_PIN "IO18"

// Config lives as JSON files under this LittleFS directory (written at runtime).
// Static web assets live under /www (flashed from fsdata/ via `uploadfs`).
#define DATA_DIR "/data"

// Parse a pin label into a raw GPIO number: "IO4" -> 4, "GPIO18" -> 18,
// "4" -> 4. Returns -1 when the label carries no digits. Pin config uses raw
// GPIO numbers; the "IO"/"GPIO" prefixes are cosmetic.
inline int resolvePin(const String& name) {
  const char* s = name.c_str();
  size_t i = 0;
  while (s[i] && (s[i] < '0' || s[i] > '9')) i++;
  if (!s[i]) return -1;
  return atoi(s + i);
}
