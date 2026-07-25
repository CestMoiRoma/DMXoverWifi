#include "devices.h"

#include "settings_store.h"

static bool isValidType(const String& t) {
  return t == "slider" || t == "button" || t == "button-momentary" || t == "button-switch";
}

String normalizeChannelType(const String& value) {
  return isValidType(value) ? value : String("slider");
}

static String newId() {
  uint32_t r;
#if defined(ESP8266)
  r = RANDOM_REG32;
#else
  r = esp_random();
#endif
  char buf[12];
  snprintf(buf, sizeof(buf), "dev-%06x", (unsigned)(r & 0xFFFFFF));
  return String(buf);
}

static Channel channelFromJson(JsonObjectConst c) {
  Channel ch;
  ch.offset = c["offset"] | 1;
  ch.name = (const char*)(c["name"] | "Channel");
  ch.type = normalizeChannelType(String((const char*)(c["type"] | "slider")));
  return ch;
}

void DeviceManager::begin() { load(); }

void DeviceManager::load() {
  JsonDocument doc;
  settings_store::load("devices.json", doc);
  _devices.clear();
  for (JsonObjectConst d : doc.as<JsonArrayConst>()) {
    Device dev;
    dev.id = (const char*)(d["id"] | "");
    dev.name = (const char*)(d["name"] | "Device");
    dev.start_channel = d["start_channel"] | 1;
    for (JsonObjectConst c : d["channels"].as<JsonArrayConst>()) {
      dev.channels.push_back(channelFromJson(c));
    }
    _devices.push_back(dev);
  }
}

void DeviceManager::save() {
  JsonDocument doc;
  JsonArray arr = doc.to<JsonArray>();
  devicesToJson(arr);
  settings_store::save("devices.json", doc);
}

void DeviceManager::deviceToJson(const Device& d, JsonObject out) const {
  out["id"] = d.id;
  out["name"] = d.name;
  out["start_channel"] = d.start_channel;
  JsonArray chans = out["channels"].to<JsonArray>();
  for (const Channel& c : d.channels) {
    JsonObject co = chans.add<JsonObject>();
    co["offset"] = c.offset;
    co["name"] = c.name;
    co["type"] = c.type;
  }
}

void DeviceManager::devicesToJson(JsonArray out) const {
  for (const Device& d : _devices) {
    deviceToJson(d, out.add<JsonObject>());
  }
}

Device* DeviceManager::find(const String& id) {
  for (auto& d : _devices)
    if (d.id == id) return &d;
  return nullptr;
}

Device* DeviceManager::findByName(const String& name) {
  for (auto& d : _devices)
    if (d.name == name) return &d;
  return nullptr;
}

int DeviceManager::nextFreeStartChannel() {
  int maxEnd = 0;
  for (auto& device : _devices) {
    if (device.channels.empty()) continue;
    int maxOffset = 0;
    for (auto& c : device.channels)
      if (c.offset > maxOffset) maxOffset = c.offset;
    int end = device.start_channel + maxOffset - 1;
    if (end > maxEnd) maxEnd = end;
  }
  return maxEnd ? maxEnd + 1 : 1;
}

Device* DeviceManager::addDevice(const String& name, int startChannel) {
  Device d;
  d.id = newId();
  d.name = name;
  d.start_channel = startChannel;
  _devices.push_back(d);
  save();
  return &_devices.back();
}

Device* DeviceManager::addDevice(const String& name, int startChannel, JsonArrayConst channels) {
  Device d;
  d.id = newId();
  d.name = name;
  d.start_channel = startChannel;
  for (JsonObjectConst c : channels) d.channels.push_back(channelFromJson(c));
  _devices.push_back(d);
  save();
  return &_devices.back();
}

Device* DeviceManager::updateDevice(const String& id, JsonObjectConst data) {
  Device* d = find(id);
  if (!d) return nullptr;
  if (data["name"].is<const char*>()) d->name = (const char*)data["name"];
  if (!data["start_channel"].isNull()) d->start_channel = data["start_channel"].as<int>();
  if (data["channels"].is<JsonArrayConst>()) {
    d->channels.clear();
    for (JsonObjectConst c : data["channels"].as<JsonArrayConst>()) {
      d->channels.push_back(channelFromJson(c));
    }
  }
  save();
  return d;
}

bool DeviceManager::removeDevice(const String& id) {
  for (size_t i = 0; i < _devices.size(); i++) {
    if (_devices[i].id == id) {
      _devices.erase(_devices.begin() + i);
      save();
      return true;
    }
  }
  return false;
}

bool DeviceManager::removeDeviceByName(const String& name) {
  for (size_t i = 0; i < _devices.size(); i++) {
    if (_devices[i].name == name) {
      _devices.erase(_devices.begin() + i);
      save();
      return true;
    }
  }
  return false;
}

Channel* DeviceManager::addChannel(const String& deviceName, const String& channelName, int offset,
                                   const String& type, String& error) {
  Device* d = findByName(deviceName);
  if (!d) {
    error = "no device named '" + deviceName + "'";
    return nullptr;
  }
  Channel ch;
  ch.offset = offset;
  ch.name = channelName;
  ch.type = normalizeChannelType(type);
  d->channels.push_back(ch);
  save();
  return &d->channels.back();
}

bool DeviceManager::removeChannelByName(const String& channelName, const String& deviceName,
                                        String& deviceOut, String& error) {
  Device* foundDev = nullptr;
  size_t foundIdx = 0;
  int count = 0;
  String multiNames;
  for (auto& device : _devices) {
    if (deviceName.length() && device.name != deviceName) continue;
    for (size_t j = 0; j < device.channels.size(); j++) {
      if (device.channels[j].name == channelName) {
        count++;
        if (multiNames.length()) multiNames += ", ";
        multiNames += device.name;
        foundDev = &device;
        foundIdx = j;
      }
    }
  }
  if (count == 0) {
    error = "no channel named '" + channelName + "'";
    return false;
  }
  if (count > 1) {
    error = "'" + channelName + "' matches channels on multiple devices (" + multiNames +
            "); specify device=";
    return false;
  }
  deviceOut = foundDev->name;
  foundDev->channels.erase(foundDev->channels.begin() + foundIdx);
  save();
  return true;
}

Channel* DeviceManager::setValue(const String& deviceId, int offset, int value) {
  Device* d = find(deviceId);
  if (!d) return nullptr;
  for (auto& c : d->channels) {
    if (c.offset == offset) {
      _dmx.setChannel(d->addressFor(c), value);
      return &c;
    }
  }
  return nullptr;
}

uint8_t DeviceManager::getValue(const Device& d, const Channel& c) const {
  return _dmx.getChannel(d.addressFor(c));
}
