import ipaddress

import wifi

from . import settings_store

DEFAULT_AP_NETMASK = "255.255.255.0"


class WifiManager:
    def __init__(self):
        self.mode = None
        self.ap_ssid = None
        self.networks = settings_store.load("wifi_networks.json")

    def reload_networks(self):
        self.networks = settings_store.load("wifi_networks.json")

    def add_network(self, ssid, password, priority=0):
        self.networks = [n for n in self.networks if n["ssid"] != ssid]
        self.networks.append({"ssid": ssid, "password": password, "priority": priority})
        settings_store.save("wifi_networks.json", self.networks)

    def remove_network(self, ssid):
        before = len(self.networks)
        self.networks = [n for n in self.networks if n["ssid"] != ssid]
        settings_store.save("wifi_networks.json", self.networks)
        return len(self.networks) != before

    def scan(self):
        results = []
        try:
            for network in wifi.radio.start_scanning_networks():
                results.append({"ssid": network.ssid, "rssi": network.rssi})
            wifi.radio.stop_scanning_networks()
        except Exception:
            pass
        return results

    def connect_known(self, timeout=8):
        ordered = sorted(self.networks, key=lambda n: n.get("priority", 0), reverse=True)
        for net in ordered:
            if not net.get("ssid"):
                continue
            if self.try_connect(net["ssid"], net.get("password"), timeout=timeout):
                return True
        return False

    def try_connect(self, ssid, password, timeout=8):
        try:
            wifi.radio.connect(ssid, password or None, timeout=timeout)
            if wifi.radio.ipv4_address:
                self.mode = "sta"
                return True
        except Exception:
            pass
        return False

    def start_ap(self, ssid, password, ip):
        wifi.radio.stop_station()
        if password:
            wifi.radio.start_ap(ssid=ssid, password=password)
        else:
            wifi.radio.start_ap(ssid=ssid)
        try:
            address = ipaddress.IPv4Address(ip)
            netmask = ipaddress.IPv4Address(DEFAULT_AP_NETMASK)
            wifi.radio.set_ipv4_address_ap(ipv4=address, netmask=netmask, gateway=address)
        except Exception:
            pass
        self.mode = "ap"
        self.ap_ssid = ssid

    def status(self):
        info = {"mode": self.mode, "ssid": None, "ip": None}
        try:
            if self.mode == "sta":
                if wifi.radio.ap_info:
                    info["ssid"] = wifi.radio.ap_info.ssid
                if wifi.radio.ipv4_address:
                    info["ip"] = str(wifi.radio.ipv4_address)
            elif self.mode == "ap":
                info["ssid"] = self.ap_ssid
                if wifi.radio.ipv4_address_ap:
                    info["ip"] = str(wifi.radio.ipv4_address_ap)
        except Exception:
            pass
        return info
