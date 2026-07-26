#pragma once

#include <Arduino.h>

// Build-time web UI toggle. A headless build keeps the REST API, MQTT, WiFi and
// DMX but drops the served HTML/JS/CSS, saving flash and RAM. Pick it at flash
// time by choosing the *_headless PlatformIO environment.
#ifndef WITH_WEBUI
#define WITH_WEBUI 1
#endif

// ---- factory defaults ----
//
// Every value below comes from dev.env, compiled in by tools/dev_env.py. What
// is written here is the fallback for a build without that file, so a checkout
// with no dev.env still produces a board that works. Change them in dev.env.
//
// These are what a board falls back to, not what it necessarily runs: anything
// saved in its settings, or seeded from a .env, is read first.

// On ESP8266 the DMX output is fixed to Serial1 (UART1 TX = GPIO2), which is the
// only pin that UART can transmit on, so the tx pin is a label there. The ESP32
// backend honours the configured pin as a real GPIO.
#if defined(ESP8266)
  #define BOARD_NAME "esp8266"
  #ifndef DEFAULT_DMX_TX_PIN_ESP8266
  #define DEFAULT_DMX_TX_PIN_ESP8266 "GPIO2"
  #endif
  #undef DEFAULT_DMX_TX_PIN
  #define DEFAULT_DMX_TX_PIN DEFAULT_DMX_TX_PIN_ESP8266
#else
  #define BOARD_NAME "esp32"
  #ifndef DEFAULT_DMX_TX_PIN
  #define DEFAULT_DMX_TX_PIN "IO4"
  #endif
#endif

#ifndef DEFAULT_DMX_DIR_PIN
#define DEFAULT_DMX_DIR_PIN "IO18"
#endif

// The board on the network. The hostname doubles as the mDNS name.
#ifndef DEFAULT_HOSTNAME
#define DEFAULT_HOSTNAME "ESP-DMX"
#endif

// The config hotspot, raised when no known network answers.
#ifndef DEFAULT_AP_SSID
#define DEFAULT_AP_SSID "ESP-DMX"
#endif
#ifndef DEFAULT_AP_PASSWORD
#define DEFAULT_AP_PASSWORD "DMX4ALL1"
#endif
#ifndef DEFAULT_AP_IP
#define DEFAULT_AP_IP "1.1.1.1"
#endif

// Used when a static address is configured with no DNS server named.
#ifndef DEFAULT_DNS
#define DEFAULT_DNS "1.1.1.1"
#endif

// Where the MQTT bridge publishes unless told otherwise. The discovery prefix
// is Home Assistant's own default.
#ifndef DEFAULT_MQTT_BASE_TOPIC
#define DEFAULT_MQTT_BASE_TOPIC "dmxwifi"
#endif
#ifndef DEFAULT_MQTT_DISCOVERY_PREFIX
#define DEFAULT_MQTT_DISCOVERY_PREFIX "homeassistant"
#endif
#ifndef DEFAULT_MQTT_PORT
#define DEFAULT_MQTT_PORT 1883
#endif

// Who to credit and where to look for updates, both reported by /api/info. The
// repository is also what the settings page asks GitHub about.
#ifndef REPO_URL
#define REPO_URL "https://github.com/CestMoiRoma/DMXoverWifi"
#endif
#ifndef AUTHOR_NAME
#define AUTHOR_NAME "CestMoiRoma"
#endif
#ifndef AUTHOR_URL
#define AUTHOR_URL "https://github.com/CestMoiRoma"
#endif

// The WebSocket needs its own port: the Arduino web server cannot share 80 with
// a socket upgrade. Both the socket and the /api/info payload read it from here
// so the UI is never told a port the board is not on.
#ifndef WS_PORT_NUMBER
#define WS_PORT_NUMBER 81
#endif

// Which build this is, which is also the name of the release asset that fits
// this board. Set per environment in platformio.ini; the fallback keeps a
// hand-rolled build compiling.
#ifndef FW_TARGET
  #if defined(ESP8266)
    #define FW_TARGET "d1mini"
  #else
    #define FW_TARGET "s2mini"
  #endif
#endif

// Config lives as JSON files under this LittleFS directory. Nothing else is on
// the filesystem any more: the web UI travels inside the firmware, so an update
// never has to write over the partition holding these.
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
