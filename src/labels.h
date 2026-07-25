#pragma once

#include <ArduinoJson.h>

#include <vector>

// A colour-coded tag. Devices carry a list of label ids and the web UI turns
// those into cumulative filter chips, so a fixture can be both "Face" and
// "PAR" and show up under either filter.
struct Label {
  String id;
  String name = "Label";
  String color = "#3b82f6";
};

// Owns the label list, persisted to labels.json. Deleting a label here leaves
// the devices untouched: DeviceManager::dropLabel does that half, since the
// store deliberately knows nothing about fixtures.
class LabelStore {
 public:
  void begin();  // load from storage

  const std::vector<Label>& labels() const { return _labels; }
  bool exists(const String& id) const;

  Label* add(const String& name, const String& color);
  Label* find(const String& id);
  Label* update(const String& id, JsonObjectConst data);
  bool remove(const String& id);

  // Replaces the whole list, used by the config import.
  void replaceAll(JsonArrayConst in);

  void labelToJson(const Label& l, JsonObject out) const;
  void labelsToJson(JsonArray out) const;

 private:
  void load();
  void save();

  std::vector<Label> _labels;
};
