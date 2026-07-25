#pragma once

#include <Arduino.h>

// Short random identifier with a type prefix, for example "dev-1a2b3c" or
// "lbl-9f8e7d". Collisions are possible in principle over 24 bits, but the
// board holds tens of objects, not thousands.
inline String makeId(const char* prefix) {
  uint32_t r;
#if defined(ESP8266)
  r = RANDOM_REG32;
#else
  r = esp_random();
#endif
  char buf[16];
  snprintf(buf, sizeof(buf), "%s-%06x", prefix, (unsigned)(r & 0xFFFFFF));
  return String(buf);
}
