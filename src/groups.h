#pragma once

#include <ArduinoJson.h>

#include <utility>
#include <vector>

#include "devices.h"

// A set of channels driven as one.
//
// A lite group is a single control writing the same value to every channel it
// holds: that is what grouping channels means, and it is what a bar of PARs
// wants when they should all dim together.
//
// An EZ group is the same idea behind a widget: it picks a kind and each role
// takes a *set* of channels rather than one, so a colour wheel drives the reds
// of six fixtures at once.
//
// Members are channel uids, like scenes, so a group survives fixtures being
// readdressed or edited underneath it.
struct GroupRole {
  String role;
  std::vector<String> channelUids;
};

struct Group {
  String id;
  String name = "Group";
  String card = "lite";  // "lite" or "ez"
  String kind;           // EZ kind when card is "ez"
  std::vector<String> members;     // lite: every channel driven together
  std::vector<GroupRole> roles;    // ez: one set of channels per role
  std::vector<std::pair<String, String>> settings;
  std::vector<String> labels;
};

class GroupStore {
 public:
  void begin();

  const std::vector<Group>& groups() const { return _groups; }
  Group* find(const String& id);

  Group* addFromJson(JsonObjectConst body);
  Group* update(const String& id, JsonObjectConst body);
  bool remove(const String& id);
  void replaceAll(JsonArrayConst in);

  // Writes one value across every channel of a lite group, or across one role
  // of an EZ group. Unknown uids are collected rather than ignored.
  bool apply(const String& id, const String& role, int value, DeviceManager& devices,
             JsonArray missing);

  void forgetMissing(DeviceManager& devices);

  void groupToJson(const Group& g, JsonObject out) const;
  void groupsToJson(JsonArray out) const;

 private:
  void load();
  void save();

  std::vector<Group> _groups;
};
