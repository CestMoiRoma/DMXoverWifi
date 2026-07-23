"""Fake `socketpool` module.

Nothing in the firmware uses a pool directly. It is created once and handed to the
HTTP server and the MQTT client, both of which are themselves stubs here, so an
inert marker object is enough.
"""


class SocketPool:
    AF_INET = 2
    SOCK_STREAM = 1

    def __init__(self, radio):
        self.radio = radio

    def socket(self, *args, **kwargs):
        raise NotImplementedError("no real sockets in the test environment")


class Socket:
    pass
