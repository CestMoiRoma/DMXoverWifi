"""Fake `wifi` module.

`radio` models the parts of the real radio the firmware touches: joining a
station, falling back to an access point, and scanning. A test declares which
networks exist and with what password via `radio.set_environment()`, then the
firmware succeeds or fails the same way it would in the field.
"""


class Network:
    def __init__(self, ssid, rssi=-50, channel=1):
        self.ssid = ssid
        self.rssi = rssi
        self.channel = channel


class Radio:
    def __init__(self):
        self.reset()

    def reset(self):
        # ssid -> password. A network absent from this map cannot be joined,
        # which is how the AP fallback path gets exercised.
        self._environment = {}
        self.enabled = True
        self.connected_ssid = None
        self.ipv4_address = None
        self.ap_active = False
        self.ap_ssid = None
        self.ap_password = None
        self.ipv4_address_ap = None
        self.ap_info = None
        self.hostname = None
        self.scanning = False
        self.connect_calls = []
        self.ap_ipv4_config = None
        self.stop_station_calls = 0

    # -- test setup --

    def set_environment(self, networks):
        """networks: {ssid: password}. Password None means an open network."""
        self._environment = dict(networks)

    # -- the API WifiManager uses --

    def connect(self, ssid, password=None, timeout=8):
        self.connect_calls.append((ssid, password, timeout))
        if ssid not in self._environment:
            raise ConnectionError("No network with that ssid")
        if self._environment[ssid] not in (None, password):
            raise ConnectionError("Authentication failure")
        self.connected_ssid = ssid
        self.ipv4_address = "192.168.1.98"
        self.ap_info = Network(ssid)
        return None

    def start_ap(self, ssid, password=None, **kwargs):
        self.ap_active = True
        self.ap_ssid = ssid
        self.ap_password = password
        self.ipv4_address_ap = "192.168.4.1"

    def stop_ap(self):
        self.ap_active = False
        self.ap_ssid = None
        self.ipv4_address_ap = None

    def stop_station(self):
        self.stop_station_calls += 1
        self.connected_ssid = None
        self.ipv4_address = None
        self.ap_info = None

    def set_ipv4_address_ap(self, ipv4=None, netmask=None, gateway=None):
        self.ap_ipv4_config = (str(ipv4), str(netmask), str(gateway))
        self.ipv4_address_ap = str(ipv4)

    def start_scanning_networks(self):
        self.scanning = True
        return [Network(ssid, rssi=-40 - i) for i, ssid in enumerate(self._environment)]

    def stop_scanning_networks(self):
        self.scanning = False


radio = Radio()


def _reset_state():
    radio.reset()
