#pragma once

#include <ArduinoJson.h>
#include <WebSocketsServer.h>

#include "config.h"
#include "devices.h"
#include "modules.h"

// Live channel control and state fan-out, on its own port because the Arduino
// web server cannot share 80 with a socket upgrade.
//
// It exists for one reason: a slider dragged across its travel emits a hundred
// values a second, and one HTTP request each would spend more time on headers
// and connection setup than on DMX. It also lets every open client watch the
// rig move, which polling cannot do without hammering the board.
//
// Frames are JSON, since the traffic is small and the readability is worth more
// here than the bytes:
//   in   {"t":"set",  "d":"<deviceId>", "o":<offset>, "v":<0-255>}
//   in   {"t":"seta", "a":<1-512>,      "v":<0-255>}
//   out  {"t":"val",  "d":"<deviceId>", "o":<offset>, "v":<0-255>}
//   out  {"t":"hello","clients":<n>}
class WsServer {
 public:
  WsServer(DeviceManager& devices, ModuleSettings& modules)
      : _devices(devices), _modules(modules), _server(WS_PORT) {}

  static const uint16_t WS_PORT = WS_PORT_NUMBER;

  void begin();  // no-op while the module is switched off
  void loop();
  bool running() const { return _running; }

  // Fans a value out to every client. Called for changes from any source, so a
  // fader moved over HTTP or over serial still shows up in an open browser.
  void broadcastValue(const String& deviceId, int offset, int value);

 private:
  void onEvent(uint8_t num, WStype_t type, uint8_t* payload, size_t length);
  bool authorize(const String& url);
  void handleFrame(uint8_t num, const String& text);

  DeviceManager& _devices;
  ModuleSettings& _modules;
  WebSocketsServer _server;
  bool _running = false;
};
