"""Fake `adafruit_minimqtt.adafruit_minimqtt`.

Records what the firmware published and subscribed to, and lets a test push a
broker message back in:

    client = MQTT.last_instance
    client.inject("dmxwifi/dev-abc123_1/set", "128")

Set `MQTT.fail_connect = True` to simulate an unreachable broker, which is the
path `MqttManager.start()` has to swallow.
"""


class MMQTTException(Exception):
    pass


class MQTT:
    # Class-level test switches.
    fail_connect = False
    last_instance = None
    instances = []

    def __init__(
        self,
        broker=None,
        port=1883,
        username=None,
        password=None,
        socket_pool=None,
        ssl_context=None,
        client_id=None,
        keep_alive=60,
    ):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.socket_pool = socket_pool
        self.client_id = client_id

        self.on_connect = None
        self.on_message = None
        self.on_disconnect = None

        self._connected = False
        self.published = []
        self.subscriptions = []
        self.loop_calls = 0
        self.connect_calls = 0
        self.disconnect_calls = 0

        MQTT.last_instance = self
        MQTT.instances.append(self)

    def connect(self, clean_session=True, host=None, port=None, keep_alive=None):
        self.connect_calls += 1
        if MQTT.fail_connect:
            raise MMQTTException("failed to connect to %s" % self.broker)
        self._connected = True
        if self.on_connect:
            self.on_connect(self, None, 0, 0)
        return 0

    def disconnect(self):
        self.disconnect_calls += 1
        if not self._connected:
            raise MMQTTException("not connected")
        self._connected = False

    def is_connected(self):
        return self._connected

    def publish(self, topic, msg, retain=False, qos=0):
        if not self._connected:
            raise MMQTTException("not connected")
        self.published.append({"topic": topic, "payload": msg, "retain": retain})

    def subscribe(self, topic, qos=0):
        if not self._connected:
            raise MMQTTException("not connected")
        self.subscriptions.append(topic)

    def loop(self, timeout=0):
        self.loop_calls += 1

    # -- test helpers --

    def inject(self, topic, message):
        """Deliver a broker message to the firmware's on_message callback."""
        if self.on_message is None:
            raise AssertionError("firmware never registered an on_message handler")
        self.on_message(self, topic, message)

    def published_to(self, topic):
        return [p for p in self.published if p["topic"] == topic]

    def retained(self):
        return [p for p in self.published if p["retain"]]


def _reset_state():
    MQTT.fail_connect = False
    MQTT.last_instance = None
    MQTT.instances = []
