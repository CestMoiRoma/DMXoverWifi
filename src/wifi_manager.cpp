#include "wifi_manager.h"

#include <algorithm>

#include "settings_store.h"

#if defined(ESP8266)
#include <ESP8266WiFi.h>
#include <ESP8266mDNS.h>
#else
#include <ESPmDNS.h>
#include <WiFi.h>
#endif

static const char* DEFAULT_NETMASK = "255.255.255.0";
static const char* FALLBACK_HOSTNAME = "esp-dmx";

// DNS labels allow letters, digits and hyphens only, and cannot start or end
// with one. Anything else in the configured hostname is folded to a hyphen so a
// name typed in the UI still resolves instead of silently failing.
static String sanitizeHostname(const String& raw) {
  String out;
  for (size_t i = 0; i < raw.length(); i++) {
    char c = raw[i];
    if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-') {
      out += c;
    } else if (c >= 'A' && c <= 'Z') {
      out += (char)(c - 'A' + 'a');
    } else if (out.length() && out[out.length() - 1] != '-') {
      out += '-';
    }
  }
  while (out.length() && out[out.length() - 1] == '-') out.remove(out.length() - 1);
  if (out.length() > 63) out = out.substring(0, 63);
  return out.length() ? out : String(FALLBACK_HOSTNAME);
}

void WifiManager::begin() {
  WiFi.persistent(false);  // don't wear flash writing creds on every begin()
  reloadNetworks();
}

void WifiManager::reloadNetworks() {
  JsonDocument doc;
  settings_store::load("wifi_networks.json", doc);
  _networks.clear();
  for (JsonObjectConst n : doc.as<JsonArrayConst>()) {
    WifiNet net;
    net.ssid = (const char*)(n["ssid"] | "");
    net.password = (const char*)(n["password"] | "");
    net.priority = n["priority"] | 0;
    _networks.push_back(net);
  }
}

void WifiManager::save() {
  JsonDocument doc;
  JsonArray arr = doc.to<JsonArray>();
  for (const WifiNet& net : _networks) {
    JsonObject o = arr.add<JsonObject>();
    o["ssid"] = net.ssid;
    o["password"] = net.password;
    o["priority"] = net.priority;
  }
  settings_store::save("wifi_networks.json", doc);
}

void WifiManager::addNetwork(const String& ssid, const String& password, int priority) {
  for (size_t i = 0; i < _networks.size(); i++) {
    if (_networks[i].ssid == ssid) {
      _networks.erase(_networks.begin() + i);
      break;
    }
  }
  WifiNet net;
  net.ssid = ssid;
  net.password = password;
  net.priority = priority;
  _networks.push_back(net);
  save();
}

bool WifiManager::removeNetwork(const String& ssid) {
  size_t before = _networks.size();
  for (size_t i = 0; i < _networks.size(); i++) {
    if (_networks[i].ssid == ssid) {
      _networks.erase(_networks.begin() + i);
      break;
    }
  }
  save();
  return _networks.size() != before;
}

void WifiManager::networksToJson(JsonArray out) const {
  for (const WifiNet& net : _networks) {
    JsonObject o = out.add<JsonObject>();
    o["ssid"] = net.ssid;
    o["password"] = net.password;
    o["priority"] = net.priority;
  }
}

void WifiManager::scan(JsonArray out) {
  int n = WiFi.scanNetworks();
  for (int i = 0; i < n; i++) {
    JsonObject o = out.add<JsonObject>();
    o["ssid"] = WiFi.SSID(i);
    o["rssi"] = WiFi.RSSI(i);
  }
  WiFi.scanDelete();
}

void WifiManager::applyStaticIp() {
  // On Arduino the static config must be applied before WiFi.begin(), unlike
  // CircuitPython which set it after associating.
  JsonDocument sys;
  settings_store::load("system.json", sys);
  if (String((const char*)(sys["sta_ip_mode"] | "dhcp")) != "static") return;

  IPAddress ip, gateway, netmask, dns;
  if (!ip.fromString((const char*)(sys["sta_static_ip"] | ""))) return;
  if (!gateway.fromString((const char*)(sys["sta_static_gateway"] | ""))) return;
  if (!netmask.fromString((const char*)(sys["sta_static_netmask"] | DEFAULT_NETMASK))) {
    netmask.fromString(DEFAULT_NETMASK);
  }
  dns.fromString((const char*)(sys["sta_static_dns"] | "1.1.1.1"));
  WiFi.config(ip, gateway, netmask, dns);
}

void WifiManager::applyHostname() {
  JsonDocument sys;
  settings_store::load("system.json", sys);
  _hostname = sanitizeHostname(String((const char*)(sys["hostname"] | FALLBACK_HOSTNAME)));
#if defined(ESP8266)
  WiFi.hostname(_hostname);
#else
  WiFi.setHostname(_hostname.c_str());
#endif
}

void WifiManager::startMdns() {
  if (!_hostname.length()) return;
  MDNS.end();
  if (!MDNS.begin(_hostname.c_str())) return;
  MDNS.addService("http", "tcp", 80);
}

void WifiManager::loop() {
#if defined(ESP8266)
  MDNS.update();
#endif
}

bool WifiManager::tryConnect(const String& ssid, const String& password, uint32_t timeoutMs) {
  WiFi.mode(WIFI_STA);  // drops any active AP, matching the CircuitPython flow
  applyHostname();
  applyStaticIp();
  WiFi.begin(ssid.c_str(), password.length() ? password.c_str() : nullptr);

  uint32_t start = millis();
  while (millis() - start < timeoutMs) {
    if (WiFi.status() == WL_CONNECTED) {
      _mode = "sta";
      _apSsid = "";
      startMdns();
      return true;
    }
    delay(100);
  }
  return false;
}

bool WifiManager::connectKnown(uint32_t timeoutMs, int passes, uint32_t pauseMs) {
  // The radio often misses on the very first attempt after a cold boot; a couple
  // of retry passes cover that without doubling the wait when nothing is there.
  std::vector<WifiNet> ordered = _networks;
  std::sort(ordered.begin(), ordered.end(),
            [](const WifiNet& a, const WifiNet& b) { return a.priority > b.priority; });

  for (int attempt = 0; attempt < passes; attempt++) {
    for (const WifiNet& net : ordered) {
      if (!net.ssid.length()) continue;
      if (tryConnect(net.ssid, net.password, timeoutMs)) return true;
    }
    if (attempt < passes - 1 && pauseMs) delay(pauseMs);
  }
  return false;
}

void WifiManager::startAp(const String& ssid, const String& password, const String& ip) {
  WiFi.mode(WIFI_AP);
  applyHostname();
  IPAddress apIp;
  if (apIp.fromString(ip)) {
    IPAddress netmask;
    netmask.fromString(DEFAULT_NETMASK);
    WiFi.softAPConfig(apIp, apIp, netmask);
  }
  if (password.length()) {
    WiFi.softAP(ssid.c_str(), password.c_str());
  } else {
    WiFi.softAP(ssid.c_str());
  }
  _mode = "ap";
  _apSsid = ssid;
  startMdns();
}

void WifiManager::statusToJson(JsonObject out) const {
  if (_hostname.length()) out["hostname"] = _hostname;
  if (_mode == "sta") {
    out["mode"] = "sta";
    out["ssid"] = WiFi.SSID();
    out["ip"] = WiFi.localIP().toString();
  } else if (_mode == "ap") {
    out["mode"] = "ap";
    out["ssid"] = _apSsid;
    out["ip"] = WiFi.softAPIP().toString();
  } else {
    out["mode"] = nullptr;
    out["ssid"] = nullptr;
    out["ip"] = nullptr;
  }
}
