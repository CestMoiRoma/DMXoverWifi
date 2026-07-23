from adafruit_httpserver import (
    DELETE, GET, POST, PUT,
    FileResponse, JSONResponse, Response, Server,
)

from . import settings_store
from .version import VERSION

_REPO_URL = "https://github.com/CestMoiRoma/DMXoverWifi"
_INFO = {
    "version": VERSION,
    "author": {"name": "CestMoiRoma", "url": "https://github.com/CestMoiRoma"},
    "repo": _REPO_URL,
    "wiki_online": _REPO_URL + "/blob/main/WIKI.md",
    "wiki_local": "/wiki.md",
}


class WebServer:
    def __init__(self, pool, device_manager, wifi_manager, mqtt_manager, dmx_driver):
        self.device_manager = device_manager
        self.wifi_manager = wifi_manager
        self.mqtt_manager = mqtt_manager
        self.dmx_driver = dmx_driver
        self.server = Server(pool, "/www", debug=False)
        self._register_routes()

    def _register_routes(self):
        s = self.server
        s.route("/", GET)(self._index)
        s.route("/wiki.md", GET)(self._serve_wiki)
        s.route("/api/devices", GET)(self._list_devices)
        s.route("/api/devices", POST)(self._create_device)
        s.route("/api/devices/<device_id>", PUT)(self._update_device)
        s.route("/api/devices/<device_id>", DELETE)(self._delete_device)
        s.route("/api/devices/<device_id>/channel/<offset>", POST)(self._set_channel)
        s.route("/api/wifi", GET)(self._get_wifi)
        s.route("/api/wifi", POST)(self._add_wifi)
        s.route("/api/wifi/<ssid>", DELETE)(self._delete_wifi)
        s.route("/api/wifi/scan", GET)(self._scan_wifi)
        s.route("/api/mqtt", GET)(self._get_mqtt)
        s.route("/api/mqtt", POST)(self._set_mqtt)
        s.route("/api/system", GET)(self._get_system)
        s.route("/api/system", POST)(self._set_system)
        s.route("/api/mesh", GET)(self._get_mesh)
        s.route("/api/mesh", POST)(self._set_mesh)
        s.route("/api/info", GET)(self._get_info)
        s.route("/api/export-env", GET)(self._export_env)

    def start(self, port=80):
        self.server.start("0.0.0.0", port=port)

    def poll(self):
        try:
            self.server.poll()
        except OSError:
            pass

    # -- pages / static --

    def _index(self, request):
        return FileResponse(request, "index.html")

    def _serve_wiki(self, request):
        return FileResponse(request, "wiki.md", content_type="text/plain")

    # -- devices --

    def _list_devices(self, request):
        return JSONResponse(request, [d.to_dict() for d in self.device_manager.devices])

    def _create_device(self, request):
        data = request.json()
        device = self.device_manager.add_device(
            data["name"], data.get("start_channel", 1), data.get("channels", [])
        )
        self.mqtt_manager.publish_discovery()
        return JSONResponse(request, device.to_dict())

    def _update_device(self, request, device_id):
        data = request.json()
        device = self.device_manager.update_device(
            device_id,
            name=data.get("name"),
            start_channel=data.get("start_channel"),
            channels=data.get("channels"),
        )
        if device is None:
            return JSONResponse(request, {"error": "not found"}, status=(404, "Not Found"))
        self.mqtt_manager.publish_discovery()
        return JSONResponse(request, device.to_dict())

    def _delete_device(self, request, device_id):
        ok = self.device_manager.remove_device(device_id)
        return JSONResponse(request, {"ok": ok})

    def _set_channel(self, request, device_id, offset):
        data = request.json()
        value = data.get("value", 0)
        channel = self.device_manager.set_value(device_id, int(offset), value)
        if channel is None:
            return JSONResponse(request, {"error": "not found"}, status=(404, "Not Found"))
        self.mqtt_manager.publish_state(device_id, int(offset), value)
        return JSONResponse(request, {"ok": True})

    # -- wifi --

    def _get_wifi(self, request):
        return JSONResponse(request, self.wifi_manager.networks)

    def _add_wifi(self, request):
        data = request.json()
        self.wifi_manager.add_network(
            data["ssid"], data.get("password", ""), data.get("priority", 0)
        )
        return JSONResponse(request, self.wifi_manager.networks)

    def _delete_wifi(self, request, ssid):
        self.wifi_manager.remove_network(ssid)
        return JSONResponse(request, self.wifi_manager.networks)

    def _scan_wifi(self, request):
        return JSONResponse(request, self.wifi_manager.scan())

    # -- mqtt --

    def _get_mqtt(self, request):
        return JSONResponse(request, self.mqtt_manager.cfg)

    def _set_mqtt(self, request):
        data = request.json()
        self.mqtt_manager.set_config(data)
        self.mqtt_manager.start()
        return JSONResponse(request, self.mqtt_manager.cfg)

    # -- system --

    def _get_system(self, request):
        return JSONResponse(request, settings_store.load("system.json"))

    def _set_system(self, request):
        data = request.json()
        cfg = settings_store.load("system.json")
        cfg.update(data)
        settings_store.save("system.json", cfg)
        return JSONResponse(request, cfg)

    # -- mesh (WIP, stored only) --

    def _get_mesh(self, request):
        return JSONResponse(request, settings_store.load("mesh.json"))

    def _set_mesh(self, request):
        data = request.json()
        cfg = settings_store.load("mesh.json")
        cfg.update(data)
        settings_store.save("mesh.json", cfg)
        return JSONResponse(request, cfg)

    # -- info / credits --

    def _get_info(self, request):
        return JSONResponse(request, _INFO)

    # -- export current config as .env text (downloadable) --

    def _export_env(self, request):
        body = _build_env_text()
        headers = {"Content-Disposition": "attachment; filename=config.env"}
        return Response(request, body, content_type="text/plain", headers=headers)


def _bool_env(value):
    return "true" if value else "false"


def _build_env_text():
    lines = []
    lines.append("# Exported from the running board. Drop next to tools/deploy.py as .env")
    lines.append("")

    wifi = settings_store.load("wifi_networks.json")
    if wifi:
        lines.append("# --- WiFi networks ---")
        for i, net in enumerate(wifi, 1):
            lines.append("WIFI_%d_SSID=%s" % (i, net.get("ssid", "")))
            lines.append("WIFI_%d_PASSWORD=%s" % (i, net.get("password", "")))
            lines.append("WIFI_%d_PRIORITY=%d" % (i, int(net.get("priority", 0) or 0)))
            lines.append("")

    mqtt = settings_store.load("mqtt.json")
    lines.append("# --- MQTT ---")
    lines.append("MQTT_ENABLED=%s" % _bool_env(mqtt.get("enabled")))
    lines.append("MQTT_HOST=%s" % mqtt.get("host", ""))
    lines.append("MQTT_PORT=%d" % int(mqtt.get("port", 1883) or 1883))
    lines.append("MQTT_USERNAME=%s" % mqtt.get("username", ""))
    lines.append("MQTT_PASSWORD=%s" % mqtt.get("password", ""))
    lines.append("MQTT_BASE_TOPIC=%s" % mqtt.get("base_topic", ""))
    lines.append("MQTT_DISCOVERY_PREFIX=%s" % mqtt.get("discovery_prefix", ""))
    lines.append("")

    system = settings_store.load("system.json")
    lines.append("# --- System / DMX / hotspot / static IP ---")
    lines.append("DMX_TX_PIN=%s" % system.get("dmx_tx_pin", ""))
    lines.append("DMX_DIR_PIN_ENABLED=%s" % _bool_env(system.get("dmx_dir_pin_enabled")))
    lines.append("DMX_DIR_PIN=%s" % system.get("dmx_dir_pin", ""))
    lines.append("HOSTNAME=%s" % system.get("hostname", ""))
    lines.append("AP_SSID=%s" % system.get("ap_ssid", ""))
    lines.append("AP_PASSWORD=%s" % system.get("ap_password", ""))
    lines.append("AP_IP=%s" % system.get("ap_ip", ""))
    lines.append("STA_IP_MODE=%s" % system.get("sta_ip_mode", "dhcp"))
    lines.append("STA_STATIC_IP=%s" % system.get("sta_static_ip", ""))
    lines.append("STA_STATIC_NETMASK=%s" % system.get("sta_static_netmask", ""))
    lines.append("STA_STATIC_GATEWAY=%s" % system.get("sta_static_gateway", ""))
    lines.append("STA_STATIC_DNS=%s" % system.get("sta_static_dns", ""))
    lines.append("")

    mesh = settings_store.load("mesh.json")
    lines.append("# --- Parent/Child mesh (WIP) ---")
    lines.append("MESH_ROLE=%s" % mesh.get("role", "none"))
    lines.append("MESH_SSID=%s" % mesh.get("ssid", ""))
    lines.append("MESH_PASSWORD=%s" % mesh.get("password", ""))
    lines.append("")

    devices = settings_store.load("devices.json")
    if devices:
        lines.append("# --- Devices ---")
        for i, dev in enumerate(devices, 1):
            lines.append("DEVICE_%d_NAME=%s" % (i, dev.get("name", "")))
            lines.append("DEVICE_%d_START_CHANNEL=%d" % (i, int(dev.get("start_channel", 1))))
            for j, ch in enumerate(dev.get("channels", []), 1):
                lines.append("DEVICE_%d_CHANNEL_%d_OFFSET=%d" % (i, j, int(ch.get("offset", j))))
                lines.append("DEVICE_%d_CHANNEL_%d_NAME=%s" % (i, j, ch.get("name", "")))
                lines.append("DEVICE_%d_CHANNEL_%d_TYPE=%s" % (i, j, ch.get("type", "slider")))
            lines.append("")

    return "\n".join(lines) + "\n"
