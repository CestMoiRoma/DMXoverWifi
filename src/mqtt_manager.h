#pragma once

#include <ArduinoJson.h>
#include <PubSubClient.h>

#if defined(ESP8266)
#include <ESP8266WiFi.h>
#include <ESP8266mDNS.h>
#else
#include <ESPmDNS.h>
#include <WiFi.h>
#endif

#include "devices.h"
#include "scenes.h"

// Optional MQTT bridge with Home Assistant auto-discovery. Publishes a number /
// switch / button entity per channel and applies inbound commands to the DMX
// output.
//
// The bridge says what it is doing. A broker that cannot be reached, a password
// the broker refuses and a module that was never switched on all look the same
// from the outside, so every attempt records why it ended and `statusToJson`
// reports it. Guessing from silence is what this class exists to avoid.
class MqttManager {
 public:
  MqttManager(DeviceManager& dm, SceneStore& scenes);

  void begin();  // load config
  void reloadConfig();
  void setConfig(JsonObjectConst cfg);   // merge + persist
  void copyConfigTo(JsonObject out) const;

  void start();
  void stop();
  void loop();

  // An attempt asked for by a person, so it ignores the backoff and reports
  // what happened rather than waiting for the next slot.
  void connectNow();

  void statusToJson(JsonObject out) const;
  void publishDiscovery();
  void publishState(const String& deviceId, int offset, int value);

  // Every channel's current value, sent after discovery. A broker that has just
  // met this board knows nothing about a rig that has been lit for an hour, and
  // a value published only when it changes would leave Home Assistant showing
  // zero until somebody moved a fader.
  void publishAllStates();

  // Retained discovery outlives whatever published it, so a fixture or a scene
  // that is deleted here has to be withdrawn there too. Called before the thing
  // itself goes, while its channels can still be named.
  void dropDevice(const Device& device);
  void dropScene(const String& sceneId);

  // Called from the PubSubClient trampoline.
  void onMessage(char* topic, uint8_t* payload, unsigned int len);

 private:
  bool connect();
  bool openSocket();      // the TCP half, on a short leash
  bool resolveHost(IPAddress& out);
  void backoff();
  void applyServer();
  bool configured() const;
  bool networkUp() const;
  String clientId() const;
  static String stateText(int state);

  String baseTopic() const;
  String discoveryPrefix() const;
  static String uid(const String& deviceId, int offset);

  static void trampoline(char* topic, uint8_t* payload, unsigned int len);
  static MqttManager* s_instance;

  // A broker that is down must not cost more than a moment per minute. Each
  // failure doubles the wait, so a wrong hostname typed at eleven at night is
  // retried twice a minute rather than twelve times, and the DMX loop keeps its
  // time. A success puts it back to the short wait.
  enum : uint32_t { kRetryMinMs = 5000, kRetryMaxMs = 60000 };
  // How long a single connection attempt may hold the loop. A broker on the
  // same LAN answers a SYN in under a millisecond; a host that is not there
  // costs this much and no more. PubSubClient's own connect would spend
  // seconds here, and seconds are dark fixtures and queued HTTP requests.
  enum : uint32_t { kTcpTimeoutMs = 250 };

  DeviceManager& _dm;
  SceneStore& _scenes;
  JsonDocument _cfg;
  WiFiClient _net;
  PubSubClient _client;
  // PubSubClient keeps the pointer it is handed rather than copying the string,
  // so the host has to outlive every call it makes. A local would be freed
  // before the first connect.
  String _host;
  IPAddress _ip;
  bool _ipValid = false;

  uint32_t _lastAttempt = 0;
  uint32_t _retryMs = kRetryMinMs;
  uint32_t _attempts = 0;
  uint32_t _connectedSince = 0;
  bool _everConnected = false;
  bool _wasConnected = false;
  int _lastState = -1;
  String _lastError;
  uint16_t _entities = 0;
};
