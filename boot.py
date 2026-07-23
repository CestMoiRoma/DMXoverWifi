import microcontroller
import storage

DOUBLE_RESET_MAGIC = 0x42


def _read_byte(index):
    try:
        return microcontroller.nvm[index]
    except Exception:
        return 0


def _write_byte(index, value):
    try:
        microcontroller.nvm[index] = value
    except Exception:
        pass


try:
    config_mode = _read_byte(0) == DOUBLE_RESET_MAGIC
    if config_mode:
        # Double-tap detected: clear the marker, leave storage host-writable
        # (skip remount) and flag config mode for code.py.
        _write_byte(0, 0)
        _write_byte(1, 1)
    else:
        _write_byte(0, DOUBLE_RESET_MAGIC)
        _write_byte(1, 0)
        storage.remount("/", readonly=False)
except Exception:
    # Never brick the board over boot-mode detection: fall back to normal
    # microcontroller-writable operation.
    try:
        storage.remount("/", readonly=False)
    except Exception:
        pass
