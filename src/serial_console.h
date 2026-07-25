#pragma once

#include <map>
#include <vector>

#include "devices.h"
#include "mqtt_manager.h"
#include "wifi_manager.h"

// Parsed command line: positional tokens plus key=value / key="quoted value".
struct ParsedArgs {
  std::vector<String> bare;
  std::map<String, String> kwargs;
  bool has(const String& k) const { return kwargs.count(k) > 0; }
  String get(const String& k, const String& def = "") const {
    auto it = kwargs.find(k);
    return it == kwargs.end() ? def : it->second;
  }
};

// USB/UART text command set: configure, inspect and reboot the board without a
// browser. Polled from the main loop.
class SerialConsole {
 public:
  SerialConsole(DeviceManager& devices, WifiManager& wifi, MqttManager& mqtt)
      : _devices(devices), _wifi(wifi), _mqtt(mqtt) {}

  void begin();
  void poll();

 private:
  void handleLine(const String& line);
  void write(const String& text);

  // shared operations
  void wifiAdd(const ParsedArgs& a);
  void mqttEnable(const ParsedArgs& a);
  void mqttDisable();

  // top-level
  void cmdSetSystem(const String& rest);
  void cmdSetDevice(const String& rest);
  void cmdSetValue(const String& rest);
  void cmdGetStatus(const String& rest);
  void cmdHelp();
  void cmdReboot();

  // output/error accumulation for the current line
  void emit(const String& line) { _out.push_back(line); }
  void fail(const String& msg) { _err = msg; }

  DeviceManager& _devices;
  WifiManager& _wifi;
  MqttManager& _mqtt;

  String _buffer;
  std::vector<String> _out;
  String _err;
};
