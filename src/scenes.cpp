#include "scenes.h"

#include "ids.h"
#include "settings_store.h"

static Scene sceneFromJson(JsonObjectConst s) {
  Scene scene;
  scene.id = (const char*)(s["id"] | "");
  scene.name = (const char*)(s["name"] | "Scene");
  scene.description = (const char*)(s["description"] | "");
  for (JsonObjectConst step : s["steps"].as<JsonArrayConst>()) {
    SceneStep item;
    item.channelUid = (const char*)(step["uid"] | "");
    item.value = step["value"] | 0;
    if (item.value < 0) item.value = 0;
    if (item.value > 255) item.value = 255;
    if (item.channelUid.length()) scene.steps.push_back(item);
  }
  for (JsonVariantConst v : s["labels"].as<JsonArrayConst>()) {
    const char* id = v.as<const char*>();
    if (id && *id) scene.labels.push_back(String(id));
  }
  if (!scene.id.length()) scene.id = makeId("scn");
  return scene;
}

void SceneStore::begin() { load(); }

void SceneStore::load() {
  JsonDocument doc;
  settings_store::load("scenes.json", doc);
  _scenes.clear();
  for (JsonObjectConst s : doc.as<JsonArrayConst>()) _scenes.push_back(sceneFromJson(s));
}

void SceneStore::save() {
  JsonDocument doc;
  scenesToJson(doc.to<JsonArray>());
  settings_store::save("scenes.json", doc);
}

Scene* SceneStore::find(const String& id) {
  for (Scene& s : _scenes)
    if (s.id == id) return &s;
  return nullptr;
}

Scene* SceneStore::addFromJson(JsonObjectConst body) {
  Scene scene = sceneFromJson(body);
  scene.id = makeId("scn");  // never trust an id from a caller on create
  _scenes.push_back(scene);
  save();
  return &_scenes.back();
}

Scene* SceneStore::update(const String& id, JsonObjectConst body) {
  Scene* s = find(id);
  if (!s) return nullptr;
  if (body["name"].is<const char*>()) s->name = (const char*)body["name"];
  if (body["description"].is<const char*>()) s->description = (const char*)body["description"];
  if (body["steps"].is<JsonArrayConst>()) {
    Scene rebuilt = sceneFromJson(body);
    s->steps = rebuilt.steps;
  }
  if (body["labels"].is<JsonArrayConst>()) {
    Scene rebuilt = sceneFromJson(body);
    s->labels = rebuilt.labels;
  }
  save();
  return s;
}

bool SceneStore::remove(const String& id) {
  for (size_t i = 0; i < _scenes.size(); i++) {
    if (_scenes[i].id == id) {
      _scenes.erase(_scenes.begin() + i);
      save();
      return true;
    }
  }
  return false;
}

void SceneStore::replaceAll(JsonArrayConst in) {
  _scenes.clear();
  for (JsonObjectConst s : in) _scenes.push_back(sceneFromJson(s));
  save();
}

bool SceneStore::play(const String& id, DeviceManager& devices, JsonArray missing) {
  Scene* s = find(id);
  if (!s) return false;
  for (const SceneStep& step : s->steps) {
    // A step whose channel is not on this board is reported rather than
    // skipped in silence: a scene that quietly does less than it says is the
    // kind of thing you find out about in front of an audience.
    if (!devices.setValueByUid(step.channelUid, step.value)) missing.add(step.channelUid);
  }
  return true;
}

void SceneStore::forgetMissing(DeviceManager& devices) {
  bool changed = false;
  for (Scene& s : _scenes) {
    for (size_t i = 0; i < s.steps.size();) {
      Device* d = nullptr;
      Channel* c = nullptr;
      if (devices.findByChannelUid(s.steps[i].channelUid, d, c)) {
        i++;
      } else {
        s.steps.erase(s.steps.begin() + i);
        changed = true;
      }
    }
  }
  if (changed) save();
}

void SceneStore::sceneToJson(const Scene& s, JsonObject out) const {
  out["id"] = s.id;
  out["name"] = s.name;
  out["description"] = s.description;
  JsonArray steps = out["steps"].to<JsonArray>();
  for (const SceneStep& step : s.steps) {
    JsonObject o = steps.add<JsonObject>();
    o["uid"] = step.channelUid;
    o["value"] = step.value;
  }
  JsonArray labels = out["labels"].to<JsonArray>();
  for (const String& id : s.labels) labels.add(id);
}

void SceneStore::scenesToJson(JsonArray out) const {
  for (const Scene& s : _scenes) sceneToJson(s, out.add<JsonObject>());
}
