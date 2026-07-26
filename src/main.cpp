#include <Arduino.h>
#include <ArduinoJson.h>

#include "config.h"
#include "devices.h"
#include "groups.h"
#include "dmx/dmx_driver.h"
#include "ethernet_manager.h"
#include "labels.h"
#include "modules.h"
#include "mqtt_manager.h"
#include "save_guard.h"
#include "scenes.h"
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
static SaveGuard saveGuard;
static SceneStore sceneStore;
static GroupStore groupStore;
static WifiManager wifiManager;
static EthernetManager ethernet;
static MqttManager mqttManager(deviceManager, sceneStore);
static WsServer wsServer(deviceManager, modules);
static DmxWebServer webServer(deviceManager, labelStore, modules, wifiManager, ethernet,
                              mqttManager, saveGuard, sceneStore, groupStore);
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
  sceneStore.begin();
  groupStore.begin();
  // After the driver exists, so the stored look can be put straight back.
  saveGuard.begin(dmx);
  modules.begin();
  serialConsole.begin();

  // WiFi off means USB-only control: no radio, no web server, no MQTT. The
  // serial console stays the whole interface, which is the point.
  if (!(sys["wifi_enabled"] | true)) {
    wifiManager.setDisabled();
    return;
  }

  // Before WiFi: a wired link that is up saves the radio a scan and a join.
  // Every wait inside is bounded, so a board configured for Ethernet with no
  // adapter attached still gets here.
  ethernet.begin();

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

// Loop timing, reported by /api/info. A single-threaded board that serves HTTP
// between DMX frames lives or dies on how long one pass takes: anything that
// blocks here is time connections spend queued, and a queue that overflows is
// answered with a reset rather than a wait.
static uint32_t s_loopCount = 0;
static uint32_t s_loopMaxUs = 0;
static uint32_t s_loopWindowStart = 0;
uint32_t loopRatePerSecond = 0;
uint32_t loopMaxUs = 0;

void loop() {
  uint32_t loopStart = micros();

  if (!wifiManager.disabled()) {
    webServer.handleClient();
    wsServer.loop();
    wifiManager.loop();
    ethernet.loop();
    if (modules.mqttEnabled()) mqttManager.loop();
  }
  saveGuard.loop();
  deviceManager.tickBursts();
  dmx.refreshIfDue();
  serialConsole.poll();

  uint32_t elapsed = micros() - loopStart;
  if (elapsed > s_loopMaxUs) s_loopMaxUs = elapsed;
  s_loopCount++;
  uint32_t now = millis();
  if (now - s_loopWindowStart >= 1000) {
    loopRatePerSecond = s_loopCount;
    loopMaxUs = s_loopMaxUs;
    s_loopCount = 0;
    s_loopMaxUs = 0;
    s_loopWindowStart = now;
  }
}
