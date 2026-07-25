#pragma once

#include <ArduinoJson.h>
#include <PubSubClient.h>

#if defined(ESP8266)
#include <ESP8266WiFi.h>
#else
#include <WiFi.h>
#endif

#include "devices.h"

// Optional MQTT bridge with Home Assistant auto-discovery. Publishes a number /
// switch / button entity per channel and applies inbound commands to the DMX
// output.
class MqttManager {
 public:
  explicit MqttManager(DeviceManager& dm);

  void begin();  // load config
  void reloadConfig();
  void setConfig(JsonObjectConst cfg);   // merge + persist
  void copyConfigTo(JsonObject out) const;

  void start();
  void stop();
  void loop();

  void statusToJson(JsonObject out) const;
  void publishDiscovery();
  void publishState(const String& deviceId, int offset, int value);

  // Called from the PubSubClient trampoline.
  void onMessage(char* topic, uint8_t* payload, unsigned int len);

 private:
  bool connect();
  String baseTopic() const;
  String discoveryPrefix() const;
  static String uid(const String& deviceId, int offset);

  static void trampoline(char* topic, uint8_t* payload, unsigned int len);
  static MqttManager* s_instance;

  DeviceManager& _dm;
  JsonDocument _cfg;
  WiFiClient _net;
  PubSubClient _client;
  uint32_t _lastReconnect = 0;
};
