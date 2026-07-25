#include "web_server.h"

#include <LittleFS.h>
#include <uri/UriBraces.h>

#include "config.h"
#include "settings_store.h"
#include "version.h"

static const char* REPO_URL = "https://github.com/CestMoiRoma/DMXoverWifi";

// ---- helpers ----

void DmxWebServer::parseBody(JsonDocument& doc) {
  if (_server.hasArg("plain")) {
    deserializeJson(doc, _server.arg("plain"));
  }
}

void DmxWebServer::sendJson(int status, const JsonDocument& doc) {
  String out;
  serializeJson(doc, out);
  _server.send(status, "application/json", out);
}

void DmxWebServer::sendError(int status, const char* msg) {
  JsonDocument doc;
  doc["error"] = msg;
  sendJson(status, doc);
}

bool DmxWebServer::serveFile(const char* path, const char* contentType) {
  File f = LittleFS.open(path, "r");
  if (!f) {
    _server.send(404, "text/plain", "not found");
    return false;
  }
  _server.streamFile(f, contentType);
  f.close();
  return true;
}

// ---- access control ----
//
// The served UI is trusted, everything else needs the API key and the HTTP API
// module switched on. "The UI" means a request whose Origin or Referer points
// back at this board, which a browser sets and will not let a page forge. It is
// not a defence against a hand-rolled client: curl sets any header it likes.
// That is the usual bargain for a device on a trusted LAN, and the key is what
// actually gates scripted access.

bool DmxWebServer::requestFromUi() {
  String host = _server.hostHeader();
  if (!host.length()) return false;
  String probe = _server.header("Origin");
  if (!probe.length()) probe = _server.header("Referer");
  if (!probe.length()) return false;
  int scheme = probe.indexOf("://");
  if (scheme >= 0) probe = probe.substring(scheme + 3);
  int slash = probe.indexOf('/');
  if (slash >= 0) probe = probe.substring(0, slash);
  return probe == host;
}

bool DmxWebServer::apiAllowed() {
  if (requestFromUi()) return true;
  if (!_modules.httpApiEnabled()) {
    sendError(403, "http api is disabled");
    return false;
  }
  String key = _server.header("X-API-Key");
  if (!key.length()) key = _server.arg("api_key");
  if (!_modules.keyMatches(key)) {
    sendError(401, "missing or invalid api key");
    return false;
  }
  return true;
}

void DmxWebServer::onApi(const Uri& uri, HTTPMethod method, std::function<void()> handler) {
  _server.on(uri, method, [this, handler]() {
    if (!apiAllowed()) return;
    handler();
  });
}

// ---- lifecycle ----

void DmxWebServer::begin() {
  // hostHeader() comes for free; these do not.
  const char* wanted[] = {"Origin", "Referer", "X-API-Key"};
  _server.collectHeaders(wanted, 3);
  registerRoutes();
  _server.begin();
}

void DmxWebServer::registerRoutes() {
#if WITH_WEBUI
  _server.on("/", HTTP_GET, [this]() { serveFile("/www/index.html", "text/html"); });
  _server.on("/index.html", HTTP_GET, [this]() { serveFile("/www/index.html", "text/html"); });
  _server.on("/app.js", HTTP_GET, [this]() { serveFile("/www/app.js", "application/javascript"); });
  _server.on("/style.css", HTTP_GET, [this]() { serveFile("/www/style.css", "text/css"); });
  _server.on("/wiki.md", HTTP_GET, [this]() { serveFile("/www/wiki.md", "text/plain"); });
#endif

  // -- devices --
  onApi("/api/devices", HTTP_GET, [this]() {
    JsonDocument doc;
    _devices.devicesToJson(doc.to<JsonArray>(), true);
    sendJson(200, doc);
  });
  onApi("/api/devices", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    Device* d = _devices.addDevice(body["name"] | "", body["start_channel"] | 1,
                                   body["channels"].as<JsonArrayConst>(),
                                   body["labels"].as<JsonArrayConst>());
    _mqtt.publishDiscovery();
    JsonDocument out;
    _devices.deviceToJson(*d, out.to<JsonObject>(), true);
    sendJson(200, out);
  });
  onApi(UriBraces("/api/devices/{}"), HTTP_PUT, [this]() {
    JsonDocument body;
    parseBody(body);
    Device* d = _devices.updateDevice(_server.pathArg(0), body.as<JsonObjectConst>());
    if (!d) {
      sendError(404, "not found");
      return;
    }
    _mqtt.publishDiscovery();
    JsonDocument out;
    _devices.deviceToJson(*d, out.to<JsonObject>(), true);
    sendJson(200, out);
  });
  onApi(UriBraces("/api/devices/{}"), HTTP_DELETE, [this]() {
    bool ok = _devices.removeDevice(_server.pathArg(0));
    JsonDocument out;
    out["ok"] = ok;
    sendJson(200, out);
  });
  onApi(UriBraces("/api/devices/{}/channel/{}"), HTTP_POST, [this]() {
    String id = _server.pathArg(0);
    int offset = _server.pathArg(1).toInt();
    JsonDocument body;
    parseBody(body);
    int value = body["value"] | 0;
    Channel* c = _devices.setValue(id, offset, value);
    if (!c) {
      sendError(404, "not found");
      return;
    }
    _mqtt.publishState(id, offset, value);
    JsonDocument out;
    out["ok"] = true;
    sendJson(200, out);
  });

  // -- labels --
  onApi("/api/labels", HTTP_GET, [this]() {
    JsonDocument doc;
    _labels.labelsToJson(doc.to<JsonArray>());
    sendJson(200, doc);
  });
  onApi("/api/labels", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    Label* l = _labels.add(body["name"] | "", body["color"] | "");
    JsonDocument out;
    _labels.labelToJson(*l, out.to<JsonObject>());
    sendJson(200, out);
  });
  onApi(UriBraces("/api/labels/{}"), HTTP_PUT, [this]() {
    JsonDocument body;
    parseBody(body);
    Label* l = _labels.update(_server.pathArg(0), body.as<JsonObjectConst>());
    if (!l) {
      sendError(404, "not found");
      return;
    }
    JsonDocument out;
    _labels.labelToJson(*l, out.to<JsonObject>());
    sendJson(200, out);
  });
  onApi(UriBraces("/api/labels/{}"), HTTP_DELETE, [this]() {
    String id = _server.pathArg(0);
    bool ok = _labels.remove(id);
    // A fixture holding a dangling id would keep filtering under a chip that no
    // longer exists, so clear it everywhere.
    if (ok) _devices.dropLabel(id);
    JsonDocument out;
    out["ok"] = ok;
    sendJson(200, out);
  });

  // -- wifi --
  onApi("/api/wifi", HTTP_GET, [this]() {
    JsonDocument doc;
    _wifi.networksToJson(doc.to<JsonArray>());
    sendJson(200, doc);
  });
  onApi("/api/wifi", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    _wifi.addNetwork(body["ssid"] | "", body["password"] | "", body["priority"] | 0);
    JsonDocument doc;
    _wifi.networksToJson(doc.to<JsonArray>());
    sendJson(200, doc);
  });
  onApi("/api/wifi/scan", HTTP_GET, [this]() {
    JsonDocument doc;
    _wifi.scan(doc.to<JsonArray>());
    sendJson(200, doc);
  });
  onApi(UriBraces("/api/wifi/{}"), HTTP_DELETE, [this]() {
    _wifi.removeNetwork(_server.pathArg(0));
    JsonDocument doc;
    _wifi.networksToJson(doc.to<JsonArray>());
    sendJson(200, doc);
  });

  // -- mqtt --
  onApi("/api/mqtt", HTTP_GET, [this]() {
    JsonDocument doc;
    _mqtt.copyConfigTo(doc.to<JsonObject>());
    sendJson(200, doc);
  });
  onApi("/api/mqtt", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    _mqtt.setConfig(body.as<JsonObjectConst>());
    if (_modules.mqttEnabled()) _mqtt.start();
    JsonDocument doc;
    _mqtt.copyConfigTo(doc.to<JsonObject>());
    sendJson(200, doc);
  });

  // -- system --
  onApi("/api/system", HTTP_GET, [this]() {
    JsonDocument doc;
    settings_store::load("system.json", doc);
    sendJson(200, doc);
  });
  onApi("/api/system", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    JsonDocument cfg;
    settings_store::load("system.json", cfg);
    for (JsonPairConst kv : body.as<JsonObjectConst>()) cfg[kv.key()] = kv.value();
    settings_store::save("system.json", cfg);
    sendJson(200, cfg);
  });

  // -- mesh (WIP, stored only) --
  onApi("/api/mesh", HTTP_GET, [this]() {
    JsonDocument doc;
    settings_store::load("mesh.json", doc);
    sendJson(200, doc);
  });
  onApi("/api/mesh", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    JsonDocument cfg;
    settings_store::load("mesh.json", cfg);
    for (JsonPairConst kv : body.as<JsonObjectConst>()) cfg[kv.key()] = kv.value();
    settings_store::save("mesh.json", cfg);
    sendJson(200, cfg);
  });

  // -- info --
  onApi("/api/info", HTTP_GET, [this]() {
    JsonDocument doc;
    doc["version"] = FW_VERSION;
    JsonObject author = doc["author"].to<JsonObject>();
    author["name"] = "CestMoiRoma";
    author["url"] = "https://github.com/CestMoiRoma";
    doc["repo"] = REPO_URL;
    doc["wiki_online"] = String(REPO_URL) + "/blob/main/WIKI.md";
    doc["wiki_local"] = "/wiki.md";
    // The UI hides the DMX pin fields on the ESP8266, where the backend is
    // wired to Serial1/GPIO2 and the pin setting has no effect.
    doc["board"] = BOARD_NAME;
    doc["hostname"] = _wifi.hostname();
    sendJson(200, doc);
  });

  // -- export current config as downloadable .env --
  onApi("/api/export-env", HTTP_GET, [this]() {
    _server.sendHeader("Content-Disposition", "attachment; filename=config.env");
    _server.send(200, "text/plain", buildEnvText());
  });

  // -- module switches and the api key --
  onApi("/api/modules", HTTP_GET, [this]() {
    JsonDocument doc;
    _modules.toJson(doc.to<JsonObject>());
    // The key itself only goes out to the UI: an external caller already has it
    // if it got this far, and a disabled-API caller must not be handed one.
    if (requestFromUi()) doc["api_key"] = _modules.apiKey();
    sendJson(200, doc);
  });
  onApi("/api/modules", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    _modules.setFromJson(body.as<JsonObjectConst>());
    if (_modules.mqttEnabled()) _mqtt.start();
    else _mqtt.stop();
    JsonDocument doc;
    _modules.toJson(doc.to<JsonObject>());
    if (requestFromUi()) doc["api_key"] = _modules.apiKey();
    sendJson(200, doc);
  });
  onApi("/api/modules/key", HTTP_POST, [this]() {
    JsonDocument doc;
    doc["api_key"] = _modules.regenerateKey();
    sendJson(200, doc);
  });

  // -- reboot --
  onApi("/api/reboot", HTTP_POST, [this]() {
    JsonDocument doc;
    doc["ok"] = true;
    sendJson(200, doc);
    // Let the response drain before pulling the rug out.
    delay(200);
    ESP.restart();
  });

  // -- whole config as .json, and restoring one --
  onApi("/api/config", HTTP_GET, [this]() {
    JsonDocument doc;
    buildConfigJson(doc);
    _server.sendHeader("Content-Disposition", "attachment; filename=config.json");
    String out;
    serializeJson(doc, out);
    _server.send(200, "application/json", out);
  });
  onApi("/api/config", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    if (!body.is<JsonObject>()) {
      sendError(400, "expected a config object");
      return;
    }
    applyConfigJson(body.as<JsonObjectConst>());
    JsonDocument out;
    out["ok"] = true;
    out["reboot_required"] = true;
    sendJson(200, out);
  });

  _server.onNotFound([this]() { sendError(404, "not found"); });
}

// ---- .json config snapshot and restore ----
//
// The .env export and this one answer different questions. .env pre-fills a
// board at flash time through tools/env_to_fsdata.py and stays human-editable;
// this one round-trips the whole live config through the UI on a running board,
// labels included, without touching the build.

static void copySection(JsonDocument& out, const char* key, const char* file) {
  JsonDocument tmp;
  settings_store::load(file, tmp);
  out[key].set(tmp.as<JsonVariantConst>());
}

void DmxWebServer::buildConfigJson(JsonDocument& out) {
  out["version"] = FW_VERSION;
  out["board"] = BOARD_NAME;
  copySection(out, "system", "system.json");
  copySection(out, "mesh", "mesh.json");
  // Includes the API key, so a restore clones the board faithfully. Treat the
  // file as a secret: it already carries every WiFi and MQTT password.
  copySection(out, "api", "api.json");
  _wifi.networksToJson(out["wifi_networks"].to<JsonArray>());
  _mqtt.copyConfigTo(out["mqtt"].to<JsonObject>());
  _labels.labelsToJson(out["labels"].to<JsonArray>());
  _devices.devicesToJson(out["devices"].to<JsonArray>());
}

// Merges one object section over what is already stored, so a partial config
// file only overrides the keys it actually carries.
static void mergeSection(JsonObjectConst in, const char* file) {
  JsonDocument cfg;
  settings_store::load(file, cfg);
  for (JsonPairConst kv : in) cfg[kv.key()] = kv.value();
  settings_store::save(file, cfg);
}

void DmxWebServer::applyConfigJson(JsonObjectConst in) {
  if (in["system"].is<JsonObjectConst>()) mergeSection(in["system"].as<JsonObjectConst>(), "system.json");
  if (in["mesh"].is<JsonObjectConst>()) mergeSection(in["mesh"].as<JsonObjectConst>(), "mesh.json");
  if (in["api"].is<JsonObjectConst>()) {
    mergeSection(in["api"].as<JsonObjectConst>(), "api.json");
    _modules.begin();  // re-read, keeping any key the file carried
  }

  if (in["wifi_networks"].is<JsonArrayConst>()) {
    JsonDocument nets;
    nets.set(in["wifi_networks"]);
    settings_store::save("wifi_networks.json", nets);
    _wifi.reloadNetworks();
  }
  if (in["mqtt"].is<JsonObjectConst>()) {
    _mqtt.setConfig(in["mqtt"].as<JsonObjectConst>());
    _mqtt.start();
  }
  // Labels first: the fixtures that follow refer to them by id.
  if (in["labels"].is<JsonArrayConst>()) _labels.replaceAll(in["labels"].as<JsonArrayConst>());
  if (in["devices"].is<JsonArrayConst>()) {
    _devices.replaceAll(in["devices"].as<JsonArrayConst>());
    _mqtt.publishDiscovery();
  }
}

// ---- .env export ----

static const char* boolEnv(bool v) { return v ? "true" : "false"; }

String DmxWebServer::buildEnvText() {
  String out;
  out += "# Exported from the running board. Drop next to the flashing tools as .env\n\n";

  JsonDocument wifi;
  settings_store::load("wifi_networks.json", wifi);
  JsonArrayConst nets = wifi.as<JsonArrayConst>();
  if (nets.size() > 0) {
    out += "# --- WiFi networks ---\n";
    int i = 1;
    for (JsonObjectConst net : nets) {
      out += "WIFI_" + String(i) + "_SSID=" + (const char*)(net["ssid"] | "") + "\n";
      out += "WIFI_" + String(i) + "_PASSWORD=" + (const char*)(net["password"] | "") + "\n";
      out += "WIFI_" + String(i) + "_PRIORITY=" + String((int)(net["priority"] | 0)) + "\n\n";
      i++;
    }
  }

  JsonDocument mqtt;
  settings_store::load("mqtt.json", mqtt);
  out += "# --- MQTT ---\n";
  out += String("MQTT_ENABLED=") + boolEnv(mqtt["enabled"] | false) + "\n";
  out += String("MQTT_HOST=") + (const char*)(mqtt["host"] | "") + "\n";
  out += "MQTT_PORT=" + String((int)(mqtt["port"] | 1883)) + "\n";
  out += String("MQTT_USERNAME=") + (const char*)(mqtt["username"] | "") + "\n";
  out += String("MQTT_PASSWORD=") + (const char*)(mqtt["password"] | "") + "\n";
  out += String("MQTT_BASE_TOPIC=") + (const char*)(mqtt["base_topic"] | "") + "\n";
  out += String("MQTT_DISCOVERY_PREFIX=") + (const char*)(mqtt["discovery_prefix"] | "") + "\n\n";

  JsonDocument sys;
  settings_store::load("system.json", sys);
  out += "# --- System / DMX / hotspot / static IP ---\n";
  out += String("DMX_TX_PIN=") + (const char*)(sys["dmx_tx_pin"] | "") + "\n";
  out += String("DMX_DIR_PIN_ENABLED=") + boolEnv(sys["dmx_dir_pin_enabled"] | false) + "\n";
  out += String("DMX_DIR_PIN=") + (const char*)(sys["dmx_dir_pin"] | "") + "\n";
  out += String("HOSTNAME=") + (const char*)(sys["hostname"] | "") + "\n";
  out += String("AP_SSID=") + (const char*)(sys["ap_ssid"] | "") + "\n";
  out += String("AP_PASSWORD=") + (const char*)(sys["ap_password"] | "") + "\n";
  out += String("AP_IP=") + (const char*)(sys["ap_ip"] | "") + "\n";
  out += String("STA_IP_MODE=") + (const char*)(sys["sta_ip_mode"] | "dhcp") + "\n";
  out += String("STA_STATIC_IP=") + (const char*)(sys["sta_static_ip"] | "") + "\n";
  out += String("STA_STATIC_NETMASK=") + (const char*)(sys["sta_static_netmask"] | "") + "\n";
  out += String("STA_STATIC_GATEWAY=") + (const char*)(sys["sta_static_gateway"] | "") + "\n";
  out += String("STA_STATIC_DNS=") + (const char*)(sys["sta_static_dns"] | "") + "\n\n";

  JsonDocument mesh;
  settings_store::load("mesh.json", mesh);
  out += "# --- Parent/Child mesh (WIP) ---\n";
  out += String("MESH_ROLE=") + (const char*)(mesh["role"] | "none") + "\n";
  out += String("MESH_SSID=") + (const char*)(mesh["ssid"] | "") + "\n";
  out += String("MESH_PASSWORD=") + (const char*)(mesh["password"] | "") + "\n\n";

  const std::vector<Label>& labels = _labels.labels();
  if (!labels.empty()) {
    out += "# --- Labels ---\n";
    int i = 1;
    for (const Label& l : labels) {
      out += "LABEL_" + String(i) + "_NAME=" + l.name + "\n";
      out += "LABEL_" + String(i) + "_COLOR=" + l.color + "\n";
      i++;
    }
    out += "\n";
  }

  JsonDocument devices;
  settings_store::load("devices.json", devices);
  JsonArrayConst devs = devices.as<JsonArrayConst>();
  if (devs.size() > 0) {
    out += "# --- Devices ---\n";
    int i = 1;
    for (JsonObjectConst dev : devs) {
      out += "DEVICE_" + String(i) + "_NAME=" + (const char*)(dev["name"] | "") + "\n";
      out += "DEVICE_" + String(i) + "_START_CHANNEL=" + String((int)(dev["start_channel"] | 1)) + "\n";
      // Labels travel by name, not by id: .env is meant to stay readable and
      // hand-editable, and the seeding script resolves the names back.
      String labelNames;
      for (JsonVariantConst v : dev["labels"].as<JsonArrayConst>()) {
        const char* id = v.as<const char*>();
        if (!id) continue;
        Label* l = _labels.find(String(id));
        if (!l) continue;
        if (labelNames.length()) labelNames += ",";
        labelNames += l->name;
      }
      if (labelNames.length()) out += "DEVICE_" + String(i) + "_LABELS=" + labelNames + "\n";
      int j = 1;
      for (JsonObjectConst ch : dev["channels"].as<JsonArrayConst>()) {
        String p = "DEVICE_" + String(i) + "_CHANNEL_" + String(j);
        out += p + "_OFFSET=" + String((int)(ch["offset"] | j)) + "\n";
        out += p + "_NAME=" + (const char*)(ch["name"] | "") + "\n";
        out += p + "_TYPE=" + (const char*)(ch["type"] | "slider") + "\n";
        j++;
      }
      out += "\n";
      i++;
    }
  }

  return out;
}
