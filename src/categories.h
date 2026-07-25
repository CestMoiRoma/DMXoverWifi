#pragma once

#include <ArduinoJson.h>
#include <Arduino.h>

// Fixture categories are a fixed vocabulary, deliberately not user-editable,
// unlike labels which are free-form tags. The distinction matters: a label
// answers "where is this in my rig", a category answers "what kind of machine
// is this", and the second one is something the firmware and the UI can both
// reason about. Adding a category means a firmware change, which is the point.
//
// The display names are English to match the rest of the UI. Editing this table
// is the only place they live.
struct FixtureCategory {
  const char* id;
  const char* name;
};

static const FixtureCategory FIXTURE_CATEGORIES[] = {
    {"par", "PAR"},
    {"bar", "LED bar"},
    {"lyre", "Moving head"},
    {"scanner", "Scanner"},
    {"strobe", "Strobe"},
    {"blinder", "Blinder"},
    {"laser", "Laser"},
    {"smoke", "Smoke and haze"},
    {"dimmer", "Dimmer pack"},
    {"effect", "Effect"},
    {"other", "Other"},
};

static const size_t FIXTURE_CATEGORY_COUNT =
    sizeof(FIXTURE_CATEGORIES) / sizeof(FIXTURE_CATEGORIES[0]);

static const char* DEFAULT_CATEGORY = "other";

// Unknown ids fall back rather than being kept, so a hand-edited config or a
// downgrade cannot leave a fixture filed under a category nothing can filter.
inline String normalizeCategory(const String& value) {
  for (size_t i = 0; i < FIXTURE_CATEGORY_COUNT; i++) {
    if (value == FIXTURE_CATEGORIES[i].id) return value;
  }
  return String(DEFAULT_CATEGORY);
}

inline void categoriesToJson(JsonArray out) {
  for (size_t i = 0; i < FIXTURE_CATEGORY_COUNT; i++) {
    JsonObject o = out.add<JsonObject>();
    o["id"] = FIXTURE_CATEGORIES[i].id;
    o["name"] = FIXTURE_CATEGORIES[i].name;
  }
}
