#!/usr/bin/env python3
"""Serve www/ backed by a fake API, so the web UI can be exercised off the board.

The real firmware answers /api/* from CircuitPython. This reimplements just
enough of that contract on a desktop Python http.server, seeded with demo
fixtures, so the UI can be screenshotted and click-tested without hardware and
without touching anyone's live rig.

The seed data deliberately covers every channel type the UI knows how to render.

    python test/ui/mock_server.py --port 8000

Run it directly to poke at the UI in a browser, or let screenshot_ui.py start it.
"""
import argparse
import json
import re
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WWW_DIR = REPO_ROOT / "www"


def seed_state():
    """Fresh demo data. Called per server so runs cannot bleed into each other."""
    return {
        "devices": [
            {
                "id": "dev-a1b2c3",
                "name": "PAR LED",
                "start_channel": 1,
                "channels": [
                    {"offset": 1, "name": "Dimmer", "type": "slider"},
                    {"offset": 2, "name": "Red", "type": "slider"},
                    {"offset": 3, "name": "Green", "type": "slider"},
                    {"offset": 4, "name": "Blue", "type": "slider"},
                ],
            },
            {
                "id": "dev-d4e5f6",
                "name": "Smoke machine",
                "start_channel": 10,
                "channels": [
                    {"offset": 1, "name": "Fog burst", "type": "button"},
                    {"offset": 2, "name": "Blast", "type": "button-momentary"},
                    {"offset": 3, "name": "Heater", "type": "button-switch"},
                ],
            },
        ],
        "wifi": [
            {"ssid": "StageNet", "password": "stage-secret", "priority": 10},
            {"ssid": "BackupHotspot", "password": "backup", "priority": 1},
        ],
        "scan": [
            {"ssid": "StageNet", "rssi": -42},
            {"ssid": "BackupHotspot", "rssi": -67},
            {"ssid": "GuestWifi", "rssi": -78},
        ],
        "mqtt": {
            "enabled": True,
            "host": "192.168.1.20",
            "port": 1883,
            "username": "dmx",
            "password": "broker-secret",
            "base_topic": "dmxwifi",
            "discovery_prefix": "homeassistant",
        },
        "system": {
            "dmx_tx_pin": "D4",
            "dmx_dir_pin_enabled": False,
            "dmx_dir_pin": "D3",
            "hostname": "ESP-DMX",
            "ap_ssid": "ESP-DMX",
            "ap_password": "DMX4ALL1",
            "ap_ip": "1.1.1.1",
            "sta_ip_mode": "dhcp",
            "sta_static_ip": "",
            "sta_static_netmask": "255.255.255.0",
            "sta_static_gateway": "",
            "sta_static_dns": "1.1.1.1",
        },
        "mesh": {"role": "none", "ssid": "", "password": ""},
        "info": {
            "version": read_version(),
            "author": {"name": "CestMoiRoma", "url": "https://github.com/CestMoiRoma"},
            "repo": "https://github.com/CestMoiRoma/DMXoverWifi",
            "wiki_online": "https://github.com/CestMoiRoma/DMXoverWifi/blob/main/WIKI.md",
            "wiki_local": "/wiki.md",
        },
        # Every channel write the UI performed, so a test can assert on them.
        "channel_writes": [],
    }


def read_version():
    text = (REPO_ROOT / "src" / "version.py").read_text()
    match = re.search(r'VERSION\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "unknown"


class MockHandler(SimpleHTTPRequestHandler):
    state = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WWW_DIR), **kwargs)

    def log_message(self, fmt, *args):
        pass  # keep the test output readable

    # -- helpers --

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _find_device(self, device_id):
        for device in self.state["devices"]:
            if device["id"] == device_id:
                return device
        return None

    def _env_download(self):
        """Mirror of the firmware's /api/export-env, down to the headers.

        Same key names and the same ordering as src/web_server.py, so a browser
        test that checks the download here is checking the real contract.
        """
        state = self.state
        lines = ["# Exported from the running board. Drop next to tools/deploy.py as .env", ""]

        if state["wifi"]:
            lines.append("# --- WiFi networks ---")
            for i, net in enumerate(state["wifi"], 1):
                lines.append("WIFI_%d_SSID=%s" % (i, net["ssid"]))
                lines.append("WIFI_%d_PASSWORD=%s" % (i, net.get("password", "")))
                lines.append("WIFI_%d_PRIORITY=%d" % (i, net.get("priority", 0)))
                lines.append("")

        mqtt = state["mqtt"]
        lines.append("# --- MQTT ---")
        lines.append("MQTT_ENABLED=%s" % ("true" if mqtt["enabled"] else "false"))
        for key, env_key in (
            ("host", "MQTT_HOST"),
            ("port", "MQTT_PORT"),
            ("username", "MQTT_USERNAME"),
            ("password", "MQTT_PASSWORD"),
            ("base_topic", "MQTT_BASE_TOPIC"),
            ("discovery_prefix", "MQTT_DISCOVERY_PREFIX"),
        ):
            lines.append("%s=%s" % (env_key, mqtt.get(key, "")))
        lines.append("")

        system = state["system"]
        lines.append("# --- System / DMX / hotspot / static IP ---")
        for env_key, key in (
            ("DMX_TX_PIN", "dmx_tx_pin"),
            ("DMX_DIR_PIN_ENABLED", "dmx_dir_pin_enabled"),
            ("DMX_DIR_PIN", "dmx_dir_pin"),
            ("HOSTNAME", "hostname"),
            ("AP_SSID", "ap_ssid"),
            ("AP_PASSWORD", "ap_password"),
            ("AP_IP", "ap_ip"),
            ("STA_IP_MODE", "sta_ip_mode"),
            ("STA_STATIC_IP", "sta_static_ip"),
            ("STA_STATIC_NETMASK", "sta_static_netmask"),
            ("STA_STATIC_GATEWAY", "sta_static_gateway"),
            ("STA_STATIC_DNS", "sta_static_dns"),
        ):
            value = system.get(key, "")
            if isinstance(value, bool):
                value = "true" if value else "false"
            lines.append("%s=%s" % (env_key, value))
        lines.append("")

        mesh = state["mesh"]
        lines.append("# --- Parent/Child mesh (WIP) ---")
        lines.append("MESH_ROLE=%s" % mesh.get("role", "none"))
        lines.append("MESH_SSID=%s" % mesh.get("ssid", ""))
        lines.append("MESH_PASSWORD=%s" % mesh.get("password", ""))
        lines.append("")

        if state["devices"]:
            lines.append("# --- Devices ---")
            for i, dev in enumerate(state["devices"], 1):
                lines.append("DEVICE_%d_NAME=%s" % (i, dev["name"]))
                lines.append("DEVICE_%d_START_CHANNEL=%d" % (i, dev["start_channel"]))
                for j, ch in enumerate(dev.get("channels", []), 1):
                    lines.append("DEVICE_%d_CHANNEL_%d_OFFSET=%d" % (i, j, ch["offset"]))
                    lines.append("DEVICE_%d_CHANNEL_%d_NAME=%s" % (i, j, ch["name"]))
                    lines.append("DEVICE_%d_CHANNEL_%d_TYPE=%s" % (i, j, ch["type"]))
                lines.append("")

        body = ("\n".join(lines) + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Disposition", "attachment; filename=config.env")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- routing --

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/devices":
            return self._json(self.state["devices"])
        if path == "/api/wifi":
            return self._json(self.state["wifi"])
        if path == "/api/wifi/scan":
            return self._json(self.state["scan"])
        if path == "/api/mqtt":
            return self._json(self.state["mqtt"])
        if path == "/api/system":
            return self._json(self.state["system"])
        if path == "/api/mesh":
            return self._json(self.state["mesh"])
        if path == "/api/info":
            return self._json(self.state["info"])
        if path == "/api/export-env":
            return self._env_download()
        if path == "/wiki.md":
            self.path = "/wiki.md"
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._body()

        channel = re.match(r"^/api/devices/([^/]+)/channel/(\d+)$", path)
        if channel:
            device_id, offset = channel.group(1), int(channel.group(2))
            device = self._find_device(device_id)
            if device is None:
                return self._json({"error": "not found"}, status=404)
            self.state["channel_writes"].append(
                {"device": device_id, "offset": offset, "value": body.get("value", 0)}
            )
            return self._json({"ok": True})

        if path == "/api/devices":
            device = {
                "id": "dev-%06x" % (len(self.state["devices"]) + 0xC0FFEE),
                "name": body.get("name", "Device"),
                "start_channel": body.get("start_channel", 1),
                "channels": body.get("channels", []),
            }
            self.state["devices"].append(device)
            return self._json(device)

        if path == "/api/wifi":
            self.state["wifi"] = [n for n in self.state["wifi"] if n["ssid"] != body["ssid"]]
            self.state["wifi"].append(
                {
                    "ssid": body["ssid"],
                    "password": body.get("password", ""),
                    "priority": body.get("priority", 0),
                }
            )
            return self._json(self.state["wifi"])

        for key in ("mqtt", "system", "mesh"):
            if path == "/api/" + key:
                self.state[key].update(body)
                return self._json(self.state[key])

        return self._json({"error": "no route"}, status=404)

    def do_PUT(self):
        match = re.match(r"^/api/devices/([^/]+)$", self.path.split("?")[0])
        if not match:
            return self._json({"error": "no route"}, status=404)
        device = self._find_device(match.group(1))
        if device is None:
            return self._json({"error": "not found"}, status=404)
        device.update({k: v for k, v in self._body().items() if v is not None})
        return self._json(device)

    def do_DELETE(self):
        path = self.path.split("?")[0]

        match = re.match(r"^/api/devices/([^/]+)$", path)
        if match:
            before = len(self.state["devices"])
            self.state["devices"] = [
                d for d in self.state["devices"] if d["id"] != match.group(1)
            ]
            return self._json({"ok": len(self.state["devices"]) != before})

        match = re.match(r"^/api/wifi/(.+)$", path)
        if match:
            from urllib.parse import unquote

            ssid = unquote(match.group(1))
            self.state["wifi"] = [n for n in self.state["wifi"] if n["ssid"] != ssid]
            return self._json(self.state["wifi"])

        return self._json({"error": "no route"}, status=404)


def make_server(port=0, state=None):
    """Return (server, state). Port 0 lets the OS pick a free one."""
    handler_state = state if state is not None else seed_state()
    handler = type("BoundMockHandler", (MockHandler,), {"state": handler_state})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    return server, handler_state


def serve_in_background(port=0, state=None):
    """Start the mock server on a daemon thread. Returns (server, state, url)."""
    server, handler_state = make_server(port, state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, handler_state, "http://127.0.0.1:%d" % server.server_address[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if not WWW_DIR.is_dir():
        print("www/ not found at %s" % WWW_DIR, file=sys.stderr)
        return 1

    server, _ = make_server(args.port)
    url = "http://127.0.0.1:%d" % server.server_address[1]
    print("Mock DMX board serving the web UI at %s" % url)
    print("Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
