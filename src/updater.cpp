#include "updater.h"

#include <Arduino.h>

#include "config.h"
#include "version.h"

void Updater::fail(const String& why) {
  _error = why;
  _busy = false;
  _ok = false;
  // Two spellings of the same idea. The ESP8266 updater has no abort(), so the
  // partial write is closed and the error flag cleared by hand.
#if defined(ESP8266)
  Update.end();
  Update.clearError();
#else
  Update.abort();
#endif
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
#if defined(ESP8266)
    fail(String("the image was rejected: ") + Update.getErrorString());
#else
    fail(String("the image was rejected: ") + Update.errorString());
#endif
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

// ---- the fetch path ----

#if !defined(ESP8266)

// How long the loop may spend on this in one pass, and how long a stalled
// download is given before it is called dead. The chunk is small on purpose: the
// same loop clocks out a DMX frame every 25 ms and answers the browser watching
// the progress bar.
static const size_t FETCH_CHUNK = 2048;
static const uint32_t FETCH_STALL_MS = 20000;

// The digest gate makes an untrusted transport safe, but it does not make the
// board a general-purpose downloader. Without this, anyone holding the API key
// could point it at any host on the internet and have it connect. Releases come
// from GitHub, so that is all this accepts.
bool Updater::hostIsGitHub(const String& url) {
  if (!url.startsWith("https://")) return false;
  int start = 8;
  int slash = url.indexOf('/', start);
  String host = slash < 0 ? url.substring(start) : url.substring(start, slash);
  host.toLowerCase();
  int at = host.indexOf('@');  // no userinfo smuggling a different host past this
  if (at >= 0) return false;
  return host == "github.com" || host == "api.github.com" ||
         host.endsWith(".githubusercontent.com");
}

// Accepts what the API actually returns, "sha256:<hex>", as well as bare hex.
String Updater::normaliseDigest(const String& in) {
  String hex = in;
  hex.trim();
  hex.toLowerCase();
  if (hex.startsWith("sha256:")) hex = hex.substring(7);
  if (hex.length() != 64) return "";
  for (size_t i = 0; i < 64; i++) {
    char c = hex[i];
    bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
    if (!ok) return "";
  }
  return hex;
}

bool Updater::beginFetch(const String& url, const String& expectedSha256) {
  if (_busy || _fetching) {
    _error = "an update is already running";
    return false;
  }

  String hex = normaliseDigest(expectedSha256);
  if (!hex.length()) {
    // Refused rather than downloaded unverified. An unverified image is the one
    // thing this path must never install, since nothing else is checking.
    _error = "a sha256 digest is required, and that one is not 64 hex characters";
    return false;
  }
  if (!hostIsGitHub(url)) {
    _error = "only https URLs on github.com or githubusercontent.com are accepted";
    return false;
  }

  _error = "";
  _written = 0;
  _total = 0;
  _ok = false;
  _expected = hex;
  _filename = url.substring(url.lastIndexOf('/') + 1);

  _tls = new WiFiClientSecure();
  // Deliberate, and the whole design rests on it: the chain is not checked
  // because the hash is. See the note in updater.h before changing this.
  _tls->setInsecure();
  // Handshake buffers come out of the heap, and the smaller pair is enough for
  // a download that only ever GETs.
  _tls->setTimeout(15);

  _http = new HTTPClient();
  // GitHub answers the download URL with a 302 to a signed blob host, so a
  // client that does not follow redirects gets nothing but the redirect.
  _http->setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  _http->setTimeout(15000);
  _http->setReuse(false);
  if (!_http->begin(*_tls, url)) {
    failFetch("could not parse that URL");
    return false;
  }
  int code = _http->GET();
  if (code != HTTP_CODE_OK) {
    failFetch(String("GitHub answered ") + code);
    return false;
  }

  int len = _http->getSize();
  _total = len > 0 ? (size_t)len : 0;
  _stream = _http->getStreamPtr();
  if (!_stream) {
    failFetch("no response body");
    return false;
  }

  if (!Update.begin(_total ? _total : UPDATE_SIZE_UNKNOWN, U_FLASH)) {
    failFetch(String("the image does not fit this partition: ") + Update.errorString());
    return false;
  }

  mbedtls_sha256_init(&_sha);
  mbedtls_sha256_starts_ret(&_sha, 0);  // 0 selects sha256 over sha224

  _fetching = true;
  _busy = true;
  _lastByteMs = millis();
  return true;
}

void Updater::loopFetch() {
  if (!_fetching) return;

  size_t available = _stream->available();
  if (available) {
    uint8_t buf[FETCH_CHUNK];
    size_t want = available > FETCH_CHUNK ? FETCH_CHUNK : available;
    int got = _stream->read(buf, want);
    if (got > 0) {
      if (_written == 0 && buf[0] != 0xE9) {
        failFetch("that download is not an ESP firmware image");
        return;
      }
      if (Update.write(buf, (size_t)got) != (size_t)got) {
        failFetch(String("write failed after ") + _written + " bytes");
        return;
      }
      mbedtls_sha256_update_ret(&_sha, buf, (size_t)got);
      _written += (size_t)got;
      _lastByteMs = millis();
    }
  }

  bool complete = _total && _written >= _total;
  if (complete) {
    endFetch();
    return;
  }

  // A connection that closed early is not a finished download. Without the
  // length check a truncated image would reach the hash comparison and be
  // rejected there anyway, but the message is worth getting right.
  if (!_stream->connected() && !_stream->available()) {
    if (_total && _written < _total) {
      failFetch(String("the connection closed after ") + _written + " of " + _total + " bytes");
    } else {
      endFetch();
    }
    return;
  }

  if (millis() - _lastByteMs > FETCH_STALL_MS) {
    failFetch(String("nothing arrived for 20 s, stopped after ") + _written + " bytes");
  }
}

void Updater::endFetch() {
  uint8_t digest[32];
  mbedtls_sha256_finish_ret(&_sha, digest);
  mbedtls_sha256_free(&_sha);

  static const char* HEX_DIGITS = "0123456789abcdef";
  String actual;
  actual.reserve(64);
  for (int i = 0; i < 32; i++) {
    actual += HEX_DIGITS[(digest[i] >> 4) & 0xF];
    actual += HEX_DIGITS[digest[i] & 0xF];
  }

  if (actual != _expected) {
    // The one failure worth being loud about. Everything else here is a network
    // that misbehaved; this is bytes that are not the bytes GitHub published.
    _fetching = false;
    Update.abort();
    delete _http;
    _http = nullptr;
    delete _tls;
    _tls = nullptr;
    _stream = nullptr;
    _busy = false;
    _ok = false;
    _error = "the download does not match the published sha256, so it was thrown away";
    return;
  }

  _fetching = false;
  bool sealed = Update.end(true);
  delete _http;
  _http = nullptr;
  delete _tls;
  _tls = nullptr;
  _stream = nullptr;

  if (!sealed) {
    _busy = false;
    _ok = false;
    _error = String("the image was rejected: ") + Update.errorString();
    return;
  }
  _busy = false;
  _ok = true;
  _error = "";
}

void Updater::failFetch(const String& why) {
  if (_fetching) {
    mbedtls_sha256_free(&_sha);
    Update.abort();
  }
  _fetching = false;
  if (_http) {
    _http->end();
    delete _http;
    _http = nullptr;
  }
  delete _tls;
  _tls = nullptr;
  _stream = nullptr;
  _busy = false;
  _ok = false;
  _error = why;
}

#endif  // !ESP8266

void Updater::statusToJson(JsonObject out) const {
  out["running_version"] = FW_VERSION;
  // The asset name a release has to carry for this board to accept it.
  out["target"] = FW_TARGET;
  out["asset"] = String("firmware-") + FW_TARGET + ".bin";
  out["busy"] = _busy;
  out["ok"] = _ok;
  out["written"] = (uint32_t)_written;
#if !defined(ESP8266)
  // Lets the UI draw a real progress bar instead of a spinner, and tells it
  // whether this board can fetch for itself at all.
  out["can_fetch"] = true;
  out["fetching"] = _fetching;
  if (_total) out["total"] = (uint32_t)_total;
#else
  out["can_fetch"] = false;
  out["fetching"] = false;
#endif
  if (_filename.length()) out["filename"] = _filename;
  if (_error.length()) out["error"] = _error;
}

void Updater::rebootSoon() {
  delay(200);  // let the response drain before pulling the rug out
  ESP.restart();
}
