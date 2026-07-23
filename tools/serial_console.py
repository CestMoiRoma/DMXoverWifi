#!/usr/bin/env python3
"""Minimal interactive serial terminal for the DMX-over-WiFi board's USB CDC
console. Cross-platform (Windows/macOS/Linux) - requires pyserial:

    pip install pyserial

Usage:
    python serial_console.py [PORT] [BAUD]

PORT defaults to /dev/ttyACM0 on Linux, /dev/tty.usbmodem* on macOS (pass it
explicitly), or COM9 on Windows. BAUD defaults to 115200 (USB CDC ignores
the actual value, but most terminals expect one to be set).
"""
import sys
import time

try:
    import serial
except ImportError:
    print("pyserial is required: pip install pyserial")
    sys.exit(1)


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM9"
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    ser = serial.Serial(port, baud, timeout=0.5)
    ser.dtr = True
    ser.rts = True
    time.sleep(0.3)
    ser.reset_input_buffer()

    print("Connected to %s at %d baud. Type a command and press Enter." % (port, baud))
    print("Type 'exit' to quit this terminal (does not reset the board).")
    print()

    try:
        while True:
            line = input("> ")
            if line == "exit":
                break
            ser.write((line + "\r\n").encode("utf-8"))
            time.sleep(0.5)
            data = ser.read(ser.in_waiting or 1)
            if data:
                print(data.decode("utf-8", errors="replace"), end="")
    finally:
        ser.close()
        print("Disconnected.")


if __name__ == "__main__":
    main()
