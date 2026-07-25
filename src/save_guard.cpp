#include "save_guard.h"

#include "settings_store.h"

static const char* STATE_FILE = "state.json";

void SaveGuard::begin(DmxDriver& dmx) {
  _dmx = &dmx;

  JsonDocument sys;
  settings_store::load("system.json", sys);
  _enabled = sys["save_guard"] | true;
  if (!_enabled) return;

  JsonDocument state;
  settings_store::load(STATE_FILE, state);
  for (JsonPairConst kv : state.as<JsonObjectConst>()) {
    int address = atoi(kv.key().c_str());
    if (address >= 1 && address <= DmxDriver::DMX_CHANNELS) {
      _dmx->setChannel(address, kv.value().as<int>());
    }
  }
  // Restoring is not a change worth writing back.
  _dmx->clearDirty();
  _pending = false;
}

void SaveGuard::setEnabled(bool enabled) {
  _enabled = enabled;
  JsonDocument sys;
  settings_store::load("system.json", sys);
  sys["save_guard"] = enabled;
  settings_store::save("system.json", sys);
  if (!enabled) {
    // Leaving a stale look on disk would resurrect it if the guard were turned
    // back on months later, which is not what "off" should mean.
    JsonDocument empty;
    empty.to<JsonObject>();
    settings_store::save(STATE_FILE, empty);
    _pending = false;
  }
}

void SaveGuard::loop() {
  if (!_enabled || !_dmx) return;

  if (_dmx->dirty()) {
    _dmx->clearDirty();
    _pending = true;
    _lastChangeMs = millis();
    return;  // still moving; the clock restarts
  }
  if (!_pending) return;
  if (millis() - _lastChangeMs < QUIET_SECONDS * 1000) return;

  save();
  _pending = false;
}

void SaveGuard::save() {
  JsonDocument doc;
  JsonObject out = doc.to<JsonObject>();
  char key[6];
  for (uint16_t address = 1; address <= DmxDriver::DMX_CHANNELS; address++) {
    uint8_t value = _dmx->getChannel(address);
    if (!value) continue;  // absent means zero
    snprintf(key, sizeof(key), "%u", address);
    out[key] = value;
  }
  settings_store::save(STATE_FILE, doc);
}
