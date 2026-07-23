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
        if not wait_for_writable(target, timeout=25):
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
