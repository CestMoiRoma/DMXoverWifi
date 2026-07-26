#include "updater.h"

#include <Arduino.h>

#include "version.h"

void Updater::fail(const String& why) {
  _error = why;
  _busy = false;
  _ok = false;
  Update.abort();
}

bool Updater::beginUpload(const String& filename) {
  _filename = filename;
  _error = "";
  _written = 0;
  _ok = false;

  // A filesystem image posted here would be written over the application and
  // brick the board until somebody found a USB cable. The name is the only
  // warning available before the bytes start arriving, so it is worth reading.
  String lower = filename;
  lower.toLowerCase();
  if (lower.indexOf("littlefs") >= 0 || lower.indexOf("spiffs") >= 0) {
    _error = "that looks like a filesystem image, not firmware";
    return false;
  }

#if defined(ESP8266)
  // The ESP8266 updater blocks on flash erase unless told to spread the work
  // across calls, and a blocked loop here is a dropped upload.
  Update.runAsync(true);
  uint32_t room = (ESP.getFreeSketchSpace() - 0x1000) & 0xFFFFF000;
  if (!Update.begin(room, U_FLASH)) {
#else
  if (!Update.begin(UPDATE_SIZE_UNKNOWN, U_FLASH)) {
#endif
    _error = "could not open the update partition";
    return false;
  }
  _busy = true;
  return true;
}

bool Updater::writeChunk(const uint8_t* data, size_t len) {
  if (!_busy) return false;
  // The first byte of an ESP image is 0xE9. Anything else is a file somebody
  // picked by mistake, and it is better to say so now than to reboot into it.
  if (_written == 0 && len > 0 && data[0] != 0xE9) {
    fail("that file is not an ESP firmware image");
    return false;
  }
  if (Update.write(const_cast<uint8_t*>(data), len) != len) {
    fail(String("write failed after ") + _written + " bytes");
    return false;
  }
  _written += len;
  return true;
}

bool Updater::endUpload() {
  if (!_busy) return false;
  if (!Update.end(true)) {
    fail(String("the image was rejected: ") + Update.errorString());
    return false;
  }
  _busy = false;
  _ok = true;
  _error = "";
  return true;
}

void Updater::abortUpload() {
  if (!_busy) return;
  fail("the upload stopped early");
}

void Updater::statusToJson(JsonObject out) const {
  out["running_version"] = FW_VERSION;
  out["busy"] = _busy;
  out["ok"] = _ok;
  out["written"] = (uint32_t)_written;
  if (_filename.length()) out["filename"] = _filename;
  if (_error.length()) out["error"] = _error;
}

void Updater::rebootSoon() {
  delay(200);  // let the response drain before pulling the rug out
  ESP.restart();
}
