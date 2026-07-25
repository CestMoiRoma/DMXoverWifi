#include "ws_server.h"

void WsServer::begin() {
  if (!_modules.websocketEnabled()) return;
  _server.begin();
  // A browser that navigates away or reloads does not always close its socket,
  // and the library holds a small fixed number of clients. Without this, a few
  // reloads fill the table with sockets nobody is on the other end of, and every
  // new connection is refused with a reset. Ping every 15 s, expect a pong
  // within 3 s, drop after two misses.
  _server.enableHeartbeat(15000, 3000, 2);
  _server.onEvent([this](uint8_t num, WStype_t type, uint8_t* payload, size_t length) {
    onEvent(num, type, payload, length);
  });
  _running = true;
}

void WsServer::loop() {
  if (_running) _server.loop();
}

// The socket has no Origin exemption: unlike the UI's own fetches, a WebSocket
// is just as reachable from a script, so every client presents the key. The UI
// reads it from /api/modules and puts it in the connect URL.
bool WsServer::authorize(const String& url) {
  int q = url.indexOf("api_key=");
  if (q < 0) return false;
  String key = url.substring(q + 8);
  int amp = key.indexOf('&');
  if (amp >= 0) key = key.substring(0, amp);
  return _modules.keyMatches(key);
}

void WsServer::onEvent(uint8_t num, WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED: {
      // For a server, the payload of CONNECTED is the requested URL.
      String url = payload ? String((const char*)payload) : String("");
      if (!authorize(url)) {
        _server.disconnect(num);
        return;
      }
      JsonDocument doc;
      doc["t"] = "hello";
      doc["clients"] = _server.connectedClients();
      String out;
      serializeJson(doc, out);
      _server.sendTXT(num, out);
      break;
    }
    case WStype_TEXT: {
      String text;
      text.reserve(length + 1);
      for (size_t i = 0; i < length; i++) text += (char)payload[i];
      handleFrame(num, text);
      break;
    }
    default:
      break;
  }
}

void WsServer::handleFrame(uint8_t num, const String& text) {
  JsonDocument doc;
  if (deserializeJson(doc, text)) return;  // malformed frames are dropped in silence

  String kind = (const char*)(doc["t"] | "");
  int value = doc["v"] | 0;
  if (value < 0) value = 0;
  if (value > 255) value = 255;

  if (kind == "set") {
    String deviceId = (const char*)(doc["d"] | "");
    int offset = doc["o"] | 0;
    // setValue tells the world through the DeviceManager callback, which is
    // what fans this out to the other clients, so nothing is echoed here.
    _devices.setValue(deviceId, offset, value);
  } else if (kind == "seta") {
    int address = doc["a"] | 0;
    if (address >= 1 && address <= 512) _devices.dmx().setChannel(address, value);
  }
}

void WsServer::broadcastValue(const String& deviceId, int offset, int value) {
  if (!_running || _server.connectedClients() == 0) return;
  JsonDocument doc;
  doc["t"] = "val";
  doc["d"] = deviceId;
  doc["o"] = offset;
  doc["v"] = value;
  String out;
  serializeJson(doc, out);
  _server.broadcastTXT(out);
}
