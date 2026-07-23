"""Fake `microcontroller` module.

`nvm` is a plain bytearray, so the config-mode marker logic in boot.py and
`Set-System reboot-config` can be driven and inspected directly.

`reset()` raises instead of returning: on hardware the call never comes back, and
a stub that returns would let a test run code that could not run on the board.
"""

NVM_SIZE = 512


class ResetCalled(BaseException):
    """Raised by reset(). Catch it to assert the firmware asked for a reset.

    Deliberately a BaseException: on hardware `reset()` never returns, so the
    firmware's own `except Exception` handlers must not be able to swallow it
    and carry on running code that could not have run on the board.
    """


nvm = bytearray(NVM_SIZE)

# Set to False to simulate a board whose partition table strips the NVM region.
nvm_available = True

cpu = type("CPU", (), {"temperature": 42.0, "frequency": 240_000_000})()


def reset():
    raise ResetCalled()


def _reset_state():
    """Test helper: back to a freshly powered board."""
    global nvm, nvm_available
    nvm = bytearray(NVM_SIZE)
    nvm_available = True
