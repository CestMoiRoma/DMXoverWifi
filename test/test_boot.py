"""boot.py decides who owns the filesystem before code.py ever runs.

boot.py is a script, not a module, so each test executes the real file in a
fresh namespace against the fake board.
"""
import microcontroller
import storage

from conftest import REPO_ROOT

CONFIG_MODE_MAGIC = 0x42
MARKER = 0
CONFIG_FLAG = 1


def run_boot():
    source = (REPO_ROOT / "boot.py").read_text()
    exec(compile(source, "boot.py", "exec"), {"__name__": "__main__"})


def test_a_normal_boot_gives_write_access_to_the_board():
    run_boot()

    assert storage.remounts == [("/", False)]
    assert microcontroller.nvm[CONFIG_FLAG] == 0
    assert microcontroller.nvm[MARKER] == 0


def test_an_armed_marker_leaves_the_filesystem_to_the_host():
    microcontroller.nvm[MARKER] = CONFIG_MODE_MAGIC

    run_boot()

    assert storage.remounts == [], "config mode must not claim the filesystem"
    assert microcontroller.nvm[CONFIG_FLAG] == 1


def test_the_marker_is_consumed_so_config_mode_lasts_one_boot():
    microcontroller.nvm[MARKER] = CONFIG_MODE_MAGIC
    run_boot()
    assert microcontroller.nvm[MARKER] == 0

    storage._reset_state()
    run_boot()

    assert storage.remounts == [("/", False)], "the next boot is a normal one"
    assert microcontroller.nvm[CONFIG_FLAG] == 0


def test_an_unrelated_marker_value_is_not_config_mode():
    microcontroller.nvm[MARKER] = 0x99

    run_boot()

    assert storage.remounts == [("/", False)]
    assert microcontroller.nvm[CONFIG_FLAG] == 0


def test_a_board_without_nvm_still_boots_writable(monkeypatch):
    class NoNvm:
        def __getitem__(self, index):
            raise RuntimeError("nvm region absent")

        def __setitem__(self, index, value):
            raise RuntimeError("nvm region absent")

    monkeypatch.setattr(microcontroller, "nvm", NoNvm())

    run_boot()

    assert storage.remounts == [("/", False)], "no NVM must not mean no firmware"


def test_a_failing_remount_does_not_brick_the_board(monkeypatch):
    calls = []

    def flaky(mount_path, readonly=False, **kwargs):
        calls.append(readonly)
        if len(calls) == 1:
            raise RuntimeError("first attempt fails")

    monkeypatch.setattr(storage, "remount", flaky)

    run_boot()  # must not raise

    assert calls == [False, False], "the fallback retries the same remount"
