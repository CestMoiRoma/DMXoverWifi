"""Fake `digitalio` module.

Only what the MAX485 direction pin needs: claim a pin, set it to output, drive it.
Every instance lands in `pin_log` so a test can check the firmware configured the
pin it said it would.
"""

pin_log = []


class Direction:
    INPUT = "input"
    OUTPUT = "output"


class Pull:
    UP = "up"
    DOWN = "down"


class DigitalInOut:
    def __init__(self, pin):
        self.pin = pin
        self.direction = Direction.INPUT
        self._value = False
        self.deinited = False
        pin_log.append(self)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new):
        if self.direction != Direction.OUTPUT:
            raise AttributeError("cannot set value on an input pin")
        self._value = bool(new)

    def switch_to_output(self, value=False):
        self.direction = Direction.OUTPUT
        self._value = bool(value)

    def deinit(self):
        self.deinited = True


def _reset_state():
    pin_log.clear()
