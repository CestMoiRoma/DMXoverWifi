"""Config persistence: /data/*.json, defaults, and recovery from a bad file."""
import json
import os

from src import settings_store


def test_missing_file_returns_defaults_and_writes_them(data_dir):
    assert not data_dir.exists()

    cfg = settings_store.load("system.json")

    assert cfg["dmx_tx_pin"] == "D4"
    assert cfg["dmx_dir_pin_enabled"] is False
    assert cfg["ap_ssid"] == "ESP-DMX"
    assert cfg["ap_ip"] == "1.1.1.1"
    # The defaults are written back, so the board never re-derives them.
    assert json.loads((data_dir / "system.json").read_text()) == cfg


def test_save_then_load_round_trip():
    settings_store.save("devices.json", [{"id": "dev-1", "name": "PAR"}])
    assert settings_store.load("devices.json") == [{"id": "dev-1", "name": "PAR"}]


def test_corrupt_file_falls_back_to_defaults(data_dir):
    os.makedirs(str(data_dir), exist_ok=True)
    (data_dir / "mqtt.json").write_text("{ this is not json")

    cfg = settings_store.load("mqtt.json")

    assert cfg["enabled"] is False
    assert cfg["base_topic"] == "dmxwifi"
    # The bad file is replaced rather than left to fail again on next boot.
    assert json.loads((data_dir / "mqtt.json").read_text()) == cfg


def test_defaults_are_copied_not_shared():
    first = settings_store.load("wifi_networks.json")
    first.append({"ssid": "leaked"})

    assert settings_store.DEFAULTS["wifi_networks.json"] == []


def test_every_known_file_has_a_default():
    for name in settings_store.DEFAULTS:
        assert settings_store.load(name) == settings_store.DEFAULTS[name]


def test_mesh_defaults_to_inactive():
    cfg = settings_store.load("mesh.json")
    assert cfg["role"] == "none"
    assert cfg["ssid"] == ""
