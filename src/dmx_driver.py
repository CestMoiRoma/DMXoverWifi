import time

import busio
import digitalio

DMX_CHANNELS = 512
DATA_BAUDRATE = 250000
BREAK_BAUDRATE = 83333
FRAME_INTERVAL = 0.025


class DmxDriver:
    def __init__(self, tx_pin, dir_pin=None):
        # dir_pin is optional: some MAX485 boards tie DE+RE straight to VCC
        # (always transmit-enabled) instead of a GPIO, in which case there's
        # nothing for the microcontroller to drive.
        self.buffer = bytearray(DMX_CHANNELS + 1)
        self._tx_pin = tx_pin
        self._direction = None
        if dir_pin is not None:
            self._direction = digitalio.DigitalInOut(dir_pin)
            self._direction.direction = digitalio.Direction.OUTPUT
            self._direction.value = True
        # 8N2 stays fixed. To emit the DMX break we only toggle the
        # baudrate: at BREAK_BAUDRATE a zero byte gives us 9 low bits
        # (>= 88us) followed by 2 stop bits (MAB, >= 8us). Reusing the
        # same UART instance avoids the driver install/uninstall churn
        # that deinit+reinit at 40Hz used to cause on ESP32-S2.
        self._uart = busio.UART(
            tx=self._tx_pin,
            rx=None,
            baudrate=DATA_BAUDRATE,
            bits=8,
            parity=None,
            stop=2,
        )
        self._last_send = 0.0

    def send_frame(self):
        self._uart.baudrate = BREAK_BAUDRATE
        self._uart.write(b"\x00")
        self._uart.baudrate = DATA_BAUDRATE
        self._uart.write(self.buffer)

    def refresh_if_due(self):
        now = time.monotonic()
        if now - self._last_send >= FRAME_INTERVAL:
            self.send_frame()
            self._last_send = now

    def set_channel(self, address, value):
        if 1 <= address <= DMX_CHANNELS:
            self.buffer[address] = max(0, min(255, int(value)))
