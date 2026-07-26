#pragma once

// The version comes from dev.env, compiled in by tools/dev_env.py. This is only
// what a build with no dev.env falls back to, so bump it there rather than here:
// the release workflow reads dev.env, and a board reporting one version while a
// tag claims another would offer an update that never stops being available.
//
// 0.1.0 was the CircuitPython line; 0.2.0 marks the full C++ rewrite.
#ifndef FW_VERSION
#define FW_VERSION "0.2.0"
#endif
