"""tools/serial_console.py, the part that runs without a board attached.

Only the port picker is reachable off hardware, but it is the part a user meets
first and the part that silently sends them to a Bluetooth port if it picks
wrong.
"""
import importlib.util

import pytest

from conftest import REPO_ROOT

pytest.importorskip("serial", reason="pyserial not installed")


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "serial_console_tool", REPO_ROOT / "tools" / "serial_console.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load_tool()


class FakePort:
    def __init__(self, device, description=""):
        self.device = device
        self.description = description


def fake_ports(monkeypatch, ports):
    monkeypatch.setattr(tool.list_ports, "comports", lambda: list(ports))


def fake_input(monkeypatch, answer):
    monkeypatch.setattr("builtins.input", lambda *_: answer)


def test_picking_a_number_returns_that_port(monkeypatch, capsys):
    fake_ports(
        monkeypatch,
        [FakePort("COM4", "Bluetooth"), FakePort("COM9", "USB Serial Device")],
    )
    fake_input(monkeypatch, "2")

    assert tool.prompt_port() == "COM9"


def test_the_listing_shows_the_description_so_the_usb_port_is_obvious(monkeypatch, capsys):
    fake_ports(monkeypatch, [FakePort("COM9", "USB Serial Device")])
    fake_input(monkeypatch, "1")

    tool.prompt_port()

    listing = capsys.readouterr().out
    assert "COM9" in listing
    assert "USB Serial Device" in listing


def test_typing_a_device_path_instead_of_a_number_works(monkeypatch):
    fake_ports(monkeypatch, [FakePort("COM4")])
    fake_input(monkeypatch, "/dev/ttyACM0")

    assert tool.prompt_port() == "/dev/ttyACM0"


def test_a_number_outside_the_list_is_treated_as_a_path(monkeypatch):
    fake_ports(monkeypatch, [FakePort("COM4")])
    fake_input(monkeypatch, "7")

    assert tool.prompt_port() == "7"


def test_it_still_asks_when_no_ports_are_detected(monkeypatch):
    fake_ports(monkeypatch, [])
    fake_input(monkeypatch, "COM9")

    assert tool.prompt_port() == "COM9"


def test_answering_nothing_exits_rather_than_opening_a_random_port(monkeypatch):
    fake_ports(monkeypatch, [FakePort("COM4")])
    fake_input(monkeypatch, "")

    with pytest.raises(SystemExit):
        tool.prompt_port()


def test_answering_nothing_with_no_ports_also_exits(monkeypatch):
    fake_ports(monkeypatch, [])
    fake_input(monkeypatch, "")

    with pytest.raises(SystemExit):
        tool.prompt_port()
