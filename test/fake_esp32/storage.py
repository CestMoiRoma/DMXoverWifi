"""Fake `storage` module.

Tracks which side owns filesystem write access, and reproduces the one failure
mode the firmware actually has to handle: CircuitPython refuses to remount while
the host still has the mass-storage volume mounted.

Test-facing state:
    usb_visible     set True to simulate a host that has not ejected the drive
    remounts        every remount call, as (path, readonly) tuples
    mount_readonly  None until something remounts, then the last readonly value
"""

usb_visible = False
remounts = []
mount_readonly = None


def remount(mount_path, readonly=False, disable_concurrent_write_protection=False):
    global mount_readonly
    if usb_visible:
        # Matches the message CircuitPython produces, which deploy.py and the
        # WIKI both quote.
        raise RuntimeError("Cannot remount '%s' when visible via USB." % mount_path)
    remounts.append((mount_path, readonly))
    mount_readonly = readonly


def erase_filesystem():
    raise NotImplementedError("not needed by the firmware")


def _reset_state(usb=False):
    """Test helper: back to a freshly powered board."""
    global usb_visible, mount_readonly
    usb_visible = usb
    mount_readonly = None
    remounts.clear()
