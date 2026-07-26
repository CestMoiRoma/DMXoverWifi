#pragma once

#include <ArduinoJson.h>

#include <vector>

#include "config.h"

// Addressing is per network, not per board: the same rig plugs into a venue
// that hands out DHCP one night and wants a fixed address the next, and the
// answer belongs to the network rather than to the board.
struct WifiNet {
  String ssid;
  String password;
  int priority = 0;  // higher wins; the UI keeps these in sync with list order
  String ip_mode = "dhcp";  // "dhcp" | "static"
  String static_ip;
  String static_netmask = "255.255.255.0";
  String static_gateway;
  String static_dns = DEFAULT_DNS;
};

// Owns the saved-network list and the radio's STA/AP state. Connects to the
// highest-priority reachable network, and falls back to its own access point.
class WifiManager {
 public:
  void begin();  // load saved networks
  void reloadNetworks();

  void addNetwork(const String& ssid, const String& password, int priority);
  bool removeNetwork(const String& ssid);
  // Replaces the whole list from an ordered array, assigning priorities from
  // the order so that first means highest. This is what the drag-and-drop list
  // and the per-network editor both post back.
  void replaceNetworks(JsonArrayConst in);
  const std::vector<WifiNet>& networks() const { return _networks; }
  void networksToJson(JsonArray out) const;  // full entries, passwords included
  // Starts a scan and reports progress: {scanning, networks[]}. Asynchronous,
  // because a blocking scan freezes the loop, and the loop is also what keeps
  // DMX going out.
  void scan(JsonObject out);

  bool connectKnown(uint32_t timeoutMs = 8000, int passes = 3, uint32_t pauseMs = 2000);
  bool tryConnect(const WifiNet& net, uint32_t timeoutMs = 8000);
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
  void sortByPriority();
  void applyAddressing(const WifiNet& net);
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
