from adafruit_httpserver import DELETE, GET, POST, PUT, FileResponse, JSONResponse, Server

from . import settings_store


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
