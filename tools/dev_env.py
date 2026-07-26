"""Compile the values in dev.env into the firmware as preprocessor defines.

PlatformIO runs this as a `pre:` extra script, before anything is compiled.
Every KEY=VALUE in dev.env becomes -DKEY="VALUE", which the matching #define in
src/config.h or src/version.h then leaves alone: those keep their own values as
a fallback, so a missing dev.env compiles rather than breaks.

The point is having one place to change a version or a hotspot password. Before
this, the AP name lived in main.cpp and settings_store.cpp, the version in
version.h and the release workflow, and each of them could drift from the rest
without anything noticing.

Not to be confused with tools/env_to_fsdata.py, which reads the gitignored .env
and writes settings files into the LittleFS image. That one seeds a particular
board; this one decides what any board falls back to.
"""

import os

Import("env")  # noqa: F821  (injected by PlatformIO/SCons)

# Compiled as integers rather than strings. Everything else is quoted, so a
# password of nothing but digits stays a password.
NUMERIC = {"WS_PORT_NUMBER", "DEFAULT_MQTT_PORT"}


def parse(path):
    values = {}
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            # A quoted value is a courtesy to anyone who writes one; the quotes
            # are not part of what they meant.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key] = value
    return values


def main():
    path = os.path.join(env.subst("$PROJECT_DIR"), "dev.env")  # noqa: F821
    if not os.path.isfile(path):
        print("dev_env: no dev.env, the firmware falls back to its own defaults")
        return

    values = parse(path)
    if not values:
        return

    # Anything already set in platformio.ini wins: FW_TARGET is per environment
    # and has no business being overridden by a file that knows nothing about
    # which environment is building.
    already = set()
    for define in env.get("CPPDEFINES", []):  # noqa: F821
        already.add(define[0] if isinstance(define, (list, tuple)) else define)

    defines = []
    for key in sorted(values):
        if key in already:
            continue
        value = values[key]
        if key in NUMERIC:
            defines.append((key, value))
        else:
            defines.append((key, env.StringifyMacro(value)))  # noqa: F821
    env.Append(CPPDEFINES=defines)  # noqa: F821

    print("dev_env: %d defaults from dev.env, version %s"
          % (len(defines), values.get("FW_VERSION", "unset")))


main()
