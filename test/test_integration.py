"""Whole-stack checks that mirror how code.py wires the firmware together.

code.py ends in `while True:`, so it cannot be imported. These tests build the
same object graph by hand and then drive it, which catches the wiring mistakes a
per-module test cannot see.
"""
import socketpool
import wifi

import board
from src import settings_store
from src.devices import DeviceManager
from src.dmx_driver import DmxDriver
from src.mqtt_manager import MqttManager
from src.serial_console import SerialConsole
from src.web_server import WebServer
from src.wifi_manager import WifiManager


class Board:
    """The object graph code.py builds, minus the infinite loop."""

    def __init__(self, config_mode=False):
        cfg = settings_store.load("system.json")
        dir_pin = None
        if cfg.get("dmx_dir_pin_enabled"):
            dir_pin = getattr(board, cfg["dmx_dir_pin"])

        self.dmx = DmxDriver(getattr(board, cfg["dmx_tx_pin"]), dir_pin)
        self.devices = DeviceManager(self.dmx)
        self.wifi = WifiManager()
        self.mqtt = MqttManager(self.devices)
        self.console = SerialConsole(self.devices, self.wifi, self.mqtt)

        if config_mode:
            self.wifi.start_ap(cfg["ap_ssid"], cfg["ap_password"], cfg["ap_ip"])
        elif not self.wifi.connect_known():
            self.wifi.start_ap(cfg["ap_ssid"], cfg["ap_password"], cfg["ap_ip"])

        pool = socketpool.SocketPool(wifi.radio)
        self.web = WebServer(pool, self.devices, self.wifi, self.mqtt, self.dmx)
        self.web.start()

        if self.wifi.mode == "sta":
            self.mqtt.start()

    def tick(self):
        """One pass of the main loop."""
        self.web.poll()
        self.mqtt.loop()
        self.dmx.refresh_if_due()
        self.console.poll()


def test_a_board_with_no_saved_networks_comes_up_on_its_own_hotspot(radio):
    box = Board()

    assert box.wifi.mode == "ap"
    assert radio.ap_ssid == "ESP-DMX"
    assert radio.ipv4_address_ap == "1.1.1.1"
    assert box.web.server.started is True


def test_a_board_that_knows_the_venue_joins_it_instead(radio):
    WifiManager().add_network("VenueNet", "venue-secret", 5)

    box = Board()

    assert box.wifi.mode == "sta"
    assert radio.ap_active is False


def test_config_mode_starts_the_hotspot_without_even_trying_the_networks(radio):
    WifiManager().add_network("VenueNet", "venue-secret", 5)

    box = Board(config_mode=True)

    assert box.wifi.mode == "ap"
    assert radio.connect_calls == [], "config mode must not depend on the venue wifi"


def test_mqtt_only_starts_once_the_board_is_on_a_real_network(radio):
    settings_store.save(
        "mqtt.json", dict(settings_store.DEFAULTS["mqtt.json"], enabled=True, host="broker.local")
    )

    on_hotspot = Board()
    assert on_hotspot.mqtt.client is None, "no broker is reachable from our own AP"

    WifiManager().add_network("VenueNet", "venue-secret", 5)
    on_network = Board()
    assert on_network.mqtt.client is not None


def test_the_configured_tx_pin_is_the_one_that_gets_claimed(radio):
    settings_store.save(
        "system.json", dict(settings_store.DEFAULTS["system.json"], dmx_tx_pin="IO7")
    )

    box = Board()

    assert box.dmx._uart.tx == board.IO7


def test_enabling_the_direction_pin_claims_it_at_boot(radio):
    settings_store.save(
        "system.json",
        dict(settings_store.DEFAULTS["system.json"], dmx_dir_pin_enabled=True, dmx_dir_pin="D5"),
    )

    box = Board()

    assert box.dmx._direction is not None
    assert box.dmx._direction.pin == board.D5


def test_the_main_loop_keeps_refreshing_dmx(radio, monkeypatch):
    box = Board()
    clock = {"now": 500.0}
    monkeypatch.setattr("src.dmx_driver.time.monotonic", lambda: clock["now"])

    frames = 0
    for _ in range(10):
        before = box.dmx._last_send
        box.tick()
        if box.dmx._last_send != before:
            frames += 1
        clock["now"] += 0.03

    assert frames >= 9, "the universe must keep going out every loop pass"


def test_a_fixture_created_over_http_is_visible_over_serial(radio):
    box = Board()
    import usb_cdc

    created = box.web.server.dispatch(
        "POST",
        "/api/devices",
        {
            "name": "PAR",
            "start_channel": 10,
            "channels": [{"offset": 1, "name": "Dim", "type": "slider"}],
        },
    ).data

    usb_cdc.console.feed("get-status device name=PAR\n")
    box.console.poll()
    replies = usb_cdc.console.take_output()

    assert replies == ["OK   1: Dim (slider) = 0"]

    box.web.server.dispatch("POST", "/api/devices/%s/channel/1" % created["id"], {"value": 128})

    assert box.dmx.buffer[10] == 128


def test_a_fixture_created_over_serial_shows_up_in_the_web_ui(radio):
    box = Board()
    import usb_cdc

    usb_cdc.console.feed("Set-device add name=Fog\n")
    box.console.poll()
    usb_cdc.console.feed("Set-device add-channel device=Fog name=Burst channel=1 mode=toggle\n")
    box.console.poll()

    devices = box.web.server.dispatch("GET", "/api/devices").data

    assert devices[0]["name"] == "Fog"
    assert devices[0]["channels"][0]["type"] == "button-switch"


def test_a_command_from_home_assistant_reaches_the_dmx_line(radio):
    WifiManager().add_network("VenueNet", "venue-secret", 5)
    settings_store.save(
        "mqtt.json", dict(settings_store.DEFAULTS["mqtt.json"], enabled=True, host="broker.local")
    )
    box = Board()

    created = box.web.server.dispatch(
        "POST",
        "/api/devices",
        {
            "name": "Lamp",
            "start_channel": 7,
            "channels": [{"offset": 1, "name": "Power", "type": "button-switch"}],
        },
    ).data

    box.mqtt.client.inject("dmxwifi/%s_1/set" % created["id"], "ON")
    box.tick()

    assert box.dmx.buffer[7] == 255
    assert box.dmx._uart.written[7] == 255, "and it actually goes out on the wire"
