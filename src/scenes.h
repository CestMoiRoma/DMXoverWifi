#pragma once

#include <ArduinoJson.h>

#include <vector>

#include "devices.h"

// A named look: a list of channels and the value each should take.
//
// Steps address channels by uid, never by fixture and offset. A rig gets
// readdressed and fixtures get edited, and a scene that remembered a position
// would afterwards light the wrong lamp without saying so. Looking the channel
// up means it either finds it or reports what it could not place.
struct SceneStep {
  String channelUid;
  int value = 0;
};

struct Scene {
  String id;
  String name = "Scene";
  String description;
  std::vector<SceneStep> steps;
  std::vector<String> labels;
};

// Owns the scene list, persisted to scenes.json.
class SceneStore {
 public:
  void begin();

  const std::vector<Scene>& scenes() const { return _scenes; }
  Scene* find(const String& id);

  Scene* addFromJson(JsonObjectConst body);
  Scene* update(const String& id, JsonObjectConst body);
  bool remove(const String& id);
  void replaceAll(JsonArrayConst in);

  // Applies a scene. `missing` collects the uids this board does not carry, so
  // a scene imported from another rig can say what it skipped rather than
  // quietly doing less than it claims.
  bool play(const String& id, DeviceManager& devices, JsonArray missing);

  // Drops any step pointing at a channel that no longer exists. Called after a
  // fixture is deleted, so scenes do not accumulate references to nothing.
  void forgetMissing(DeviceManager& devices);

  void sceneToJson(const Scene& s, JsonObject out) const;
  void scenesToJson(JsonArray out) const;

 private:
  void load();
  void save();

  std::vector<Scene> _scenes;
};
