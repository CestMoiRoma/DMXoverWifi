"""The HTTP surface: static pages plus the JSON API the web UI drives."""
import pytest

from src import settings_store


def test_the_server_is_rooted_at_the_web_ui_directory(server):
    assert server.server.root_path == "/www"


def test_start_listens_on_all_interfaces_on_port_80(server):
    server.start()

    assert server.server.started is True
    assert (server.server.host, server.server.port) == ("0.0.0.0", 80)


def test_poll_survives_a_dropped_connection(server, monkeypatch):
    def explode():
        raise OSError("connection reset by peer")

    monkeypatch.setattr(server.server, "poll", explode)
    server.poll()  # a dead socket must not take the main loop down


def test_the_root_serves_the_single_page_app(server):
    response = server.server.dispatch("GET", "/")
    assert response.filename == "index.html"


def test_the_wiki_is_served_as_plain_text(server):
    response = server.server.dispatch("GET", "/wiki.md")

    assert response.filename == "wiki.md"
    assert response.content_type == "text/plain"


# -- devices ---------------------------------------------------------------


def test_devices_start_empty(server):
    assert server.server.dispatch("GET", "/api/devices").data == []


def test_creating_a_device_returns_it_with_an_id(server):
    payload = {
        "name": "PAR LED",
        "start_channel": 5,
        "channels": [{"offset": 1, "name": "Dim", "type": "slider"}],
    }

    created = server.server.dispatch("POST", "/api/devices", payload).data

    assert created["id"].startswith("dev-")
    assert created["name"] == "PAR LED"
    assert created["start_channel"] == 5
    assert created["channels"] == [{"offset": 1, "name": "Dim", "type": "slider"}]


def test_creating_a_device_defaults_to_address_one_with_no_channels(server):
    created = server.server.dispatch("POST", "/api/devices", {"name": "Bare"}).data

    assert created["start_channel"] == 1
    assert created["channels"] == []


def test_listing_devices_reflects_what_was_created(server):
    server.server.dispatch("POST", "/api/devices", {"name": "One"})
    server.server.dispatch("POST", "/api/devices", {"name": "Two"})

    assert [d["name"] for d in server.server.dispatch("GET", "/api/devices").data] == [
        "One",
        "Two",
    ]


def test_updating_a_device(server, par_fixture):
    updated = server.server.dispatch(
        "PUT", "/api/devices/%s" % par_fixture.id, {"name": "Renamed", "start_channel": 60}
    ).data

    assert updated["name"] == "Renamed"
    assert updated["start_channel"] == 60


def test_updating_an_unknown_device_is_a_404(server):
    response = server.server.dispatch("PUT", "/api/devices/dev-ghost", {"name": "x"})

    assert response.status_code == 404
    assert response.data == {"error": "not found"}


def test_deleting_a_device(server, par_fixture):
    assert server.server.dispatch("DELETE", "/api/devices/%s" % par_fixture.id).data == {
        "ok": True
    }
    assert server.server.dispatch("GET", "/api/devices").data == []


def test_deleting_an_unknown_device_reports_a_miss(server):
    assert server.server.dispatch("DELETE", "/api/devices/dev-ghost").data == {"ok": False}


@pytest.mark.parametrize("offset,address", [(1, 1), (2, 2), (4, 4)])
def test_setting_a_channel_drives_the_dmx_line(server, par_fixture, dmx, offset, address):
    response = server.server.dispatch(
        "POST", "/api/devices/%s/channel/%d" % (par_fixture.id, offset), {"value": 199}
    )

    assert response.data == {"ok": True}
    assert dmx.buffer[address] == 199


def test_setting_a_channel_on_a_relocated_fixture_follows_the_address(server, dmx):
    device = server.server.dispatch(
        "POST",
        "/api/devices",
        {
            "name": "Wash",
            "start_channel": 100,
            "channels": [{"offset": 3, "name": "Blue", "type": "slider"}],
        },
    ).data

    server.server.dispatch("POST", "/api/devices/%s/channel/3" % device["id"], {"value": 50})

    assert dmx.buffer[102] == 50


def test_setting_a_channel_without_a_value_turns_it_off(server, par_fixture, dmx):
    server.server.dispatch("POST", "/api/devices/%s/channel/1" % par_fixture.id, {"value": 255})

    server.server.dispatch("POST", "/api/devices/%s/channel/1" % par_fixture.id, {})

    assert dmx.buffer[1] == 0


def test_setting_an_unknown_channel_is_a_404(server, par_fixture):
    response = server.server.dispatch(
        "POST", "/api/devices/%s/channel/99" % par_fixture.id, {"value": 1}
    )
    assert response.status_code == 404


def test_creating_a_device_republishes_mqtt_discovery(server, mqtt):
    mqtt.set_config({"enabled": True, "host": "broker.local"})
    mqtt.start()

    created = server.server.dispatch(
        "POST",
        "/api/devices",
        {"name": "New", "channels": [{"offset": 1, "name": "Dim", "type": "slider"}]},
    ).data

    assert mqtt.client.published_to(
        "homeassistant/number/%s_1/config" % created["id"]
    ), "a fixture added from the web UI must show up in Home Assistant"


# -- wifi ------------------------------------------------------------------


def test_wifi_list_is_empty_at_first(server):
    assert server.server.dispatch("GET", "/api/wifi").data == []


def test_adding_a_network_returns_the_updated_list(server):
    networks = server.server.dispatch(
        "POST", "/api/wifi", {"ssid": "HomeNet", "password": "s3cret", "priority": 4}
    ).data

    assert networks == [{"ssid": "HomeNet", "password": "s3cret", "priority": 4}]


def test_adding_a_network_over_http_does_not_try_to_join_it(server, radio):
    server.server.dispatch("POST", "/api/wifi", {"ssid": "HomeNet", "password": "home-secret"})

    assert radio.connect_calls == [], "the UI saves; only the serial command connects"


def test_a_network_added_without_a_password_is_stored_open(server):
    networks = server.server.dispatch("POST", "/api/wifi", {"ssid": "Open"}).data
    assert networks[0] == {"ssid": "Open", "password": "", "priority": 0}


def test_deleting_a_network(server):
    server.server.dispatch("POST", "/api/wifi", {"ssid": "HomeNet", "password": "x"})

    assert server.server.dispatch("DELETE", "/api/wifi/HomeNet").data == []


def test_scanning_reports_what_the_radio_can_see(server, radio):
    results = server.server.dispatch("GET", "/api/wifi/scan").data

    assert {net["ssid"] for net in results} == {"HomeNet", "VenueNet"}


def test_the_scan_route_is_not_shadowed_by_the_delete_route(server, radio):
    assert server.server.has_route("GET", "/api/wifi/scan")


# -- mqtt ------------------------------------------------------------------


def test_reading_mqtt_config_returns_the_defaults(server):
    cfg = server.server.dispatch("GET", "/api/mqtt").data

    assert cfg["enabled"] is False
    assert cfg["port"] == 1883
    assert cfg["base_topic"] == "dmxwifi"


def test_saving_mqtt_config_connects_and_persists(server, mqtt):
    cfg = server.server.dispatch(
        "POST",
        "/api/mqtt",
        {"enabled": True, "host": "broker.local", "username": "dmx", "password": "p"},
    ).data

    assert cfg["host"] == "broker.local"
    assert mqtt.client is not None
    assert settings_store.load("mqtt.json")["host"] == "broker.local"


def test_saving_partial_mqtt_config_keeps_the_rest(server):
    server.server.dispatch("POST", "/api/mqtt", {"base_topic": "stage"})

    cfg = server.server.dispatch("GET", "/api/mqtt").data
    assert cfg["base_topic"] == "stage"
    assert cfg["discovery_prefix"] == "homeassistant"


# -- system ----------------------------------------------------------------


def test_reading_system_config_returns_the_shipping_defaults(server):
    cfg = server.server.dispatch("GET", "/api/system").data

    assert cfg["dmx_tx_pin"] == "D4"
    assert cfg["dmx_dir_pin_enabled"] is False
    assert cfg["ap_ssid"] == "ESP-DMX"
    assert cfg["ap_ip"] == "1.1.1.1"


def test_saving_system_config_merges_rather_than_replaces(server):
    cfg = server.server.dispatch("POST", "/api/system", {"dmx_tx_pin": "IO7"}).data

    assert cfg["dmx_tx_pin"] == "IO7"
    assert cfg["ap_ssid"] == "ESP-DMX", "untouched keys must survive"
    assert settings_store.load("system.json")["dmx_tx_pin"] == "IO7"


def test_the_direction_pin_can_be_enabled_from_the_ui(server):
    cfg = server.server.dispatch(
        "POST", "/api/system", {"dmx_dir_pin_enabled": True, "dmx_dir_pin": "D3"}
    ).data

    assert cfg["dmx_dir_pin_enabled"] is True
    assert cfg["dmx_dir_pin"] == "D3"


# -- mesh ------------------------------------------------------------------


def test_mesh_config_defaults_to_inactive(server):
    assert server.server.dispatch("GET", "/api/mesh").data["role"] == "none"


def test_mesh_config_is_stored(server):
    cfg = server.server.dispatch("POST", "/api/mesh", {"role": "child", "ssid": "MESH"}).data

    assert cfg["role"] == "child"
    assert settings_store.load("mesh.json")["ssid"] == "MESH"


# -- info ------------------------------------------------------------------


def test_the_info_page_gets_version_author_and_links(server):
    info = server.server.dispatch("GET", "/api/info").data

    assert set(info) >= {"version", "author", "repo", "wiki_online", "wiki_local"}
    assert info["author"]["name"]
    assert info["author"]["url"].startswith("https://")
    assert info["repo"].startswith("https://github.com/")
    assert info["wiki_local"] == "/wiki.md"


def test_the_reported_version_matches_the_source_of_truth(server):
    from src.version import VERSION

    assert server.server.dispatch("GET", "/api/info").data["version"] == VERSION


def test_the_online_wiki_link_points_at_the_repo(server):
    info = server.server.dispatch("GET", "/api/info").data

    assert info["wiki_online"].startswith(info["repo"])
    assert info["wiki_online"].endswith("WIKI.md")
