"""Seed the LittleFS image's /data config from a local .env file.

PlatformIO runs this as a `pre:` extra script, so it fires before any target is
built and in particular before `buildfs` packs $PROJECT_DATA_DIR into the
LittleFS image. It reads .env at the project root and writes the matching
data/*.json files that settings_store reads at boot, which is what the deleted
tools/deploy.py used to do for the CircuitPython firmware.

The generated files are regenerated from scratch on every build, so .env is the
single source of truth for what a freshly flashed board starts with. Groups
absent from .env produce no file at all, and the firmware seeds its own defaults
for those. .env itself is optional: without it this script does nothing.

Note that `uploadfs` erases the whole LittleFS partition, so it also discards
whatever the board saved at runtime through the web UI or the serial console.
Export the live config first if you want to keep it.
"""

import json
import os
import shutil

Import("env")  # noqa: F821  (injected by PlatformIO/SCons)

# Files this script owns. They are wiped before each run so that removing a
# group from .env actually removes it from the image instead of leaving the
# previous build's copy behind.
MANAGED = (
    "wifi_networks.json",
    "mqtt.json",
    "system.json",
    "mesh.json",
    "api.json",
    "labels.json",
    "devices.json",
)


def parse_env(path):
    """Parse a .env-style file into a flat {KEY: value} dict."""
    result = {}
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle.read().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def as_bool(value, default=False):
    v = str(value or "").strip().lower()
    if v in ("true", "1", "yes", "on"):
        return True
    if v in ("false", "0", "no", "off"):
        return False
    return default


def as_int(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def wifi_from_env(cfg):
    """Collect WIFI_<n>_SSID/PASSWORD/PRIORITY groups into wifi_networks entries."""
    groups = {}
    for key, value in cfg.items():
        if not key.startswith("WIFI_"):
            continue
        parts = key.split("_", 2)
        if len(parts) != 3:
            continue
        n, field = parts[1], parts[2].lower()
        groups.setdefault(n, {})[field] = value

    out = []
    for n in sorted(groups, key=as_int):
        group = groups[n]
        if not group.get("ssid"):
            continue
        mode = group.get("ip_mode", "dhcp").strip().lower()
        out.append({
            "ssid": group["ssid"],
            "password": group.get("password", ""),
            "priority": as_int(group.get("priority", 0)),
            # Addressing is per network: the same rig meets DHCP at one venue
            # and a fixed address at the next.
            "ip_mode": mode if mode == "static" else "dhcp",
            "static_ip": group.get("static_ip", ""),
            "static_netmask": group.get("static_netmask", "255.255.255.0"),
            "static_gateway": group.get("static_gateway", ""),
            "static_dns": group.get("static_dns", "1.1.1.1"),
        })
    return out or None


def mqtt_from_env(cfg):
    if not any(k.startswith("MQTT_") for k in cfg):
        return None
    return {
        "enabled": as_bool(cfg.get("MQTT_ENABLED"), False),
        "host": cfg.get("MQTT_HOST", ""),
        "port": as_int(cfg.get("MQTT_PORT", 1883), 1883),
        "username": cfg.get("MQTT_USERNAME", ""),
        "password": cfg.get("MQTT_PASSWORD", ""),
        "base_topic": cfg.get("MQTT_BASE_TOPIC", "dmxwifi"),
        "discovery_prefix": cfg.get("MQTT_DISCOVERY_PREFIX", "homeassistant"),
    }


SYSTEM_KEYS = (
    "WIFI_ENABLED",
    "DMX_TX_PIN", "DMX_DIR_PIN_ENABLED", "DMX_DIR_PIN",
    "HOSTNAME", "AP_SSID", "AP_PASSWORD", "AP_IP",
)

API_KEYS = ("API_HTTP_ENABLED", "API_WEBSOCKET_ENABLED", "API_MQTT_ENABLED")


def api_from_env(cfg):
    """Module switches for api.json. The API key itself is never seeded: the
    board mints its own on first boot, and putting one in .env would ship the
    same key to every board flashed from this checkout."""
    if not any(k in cfg for k in API_KEYS):
        return None
    return {
        "http_api_enabled": as_bool(cfg.get("API_HTTP_ENABLED"), True),
        "websocket_enabled": as_bool(cfg.get("API_WEBSOCKET_ENABLED"), True),
        "mqtt_enabled": as_bool(cfg.get("API_MQTT_ENABLED"), True),
        "api_key": "",
    }


def system_from_env(cfg, default_tx_pin):
    if not any(k in cfg for k in SYSTEM_KEYS):
        return None
    return {
        "wifi_enabled": as_bool(cfg.get("WIFI_ENABLED"), True),
        "dmx_tx_pin": cfg.get("DMX_TX_PIN", default_tx_pin),
        "dmx_dir_pin_enabled": as_bool(cfg.get("DMX_DIR_PIN_ENABLED"), False),
        "dmx_dir_pin": cfg.get("DMX_DIR_PIN", "IO18"),
        "hostname": cfg.get("HOSTNAME", "ESP-DMX"),
        "ap_ssid": cfg.get("AP_SSID", "ESP-DMX"),
        "ap_password": cfg.get("AP_PASSWORD", "DMX4ALL1"),
        "ap_ip": cfg.get("AP_IP", "1.1.1.1"),
    }


def mesh_from_env(cfg):
    if not any(k.startswith("MESH_") for k in cfg):
        return None
    return {
        "role": cfg.get("MESH_ROLE", "none"),
        "ssid": cfg.get("MESH_SSID", ""),
        "password": cfg.get("MESH_PASSWORD", ""),
    }


def labels_from_env(cfg):
    """Collect LABEL_<n>_NAME/COLOR groups into label entries.

    Ids are derived from the group number rather than random, so the same .env
    always produces the same ids and the devices below can point at them.
    """
    groups = {}
    for key, value in cfg.items():
        if not key.startswith("LABEL_"):
            continue
        parts = key.split("_", 2)
        if len(parts) != 3:
            continue
        groups.setdefault(parts[1], {})[parts[2].lower()] = value

    out = []
    for n in sorted(groups, key=as_int):
        group = groups[n]
        if not group.get("name"):
            continue
        out.append({
            "id": "lbl-env%s" % n,
            "name": group["name"],
            "color": group.get("color", "#3b82f6"),
        })
    return out or None


def devices_from_env(cfg, labels):
    """Collect DEVICE_<n>_* and DEVICE_<n>_CHANNEL_<m>_* groups into fixtures."""
    device_groups = {}
    channel_groups = {}  # (device_n, channel_m) -> {field: value}

    for key, value in cfg.items():
        if not key.startswith("DEVICE_"):
            continue
        parts = key.split("_")
        # DEVICE_1_NAME           -> [DEVICE, 1, NAME]
        # DEVICE_1_START_CHANNEL  -> [DEVICE, 1, START, CHANNEL]
        # DEVICE_1_CHANNEL_1_NAME -> [DEVICE, 1, CHANNEL, 1, NAME]
        if len(parts) < 3:
            continue
        dev_n = parts[1]
        rest = "_".join(parts[2:]).lower()
        if rest.startswith("channel_"):
            ch_parts = rest[len("channel_"):].split("_", 1)
            if len(ch_parts) != 2:
                continue
            channel_groups.setdefault((dev_n, ch_parts[0]), {})[ch_parts[1]] = value
        else:
            device_groups.setdefault(dev_n, {})[rest] = value

    if not device_groups:
        return None

    devices = []
    for dev_n in sorted(device_groups, key=as_int):
        group = device_groups[dev_n]
        if not group.get("name"):
            continue
        channel_keys = sorted(
            (k for k in channel_groups if k[0] == dev_n),
            key=lambda k: as_int(k[1]),
        )
        channels = []
        for i, channel_key in enumerate(channel_keys, start=1):
            channel = channel_groups[channel_key]
            channels.append({
                "offset": as_int(channel.get("offset", i), i),
                "name": channel.get("name", "Channel %d" % i),
                "type": channel.get("type", "slider"),
            })
        # EZ cards: DEVICE_n_CARD, DEVICE_n_EZ_KIND, DEVICE_n_EZ_MODE, plus one
        # key per role and per setting. Presets are deliberately not seeded:
        # they are made live and belong to the .json backup, and spelling a
        # colour out across four keys would bury the readable part of this file.
        ez = None
        if group.get("card") == "ez" or group.get("ez_kind"):
            roles = {}
            settings = {}
            for key, value in group.items():
                if key.startswith("ez_role_"):
                    roles[key[len("ez_role_"):]] = as_int(value)
                elif key.startswith("ez_set_"):
                    settings[key[len("ez_set_"):]] = value
            ez = {
                "kind": group.get("ez_kind", ""),
                "mode": group.get("ez_mode", ""),
                "roles": roles,
                "settings": settings,
                "presets": [],
            }

        devices.append({
            "id": "dev-env%s" % dev_n,
            "card": "ez" if ez else "lite",
            "ez": ez or {},
            "name": group["name"],
            # Unknown ids are left as written: the firmware normalises them to
            # "other" on load, and doing it here too would hide the typo.
            "category": group.get("category", "other"),
            "start_channel": as_int(group.get("start_channel", 1), 1),
            "channels": channels,
            "labels": resolve_labels(group.get("labels", ""), labels),
        })
    return devices or None


def resolve_labels(spec, labels):
    """Turn a comma-separated list of label names into the matching label ids.

    Names that match nothing are dropped rather than invented, so a typo shows
    up as a missing chip instead of a fixture nobody can filter.
    """
    by_name = {l["name"].strip().lower(): l["id"] for l in (labels or [])}
    out = []
    for name in spec.split(","):
        name = name.strip()
        if not name:
            continue
        label_id = by_name.get(name.lower())
        if label_id and label_id not in out:
            out.append(label_id)
    return out


def main():
    project_dir = env.subst("$PROJECT_DIR")  # noqa: F821
    data_dir = env.subst("$PROJECT_DATA_DIR")  # noqa: F821
    env_path = os.path.join(project_dir, ".env")
    out_dir = os.path.join(data_dir, "data")

    # Start clean so a group dropped from .env disappears from the image too.
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)

    if not os.path.isfile(env_path):
        print("env_to_fsdata: no .env at project root, leaving the image config empty")
        return

    cfg = parse_env(env_path)

    # On the ESP8266 the DMX output is fixed to Serial1/GPIO2 by the backend, so
    # the pin is a label there; label it accurately anyway.
    is_esp8266 = env.subst("$PIOPLATFORM") == "espressif8266"  # noqa: F821
    default_tx_pin = "GPIO2" if is_esp8266 else "IO4"

    labels = labels_from_env(cfg)
    generated = {
        "wifi_networks.json": wifi_from_env(cfg),
        "mqtt.json": mqtt_from_env(cfg),
        "system.json": system_from_env(cfg, default_tx_pin),
        "mesh.json": mesh_from_env(cfg),
        "api.json": api_from_env(cfg),
        "labels.json": labels,
        "devices.json": devices_from_env(cfg, labels),
    }

    written = []
    for name in MANAGED:
        payload = generated.get(name)
        if payload is None:
            continue
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        written.append(name)

    if written:
        print("env_to_fsdata: seeded %s from .env" % ", ".join(written))
    else:
        print("env_to_fsdata: .env holds no recognised keys, nothing seeded")


main()
