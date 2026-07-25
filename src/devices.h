#pragma once

#include <ArduinoJson.h>

#include <functional>
#include <vector>

#include "categories.h"
#include "dmx/dmx_driver.h"

// A single DMX control within a fixture. `type` is one of:
//   "slider" | "button" | "button-momentary" | "button-switch"
struct Channel {
  int offset = 1;
  String name = "Channel";
  String type = "slider";
};

// A named group of channels mapped onto a contiguous DMX address range starting
// at start_channel. `labels` holds LabelStore ids, and a fixture may carry
// several so it can match more than one filter chip.
struct Device {
  String id;
  String name = "Device";
  String category = "other";  // one of categories.h, chosen at creation
  int start_channel = 1;
  std::vector<Channel> channels;
  std::vector<String> labels;

  int addressFor(const Channel& c) const { return start_channel + c.offset - 1; }
};

// Owns the fixture list, keeps it persisted to devices.json, and pushes channel
// writes down to the DMX driver.
class DeviceManager {
 public:
  explicit DeviceManager(DmxDriver& dmx) : _dmx(dmx) {}

  void begin();  // load from storage

  std::vector<Device>& devices() { return _devices; }

  // Raw universe access, for callers that address DMX slots directly rather
  // than through a fixture.
  DmxDriver& dmx() { return _dmx; }

  // Fires on every successful setValue, whatever drove it: HTTP, WebSocket or
  // the serial console. The WebSocket server uses it to fan changes out, so a
  // fader moved from one client shows up on the others without any of the
  // callers having to know the socket exists.
  void onValueChanged(std::function<void(const String&, int, int)> cb) {
    _onValueChanged = std::move(cb);
  }

  Device* find(const String& id);
  Device* findByName(const String& name);
  int nextFreeStartChannel();

  Device* addDevice(const String& name, int startChannel);
  Device* addDevice(const String& name, int startChannel, JsonArrayConst channels);
  Device* addDevice(const String& name, int startChannel, JsonArrayConst channels,
                    JsonArrayConst labels);
  // Builds a fixture from a whole API body, which keeps the parameter list from
  // growing a slot every time a field is added. Any id in the body is ignored:
  // the board mints its own on create.
  Device* addDeviceFromJson(JsonObjectConst body);
  Device* updateDevice(const String& id, JsonObjectConst data);
  bool removeDevice(const String& id);
  bool removeDeviceByName(const String& name);

  // Strips a deleted label from every fixture that carried it.
  void dropLabel(const String& labelId);

  // Replaces the whole fixture list, used by the config import.
  void replaceAll(JsonArrayConst in);

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

  // Serialization. `withValues` adds each channel's live DMX value, which the
  // API wants so the UI can show real slider positions, and which persistence
  // does not: devices.json describes the rig, not the current look.
  void deviceToJson(const Device& d, JsonObject out, bool withValues = false) const;
  void devicesToJson(JsonArray out, bool withValues = false) const;

 private:
  void load();
  void save();

  DmxDriver& _dmx;
  std::vector<Device> _devices;
  std::function<void(const String&, int, int)> _onValueChanged;
};

// Normalize an arbitrary type string to one of the four valid channel types.
String normalizeChannelType(const String& value);
