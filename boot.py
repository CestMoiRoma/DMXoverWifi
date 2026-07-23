import microcontroller
import storage

CONFIG_MODE_MAGIC = 0x42


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
    if _read_byte(0) == CONFIG_MODE_MAGIC:
        # Config-mode marker set (by "Set-System reboot-config" over serial,
        # or by tools/deploy.py auto-unlock). Consume it, flag code.py, and
        # leave the filesystem PC-writable.
        _write_byte(0, 0)
        _write_byte(1, 1)
    else:
        _write_byte(1, 0)
        storage.remount("/", readonly=False)
except Exception:
    # Never brick the board over boot-mode detection: fall back to normal
    # microcontroller-writable operation.
    try:
        storage.remount("/", readonly=False)
    except Exception:
        pass
