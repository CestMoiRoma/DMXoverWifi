import json

import socketpool
import wifi
from adafruit_minimqtt import adafruit_minimqtt as MQTT

from . import settings_store


class MqttManager:
    def __init__(self, device_manager):
        self.device_manager = device_manager
        self.cfg = settings_store.load("mqtt.json")
        self.client = None

    def reload_config(self):
        self.cfg = settings_store.load("mqtt.json")

    def set_config(self, cfg):
        self.cfg.update(cfg)
        settings_store.save("mqtt.json", self.cfg)

    def start(self):
        self.stop()
        if not self.cfg.get("enabled") or not self.cfg.get("host"):
            return
        pool = socketpool.SocketPool(wifi.radio)
        self.client = MQTT.MQTT(
            broker=self.cfg["host"],
            port=self.cfg.get("port", 1883),
            username=self.cfg.get("username") or None,
            password=self.cfg.get("password") or None,
            socket_pool=pool,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        try:
            self.client.connect()
        except Exception:
            self.client = None

    def stop(self):
        if self.client is not None:
            try:
                self.client.disconnect()
            except Exception:
                pass
            self.client = None

    def _base_topic(self):
        return self.cfg.get("base_topic", "dmxwifi")

    def _discovery_prefix(self):
        return self.cfg.get("discovery_prefix", "homeassistant")

    def _uid(self, device_id, offset):
        return "%s_%d" % (device_id, offset)

    def _on_connect(self, client, userdata, flags, rc):
        self.publish_discovery()

    def publish_discovery(self):
        if self.client is None:
            return
        for device in self.device_manager.devices:
            device_block = {
                "identifiers": [device.id],
                "name": device.name,
                "manufacturer": "DIY",
                "model": "DMX-over-WiFi",
            }
            for channel in device.channels:
                uid = self._uid(device.id, channel.offset)
                command_topic = "%s/%s/set" % (self._base_topic(), uid)
                config_topic = None
                payload = None
                if channel.type == "slider":
                    state_topic = "%s/%s/state" % (self._base_topic(), uid)
                    payload = {
                        "name": channel.name,
                        "unique_id": uid,
                        "command_topic": command_topic,
                        "state_topic": state_topic,
                        "min": 0,
                        "max": 255,
                        "step": 1,
                        "device": device_block,
                    }
                    config_topic = "%s/number/%s/config" % (self._discovery_prefix(), uid)
                else:
                    payload = {
                        "name": channel.name,
                        "unique_id": uid,
                        "command_topic": command_topic,
                        "device": device_block,
                    }
                    config_topic = "%s/button/%s/config" % (self._discovery_prefix(), uid)
                try:
                    self.client.publish(config_topic, json.dumps(payload), retain=True)
                    self.client.subscribe(command_topic)
                except Exception:
                    pass

    def _on_message(self, client, topic, message):
        try:
            prefix = self._base_topic() + "/"
            if not topic.startswith(prefix) or not topic.endswith("/set"):
                return
            uid = topic[len(prefix):-len("/set")]
            device_id, offset_str = uid.rsplit("_", 1)
            offset = int(offset_str)
        except (ValueError, IndexError):
            return

        channel = None
        for device in self.device_manager.devices:
            if device.id == device_id:
                for c in device.channels:
                    if c.offset == offset:
                        channel = c
                        break
                break
        if channel is None:
            return

        if channel.type == "button":
            value = 255
        else:
            try:
                value = int(float(message))
            except ValueError:
                return

        self.device_manager.set_value(device_id, offset, value)
        if channel.type == "slider":
            self.publish_state(device_id, offset, value)

    def publish_state(self, device_id, offset, value):
        if self.client is None:
            return
        state_topic = "%s/%s/state" % (self._base_topic(), self._uid(device_id, offset))
        try:
            self.client.publish(state_topic, str(value))
        except Exception:
            pass

    def loop(self):
        if self.client is None:
            return
        try:
            self.client.loop(timeout=0.01)
        except Exception:
            self.client = None
