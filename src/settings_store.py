import json
import os

DATA_DIR = "/data"

DEFAULTS = {
    "wifi_networks.json": [],
    "devices.json": [],
    "mqtt.json": {
        "enabled": False,
        "host": "",
        "port": 1883,
        "username": "",
        "password": "",
        "base_topic": "dmxwifi",
        "discovery_prefix": "homeassistant",
    },
    "system.json": {
        "dmx_tx_pin": "D4",
        "dmx_dir_pin_enabled": False,
        "dmx_dir_pin": "D3",
        "hostname": "ESP-DMX",
        "ap_ssid": "ESP-DMX",
        "ap_password": "DMX4ALL1",
        "ap_ip": "1.1.1.1",
        "sta_ip_mode": "dhcp",  # "dhcp" | "static"
        "sta_static_ip": "",
        "sta_static_netmask": "255.255.255.0",
        "sta_static_gateway": "",
        "sta_static_dns": "1.1.1.1",
    },
    "mesh.json": {
        # WIP: not acted on yet, only stored. See mesh_manager.py.
        "role": "none",  # "none" | "parent" | "child"
        "ssid": "",
        "password": "",
    },
}


def _path(name):
    return DATA_DIR + "/" + name


def _copy_default(name):
    default = DEFAULTS[name]
    return list(default) if isinstance(default, list) else dict(default)


def load(name):
    try:
        with open(_path(name), "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        data = _copy_default(name)
        save(name, data)
        return data


def save(name, data):
    try:
        os.stat(DATA_DIR)
    except OSError:
        os.mkdir(DATA_DIR)
    with open(_path(name), "w") as f:
        json.dump(data, f)
