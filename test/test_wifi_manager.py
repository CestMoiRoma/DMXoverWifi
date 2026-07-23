"""Saved-network database, priority ordering and the access-point fallback."""
from src.wifi_manager import WifiManager


def test_networks_start_empty(wifi_manager):
    assert wifi_manager.networks == []


def test_adding_a_network_persists_it(wifi_manager):
    wifi_manager.add_network("HomeNet", "home-secret", 5)

    assert WifiManager().networks == [
        {"ssid": "HomeNet", "password": "home-secret", "priority": 5}
    ]


def test_re_adding_an_ssid_replaces_it_instead_of_duplicating(wifi_manager):
    wifi_manager.add_network("HomeNet", "old", 0)
    wifi_manager.add_network("HomeNet", "new", 9)

    assert len(wifi_manager.networks) == 1
    assert wifi_manager.networks[0]["password"] == "new"
    assert wifi_manager.networks[0]["priority"] == 9


def test_remove_network_reports_whether_it_matched(wifi_manager):
    wifi_manager.add_network("HomeNet", "x", 0)

    assert wifi_manager.remove_network("HomeNet") is True
    assert wifi_manager.remove_network("HomeNet") is False
    assert WifiManager().networks == []


def test_connect_known_tries_the_highest_priority_first(wifi_manager, radio):
    wifi_manager.add_network("VenueNet", "venue-secret", 1)
    wifi_manager.add_network("HomeNet", "home-secret", 10)

    assert wifi_manager.connect_known() is True
    assert radio.connect_calls[0][0] == "HomeNet"
    assert wifi_manager.mode == "sta"


def test_connect_known_falls_through_to_the_next_network(wifi_manager, radio):
    wifi_manager.add_network("AbsentNet", "nope", 10)
    wifi_manager.add_network("HomeNet", "home-secret", 1)

    assert wifi_manager.connect_known() is True
    assert [call[0] for call in radio.connect_calls] == ["AbsentNet", "HomeNet"]
    assert radio.connected_ssid == "HomeNet"


def test_connect_known_reports_failure_when_nothing_is_in_range(wifi_manager, radio):
    wifi_manager.add_network("AbsentNet", "nope", 0)

    assert wifi_manager.connect_known() is False
    assert wifi_manager.mode is None


def test_a_wrong_password_is_a_failure_not_a_crash(wifi_manager, radio):
    wifi_manager.add_network("HomeNet", "wrong-password", 0)

    assert wifi_manager.connect_known() is False


def test_entries_without_an_ssid_are_skipped(wifi_manager, radio):
    wifi_manager.networks = [{"ssid": "", "password": "x", "priority": 99}]
    wifi_manager.add_network("HomeNet", "home-secret", 0)

    assert wifi_manager.connect_known() is True
    assert radio.connect_calls[0][0] == "HomeNet"


def test_joining_a_network_shuts_down_a_running_hotspot(wifi_manager, radio):
    wifi_manager.start_ap("ESP-DMX", "DMX4ALL1", "1.1.1.1")
    assert radio.ap_active is True

    wifi_manager.try_connect("HomeNet", "home-secret")

    assert radio.ap_active is False
    assert wifi_manager.ap_ssid is None
    assert wifi_manager.mode == "sta"


def test_start_ap_applies_the_configured_static_address(wifi_manager, radio):
    wifi_manager.start_ap("ESP-DMX", "DMX4ALL1", "1.1.1.1")

    assert wifi_manager.mode == "ap"
    assert radio.ap_ssid == "ESP-DMX"
    assert radio.ap_password == "DMX4ALL1"
    assert radio.ap_ipv4_config == ("1.1.1.1", "255.255.255.0", "1.1.1.1")
    assert radio.stop_station_calls == 1


def test_start_ap_without_a_password_opens_the_network(wifi_manager, radio):
    wifi_manager.start_ap("ESP-DMX", "", "1.1.1.1")
    assert radio.ap_password is None


def test_a_bad_static_address_does_not_stop_the_hotspot(wifi_manager, radio):
    wifi_manager.start_ap("ESP-DMX", "DMX4ALL1", "not-an-ip")

    assert wifi_manager.mode == "ap"
    assert radio.ap_active is True


def test_status_in_station_mode(wifi_manager, radio):
    wifi_manager.try_connect("HomeNet", "home-secret")

    assert wifi_manager.status() == {
        "mode": "sta",
        "ssid": "HomeNet",
        "ip": "192.168.1.98",
    }


def test_status_in_access_point_mode(wifi_manager, radio):
    wifi_manager.start_ap("ESP-DMX", "DMX4ALL1", "1.1.1.1")

    assert wifi_manager.status() == {
        "mode": "ap",
        "ssid": "ESP-DMX",
        "ip": "1.1.1.1",
    }


def test_status_before_any_radio_activity(wifi_manager):
    assert wifi_manager.status() == {"mode": None, "ssid": None, "ip": None}


def test_scan_lists_visible_networks(wifi_manager, radio):
    results = wifi_manager.scan()

    assert {net["ssid"] for net in results} == {"HomeNet", "VenueNet"}
    assert all(isinstance(net["rssi"], int) for net in results)
    assert radio.scanning is False, "the scan must be stopped again"


def test_reload_networks_picks_up_changes_written_elsewhere(wifi_manager):
    WifiManager().add_network("Added", "elsewhere", 0)
    assert wifi_manager.networks == []

    wifi_manager.reload_networks()
    assert [n["ssid"] for n in wifi_manager.networks] == ["Added"]
