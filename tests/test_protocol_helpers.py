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
