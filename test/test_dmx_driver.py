"""DMX512 frame generation: buffer, clamping, break/MAB, refresh rate."""
import busio
import digitalio

import board
from src.dmx_driver import BREAK_BAUDRATE, DATA_BAUDRATE, FRAME_INTERVAL, DmxDriver


def test_buffer_is_one_slot_per_channel_plus_start_code(dmx):
    assert len(dmx.buffer) == 513
    assert set(dmx.buffer) == {0}


def test_set_channel_writes_the_right_slot(dmx):
    dmx.set_channel(1, 200)
    dmx.set_channel(512, 15)

    assert dmx.buffer[1] == 200
    assert dmx.buffer[512] == 15
    assert dmx.buffer[0] == 0, "start code must stay at 0"


def test_set_channel_clamps_out_of_range_values(dmx):
    dmx.set_channel(5, 999)
    dmx.set_channel(6, -40)

    assert dmx.buffer[5] == 255
    assert dmx.buffer[6] == 0


def test_set_channel_ignores_addresses_outside_the_universe(dmx):
    dmx.set_channel(0, 128)
    dmx.set_channel(513, 128)

    assert set(dmx.buffer) == {0}


def test_data_uart_is_opened_with_dmx_line_settings(dmx):
    uart = busio.uart_log[-1]

    assert uart.baudrate == DATA_BAUDRATE
    assert uart.stop == 2, "DMX512 uses two stop bits"
    assert uart.bits == 8
    assert uart.parity is None
    assert uart.tx == board.D4
    assert uart.rx is None, "transmit only, RO is not wired"


def test_send_frame_emits_a_break_then_the_universe(dmx):
    dmx.set_channel(1, 77)
    before = len(busio.uart_log)

    dmx.send_frame()

    created = busio.uart_log[before:]
    assert len(created) == 2, "one UART for the break, one for the data"

    break_uart, data_uart = created
    assert break_uart.baudrate == BREAK_BAUDRATE
    assert break_uart.stop == 1
    assert break_uart.written == b"\x00", "a zero byte at 83333 baud is the break"
    assert break_uart.deinited, "the break UART must be torn down before data"

    assert data_uart.baudrate == DATA_BAUDRATE
    assert data_uart.written == bytes(dmx.buffer)
    assert data_uart.written[1] == 77


def test_refresh_is_rate_limited(dmx, monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr("src.dmx_driver.time.monotonic", lambda: clock["now"])

    dmx.refresh_if_due()
    after_first = len(busio.uart_log)

    dmx.refresh_if_due()
    assert len(busio.uart_log) == after_first, "too soon, nothing should be sent"

    clock["now"] += FRAME_INTERVAL * 1.01
    dmx.refresh_if_due()
    assert len(busio.uart_log) > after_first


def test_refresh_interval_is_about_forty_frames_per_second():
    assert 0.02 <= FRAME_INTERVAL <= 0.03


def test_no_direction_pin_is_claimed_when_de_re_are_tied_to_vcc():
    DmxDriver(board.D4, None)
    assert digitalio.pin_log == [], "nothing to drive when DE+RE sit on VCC"


def test_direction_pin_is_driven_high_for_transmit():
    DmxDriver(board.D4, board.D3)

    assert len(digitalio.pin_log) == 1
    direction = digitalio.pin_log[0]
    assert direction.pin == board.D3
    assert direction.direction == digitalio.Direction.OUTPUT
    assert direction.value is True, "MAX485 must be transmit-enabled"
