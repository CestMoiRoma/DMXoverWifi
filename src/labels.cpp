#include "labels.h"

#include "ids.h"
#include "settings_store.h"

static const char* DEFAULT_COLOR = "#3b82f6";

void LabelStore::begin() { load(); }

void LabelStore::load() {
  JsonDocument doc;
  settings_store::load("labels.json", doc);
  _labels.clear();
  for (JsonObjectConst l : doc.as<JsonArrayConst>()) {
    Label label;
    label.id = (const char*)(l["id"] | "");
    label.name = (const char*)(l["name"] | "Label");
    label.color = (const char*)(l["color"] | DEFAULT_COLOR);
    if (!label.id.length()) label.id = makeId("lbl");
    _labels.push_back(label);
  }
}

void LabelStore::save() {
  JsonDocument doc;
  labelsToJson(doc.to<JsonArray>());
  settings_store::save("labels.json", doc);
}

bool LabelStore::exists(const String& id) const {
  for (const Label& l : _labels) {
    if (l.id == id) return true;
  }
  return false;
}

Label* LabelStore::find(const String& id) {
  for (Label& l : _labels) {
    if (l.id == id) return &l;
  }
  return nullptr;
}

Label* LabelStore::add(const String& name, const String& color) {
  Label label;
  label.id = makeId("lbl");
  if (name.length()) label.name = name;
  if (color.length()) label.color = color;
  _labels.push_back(label);
  save();
  return &_labels.back();
}

Label* LabelStore::update(const String& id, JsonObjectConst data) {
  Label* l = find(id);
  if (!l) return nullptr;
  if (data["name"].is<const char*>()) l->name = (const char*)data["name"];
  if (data["color"].is<const char*>()) l->color = (const char*)data["color"];
  save();
  return l;
}

bool LabelStore::remove(const String& id) {
  for (size_t i = 0; i < _labels.size(); i++) {
    if (_labels[i].id == id) {
      _labels.erase(_labels.begin() + i);
      save();
      return true;
    }
  }
  return false;
}

void LabelStore::replaceAll(JsonArrayConst in) {
  _labels.clear();
  for (JsonObjectConst l : in) {
    Label label;
    label.id = (const char*)(l["id"] | "");
    label.name = (const char*)(l["name"] | "Label");
    label.color = (const char*)(l["color"] | DEFAULT_COLOR);
    if (!label.id.length()) label.id = makeId("lbl");
    _labels.push_back(label);
  }
  save();
}

void LabelStore::labelToJson(const Label& l, JsonObject out) const {
  out["id"] = l.id;
  out["name"] = l.name;
  out["color"] = l.color;
}

void LabelStore::labelsToJson(JsonArray out) const {
  for (const Label& l : _labels) {
    labelToJson(l, out.add<JsonObject>());
  }
}
