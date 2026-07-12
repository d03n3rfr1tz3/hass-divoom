"""Tests of devices/divoom.py: none of these touch the message bytes sent
over an already-open connection, only connection lifecycle/error-handling
behaviour, so they live separately from the golden-master and
protocol-helper tests."""
from __future__ import annotations

import errno
import logging
import socket

from custom_components.divoom.devices import divoom as divoom_module
from custom_components.divoom.devices.pixoo import Pixoo
from tests.support import make_connected_device


class _FailingConnectSocket:
    """Stands in for socket.socket(...) itself failing to connect."""

    def __init__(self, errno_value=errno.ECONNREFUSED):
        self._errno = errno_value

    def connect(self, addr):
        raise OSError(self._errno, "connection refused")

    def settimeout(self, *_args, **_kwargs):
        pass

    def close(self):
        pass


class _PassthroughSocket:
    """Wraps a real, already-connected socket so connect()/settimeout() are
    no-ops (the pair is connected via socket.socketpair() before the test
    even calls device.connect()), while still recording sendall() calls."""

    def __init__(self, real_socket):
        self._real = real_socket
        self.sent_messages: list[bytes] = []

    def connect(self, addr):
        pass

    def settimeout(self, *_args, **_kwargs):
        pass

    def sendall(self, data, *args, **kwargs):
        self.sent_messages.append(bytes(data))
        return self._real.sendall(data, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _FailingRecvSocket:
    """Selectable (via fileno()) but recv() always raises - simulates the
    peer resetting the connection after data has already arrived."""

    def __init__(self, real_socket):
        self._real = real_socket

    def recv(self, *args, **kwargs):
        raise OSError(errno.ECONNRESET, "connection reset")

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_message_buf_is_isolated_per_instance():
    """message_buf used to be a class attribute (a mutable list), so
    receive() on one device instance (self.message_buf += data) mutated the
    list shared by every Divoom instance."""
    device_a, recorder_a, server_a = make_connected_device(Pixoo)
    device_b, recorder_b, server_b = make_connected_device(Pixoo)
    try:
        server_a.send(b"\x01\x02\x03")
        device_a.receive()
    finally:
        device_a.disconnect()
        server_a.close()
        device_b.disconnect()
        server_b.close()

    assert device_a.message_buf == [0x01, 0x02, 0x03]
    assert device_b.message_buf == []


def test_receive_returns_zero_when_socket_is_none():
    device = Pixoo(mac="11:22:33:44:55:66")
    assert device.socket is None
    assert device.receive() == 0


def test_receive_returns_zero_when_nothing_ready():
    device, recorder, server_sock = make_connected_device(Pixoo)
    try:
        result = device.receive()
    finally:
        device.disconnect()
        server_sock.close()

    assert result == 0


def test_receive_returns_zero_on_socket_error():
    """recv() raising used to leave receive() falling off the end of the
    function, implicitly returning None; clear_input_buffer()'s
    `while self.receive() > 0` would then crash with a TypeError."""
    device, recorder, server_sock = make_connected_device(Pixoo)
    try:
        server_sock.send(b"\x01")
        device.socket = _FailingRecvSocket(recorder._real)
        result = device.receive()
    finally:
        device.socket = recorder
        device.disconnect()
        server_sock.close()

    assert result == 0
    assert device.socket_errno == errno.ECONNRESET


def test_connect_clears_socket_after_connection_failure(monkeypatch):
    """socket.connect() failing used to leave self.socket pointing at a
    never-connected socket object, so later code thought the device was
    connected."""
    device = Pixoo(mac="11:22:33:44:55:66")
    monkeypatch.setattr(
        divoom_module.socket, "socket", lambda *a, **kw: _FailingConnectSocket()
    )

    device.connect()

    assert device.socket is None
    assert device.socket_errno == errno.ECONNREFUSED


def test_connect_and_disconnect_host_mode_send_expected_handshake_bytes(monkeypatch):
    """The ESP32-proxy (host-mode) open/close handshake bytes were never
    covered by the golden-master suite (which only exercises mac/Bluetooth
    devices). This locks in the exact bytes across the send() -> sendall()
    change."""
    server_sock, client_sock = socket.socketpair()
    fake = _PassthroughSocket(client_sock)
    monkeypatch.setattr(divoom_module.socket, "socket", lambda *a, **kw: fake)
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)

    device = Pixoo(host="10.0.0.5", mac="11:22:33:44:55:66", port=1)
    try:
        device.connect()
        assert device.socket is fake
        assert fake.sent_messages == [
            bytes([0x69, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x01])
        ]

        device.disconnect()
        assert fake.sent_messages[-1] == bytes(
            [0x96, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66]
        )
        assert device.socket is None
    finally:
        server_sock.close()
        client_sock.close()


def test_connect_host_mode_handshake_failure_clears_socket(monkeypatch):
    """The 0x69 handshake send() used to be unguarded: a failure there
    raised straight out of connect() instead of being recorded like every
    other connection failure."""

    class _FailingHandshakeSocket:
        def connect(self, addr):
            pass

        def settimeout(self, *_args, **_kwargs):
            pass

        def sendall(self, data):
            raise OSError(errno.EPIPE, "broken pipe")

        def close(self):
            pass

    monkeypatch.setattr(
        divoom_module.socket, "socket", lambda *a, **kw: _FailingHandshakeSocket()
    )
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)

    device = Pixoo(host="10.0.0.5", mac="11:22:33:44:55:66", port=1)
    device.connect()

    assert device.socket is None
    assert device.socket_errno == errno.EPIPE


def test_reconnect_logs_error_after_exhausting_retries(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    device = Pixoo(mac="11:22:33:44:55:66")
    monkeypatch.setattr(
        divoom_module.socket, "socket", lambda *a, **kw: _FailingConnectSocket()
    )
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)

    device.reconnect(skipPing=True)

    assert device.socket is None
    assert "giving up after 5 attempts" in caplog.text


def test_send_payload_warns_when_socket_not_writable(monkeypatch, caplog):
    """A full send buffer used to silently drop the message (only
    socket_errno was set, with nothing logged)."""
    caplog.set_level(logging.WARNING)
    device, recorder, server_sock = make_connected_device(Pixoo)
    monkeypatch.setattr(divoom_module.select, "select", lambda *a, **kw: ([], [], []))
    try:
        result = device.send_command("set brightness", [50])
    finally:
        device.disconnect()
        server_sock.close()

    assert result == 0
    assert device.socket_errno == 98
    assert recorder.sent_messages == []
    assert "socket not writable" in caplog.text
