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

GOLDEN_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "goldens"))


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


def _drain_forever(sock: socket.socket) -> None:
    try:
        while sock.recv(65536):
            pass
    except OSError:
        pass


def make_connected_device(device_cls, mac="11:22:33:44:55:66", **kwargs):
    """Instantiate a device with a live, already "connected" socket pair,
    bypassing connect() so tests need no real Bluetooth/TCP hardware.

    Returns (device, recorder, server_sock). Call device.disconnect() and
    server_sock.close() when done.
    """
    device = device_cls(mac=mac, **kwargs)
    server_sock, client_sock = socket.socketpair()
    client_sock.settimeout(3)
    recorder = RecordingSocket(client_sock)
    device.socket = recorder
    device.socket_errno = 0

    # Keep the peer side drained so a chunked animation with many chunks
    # can never block on a full socket buffer.
    drainer = threading.Thread(target=_drain_forever, args=(server_sock,), daemon=True)
    drainer.start()

    return device, recorder, server_sock


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
