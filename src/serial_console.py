import gc

import microcontroller
import storage
import usb_cdc

from . import settings_store

HELP_LINES = (
    "Add-Wifi ssid=<ssid> passwd=<password> [priority=<n>]",
    "Add-mqtt broker=<ip> user=<user> passwd=<password> [port=<n>]",
    "Set-System pin=<pin>                              - MAX485 direction pin (reboot to apply)",
    "Set-System hotspot name=<name> passwd=<password>  - AP ssid/password (reboot to apply)",
    "Set-System wifi-add ssid=<ssid> passwd=<password>[priority=<n>] - same as Add-Wifi",
    "Set-System wifi-del ssid=<ssid>                   - remove a saved network",
    "Set-System wifi-list                              - saved + visible networks",
    "Set-System mqtt-enable broker=<ip> user=<u> passwd=<p> [port=<n>] - same as Add-mqtt",
    "Set-System mqtt-disable                           - disable mqtt",
    "Set-System unlock-write                           - make filesystem PC-writable until"
    " reboot (recovery fallback; CircuitPython loses write access until next reboot)",
    "Set-device add name=<name>                        - add a device",
    "Set-device add-channel device=<name> name=<ch> channel=<offset> mode=<slider|bool>",
    "Set-device del-channel name=<ch> [device=<name>]  - remove a channel",
    "Set-device del device=<name>                      - remove a device",
    "get-status [all|wifi|mqtt|devices]",
    "get-status device name=<name>                     - channels of one device",
    "get-status channel channel=<ch> [device=<name>]   - one channel's value",
    "Help                                               - this message",
    "Reboot                                             - restart the board",
)


def _normalize_type(value):
    value = (value or "slider").strip().lower()
    if value in ("button", "btn", "bool", "boolean"):
        return "button"
    return "slider"


def _password_arg(args):
    for key in ("passwd", "psswd", "password"):
        if key in args:
            return args[key]
    return ""


class SerialConsole:
    def __init__(self, device_manager, wifi_manager, mqtt_manager):
        self.device_manager = device_manager
        self.wifi_manager = wifi_manager
        self.mqtt_manager = mqtt_manager
        self.serial = usb_cdc.console
        self._buffer = ""

        self._top_level = {
            "add-wifi": self._cmd_add_wifi,
            "add-mqtt": self._cmd_add_mqtt,
            "set-system": self._cmd_set_system,
            "set-device": self._cmd_set_device,
            "get-status": self._cmd_get_status,
            "help": self._cmd_help,
            "reboot": self._cmd_reboot,
        }
        self._set_system_subs = {
            "pin": self._sys_pin,
            "hotspot": self._sys_hotspot,
            "wifi-add": self._sys_wifi_add,
            "wifi-del": self._sys_wifi_del,
            "wifi-list": self._sys_wifi_list,
            "mqtt-enable": self._sys_mqtt_enable,
            "mqtt-disable": self._sys_mqtt_disable,
            "unlock-write": self._sys_unlock_write,
        }
        self._set_device_subs = {
            "add": self._dev_add,
            "add-channel": self._dev_add_channel,
            "del-channel": self._dev_del_channel,
            "del": self._dev_del,
        }
        self._get_status_subs = {
            "all": self._status_all,
            "wifi": self._status_wifi,
            "mqtt": self._status_mqtt,
            "devices": self._status_devices,
            "device": self._status_device,
            "channel": self._status_channel,
        }

    # -- I/O --

    def poll(self):
        if self.serial is None:
            return
        try:
            waiting = self.serial.in_waiting
        except Exception:
            return
        if not waiting:
            return
        try:
            chunk = self.serial.read(waiting)
            text = chunk.decode("utf-8")
        except Exception:
            return
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._handle_line(line.strip())

    def _write(self, text):
        try:
            self.serial.write((text + "\r\n").encode("utf-8"))
        except Exception:
            pass

    # -- parsing --

    @staticmethod
    def _tokenize(text):
        bare = []
        kwargs = {}
        for token in text.split():
            if "=" in token:
                key, _, value = token.partition("=")
                kwargs[key.strip().lower()] = value.strip()
            else:
                bare.append(token)
        return bare, kwargs

    def _sub_and_args(self, rest):
        bare, kwargs = self._tokenize(rest)
        if bare:
            return bare[0].lower(), kwargs
        if kwargs:
            return next(iter(kwargs)), kwargs
        return "", kwargs

    def _handle_line(self, line):
        if not line:
            return
        parts = line.split(None, 1)
        command = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        handler = self._top_level.get(command)
        if handler is None:
            self._write("ERR unknown command: %s (try Help)" % parts[0])
            return
        try:
            lines = handler(rest)
        except Exception as exc:
            self._write("ERR %s" % exc)
            return
        for out in lines or []:
            self._write("OK " + out)

    # -- top-level commands --

    def _cmd_add_wifi(self, rest):
        _, args = self._tokenize(rest)
        return [self._wifi_add(args)]

    def _cmd_add_mqtt(self, rest):
        _, args = self._tokenize(rest)
        return [self._mqtt_enable(args)]

    def _cmd_set_system(self, rest):
        sub, args = self._sub_and_args(rest)
        fn = self._set_system_subs.get(sub)
        if fn is None:
            raise ValueError("unknown Set-System subcommand: %s" % sub)
        result = fn(args)
        return [result] if isinstance(result, str) else result

    def _cmd_set_device(self, rest):
        sub, args = self._sub_and_args(rest)
        fn = self._set_device_subs.get(sub)
        if fn is None:
            raise ValueError("unknown Set-device subcommand: %s" % sub)
        result = fn(args)
        return [result] if isinstance(result, str) else result

    def _cmd_get_status(self, rest):
        sub, args = self._sub_and_args(rest)
        sub = sub or "all"
        fn = self._get_status_subs.get(sub)
        if fn is None:
            raise ValueError("unknown get-status subcommand: %s" % sub)
        return fn(args)

    def _cmd_help(self, rest):
        return list(HELP_LINES)

    def _cmd_reboot(self, rest):
        self._write("OK rebooting")
        microcontroller.reset()
        return []

    # -- wifi / mqtt (shared by Add-* and Set-System subcommands) --

    def _wifi_add(self, args):
        ssid = args.get("ssid")
        if not ssid:
            raise ValueError("ssid required")
        password = _password_arg(args)
        priority = int(args.get("priority", 0))
        self.wifi_manager.add_network(ssid, password, priority)
        connected = self.wifi_manager.try_connect(ssid, password)
        return "wifi '%s' saved%s" % (ssid, " and connected" if connected else "")

    def _mqtt_enable(self, args):
        broker = args.get("broker")
        if not broker:
            raise ValueError("broker required")
        cfg = {
            "enabled": True,
            "host": broker,
            "username": args.get("user", ""),
            "password": _password_arg(args),
        }
        if "port" in args:
            cfg["port"] = int(args["port"])
        self.mqtt_manager.set_config(cfg)
        self.mqtt_manager.start()
        return "mqtt enabled, broker=%s" % broker

    def _mqtt_disable(self, args):
        self.mqtt_manager.set_config({"enabled": False})
        self.mqtt_manager.stop()
        return "mqtt disabled"

    # -- Set-System subcommands --

    def _sys_pin(self, args):
        pin = args.get("pin")
        if not pin:
            raise ValueError("pin required, e.g. pin=D9")
        cfg = settings_store.load("system.json")
        cfg["dmx_dir_pin"] = pin
        settings_store.save("system.json", cfg)
        return "dmx direction pin set to '%s' (reboot to apply)" % pin

    def _sys_hotspot(self, args):
        cfg = settings_store.load("system.json")
        if "name" in args:
            cfg["ap_ssid"] = args["name"]
        if any(k in args for k in ("passwd", "psswd", "password")):
            cfg["ap_password"] = _password_arg(args)
        settings_store.save("system.json", cfg)
        return "hotspot set to ssid='%s' (reboot to apply)" % cfg["ap_ssid"]

    def _sys_wifi_add(self, args):
        return self._wifi_add(args)

    def _sys_wifi_del(self, args):
        ssid = args.get("ssid")
        if not ssid:
            raise ValueError("ssid required")
        removed = self.wifi_manager.remove_network(ssid)
        return "wifi '%s' removed" % ssid if removed else "wifi '%s' not found" % ssid

    def _sys_wifi_list(self, args):
        lines = ["visible networks:"]
        for net in self.wifi_manager.scan():
            lines.append("  %s (rssi %s)" % (net["ssid"], net["rssi"]))
        lines.append("saved networks:")
        for net in self.wifi_manager.networks:
            lines.append("  %s (priority %s)" % (net["ssid"], net.get("priority", 0)))
        if not self.wifi_manager.networks:
            lines.append("  (none saved)")
        return lines

    def _sys_mqtt_enable(self, args):
        return self._mqtt_enable(args)

    def _sys_mqtt_disable(self, args):
        return self._mqtt_disable(args)

    def _sys_unlock_write(self, args):
        storage.remount("/", readonly=True)
        return (
            "filesystem is now PC-writable; CircuitPython can no longer save config "
            "until the next reboot"
        )

    # -- Set-device subcommands --

    def _dev_add(self, args):
        name = args.get("name")
        if not name:
            raise ValueError("name required")
        start = self.device_manager.next_free_start_channel()
        self.device_manager.add_device(name, start, [])
        return "device '%s' added (start channel %d)" % (name, start)

    def _dev_add_channel(self, args):
        device_name = args.get("device")
        channel_name = args.get("name")
        offset = args.get("channel")
        if not (device_name and channel_name and offset):
            raise ValueError("device=, name= and channel= required")
        type_ = _normalize_type(args.get("mode"))
        _, channel = self.device_manager.add_channel(
            device_name, channel_name, int(offset), type_
        )
        self.mqtt_manager.publish_discovery()
        return "channel '%s' added to '%s' (offset %d, %s)" % (
            channel_name,
            device_name,
            channel.offset,
            channel.type,
        )

    def _dev_del_channel(self, args):
        name = args.get("name")
        if not name:
            raise ValueError("name required")
        device = self.device_manager.remove_channel_by_name(name, args.get("device"))
        self.mqtt_manager.publish_discovery()
        return "channel '%s' removed from '%s'" % (name, device.name)

    def _dev_del(self, args):
        name = args.get("device")
        if not name:
            raise ValueError("device required")
        removed = self.device_manager.remove_device_by_name(name)
        return "device '%s' removed" % name if removed else "device '%s' not found" % name

    # -- get-status subcommands --

    def _status_all(self, args):
        lines = []
        w = self.wifi_manager.status()
        lines.append("wifi: mode=%s ssid=%s ip=%s" % (w["mode"], w["ssid"], w["ip"]))
        m = self.mqtt_manager.status()
        lines.append(
            "mqtt: enabled=%s connected=%s broker=%s" % (m["enabled"], m["connected"], m["broker"])
        )
        system_cfg = settings_store.load("system.json")
        lines.append(
            "system: hostname=%s tx_pin=%s dir_pin=%s"
            % (system_cfg["hostname"], system_cfg["dmx_tx_pin"], system_cfg["dmx_dir_pin"])
        )
        device_count = len(self.device_manager.devices)
        channel_count = sum(len(d.channels) for d in self.device_manager.devices)
        lines.append("devices: %d device(s), %d channel(s)" % (device_count, channel_count))
        lines.append("memory: %d bytes free" % gc.mem_free())
        return lines

    def _status_wifi(self, args):
        w = self.wifi_manager.status()
        return ["wifi: mode=%s ssid=%s ip=%s" % (w["mode"], w["ssid"], w["ip"])]

    def _status_mqtt(self, args):
        m = self.mqtt_manager.status()
        return [
            "mqtt: enabled=%s connected=%s broker=%s" % (m["enabled"], m["connected"], m["broker"])
        ]

    def _status_devices(self, args):
        if not self.device_manager.devices:
            return ["(no devices configured)"]
        return [
            "%s: start=%d channels=%d" % (d.name, d.start_channel, len(d.channels))
            for d in self.device_manager.devices
        ]

    def _status_device(self, args):
        name = args.get("name")
        if not name:
            raise ValueError("name required")
        device = self.device_manager.find_by_name(name)
        if device is None:
            raise ValueError("no device named '%s'" % name)
        if not device.channels:
            return ["%s has no channels" % name]
        return [
            "  %d: %s (%s) = %d"
            % (c.offset, c.name, c.type, self.device_manager.get_value(device, c))
            for c in device.channels
        ]

    def _status_channel(self, args):
        name = args.get("channel")
        if not name:
            raise ValueError("channel required")
        matches = self.device_manager.find_channels_by_name(name, args.get("device"))
        if not matches:
            raise ValueError("no channel named '%s'" % name)
        return [
            "%s/%s: offset=%d mode=%s value=%d"
            % (d.name, c.name, c.offset, c.type, self.device_manager.get_value(d, c))
            for d, c in matches
        ]
