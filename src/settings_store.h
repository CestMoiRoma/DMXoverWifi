#pragma once

#include <ArduinoJson.h>

// Config persistence: one JSON file per settings group under /data on LittleFS,
// same on-disk shapes as the CircuitPython firmware. A missing or corrupt file
// is transparently reseeded from defaults.
namespace settings_store {

// Mount LittleFS (formatting on first use) and ensure /data exists.
bool begin();

// Fill `doc` from /data/<name>. On failure, seed defaults into `doc` and persist
// them so later loads are consistent.
void load(const char* name, JsonDocument& doc);

// Persist `doc` to /data/<name> atomically (write sibling .tmp, then rename).
bool save(const char* name, const JsonDocument& doc);

}  // namespace settings_store
