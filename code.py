import time

import board
import microcontroller
import socketpool
import wifi

from src import settings_store
from src.devices import DeviceManager
from src.dmx_driver import DmxDriver
from src.mqtt_manager import MqttManager
from src.serial_console import SerialConsole
from src.web_server import WebServer
from src.wifi_manager import WifiManager

CONFIG_MODE_FLAG_INDEX = 1
DOUBLE_RESET_MARKER_INDEX = 0
BOOT_SETTLE_SECONDS = 2.5


def _in_config_mode():
    try:
        return microcontroller.nvm[CONFIG_MODE_FLAG_INDEX] == 1
    except Exception:
        return False


def _clear_double_reset_marker():
    try:
        microcontroller.nvm[DOUBLE_RESET_MARKER_INDEX] = 0
    except Exception:
        pass


def _resolve_pin(name):
    return getattr(board, name)


system_cfg = settings_store.load("system.json")
dmx_driver = DmxDriver(
    _resolve_pin(system_cfg["dmx_tx_pin"]), _resolve_pin(system_cfg["dmx_dir_pin"])
)
device_manager = DeviceManager(dmx_driver)
wifi_manager = WifiManager()
mqtt_manager = MqttManager(device_manager)
serial_console = SerialConsole(device_manager, wifi_manager, mqtt_manager)

if _in_config_mode():
    wifi_manager.start_ap(system_cfg["ap_ssid"], system_cfg["ap_password"], system_cfg["ap_ip"])
else:
    # Short settle window: a reset during this delay is caught by boot.py on
    # the next boot as a double-tap and routes into config mode instead.
    time.sleep(BOOT_SETTLE_SECONDS)
    _clear_double_reset_marker()
    if not wifi_manager.connect_known():
        wifi_manager.start_ap(
            system_cfg["ap_ssid"], system_cfg["ap_password"], system_cfg["ap_ip"]
        )

pool = socketpool.SocketPool(wifi.radio)
web_server = WebServer(pool, device_manager, wifi_manager, mqtt_manager, dmx_driver)
web_server.start()

if wifi_manager.mode == "sta":
    mqtt_manager.start()

while True:
    web_server.poll()
    mqtt_manager.loop()
    dmx_driver.refresh_if_due()
    serial_console.poll()
