"""Shared helpers for the golden-master test suite.

RecordingSocket wraps one end of a real socketpair, so select, send and recv
behave as in production, and records every send()/sendall() as one message.
"""
from __future__ import annotations

import os
import socket
import threading
import time

GOLDEN_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "goldens"))

MEDIA_START_PREFIX = b"\x01\x08\x00\x8b\x00"
MEDIA_READY = bytes.fromhex("01060004 8b5500 ea0002")


class RecordingSocket:
    """Proxy around a real socket that records each send()/sendall() call."""

    def __init__(self, real_socket):
        self._real = real_socket
        self.sent_messages: list[bytes] = []

    def send(self, data, *args, **kwargs):
        self.sent_messages.append(bytes(data))
        return self._real.send(data, *args, **kwargs)

    def sendall(self, data, *args, **kwargs):
        self.sent_messages.append(bytes(data))
        return self._real.sendall(data, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class ConnectedSocket(RecordingSocket):
    """RecordingSocket for tests that go through connect(): the pair is already
    connected, so connect()/settimeout() have nothing left to do."""

    def connect(self, addr):
        pass

    def settimeout(self, *_args, **_kwargs):
        pass


class FakeSocket:
    """Stand-in for socket.socket() itself, for tests that drive connect()
    without a real pair behind it. Records every call in order and raises where
    the test asks it to. Handed out for every socket.socket() call, so one
    instance holds a whole retry sequence."""

    def __init__(self, bind_error=None, connect_error=None, send_error=None, shutdown_error=None):
        self.calls: list[tuple] = []
        self._errors = {"bind": bind_error, "connect": connect_error, "sendall": send_error,
                        "shutdown": shutdown_error}

    def _record(self, name, *args):
        self.calls.append((name, *args))
        error = self._errors.get(name)
        if error is not None:
            raise error

    def settimeout(self, value):
        self._record("settimeout", value)

    def bind(self, addr):
        self._record("bind", addr)

    def connect(self, addr):
        self._record("connect", addr)

    def sendall(self, data, *_args, **_kwargs):
        self._record("sendall", bytes(data))
        return len(data)

    def shutdown(self, how):
        self._record("shutdown")

    def close(self):
        self._record("close")

    @property
    def sent_messages(self) -> list[bytes]:
        return [args[0] for name, *args in self.calls if name == "sendall"]

    def timeouts(self) -> list:
        return [args[0] for name, *args in self.calls if name == "settimeout"]


def media_responder(data: bytes) -> bytes | None:
    """Answer a 0x8b start packet the way a 128x128 device does, with "send the
    animation"."""
    return MEDIA_READY if data.startswith(MEDIA_START_PREFIX) else None


def media_resend_request(index: int) -> bytes:
    """The device's "resend the chunk at index" message: 04 8b 55 01 <index LE16>.
    Envelope and checksum come from a 128x128 device's make_message."""
    from custom_components.divoom.devices.minitoo import MiniToo

    args = [0x8B, 0x55, 0x01] + list(int(index).to_bytes(2, "little"))
    payload = list((len(args) + 3).to_bytes(2, "little")) + [0x04] + args
    return bytes(MiniToo(mac="00:00:00:00:00:00").make_message(payload))


class MediaResendResponder:
    """Responder that answers the start packet and then, once `after_chunks` chunk
    packets have arrived, asks a single time for `index` to be resent.

    `delay` holds that request back by as many seconds, so it arrives only
    after the last chunk."""

    def __init__(self, index: int, after_chunks: int = 3, delay: float = 0.0):
        self.index = index
        self.after_chunks = after_chunks
        self.delay = delay
        self.chunks_seen = 0
        self.requested = False

    def __call__(self, data: bytes) -> bytes | None:
        if data.startswith(MEDIA_START_PREFIX):
            return MEDIA_READY
        self.chunks_seen += 1
        if self.requested or self.chunks_seen < self.after_chunks:
            return None
        self.requested = True
        if self.delay:
            time.sleep(self.delay)
        return media_resend_request(self.index)


def _serve_forever(sock: socket.socket, responder) -> None:
    buf = b""
    try:
        while True:
            data = sock.recv(65536)
            if not data:
                break
            if responder is None:
                continue
            buf += data

            while len(buf) >= 3:
                size = int.from_bytes(buf[1:3], "little") + 4 if buf[0] == 0x01 else len(buf)
                if len(buf) < size:
                    break
                message, buf = buf[:size], buf[size:]
                reply = responder(message)
                if reply:
                    sock.sendall(reply)
    except OSError:
        pass


def make_connected_device(device_cls, mac="11:22:33:44:55:66", responder=None, **kwargs):
    """Instantiate a device with a live, already "connected" socket pair,
    bypassing connect() so tests need no real Bluetooth/TCP hardware.

    `responder` is an optional callback receiving each message read from the
    device; whatever it returns is sent back. Without one the peer only drains.

    Returns (device, recorder, server_sock). Call device.disconnect() and
    server_sock.close() when done.
    """
    device = device_cls(mac=mac, **kwargs)
    server_sock, client_sock = socket.socketpair()
    client_sock.settimeout(3)
    recorder = RecordingSocket(client_sock)
    device.socket = recorder
    device.socket_errno = 0

    # send pacing is only needed by real hardware
    device.senddelay = 0

    # shorter resend window to keep the suite fast, resend tests raise it themselves
    if hasattr(device, "resendwindow"):
        device.resendwindow = 0.2

    # Keep the peer side drained so a chunked animation with many chunks
    # can never block on a full socket buffer.
    drainer = threading.Thread(
        target=_serve_forever, args=(server_sock, responder), daemon=True)
    drainer.start()

    return device, recorder, PeerSocket(server_sock, drainer)


class PeerSocket:
    """Peer end of the pair; close() also waits for its drain thread."""

    def __init__(self, real_socket, thread):
        self._real = real_socket
        self._thread = thread

    def close(self):
        # close() alone does not wake a blocked recv() on Linux
        try:
            self._real.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._thread.join(timeout=5)
        self._real.close()

    def __getattr__(self, name):
        return getattr(self._real, name)


def solid_color(index: int) -> tuple[int, int, int]:
    """A distinct color per frame index, below 512."""
    return (index % 256, index // 256 * 64, 128)


def solid_gif(path: str, frames: int, duration: int = 100, size: int = 16) -> str:
    """An animation of solid frames in solid_color(index). Distinct colors keep
    GIF saving from merging frames, and each frame tells where it came from."""
    from PIL import Image

    images = [Image.new("RGB", (size, size), solid_color(i)) for i in range(frames)]
    images[0].save(path, save_all=True, append_images=images[1:], duration=duration, loop=0)
    return path


def hexdump(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data)


def format_golden(messages: list[bytes]) -> str:
    """One hex-dumped message per line."""
    return "".join(hexdump(m) + "\n" for m in messages)


def parse_golden(text: str) -> list[bytes]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [bytes.fromhex(line.replace(" ", "")) for line in lines]


def unescape_message(message: bytes) -> bytes:
    """Reverse Divoom.escape_payload's 0x03,X -> X-0x03 substitution.

    With escapePayload, the wire length depends on how many payload bytes fall
    into 0x01-0x03. Comparing unescaped messages removes that variance."""
    result = bytearray()
    i = 0
    while i < len(message):
        b = message[i]
        if b == 0x03 and i + 1 < len(message) and message[i + 1] in (0x04, 0x05, 0x06):
            result.append(message[i + 1] - 0x03)
            i += 2
        else:
            result.append(b)
            i += 1
    return bytes(result)
