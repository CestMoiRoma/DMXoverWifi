#pragma once

#include <ArduinoJson.h>

#include "dmx/dmx_driver.h"

// Remembers the look across a reboot or a power cut.
//
// The stored table is sparse: only channels holding a non-zero value are
// written, keyed by DMX address. A channel absent from the table is zero, which
// is what a dark channel means anyway. A rig using twenty slots stores twenty
// numbers rather than five hundred and twelve, and an idle board stores none.
//
// Addresses, not channel uids. This restores the state of a universe, which is
// a physical thing: if a fixture is readdressed the light that was lit is the
// one at that address, not the one that used to be called that.
//
// Writes are held back until the rig has been still for a while. Flash has a
// finite number of erase cycles and a fader dragged across its travel would
// otherwise ask for a hundred of them.
class SaveGuard {
 public:
  void begin(DmxDriver& dmx);  // loads and applies the stored look
  void loop();                 // writes once the rig has been quiet

  bool enabled() const { return _enabled; }
  void setEnabled(bool enabled);

  // Seconds of stillness before the state is committed.
  static const uint32_t QUIET_SECONDS = 10;

 private:
  void save();

  DmxDriver* _dmx = nullptr;
  bool _enabled = true;
  bool _pending = false;
  uint32_t _lastChangeMs = 0;
};
