"""tools/deploy.py, the part that runs without a board attached.

The .env seeding logic decides what lands in data/*.json on the target, so a
regression here silently wipes someone's saved config or silently fails to seed
a fresh flash. Neither shows up until the board is in your hands.

The serial and eject paths need real hardware and are not covered.
"""
import importlib.util
import json

import pytest

from conftest import REPO_ROOT


def load_deploy():
    spec = importlib.util.spec_from_file_location(
        "deploy_tool", REPO_ROOT / "tools" / "deploy.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deploy = load_deploy()


@pytest.fixture
def target(tmp_path):
    """A stand-in for a mounted CIRCUITPY volume."""
    root = tmp_path / "CIRCUITPY"
    root.mkdir()
    return root


def data_file(target, name):
    return json.loads((target / "data" / name).read_text())


# -- .env parsing ----------------------------------------------------------


def test_parse_env_reads_key_value_pairs(tmp_path):
    path = tmp_path / ".env"
    path.write_text("WIFI_1_SSID=StageNet\nWIFI_1_PASSWORD=secret\n")

    assert deploy.parse_env(path) == {
        "WIFI_1_SSID": "StageNet",
        "WIFI_1_PASSWORD": "secret",
    }


def test_parse_env_skips_comments_and_blank_lines(tmp_path):
    path = tmp_path / ".env"
    path.write_text("# a comment\n\n   \nAP_SSID=ESP-DMX\n# trailing\n")

    assert deploy.parse_env(path) == {"AP_SSID": "ESP-DMX"}


def test_parse_env_strips_surrounding_quotes(tmp_path):
    path = tmp_path / ".env"
    path.write_text('WIFI_1_SSID="Guest Network"\nWIFI_1_PASSWORD=\'two words\'\n')

    env = deploy.parse_env(path)
    assert env["WIFI_1_SSID"] == "Guest Network"
    assert env["WIFI_1_PASSWORD"] == "two words"


def test_parse_env_keeps_equals_signs_inside_values(tmp_path):
    path = tmp_path / ".env"
    path.write_text("MQTT_PASSWORD=a=b=c\n")

    assert deploy.parse_env(path)["MQTT_PASSWORD"] == "a=b=c"


def test_parse_env_ignores_lines_without_an_equals(tmp_path):
    path = tmp_path / ".env"
    path.write_text("this is not a setting\nAP_IP=1.1.1.1\n")

    assert deploy.parse_env(path) == {"AP_IP": "1.1.1.1"}


# -- wifi groups -----------------------------------------------------------


def test_wifi_groups_come_out_in_numeric_order():
    env = {
        "WIFI_10_SSID": "Tenth",
        "WIFI_2_SSID": "Second",
        "WIFI_1_SSID": "First",
    }

    assert [n["ssid"] for n in deploy.wifi_defaults_from_env(env)] == [
        "First",
        "Second",
        "Tenth",
    ]


def test_a_wifi_group_without_an_ssid_is_dropped():
    env = {"WIFI_1_PASSWORD": "orphan", "WIFI_2_SSID": "Real"}

    assert [n["ssid"] for n in deploy.wifi_defaults_from_env(env)] == ["Real"]


def test_wifi_password_and_priority_default_sensibly():
    assert deploy.wifi_defaults_from_env({"WIFI_1_SSID": "Open"}) == [
        {"ssid": "Open", "password": "", "priority": 0}
    ]


def test_a_non_numeric_wifi_priority_falls_back_to_zero():
    env = {"WIFI_1_SSID": "StageNet", "WIFI_1_PRIORITY": "high"}

    assert deploy.wifi_defaults_from_env(env)[0]["priority"] == 0


def test_no_wifi_keys_means_no_entries():
    assert deploy.wifi_defaults_from_env({"AP_SSID": "ESP-DMX"}) == []


# -- the other config groups -----------------------------------------------


def test_each_group_returns_none_when_its_keys_are_absent():
    assert deploy.mqtt_defaults_from_env({}) is None
    assert deploy.system_defaults_from_env({}) is None
    assert deploy.mesh_defaults_from_env({}) is None
    assert deploy.devices_defaults_from_env({}) is None


def test_mqtt_group_fills_in_the_shipping_defaults():
    cfg = deploy.mqtt_defaults_from_env({"MQTT_HOST": "broker.local"})

    assert cfg["host"] == "broker.local"
    assert cfg["enabled"] is False
    assert cfg["port"] == 1883
    assert cfg["base_topic"] == "dmxwifi"
    assert cfg["discovery_prefix"] == "homeassistant"


@pytest.mark.parametrize("truthy", ["true", "TRUE", "1", "yes", "on"])
def test_env_booleans_accept_the_usual_yes_words(truthy):
    assert deploy.mqtt_defaults_from_env({"MQTT_ENABLED": truthy})["enabled"] is True


@pytest.mark.parametrize("falsy", ["false", "0", "no", "off", ""])
def test_env_booleans_treat_everything_else_as_off(falsy):
    assert deploy.mqtt_defaults_from_env({"MQTT_ENABLED": falsy})["enabled"] is False


def test_system_group_carries_pins_hotspot_and_static_ip():
    cfg = deploy.system_defaults_from_env(
        {
            "DMX_TX_PIN": "IO7",
            "DMX_DIR_PIN_ENABLED": "true",
            "DMX_DIR_PIN": "IO9",
            "STA_IP_MODE": "static",
            "STA_STATIC_IP": "192.168.1.50",
            "STA_STATIC_GATEWAY": "192.168.1.1",
        }
    )

    assert cfg["dmx_tx_pin"] == "IO7"
    assert cfg["dmx_dir_pin_enabled"] is True
    assert cfg["sta_ip_mode"] == "static"
    assert cfg["sta_static_ip"] == "192.168.1.50"
    assert cfg["ap_ssid"] == "ESP-DMX", "unmentioned keys keep their default"


def test_system_group_keys_match_what_the_firmware_reads():
    from src import settings_store

    cfg = deploy.system_defaults_from_env({"DMX_TX_PIN": "D4"})

    assert set(cfg) == set(settings_store.DEFAULTS["system.json"]), (
        "deploy.py and settings_store disagree about system.json, so a seeded "
        "board would boot with keys the firmware does not expect"
    )


def test_mqtt_group_keys_match_what_the_firmware_reads():
    from src import settings_store

    cfg = deploy.mqtt_defaults_from_env({"MQTT_HOST": "x"})

    assert set(cfg) == set(settings_store.DEFAULTS["mqtt.json"])


def test_mesh_group_keys_match_what_the_firmware_reads():
    from src import settings_store

    cfg = deploy.mesh_defaults_from_env({"MESH_ROLE": "parent"})

    assert set(cfg) == set(settings_store.DEFAULTS["mesh.json"])


# -- fixtures --------------------------------------------------------------


def test_a_device_group_becomes_a_fixture_with_channels():
    env = {
        "DEVICE_1_NAME": "Studio Par",
        "DEVICE_1_START_CHANNEL": "5",
        "DEVICE_1_CHANNEL_1_OFFSET": "1",
        "DEVICE_1_CHANNEL_1_NAME": "Red",
        "DEVICE_1_CHANNEL_1_TYPE": "slider",
        "DEVICE_1_CHANNEL_2_OFFSET": "2",
        "DEVICE_1_CHANNEL_2_NAME": "Lamp",
        "DEVICE_1_CHANNEL_2_TYPE": "button-switch",
    }

    devices = deploy.devices_defaults_from_env(env)

    assert len(devices) == 1
    assert devices[0]["name"] == "Studio Par"
    assert devices[0]["start_channel"] == 5
    assert devices[0]["channels"] == [
        {"offset": 1, "name": "Red", "type": "slider"},
        {"offset": 2, "name": "Lamp", "type": "button-switch"},
    ]


def test_a_device_without_a_name_is_dropped():
    env = {"DEVICE_1_START_CHANNEL": "5", "DEVICE_2_NAME": "Real"}

    assert [d["name"] for d in deploy.devices_defaults_from_env(env)] == ["Real"]


def test_devices_come_out_in_numeric_order():
    env = {"DEVICE_10_NAME": "Tenth", "DEVICE_2_NAME": "Second", "DEVICE_1_NAME": "First"}

    assert [d["name"] for d in deploy.devices_defaults_from_env(env)] == [
        "First",
        "Second",
        "Tenth",
    ]


def test_a_seeded_fixture_is_shaped_the_way_the_firmware_expects():
    from src.devices import Device

    env = {
        "DEVICE_1_NAME": "Par",
        "DEVICE_1_CHANNEL_1_NAME": "Dim",
        "DEVICE_1_CHANNEL_1_TYPE": "button-momentary",
    }

    device = Device.from_dict(deploy.devices_defaults_from_env(env)[0])

    assert device.name == "Par"
    assert device.channels[0].type == "button-momentary"


# -- writing to the target -------------------------------------------------


def test_wifi_entries_are_appended_to_what_is_already_on_the_board(target):
    (target / "data").mkdir()
    (target / "data" / "wifi_networks.json").write_text(
        json.dumps([{"ssid": "AlreadyThere", "password": "x", "priority": 1}])
    )

    added = deploy.merge_wifi_defaults(target, [{"ssid": "New", "password": "y", "priority": 2}])

    assert added == 1
    assert [n["ssid"] for n in data_file(target, "wifi_networks.json")] == [
        "AlreadyThere",
        "New",
    ]


def test_merging_never_clobbers_an_ssid_the_board_already_knows(target):
    (target / "data").mkdir()
    (target / "data" / "wifi_networks.json").write_text(
        json.dumps([{"ssid": "StageNet", "password": "the-real-one", "priority": 9}])
    )

    added = deploy.merge_wifi_defaults(
        target, [{"ssid": "StageNet", "password": "stale-from-env", "priority": 0}]
    )

    assert added == 0
    assert data_file(target, "wifi_networks.json")[0]["password"] == "the-real-one"


def test_merging_into_a_board_with_no_data_directory_creates_it(target):
    added = deploy.merge_wifi_defaults(target, [{"ssid": "New", "password": "", "priority": 0}])

    assert added == 1
    assert (target / "data" / "wifi_networks.json").exists()


def test_a_corrupt_wifi_file_on_the_board_is_replaced_rather_than_crashing(target):
    (target / "data").mkdir()
    (target / "data" / "wifi_networks.json").write_text("{ not json")

    added = deploy.merge_wifi_defaults(target, [{"ssid": "New", "password": "", "priority": 0}])

    assert added == 1
    assert [n["ssid"] for n in data_file(target, "wifi_networks.json")] == ["New"]


def test_config_files_are_only_written_when_missing(target):
    assert deploy.write_config_if_absent(target, "mqtt.json", {"host": "first"}) is True
    assert deploy.write_config_if_absent(target, "mqtt.json", {"host": "second"}) is False

    assert data_file(target, "mqtt.json")["host"] == "first"


def test_force_overwrites_an_existing_config_file(target):
    deploy.write_config_if_absent(target, "mqtt.json", {"host": "first"})

    assert deploy.write_config_if_absent(target, "mqtt.json", {"host": "second"}, force=True)
    assert data_file(target, "mqtt.json")["host"] == "second"


# -- the whole seeding pass ------------------------------------------------


SAMPLE_ENV = {
    "WIFI_1_SSID": "StageNet",
    "WIFI_1_PASSWORD": "stage-secret",
    "WIFI_1_PRIORITY": "10",
    "MQTT_HOST": "broker.local",
    "DMX_TX_PIN": "IO7",
    "MESH_ROLE": "parent",
    "DEVICE_1_NAME": "Par",
}


def test_a_fresh_board_gets_every_file_seeded(target):
    deploy.apply_env_defaults(SAMPLE_ENV, target, force=False)

    assert data_file(target, "wifi_networks.json")[0]["ssid"] == "StageNet"
    assert data_file(target, "mqtt.json")["host"] == "broker.local"
    assert data_file(target, "system.json")["dmx_tx_pin"] == "IO7"
    assert data_file(target, "mesh.json")["role"] == "parent"
    assert data_file(target, "devices.json")[0]["name"] == "Par"


def test_redeploying_leaves_settings_made_through_the_ui_alone(target):
    deploy.apply_env_defaults(SAMPLE_ENV, target, force=False)
    # The user then changes the pin from the web UI.
    (target / "data" / "system.json").write_text(json.dumps({"dmx_tx_pin": "D9"}))

    deploy.apply_env_defaults(SAMPLE_ENV, target, force=False)

    assert data_file(target, "system.json")["dmx_tx_pin"] == "D9"


def test_force_resets_everything_back_to_the_env_file(target):
    deploy.apply_env_defaults(SAMPLE_ENV, target, force=False)
    (target / "data" / "system.json").write_text(json.dumps({"dmx_tx_pin": "D9"}))
    (target / "data" / "wifi_networks.json").write_text(
        json.dumps([{"ssid": "Leftover", "password": "", "priority": 0}])
    )

    deploy.apply_env_defaults(SAMPLE_ENV, target, force=True)

    assert data_file(target, "system.json")["dmx_tx_pin"] == "IO7"
    assert [n["ssid"] for n in data_file(target, "wifi_networks.json")] == ["StageNet"]


def test_force_resets_system_keys_the_env_file_never_mentions(target):
    """The sharp edge of --force, pinned so it cannot change silently.

    system_defaults_from_env fills in every key as soon as one SYSTEM_ key is
    present. An .env that sets only the DMX pin therefore also resets the static
    IP block to its defaults, so a board configured for a fixed address goes
    back to DHCP on the next --force deploy.
    """
    (target / "data").mkdir()
    (target / "data" / "system.json").write_text(
        json.dumps(
            {
                "dmx_tx_pin": "D4",
                "sta_ip_mode": "static",
                "sta_static_ip": "192.168.1.50",
                "sta_static_gateway": "192.168.1.1",
            }
        )
    )

    deploy.apply_env_defaults({"DMX_TX_PIN": "IO7"}, target, force=True)

    system = data_file(target, "system.json")
    assert system["dmx_tx_pin"] == "IO7"
    assert system["sta_ip_mode"] == "dhcp"
    assert system["sta_static_ip"] == ""


def test_without_force_a_partial_env_cannot_reset_anything(target):
    (target / "data").mkdir()
    (target / "data" / "system.json").write_text(
        json.dumps({"sta_ip_mode": "static", "sta_static_ip": "192.168.1.50"})
    )

    deploy.apply_env_defaults({"DMX_TX_PIN": "IO7"}, target, force=False)

    assert data_file(target, "system.json")["sta_ip_mode"] == "static"


def test_groups_absent_from_the_env_file_are_not_written_at_all(target):
    deploy.apply_env_defaults({"WIFI_1_SSID": "OnlyWifi"}, target, force=False)

    assert (target / "data" / "wifi_networks.json").exists()
    assert not (target / "data" / "mqtt.json").exists()
    assert not (target / "data" / "system.json").exists()


def test_the_seeded_files_are_readable_by_the_firmware(target, monkeypatch):
    """What deploy.py writes must be what settings_store reads back."""
    from src import settings_store
    from src.devices import DeviceManager
    from src.dmx_driver import DmxDriver

    import board

    deploy.apply_env_defaults(SAMPLE_ENV, target, force=False)
    monkeypatch.setattr(settings_store, "DATA_DIR", str(target / "data"))

    assert settings_store.load("system.json")["dmx_tx_pin"] == "IO7"
    assert settings_store.load("mqtt.json")["host"] == "broker.local"

    manager = DeviceManager(DmxDriver(board.D4))
    assert [d.name for d in manager.devices] == ["Par"]


# -- what gets copied to the board -----------------------------------------


def test_desktop_bytecode_is_kept_off_the_board(tmp_path):
    """Running the test suite leaves __pycache__ in src/, and the board has a
    few hundred KB free. Those .pyc files are the wrong Python version anyway."""
    source = tmp_path / "src"
    (source / "__pycache__").mkdir(parents=True)
    (source / "__pycache__" / "devices.cpython-312.pyc").write_bytes(b"\x00" * 64)
    (source / "devices.py").write_text("# real firmware\n")
    (source / "stray.pyc").write_bytes(b"\x00")

    import shutil

    destination = tmp_path / "CIRCUITPY" / "src"
    shutil.copytree(source, destination, ignore=deploy.SKIP_ON_BOARD)

    copied = {p.name for p in destination.rglob("*")}
    assert "devices.py" in copied
    assert "__pycache__" not in copied
    assert not any(name.endswith(".pyc") for name in copied)


def test_editor_and_os_droppings_are_kept_off_the_board(tmp_path):
    source = tmp_path / "www"
    source.mkdir()
    (source / "index.html").write_text("<html></html>")
    (source / ".DS_Store").write_bytes(b"\x00")
    (source / "Thumbs.db").write_bytes(b"\x00")

    import shutil

    destination = tmp_path / "CIRCUITPY" / "www"
    shutil.copytree(source, destination, ignore=deploy.SKIP_ON_BOARD)

    assert {p.name for p in destination.iterdir()} == {"index.html"}


# -- the shipped .env.example ----------------------------------------------


def test_the_shipped_env_example_parses():
    env = deploy.parse_env(REPO_ROOT / ".env.example")

    assert env, ".env.example produced nothing, so the template is broken"
    assert "WIFI_1_SSID" in env


def test_every_key_documented_in_env_example_is_one_deploy_actually_reads():
    """A key in the template that nothing consumes is a lie to the user."""
    env = deploy.parse_env(REPO_ROOT / ".env.example")

    consumed = set(deploy.SYSTEM_KEYS)
    for key in env:
        if key.startswith(("WIFI_", "MQTT_", "MESH_", "DEVICE_")):
            continue
        assert key in consumed, "%s is in .env.example but deploy.py ignores it" % key


def test_the_env_example_seeds_a_board_the_firmware_can_read(target, monkeypatch):
    from src import settings_store

    env = deploy.parse_env(REPO_ROOT / ".env.example")
    deploy.apply_env_defaults(env, target, force=False)
    monkeypatch.setattr(settings_store, "DATA_DIR", str(target / "data"))

    system = settings_store.load("system.json")
    assert set(system) == set(settings_store.DEFAULTS["system.json"])
    assert settings_store.load("wifi_networks.json")[0]["ssid"]
    assert settings_store.load("mqtt.json")["base_topic"]


def test_the_env_example_covers_every_group_the_deploy_script_understands():
    text = (REPO_ROOT / ".env.example").read_text()

    for key in (
        "WIFI_1_SSID",
        "MQTT_HOST",
        "DMX_TX_PIN",
        "AP_SSID",
        "STA_IP_MODE",
        "MESH_ROLE",
        "DEVICE_1_NAME",
    ):
        assert key in text, "%s is undocumented in .env.example" % key


# -- ejecting the volume ---------------------------------------------------


@pytest.fixture
def recorded_commands(monkeypatch):
    """Capture what eject_host shells out to, instead of running it."""
    calls = []

    def fake_run(command, **kwargs):
        calls.append(list(command))

        class Result:
            stdout = ""

        return Result()

    monkeypatch.setattr(deploy.subprocess, "run", fake_run)
    return calls


def test_windows_ejects_through_the_shell_verb(monkeypatch, recorded_commands):
    monkeypatch.setattr(deploy.sys, "platform", "win32")

    deploy.eject_host("E:\\")

    assert recorded_commands[0][0] == "powershell"
    assert "InvokeVerb('Eject')" in recorded_commands[0][-1]
    assert "ParseName('E:')" in recorded_commands[0][-1], "the trailing slash must go"


def test_macos_ejects_with_diskutil(monkeypatch, recorded_commands):
    monkeypatch.setattr(deploy.sys, "platform", "darwin")

    deploy.eject_host("/Volumes/CIRCUITPY")

    assert recorded_commands[0] == ["diskutil", "eject", "/Volumes/CIRCUITPY"]


def test_linux_resolves_the_block_device_before_unmounting(monkeypatch):
    """udisksctl unmounts by device, never by mount point."""
    calls = []

    def fake_run(command, **kwargs):
        calls.append(list(command))

        class Result:
            stdout = "/dev/sdb1\n" if command[0] == "findmnt" else ""

        return Result()

    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.subprocess, "run", fake_run)

    deploy.eject_host("/media/steepy/CIRCUITPY")

    assert calls[0][0] == "findmnt"
    assert calls[1] == ["udisksctl", "unmount", "-b", "/dev/sdb1"]


def test_linux_falls_back_to_umount_when_the_device_cannot_be_resolved(
    monkeypatch, recorded_commands
):
    monkeypatch.setattr(deploy.sys, "platform", "linux")

    deploy.eject_host("/media/steepy/CIRCUITPY")

    assert recorded_commands[-1] == ["umount", "/media/steepy/CIRCUITPY"]


# -- waiting for the drive -------------------------------------------------


def test_waiting_returns_as_soon_as_the_drive_is_writable(target):
    assert deploy.wait_for_writable(target, timeout=2) is True


def test_waiting_gives_up_on_a_drive_that_never_appears(tmp_path):
    assert deploy.wait_for_writable(tmp_path / "never", timeout=1) is False


# -- writability probe -----------------------------------------------------


def test_is_writable_says_yes_on_a_normal_directory_and_cleans_up(target):
    assert deploy.is_writable(target) is True
    assert list(target.iterdir()) == [], "the probe file must not be left behind"


def test_is_writable_says_no_when_the_path_does_not_exist(tmp_path):
    assert deploy.is_writable(tmp_path / "not-mounted") is False
