#pragma once

#include <ArduinoJson.h>

#if defined(ESP8266)
#include <ESP8266WebServer.h>
using WebServerClass = ESP8266WebServer;
#else
#include <WebServer.h>
using WebServerClass = WebServer;
#endif

#include "devices.h"
#include "labels.h"
#include "mqtt_manager.h"
#include "wifi_manager.h"

// Serves the web UI (unless WITH_WEBUI is 0) and the REST API the UI, the MQTT
// bridge and external clients all speak. Synchronous: driven by handleClient()
// from the main loop, mirroring the CircuitPython poll model.
class DmxWebServer {
 public:
  DmxWebServer(DeviceManager& devices, LabelStore& labels, WifiManager& wifi, MqttManager& mqtt)
      : _devices(devices), _labels(labels), _wifi(wifi), _mqtt(mqtt), _server(80) {}

  void begin();
  void handleClient() { _server.handleClient(); }

 private:
  void registerRoutes();

  // helpers
  void parseBody(JsonDocument& doc);
  void sendJson(int status, const JsonDocument& doc);
  void sendError(int status, const char* msg);
  bool serveFile(const char* path, const char* contentType);
  String buildEnvText();

  // Whole-config snapshot and restore, the .json counterpart of the .env export.
  void buildConfigJson(JsonDocument& out);
  void applyConfigJson(JsonObjectConst in);

  DeviceManager& _devices;
  LabelStore& _labels;
  WifiManager& _wifi;
  MqttManager& _mqtt;
  WebServerClass _server;
};
