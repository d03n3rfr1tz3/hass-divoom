"""Tests of devices/divoom.py: none of these touch the message bytes sent
over an already-open connection, only connection lifecycle/error-handling
behaviour, so they live separately from the golden-master and
protocol-helper tests."""
from __future__ import annotations

import errno
import logging
import select
import socket
import threading

import pytest

from custom_components.divoom.devices import divoom as divoom_module
from custom_components.divoom.devices.minitoo import MiniToo
from custom_components.divoom.devices.pixoo import Pixoo
from tests.support import PeerSocket, _serve_forever, make_connected_device


@pytest.fixture(autouse=True)
def _ensure_bluetooth_socket_constants(monkeypatch):
    """AF_BLUETOOTH/BTPROTO_RFCOMM are missing on some Python builds without
    bluetooth headers (e.g. some CI runners). These tests mock socket.socket()
    entirely, so a placeholder value is enough to keep the attribute access
    from raising."""
    monkeypatch.setattr(socket, "AF_BLUETOOTH", getattr(socket, "AF_BLUETOOTH", 31), raising=False)
    monkeypatch.setattr(socket, "BTPROTO_RFCOMM", getattr(socket, "BTPROTO_RFCOMM", 3), raising=False)


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

    result = device.reconnect(skipPing=True)

    assert result is False
    assert device.socket is None
    assert "giving up after 5 attempts" in caplog.text


def test_reconnect_pings_without_socket_after_failed_connect(monkeypatch, caplog):
    """send_command used to return None without a socket, so the proxy
    reply check raised TypeError on list(None)."""
    caplog.set_level(logging.ERROR)
    device = Pixoo(host="10.0.0.5", mac="11:22:33:44:55:66")
    monkeypatch.setattr(
        divoom_module.socket, "socket", lambda *a, **kw: _FailingConnectSocket()
    )
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)

    result = device.reconnect()

    assert result is False
    assert device.socket is None
    assert "giving up after 5 attempts" in caplog.text


PROXY_BT_GONE = b"\x96"
DEVICE_REPLY = bytes.fromhex("0104000446004e0002")


def _answer_pings_with(reply):
    """Responder for the peer: answers every Divoom message (the ping), but
    not the proxy handshake, which does not end in 0x02."""
    return lambda data: reply if data.endswith(b"\x02") else None


def _proxy_connections(monkeypatch, *responders):
    """socket.socket() hands out one connected pair per call, each peer
    answering through its own responder."""
    clients, peers = [], []
    for responder in responders:
        server_sock, client_sock = socket.socketpair()
        thread = threading.Thread(target=_serve_forever, args=(server_sock, responder), daemon=True)
        thread.start()
        clients.append(_PassthroughSocket(client_sock))
        peers.append(PeerSocket(server_sock, thread))
    handout = iter(clients)
    monkeypatch.setattr(divoom_module.socket, "socket", lambda *a, **kw: next(handout))
    return clients, peers


def _record_select_timeouts(monkeypatch, writes=False):
    real_select = divoom_module.select.select
    timeouts = []

    def recording_select(rlist, wlist, xlist, timeout):
        if wlist if writes else rlist:
            timeouts.append(timeout)
        return real_select(rlist, wlist, xlist, timeout)

    monkeypatch.setattr(divoom_module.select, "select", recording_select)
    return timeouts


def test_reconnect_pings_after_rebuilding_the_connection(monkeypatch, caplog):
    """The retry loop used to stop as soon as TCP was up again, so the next
    command went out while the proxy had no bluetooth link and got lost."""
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)
    clients, peers = _proxy_connections(
        monkeypatch, _answer_pings_with(PROXY_BT_GONE), _answer_pings_with(DEVICE_REPLY))
    device = Pixoo(host="10.0.0.5", mac="11:22:33:44:55:66", port=1)
    try:
        result = device.reconnect()
        assert device.socket is clients[1]
    finally:
        device.disconnect()
        for peer in peers:
            peer.close()

    assert result is True
    assert caplog.text.count("Trying to reconnect") == 1
    assert "giving up" not in caplog.text


def test_send_ping_skips_stale_replies_via_proxy():
    """A reply to an earlier command still waiting in the socket used to be
    taken as the ping's answer, hiding the proxy's 0x96."""
    device, recorder, server_sock = make_connected_device(
        Pixoo, host="10.0.0.5", responder=_answer_pings_with(PROXY_BT_GONE))
    try:
        server_sock.sendall(DEVICE_REPLY)
        select.select([recorder], [], [], 1)
        result = device.send_ping()
    finally:
        device.disconnect()
        server_sock.close()

    assert result == PROXY_BT_GONE


def test_reconnect_ping_waits_for_the_proxy_bluetooth_connect(monkeypatch):
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)
    clients, peers = _proxy_connections(monkeypatch, _answer_pings_with(DEVICE_REPLY))
    timeouts = _record_select_timeouts(monkeypatch)
    device = Pixoo(host="10.0.0.5", mac="11:22:33:44:55:66", port=1)
    try:
        device.reconnect()
    finally:
        device.disconnect()
        peers[0].close()

    assert timeouts == [0, 10]


@pytest.mark.parametrize(("host", "expected"), [(None, [0.2]), ("10.0.0.5", [0, 2])])
def test_reconnect_ping_window_on_an_open_connection(monkeypatch, host, expected):
    device, _, server_sock = make_connected_device(
        Pixoo, host=host, responder=_answer_pings_with(DEVICE_REPLY))
    timeouts = _record_select_timeouts(monkeypatch)
    try:
        device.reconnect()
    finally:
        device.disconnect()
        server_sock.close()

    assert timeouts == expected


def test_send_payload_paces_every_write(monkeypatch):
    """send_payload is the one write path all devices share, so the pause
    belongs there - once per message, after the write, and only when one
    actually happened."""
    slept = []
    monkeypatch.setattr(divoom_module.time, "sleep", slept.append)
    device, _, server_sock = make_connected_device(Pixoo)
    device.senddelay = 0.015
    try:
        device.send_command("set brightness", [50])
        device.send_command("set brightness", [60])
        device.send_command("set brightness", [70])
    finally:
        device.disconnect()
        server_sock.close()

    assert slept == [0.015, 0.015, 0.015]


def test_send_payload_does_not_pace_via_proxy(monkeypatch):
    slept = []
    monkeypatch.setattr(divoom_module.time, "sleep", slept.append)
    device, _, server_sock = make_connected_device(Pixoo, host="10.0.0.5")
    device.senddelay = 0.015
    try:
        device.send_command("set brightness", [50])
        device.send_command("set brightness", [60])
    finally:
        device.disconnect()
        server_sock.close()

    assert slept == []


def test_send_payload_paces_a_128_device_via_proxy(monkeypatch):
    """The 128 upload listens for resend requests in a fixed window, so it
    must not run ahead of the device through the proxy's buffers."""
    slept = []
    monkeypatch.setattr(divoom_module.time, "sleep", slept.append)
    device, _, server_sock = make_connected_device(MiniToo, host="10.0.0.5")
    device.senddelay = 0.015
    try:
        device.send_command("set brightness", [50])
        device.send_command("set brightness", [60])
    finally:
        device.disconnect()
        server_sock.close()

    assert slept == [0.015, 0.015]


class _OptionRecordingSocket:
    """Records setsockopt(); a socketpair is AF_UNIX on Linux and would
    reject TCP options."""

    def __init__(self):
        self.options = []

    def setsockopt(self, level, option, value):
        self.options.append((level, option, value))

    def connect(self, addr):
        pass

    def settimeout(self, *_args, **_kwargs):
        pass

    def sendall(self, data):
        pass

    def close(self):
        pass


@pytest.mark.parametrize(
    ("device_cls", "expected"),
    [(MiniToo, [(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]), (Pixoo, [])],
)
def test_connect_disables_nagle_only_for_proxy_pacing(monkeypatch, device_cls, expected):
    """Nagle would bundle the paced chunks again; the 16/32 burst keeps it."""
    fake = _OptionRecordingSocket()
    monkeypatch.setattr(divoom_module.socket, "socket", lambda *a, **kw: fake)
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)

    device_cls(host="10.0.0.5", mac="11:22:33:44:55:66").connect()

    assert fake.options == expected


@pytest.mark.parametrize(("host", "expected"), [(None, [0.1]), ("10.0.0.5", [3])])
def test_send_payload_waits_for_the_proxy_to_take_more(monkeypatch, host, expected):
    """A proxy pushing back used to get the message dropped after 0.1s."""
    device, _, server_sock = make_connected_device(Pixoo, host=host)
    timeouts = _record_select_timeouts(monkeypatch, writes=True)
    try:
        device.send_command("set brightness", [50])
    finally:
        device.disconnect()
        server_sock.close()

    assert timeouts == expected


@pytest.mark.parametrize(("host", "expected"), [(None, 0.5), ("10.0.0.5", 1.0)])
def test_resend_window_allows_for_the_proxy_delay(host, expected):
    assert MiniToo(host=host, mac="11:22:33:44:55:66").resendwindow == expected


def test_send_payload_does_not_pace_a_dropped_message(monkeypatch):
    slept = []
    monkeypatch.setattr(divoom_module.time, "sleep", slept.append)
    device, _, server_sock = make_connected_device(Pixoo)
    device.senddelay = 0.015
    monkeypatch.setattr(divoom_module.select, "select", lambda *a, **kw: ([], [], []))
    try:
        device.send_command("set brightness", [50])
    finally:
        device.disconnect()
        server_sock.close()

    assert slept == []


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
