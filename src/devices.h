#pragma once

#include <ArduinoJson.h>

#include <vector>

#include "dmx/dmx_driver.h"

// A single DMX control within a fixture. `type` is one of:
//   "slider" | "button" | "button-momentary" | "button-switch"
struct Channel {
  int offset = 1;
  String name = "Channel";
  String type = "slider";
};

// A named group of channels mapped onto a contiguous DMX address range starting
// at start_channel.
struct Device {
  String id;
  String name = "Device";
  int start_channel = 1;
  std::vector<Channel> channels;

  int addressFor(const Channel& c) const { return start_channel + c.offset - 1; }
};

// Owns the fixture list, keeps it persisted to devices.json, and pushes channel
// writes down to the DMX driver.
class DeviceManager {
 public:
  explicit DeviceManager(DmxDriver& dmx) : _dmx(dmx) {}

  void begin();  // load from storage

  std::vector<Device>& devices() { return _devices; }

  Device* find(const String& id);
  Device* findByName(const String& name);
  int nextFreeStartChannel();

  Device* addDevice(const String& name, int startChannel);
  Device* addDevice(const String& name, int startChannel, JsonArrayConst channels);
  Device* updateDevice(const String& id, JsonObjectConst data);
  bool removeDevice(const String& id);
  bool removeDeviceByName(const String& name);

  // Returns the added channel, or nullptr with `error` set when the device is
  // unknown.
  Channel* addChannel(const String& deviceName, const String& channelName, int offset,
                      const String& type, String& error);
  // Removes a uniquely-named channel. Returns the owning device name via
  // `deviceOut`; sets `error` on no-match or ambiguous-match.
  bool removeChannelByName(const String& channelName, const String& deviceName, String& deviceOut,
                           String& error);

  // Applies a value to the DMX address behind (deviceId, offset). Returns the
  // channel or nullptr if not found.
  Channel* setValue(const String& deviceId, int offset, int value);
  uint8_t getValue(const Device& d, const Channel& c) const;

  // Serialization for the REST API.
  void deviceToJson(const Device& d, JsonObject out) const;
  void devicesToJson(JsonArray out) const;

 private:
  void load();
  void save();

  DmxDriver& _dmx;
  std::vector<Device> _devices;
};

// Normalize an arbitrary type string to one of the four valid channel types.
String normalizeChannelType(const String& value);
