#pragma once

#include <ArduinoJson.h>

// Wired networking through a W5500 on SPI, as an alternative or an addition to
// WiFi. ESP32 only for now: the ESP8266 has neither the SPI headroom nor a
// tested wiring for it here.
//
// UNTESTED ON HARDWARE. Written against the W5500's documented behaviour, never
// run against the chip, which is why the UI marks it Beta and warns on enabling
// it. Treat every claim here as intent rather than observation.
//
// The one thing that is defended carefully is the failure case: a board told to
// use Ethernet with no W5500 attached, or with no cable in it, must still boot
// and still come up on WiFi. Every wait is bounded for that reason. A setting
// that can lock you out of the board is worse than a missing feature.
class EthernetManager {
 public:
  void begin();  // reads ethernet.json; a no-op unless enabled
  void loop();   // renews a DHCP lease, cheap when idle

  bool enabled() const { return _enabled; }
  bool linkUp() const;
  void statusToJson(JsonObject out) const;

  void setConfig(JsonObjectConst cfg);  // merge and persist; applies on reboot
  void copyConfigTo(JsonObject out) const;

 private:
  void load();

  bool _enabled = false;
  bool _started = false;
  bool _hardwareSeen = false;
  int _csPin = 10;
  String _ipMode = "dhcp";
  String _staticIp, _staticNetmask, _staticGateway, _staticDns;
  String _lastError;
};
