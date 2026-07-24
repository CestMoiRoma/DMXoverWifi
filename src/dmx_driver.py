import time

import busio
import digitalio

DMX_CHANNELS = 512
DATA_BAUDRATE = 250000
FRAME_INTERVAL = 0.025

# DMX break/MAB timing (spec: break >= 88us, MAB >= 8us). We stay well
# above both to give slow receivers slack, and because CircuitPython's
# time.sleep resolution isn't microsecond-tight anyway.
BREAK_SECONDS = 0.00025  # 250us
MAB_SECONDS = 0.00003    # 30us


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
        self._uart = None
        self._last_send = 0.0
        self._open_uart()

    def _open_uart(self):
        self._uart = busio.UART(
            tx=self._tx_pin,
            rx=None,
            baudrate=DATA_BAUDRATE,
            bits=8,
            parity=None,
            stop=2,
        )

    def send_frame(self):
        # Drive the break manually via digitalio: baudrate-switch was
        # unreliable on ESP32-S2 because busio.UART.write returns before
        # the FIFO drains, so the break byte would get shifted out at the
        # new (higher) baudrate and end up below the 88us spec.
        self._uart.deinit()
        pin = digitalio.DigitalInOut(self._tx_pin)
        pin.direction = digitalio.Direction.OUTPUT
        pin.value = False       # break: hold TX low
        time.sleep(BREAK_SECONDS)
        pin.value = True        # MAB: idle high
        time.sleep(MAB_SECONDS)
        pin.deinit()
        self._open_uart()
        self._uart.write(self.buffer)

    def refresh_if_due(self):
        now = time.monotonic()
        if now - self._last_send >= FRAME_INTERVAL:
            self.send_frame()
            self._last_send = now

    def set_channel(self, address, value):
        if 1 <= address <= DMX_CHANNELS:
            self.buffer[address] = max(0, min(255, int(value)))
