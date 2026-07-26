# Configuration

[Wiki index](../../WIKI.md)

Three places hold settings, and they answer different questions.

| | What it is | Committed |
|---|---|---|
| `/data/*.json` on the board | What this board is actually running. Written as you change things | no, it lives on the board |
| [dev.env](../../dev.env) | The repo's factory defaults: version, hotspot, hostname, pins, MQTT topics. What a board falls back to with nothing stored | **yes** |
| `.env` | One board's settings, credentials and all, seeded into the filesystem image at build time | no, gitignored |

Where `.env` and `dev.env` name the same thing, `.env` wins: it lands as a stored
setting, and stored settings are read first.

## Files on the board

JSON under `/data` on LittleFS. This is runtime data, separate from the firmware,
so a firmware upload or an over-the-air update leaves it alone. Missing files are
recreated from defaults on first read, and a corrupt one is replaced rather than
left to fail again on the next boot. Each save is written to a sibling `.tmp` and
renamed, so an interrupted write cannot truncate the live file.

| File | Holds |
|---|---|
| `devices.json` | `[{id, name, category, start_channel, channels[], labels[], card, ez{}}]` |
| `scenes.json` | `[{id, name, description, steps[], labels[]}]` |
| `groups.json` | `[{id, name, card, kind, members[], roles{}, settings{}, labels[]}]` |
| `labels.json` | `[{id, name, color}]` |
| `wifi_networks.json` | `[{ssid, password, priority, ip_mode, static_*}]`, highest priority first |
| `mqtt.json` | `enabled`, `host`, `port`, `username`, `password`, `base_topic`, `discovery_prefix` |
| `api.json` | `http_api_enabled`, `websocket_enabled`, `mqtt_enabled`, `api_key` |
| `system.json` | `wifi_enabled`, `save_guard`, `dmx_tx_pin`, `dmx_dir_pin_enabled`, `dmx_dir_pin`, `hostname`, `ap_ssid`, `ap_password`, `ap_ip` |
| `ethernet.json` | W5500 settings. Beta |
| `mesh.json` | `role`, `ssid`, `password`. Work in progress, stored only |
| `saved_look.json` | The save-guard's table of addresses and values |

To wipe a setting back to defaults, delete its file and reboot.

## Modules

**Settings**, **API**. Three switches, each one a subsystem that can be off:

| Module | Off means |
|---|---|
| HTTP API | Every caller but the served UI is refused, key or no key |
| WebSocket | The UI falls back to plain HTTP writes on the same 30 ms schedule |
| MQTT bridge | No broker connection, no discovery, nothing published |

MQTT is off by default; the other two are on.

## The save-guard

**Settings**, **Config**. With it on, the board remembers the look and puts it
back after a reboot or a power cut.

Only the channels holding a value are stored, as a sparse table of address to
value, and anything absent from it is zero. A rig using 20 channels stores 20
entries rather than 512.

It waits for the rig to be still for ten seconds before writing, so dragging a
fader does not spend the flash's erase cycles.

## The hostname

Handed to the radio and announced over mDNS, so the board answers on
`<hostname>.local` as well as on whatever address the router gave it. It is
sanitised first, since DNS labels allow only letters, digits and hyphens:
anything else folds to a hyphen, and an empty result falls back to the default. A
change takes effect on the next reboot, when the radio comes up again.

## Backing up and restoring

**Settings**, **Config**, **Save .json**, or `GET /api/config`: the whole live
config in one file, system, mesh, saved networks, MQTT, labels, fixtures, scenes
and groups. **Load .json** posts it back and applies it section by section. A
file missing a section leaves that section alone, so a partial config is a patch
rather than a wipe. Pin changes need a reboot.

> That file carries every WiFi and MQTT password and the API key in clear text.
> It is a secret.

**Export .env** hands back the same config in the format the build reads. Reach
for the `.json` to snapshot a board before experimenting or to clone one board
onto another; reach for the `.env` when you want a config to survive being
reflashed from scratch.

## Seeding a fresh board from `.env`

The export round-trips. Drop the file next to `platformio.ini` as `.env` and
`tools/env_to_fsdata.py` turns it into `data/*.json` inside the LittleFS image
before it is packed. Flashing with `pio run -e <env> -t uploadfs` puts the whole
config on the board. [.env.example](../../.env.example) documents every key.

Two things follow from this being a build step rather than a live import:

- `.env` is the source of truth for the image. It is regenerated from scratch on
  every build, so removing a group removes it from the image, and no `.env` at
  all means the firmware falls back to the `dev.env` defaults.
- `uploadfs` writes the whole partition, so it erases anything the board saved at
  runtime. Export first if that matters.

`uploadfs` is **not** needed to update the UI any more. That lives in the
firmware.

Both `.env` and the generated `fsdata/` are gitignored, since they carry WiFi and
MQTT passwords in clear text.

## Factory defaults

[dev.env](../../dev.env) is committed and compiled into the firmware, one `-D`
per key, by `tools/dev_env.py`. It holds the version, the repository and author
links, the default hostname, the config hotspot's name, password and address, the
DNS fallback, the DMX pins, the MQTT topics and ports.

The matching `#define` in `src/config.h` stays as a fallback, so a checkout
without `dev.env` still builds and still produces a board that works.

Every value is compiled as a string except the ones the script lists as numeric,
so a password of nothing but digits stays a password.

## USB-only mode

`WIFI_ENABLED=false`, or `Set-System wifi-toggle off`, and the radio never comes
up. No web server, no mDNS, no MQTT. The [serial console](serial-console.md)
becomes the entire interface, which is the point: a rig driven from a laptop over
USB has no reason to broadcast.
