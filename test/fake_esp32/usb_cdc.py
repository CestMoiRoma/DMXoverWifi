"""Fake `usb_cdc` module.

`console` behaves like the USB CDC stream the serial console polls: bytes fed in
by a test come back out of read(), and everything the firmware writes is kept for
assertions.
"""


class FakeSerial:
    def __init__(self):
        self._inbox = bytearray()
        self.written = bytearray()

    # -- the API SerialConsole uses --

    @property
    def in_waiting(self):
        return len(self._inbox)

    def read(self, count):
        chunk = bytes(self._inbox[:count])
        del self._inbox[:count]
        return chunk

    def write(self, data):
        self.written.extend(data)
        return len(data)

    # -- test helpers --

    def feed(self, text):
        """Queue a command as if it had been typed into the terminal."""
        if isinstance(text, str):
            text = text.encode("utf-8")
        self._inbox.extend(text)

    def take_output(self):
        """Drain everything written since the last call, as a list of lines."""
        text = bytes(self.written).decode("utf-8", "replace")
        self.written.clear()
        return [line for line in text.replace("\r\n", "\n").split("\n") if line]

    def reset(self):
        self._inbox.clear()
        self.written.clear()


console = FakeSerial()
data = None  # the second CDC endpoint, disabled by default on CircuitPython


def _reset_state():
    console.reset()
