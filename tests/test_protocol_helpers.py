"""Unit tests for the low-level protocol helpers in devices/divoom.py.
These freeze the CURRENT behaviour (including the checksum branch, which is
intentional PixooMax-compatibility code, not a bug to be fixed).
"""
from __future__ import annotations

import os
import random

import pytest
from PIL import Image

from custom_components.divoom.devices.aurabox import Aurabox
from custom_components.divoom.devices.ditoo import Ditoo
from custom_components.divoom.devices.minitoo import MiniToo
from custom_components.divoom.devices.pixoo import Pixoo
from custom_components.divoom.devices.pixoomax import PixooMax
from custom_components.divoom.devices.timeboxmini import TimeboxMini
from tests.support import make_connected_device, solid_color, solid_gif

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


def _time_codes(frames):
    """LE16 time code of each AA <length LE16> <time LE16> ... frame."""
    return [int.from_bytes(bytes(payload[3:5]), "little") for payload, _ in frames]


def test_pick_frames_spreads_evenly():
    device = make_pixoo()
    assert device.pick_frames(20, 10) == list(range(0, 20, 2))

    picks = device.pick_frames(300, 92)
    assert len(picks) == 92 and picks[0] == 0
    assert {b - a for a, b in zip(picks, picks[1:])} == {3, 4}


def test_process_image_thins_long_animation_evenly(tmp_path):
    """Over maxframes, frames are picked evenly and each one lasts as long as
    the frames it stands for."""
    device = make_pixoo()
    count = 100
    frames, frame_count = device.process_image(solid_gif(str(tmp_path / "long.gif"), count, duration=50))

    assert frame_count == len(frames) == Pixoo.maxframes
    assert sum(_time_codes(frames)) == count * 50
    # AA <length LE16> <time LE16> <palette flag> <color count> <r g b> ...
    assert [tuple(payload[7:10]) for payload, _ in frames] == [
        solid_color(i * count // frame_count) for i in range(frame_count)]


def test_process_image_thins_animation_over_the_chunk_index(tmp_path):
    """60 frames of 256 colors each need more than the 256 chunks a u8 index
    can address; the animation is thinned out until they fit."""
    rnd = random.Random(20240912)
    images = []
    for _ in range(60):
        img = Image.new("P", (16, 16))
        img.putpalette(bytes(rnd.getrandbits(8) for _ in range(768)))
        img.putdata(rnd.sample(range(256), 256))
        images.append(img)
    path = str(tmp_path / "noise.gif")
    images[0].save(path, save_all=True, append_images=images[1:], duration=100, loop=0)

    device = Ditoo(mac="11:22:33:44:55:66")
    frames, frame_count = device.process_image(path)

    size = sum(length for _, length in frames)
    assert 1 < frame_count == len(frames) < 60
    assert size < 1 << 16 and -(-size // device.chunksize) <= 256
    assert sum(_time_codes(frames)) == 60 * 100


@pytest.mark.parametrize("device_cls", [Aurabox, TimeboxMini])
def test_process_image_thins_to_twelve_frames_on_old_devices(device_cls, tmp_path):
    device = device_cls(mac="11:22:33:44:55:66")
    frames, frame_count = device.process_image(solid_gif(str(tmp_path / "long.gif"), 30))

    assert frame_count == len(frames) == 12
    assert sum(payload[0] for payload, _ in frames) == 30, "delay bytes in 100 ms keep the total"


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


def test_send_json_sorts_keys_and_drops_whitespace():
    """The app serializes with fastjson's SortField, so the device only ever
    sees alphabetically sorted, compact JSON."""
    device, recorder, server_sock = make_connected_device(MiniToo)
    try:
        device.send_json({"B": "x", "A": 1})
    finally:
        device.disconnect()
        server_sock.close()

    body = b'{"A":1,"B":"x"}'
    payload = list((len(body) + 3).to_bytes(2, "little")) + [0x01] + list(body)
    assert recorder.sent_messages == [bytes(device.make_message(payload))]


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
