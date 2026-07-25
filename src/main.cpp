#include <Arduino.h>
#include <ArduinoJson.h>

#include "config.h"
#include "devices.h"
#include "dmx/dmx_driver.h"
#include "labels.h"
#include "modules.h"
#include "mqtt_manager.h"
#include "serial_console.h"
#include "settings_store.h"
#include "version.h"
#include "web_server.h"
#include "wifi_manager.h"
#include "ws_server.h"

static DmxDriver dmx;
static DeviceManager deviceManager(dmx);
static LabelStore labelStore;
static ModuleSettings modules;
static WifiManager wifiManager;
static MqttManager mqttManager(deviceManager);
static WsServer wsServer(deviceManager, modules);
static DmxWebServer webServer(deviceManager, labelStore, modules, wifiManager, mqttManager);
static SerialConsole serialConsole(deviceManager, labelStore, wifiManager, mqttManager);

void setup() {
  Serial.begin(115200);
  settings_store::begin();

  JsonDocument sys;
  settings_store::load("system.json", sys);

  // DMX output. On ESP8266 the tx pin is a label only (fixed to Serial1/GPIO2).
  int txPin = resolvePin(String((const char*)(sys["dmx_tx_pin"] | DEFAULT_DMX_TX_PIN)));
  int dirPin = -1;
  if (sys["dmx_dir_pin_enabled"] | false) {
    dirPin = resolvePin(String((const char*)(sys["dmx_dir_pin"] | DEFAULT_DMX_DIR_PIN)));
  }
  dmx.begin(txPin, dirPin);

  deviceManager.begin();
  labelStore.begin();
  modules.begin();
  serialConsole.begin();

  // WiFi off means USB-only control: no radio, no web server, no MQTT. The
  // serial console stays the whole interface, which is the point.
  if (!(sys["wifi_enabled"] | true)) {
    wifiManager.setDisabled();
    return;
  }

  wifiManager.begin();
  mqttManager.begin();

  // Join a known network, or fall back to the config hotspot.
  if (!wifiManager.connectKnown()) {
    wifiManager.startAp(sys["ap_ssid"] | "ESP-DMX", sys["ap_password"] | "DMX4ALL1",
                        sys["ap_ip"] | "1.1.1.1");
  }

  webServer.begin();
  wsServer.begin();
  deviceManager.onValueChanged([](const String& deviceId, int offset, int value) {
    wsServer.broadcastValue(deviceId, offset, value);
  });

  if (modules.mqttEnabled() && wifiManager.mode() == "sta") {
    mqttManager.start();
  }
}

void loop() {
  if (!wifiManager.disabled()) {
    webServer.handleClient();
    wsServer.loop();
    wifiManager.loop();
    if (modules.mqttEnabled()) mqttManager.loop();
  }
  dmx.refreshIfDue();
  serialConsole.poll();
}
