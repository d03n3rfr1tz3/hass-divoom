"""Shared helpers for the golden-master test suite.

The core trick: `device.socket` only needs to behave like a real connected
socket (`select.select`, `.send()`/`.sendall()`, `.recv()`, `.fileno()`).
`RecordingSocket` wraps one end of a real `socket.socketpair()` so all of
that keeps working exactly as in production, while additionally recording
every `send()`/`sendall()` call as one separate captured message.
"""
from __future__ import annotations

import os
import socket
import threading
import time

GOLDEN_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "goldens"))

MINITOO_START_PREFIX = b"\x01\x08\x00\x8b\x00"
MINITOO_READY = bytes.fromhex("01060004 8b5500 ea0002")


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


def minitoo_responder(data: bytes) -> bytes | None:
    """Answer a 0x8b start packet the way a real MiniToo does: "send the
    animation". Without it MiniToo._await_request() runs into its 2s timeout
    on every media case and the handshake stays untested."""
    return MINITOO_READY if data.startswith(MINITOO_START_PREFIX) else None


def minitoo_resend_request(index: int) -> bytes:
    """The device's "resend the chunk at index" message: 04 8b 55 01 <index LE16>.
    Built through MiniToo.make_message so the envelope and checksum come from the
    implementation, not from hand."""
    from custom_components.divoom.devices.minitoo import MiniToo

    args = [0x8B, 0x55, 0x01] + list(int(index).to_bytes(2, "little"))
    payload = list((len(args) + 3).to_bytes(2, "little")) + [0x04] + args
    return bytes(MiniToo(mac="00:00:00:00:00:00").make_message(payload))


class MiniTooResendResponder:
    """Responder that answers the start packet and then, once `after_chunks` chunk
    packets have arrived, asks a single time for `index` to be resent.

    `delay` holds that answer back by that many seconds, which is how the
    linger-window case is reached: the stream is long over by then, so the
    request can only be served after the last chunk."""

    def __init__(self, index: int, after_chunks: int = 3, delay: float = 0.0):
        self.index = index
        self.after_chunks = after_chunks
        self.delay = delay
        self.chunks_seen = 0
        self.requested = False

    def __call__(self, data: bytes) -> bytes | None:
        if data.startswith(MINITOO_START_PREFIX):
            return MINITOO_READY
        self.chunks_seen += 1
        if self.requested or self.chunks_seen < self.after_chunks:
            return None
        self.requested = True
        if self.delay:
            time.sleep(self.delay)
        return minitoo_resend_request(self.index)


def _serve_forever(sock: socket.socket, responder) -> None:
    try:
        while True:
            data = sock.recv(65536)
            if not data:
                break
            reply = responder(data) if responder is not None else None
            if reply:
                sock.sendall(reply)
    except OSError:
        pass


def make_connected_device(device_cls, mac="11:22:33:44:55:66", responder=None, **kwargs):
    """Instantiate a device with a live, already "connected" socket pair,
    bypassing connect() so tests need no real Bluetooth/TCP hardware.

    `responder` is an optional callback receiving each chunk of bytes read
    from the device; whatever it returns is sent back. Without one the peer
    only drains, exactly as before.

    Returns (device, recorder, server_sock). Call device.disconnect() and
    server_sock.close() when done.
    """
    device = device_cls(mac=mac, **kwargs)
    server_sock, client_sock = socket.socketpair()
    client_sock.settimeout(3)
    recorder = RecordingSocket(client_sock)
    device.socket = recorder
    device.socket_errno = 0

    # Send pacing is meant for real hardware; over a socketpair it is pure
    # sleeping - roughly 16s across the suite for the MiniToo alone.
    device.senddelay = 0

    # Likewise the window MiniToo keeps listening for resend requests in: 0.5s
    # per media case would dominate the suite, 0.2s matches what the
    # clear_input_buffer() it replaced used to cost. Tests that exercise a
    # resend raise it themselves.
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

    Devices with escapePayload=True (e.g. TimeboxMini) escape every 0x01-0x03
    byte in the checksummed payload as a 2-byte sequence, so the *wire*
    length of an otherwise-identical message varies with how many payload
    bytes happen to fall in that range. Comparing messages after unescaping
    removes that variance while still catching any real structural
    difference (frame count, command, sizes)."""
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
