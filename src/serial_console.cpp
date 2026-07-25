#include "serial_console.h"

#include "settings_store.h"

static const char* HELP_LINES[] = {
    "Add-Wifi ssid=<ssid> passwd=<password> [priority=<n>]",
    "Add-mqtt broker=<ip> user=<user> passwd=<password> [port=<n>]",
    "Set-System tx-pin=<pin>                            - MAX485 DI/UART pin (reboot to apply)",
    "Set-System dir-pin enable=<true|false> [pin=<pin>] - MAX485 DE/RE pin, disabled by default"
    " (tie DE+RE to VCC and leave disabled if that's your wiring) (reboot to apply)",
    "Set-System hotspot name=<name> passwd=<password>   - AP ssid/password (reboot to apply)",
    "Set-System wifi-toggle on|off                      - off is USB-only: no radio, no web UI,"
    " no MQTT (reboot to apply)",
    "Set-Value channel=<ch> [device=<name>] value=<0-255> - drive a channel",
    "Set-Value address=<1-512> value=<0-255>            - drive a raw DMX slot",
    "Set-System mesh role=<none|parent|child> [ssid=<>] [passwd=<>] - WIP, stored only, no effect yet",
    "Set-System wifi-add ssid=<ssid> passwd=<password> [priority=<n>] - same as Add-Wifi",
    "Set-System wifi-del ssid=<ssid>                    - remove a saved network",
    "Set-System wifi-list                               - saved + visible networks",
    "Set-System mqtt-enable broker=<ip> user=<u> passwd=<p> [port=<n>] - same as Add-mqtt",
    "Set-System mqtt-disable                            - disable mqtt",
    "Set-device add name=<name> [channel=<start>] [category=<cat>] - add a device;"
    " category is one of par, bar, lyre, scanner, strobe, blinder, laser, smoke, dimmer,"
    " effect, other",
    "Set-device add-channel device=<name> name=<ch> channel=<offset> mode=<slider|button|momentary|switch>",
    "Set-device del-channel name=<ch> [device=<name>]   - remove a channel",
    "Set-device del device=<name>                       - remove a device",
    "get-status [all|wifi|mqtt|devices|mesh]",
    "get-status device name=<name>                      - channels of one device",
    "get-status channel channel=<ch> [device=<name>]    - one channel's value",
    "Help                                               - this message",
    "Reboot                                             - restart the board",
};

// ---- parsing helpers ----

static ParsedArgs tokenize(const String& text) {
  ParsedArgs res;
  int i = 0;
  int n = text.length();
  while (i < n) {
    while (i < n && text[i] == ' ') i++;
    if (i >= n) break;
    int start = i;
    while (i < n && text[i] != '=' && text[i] != ' ') i++;
    String key = text.substring(start, i);
    if (i < n && text[i] == '=') {
      i++;
      String value;
      if (i < n && (text[i] == '"' || text[i] == '\'')) {
        char quote = text[i];
        i++;
        int vs = i;
        while (i < n && text[i] != quote) i++;
        value = text.substring(vs, i);
        if (i < n) i++;
      } else {
        int vs = i;
        while (i < n && text[i] != ' ') i++;
        value = text.substring(vs, i);
      }
      key.trim();
      key.toLowerCase();
      res.kwargs[key] = value;
    } else {
      res.bare.push_back(key);
    }
  }
  return res;
}

static void subAndArgs(const String& rest, String& sub, ParsedArgs& args) {
  args = tokenize(rest);
  if (!args.bare.empty()) {
    sub = args.bare[0];
    sub.toLowerCase();
  } else if (!args.kwargs.empty()) {
    sub = args.kwargs.begin()->first;
  } else {
    sub = "";
  }
}

static String passwordArg(const ParsedArgs& a) {
  if (a.has("passwd")) return a.get("passwd");
  if (a.has("psswd")) return a.get("psswd");
  if (a.has("password")) return a.get("password");
  return "";
}

static bool truthy(String v) {
  v.trim();
  v.toLowerCase();
  return v == "true" || v == "1" || v == "yes" || v == "on";
}

static String normalizeTypeAlias(String value) {
  value.trim();
  value.toLowerCase();
  if (value == "button-momentary" || value == "momentary" || value == "btn-momentary" ||
      value == "hold")
    return "button-momentary";
  if (value == "button-switch" || value == "switch" || value == "btn-switch" || value == "toggle")
    return "button-switch";
  if (value == "button" || value == "btn" || value == "trigger" || value == "bool" ||
      value == "boolean")
    return "button";
  return "slider";
}

static String pyBool(bool b) { return b ? "True" : "False"; }

static String orNone(JsonVariantConst v) {
  if (v.isNull()) return "None";
  return String((const char*)v);
}

// ---- I/O ----

void SerialConsole::begin() {}

void SerialConsole::poll() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      String line = _buffer;
      line.trim();
      handleLine(line);
      _buffer = "";
    } else if (c != '\r') {
      _buffer += c;
    }
  }
}

void SerialConsole::write(const String& text) {
  Serial.print(text);
  Serial.print("\r\n");
}

// ---- shared operations ----

void SerialConsole::wifiAdd(const ParsedArgs& a) {
  String ssid = a.get("ssid");
  if (!ssid.length()) {
    fail("ssid required");
    return;
  }
  String password = passwordArg(a);
  int priority = a.get("priority", "0").toInt();
  _wifi.addNetwork(ssid, password, priority);
  bool connected = _wifi.tryConnect(ssid, password);
  emit("wifi '" + ssid + "' saved" + (connected ? String(" and connected") : String("")));
}

void SerialConsole::mqttEnable(const ParsedArgs& a) {
  String broker = a.get("broker");
  if (!broker.length()) {
    fail("broker required");
    return;
  }
  JsonDocument cfg;
  cfg["enabled"] = true;
  cfg["host"] = broker;
  cfg["username"] = a.get("user", "");
  cfg["password"] = passwordArg(a);
  if (a.has("port")) cfg["port"] = a.get("port").toInt();
  _mqtt.setConfig(cfg.as<JsonObjectConst>());
  _mqtt.start();
  emit("mqtt enabled, broker=" + broker);
}

void SerialConsole::mqttDisable() {
  JsonDocument cfg;
  cfg["enabled"] = false;
  _mqtt.setConfig(cfg.as<JsonObjectConst>());
  _mqtt.stop();
  emit("mqtt disabled");
}

// ---- Set-System ----

void SerialConsole::cmdSetSystem(const String& rest) {
  String sub;
  ParsedArgs a;
  subAndArgs(rest, sub, a);

  if (sub == "tx-pin") {
    String pin = a.has("tx-pin") ? a.get("tx-pin") : a.get("pin");
    if (!pin.length()) {
      fail("pin required, e.g. tx-pin=D9");
      return;
    }
    JsonDocument cfg;
    settings_store::load("system.json", cfg);
    cfg["dmx_tx_pin"] = pin;
    settings_store::save("system.json", cfg);
    emit("dmx tx pin set to '" + pin + "' (reboot to apply)");

  } else if (sub == "dir-pin") {
    JsonDocument cfg;
    settings_store::load("system.json", cfg);
    if (a.has("enable")) cfg["dmx_dir_pin_enabled"] = truthy(a.get("enable"));
    if (a.has("pin")) cfg["dmx_dir_pin"] = a.get("pin");
    settings_store::save("system.json", cfg);
    bool en = cfg["dmx_dir_pin_enabled"] | false;
    emit(String("dir pin ") + (en ? "enabled" : "disabled") + " (pin=" +
         (const char*)(cfg["dmx_dir_pin"] | "") + ") (reboot to apply)");

  } else if (sub == "wifi-toggle") {
    String state = a.has("wifi-toggle") ? a.get("wifi-toggle") : "";
    if (!state.length() && !a.bare.empty()) state = a.bare[0];
    if (!state.length()) {
      fail("on or off required, e.g. Set-System wifi-toggle off");
      return;
    }
    JsonDocument cfg;
    settings_store::load("system.json", cfg);
    bool on = truthy(state);
    cfg["wifi_enabled"] = on;
    settings_store::save("system.json", cfg);
    emit(String("wifi ") + (on ? "enabled" : "disabled") +
         " (reboot to apply; off means USB-only, no web UI and no MQTT)");

  } else if (sub == "hotspot") {
    JsonDocument cfg;
    settings_store::load("system.json", cfg);
    if (a.has("name")) cfg["ap_ssid"] = a.get("name");
    if (a.has("passwd") || a.has("psswd") || a.has("password"))
      cfg["ap_password"] = passwordArg(a);
    settings_store::save("system.json", cfg);
    emit("hotspot set to ssid='" + String((const char*)(cfg["ap_ssid"] | "")) +
         "' (reboot to apply)");

  } else if (sub == "wifi-add") {
    wifiAdd(a);

  } else if (sub == "wifi-del") {
    String ssid = a.get("ssid");
    if (!ssid.length()) {
      fail("ssid required");
      return;
    }
    bool removed = _wifi.removeNetwork(ssid);
    emit(removed ? "wifi '" + ssid + "' removed" : "wifi '" + ssid + "' not found");

  } else if (sub == "wifi-list") {
    emit("visible networks:");
    JsonDocument scan;
    _wifi.scan(scan.to<JsonArray>());
    for (JsonObjectConst net : scan.as<JsonArrayConst>())
      emit("  " + String((const char*)(net["ssid"] | "")) + " (rssi " +
           String((int)(net["rssi"] | 0)) + ")");
    emit("saved networks:");
    if (_wifi.networks().empty()) emit("  (none saved)");
    for (const WifiNet& net : _wifi.networks())
      emit("  " + net.ssid + " (priority " + String(net.priority) + ")");

  } else if (sub == "mqtt-enable") {
    mqttEnable(a);

  } else if (sub == "mqtt-disable") {
    mqttDisable();

  } else if (sub == "mesh") {
    String role = a.get("role");
    if (role.length() && role != "none" && role != "parent" && role != "child") {
      fail("role must be none, parent or child");
      return;
    }
    JsonDocument cfg;
    settings_store::load("mesh.json", cfg);
    if (role.length()) cfg["role"] = role;
    if (a.has("ssid")) cfg["ssid"] = a.get("ssid");
    if (a.has("passwd") || a.has("psswd") || a.has("password")) cfg["password"] = passwordArg(a);
    settings_store::save("mesh.json", cfg);
    emit("mesh role='" + String((const char*)(cfg["role"] | "none")) + "' ssid='" +
         String((const char*)(cfg["ssid"] | "")) + "' (WIP, not active yet)");

  } else {
    fail("unknown Set-System subcommand: " + sub);
  }
}

// ---- Set-device ----

void SerialConsole::cmdSetDevice(const String& rest) {
  String sub;
  ParsedArgs a;
  subAndArgs(rest, sub, a);

  if (sub == "add") {
    String name = a.get("name");
    if (!name.length()) {
      fail("name required");
      return;
    }
    int start = a.has("channel") ? a.get("channel").toInt() : _devices.nextFreeStartChannel();
    String category = normalizeCategory(a.get("category", DEFAULT_CATEGORY));
    Device* d = _devices.addDevice(name, start);
    d->category = category;
    _devices.updateDevice(d->id, JsonObjectConst());  // persist the category
    emit("device '" + name + "' added (start channel " + String(start) + ", category " + category +
         ")");

  } else if (sub == "add-channel") {
    String dev = a.get("device");
    String name = a.get("name");
    String off = a.get("channel");
    if (!dev.length() || !name.length() || !off.length()) {
      fail("device=, name= and channel= required");
      return;
    }
    String type = normalizeTypeAlias(a.get("mode"));
    String err;
    Channel* ch = _devices.addChannel(dev, name, off.toInt(), type, err);
    if (!ch) {
      fail(err);
      return;
    }
    _mqtt.publishDiscovery();
    emit("channel '" + name + "' added to '" + dev + "' (offset " + String(ch->offset) + ", " +
         ch->type + ")");

  } else if (sub == "del-channel") {
    String name = a.get("name");
    if (!name.length()) {
      fail("name required");
      return;
    }
    String devOut, err;
    if (!_devices.removeChannelByName(name, a.get("device"), devOut, err)) {
      fail(err);
      return;
    }
    _mqtt.publishDiscovery();
    emit("channel '" + name + "' removed from '" + devOut + "'");

  } else if (sub == "del") {
    String name = a.get("device");
    if (!name.length()) {
      fail("device required");
      return;
    }
    bool removed = _devices.removeDeviceByName(name);
    emit(removed ? "device '" + name + "' removed" : "device '" + name + "' not found");

  } else {
    fail("unknown Set-device subcommand: " + sub);
  }
}

// ---- get-status ----

void SerialConsole::cmdGetStatus(const String& rest) {
  String sub;
  ParsedArgs a;
  subAndArgs(rest, sub, a);
  if (!sub.length()) sub = "all";

  if (sub == "all") {
    JsonDocument w;
    _wifi.statusToJson(w.to<JsonObject>());
    emit("wifi: mode=" + orNone(w["mode"]) + " ssid=" + orNone(w["ssid"]) + " ip=" +
         orNone(w["ip"]));
    JsonDocument m;
    _mqtt.statusToJson(m.to<JsonObject>());
    emit("mqtt: enabled=" + pyBool(m["enabled"] | false) + " connected=" +
         pyBool(m["connected"] | false) + " broker=" + String((const char*)(m["broker"] | "")));
    JsonDocument sys;
    settings_store::load("system.json", sys);
    String dirPin = (sys["dmx_dir_pin_enabled"] | false)
                        ? String((const char*)(sys["dmx_dir_pin"] | ""))
                        : String("disabled");
    emit("system: hostname=" + String((const char*)(sys["hostname"] | "")) + " tx_pin=" +
         String((const char*)(sys["dmx_tx_pin"] | "")) + " dir_pin=" + dirPin);
    int devCount = _devices.devices().size();
    int chCount = 0;
    for (const Device& d : _devices.devices()) chCount += d.channels.size();
    emit("devices: " + String(devCount) + " device(s), " + String(chCount) + " channel(s)");
    emit("memory: " + String(ESP.getFreeHeap()) + " bytes free");

  } else if (sub == "wifi") {
    JsonDocument w;
    _wifi.statusToJson(w.to<JsonObject>());
    emit("wifi: mode=" + orNone(w["mode"]) + " ssid=" + orNone(w["ssid"]) + " ip=" +
         orNone(w["ip"]));

  } else if (sub == "mqtt") {
    JsonDocument m;
    _mqtt.statusToJson(m.to<JsonObject>());
    emit("mqtt: enabled=" + pyBool(m["enabled"] | false) + " connected=" +
         pyBool(m["connected"] | false) + " broker=" + String((const char*)(m["broker"] | "")));

  } else if (sub == "devices") {
    if (_devices.devices().empty()) {
      emit("(no devices configured)");
    } else {
      for (const Device& d : _devices.devices())
        emit(d.name + ": start=" + String(d.start_channel) + " channels=" +
             String((int)d.channels.size()));
    }

  } else if (sub == "device") {
    String name = a.get("name");
    if (!name.length()) {
      fail("name required");
      return;
    }
    Device* dev = _devices.findByName(name);
    if (!dev) {
      fail("no device named '" + name + "'");
      return;
    }
    if (dev->channels.empty()) {
      emit(name + " has no channels");
      return;
    }
    for (const Channel& c : dev->channels)
      emit("  " + String(c.offset) + ": " + c.name + " (" + c.type + ") = " +
           String(_devices.getValue(*dev, c)));

  } else if (sub == "channel") {
    String name = a.get("channel");
    if (!name.length()) {
      fail("channel required");
      return;
    }
    String devFilter = a.get("device");
    bool any = false;
    for (Device& d : _devices.devices()) {
      if (devFilter.length() && d.name != devFilter) continue;
      for (const Channel& c : d.channels) {
        if (c.name == name) {
          any = true;
          emit(d.name + "/" + c.name + ": offset=" + String(c.offset) + " mode=" + c.type +
               " value=" + String(_devices.getValue(d, c)));
        }
      }
    }
    if (!any) {
      fail("no channel named '" + name + "'");
      return;
    }

  } else if (sub == "mesh") {
    JsonDocument cfg;
    settings_store::load("mesh.json", cfg);
    emit("mesh (WIP): role=" + String((const char*)(cfg["role"] | "")) + " ssid=" +
         String((const char*)(cfg["ssid"] | "")));

  } else {
    fail("unknown get-status subcommand: " + sub);
  }
}

// ---- misc top-level ----

// Set-Value channel=<name> [device=<name>] value=<0-255>
// Set-Value address=<1-512> value=<0-255>
//
// The console could read a channel but never write one, which made USB-only
// control impossible. `address=` bypasses the fixture model and pokes a raw DMX
// slot, which is what the binary protocol and a probe both want.
void SerialConsole::cmdSetValue(const String& rest) {
  ParsedArgs a = tokenize(rest);
  if (!a.has("value")) {
    fail("value required, e.g. Set-Value channel=Red value=255");
    return;
  }
  int value = a.get("value").toInt();
  if (value < 0) value = 0;
  if (value > 255) value = 255;

  if (a.has("address")) {
    int address = a.get("address").toInt();
    if (address < 1 || address > 512) {
      fail("address must be 1-512");
      return;
    }
    _devices.dmx().setChannel(address, value);
    emit("dmx " + String(address) + " = " + String(value));
    return;
  }

  String name = a.get("channel");
  if (!name.length()) {
    fail("channel= or address= required");
    return;
  }
  String devFilter = a.get("device");
  bool any = false;
  for (Device& d : _devices.devices()) {
    if (devFilter.length() && d.name != devFilter) continue;
    for (const Channel& c : d.channels) {
      if (c.name != name) continue;
      any = true;
      _devices.setValue(d.id, c.offset, value);
      emit(d.name + "/" + c.name + " = " + String(value) + " (dmx " + String(d.addressFor(c)) + ")");
    }
  }
  if (!any) fail("no channel named '" + name + "'");
}

void SerialConsole::cmdHelp() {
  for (const char* line : HELP_LINES) emit(line);
}

void SerialConsole::cmdReboot() {
  write("OK rebooting");
  delay(50);
  ESP.restart();
}

// ---- dispatch ----

void SerialConsole::handleLine(const String& line) {
  if (!line.length()) return;

  int sp = -1;
  for (int i = 0; i < (int)line.length(); i++) {
    if (line[i] == ' ' || line[i] == '\t') {
      sp = i;
      break;
    }
  }
  String origCmd = sp < 0 ? line : line.substring(0, sp);
  String rest = sp < 0 ? String("") : line.substring(sp + 1);
  rest.trim();
  String cmd = origCmd;
  cmd.toLowerCase();

  _out.clear();
  _err = "";

  if (cmd == "add-wifi") {
    ParsedArgs a = tokenize(rest);
    wifiAdd(a);
  } else if (cmd == "add-mqtt") {
    ParsedArgs a = tokenize(rest);
    mqttEnable(a);
  } else if (cmd == "set-system") {
    cmdSetSystem(rest);
  } else if (cmd == "set-device") {
    cmdSetDevice(rest);
  } else if (cmd == "set-value") {
    cmdSetValue(rest);
  } else if (cmd == "get-status") {
    cmdGetStatus(rest);
  } else if (cmd == "help") {
    cmdHelp();
  } else if (cmd == "reboot") {
    cmdReboot();
  } else {
    write("ERR unknown command: " + origCmd + " (try Help)");
    return;
  }

  if (_err.length()) {
    write("ERR " + _err);
    return;
  }
  for (const String& l : _out) write("OK " + l);
}
