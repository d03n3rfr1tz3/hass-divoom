"""Structural verification of the MiniToo's media path (opcode 0x8b).

These cases are deliberately absent from tests/goldens/: the payload is one
Zstandard stream, whose bytes are not guaranteed identical across
zstandard/libzstd versions, so a recorded hexdump would be flaky - and at
roughly 1.5 MB it would be unreadable besides. Instead everything a golden
would freeze is checked here directly, and more sharply: envelope and
checksum of every message (recomputed through the device's own
make_message), the start packet, gapless chunk indices and sizes, the media
header, and - after decompressing - the pixel buffer itself, compared
against an independently rebuilt reference.

The comparison is against the *decompressed* bytes, so it stays valid no
matter how the compressor version changes. One frozen hash pins
MiniToo._fit() itself; without it the content check would only compare
show_image against itself.
"""
from __future__ import annotations

import hashlib
import os

import pytest
import zstandard as zstd
from PIL import Image

from custom_components.divoom.devices.minitoo import MiniToo
from tests.cases import (
    PIXELART_DIR,
    all_cases,
    image_case_name,
    is_media_case,
    pixelart_files,
)
from tests.support import make_connected_device, minitoo_responder

MEDIA_CASES = [name for name, _ in all_cases() if is_media_case("MiniToo", name)]

OPCODE = 0x8B
SCREEN = 128
BLOCKS = SCREEN // 16
BYTES_PER_FRAME = SCREEN * SCREEN * 3
CHUNK_SIZE = 256
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

# sha256 of pixelart/smiley16.gif run through MiniToo._fit(). This pins the
# crop/resample pipeline itself - the reference buffer below is rebuilt with
# _fit(), so without this the content check would compare show_image against
# itself. Regenerate only after an intentional _fit() change.
SMILEY16_RAW_SHA256 = "107555b53cab5b6d5d3e3f27ad21864b7e49b8a934f959aa65f3b31df3b146c5"


def _source_file(case_name):
    """The pixelart file a show_image case came from, or None for show_text."""
    for filename in pixelart_files():
        if image_case_name(filename) == case_name:
            return os.path.join(PIXELART_DIR, filename)
    return None


def _expected_frames(device, path):
    """Rebuild the frames and speed a show_image case has to produce. Shares
    only _fit() with the device, so the frame walk itself stays independent."""
    with Image.open(path) as img:
        n = getattr(img, "n_frames", 1)
        if n <= 1:
            return [device._fit(img)], 1000
        frames, durations = [], []
        for i in range(min(n, 255)):
            img.seek(i)
            frames.append(device._fit(img.convert("RGB")))
            durations.append(img.info.get("duration", 100))
        return frames, max(1, int(sum(durations) / len(durations)))


def _run_case(case_name):
    device, recorder, server_sock = make_connected_device(
        MiniToo, responder=minitoo_responder)
    try:
        dict(all_cases())[case_name](device)
    finally:
        device.disconnect()
        server_sock.close()
    return device, recorder.sent_messages


def _body(message):
    """Strip the envelope 01 <length LE16> <opcode> ... <checksum LE16> 02."""
    return message[4:-3]


def test_await_request_sees_the_device_reply():
    """The handshake itself: without this a broken _await_request() would only
    make the cases below slow (2s timeout each), never red."""
    device, _, server_sock = make_connected_device(
        MiniToo, responder=minitoo_responder)
    try:
        device.send_command("set gif", [0x00, 0x00, 0x00, 0x00, 0x00], skipRead=True)
        assert device._await_request() is True
    finally:
        device.disconnect()
        server_sock.close()


def test_await_request_times_out_without_a_reply():
    device, _, server_sock = make_connected_device(MiniToo)
    try:
        device.send_command("set gif", [0x00, 0x00, 0x00, 0x00, 0x00], skipRead=True)
        assert device._await_request(timeout=0.3) is False
    finally:
        device.disconnect()
        server_sock.close()


@pytest.mark.parametrize("case_name", MEDIA_CASES)
def test_minitoo_media(case_name):
    device, messages = _run_case(case_name)
    assert len(messages) >= 2, "expected a start packet plus at least one chunk"

    # 1. envelope, opcode and checksum of every single message
    for message in messages:
        payload = list(message[1:-3])
        assert message[0] == 0x01 and message[-1] == 0x02
        assert int.from_bytes(message[1:3], "little") == len(payload)
        assert payload[2] == OPCODE
        assert bytes(device.make_message(payload)) == message

    # 2. start packet: 00 <total length LE32>
    start = _body(messages[0])
    assert len(start) == 5
    assert start[0] == 0x00
    total = int.from_bytes(start[1:5], "little")

    # 3. chunks: 01 <same total LE32> <index LE16> <up to 256 bytes>
    payload_bytes = bytearray()
    last = len(messages) - 2
    for index, message in enumerate(messages[1:]):
        chunk = _body(message)
        assert chunk[0] == 0x01
        assert int.from_bytes(chunk[1:5], "little") == total
        assert int.from_bytes(chunk[5:7], "little") == index
        data = chunk[7:]
        assert 0 < len(data) <= CHUNK_SIZE
        if index < last:
            assert len(data) == CHUNK_SIZE, "only the last chunk may be short"
        payload_bytes += data
    assert len(payload_bytes) == total

    # 4. media header: 25 <frames> <speed BE16> <rows> <cols> <zstd length BE32>
    assert payload_bytes[0] == 0x25
    frames = payload_bytes[1]
    speed = int.from_bytes(payload_bytes[2:4], "big")
    assert payload_bytes[4] == BLOCKS
    assert payload_bytes[5] == BLOCKS
    stream = bytes(payload_bytes[10:])
    assert int.from_bytes(payload_bytes[6:10], "big") == len(stream)
    assert stream[:4] == ZSTD_MAGIC

    # 5. the pixels themselves
    raw = zstd.ZstdDecompressor().decompress(stream)
    assert len(raw) == frames * BYTES_PER_FRAME

    path = _source_file(case_name)
    if path is None:
        # show_text: rebuilding the glyphs would compare show_text against
        # itself, and would depend on the FreeType build the same way the
        # goldens in test_golden_devices.py do. Length and framing above are
        # what is actually verifiable here.
        assert frames == 1
        return

    expected_frames, expected_speed = _expected_frames(device, path)
    assert frames == len(expected_frames)
    assert speed == expected_speed
    assert raw == b"".join(f.tobytes("raw", "RGB") for f in expected_frames)

    if os.path.basename(path) == "smiley16.gif":
        assert hashlib.sha256(raw).hexdigest() == SMILEY16_RAW_SHA256
