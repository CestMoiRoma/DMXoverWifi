#include "ethernet_manager.h"

#include "settings_store.h"

#if defined(ESP8266)

// No W5500 support on the ESP8266 build. Everything compiles, nothing runs, so
// the API and the UI can talk about Ethernet on either board without the
// firmware growing a second shape.
void EthernetManager::begin() {}
void EthernetManager::loop() {}
bool EthernetManager::linkUp() const { return false; }
void EthernetManager::load() {}

void EthernetManager::statusToJson(JsonObject out) const {
  out["supported"] = false;
  out["enabled"] = false;
  out["link"] = false;
  out["reason"] = "the ESP8266 build has no W5500 support";
}

void EthernetManager::setConfig(JsonObjectConst) {}

void EthernetManager::copyConfigTo(JsonObject out) const {
  out["supported"] = false;
  out["enabled"] = false;
}

#else

#include <Ethernet.h>
#include <SPI.h>
#include <WiFi.h>

// Bounded so a board configured for Ethernet with nothing plugged in still
// finishes booting. The stock five-second DHCP wait is the difference between
// a slow boot and a board nobody can reach.
static const unsigned long DHCP_TIMEOUT_MS = 5000;
static const unsigned long DHCP_RESPONSE_TIMEOUT_MS = 2000;

void EthernetManager::load() {
  JsonDocument doc;
  settings_store::load("ethernet.json", doc);
  _enabled = doc["enabled"] | false;
  _csPin = doc["cs_pin"] | 10;
  _ipMode = (const char*)(doc["ip_mode"] | "dhcp");
  if (_ipMode != "static") _ipMode = "dhcp";
  _staticIp = (const char*)(doc["static_ip"] | "");
  _staticNetmask = (const char*)(doc["static_netmask"] | "255.255.255.0");
  _staticGateway = (const char*)(doc["static_gateway"] | "");
  _staticDns = (const char*)(doc["static_dns"] | DEFAULT_DNS);
}

void EthernetManager::begin() {
  load();
  if (!_enabled) return;

  // Borrow the WiFi MAC rather than inventing one. A made-up address is fine
  // until two of these boards meet on the same switch.
  uint8_t mac[6];
  WiFi.macAddress(mac);
  mac[0] = (uint8_t)((mac[0] & 0xFE) | 0x02);  // locally administered, unicast

  Ethernet.init(_csPin);

  if (_ipMode == "static") {
    IPAddress ip, gateway, netmask, dns;
    if (!ip.fromString(_staticIp) || !gateway.fromString(_staticGateway)) {
      _lastError = "static address or gateway does not parse";
      return;
    }
    if (!netmask.fromString(_staticNetmask)) netmask.fromString("255.255.255.0");
    if (!dns.fromString(_staticDns)) dns.fromString(DEFAULT_DNS);
    Ethernet.begin(mac, ip, dns, gateway, netmask);
    _started = true;
  } else if (Ethernet.begin(mac, DHCP_TIMEOUT_MS, DHCP_RESPONSE_TIMEOUT_MS) == 1) {
    _started = true;
  } else {
    _lastError = "no DHCP lease within 5 s";
  }

  _hardwareSeen = Ethernet.hardwareStatus() != EthernetNoHardware;
  if (!_hardwareSeen) _lastError = "no W5500 found on the configured CS pin";
}

void EthernetManager::loop() {
  if (_started) Ethernet.maintain();
}

bool EthernetManager::linkUp() const {
  return _started && Ethernet.linkStatus() == LinkON;
}

void EthernetManager::statusToJson(JsonObject out) const {
  out["supported"] = true;
  out["enabled"] = _enabled;
  out["hardware"] = _hardwareSeen;
  out["link"] = linkUp();
  out["ip"] = _started ? Ethernet.localIP().toString() : String("");
  if (_lastError.length()) out["reason"] = _lastError;
}

void EthernetManager::setConfig(JsonObjectConst cfg) {
  JsonDocument doc;
  settings_store::load("ethernet.json", doc);
  for (JsonPairConst kv : cfg) doc[kv.key()] = kv.value();
  settings_store::save("ethernet.json", doc);
  // Deliberately not restarting the interface here. Bringing SPI up underneath
  // a running web server is how you lose the connection you are configuring it
  // from; the UI says to reboot.
  load();
}

void EthernetManager::copyConfigTo(JsonObject out) const {
  out["supported"] = true;
  out["enabled"] = _enabled;
  out["cs_pin"] = _csPin;
  out["ip_mode"] = _ipMode;
  out["static_ip"] = _staticIp;
  out["static_netmask"] = _staticNetmask;
  out["static_gateway"] = _staticGateway;
  out["static_dns"] = _staticDns;
}

#endif
