"""The USB serial command set, end to end through the console's own parser."""
import microcontroller
import pytest
import storage
import usb_cdc

from src import settings_store


def only(lines):
    assert len(lines) == 1, "expected one reply line, got %r" % (lines,)
    return lines[0]


# -- parsing ---------------------------------------------------------------


def test_commands_are_case_insensitive(send):
    assert only(send("REBOOT-config-nope")).startswith("ERR unknown command")
    assert send("HELP") == send("help")


def test_an_unknown_command_is_reported_not_ignored(send):
    assert only(send("Fly-Me-To-The-Moon")) == (
        "ERR unknown command: Fly-Me-To-The-Moon (try Help)"
    )


def test_quoted_values_keep_their_spaces(send, wifi_manager):
    send('Add-Wifi ssid="Guest Network 5G" passwd="two words"')

    assert wifi_manager.networks[0]["ssid"] == "Guest Network 5G"
    assert wifi_manager.networks[0]["password"] == "two words"


def test_single_quotes_work_too(send, wifi_manager):
    send("Add-Wifi ssid='Cafe Wifi' passwd='p@ss word'")

    assert wifi_manager.networks[0]["ssid"] == "Cafe Wifi"
    assert wifi_manager.networks[0]["password"] == "p@ss word"


def test_all_three_password_spellings_are_accepted(send, wifi_manager):
    send("Add-Wifi ssid=A passwd=one")
    send("Add-Wifi ssid=B psswd=two")
    send("Add-Wifi ssid=C password=three")

    assert [n["password"] for n in wifi_manager.networks] == ["one", "two", "three"]


def test_blank_lines_are_ignored(send):
    assert send("") == []
    assert send("   ") == []


def test_several_commands_arriving_in_one_chunk_all_run(console, devices):
    usb_cdc.console.feed("Set-device add name=One\nSet-device add name=Two\n")
    console.poll()

    assert [d.name for d in devices.devices] == ["One", "Two"]


def test_a_command_split_across_chunks_waits_for_its_newline(console, devices):
    usb_cdc.console.feed("Set-device add nam")
    console.poll()
    assert devices.devices == []

    usb_cdc.console.feed("e=Split\n")
    console.poll()
    assert [d.name for d in devices.devices] == ["Split"]


# -- help ------------------------------------------------------------------


def test_help_documents_every_top_level_command(send):
    text = "\n".join(send("Help")).lower()

    for command in ("add-wifi", "add-mqtt", "set-system", "set-device", "get-status"):
        assert command in text


def test_help_documents_the_new_button_modes(send):
    assert "momentary" in "\n".join(send("Help"))
    assert "switch" in "\n".join(send("Help"))


# -- wifi ------------------------------------------------------------------


def test_add_wifi_saves_and_connects(send, radio, wifi_manager):
    assert only(send("Add-Wifi ssid=HomeNet passwd=home-secret priority=10")) == (
        "OK wifi 'HomeNet' saved and connected"
    )
    assert wifi_manager.networks[0]["priority"] == 10
    assert radio.connected_ssid == "HomeNet"


def test_add_wifi_saves_even_when_the_network_is_out_of_range(send, radio, wifi_manager):
    assert only(send("Add-Wifi ssid=Elsewhere passwd=x")) == "OK wifi 'Elsewhere' saved"
    assert wifi_manager.networks[0]["ssid"] == "Elsewhere"


def test_add_wifi_without_an_ssid_is_an_error(send):
    assert only(send("Add-Wifi passwd=lonely")) == "ERR ssid required"


def test_wifi_add_under_set_system_is_the_same_command(send, radio, wifi_manager):
    send("Set-System wifi-add ssid=HomeNet passwd=home-secret")
    assert wifi_manager.networks[0]["ssid"] == "HomeNet"


def test_wifi_del_reports_hit_and_miss(send, wifi_manager):
    send("Add-Wifi ssid=HomeNet passwd=home-secret")

    assert only(send("Set-System wifi-del ssid=HomeNet")) == "OK wifi 'HomeNet' removed"
    assert only(send("Set-System wifi-del ssid=HomeNet")) == "OK wifi 'HomeNet' not found"


def test_wifi_list_shows_both_visible_and_saved_networks(send, radio):
    send("Add-Wifi ssid=HomeNet passwd=home-secret priority=3")

    lines = send("Set-System wifi-list")
    text = "\n".join(lines)

    assert "OK visible networks:" in lines
    assert "OK saved networks:" in lines
    assert "VenueNet" in text
    assert "HomeNet (priority 3)" in text


def test_wifi_list_says_so_when_nothing_is_saved(send, radio):
    assert "OK   (none saved)" in send("Set-System wifi-list")


# -- mqtt ------------------------------------------------------------------


def test_add_mqtt_enables_the_bridge(send, mqtt):
    assert only(send("Add-mqtt broker=192.168.1.20 user=dmx passwd=secret")) == (
        "OK mqtt enabled, broker=192.168.1.20"
    )
    assert mqtt.cfg["enabled"] is True
    assert mqtt.cfg["username"] == "dmx"
    assert mqtt.client is not None


def test_add_mqtt_accepts_a_custom_port(send, mqtt):
    send("Add-mqtt broker=broker.local user=u passwd=p port=8883")
    assert mqtt.cfg["port"] == 8883


def test_add_mqtt_without_a_broker_is_an_error(send):
    assert only(send("Add-mqtt user=dmx")) == "ERR broker required"


def test_mqtt_disable_tears_the_bridge_down(send, mqtt):
    send("Add-mqtt broker=broker.local user=u passwd=p")

    assert only(send("Set-System mqtt-disable")) == "OK mqtt disabled"
    assert mqtt.cfg["enabled"] is False
    assert mqtt.client is None


# -- dmx pins --------------------------------------------------------------


def test_tx_pin_is_stored_for_the_next_boot(send):
    assert only(send("Set-System tx-pin=IO7")) == "OK dmx tx pin set to 'IO7' (reboot to apply)"
    assert settings_store.load("system.json")["dmx_tx_pin"] == "IO7"


def test_tx_pin_also_accepts_the_spelled_out_form(send):
    send("Set-System tx-pin pin=D9")
    assert settings_store.load("system.json")["dmx_tx_pin"] == "D9"


def test_tx_pin_without_a_value_is_an_error(send):
    assert only(send("Set-System tx-pin")).startswith("ERR pin required")


def test_direction_pin_can_be_enabled_and_named(send):
    reply = only(send("Set-System dir-pin enable=true pin=D3"))

    assert reply == "OK dir pin enabled (pin=D3) (reboot to apply)"
    cfg = settings_store.load("system.json")
    assert cfg["dmx_dir_pin_enabled"] is True
    assert cfg["dmx_dir_pin"] == "D3"


def test_direction_pin_is_off_by_default_and_can_be_turned_back_off(send):
    send("Set-System dir-pin enable=true pin=D3")

    assert only(send("Set-System dir-pin enable=false")) == (
        "OK dir pin disabled (pin=D3) (reboot to apply)"
    )
    assert settings_store.load("system.json")["dmx_dir_pin_enabled"] is False


@pytest.mark.parametrize("truthy", ["true", "TRUE", "1", "yes", "on"])
def test_direction_pin_accepts_the_usual_yes_words(send, truthy):
    send("Set-System dir-pin enable=%s" % truthy)
    assert settings_store.load("system.json")["dmx_dir_pin_enabled"] is True


@pytest.mark.parametrize("falsy", ["false", "0", "no", "off", "banana"])
def test_anything_else_turns_the_direction_pin_off(send, falsy):
    send("Set-System dir-pin enable=true pin=D3")
    send("Set-System dir-pin enable=%s" % falsy)
    assert settings_store.load("system.json")["dmx_dir_pin_enabled"] is False


# -- hotspot ---------------------------------------------------------------


def test_hotspot_credentials_can_be_changed(send):
    reply = only(send('Set-System hotspot name="Stage Box" passwd=newsecret'))

    assert reply == "OK hotspot set to ssid='Stage Box' (reboot to apply)"
    cfg = settings_store.load("system.json")
    assert cfg["ap_ssid"] == "Stage Box"
    assert cfg["ap_password"] == "newsecret"


# -- filesystem ------------------------------------------------------------


def test_unlock_write_hands_the_filesystem_to_the_host(send):
    reply = only(send("Set-System unlock-write"))

    assert "PC-writable" in reply
    assert storage.remounts[-1] == ("/", True)


def test_unlock_write_fails_while_the_host_still_has_the_drive_mounted(send):
    storage.usb_visible = True

    reply = only(send("Set-System unlock-write"))

    assert reply == "ERR Cannot remount '/' when visible via USB."
    assert storage.remounts == []


def test_reboot_config_arms_the_marker_then_resets(send):
    with pytest.raises(microcontroller.ResetCalled):
        send("Set-System reboot-config")

    assert microcontroller.nvm[0] == 0x42
    assert "entering config mode" in usb_cdc.console.take_output()[0]


def test_reboot_config_explains_itself_when_nvm_is_unavailable(send, monkeypatch):
    class NoNvm:
        def __setitem__(self, index, value):
            raise RuntimeError("nvm region absent")

    monkeypatch.setattr(microcontroller, "nvm", NoNvm())

    assert "cannot arm config mode" in only(send("Set-System reboot-config"))


def test_reboot_resets_the_board(send):
    with pytest.raises(microcontroller.ResetCalled):
        send("Reboot")

    assert "OK rebooting" in usb_cdc.console.take_output()


# -- mesh ------------------------------------------------------------------


def test_mesh_settings_are_stored_but_flagged_as_inactive(send):
    reply = only(send("Set-System mesh role=parent ssid=DMXMESH passwd=meshpass"))

    assert reply == "OK mesh role='parent' ssid='DMXMESH' (WIP, not active yet)"
    cfg = settings_store.load("mesh.json")
    assert cfg == {"role": "parent", "ssid": "DMXMESH", "password": "meshpass"}


def test_an_invalid_mesh_role_is_rejected(send):
    assert only(send("Set-System mesh role=overlord")) == (
        "ERR role must be none, parent or child"
    )


def test_an_unknown_set_system_subcommand_is_reported(send):
    assert only(send("Set-System teleport")) == (
        "ERR unknown Set-System subcommand: teleport"
    )


# -- devices ---------------------------------------------------------------


def test_adding_a_device_assigns_the_next_free_address(send, devices):
    assert only(send("Set-device add name=PAR")) == "OK device 'PAR' added (start channel 1)"

    send("Set-device add-channel device=PAR name=Dim channel=4 mode=slider")
    assert only(send("Set-device add name=Fog")) == "OK device 'Fog' added (start channel 5)"


def test_adding_a_device_without_a_name_is_an_error(send):
    assert only(send("Set-device add")) == "ERR name required"


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("slider", "slider"),
        ("button", "button"),
        ("trigger", "button"),
        ("btn", "button"),
        ("momentary", "button-momentary"),
        ("hold", "button-momentary"),
        ("button-momentary", "button-momentary"),
        ("switch", "button-switch"),
        ("toggle", "button-switch"),
        ("button-switch", "button-switch"),
        ("nonsense", "slider"),
    ],
)
def test_every_channel_mode_alias_maps_to_a_real_type(send, devices, mode, expected):
    send("Set-device add name=PAR")
    send("Set-device add-channel device=PAR name=Ch channel=1 mode=%s" % mode)

    assert devices.find_by_name("PAR").channels[0].type == expected


def test_adding_a_channel_reports_where_it_landed(send):
    send("Set-device add name=PAR")

    assert only(send("Set-device add-channel device=PAR name=Dim channel=2 mode=slider")) == (
        "OK channel 'Dim' added to 'PAR' (offset 2, slider)"
    )


def test_adding_a_channel_needs_device_name_and_offset(send):
    send("Set-device add name=PAR")

    assert only(send("Set-device add-channel device=PAR name=Dim")) == (
        "ERR device=, name= and channel= required"
    )


def test_adding_a_channel_to_an_unknown_device_is_an_error(send):
    assert only(send("Set-device add-channel device=Ghost name=Dim channel=1")) == (
        "ERR no device named 'Ghost'"
    )


def test_removing_a_channel(send, devices):
    send("Set-device add name=PAR")
    send("Set-device add-channel device=PAR name=Dim channel=1")

    assert only(send("Set-device del-channel name=Dim")) == "OK channel 'Dim' removed from 'PAR'"
    assert devices.find_by_name("PAR").channels == []


def test_removing_an_ambiguous_channel_asks_which_device(send):
    for name in ("Left", "Right"):
        send("Set-device add name=%s" % name)
        send("Set-device add-channel device=%s name=Dim channel=1" % name)

    assert "multiple devices" in only(send("Set-device del-channel name=Dim"))
    assert only(send("Set-device del-channel name=Dim device=Left")) == (
        "OK channel 'Dim' removed from 'Left'"
    )


def test_removing_a_device_reports_hit_and_miss(send):
    send("Set-device add name=PAR")

    assert only(send("Set-device del device=PAR")) == "OK device 'PAR' removed"
    assert only(send("Set-device del device=PAR")) == "OK device 'PAR' not found"


def test_removing_a_device_needs_the_device_argument(send):
    assert only(send("Set-device del name=PAR")) == "ERR device required"


# -- status ----------------------------------------------------------------


def test_get_status_defaults_to_the_full_report(send, radio, par_fixture):
    lines = send("get-status")
    text = "\n".join(lines)

    assert "OK wifi: mode=None" in text
    assert "OK mqtt: enabled=False connected=False broker=" in text
    assert "OK system: hostname=ESP-DMX tx_pin=D4 dir_pin=disabled" in text
    assert "OK devices: 1 device(s), 4 channel(s)" in text
    assert "bytes free" in text


def test_get_status_all_is_the_same_as_no_argument(send):
    assert send("get-status") == send("get-status all")


def test_status_shows_the_direction_pin_once_enabled(send):
    send("Set-System dir-pin enable=true pin=D3")

    assert "dir_pin=D3" in "\n".join(send("get-status"))


def test_status_wifi_after_joining_a_network(send, radio, wifi_manager):
    wifi_manager.try_connect("HomeNet", "home-secret")

    assert only(send("get-status wifi")) == "OK wifi: mode=sta ssid=HomeNet ip=192.168.1.98"


def test_status_mqtt(send):
    send("Add-mqtt broker=broker.local user=u passwd=p")

    assert only(send("get-status mqtt")) == (
        "OK mqtt: enabled=True connected=True broker=broker.local"
    )


def test_status_devices_lists_each_fixture(send, par_fixture):
    assert only(send("get-status devices")) == "OK PAR LED: start=1 channels=4"


def test_status_devices_says_so_when_there_are_none(send):
    assert only(send("get-status devices")) == "OK (no devices configured)"


def test_status_device_shows_live_channel_values(send, devices, par_fixture):
    devices.set_value(par_fixture.id, 2, 200)

    lines = send('get-status device name="PAR LED"')

    assert "OK   1: Dimmer (slider) = 0" in lines
    assert "OK   2: Red (slider) = 200" in lines
    assert "OK   3: Strobe (button-momentary) = 0" in lines
    assert "OK   4: Lamp (button-switch) = 0" in lines


def test_status_device_needs_a_name(send):
    assert only(send("get-status device")) == "ERR name required"


def test_status_device_reports_an_unknown_fixture(send):
    assert only(send("get-status device name=Ghost")) == "ERR no device named 'Ghost'"


def test_status_channel_finds_one_channel(send, devices, par_fixture):
    devices.set_value(par_fixture.id, 1, 42)

    assert only(send("get-status channel channel=Dimmer")) == (
        "OK PAR LED/Dimmer: offset=1 mode=slider value=42"
    )


def test_status_channel_reports_every_match_across_devices(send, devices):
    for name, start in (("Left", 1), ("Right", 10)):
        devices.add_device(name, start, [{"offset": 1, "name": "Dim", "type": "slider"}])

    assert len(send("get-status channel channel=Dim")) == 2
    assert len(send("get-status channel channel=Dim device=Left")) == 1


def test_status_channel_needs_a_channel_name(send):
    assert only(send("get-status channel")) == "ERR channel required"


def test_status_channel_reports_an_unknown_channel(send):
    assert only(send("get-status channel channel=Ghost")) == "ERR no channel named 'Ghost'"


def test_status_mesh_flags_the_feature_as_unfinished(send):
    assert only(send("get-status mesh")) == "OK mesh (WIP): role=none ssid="


def test_an_unknown_status_subcommand_is_reported(send):
    assert only(send("get-status weather")) == "ERR unknown get-status subcommand: weather"
