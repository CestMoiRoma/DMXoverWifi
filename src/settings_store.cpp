#include "settings_store.h"

#include <LittleFS.h>

#include "config.h"

namespace settings_store {

static String path(const char* name) {
  return String(DATA_DIR) + "/" + name;
}

// Build the default document for a settings file, mirroring the CircuitPython
// DEFAULTS table.
static void seedDefault(const char* name, JsonDocument& doc) {
  doc.clear();
  if (strcmp(name, "wifi_networks.json") == 0 || strcmp(name, "devices.json") == 0 ||
      strcmp(name, "labels.json") == 0) {
    doc.to<JsonArray>();  // empty list
  } else if (strcmp(name, "mqtt.json") == 0) {
    doc["enabled"] = false;
    doc["host"] = "";
    doc["port"] = 1883;
    doc["username"] = "";
    doc["password"] = "";
    doc["base_topic"] = "dmxwifi";
    doc["discovery_prefix"] = "homeassistant";
  } else if (strcmp(name, "api.json") == 0) {
    doc["http_api_enabled"] = true;
    doc["websocket_enabled"] = true;
    doc["mqtt_enabled"] = true;
    doc["api_key"] = "";  // minted on first boot by ModuleSettings
  } else if (strcmp(name, "system.json") == 0) {
    doc["wifi_enabled"] = true;
    doc["dmx_tx_pin"] = DEFAULT_DMX_TX_PIN;
    doc["dmx_dir_pin_enabled"] = false;
    doc["dmx_dir_pin"] = DEFAULT_DMX_DIR_PIN;
    doc["hostname"] = "ESP-DMX";
    doc["ap_ssid"] = "ESP-DMX";
    doc["ap_password"] = "DMX4ALL1";
    doc["ap_ip"] = "1.1.1.1";
    // Station addressing lives per WiFi entry now, not here.
  } else if (strcmp(name, "mesh.json") == 0) {
    doc["role"] = "none";  // WIP: stored only, not acted on yet
    doc["ssid"] = "";
    doc["password"] = "";
  } else {
    doc.to<JsonObject>();  // unknown file: empty object
  }
}

bool begin() {
  if (!LittleFS.begin()) {
    // First boot on a blank chip: format then retry.
    if (!LittleFS.format() || !LittleFS.begin()) {
      return false;
    }
  }
  if (!LittleFS.exists(DATA_DIR)) {
    LittleFS.mkdir(DATA_DIR);
  }
  return true;
}

void load(const char* name, JsonDocument& doc) {
  File f = LittleFS.open(path(name), "r");
  if (f) {
    DeserializationError err = deserializeJson(doc, f);
    f.close();
    if (!err) return;
  }
  // Missing or corrupt: fall back to defaults and persist them.
  seedDefault(name, doc);
  save(name, doc);
}

bool save(const char* name, const JsonDocument& doc) {
  if (!LittleFS.exists(DATA_DIR)) {
    LittleFS.mkdir(DATA_DIR);
  }
  // Write to a sibling then swap, so an interrupted write can't truncate the
  // live file.
  String target = path(name);
  String tmp = target + ".tmp";

  File f = LittleFS.open(tmp, "w");
  if (!f) return false;
  size_t written = serializeJson(doc, f);
  f.close();
  if (written == 0) {
    LittleFS.remove(tmp);
    return false;
  }

  LittleFS.remove(target);
  return LittleFS.rename(tmp, target);
}

}  // namespace settings_store
