#include "modules.h"

#include "settings_store.h"

void ModuleSettings::begin() {
  load();
  if (!_apiKey.length()) {
    _apiKey = randomKey();
    save();
  }
}

void ModuleSettings::load() {
  JsonDocument doc;
  settings_store::load("api.json", doc);
  _httpApi = doc["http_api_enabled"] | true;
  _websocket = doc["websocket_enabled"] | true;
  _mqtt = doc["mqtt_enabled"] | true;
  _apiKey = (const char*)(doc["api_key"] | "");
}

void ModuleSettings::save() {
  JsonDocument doc;
  toJson(doc.to<JsonObject>());
  doc["api_key"] = _apiKey;  // toJson deliberately leaves the key out
  settings_store::save("api.json", doc);
}

String ModuleSettings::randomKey() {
  // Arduino's Print.h defines HEX as a macro, hence the longer name.
  static const char* HEX_DIGITS = "0123456789abcdef";
  String key;
  key.reserve(64);  // 8 words x 4 bytes x 2 hex digits
  for (int i = 0; i < 8; i++) {
#if defined(ESP8266)
    uint32_t r = RANDOM_REG32;
#else
    uint32_t r = esp_random();
#endif
    for (int j = 0; j < 4; j++) {
      key += HEX_DIGITS[(r >> (j * 8 + 4)) & 0xF];
      key += HEX_DIGITS[(r >> (j * 8)) & 0xF];
    }
  }
  return key;
}

// Constant-time-ish compare. The board is on a LAN behind a key that is not a
// password, so this is about not leaking length rather than real hardening.
bool ModuleSettings::keyMatches(const String& candidate) const {
  if (!_apiKey.length()) return false;
  if (candidate.length() != _apiKey.length()) return false;
  uint8_t diff = 0;
  for (size_t i = 0; i < _apiKey.length(); i++) diff |= (uint8_t)(_apiKey[i] ^ candidate[i]);
  return diff == 0;
}

void ModuleSettings::setFromJson(JsonObjectConst in) {
  if (!in["http_api_enabled"].isNull()) _httpApi = in["http_api_enabled"].as<bool>();
  if (!in["websocket_enabled"].isNull()) _websocket = in["websocket_enabled"].as<bool>();
  if (!in["mqtt_enabled"].isNull()) _mqtt = in["mqtt_enabled"].as<bool>();
  save();
}

String ModuleSettings::regenerateKey() {
  _apiKey = randomKey();
  save();
  return _apiKey;
}

void ModuleSettings::toJson(JsonObject out) const {
  out["http_api_enabled"] = _httpApi;
  out["websocket_enabled"] = _websocket;
  out["mqtt_enabled"] = _mqtt;
}
