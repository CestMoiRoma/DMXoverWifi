#!/usr/bin/env python3
"""Desktop control surface for a DMX-over-WiFi board, over USB.

Mirrors the board's web UI, but talks to it on the serial link instead of the
network, so a rig can be driven with the radio switched off entirely
(`Set-System wifi-toggle off`).

    python tools/dmx_desktop.py [--port COM5]

Needs pyserial. Tkinter ships with CPython on Windows and macOS; on Linux it is
usually a separate package (python3-tk).

Two protocols share the one link, because they want opposite things:

* Configuration is read once with the text console's `Get-Config`, which answers
  with a line of JSON. Readable, easy to debug, and speed does not matter.
* Channel values go out as binary frames. A dragged fader emits values far
  faster than a forty-byte text command per slot could carry, and parsing
  strings for every one of them would waste the link on syntax.

Note on speed: on the ESP32-S2 the port is native USB CDC, where the baud rate
is a fiction the host and the firmware both ignore. Throughput is the USB
link's, so the win comes from the compact frames rather than from any baud
setting.
"""

import argparse
import json
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    sys.exit("pyserial is required: python -m pip install pyserial")

ESPRESSIF_VID = 0x303A
BAUD = 115200

FRAME_START = 0x7E
CMD_SET_ADDR = 0x01
CMD_SET_BLOCK = 0x02
CMD_PING = 0x10

# Matches the firmware's coalescing window, for the same reason: one message per
# channel per tick rather than one per pixel of travel.
FLUSH_INTERVAL = 0.03


def crc8(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def build_frame(cmd, payload=b""):
    body = bytes([cmd, len(payload)]) + payload
    return bytes([FRAME_START]) + body + bytes([crc8(body)])


def find_board_port():
    for port in serial.tools.list_ports.comports():
        if port.vid == ESPRESSIF_VID:
            return port.device
    return None


class BoardLink:
    """Owns the serial port: one writer thread, coalesced channel writes."""

    def __init__(self, port):
        self.serial = serial.Serial(port, BAUD, timeout=1)
        self.serial.dtr = True
        time.sleep(1.0)
        # Opening a native USB CDC port can deliver stray bytes, which sit in the
        # board's line buffer and glue themselves to the front of the first real
        # command. A bare newline closes that partial line so it fails on its own
        # rather than corrupting ours.
        self.serial.reset_input_buffer()
        self.serial.write(b"\n")
        self.serial.flush()
        time.sleep(0.3)
        self.serial.reset_input_buffer()
        self._pending = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._writer = threading.Thread(target=self._flush_loop, daemon=True)
        self._writer.start()

    def close(self):
        self._stop.set()
        self._writer.join(timeout=1)
        try:
            self.serial.close()
        except Exception:
            pass

    # -- text side --

    def command(self, line, expect_prefix=None, timeout=4.0):
        """Send a console command and collect its OK lines."""
        with self._lock:
            self.serial.reset_input_buffer()
            self.serial.write((line + "\n").encode())
            self.serial.flush()
            deadline = time.time() + timeout
            collected = []
            while time.time() < deadline:
                raw = self.serial.readline()
                if not raw:
                    continue
                text = raw.decode("utf-8", "replace").strip()
                if not text:
                    continue
                if text.startswith("ERR "):
                    raise RuntimeError(text[4:])
                if text.startswith("OK "):
                    text = text[3:]
                collected.append(text)
                if expect_prefix and text.startswith(expect_prefix):
                    return collected
            return collected

    def read_config(self):
        for line in self.command("Get-Config", expect_prefix="config ", timeout=6.0):
            if line.startswith("config "):
                return json.loads(line[len("config "):])
        raise RuntimeError("the board did not answer Get-Config; is the firmware current?")

    # -- binary side --

    def set_channel(self, address, value):
        with self._lock:
            self._pending[address] = value & 0xFF

    def _flush_loop(self):
        while not self._stop.is_set():
            time.sleep(FLUSH_INTERVAL)
            with self._lock:
                if not self._pending:
                    continue
                pending = self._pending
                self._pending = {}
                # Consecutive addresses ride in one block frame, which is what a
                # colour fade across R, G and B produces.
                for start, values in group_runs(pending):
                    if len(values) == 1:
                        payload = bytes([start >> 8, start & 0xFF, values[0]])
                        frame = build_frame(CMD_SET_ADDR, payload)
                    else:
                        payload = bytes([start >> 8, start & 0xFF, len(values)]) + bytes(values)
                        frame = build_frame(CMD_SET_BLOCK, payload)
                    try:
                        self.serial.write(frame)
                    except Exception:
                        self._stop.set()
                        return
                try:
                    self.serial.flush()
                except Exception:
                    self._stop.set()


def group_runs(pending):
    """Turn {address: value} into [(start_address, [values...])] runs."""
    runs = []
    for address in sorted(pending):
        if runs and address == runs[-1][0] + len(runs[-1][1]) and len(runs[-1][1]) < 250:
            runs[-1][1].append(pending[address])
        else:
            runs.append((address, [pending[address]]))
    return runs


class DesktopApp:
    def __init__(self, root, link, config):
        self.root = root
        self.link = link
        self.devices = config.get("devices", [])
        self.labels = {l["id"]: l for l in config.get("labels", [])}
        self.categories = {c["id"]: c["name"] for c in config.get("categories", [])}
        self.active_category = tk.StringVar(value="")

        root.title("DMX over WiFi: USB control")
        root.geometry("620x720")

        self._build_filter_bar()

        canvas = tk.Canvas(root, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
        self.body = ttk.Frame(canvas)
        self.body.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all(
            "<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units")
        )

        self.render()

    def _build_filter_bar(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=8, pady=(8, 0))
        ttk.Label(bar, text="Type:").pack(side="left")
        present = sorted({d.get("category", "other") for d in self.devices})
        choices = [("All", "")] + [(self.categories.get(c, c), c) for c in present]
        for name, value in choices:
            ttk.Radiobutton(
                bar,
                text=name,
                value=value,
                variable=self.active_category,
                command=self.render,
            ).pack(side="left", padx=2)

    def visible_devices(self):
        wanted = self.active_category.get()
        if not wanted:
            return self.devices
        return [d for d in self.devices if d.get("category", "other") == wanted]

    def render(self):
        for child in self.body.winfo_children():
            child.destroy()

        shown = self.visible_devices()
        if not shown:
            ttk.Label(self.body, text="No fixtures.").pack(anchor="w")
            return

        for device in shown:
            self._render_device(device)

    def _render_device(self, device):
        start = device.get("start_channel", 1)
        category = self.categories.get(device.get("category", "other"), "")
        tags = ", ".join(
            self.labels[i]["name"] for i in device.get("labels", []) if i in self.labels
        )
        heading = "%s  (%s, start ch. %d)" % (device.get("name", "?"), category, start)
        if tags:
            heading += "  [%s]" % tags

        frame = ttk.LabelFrame(self.body, text=heading)
        frame.pack(fill="x", expand=True, pady=6, padx=2)

        for channel in device.get("channels", []):
            address = start + channel.get("offset", 1) - 1
            self._render_channel(frame, channel, address)

    def _render_channel(self, parent, channel, address):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)

        label = "%s  (ch %d)" % (channel.get("name", "?"), address)
        ttk.Label(row, text=label, width=24, anchor="w").pack(side="left")

        kind = channel.get("type", "slider")
        current = channel.get("value", 0)

        if kind == "slider":
            readout = ttk.Label(row, text=str(current), width=4, anchor="e")
            scale = ttk.Scale(row, from_=0, to=255, orient="horizontal")
            scale.set(current)

            def on_move(_event=None, scale=scale, readout=readout, address=address):
                value = int(float(scale.get()))
                readout.config(text=str(value))
                # Fires all through the drag, which is the whole point.
                self.link.set_channel(address, value)

            scale.configure(command=lambda _v, f=on_move: f())
            scale.pack(side="left", fill="x", expand=True, padx=6)
            readout.pack(side="left")

        elif kind == "button-momentary":
            button = ttk.Button(row, text="Hold")
            button.bind("<ButtonPress-1>", lambda e, a=address: self.link.set_channel(a, 255))
            button.bind("<ButtonRelease-1>", lambda e, a=address: self.link.set_channel(a, 0))
            button.pack(side="left", padx=6)

        elif kind == "button-switch":
            state = {"on": current > 0}
            button = ttk.Button(row, text="On" if state["on"] else "Off")

            def toggle(a=address, s=state, b=button):
                s["on"] = not s["on"]
                b.config(text="On" if s["on"] else "Off")
                self.link.set_channel(a, 255 if s["on"] else 0)

            button.config(command=toggle)
            button.pack(side="left", padx=6)

        else:
            ttk.Button(
                row, text="Trigger", command=lambda a=address: self.link.set_channel(a, 255)
            ).pack(side="left", padx=6)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="serial port; auto-detected when omitted")
    args = parser.parse_args()

    port = args.port or find_board_port()
    if not port:
        sys.exit("No Espressif serial port found. Pass --port explicitly.")

    try:
        link = BoardLink(port)
    except serial.SerialException as exc:
        sys.exit("Could not open %s: %s\nClose any serial monitor holding it." % (port, exc))

    try:
        config = link.read_config()
    except Exception as exc:
        link.close()
        sys.exit("Could not read the config from %s: %s" % (port, exc))

    root = tk.Tk()
    app = DesktopApp(root, link, config)
    root.protocol("WM_DELETE_WINDOW", lambda: (link.close(), root.destroy()))
    try:
        root.mainloop()
    finally:
        link.close()


if __name__ == "__main__":
    main()
