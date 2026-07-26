#pragma once

#include <ArduinoJson.h>

#if defined(ESP8266)
#include <Updater.h>
#else
#include <Update.h>
#endif

// Over-the-air updates, in the spirit of the thing they are usually compared to:
// the application partition is rewritten and the data partition is not touched,
// so a board comes back from an update with its fixtures, scenes, groups, labels
// and network settings exactly as they were.
//
// That only works because the web UI travels inside the firmware (see
// tools/pack_web.py). With the page on LittleFS there would be no way to update
// the two together without writing over the settings.
//
// Two ways in, one mechanism underneath:
//   - a .bin posted from the settings page, for a build made on your own machine
//   - a release fetched from GitHub, for everyone else
class Updater {
 public:
  // The upload path, driven by the web server's multipart handler.
  bool beginUpload(const String& filename);
  bool writeChunk(const uint8_t* data, size_t len);
  bool endUpload();
  void abortUpload();

  // What the last attempt did. Also what the settings page polls while a GitHub
  // install is running, since that one has no browser sending the bytes.
  void statusToJson(JsonObject out) const;

  bool busy() const { return _busy; }
  const String& error() const { return _error; }
  size_t written() const { return _written; }

  // Reboots once the current response has drained. Anything that rewrites the
  // running application has to leave by this door rather than restarting from
  // inside a request handler.
  static void rebootSoon();

 private:
  void fail(const String& why);

  bool _busy = false;
  bool _ok = false;
  size_t _written = 0;
  String _error;
  String _filename;
};
