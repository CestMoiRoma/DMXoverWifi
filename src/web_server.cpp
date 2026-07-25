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

// ---- lifecycle ----

void DmxWebServer::begin() {
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
  _server.on("/api/devices", HTTP_GET, [this]() {
    JsonDocument doc;
    _devices.devicesToJson(doc.to<JsonArray>());
    sendJson(200, doc);
  });
  _server.on("/api/devices", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    Device* d = _devices.addDevice(body["name"] | "", body["start_channel"] | 1,
                                   body["channels"].as<JsonArrayConst>());
    _mqtt.publishDiscovery();
    JsonDocument out;
    _devices.deviceToJson(*d, out.to<JsonObject>());
    sendJson(200, out);
  });
  _server.on(UriBraces("/api/devices/{}"), HTTP_PUT, [this]() {
    JsonDocument body;
    parseBody(body);
    Device* d = _devices.updateDevice(_server.pathArg(0), body.as<JsonObjectConst>());
    if (!d) {
      sendError(404, "not found");
      return;
    }
    _mqtt.publishDiscovery();
    JsonDocument out;
    _devices.deviceToJson(*d, out.to<JsonObject>());
    sendJson(200, out);
  });
  _server.on(UriBraces("/api/devices/{}"), HTTP_DELETE, [this]() {
    bool ok = _devices.removeDevice(_server.pathArg(0));
    JsonDocument out;
    out["ok"] = ok;
    sendJson(200, out);
  });
  _server.on(UriBraces("/api/devices/{}/channel/{}"), HTTP_POST, [this]() {
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

  // -- wifi --
  _server.on("/api/wifi", HTTP_GET, [this]() {
    JsonDocument doc;
    _wifi.networksToJson(doc.to<JsonArray>());
    sendJson(200, doc);
  });
  _server.on("/api/wifi", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    _wifi.addNetwork(body["ssid"] | "", body["password"] | "", body["priority"] | 0);
    JsonDocument doc;
    _wifi.networksToJson(doc.to<JsonArray>());
    sendJson(200, doc);
  });
  _server.on("/api/wifi/scan", HTTP_GET, [this]() {
    JsonDocument doc;
    _wifi.scan(doc.to<JsonArray>());
    sendJson(200, doc);
  });
  _server.on(UriBraces("/api/wifi/{}"), HTTP_DELETE, [this]() {
    _wifi.removeNetwork(_server.pathArg(0));
    JsonDocument doc;
    _wifi.networksToJson(doc.to<JsonArray>());
    sendJson(200, doc);
  });

  // -- mqtt --
  _server.on("/api/mqtt", HTTP_GET, [this]() {
    JsonDocument doc;
    _mqtt.copyConfigTo(doc.to<JsonObject>());
    sendJson(200, doc);
  });
  _server.on("/api/mqtt", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    _mqtt.setConfig(body.as<JsonObjectConst>());
    _mqtt.start();
    JsonDocument doc;
    _mqtt.copyConfigTo(doc.to<JsonObject>());
    sendJson(200, doc);
  });

  // -- system --
  _server.on("/api/system", HTTP_GET, [this]() {
    JsonDocument doc;
    settings_store::load("system.json", doc);
    sendJson(200, doc);
  });
  _server.on("/api/system", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    JsonDocument cfg;
    settings_store::load("system.json", cfg);
    for (JsonPairConst kv : body.as<JsonObjectConst>()) cfg[kv.key()] = kv.value();
    settings_store::save("system.json", cfg);
    sendJson(200, cfg);
  });

  // -- mesh (WIP, stored only) --
  _server.on("/api/mesh", HTTP_GET, [this]() {
    JsonDocument doc;
    settings_store::load("mesh.json", doc);
    sendJson(200, doc);
  });
  _server.on("/api/mesh", HTTP_POST, [this]() {
    JsonDocument body;
    parseBody(body);
    JsonDocument cfg;
    settings_store::load("mesh.json", cfg);
    for (JsonPairConst kv : body.as<JsonObjectConst>()) cfg[kv.key()] = kv.value();
    settings_store::save("mesh.json", cfg);
    sendJson(200, cfg);
  });

  // -- info --
  _server.on("/api/info", HTTP_GET, [this]() {
    JsonDocument doc;
    doc["version"] = FW_VERSION;
    JsonObject author = doc["author"].to<JsonObject>();
    author["name"] = "CestMoiRoma";
    author["url"] = "https://github.com/CestMoiRoma";
    doc["repo"] = REPO_URL;
    doc["wiki_online"] = String(REPO_URL) + "/blob/main/WIKI.md";
    doc["wiki_local"] = "/wiki.md";
    sendJson(200, doc);
  });

  // -- export current config as downloadable .env --
  _server.on("/api/export-env", HTTP_GET, [this]() {
    _server.sendHeader("Content-Disposition", "attachment; filename=config.env");
    _server.send(200, "text/plain", buildEnvText());
  });

  _server.onNotFound([this]() { sendError(404, "not found"); });
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

  JsonDocument devices;
  settings_store::load("devices.json", devices);
  JsonArrayConst devs = devices.as<JsonArrayConst>();
  if (devs.size() > 0) {
    out += "# --- Devices ---\n";
    int i = 1;
    for (JsonObjectConst dev : devs) {
      out += "DEVICE_" + String(i) + "_NAME=" + (const char*)(dev["name"] | "") + "\n";
      out += "DEVICE_" + String(i) + "_START_CHANNEL=" + String((int)(dev["start_channel"] | 1)) + "\n";
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
