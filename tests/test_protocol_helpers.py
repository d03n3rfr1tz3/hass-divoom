"""Unit tests for the low-level protocol helpers in devices/divoom.py.
These freeze the CURRENT behaviour (including the checksum branch, which is
intentional PixooMax-compatibility code - see the plan's "checksum()" note,
not a bug to be fixed).
"""
from __future__ import annotations

import os

from custom_components.divoom.devices.aurabox import Aurabox
from custom_components.divoom.devices.pixoo import Pixoo
from custom_components.divoom.devices.pixoomax import PixooMax
from tests.support import make_connected_device

PIXELART_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "pixelart"))


def make_pixoo():
    return Pixoo(mac="11:22:33:44:55:66")


def test_checksum_two_byte_branch_just_below_boundary():
    device = make_pixoo()
    payload = [255] * 256 + [254]  # sum == 65534
    assert sum(payload) == 65534
    assert device.checksum(payload) == [254, 255]


def test_checksum_four_byte_branch_at_boundary():
    device = make_pixoo()
    payload = [255] * 257  # sum == 65535, the ">=" boundary itself
    assert sum(payload) == 65535
    assert device.checksum(payload) == [255, 255, 0, 0]


def test_checksum_four_byte_branch_real_pixoomax_single_frame():
    """A real 32x32 single-frame image (unchunked show_image path) whose
    payload byte-sum exceeds 65535 - the scenario the 4-byte checksum
    branch exists for."""
    device = PixooMax(mac="11:22:33:44:55:66")
    frames, frame_count = device.process_image(os.path.join(PIXELART_DIR, "smiley32.gif"))
    assert frame_count == 1

    payload, _length = frames[-1]
    assert sum(payload) >= 65535
    assert len(device.checksum(payload)) == 4


def test_process_pixels_one_bit_per_pixel():
    device = make_pixoo()
    colors = [[0, 0, 0], [255, 255, 255]]
    pixels = [0, 1, 0, 1, 1, 0, 1, 0]
    assert device.process_pixels(pixels, colors) == [90]


def test_process_pixels_two_bits_per_pixel():
    device = make_pixoo()
    colors = [[0, 0, 0], [1, 1, 1], [2, 2, 2], [3, 3, 3]]
    pixels = [0, 1, 2, 3, 3, 2, 1, 0, 1, 1, 1, 1]
    assert device.process_pixels(pixels, colors) == [228, 27, 85]


def test_parse_frequency_none_defaults_to_zero():
    device = make_pixoo()
    assert device._parse_frequency(None) == [0, 0]


def test_parse_frequency_below_100_mhz():
    device = make_pixoo()
    assert device._parse_frequency(50.0) == [0, 5]


def test_parse_frequency_above_100_mhz():
    device = make_pixoo()
    assert device._parse_frequency(101.3) == [13, 10]


def test_parse_frequency_accepts_string():
    device = make_pixoo()
    assert device._parse_frequency("101.3") == [13, 10]


def test_escape_payload_disabled_is_passthrough():
    device = make_pixoo()
    assert device.escapePayload is False
    assert device.escape_payload([0x01, 0x02, 0x03, 0x04, 0x99]) == [0x01, 0x02, 0x03, 0x04, 0x99]


def test_escape_payload_enabled_escapes_control_bytes():
    device = Aurabox(mac="11:22:33:44:55:66")
    assert device.escapePayload is True
    assert device.escape_payload([0x01, 0x02, 0x03, 0x04, 0x99]) == [
        0x03, 0x04, 0x03, 0x05, 0x03, 0x06, 0x04, 0x99,
    ]


def test_make_message_without_escaping():
    device = make_pixoo()
    assert device.make_message([0x01, 0x02, 0x03]) == [0x01, 0x01, 0x02, 0x03, 0x06, 0x00, 0x02]


def test_make_message_with_escaping():
    device = Aurabox(mac="11:22:33:44:55:66")
    assert device.make_message([0x01, 0x02, 0x03]) == [
        0x01, 0x03, 0x04, 0x03, 0x05, 0x03, 0x06, 0x06, 0x00, 0x02,
    ]


def test_send_weather_celsius_sends_set_temp_type_zero():
    """value[-2] == "°C" compares a single character against a 2-character
    string and is never true - value[-2:] is required for the "set temp
    type" follow-up command to ever be sent."""
    device, recorder, server_sock = make_connected_device(Pixoo)
    try:
        device.send_weather("22°C", weather=3)
    finally:
        device.disconnect()
        server_sock.close()

    assert len(recorder.sent_messages) == 2
    temp_message = recorder.sent_messages[0]
    assert temp_message[3] == 0x5f  # "set temp" command byte
    assert temp_message[4] == 22  # Celsius value sent as-is
    temp_type_message = recorder.sent_messages[1]
    assert temp_type_message[3] == 0x2b  # "set temp type" command byte
    assert temp_type_message[4] == 0x00  # Celsius


def test_send_weather_fahrenheit_sends_set_temp_type_one():
    """The device always interprets the "set temp" value as Celsius (the
    "set temp type" flag only controls how it is *displayed*), so a
    Fahrenheit input must be converted to Celsius before being sent -
    confirmed by a BT snoop of the official app, which sends the same
    Celsius reading regardless of the selected display unit."""
    device, recorder, server_sock = make_connected_device(Pixoo)
    try:
        device.send_weather("70°F", weather=3)
    finally:
        device.disconnect()
        server_sock.close()

    assert len(recorder.sent_messages) == 2
    temp_message = recorder.sent_messages[0]
    assert temp_message[3] == 0x5f
    assert temp_message[4] == round((70 - 32) * 5 / 9)  # 21, converted to Celsius
    temp_type_message = recorder.sent_messages[1]
    assert temp_type_message[3] == 0x2b
    assert temp_type_message[4] == 0x01


def test_show_clock_string_clock_matches_int_clock():
    """clock arrives as a string from HA service calls; show_clock must
    accept it the same way show_alarm already does."""
    device_str, recorder_str, server_str = make_connected_device(Pixoo)
    device_int, recorder_int, server_int = make_connected_device(Pixoo)
    try:
        device_str.show_clock(clock="3", twentyfour=True)
        device_int.show_clock(clock=3, twentyfour=True)
    finally:
        device_str.disconnect()
        server_str.close()
        device_int.disconnect()
        server_int.close()

    assert recorder_str.sent_messages == recorder_int.sent_messages


def test_send_gamecontrol_invalid_string_logs_and_sends_nothing():
    device, recorder, server_sock = make_connected_device(Pixoo)
    try:
        result = device.send_gamecontrol(value="not-a-value")
    finally:
        device.disconnect()
        server_sock.close()

    assert result is None
    assert recorder.sent_messages == []


def test_disconnect_swallows_socket_errors_and_clears_socket():
    """The bare `except:` in disconnect() used to also swallow
    BaseException subclasses like SystemExit/KeyboardInterrupt; narrowing it
    to `except Exception:` must not change behaviour for ordinary socket
    errors raised from shutdown()."""
    device = Pixoo(mac="11:22:33:44:55:66")

    class RaisingSocket:
        def shutdown(self, *args, **kwargs):
            raise OSError("shutdown failed")

        def close(self):
            pass

    device.socket = RaisingSocket()
    device.disconnect()

    assert device.socket is None
