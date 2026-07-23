#!/usr/bin/env python3
"""
Copy firmware source (boot.py, code.py, src/, www/, lib/) onto the
board's CIRCUITPY drive. Does not touch data/ (runtime config) on the
target.

If the target drive is read-only (normal boot state), the script will:
  1. Ask which serial port the board is on (or accept --port).
  2. Eject the drive from the host OS.
  3. Send "Set-System reboot-config" to trigger a reset into config
     mode (host-writable filesystem).
  4. Wait for the drive to re-appear as writable, then copy files.
  5. Send "Reboot" so the board comes back up in normal (STA) mode.

Requires pyserial for the auto-unlock path (only imported when needed):
    pip install pyserial

Usage:
    python tools/deploy.py [TARGET] [--port PORT]

If TARGET or --port are omitted, you'll be prompted.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ITEMS = ("boot.py", "code.py", "src", "www", "lib")


def prompt_target():
    if sys.platform == "win32":
        hint = "e.g. E:\\ or L:\\"
    elif sys.platform == "darwin":
        hint = "e.g. /Volumes/CIRCUITPY"
    else:
        hint = "e.g. /media/$USER/CIRCUITPY or /run/media/$USER/CIRCUITPY"
    answer = input("Path to the CIRCUITPY drive (%s): " % hint).strip()
    if not answer:
        print("No target provided.", file=sys.stderr)
        sys.exit(1)
    return answer


def prompt_port():
    try:
        from serial.tools import list_ports
    except ImportError:
        answer = input(
            "Serial port (e.g. COM9 / /dev/ttyACM0 / /dev/tty.usbmodem*): "
        ).strip()
        if not answer:
            print("No port provided.", file=sys.stderr)
            sys.exit(1)
        return answer

    ports = list(list_ports.comports())
    if ports:
        print("Detected serial ports:")
        for i, p in enumerate(ports, 1):
            desc = (" - " + p.description) if p.description else ""
            print("  %d. %s%s" % (i, p.device, desc))
        answer = input("Pick a number, or type a device path: ").strip()
        if answer.isdigit():
            idx = int(answer) - 1
            if 0 <= idx < len(ports):
                return ports[idx].device
        if answer:
            return answer
    else:
        answer = input(
            "Serial port (e.g. COM9 / /dev/ttyACM0 / /dev/tty.usbmodem*): "
        ).strip()
        if answer:
            return answer
    print("No port selected.", file=sys.stderr)
    sys.exit(1)


def is_writable(target):
    test = target / ".deploy_write_test"
    try:
        test.write_text("t")
        test.unlink()
        return True
    except OSError:
        return False


def eject_host(target):
    """Ask the OS to release its handle on the mass-storage volume so
    CircuitPython can remount cleanly."""
    path = str(target).rstrip("\\/")
    if sys.platform == "win32":
        ps = (
            "$s = New-Object -ComObject Shell.Application;"
            "$s.NameSpace(17).ParseName('%s').InvokeVerb('Eject')" % path
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif sys.platform == "darwin":
        subprocess.run(["diskutil", "eject", path], check=False)
    else:
        subprocess.run(["udisksctl", "unmount", "--path", path], check=False)


def _open_serial(port):
    try:
        import serial
    except ImportError:
        print(
            "pyserial required for auto-unlock: pip install pyserial",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        ser = serial.Serial(port, 115200, timeout=1)
    except serial.SerialException as e:
        print("Could not open %s: %s" % (port, e), file=sys.stderr)
        sys.exit(1)
    ser.dtr = True
    ser.rts = True
    time.sleep(0.3)
    try:
        ser.reset_input_buffer()
    except Exception:
        pass
    return ser


def send_line(port, line):
    ser = _open_serial(port)
    try:
        ser.write((line + "\r\n").encode("utf-8"))
        time.sleep(0.4)
    finally:
        ser.close()


def repl_arm_config_reset(port):
    """Bootstrap fallback: interrupt code.py and arm config mode from the
    raw REPL. Used when the firmware on the board is too old to know the
    Set-System reboot-config command."""
    ser = _open_serial(port)
    try:
        ser.write(bytes([3]))              # Ctrl-C to break running code.py
        time.sleep(0.7)
        try:
            ser.reset_input_buffer()
        except Exception:
            pass
        ser.write(b"\r\n")
        time.sleep(0.3)
        ser.write(b"import microcontroller\r\n")
        time.sleep(0.4)
        ser.write(b"microcontroller.nvm[0] = 0x42\r\n")
        time.sleep(0.4)
        ser.write(b"microcontroller.reset()\r\n")
        time.sleep(0.8)
    finally:
        ser.close()


def parse_env(path):
    """Parse a .env-style file into a flat {KEY: value} dict."""
    env = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _as_bool(value, default=False):
    v = str(value or "").strip().lower()
    if v in ("true", "1", "yes", "on"):
        return True
    if v in ("false", "0", "no", "off"):
        return False
    return default


def _as_int(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def wifi_defaults_from_env(env):
    """Extract WIFI_N_SSID/PASSWORD/PRIORITY groups into wifi_networks entries."""
    groups = {}
    for key, value in env.items():
        if not key.startswith("WIFI_"):
            continue
        parts = key.split("_", 2)
        if len(parts) != 3:
            continue
        n, field = parts[1], parts[2].lower()
        groups.setdefault(n, {})[field] = value
    out = []
    for n in sorted(groups.keys(), key=lambda x: _as_int(x)):
        g = groups[n]
        if not g.get("ssid"):
            continue
        out.append({
            "ssid": g["ssid"],
            "password": g.get("password", ""),
            "priority": _as_int(g.get("priority", 0)),
        })
    return out


def mqtt_defaults_from_env(env):
    """Return a dict for mqtt.json if any MQTT_* key is present, else None."""
    if not any(k.startswith("MQTT_") for k in env):
        return None
    return {
        "enabled": _as_bool(env.get("MQTT_ENABLED"), False),
        "host": env.get("MQTT_HOST", ""),
        "port": _as_int(env.get("MQTT_PORT", 1883), 1883),
        "username": env.get("MQTT_USERNAME", ""),
        "password": env.get("MQTT_PASSWORD", ""),
        "base_topic": env.get("MQTT_BASE_TOPIC", "dmxwifi"),
        "discovery_prefix": env.get("MQTT_DISCOVERY_PREFIX", "homeassistant"),
    }


SYSTEM_KEYS = (
    "DMX_TX_PIN", "DMX_DIR_PIN_ENABLED", "DMX_DIR_PIN",
    "HOSTNAME", "AP_SSID", "AP_PASSWORD", "AP_IP",
    "STA_IP_MODE", "STA_STATIC_IP", "STA_STATIC_NETMASK",
    "STA_STATIC_GATEWAY", "STA_STATIC_DNS",
)


def system_defaults_from_env(env):
    if not any(k in env for k in SYSTEM_KEYS):
        return None
    return {
        "dmx_tx_pin": env.get("DMX_TX_PIN", "D4"),
        "dmx_dir_pin_enabled": _as_bool(env.get("DMX_DIR_PIN_ENABLED"), False),
        "dmx_dir_pin": env.get("DMX_DIR_PIN", "D3"),
        "hostname": env.get("HOSTNAME", "ESP-DMX"),
        "ap_ssid": env.get("AP_SSID", "ESP-DMX"),
        "ap_password": env.get("AP_PASSWORD", "DMX4ALL1"),
        "ap_ip": env.get("AP_IP", "1.1.1.1"),
        "sta_ip_mode": env.get("STA_IP_MODE", "dhcp"),
        "sta_static_ip": env.get("STA_STATIC_IP", ""),
        "sta_static_netmask": env.get("STA_STATIC_NETMASK", "255.255.255.0"),
        "sta_static_gateway": env.get("STA_STATIC_GATEWAY", ""),
        "sta_static_dns": env.get("STA_STATIC_DNS", "1.1.1.1"),
    }


def mesh_defaults_from_env(env):
    if not any(k.startswith("MESH_") for k in env):
        return None
    return {
        "role": env.get("MESH_ROLE", "none"),
        "ssid": env.get("MESH_SSID", ""),
        "password": env.get("MESH_PASSWORD", ""),
    }


def devices_defaults_from_env(env):
    """Extract DEVICE_N_* / DEVICE_N_CHANNEL_M_* groups into device entries."""
    device_groups = {}
    channel_groups = {}  # (device_n, channel_m) -> {field: value}
    for key, value in env.items():
        if not key.startswith("DEVICE_"):
            continue
        parts = key.split("_")
        # DEVICE_1_NAME                 -> parts = [DEVICE, 1, NAME]
        # DEVICE_1_START_CHANNEL        -> parts = [DEVICE, 1, START, CHANNEL]
        # DEVICE_1_CHANNEL_1_NAME       -> parts = [DEVICE, 1, CHANNEL, 1, NAME]
        if len(parts) < 3:
            continue
        dev_n = parts[1]
        rest = "_".join(parts[2:]).lower()
        if rest.startswith("channel_"):
            # channel_<m>_<field>
            sub = rest[len("channel_"):]
            ch_parts = sub.split("_", 1)
            if len(ch_parts) != 2:
                continue
            ch_m, ch_field = ch_parts
            channel_groups.setdefault((dev_n, ch_m), {})[ch_field] = value
        else:
            device_groups.setdefault(dev_n, {})[rest] = value

    if not device_groups:
        return None

    devices = []
    for dev_n in sorted(device_groups.keys(), key=lambda x: _as_int(x)):
        g = device_groups[dev_n]
        if not g.get("name"):
            continue
        channels = []
        ch_keys = sorted(
            (k for k in channel_groups if k[0] == dev_n),
            key=lambda k: _as_int(k[1]),
        )
        for i, ch_key in enumerate(ch_keys, start=1):
            cg = channel_groups[ch_key]
            channels.append({
                "offset": _as_int(cg.get("offset", i), i),
                "name": cg.get("name", "Channel %d" % i),
                "type": cg.get("type", "slider"),
            })
        devices.append({
            "id": "dev-env%s" % dev_n,
            "name": g["name"],
            "start_channel": _as_int(g.get("start_channel", 1), 1),
            "channels": channels,
        })
    return devices


def merge_wifi_defaults(target, entries):
    """Append entries into target/data/wifi_networks.json (skip existing SSIDs).
    Use --force to overwrite instead."""
    data_dir = target / "data"
    data_dir.mkdir(exist_ok=True)
    fp = data_dir / "wifi_networks.json"
    existing = []
    if fp.exists():
        try:
            existing = json.loads(fp.read_text())
        except (OSError, ValueError):
            existing = []
    seen = {n.get("ssid") for n in existing if isinstance(n, dict)}
    added = 0
    for entry in entries:
        if entry["ssid"] in seen:
            continue
        existing.append(entry)
        seen.add(entry["ssid"])
        added += 1
    fp.write_text(json.dumps(existing))
    return added


def write_config_if_absent(target, filename, data, force=False):
    """Write data/<filename> from the given dict/list. Skips if the file
    already exists unless force=True."""
    data_dir = target / "data"
    data_dir.mkdir(exist_ok=True)
    fp = data_dir / filename
    if fp.exists() and not force:
        return False
    fp.write_text(json.dumps(data))
    return True


def apply_env_defaults(env, target, force):
    """Push .env-derived defaults into target/data/*.json."""
    wifi_entries = wifi_defaults_from_env(env)
    if wifi_entries:
        if force:
            (target / "data").mkdir(exist_ok=True)
            (target / "data" / "wifi_networks.json").write_text(json.dumps(wifi_entries))
            print("  wifi_networks.json: overwritten with %d entries" % len(wifi_entries))
        else:
            added = merge_wifi_defaults(target, wifi_entries)
            print("  wifi_networks.json: %d new entries (existing SSIDs kept)" % added)

    for filename, defaults_fn in (
        ("mqtt.json", mqtt_defaults_from_env(env)),
        ("system.json", system_defaults_from_env(env)),
        ("mesh.json", mesh_defaults_from_env(env)),
        ("devices.json", devices_defaults_from_env(env)),
    ):
        if defaults_fn is None:
            continue
        written = write_config_if_absent(target, filename, defaults_fn, force=force)
        if written:
            action = "overwritten" if force else "created"
            print("  %s: %s from .env" % (filename, action))
        else:
            print("  %s: already exists, kept (use --reset-config to overwrite)" % filename)


def wait_for_writable(target, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if target.exists() and is_writable(target):
                return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def main():
    parser = argparse.ArgumentParser(description="Deploy firmware to the CIRCUITPY drive.")
    parser.add_argument("target", nargs="?", help="Path to the CIRCUITPY drive.")
    parser.add_argument("--port", help="Serial port (only needed if the drive is locked).")
    parser.add_argument(
        "--no-reboot",
        action="store_true",
        help="Leave the board in config mode after deploy (skip final Reboot).",
    )
    parser.add_argument(
        "--force",
        "--reset-config",
        action="store_true",
        dest="force",
        help="Overwrite every target data/*.json from .env, ignoring what's "
             "already on the board (default: only write missing files; wifi "
             "is append-only).",
    )
    args = parser.parse_args()

    target = Path(args.target if args.target else prompt_target())
    if not target.exists():
        print("Target %s not found." % target, file=sys.stderr)
        sys.exit(1)

    unlocked_us = False
    port = args.port
    if not is_writable(target):
        print("Target %s is read-only; unlocking via serial..." % target)
        if not port:
            port = prompt_port()
        print("  ejecting drive from host...")
        eject_host(target)
        time.sleep(0.5)
        print("  sending Set-System reboot-config...")
        send_line(port, "Set-System reboot-config")
        print("  waiting for drive to come back writable...")
        if not wait_for_writable(target, timeout=15):
            # Fallback: older firmware doesn't know reboot-config. Drop into
            # the raw REPL and arm the marker + reset directly.
            print("  no response - falling back to raw REPL bootstrap...")
            eject_host(target)
            time.sleep(0.5)
            repl_arm_config_reset(port)
            if not wait_for_writable(target, timeout=20):
                print(
                    "Timed out waiting for %s to become writable." % target,
                    file=sys.stderr,
                )
                sys.exit(1)
        unlocked_us = True
        print("  drive is writable.")

    repo_root = Path(__file__).resolve().parent.parent
    for item in ITEMS:
        src = repo_root / item
        dst = target / item
        if not src.exists():
            print("Skipping %s (not found in repo)" % item)
            continue
        print("Syncing %s ..." % item)
        if src.is_dir():
            # Wipe destination first: copytree(dirs_exist_ok=True) merges,
            # but we want a clean overwrite so removed files don't linger.
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # WIKI.md lives at repo root, but the HTTP server only serves from www/.
    # Drop a copy in www/ so the Info page's "Local copy" link works offline.
    wiki_src = repo_root / "WIKI.md"
    if wiki_src.exists():
        print("Syncing WIKI.md -> www/wiki.md ...")
        shutil.copy2(wiki_src, target / "www" / "wiki.md")

    env_path = repo_root / ".env"
    if env_path.exists():
        print("Applying .env defaults:")
        apply_env_defaults(parse_env(env_path), target, force=args.force)

    if unlocked_us and not args.no_reboot:
        print("Rebooting board back to normal mode...")
        try:
            send_line(port, "Reboot")
        except SystemExit:
            # Serial might briefly disappear during the earlier reset; give
            # it another moment and retry once.
            time.sleep(1.5)
            try:
                send_line(port, "Reboot")
            except SystemExit:
                print(
                    "Could not send Reboot - the board is still in config mode. "
                    "Reset it manually to return to normal.",
                    file=sys.stderr,
                )

    print("Deploy complete.")


if __name__ == "__main__":
    main()
