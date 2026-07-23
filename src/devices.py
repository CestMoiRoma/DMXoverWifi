import os

from . import settings_store

DMX_CHANNELS = 512
CHANNEL_TYPES = ("slider", "button")


def _new_id():
    return "dev-" + "".join("%02x" % b for b in os.urandom(3))


class Channel:
    def __init__(self, offset, name, type_):
        self.offset = int(offset)
        self.name = name
        self.type = type_ if type_ in CHANNEL_TYPES else "slider"

    def to_dict(self):
        return {"offset": self.offset, "name": self.name, "type": self.type}

    @classmethod
    def from_dict(cls, d):
        return cls(d["offset"], d.get("name", "Channel"), d.get("type", "slider"))


class Device:
    def __init__(self, id_, name, start_channel, channels):
        self.id = id_
        self.name = name
        self.start_channel = int(start_channel)
        self.channels = channels

    def address_for(self, channel):
        return self.start_channel + channel.offset - 1

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "start_channel": self.start_channel,
            "channels": [c.to_dict() for c in self.channels],
        }

    @classmethod
    def from_dict(cls, d):
        channels = [Channel.from_dict(c) for c in d.get("channels", [])]
        return cls(d["id"], d.get("name", "Device"), d.get("start_channel", 1), channels)


class DeviceManager:
    def __init__(self, dmx_driver):
        self.dmx_driver = dmx_driver
        self.devices = []
        self._load()

    def _load(self):
        raw = settings_store.load("devices.json")
        self.devices = [Device.from_dict(d) for d in raw]

    def _save(self):
        settings_store.save("devices.json", [d.to_dict() for d in self.devices])

    def find(self, device_id):
        for d in self.devices:
            if d.id == device_id:
                return d
        return None

    def add_device(self, name, start_channel, channels):
        device = Device(_new_id(), name, start_channel, [Channel.from_dict(c) for c in channels])
        self.devices.append(device)
        self._save()
        return device

    def update_device(self, device_id, name=None, start_channel=None, channels=None):
        device = self.find(device_id)
        if device is None:
            return None
        if name is not None:
            device.name = name
        if start_channel is not None:
            device.start_channel = int(start_channel)
        if channels is not None:
            device.channels = [Channel.from_dict(c) for c in channels]
        self._save()
        return device

    def remove_device(self, device_id):
        device = self.find(device_id)
        if device is None:
            return False
        self.devices.remove(device)
        self._save()
        return True

    def set_value(self, device_id, offset, value):
        device = self.find(device_id)
        if device is None:
            return None
        for channel in device.channels:
            if channel.offset == offset:
                address = device.address_for(channel)
                self.dmx_driver.set_channel(address, value)
                return channel
        return None
