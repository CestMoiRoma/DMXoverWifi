#include "mqtt_manager.h"

#include "settings_store.h"

MqttManager* MqttManager::s_instance = nullptr;

MqttManager::MqttManager(DeviceManager& dm) : _dm(dm), _client(_net) {}

void MqttManager::begin() { reloadConfig(); }

void MqttManager::reloadConfig() { settings_store::load("mqtt.json", _cfg); }

void MqttManager::setConfig(JsonObjectConst cfg) {
  for (JsonPairConst kv : cfg) {
    _cfg[kv.key()] = kv.value();
  }
  settings_store::save("mqtt.json", _cfg);
}

void MqttManager::copyConfigTo(JsonObject out) const {
  for (JsonPairConst kv : _cfg.as<JsonObjectConst>()) {
    out[kv.key()] = kv.value();
  }
}

String MqttManager::baseTopic() const {
  return String((const char*)(_cfg["base_topic"] | "dmxwifi"));
}

String MqttManager::discoveryPrefix() const {
  return String((const char*)(_cfg["discovery_prefix"] | "homeassistant"));
}

String MqttManager::uid(const String& deviceId, int offset) {
  return deviceId + "_" + String(offset);
}

void MqttManager::start() {
  stop();
  if (!(_cfg["enabled"] | false)) return;
  String host = (const char*)(_cfg["host"] | "");
  if (!host.length()) return;

  int port = _cfg["port"] | 1883;
  _client.setServer(host.c_str(), port);
  _client.setBufferSize(1024);  // HA discovery payloads exceed the 256 default
  _client.setCallback(&MqttManager::trampoline);
  s_instance = this;
  connect();
}

bool MqttManager::connect() {
#if defined(ESP8266)
  String clientId = "dmxwifi-" + String(ESP.getChipId(), HEX);
#else
  String clientId = "dmxwifi-" + String((uint32_t)ESP.getEfuseMac(), HEX);
#endif
  String user = (const char*)(_cfg["username"] | "");
  String pass = (const char*)(_cfg["password"] | "");

  bool ok;
  if (user.length()) {
    ok = _client.connect(clientId.c_str(), user.c_str(), pass.c_str());
  } else {
    ok = _client.connect(clientId.c_str());
  }
  if (ok) publishDiscovery();
  return ok;
}

void MqttManager::stop() {
  if (_client.connected()) _client.disconnect();
}

void MqttManager::loop() {
  if (!(_cfg["enabled"] | false)) return;
  if (!String((const char*)(_cfg["host"] | "")).length()) return;

  if (_client.connected()) {
    _client.loop();
    return;
  }
  // Dropped connection: retry on a slow cadence so a down broker doesn't stall
  // the DMX loop.
  uint32_t now = millis();
  if (now - _lastReconnect >= 5000) {
    _lastReconnect = now;
    connect();
  }
}

void MqttManager::statusToJson(JsonObject out) const {
  out["enabled"] = (bool)(_cfg["enabled"] | false);
  out["broker"] = (const char*)(_cfg["host"] | "");
  out["connected"] = const_cast<PubSubClient&>(_client).connected();
}

void MqttManager::publishDiscovery() {
  if (!_client.connected()) return;
  String prefix = discoveryPrefix();
  String base = baseTopic();

  for (Device& device : _dm.devices()) {
    for (Channel& channel : device.channels) {
      String u = uid(device.id, channel.offset);
      String commandTopic = base + "/" + u + "/set";
      String stateTopic = base + "/" + u + "/state";

      JsonDocument payload;
      payload["name"] = channel.name;
      payload["unique_id"] = u;
      payload["command_topic"] = commandTopic;

      String configTopic;
      if (channel.type == "slider") {
        payload["state_topic"] = stateTopic;
        payload["min"] = 0;
        payload["max"] = 255;
        payload["step"] = 1;
        configTopic = prefix + "/number/" + u + "/config";
      } else if (channel.type == "button-switch") {
        payload["state_topic"] = stateTopic;
        payload["payload_on"] = "255";
        payload["payload_off"] = "0";
        payload["state_on"] = "255";
        payload["state_off"] = "0";
        configTopic = prefix + "/switch/" + u + "/config";
      } else {
        // button + button-momentary map to HA's button entity (press event).
        configTopic = prefix + "/button/" + u + "/config";
      }

      JsonObject deviceBlock = payload["device"].to<JsonObject>();
      deviceBlock["identifiers"].to<JsonArray>().add(device.id);
      deviceBlock["name"] = device.name;
      deviceBlock["manufacturer"] = "DIY";
      deviceBlock["model"] = "DMX-over-WiFi";

      String out;
      serializeJson(payload, out);
      _client.publish(configTopic.c_str(), out.c_str(), true);
      _client.subscribe(commandTopic.c_str());
    }
  }
}

void MqttManager::onMessage(char* topic, uint8_t* payload, unsigned int len) {
  String t = topic;
  String prefix = baseTopic() + "/";
  if (!t.startsWith(prefix) || !t.endsWith("/set")) return;

  String u = t.substring(prefix.length(), t.length() - 4);  // drop prefix and "/set"
  int us = u.lastIndexOf('_');
  if (us < 0) return;
  String deviceId = u.substring(0, us);
  int offset = u.substring(us + 1).toInt();

  String msg;
  msg.reserve(len);
  for (unsigned int i = 0; i < len; i++) msg += (char)payload[i];

  Channel* channel = nullptr;
  for (Device& device : _dm.devices()) {
    if (device.id != deviceId) continue;
    for (Channel& c : device.channels) {
      if (c.offset == offset) {
        channel = &c;
        break;
      }
    }
    break;
  }
  if (!channel) return;

  int value;
  if (channel->type == "button" || channel->type == "button-momentary") {
    value = 255;
  } else if (channel->type == "button-switch") {
    String p = msg;
    p.trim();
    p.toUpperCase();
    if (p == "ON" || p == "TRUE" || p == "1" || p == "255") {
      value = 255;
    } else if (p == "OFF" || p == "FALSE" || p == "0") {
      value = 0;
    } else {
      return;
    }
  } else {
    value = (int)msg.toFloat();
  }

  _dm.setValue(deviceId, offset, value);
  if (channel->type == "slider" || channel->type == "button-switch") {
    publishState(deviceId, offset, value);
  }
}

void MqttManager::publishState(const String& deviceId, int offset, int value) {
  if (!_client.connected()) return;
  String stateTopic = baseTopic() + "/" + uid(deviceId, offset) + "/state";
  _client.publish(stateTopic.c_str(), String(value).c_str());
}

void MqttManager::trampoline(char* topic, uint8_t* payload, unsigned int len) {
  if (s_instance) s_instance->onMessage(topic, payload, len);
}
