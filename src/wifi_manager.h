#pragma once

#include <ArduinoJson.h>

#include <vector>

struct WifiNet {
  String ssid;
  String password;
  int priority = 0;
};

// Owns the saved-network list and the radio's STA/AP state. Connects to the
// highest-priority reachable network, and falls back to its own access point.
class WifiManager {
 public:
  void begin();  // load saved networks
  void reloadNetworks();

  void addNetwork(const String& ssid, const String& password, int priority);
  bool removeNetwork(const String& ssid);
  const std::vector<WifiNet>& networks() const { return _networks; }
  void networksToJson(JsonArray out) const;  // full entries, passwords included
  void scan(JsonArray out);                  // visible networks [{ssid, rssi}]

  bool connectKnown(uint32_t timeoutMs = 8000, int passes = 3, uint32_t pauseMs = 2000);
  bool tryConnect(const String& ssid, const String& password, uint32_t timeoutMs = 8000);
  void startAp(const String& ssid, const String& password, const String& ip);

  // Services mDNS. The ESP8266 responder needs pumping; the ESP32 one does not,
  // so this is a no-op there.
  void loop();

  // USB-only mode: the radio was never brought up, so the main loop skips the
  // web server, mDNS and MQTT entirely.
  void setDisabled() { _disabled = true; }
  bool disabled() const { return _disabled; }

  void statusToJson(JsonObject out) const;
  const String& mode() const { return _mode; }
  const String& hostname() const { return _hostname; }

 private:
  void save();
  void applyStaticIp();
  // Reads system.json, sanitises the hostname and hands it to the radio. Must
  // run after WiFi.mode() and before WiFi.begin() to take effect.
  void applyHostname();
  void startMdns();

  std::vector<WifiNet> _networks;
  String _mode;    // "" | "sta" | "ap"
  String _apSsid;
  String _hostname;
  bool _disabled = false;
};
