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
static const char* FALLBACK_HOSTNAME = DEFAULT_HOSTNAME;

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

static WifiNet netFromJson(JsonObjectConst n) {
  WifiNet net;
  net.ssid = (const char*)(n["ssid"] | "");
  net.password = (const char*)(n["password"] | "");
  net.priority = n["priority"] | 0;
  net.ip_mode = (const char*)(n["ip_mode"] | "dhcp");
  if (net.ip_mode != "static") net.ip_mode = "dhcp";
  net.static_ip = (const char*)(n["static_ip"] | "");
  net.static_netmask = (const char*)(n["static_netmask"] | DEFAULT_NETMASK);
  net.static_gateway = (const char*)(n["static_gateway"] | "");
  net.static_dns = (const char*)(n["static_dns"] | DEFAULT_DNS);
  return net;
}

static void netToJson(const WifiNet& net, JsonObject o) {
  o["ssid"] = net.ssid;
  o["password"] = net.password;
  o["priority"] = net.priority;
  o["ip_mode"] = net.ip_mode;
  o["static_ip"] = net.static_ip;
  o["static_netmask"] = net.static_netmask;
  o["static_gateway"] = net.static_gateway;
  o["static_dns"] = net.static_dns;
}

void WifiManager::reloadNetworks() {
  JsonDocument doc;
  settings_store::load("wifi_networks.json", doc);
  _networks.clear();
  for (JsonObjectConst n : doc.as<JsonArrayConst>()) _networks.push_back(netFromJson(n));
  sortByPriority();
}

// Highest priority first. Kept stable so two networks sharing a priority hold
// the order they were saved in rather than shuffling on every boot.
void WifiManager::sortByPriority() {
  std::stable_sort(_networks.begin(), _networks.end(),
                   [](const WifiNet& a, const WifiNet& b) { return a.priority > b.priority; });
}

void WifiManager::save() {
  JsonDocument doc;
  JsonArray arr = doc.to<JsonArray>();
  for (const WifiNet& net : _networks) netToJson(net, arr.add<JsonObject>());
  settings_store::save("wifi_networks.json", doc);
}

void WifiManager::replaceNetworks(JsonArrayConst in) {
  std::vector<WifiNet> previous = _networks;
  _networks.clear();
  int count = in.size();
  for (JsonObjectConst n : in) {
    WifiNet net = netFromJson(n);
    if (!net.ssid.length()) continue;
    // An absent password keeps whatever the entry already had. Reordering a
    // list or editing an address should not be able to wipe a credential the
    // caller never mentioned; an explicit "" still sets an open network.
    if (!n["password"].is<const char*>()) {
      for (const WifiNet& old : previous) {
        if (old.ssid == net.ssid) {
          net.password = old.password;
          break;
        }
      }
    }
    // The posted order is the priority: first is highest. Numbering them here
    // rather than trusting the body keeps the two from ever disagreeing.
    net.priority = count--;
    _networks.push_back(net);
  }
  save();
}

void WifiManager::addNetwork(const String& ssid, const String& password, int priority) {
  for (size_t i = 0; i < _networks.size(); i++) {
    if (_networks[i].ssid == ssid) {
      // Re-adding keeps whatever addressing the entry already had, so setting a
      // static address then fixing a typo in the password does not silently
      // drop back to DHCP.
      _networks[i].password = password;
      _networks[i].priority = priority;
      sortByPriority();
      save();
      return;
    }
  }
  WifiNet net;
  net.ssid = ssid;
  net.password = password;
  net.priority = priority;
  _networks.push_back(net);
  sortByPriority();
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
  for (const WifiNet& net : _networks) netToJson(net, out.add<JsonObject>());
}

// Asynchronous on purpose. A blocking scan takes about seven seconds, and this
// board runs everything from one loop: for those seven seconds it serves no
// requests and, worse, stops refreshing DMX. Starting the scan and coming back
// for the answer costs the caller a few polls and costs the rig nothing.
void WifiManager::scan(JsonObject out) {
  int state = WiFi.scanComplete();

  if (state == WIFI_SCAN_FAILED) {  // nothing running: start one
    WiFi.scanNetworks(true);
    out["scanning"] = true;
    out["networks"].to<JsonArray>();
    return;
  }
  if (state == WIFI_SCAN_RUNNING) {
    out["scanning"] = true;
    out["networks"].to<JsonArray>();
    return;
  }

  out["scanning"] = false;
  JsonArray list = out["networks"].to<JsonArray>();
  for (int i = 0; i < state; i++) {
    JsonObject o = list.add<JsonObject>();
    o["ssid"] = WiFi.SSID(i);
    o["rssi"] = WiFi.RSSI(i);
  }
  WiFi.scanDelete();
}

// On Arduino the address config must be applied before WiFi.begin(), unlike
// CircuitPython which set it after associating. A static entry that does not
// parse falls back to DHCP rather than dropping the board off the network.
void WifiManager::applyAddressing(const WifiNet& net) {
  if (net.ip_mode != "static") {
    // Undo any static config left over from a previous network in this boot.
    WiFi.config(IPAddress((uint32_t)0), IPAddress((uint32_t)0), IPAddress((uint32_t)0));
    return;
  }
  IPAddress ip, gateway, netmask, dns;
  if (!ip.fromString(net.static_ip)) return;
  if (!gateway.fromString(net.static_gateway)) return;
  if (!netmask.fromString(net.static_netmask)) netmask.fromString(DEFAULT_NETMASK);
  if (!dns.fromString(net.static_dns)) dns.fromString(DEFAULT_DNS);
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
  WifiNet net;
  net.ssid = ssid;
  net.password = password;
  // A network we have saved knows its own addressing; borrow it so the console's
  // Add-Wifi does not connect on DHCP to something configured static.
  for (const WifiNet& known : _networks) {
    if (known.ssid == ssid) {
      net.ip_mode = known.ip_mode;
      net.static_ip = known.static_ip;
      net.static_netmask = known.static_netmask;
      net.static_gateway = known.static_gateway;
      net.static_dns = known.static_dns;
      break;
    }
  }
  return tryConnect(net, timeoutMs);
}

bool WifiManager::tryConnect(const WifiNet& net, uint32_t timeoutMs) {
  const String& ssid = net.ssid;
  const String& password = net.password;
  WiFi.mode(WIFI_STA);  // drops any active AP, matching the CircuitPython flow
  applyHostname();
  applyAddressing(net);
  WiFi.begin(ssid.c_str(), password.length() ? password.c_str() : nullptr);

  uint32_t start = millis();
  while (millis() - start < timeoutMs) {
    if (WiFi.status() == WL_CONNECTED) {
      _mode = "sta";
      _apSsid = "";
      // Modem sleep parks the radio between beacons, so an incoming packet waits
      // for the next one. That is tens of milliseconds added to every request,
      // which on a board already serving one client at a time is enough to let a
      // burst of connections pile up. This is a mains-powered DMX box, not a
      // battery sensor: keep the radio awake.
      WiFi.setSleep(false);
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
  // _networks is already highest-priority-first, kept that way on load and on
  // every save, so the list the UI shows is the order actually tried.
  for (int attempt = 0; attempt < passes; attempt++) {
    for (const WifiNet& net : _networks) {
      if (!net.ssid.length()) continue;
      if (tryConnect(net, timeoutMs)) return true;
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
  if (_disabled) {
    out["mode"] = "off";
    out["ssid"] = nullptr;
    out["ip"] = nullptr;
  } else if (_mode == "sta") {
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
