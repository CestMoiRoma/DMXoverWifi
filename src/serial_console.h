#pragma once

#include <map>
#include <vector>

#include "devices.h"
#include "labels.h"
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
  SerialConsole(DeviceManager& devices, LabelStore& labels, WifiManager& wifi, MqttManager& mqtt)
      : _devices(devices), _labels(labels), _wifi(wifi), _mqtt(mqtt) {}

  void begin();
  void poll();

 private:
  void handleLine(const String& line);
  void write(const String& text);

  // ---- binary control channel ----
  //
  // The text console is fine for configuring a board but hopeless for driving
  // it: "Set-Value channel=Red device=PAR value=200" is forty-odd bytes and a
  // string parse for one DMX slot, which a dragged fader would send hundreds of
  // times a second. Frames sit alongside the text on the same link, told apart
  // by a start byte the text protocol never begins a line with.
  //
  //   host -> board   7E <cmd> <len> <payload...> <crc8>
  //   board -> host   7E <cmd|0x80> <len> <payload...> <crc8>
  //
  // crc8 is the classic poly 0x07 over cmd, len and payload.
  static const uint8_t FRAME_START = 0x7E;
  static const uint8_t CMD_SET_ADDR = 0x01;   // addr_hi addr_lo value
  static const uint8_t CMD_SET_BLOCK = 0x02;  // addr_hi addr_lo count values...
  static const uint8_t CMD_GET_BLOCK = 0x03;  // addr_hi addr_lo count
  static const uint8_t CMD_PING = 0x10;       // no payload
  static const uint8_t REPLY_FLAG = 0x80;
  static const size_t MAX_PAYLOAD = 255;

  enum BinaryState { BIN_IDLE, BIN_CMD, BIN_LEN, BIN_PAYLOAD, BIN_CRC };

  void feedBinary(uint8_t byte);
  void dispatchFrame();
  void sendFrame(uint8_t cmd, const uint8_t* payload, size_t length);

  // shared operations
  void wifiAdd(const ParsedArgs& a);
  void mqttEnable(const ParsedArgs& a);
  void mqttDisable();

  // top-level
  void cmdSetSystem(const String& rest);
  void cmdSetDevice(const String& rest);
  void cmdSetValue(const String& rest);
  void cmdGetConfig();
  void cmdGetStatus(const String& rest);
  void cmdHelp();
  void cmdReboot();

  // output/error accumulation for the current line
  void emit(const String& line) { _out.push_back(line); }
  void fail(const String& msg) { _err = msg; }

  DeviceManager& _devices;
  LabelStore& _labels;
  WifiManager& _wifi;
  MqttManager& _mqtt;

  String _buffer;
  std::vector<String> _out;
  String _err;

  BinaryState _binState = BIN_IDLE;
  uint8_t _binCmd = 0;
  uint8_t _binLen = 0;
  uint8_t _binPayload[MAX_PAYLOAD];
  size_t _binIndex = 0;
};
