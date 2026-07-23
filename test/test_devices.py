"""Fixtures, channels, DMX addressing and persistence."""
import pytest

from src.devices import CHANNEL_TYPES, Channel, DeviceManager


def test_all_four_channel_types_are_accepted():
    assert set(CHANNEL_TYPES) == {"slider", "button", "button-momentary", "button-switch"}
    for type_ in CHANNEL_TYPES:
        assert Channel(1, "ch", type_).type == type_


def test_unknown_channel_type_falls_back_to_slider():
    assert Channel(1, "ch", "rotary-encoder").type == "slider"
    assert Channel(1, "ch", None).type == "slider"


def test_channel_offset_is_relative_to_the_fixture_address(devices):
    device = devices.add_device("Wash", 10, [{"offset": 1, "name": "Dim", "type": "slider"}])
    channel = device.channels[0]

    # Start channel 10, offset 1 lands on DMX 10, not 11.
    assert device.address_for(channel) == 10


def test_setting_a_channel_writes_the_mapped_dmx_slot(devices, dmx):
    device = devices.add_device("Wash", 10, [{"offset": 3, "name": "Blue", "type": "slider"}])

    devices.set_value(device.id, 3, 200)

    assert dmx.buffer[12] == 200
    assert devices.get_value(device, device.channels[0]) == 200


def test_setting_a_channel_clamps_to_the_dmx_range(devices, dmx):
    device = devices.add_device("Wash", 1, [{"offset": 1, "name": "Dim", "type": "slider"}])

    devices.set_value(device.id, 1, 9999)
    assert dmx.buffer[1] == 255

    devices.set_value(device.id, 1, -5)
    assert dmx.buffer[1] == 0


def test_setting_an_unknown_device_or_channel_reports_a_miss(devices, par_fixture):
    assert devices.set_value("dev-nope", 1, 128) is None
    assert devices.set_value(par_fixture.id, 99, 128) is None


def test_devices_survive_a_reboot(devices, dmx, par_fixture):
    reloaded = DeviceManager(dmx)

    assert [d.name for d in reloaded.devices] == ["PAR LED"]
    assert [c.type for c in reloaded.devices[0].channels] == [
        "slider",
        "slider",
        "button-momentary",
        "button-switch",
    ]


def test_each_device_gets_a_distinct_id(devices):
    first = devices.add_device("A", 1, [])
    second = devices.add_device("B", 2, [])

    assert first.id != second.id
    assert first.id.startswith("dev-")


def test_next_free_start_channel_packs_fixtures_end_to_end(devices):
    assert devices.next_free_start_channel() == 1

    devices.add_device("PAR", 1, [{"offset": 1, "name": "a"}, {"offset": 4, "name": "d"}])
    # PAR occupies 1 through 4, so the next fixture starts at 5.
    assert devices.next_free_start_channel() == 5


def test_channelless_devices_do_not_reserve_addresses(devices):
    devices.add_device("Empty", 1, [])
    assert devices.next_free_start_channel() == 1


def test_update_device_changes_only_what_is_passed(devices, par_fixture):
    updated = devices.update_device(par_fixture.id, start_channel=100)

    assert updated.start_channel == 100
    assert updated.name == "PAR LED"
    assert len(updated.channels) == 4


def test_update_device_can_replace_the_channel_list(devices, par_fixture):
    updated = devices.update_device(
        par_fixture.id, channels=[{"offset": 1, "name": "Only", "type": "button"}]
    )

    assert [c.name for c in updated.channels] == ["Only"]


def test_update_unknown_device_returns_none(devices):
    assert devices.update_device("dev-nope", name="x") is None


def test_remove_device_by_id_and_by_name(devices):
    keep = devices.add_device("Keep", 1, [])
    drop = devices.add_device("Drop", 2, [])

    assert devices.remove_device(drop.id) is True
    assert devices.remove_device(drop.id) is False
    assert devices.remove_device_by_name("Nope") is False
    assert [d.id for d in devices.devices] == [keep.id]


def test_add_channel_to_an_unknown_device_raises(devices):
    with pytest.raises(ValueError, match="no device named"):
        devices.add_channel("Ghost", "Dim", 1, "slider")


def test_removing_an_ambiguous_channel_name_asks_for_the_device(devices):
    devices.add_device("Left", 1, [{"offset": 1, "name": "Dimmer", "type": "slider"}])
    devices.add_device("Right", 10, [{"offset": 1, "name": "Dimmer", "type": "slider"}])

    with pytest.raises(ValueError, match="multiple devices"):
        devices.remove_channel_by_name("Dimmer")

    # Naming the device disambiguates it.
    assert devices.remove_channel_by_name("Dimmer", "Right").name == "Right"


def test_removing_an_unknown_channel_raises(devices):
    with pytest.raises(ValueError, match="no channel named"):
        devices.remove_channel_by_name("Nothing")


def test_to_dict_round_trips_through_json_shape(devices, par_fixture):
    payload = par_fixture.to_dict()

    assert set(payload) == {"id", "name", "start_channel", "channels"}
    assert payload["channels"][2] == {
        "offset": 3,
        "name": "Strobe",
        "type": "button-momentary",
    }
