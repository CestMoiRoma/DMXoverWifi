"""Shared test setup.

Puts `test/fake_esp32` ahead of the repo root on `sys.path` so the firmware's
`import board` (and friends) land on the stubs, then hands out ready-made
firmware objects wired together the way `code.py` wires them.

Every test starts from a freshly powered fake board with an empty config
directory, so nothing leaks between tests.
"""
import os
import sys
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parent
FAKE_HW = TEST_DIR / "fake_esp32"

# The repo root holds code.py, the firmware entry point CircuitPython runs on
# boot. On CPython that name collides with the stdlib `code` module, which pdb
# imports, which pytest imports at startup. If the repo root sits early on
# sys.path, starting pytest runs the firmware and blocks forever in its main
# loop. So: drop the repo root from the front of sys.path, pin the real stdlib
# module in sys.modules while nothing can shadow it, and only then re-add the
# repo root at the very end where it can no longer win a name race.
_ROOT_ALIASES = {"", str(REPO_ROOT), str(REPO_ROOT) + os.sep, os.getcwd()}
sys.path[:] = [entry for entry in sys.path if entry not in _ROOT_ALIASES]

import code as _stdlib_code  # noqa: E402,F401  pinned before src/ is reachable

sys.path.insert(0, str(FAKE_HW))
sys.path.append(str(REPO_ROOT))

assert _stdlib_code.__file__ != str(REPO_ROOT / "code.py"), (
    "stdlib `code` got shadowed by the firmware entry point; "
    "the sys.path guard above is not doing its job"
)

import gc  # noqa: E402

import busio  # noqa: E402
import digitalio  # noqa: E402
import microcontroller  # noqa: E402
import pytest  # noqa: E402
import socketpool  # noqa: E402
import storage  # noqa: E402
import usb_cdc  # noqa: E402
import wifi  # noqa: E402
from adafruit_minimqtt import adafruit_minimqtt as fake_mqtt  # noqa: E402

import board  # noqa: E402
from src import settings_store  # noqa: E402
from src.devices import DeviceManager  # noqa: E402
from src.dmx_driver import DmxDriver  # noqa: E402
from src.mqtt_manager import MqttManager  # noqa: E402
from src.serial_console import SerialConsole  # noqa: E402
from src.web_server import WebServer  # noqa: E402
from src.wifi_manager import WifiManager  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_board(tmp_path, monkeypatch):
    """Power-cycle every stub and point the config store at a temp directory.

    settings_store writes to the absolute path /data on the board. Left alone it
    would try to write to the filesystem root of whatever machine runs the suite.
    """
    busio._reset_state()
    digitalio._reset_state()
    microcontroller._reset_state()
    storage._reset_state()
    usb_cdc._reset_state()
    wifi._reset_state()
    fake_mqtt._reset_state()
    monkeypatch.setattr(settings_store, "DATA_DIR", str(tmp_path / "data"))
    # CircuitPython's gc reports free heap; CPython's does not. get-status
    # prints it, so give the real module a stand-in for the duration.
    monkeypatch.setattr(gc, "mem_free", lambda: 1_946_528, raising=False)
    yield


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def radio():
    """The fake radio, with a couple of networks in range by default."""
    wifi.radio.set_environment({"HomeNet": "home-secret", "VenueNet": "venue-secret"})
    return wifi.radio


@pytest.fixture
def dmx():
    return DmxDriver(board.D4)


@pytest.fixture
def devices(dmx):
    return DeviceManager(dmx)


@pytest.fixture
def wifi_manager():
    return WifiManager()


@pytest.fixture
def mqtt(devices):
    return MqttManager(devices)


@pytest.fixture
def console(devices, wifi_manager, mqtt):
    return SerialConsole(devices, wifi_manager, mqtt)


@pytest.fixture
def server(devices, wifi_manager, mqtt, dmx):
    pool = socketpool.SocketPool(wifi.radio)
    return WebServer(pool, devices, wifi_manager, mqtt, dmx)


@pytest.fixture
def send(console):
    """Type a line into the serial console and collect the reply lines."""

    def _send(line):
        usb_cdc.console.feed(line + "\n")
        console.poll()
        return usb_cdc.console.take_output()

    return _send


@pytest.fixture
def par_fixture(devices):
    """A four-channel dimmer at DMX address 1, used by several tests."""
    return devices.add_device(
        "PAR LED",
        1,
        [
            {"offset": 1, "name": "Dimmer", "type": "slider"},
            {"offset": 2, "name": "Red", "type": "slider"},
            {"offset": 3, "name": "Strobe", "type": "button-momentary"},
            {"offset": 4, "name": "Lamp", "type": "button-switch"},
        ],
    )
