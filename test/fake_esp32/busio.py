"""Fake `busio` module.

The DMX driver generates its break by tearing down the UART and re-opening it at
a slower baud rate, so the interesting thing to assert on is the *sequence* of
UART lifetimes and what each one wrote. Every instance is appended to
`uart_log` in creation order and keeps its own config and writes.
"""

uart_log = []


class UART:
    def __init__(
        self,
        tx=None,
        rx=None,
        baudrate=9600,
        bits=8,
        parity=None,
        stop=1,
        timeout=1,
        receiver_buffer_size=64,
    ):
        self.tx = tx
        self.rx = rx
        self.baudrate = baudrate
        self.bits = bits
        self.parity = parity
        self.stop = stop
        self.writes = []
        self.deinited = False
        uart_log.append(self)

    def write(self, data):
        if self.deinited:
            raise ValueError("UART used after deinit")
        self.writes.append(bytes(data))
        return len(data)

    def read(self, count=None):
        return None

    def deinit(self):
        self.deinited = True

    @property
    def written(self):
        """Everything this UART sent, concatenated."""
        return b"".join(self.writes)


class Parity:
    ODD = "odd"
    EVEN = "even"


def _reset_state():
    uart_log.clear()
