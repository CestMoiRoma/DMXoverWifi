"""
Minimal DMX transmit test. No wifi, no MQTT, no web, no serial console.
Just an infinite loop that pushes a DMX frame with every channel at
255 out of board.IO4 (GPIO4). If the par lights up, DMX + wiring work
and something else in the main firmware is masking that. If not, the
DMX driver, the pin, or the physical link is still broken.
"""

import time
import board
import busio
import digitalio

TX_PIN = board.IO4
BAUD = 250000
BREAK_S = 0.00025
MAB_S = 0.00003
CHANNELS = 512

# All channels at 255 (start code = 0)
buffer = bytearray(CHANNELS + 1)
for i in range(1, CHANNELS + 1):
    buffer[i] = 255

uart = busio.UART(
    tx=TX_PIN, rx=None, baudrate=BAUD, bits=8, parity=None, stop=2
)

print("DMX minimal test: TX=IO4, all channels = 255, refresh 40 Hz")

while True:
    # Break via digitalio: deinit UART, drive pin low, then high, reinit.
    uart.deinit()
    pin = digitalio.DigitalInOut(TX_PIN)
    pin.direction = digitalio.Direction.OUTPUT
    pin.value = False
    time.sleep(BREAK_S)
    pin.value = True
    time.sleep(MAB_S)
    pin.deinit()
    uart = busio.UART(
        tx=TX_PIN, rx=None, baudrate=BAUD, bits=8, parity=None, stop=2
    )
    uart.write(buffer)
    time.sleep(0.025)
