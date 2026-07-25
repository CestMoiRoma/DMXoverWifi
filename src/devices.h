#pragma once

#include <ArduinoJson.h>

#include <functional>
#include <utility>
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

// Binds channels to the roles an EZ card understands, for example which offset
// is red and which is the master dimmer. The firmware stores and echoes this
// without interpreting it: the UI decides what a colour wheel does with the
// roles, while the board keeps dealing in plain channels so MQTT, the serial
// console and the raw API carry on working unchanged.
// A named capture of what a card was showing: a colour on a light card, a
// position on a motion card, the same thing underneath. Values are keyed by
// role, so a preset survives the fixture being readdressed.
struct EzPreset {
  String name;
  std::vector<std::pair<String, int>> values;  // role name -> 0..255
};

struct EzConfig {
  String kind;  // "" for none, else dimmer, strobe, mono, rgb, rgbw, cwww, smoke, motion
  String mode;  // smoke: "onoff" or "slider"
  std::vector<std::pair<String, int>> roles;  // role name -> channel offset
  // Per-card knobs the UI defines and interprets: joystick inversion, maximum
  // step, the smoke auto-off, the fine-tune mode. Deliberately untyped here so
  // a new widget setting does not need a firmware change to be stored.
  std::vector<std::pair<String, String>> settings;
  std::vector<EzPreset> presets;

  bool empty() const { return kind.length() == 0; }
};

// Bounded because the whole config goes out on every read of /api/devices, and
// an unbounded list on a dozen fixtures would make that response the slowest
// thing the board does.
static const size_t MAX_EZ_PRESETS = 12;

// A named group of channels mapped onto a contiguous DMX address range starting
// at start_channel. `labels` holds LabelStore ids, and a fixture may carry
// several so it can match more than one filter chip.
struct Device {
  String id;
  String name = "Device";
  String category = "other";  // one of categories.h, chosen at creation
  String card = "lite";       // "lite" is one control per channel, "ez" a widget
  int start_channel = 1;
  std::vector<Channel> channels;
  std::vector<String> labels;
  EzConfig ez;

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

  // Drives a channel for a fixed time, then puts it back to zero. The timer
  // lives here rather than in the browser on purpose: a smoke machine opened by
  // a tab that then closes, or by a client that loses WiFi mid-burst, keeps
  // pumping until somebody walks over to it. Duration is capped for the same
  // reason. Returns false when the channel does not exist.
  static const uint32_t MAX_BURST_MS = 30000;
  bool startBurst(const String& deviceId, int offset, int value, uint32_t ms);
  void tickBursts();  // called from the main loop

  // Serialization. `withValues` adds each channel's live DMX value, which the
  // API wants so the UI can show real slider positions, and which persistence
  // does not: devices.json describes the rig, not the current look.
  void deviceToJson(const Device& d, JsonObject out, bool withValues = false) const;
  void devicesToJson(JsonArray out, bool withValues = false) const;

 private:
  void load();
  void save();

  struct Burst {
    String deviceId;
    int offset;
    uint32_t dueMs;
  };

  DmxDriver& _dmx;
  std::vector<Device> _devices;
  std::vector<Burst> _bursts;
  std::function<void(const String&, int, int)> _onValueChanged;
};

// Normalize an arbitrary type string to one of the four valid channel types.
String normalizeChannelType(const String& value);
