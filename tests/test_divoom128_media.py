"""Structural checks of the 128x128 media path (opcode 0x8b).

Its zstd payload is not byte-stable across libzstd versions, so instead of
goldens these tests check envelope, checksums, start packet, chunk indices,
media header and the decompressed pixels against a rebuilt reference.
"""
from __future__ import annotations

import hashlib
import os
import random

import pytest
import zstandard as zstd
from PIL import Image

from custom_components.divoom.devices.flowtoo import FlowToo
from custom_components.divoom.devices.minitoo import MiniToo
from tests.cases import (
    DEVICE_CLASSES,
    MEDIA_DEVICES,
    PIXELART_DIR,
    all_cases,
    image_case_name,
    is_media_case,
    pixelart_files,
)
from tests.support import (
    MediaResendResponder,
    make_connected_device,
    media_responder,
    solid_color,
    solid_gif,
)

MEDIA_CASES = [name for name, _ in all_cases() if is_media_case("MiniToo", name)]

OPCODE = 0x8B
SCREEN = 128
BLOCKS = SCREEN // 16
PIXELS = SCREEN * SCREEN
BYTES_PER_FRAME = PIXELS * 3 # RGB888, as everything but the FlowToo sends it
CHUNK_SIZE = 256
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

MEDIA_MAX_BYTES = 307200

# bytes per pixel and zstd window_log, one entry per media device
MEDIA_DEVICE_SPECS = {"FlowToo": (2, 16), "MiniToo": (3, 17), "Tiivoo2": (3, 17)}

# sha256 of pixelart/smiley16.gif run through Divoom128._fit() and _quantize().
# The reference below is rebuilt with both, so this hash pins them. Regenerate
# only after an intended change, and check the decoded frame first.
SMILEY16_RAW_SHA256 = "63f506cbcda03d1c3303167f5c01b9d404916444cdcdc5d29335c99c0d944f10"


def _source_file(case_name):
    """The pixelart file a show_image case came from, or None for show_text."""
    for filename in pixelart_files():
        if image_case_name(filename) == case_name:
            return os.path.join(PIXELART_DIR, filename)
    return None


def _expected_frames(device, path):
    """Rebuild the frames and speed a show_image case has to produce, sharing
    only _fit(), _quantize() and pick_frames() with the device."""
    with Image.open(path) as img:
        n = getattr(img, "n_frames", 1)
        if n <= 1:
            return [device._quantize(device._fit(img))], 1000
        frames, durations = [], []
        for i in range(n):
            img.seek(i)
            frames.append(device._quantize(device._fit(img)))
            durations.append(img.info.get("duration", 100))
        keep = min(n, device.maxframes)
        speed = max(1, int(sum(durations) / len(durations)))
        if keep < n: speed = round(speed * n / keep)
        return [frames[i] for i in device.pick_frames(n, keep)], speed


def _run_case(case_name, device_cls=MiniToo, responder=media_responder, **kwargs):
    device, recorder, server_sock = make_connected_device(
        device_cls, responder=responder, **kwargs)
    try:
        dict(all_cases())[case_name](device)
    finally:
        device.disconnect()
        server_sock.close()
    return device, recorder.sent_messages


def _body(message):
    """Strip the envelope 01 <length LE16> <opcode> ... <checksum LE16> 02."""
    return message[4:-3]


def _chunk_index(message):
    """LE16 chunk index of a chunk packet, or None for the start packet."""
    body = _body(message)
    return int.from_bytes(body[5:7], "little") if body[0] == 0x01 else None


def _decoded_frames(messages):
    """Frame count, speed and the decompressed pixel buffer of a sent animation."""
    payload = bytearray()
    for message in messages[1:]:
        payload += _body(message)[7:]
    stream = bytes(payload[10:])
    raw = zstd.ZstdDecompressor().decompress(stream)
    return payload[1], int.from_bytes(payload[2:4], "big"), stream, raw


def test_await_request_sees_the_device_reply():
    """_await_request() sees the device's reply to the start packet. Without
    this test, a broken handshake would only slow the media cases down."""
    device, _, server_sock = make_connected_device(
        MiniToo, responder=media_responder)
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


@pytest.mark.parametrize("device_type", sorted(MEDIA_DEVICES))
@pytest.mark.parametrize("case_name", MEDIA_CASES)
def test_divoom128_media(case_name, device_type):
    bytes_per_pixel, window_log = MEDIA_DEVICE_SPECS[device_type]
    device, messages = _run_case(case_name, device_cls=DEVICE_CLASSES[device_type])
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
    # a wider window than the device announces would not decompress there
    assert zstd.get_frame_parameters(stream).window_size <= 1 << window_log
    raw = zstd.ZstdDecompressor().decompress(stream)
    assert len(raw) == frames * PIXELS * bytes_per_pixel

    path = _source_file(case_name)
    if path is None:
        # show_text: rebuilt glyphs would compare show_text against itself and
        # depend on the FreeType build, so length and framing above must do
        assert frames == 1
        return

    expected_frames, expected_speed = _expected_frames(device, path)
    assert frames == len(expected_frames)
    assert speed == expected_speed
    assert raw == b"".join(device._pixels(f) for f in expected_frames)

    if os.path.basename(path) == "smiley16.gif" and bytes_per_pixel == 3:
        assert hashlib.sha256(raw).hexdigest() == SMILEY16_RAW_SHA256


# --- resend requests (04 8b 55 01 <index LE16>) -----------------------------

RESEND_IMAGE = os.path.join(PIXELART_DIR, "ha32.gif")  # 9 chunks


def _run_show_image(responder, resendwindow=0.5, path=RESEND_IMAGE, time=None, device_cls=MiniToo):
    device, recorder, server_sock = make_connected_device(device_cls, responder=responder)
    device.resendwindow = resendwindow
    try:
        device.show_image(path, time=time)
    finally:
        device.disconnect()
        server_sock.close()
    return recorder.sent_messages


def test_resend_request_mid_stream():
    """A chunk the device asks for again has to go out again, byte for byte."""
    baseline = _run_show_image(media_responder)
    messages = _run_show_image(MediaResendResponder(1, after_chunks=3))

    assert len(messages) == len(baseline) + 1
    positions = [i for i, m in enumerate(messages) if _chunk_index(m) == 1]
    assert len(positions) == 2, "chunk 1 should have gone out twice"
    assert messages[positions[0]] == messages[positions[1]]
    assert positions[0] == 2  # start packet, chunk 0, chunk 1
    assert positions[1] > 3, "the copy is a reaction, not a duplicate send"
    # everything else is untouched: dropping the extra copy restores the baseline
    assert messages[:positions[1]] + messages[positions[1] + 1:] == baseline


def test_resend_request_in_the_linger_window():
    """A resend request arriving after the last chunk is still served, as
    _send_packets keeps listening for resendwindow seconds."""
    responder = MediaResendResponder(2, after_chunks=1, delay=0.15)
    messages = _run_show_image(responder)

    assert responder.requested, "the responder never got to ask"
    assert len([m for m in messages if _chunk_index(m) == 2]) == 2
    assert _chunk_index(messages[-1]) == 2, "the resend is the last thing sent"


def test_resend_request_with_unknown_index_is_ignored():
    baseline = _run_show_image(media_responder)
    messages = _run_show_image(MediaResendResponder(9999, after_chunks=2))
    assert messages == baseline


# --- size limits and quantization -----------------------------------

def _noise_gif(path, frames=20, seed=20240912):
    """A GIF that cannot be compressed away: full-entropy 128x128 noise. 20 of
    these frames exceed MEDIA_MAX_BYTES, so the encoder has to thin them out."""
    rnd = random.Random(seed)
    images = [
        Image.frombytes("RGB", (SCREEN, SCREEN),
                        bytes(rnd.getrandbits(8) for _ in range(BYTES_PER_FRAME)))
        for _ in range(frames)
    ]
    images[0].save(path, save_all=True, append_images=images[1:],
                   duration=100, loop=0)
    return path


def test_oversized_animation_is_thinned(tmp_path):
    path = _noise_gif(str(tmp_path / "noise.gif"))
    messages = _run_show_image(media_responder, path=path)
    frames, speed, stream, raw = _decoded_frames(messages)

    assert len(stream) <= MEDIA_MAX_BYTES
    assert 1 < frames < 20
    assert speed == round(100 * 20 / frames), "the cycle length is preserved by stretching speed"
    assert len(raw) == frames * BYTES_PER_FRAME

    device = MiniToo(mac="00:00:00:00:00:00")
    with Image.open(path) as img:
        source = []
        for i in range(img.n_frames):
            img.seek(i)
            source.append(device._quantize(device._fit(img)))
    assert raw == b"".join(device._pixels(source[i]) for i in device.pick_frames(20, frames))


def test_long_animation_is_thinned_evenly(tmp_path):
    """Over maxframes, frames are picked evenly over the whole animation
    instead of cutting it off."""
    count = 300
    path = solid_gif(str(tmp_path / "long.gif"), count)
    frames, speed, _, raw = _decoded_frames(_run_show_image(media_responder, path=path))

    assert frames == MiniToo.maxframes
    assert speed == round(100 * count / frames)
    picked = [tuple(raw[i * BYTES_PER_FRAME:i * BYTES_PER_FRAME + 3]) for i in range(frames)]
    assert picked == [solid_color(i * count // frames) for i in range(frames)]


def test_transparency_turns_black(tmp_path):
    """Transparent pixels show black, not the color they hide."""
    path = str(tmp_path / "half.png")
    img = Image.new("RGBA", (16, 16), (255, 255, 255, 0))
    img.paste((255, 0, 0, 255), (8, 0, 16, 16))
    img.save(path)
    frames, _, _, raw = _decoded_frames(_run_show_image(media_responder, path=path))

    assert frames == 1
    half = SCREEN * SCREEN // 2
    frame = Image.frombytes("RGB", (SCREEN, SCREEN), raw)
    assert sorted(frame.getcolors()) == [(half, (0, 0, 0)), (half, (255, 0, 0))]
    assert frame.getpixel((0, 0)) == (0, 0, 0)


def test_send_media_without_connection_encodes_nothing(monkeypatch):
    """Without a socket there is nobody to wait for, so skip the encoding too."""
    device = MiniToo(mac="00:00:00:00:00:00")

    def encode(*args, **kwargs):
        raise AssertionError("encoded without a connection")

    monkeypatch.setattr(device, "_encode_media", encode)
    assert device.send_media([Image.new("RGB", (SCREEN, SCREEN))]) is None


def test_flowtoo_pixels_are_rgb565_big_endian(tmp_path):
    """The FlowToo packs each pixel into two bytes, high byte first. The four
    quadrants are pinned by hand so _pixels is checked against the format, not
    against itself."""
    path = str(tmp_path / "quadrants.png")
    img = Image.new("RGB", (2, 2))
    img.putdata([(255, 255, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255)])
    img.save(path)
    frames, _, _, raw = _decoded_frames(
        _run_show_image(media_responder, path=path, device_cls=FlowToo))

    assert frames == 1
    half = SCREEN // 2
    corners = [raw[(y * SCREEN + x) * 2:(y * SCREEN + x) * 2 + 2].hex()
        for x, y in [(0, 0), (half, 0), (0, half), (half, half)]]
    assert corners == ["ffff", "f800", "07e0", "001f"]


def test_frames_are_quantized():
    """Frames are capped at 255 colors before compressing."""
    _, messages = _run_case(image_case_name("ha32.gif"))
    frames, _, _, raw = _decoded_frames(messages)

    for i in range(frames):
        frame = Image.frombytes(
            "RGB", (SCREEN, SCREEN),
            raw[i * BYTES_PER_FRAME:(i + 1) * BYTES_PER_FRAME])
        colors = frame.getcolors(maxcolors=1 << 16)
        assert colors is not None and len(colors) <= 255


# --- time and text layout -------------------------------------------

LONG_TEXT = " ".join(["Divoom"] * 40)


def _run_show_text(text, time=None):
    device, recorder, server_sock = make_connected_device(MiniToo, responder=media_responder)
    try:
        device.show_text(text, None, time=time)
    finally:
        device.disconnect()
        server_sock.close()
    return recorder.sent_messages


def test_image_time_sets_speed():
    path = os.path.join(PIXELART_DIR, "ha16.gif")
    frames, speed, _, raw = _decoded_frames(_run_show_image(media_responder, path=path))
    timed_frames, timed_speed, _, timed_raw = _decoded_frames(
        _run_show_image(media_responder, path=path, time=40))

    assert frames > 1 and speed != 40
    assert timed_speed == 40
    assert (timed_frames, timed_raw) == (frames, raw)


def test_long_text_scrolls_vertically():
    frames, speed, _, raw = _decoded_frames(_run_show_text(LONG_TEXT))

    assert 1 < frames <= MiniToo.maxframes
    assert speed == 100
    assert len(raw) == frames * BYTES_PER_FRAME
    assert set(raw[:BYTES_PER_FRAME]) == {0}, "the text starts below the screen"
    middle = frames // 2 * BYTES_PER_FRAME
    assert set(raw[middle:middle + BYTES_PER_FRAME]) != {0}


def test_long_text_time_sets_speed():
    _, speed, _, _ = _decoded_frames(_run_show_text(LONG_TEXT, time=40))
    assert speed == 40
