#include "groups.h"

#include "ids.h"
#include "settings_store.h"

static void uidsFromJson(JsonArrayConst in, std::vector<String>& out) {
  out.clear();
  for (JsonVariantConst v : in) {
    const char* uid = v.as<const char*>();
    if (uid && *uid) out.push_back(String(uid));
  }
}

static Group groupFromJson(JsonObjectConst g) {
  Group group;
  group.id = (const char*)(g["id"] | "");
  group.name = (const char*)(g["name"] | "Group");
  group.card = (const char*)(g["card"] | "lite");
  if (group.card != "ez") group.card = "lite";
  group.kind = (const char*)(g["kind"] | "");
  uidsFromJson(g["members"].as<JsonArrayConst>(), group.members);

  for (JsonPairConst kv : g["roles"].as<JsonObjectConst>()) {
    GroupRole role;
    role.role = String(kv.key().c_str());
    uidsFromJson(kv.value().as<JsonArrayConst>(), role.channelUids);
    if (!role.channelUids.empty()) group.roles.push_back(role);
  }
  for (JsonPairConst kv : g["settings"].as<JsonObjectConst>()) {
    const char* value = kv.value().as<const char*>();
    group.settings.push_back(std::make_pair(String(kv.key().c_str()), String(value ? value : "")));
  }
  for (JsonVariantConst v : g["labels"].as<JsonArrayConst>()) {
    const char* id = v.as<const char*>();
    if (id && *id) group.labels.push_back(String(id));
  }
  if (!group.id.length()) group.id = makeId("grp");
  return group;
}

void GroupStore::begin() { load(); }

void GroupStore::load() {
  JsonDocument doc;
  settings_store::load("groups.json", doc);
  _groups.clear();
  for (JsonObjectConst g : doc.as<JsonArrayConst>()) _groups.push_back(groupFromJson(g));
}

void GroupStore::save() {
  JsonDocument doc;
  groupsToJson(doc.to<JsonArray>());
  settings_store::save("groups.json", doc);
}

Group* GroupStore::find(const String& id) {
  for (Group& g : _groups)
    if (g.id == id) return &g;
  return nullptr;
}

Group* GroupStore::addFromJson(JsonObjectConst body) {
  Group group = groupFromJson(body);
  group.id = makeId("grp");
  _groups.push_back(group);
  save();
  return &_groups.back();
}

Group* GroupStore::update(const String& id, JsonObjectConst body) {
  Group* existing = find(id);
  if (!existing) return nullptr;
  Group rebuilt = groupFromJson(body);
  rebuilt.id = existing->id;
  *existing = rebuilt;
  save();
  return existing;
}

bool GroupStore::remove(const String& id) {
  for (size_t i = 0; i < _groups.size(); i++) {
    if (_groups[i].id == id) {
      _groups.erase(_groups.begin() + i);
      save();
      return true;
    }
  }
  return false;
}

void GroupStore::replaceAll(JsonArrayConst in) {
  _groups.clear();
  for (JsonObjectConst g : in) _groups.push_back(groupFromJson(g));
  save();
}

bool GroupStore::apply(const String& id, const String& role, int value, DeviceManager& devices,
                       JsonArray missing) {
  Group* g = find(id);
  if (!g) return false;
  if (value < 0) value = 0;
  if (value > 255) value = 255;

  if (g->card != "ez") {
    for (const String& uid : g->members) {
      if (!devices.setValueByUid(uid, value)) missing.add(uid);
    }
    return true;
  }
  for (const GroupRole& r : g->roles) {
    if (r.role != role) continue;
    for (const String& uid : r.channelUids) {
      if (!devices.setValueByUid(uid, value)) missing.add(uid);
    }
    return true;
  }
  return true;  // a role nothing is bound to writes nothing, which is correct
}

void GroupStore::forgetMissing(DeviceManager& devices) {
  bool changed = false;
  auto prune = [&](std::vector<String>& uids) {
    for (size_t i = 0; i < uids.size();) {
      Device* d = nullptr;
      Channel* c = nullptr;
      if (devices.findByChannelUid(uids[i], d, c)) {
        i++;
      } else {
        uids.erase(uids.begin() + i);
        changed = true;
      }
    }
  };
  for (Group& g : _groups) {
    prune(g.members);
    for (GroupRole& r : g.roles) prune(r.channelUids);
  }
  if (changed) save();
}

void GroupStore::groupToJson(const Group& g, JsonObject out) const {
  out["id"] = g.id;
  out["name"] = g.name;
  out["card"] = g.card;
  out["kind"] = g.kind;
  JsonArray members = out["members"].to<JsonArray>();
  for (const String& uid : g.members) members.add(uid);
  JsonObject roles = out["roles"].to<JsonObject>();
  for (const GroupRole& r : g.roles) {
    JsonArray list = roles[r.role].to<JsonArray>();
    for (const String& uid : r.channelUids) list.add(uid);
  }
  JsonObject settings = out["settings"].to<JsonObject>();
  for (const auto& s : g.settings) settings[s.first] = s.second;
  JsonArray labels = out["labels"].to<JsonArray>();
  for (const String& id : g.labels) labels.add(id);
}

void GroupStore::groupsToJson(JsonArray out) const {
  for (const Group& g : _groups) groupToJson(g, out.add<JsonObject>());
}
