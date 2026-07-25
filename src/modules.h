#pragma once

#include <ArduinoJson.h>

// Runtime switches for the optional subsystems, plus the API key that gates
// external access. Persisted to api.json, which is what the Settings > API page
// edits.
//
// The MQTT switch is not the same thing as mqtt.json's `enabled`: that one says
// "a broker is configured, connect to it", this one says "run the MQTT
// subsystem at all". Turning the module off leaves the broker settings intact
// for when it comes back.
class ModuleSettings {
 public:
  void begin();  // load, and mint an API key on first run

  bool httpApiEnabled() const { return _httpApi; }
  bool websocketEnabled() const { return _websocket; }
  bool mqttEnabled() const { return _mqtt; }
  const String& apiKey() const { return _apiKey; }

  bool keyMatches(const String& candidate) const;

  void setFromJson(JsonObjectConst in);  // merge and persist
  String regenerateKey();
  void toJson(JsonObject out) const;

 private:
  void load();
  void save();
  static String randomKey();

  bool _httpApi = true;
  bool _websocket = true;
  bool _mqtt = true;
  String _apiKey;
};
