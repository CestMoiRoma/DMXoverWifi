"""Fake `board` module.

Exposes the pin names a Lolin S2 Mini offers under CircuitPython. Anything else
raises AttributeError, which is what the real module does and what `code.py`
relies on to fail loudly on a bad `dmx_tx_pin` setting.
"""


class Pin:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "Pin(%s)" % self.name

    def __eq__(self, other):
        return isinstance(other, Pin) and other.name == self.name

    def __hash__(self):
        return hash(self.name)


_NAMES = (
    ["D%d" % i for i in range(16)]
    + ["IO%d" % i for i in range(22)]
    + ["A0", "A1", "A2", "A3", "LED", "NEOPIXEL", "TX", "RX", "SCL", "SDA"]
)

for _name in _NAMES:
    globals()[_name] = Pin(_name)


def board_id():
    return "lolin_s2_mini"
