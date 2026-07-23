import time

import busio
import digitalio

DMX_CHANNELS = 512
DATA_BAUDRATE = 250000
BREAK_BAUDRATE = 83333
FRAME_INTERVAL = 0.025


class DmxDriver:
    def __init__(self, tx_pin, dir_pin):
        self.buffer = bytearray(DMX_CHANNELS + 1)
        self._tx_pin = tx_pin
        self._direction = digitalio.DigitalInOut(dir_pin)
        self._direction.direction = digitalio.Direction.OUTPUT
        self._direction.value = True
        self._uart = None
        self._last_send = 0.0
        self._open_data_uart()

    def _open_data_uart(self):
        if self._uart is not None:
            self._uart.deinit()
        self._uart = busio.UART(
            tx=self._tx_pin, rx=None, baudrate=DATA_BAUDRATE, bits=8, parity=None, stop=2
        )

    def _send_break(self):
        self._uart.deinit()
        break_uart = busio.UART(
            tx=self._tx_pin, rx=None, baudrate=BREAK_BAUDRATE, bits=8, parity=None, stop=1
        )
        break_uart.write(b"\x00")
        break_uart.deinit()

    def send_frame(self):
        self._send_break()
        self._open_data_uart()
        self._uart.write(self.buffer)

    def refresh_if_due(self):
        now = time.monotonic()
        if now - self._last_send >= FRAME_INTERVAL:
            self.send_frame()
            self._last_send = now

    def set_channel(self, address, value):
        if 1 <= address <= DMX_CHANNELS:
            self.buffer[address] = max(0, min(255, int(value)))
