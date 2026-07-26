#pragma once

#include <ArduinoJson.h>

#if defined(ESP8266)
#include <Updater.h>
#else
#include <Update.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <mbedtls/sha256.h>
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
// Three ways in, one mechanism underneath:
//   - a .bin posted from the settings page, for a build made on your own machine
//   - a release the board fetches itself, which is the one-press path
//   - the same release downloaded by hand and posted, for when the board cannot
//     reach GitHub
//
// ---- why the fetch verifies a hash instead of a certificate ----
//
// The board used to be kept out of this deliberately: trusting a TLS certificate
// needs a root bundle in flash, which goes stale, and skipping the check means
// accepting firmware from anything able to sit in the middle of the connection.
// So the browser fetched the release and posted the bytes.
//
// That stopped working, and not by our doing: GitHub serves release assets with
// no Access-Control-Allow-Origin header on either route, so a page served from
// the board cannot read those bytes at all. The download reaches the disk and
// never reaches the script.
//
// The way out is that integrity does not have to come from the transport. The
// GitHub API publishes a sha256 digest for every asset and does allow
// cross-origin reads, so the browser reads the expected hash over a connection
// its own certificate store verified, and hands it to the board with the URL.
// The board then downloads over TLS without verifying the chain, hashes every
// byte on the way past, and refuses the image unless it matches. Substituting
// firmware means matching a hash that arrived over a channel the attacker was
// not on, which is a stronger position than a root certificate that expires.
class Updater {
 public:
  // The upload path, driven by the web server's multipart handler.
  bool beginUpload(const String& filename);
  bool writeChunk(const uint8_t* data, size_t len);
  bool endUpload();
  void abortUpload();

#if !defined(ESP8266)
  // The fetch path. Returns false and sets the error when the request itself is
  // refused; a download that fails later reports through statusToJson.
  bool beginFetch(const String& url, const String& expectedSha256);
  // Called every pass. Reads at most one bounded chunk, because the same loop
  // has to keep feeding DMX and answering the browser that is watching this.
  void loopFetch();
  bool fetching() const { return _fetching; }
#else
  bool beginFetch(const String&, const String&) {
    _error = "this board cannot fetch its own firmware; download it and post it instead";
    return false;
  }
  void loopFetch() {}
  bool fetching() const { return false; }
#endif

  // What the last attempt did. Also what the settings page polls while a fetch
  // is running, since that one has no browser sending the bytes.
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

#if !defined(ESP8266)
  void endFetch();
  void failFetch(const String& why);
  static bool hostIsGitHub(const String& url);
  static String normaliseDigest(const String& in);

  bool _fetching = false;
  size_t _total = 0;      // 0 when the server sent no length
  uint32_t _lastByteMs = 0;
  String _expected;       // 64 lowercase hex characters
  mbedtls_sha256_context _sha;
  // Both outlive a single loop pass, so neither can be a local.
  WiFiClientSecure* _tls = nullptr;
  HTTPClient* _http = nullptr;
  WiFiClient* _stream = nullptr;
#endif
};
