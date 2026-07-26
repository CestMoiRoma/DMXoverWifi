#include "mqtt_manager.h"

#include "settings_store.h"

MqttManager* MqttManager::s_instance = nullptr;

MqttManager::MqttManager(DeviceManager& dm, SceneStore& scenes)
    : _dm(dm), _scenes(scenes), _client(_net) {}

void MqttManager::begin() { reloadConfig(); }

void MqttManager::reloadConfig() { settings_store::load("mqtt.json", _cfg); }

void MqttManager::setConfig(JsonObjectConst cfg) {
  for (JsonPairConst kv : cfg) {
    // A browser form posts everything as text, and a port stored as "1883" is
    // not an integer as far as ArduinoJson is concerned: `_cfg["port"] | 1883`
    // would hand back the default and the board would dial a door nobody asked
    // for. Coerced here rather than trusted at every read.
    if (strcmp(kv.key().c_str(), "port") == 0) {
      int port = 0;
      if (kv.value().is<int>()) port = kv.value().as<int>();
      else if (kv.value().is<const char*>()) port = String(kv.value().as<const char*>()).toInt();
      if (port <= 0 || port > 65535) port = 1883;
      _cfg["port"] = port;
      continue;
    }
    // A hostname with a stray space resolves to nothing and reports it as an
    // unreachable broker, which sends you looking at the broker.
    if (strcmp(kv.key().c_str(), "host") == 0 && kv.value().is<const char*>()) {
      String host = kv.value().as<const char*>();
      host.trim();
      _cfg["host"] = host;
      continue;
    }
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

String MqttManager::clientId() const {
#if defined(ESP8266)
  return "dmxwifi-" + String(ESP.getChipId(), HEX);
#else
  return "dmxwifi-" + String((uint32_t)ESP.getEfuseMac(), HEX);
#endif
}

bool MqttManager::configured() const {
  if (!(_cfg["enabled"] | false)) return false;
  return String((const char*)(_cfg["host"] | "")).length() > 0;
}

// The bridge speaks over WiFiClient, so a board on the wired link alone cannot
// reach a broker. Reported rather than retried in silence.
bool MqttManager::networkUp() const { return WiFi.status() == WL_CONNECTED; }

void MqttManager::applyServer() {
  String host = (const char*)(_cfg["host"] | "");
  if (host != _host) _ipValid = false;  // a new name deserves a new lookup
  _host = host;
  _client.setServer(_host.c_str(), (uint16_t)(_cfg["port"] | 1883));
  _client.setBufferSize(1024);  // HA discovery payloads exceed the 256 default
  _client.setKeepAlive(20);
  // Only the wait for the broker's CONNACK now: the TCP connection is made in
  // openSocket() below, on a much shorter leash than PubSubClient would use.
  _client.setSocketTimeout(2);
  _client.setCallback(&MqttManager::trampoline);
  s_instance = this;
}

void MqttManager::start() {
  stop();
  _retryMs = kRetryMinMs;
  if (!configured()) return;
  applyServer();
  if (networkUp()) connect();
}

void MqttManager::connectNow() {
  if (_client.connected()) _client.disconnect();
  _retryMs = kRetryMinMs;
  if (!configured()) return;
  applyServer();
  if (networkUp()) connect();
}

void MqttManager::backoff() {
  _retryMs = _retryMs * 2;
  if (_retryMs > (uint32_t)kRetryMaxMs) _retryMs = kRetryMaxMs;
}

// A name is looked up once and remembered. Repeating a DNS query on every retry
// is how a wrong hostname turns into a stall every few seconds.
bool MqttManager::resolveHost(IPAddress& out) {
  if (_ipValid) {
    out = _ip;
    return true;
  }
  if (out.fromString(_host)) {  // already an address, nothing to ask anyone
    _ip = out;
    _ipValid = true;
    return true;
  }

  IPAddress found;
  bool ok;
  if (_host.endsWith(".local")) {
    // A .local name is mDNS, not DNS. Asking a DNS server for it fails, and
    // "homeassistant.local" is what most people will type.
    String bare = _host.substring(0, _host.length() - 6);
#if defined(ESP8266)
    found = MDNS.queryHost(bare, 1000);
    ok = found != INADDR_NONE && (uint32_t)found != 0;
#else
    found = MDNS.queryHost(bare, 1000);
    ok = (uint32_t)found != 0;
#endif
  } else {
    ok = WiFi.hostByName(_host.c_str(), found) == 1;
  }
  if (!ok) return false;

  _ip = found;
  _ipValid = true;
  out = found;
  return true;
}

// The TCP half of connecting, done here rather than inside PubSubClient so it
// can be given a deadline. PubSubClient reuses a socket that is already open,
// so this costs nothing but control.
bool MqttManager::openSocket() {
  if (_net.connected()) return true;

  IPAddress ip;
  if (!resolveHost(ip)) {
    _lastState = -2;
    _lastError = _host.endsWith(".local") ? "that .local name did not answer on mDNS"
                                          : "that broker name did not resolve";
    return false;
  }

  uint16_t port = (uint16_t)(_cfg["port"] | 1883);
#if defined(ESP8266)
  _net.setTimeout(kTcpTimeoutMs);
  bool up = _net.connect(ip, port);
#else
  bool up = _net.connect(ip, port, kTcpTimeoutMs) == 1;
#endif
  if (!up) {
    _net.stop();
    _lastState = -2;
    _lastError = "nothing answered on that host and port";
    return false;
  }
  return true;
}

bool MqttManager::connect() {
  _attempts++;
  _lastAttempt = millis();

  if (!openSocket()) {
    backoff();
    return false;
  }

  String user = (const char*)(_cfg["username"] | "");
  String pass = (const char*)(_cfg["password"] | "");
  // A last will, so Home Assistant marks the entities unavailable when the
  // board drops off instead of showing the last value it happened to hear.
  String availability = baseTopic() + "/status";
  String id = clientId();

  bool ok = _client.connect(id.c_str(), user.length() ? user.c_str() : nullptr,
                            user.length() ? pass.c_str() : nullptr, availability.c_str(), 0, true,
                            "offline");
  if (ok) {
    _client.publish(availability.c_str(), "online", true);
    _everConnected = true;
    _wasConnected = true;
    _connectedSince = millis();
    _retryMs = kRetryMinMs;
    _lastState = 0;
    _lastError = "";
    publishDiscovery();
    return true;
  }

  _lastState = _client.state();
  _lastError = stateText(_lastState);
  _net.stop();
  backoff();
  return false;
}

void MqttManager::stop() {
  if (_client.connected()) _client.disconnect();
  _wasConnected = false;
}

void MqttManager::loop() {
  if (!configured()) return;

  if (_client.connected()) {
    _client.loop();
    return;
  }
  // Note the drop once, while the client still knows why, rather than reporting
  // the generic disconnected state forever after.
  if (_wasConnected) {
    _wasConnected = false;
    _lastState = _client.state();
    _lastError = stateText(_lastState);
  }
  if (!networkUp()) return;

  if (millis() - _lastAttempt >= _retryMs) {
    applyServer();
    connect();
  }
}

String MqttManager::stateText(int state) {
  switch (state) {
    case -4: return "the broker stopped answering, keepalive timed out";
    case -3: return "the network connection was lost";
    case -2: return "nothing answered on that host and port";
    case -1: return "disconnected";
    case 0: return "connected";
    case 1: return "the broker refused the protocol version";
    case 2: return "the broker rejected the client id";
    case 3: return "the broker is unavailable";
    case 4: return "the broker refused the username or password";
    case 5: return "the broker refused this client, not authorised";
    default: return "unknown state " + String(state);
  }
}

void MqttManager::statusToJson(JsonObject out) const {
  PubSubClient& client = const_cast<PubSubClient&>(_client);
  bool enabled = _cfg["enabled"] | false;
  String host = (const char*)(_cfg["host"] | "");
  bool connected = client.connected();

  out["enabled"] = enabled;
  out["broker"] = host;
  out["port"] = (int)(_cfg["port"] | 1883);
  out["base_topic"] = baseTopic();
  out["discovery_prefix"] = discoveryPrefix();
  out["client_id"] = clientId();
  out["connected"] = connected;
  out["state"] = client.state();
  out["state_text"] = stateText(client.state());
  out["attempts"] = _attempts;
  out["ever_connected"] = _everConnected;
  out["entities"] = _entities;
  if (connected) out["connected_for_s"] = (millis() - _connectedSince) / 1000;
  if (_lastError.length()) out["last_error"] = _lastError;

  // One sentence naming what is in the way, in the order a person would check.
  if (!enabled) {
    out["reason"] = "the MQTT bridge is switched off under Modules";
  } else if (!host.length()) {
    out["reason"] = "no broker host is set";
  } else if (!networkUp()) {
    out["reason"] = "the board is not on a WiFi network, and the bridge speaks over WiFi";
  } else if (!connected) {
    out["reason"] = _lastError.length() ? _lastError : "no connection attempt has finished yet";
    uint32_t waited = millis() - _lastAttempt;
    out["next_retry_s"] = waited >= _retryMs ? 0 : (_retryMs - waited + 999) / 1000;
  }
}

void MqttManager::publishDiscovery() {
  if (!_client.connected()) return;
  String prefix = discoveryPrefix();
  String base = baseTopic();
  String availability = base + "/status";
  _entities = 0;

  for (Device& device : _dm.devices()) {
    for (Channel& channel : device.channels) {
      String u = uid(device.id, channel.offset);
      String commandTopic = base + "/" + u + "/set";
      String stateTopic = base + "/" + u + "/state";

      JsonDocument payload;
      payload["name"] = channel.name;
      payload["unique_id"] = u;
      payload["command_topic"] = commandTopic;
      payload["availability_topic"] = availability;

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
      if (_client.publish(configTopic.c_str(), out.c_str(), true)) _entities++;
      _client.subscribe(commandTopic.c_str());
    }
  }

  // Scenes, as Home Assistant scene entities. Stateless by nature: a scene is
  // something you fire, not something that is on, so there is no state topic
  // and nothing to keep in step.
  for (const Scene& scene : _scenes.scenes()) {
    String commandTopic = base + "/scene/" + scene.id + "/set";

    JsonDocument payload;
    payload["name"] = scene.name;
    payload["unique_id"] = scene.id;
    payload["command_topic"] = commandTopic;
    payload["payload_on"] = "ON";
    payload["availability_topic"] = availability;
    if (scene.description.length()) payload["icon"] = "mdi:palette";

    // All the scenes hang off one device, the board itself, rather than
    // scattering loose entities through the integration.
    JsonObject deviceBlock = payload["device"].to<JsonObject>();
    deviceBlock["identifiers"].to<JsonArray>().add(clientId());
    deviceBlock["name"] = "DMX over WiFi";
    deviceBlock["manufacturer"] = "DIY";
    deviceBlock["model"] = "DMX-over-WiFi";

    String out;
    serializeJson(payload, out);
    if (_client.publish((prefix + "/scene/" + scene.id + "/config").c_str(), out.c_str(), true)) {
      _entities++;
    }
    _client.subscribe(commandTopic.c_str());
  }

  // The emergency stop, on the same device as the scenes. Somebody holding a
  // phone in another room should be able to kill the rig without first finding
  // the web UI and the right page of it.
  {
    String commandTopic = base + "/estop/set";
    String u = clientId() + "_estop";

    JsonDocument payload;
    payload["name"] = "Emergency stop";
    payload["unique_id"] = u;
    payload["command_topic"] = commandTopic;
    payload["availability_topic"] = availability;
    payload["icon"] = "mdi:alert-octagon";

    JsonObject deviceBlock = payload["device"].to<JsonObject>();
    deviceBlock["identifiers"].to<JsonArray>().add(clientId());
    deviceBlock["name"] = "DMX over WiFi";
    deviceBlock["manufacturer"] = "DIY";
    deviceBlock["model"] = "DMX-over-WiFi";

    String out;
    serializeJson(payload, out);
    if (_client.publish((prefix + "/button/" + u + "/config").c_str(), out.c_str(), true)) {
      _entities++;
    }
    _client.subscribe(commandTopic.c_str());
  }

  // Discovery says what exists; this says where it currently stands.
  publishAllStates();
}

void MqttManager::publishAllStates() {
  if (!_client.connected()) return;
  for (Device& device : _dm.devices()) {
    for (Channel& channel : device.channels) {
      // Buttons have no state to report: pressing one is an event, and there is
      // no such thing as a button that is currently pressed here.
      if (channel.type != "slider" && channel.type != "button-switch") continue;
      publishState(device.id, channel.offset, _dm.getValue(device, channel));
    }
  }
}

// An empty retained payload on a config topic is how MQTT discovery says "this
// entity is gone". Without it Home Assistant keeps showing a fixture that no
// longer exists on a board that never mentions it again.
void MqttManager::dropDevice(const Device& device) {
  if (!_client.connected()) return;
  String prefix = discoveryPrefix();
  for (const Channel& channel : device.channels) {
    String u = uid(device.id, channel.offset);
    _client.publish((prefix + "/number/" + u + "/config").c_str(), "", true);
    _client.publish((prefix + "/switch/" + u + "/config").c_str(), "", true);
    _client.publish((prefix + "/button/" + u + "/config").c_str(), "", true);
    _client.unsubscribe((baseTopic() + "/" + u + "/set").c_str());
  }
}

void MqttManager::dropScene(const String& sceneId) {
  if (!_client.connected()) return;
  _client.publish((discoveryPrefix() + "/scene/" + sceneId + "/config").c_str(), "", true);
  _client.unsubscribe((baseTopic() + "/scene/" + sceneId + "/set").c_str());
}

void MqttManager::onMessage(char* topic, uint8_t* payload, unsigned int len) {
  String t = topic;
  String prefix = baseTopic() + "/";
  if (!t.startsWith(prefix) || !t.endsWith("/set")) return;

  String u = t.substring(prefix.length(), t.length() - 4);  // drop prefix and "/set"

  // Everything to zero, whatever the payload says. A panic button that argues
  // about its argument is not a panic button.
  if (u == "estop") {
    _dm.allOff();
    publishAllStates();
    return;
  }

  // A scene is fired, not set. Any payload does it: Home Assistant sends "ON",
  // and an automation written by hand should not have to guess the word.
  if (u.startsWith("scene/")) {
    JsonDocument doc;
    JsonArray missing = doc.to<JsonArray>();
    _scenes.play(u.substring(6), _dm, missing);
    return;
  }

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
  // Retained, so a Home Assistant that restarts learns the rig's state from the
  // broker instead of waiting for the next time somebody moves something. The
  // last will covers the case where the value is retained but the board is gone.
  _client.publish(stateTopic.c_str(), String(value).c_str(), true);
}

void MqttManager::trampoline(char* topic, uint8_t* payload, unsigned int len) {
  if (s_instance) s_instance->onMessage(topic, payload, len);
}
