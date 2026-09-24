"""Connection lifecycle and error handling of devices/divoom.py."""
from __future__ import annotations

import errno
import logging
import os
import select
import socket
import threading

import pytest

from custom_components.divoom.devices import divoom as divoom_module
from custom_components.divoom.devices.divoom import Divoom
from custom_components.divoom.devices.divoom128 import Divoom128
from custom_components.divoom.devices.minitoo import MiniToo
from custom_components.divoom.devices.pixoo import Pixoo
from tests.cases import PIXELART_DIR
from tests.support import (
    ConnectedSocket,
    FakeSocket,
    PeerSocket,
    _serve_forever,
    make_connected_device,
    media_responder,
)


@pytest.fixture(autouse=True)
def _ensure_bluetooth_socket_constants(monkeypatch):
    """AF_BLUETOOTH/BTPROTO_RFCOMM are missing on Python builds without
    bluetooth headers. socket.socket() is mocked here, so placeholders suffice."""
    monkeypatch.setattr(socket, "AF_BLUETOOTH", getattr(socket, "AF_BLUETOOTH", 31), raising=False)
    monkeypatch.setattr(socket, "BTPROTO_RFCOMM", getattr(socket, "BTPROTO_RFCOMM", 3), raising=False)


# --- test doubles ---


class _FailingRecvSocket:
    """Selectable (via fileno()) but recv() always raises - simulates the
    peer resetting the connection after data has already arrived."""

    def __init__(self, real_socket):
        self._real = real_socket

    def recv(self, *args, **kwargs):
        raise OSError(errno.ECONNRESET, "connection reset")

    def __getattr__(self, name):
        return getattr(self._real, name)


def _hands_out(monkeypatch, fake):
    """Every socket.socket() in the device module returns this stand-in, so one
    instance records the whole retry sequence."""
    monkeypatch.setattr(divoom_module.socket, "socket", lambda *_a, **_kw: fake)
    return fake


# --- peer behaviour and probes ---

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
        clients.append(ConnectedSocket(client_sock))
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


# --- receive() ---


def test_message_buf_is_isolated_per_instance():
    """Each instance has its own message_buf, so receiving on one device leaves
    the others untouched."""
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
    """recv() raising makes receive() return 0, so `while self.receive() > 0`
    loops end cleanly."""
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


# --- connect() ---


def test_connect_clears_socket_after_connection_failure(monkeypatch):
    """A failed socket.connect() leaves no socket behind, so the device does
    not count as connected."""
    device = Pixoo(mac="11:22:33:44:55:66")
    _hands_out(monkeypatch, FakeSocket(connect_error=OSError(errno.ECONNREFUSED, "refused")))

    device.connect()

    assert device.socket is None
    assert device.socket_errno == errno.ECONNREFUSED


def test_connect_bounds_the_connect_itself(monkeypatch):
    """The timeout is set before connect(), so an unanswered bluetooth connect
    cannot hold the executor thread and the device lock indefinitely."""
    fake = _hands_out(monkeypatch, FakeSocket())

    device = Pixoo(mac="11:22:33:44:55:66")
    device.connect()

    assert fake.calls == [
        ("settimeout", 10),
        ("connect", ("11:22:33:44:55:66", 1)),
        ("settimeout", 3),
    ]


def test_connect_binds_to_the_configured_adapter(monkeypatch):
    """The socket binds to the configured adapter, so on a host with several
    adapters the connection goes out through the one the device is paired with."""
    fake = _hands_out(monkeypatch, FakeSocket())

    device = Pixoo(adapter="AA:BB:CC:DD:EE:FF", mac="11:22:33:44:55:66")
    device.connect()

    assert fake.calls == [
        ("settimeout", 10),
        ("bind", ("AA:BB:CC:DD:EE:FF", 0)),
        ("connect", ("11:22:33:44:55:66", 1)),
        ("settimeout", 3),
    ]


def test_connect_without_adapter_does_not_bind(monkeypatch):
    """Without a configured adapter, the kernel routes the connection."""
    fake = _hands_out(monkeypatch, FakeSocket())

    device = Pixoo(mac="11:22:33:44:55:66")
    device.connect()

    assert [name for name, *_args in fake.calls] == ["settimeout", "connect", "settimeout"]


def test_connect_host_mode_ignores_the_adapter(monkeypatch):
    """Host mode talks TCP to the ESP32 proxy, so a local bluetooth adapter
    has no meaning there."""
    fake = _hands_out(monkeypatch, FakeSocket())
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)

    device = Pixoo(adapter="AA:BB:CC:DD:EE:FF", host="10.0.0.5", mac="11:22:33:44:55:66")
    device.connect()

    assert device.socket is fake
    assert "bind" not in [name for name, *_args in fake.calls]


def test_connect_clears_socket_after_bind_failure(monkeypatch):
    """A bind() failure, e.g. from an unplugged dongle, is recorded like any
    other connection failure and leaves no socket behind."""
    _hands_out(monkeypatch, FakeSocket(bind_error=OSError(errno.EADDRNOTAVAIL, "not available")))

    device = Pixoo(adapter="AA:BB:CC:DD:EE:FF", mac="11:22:33:44:55:66")
    device.connect()

    assert device.socket is None
    assert device.socket_errno == errno.EADDRNOTAVAIL


def test_connect_timeout_is_recorded_as_a_failure(monkeypatch):
    """A timed out connect counts as a failure, although TimeoutError carries
    no errno."""
    _hands_out(monkeypatch, FakeSocket(connect_error=TimeoutError("timed out")))
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)

    device = Pixoo(mac="11:22:33:44:55:66")

    assert device.reconnect() is False
    assert device.socket is None
    assert device.socket_errno == errno.ETIMEDOUT


def test_connect_and_disconnect_host_mode_send_expected_handshake_bytes(monkeypatch):
    """The ESP32 proxy open/close handshake, which the golden-master suite
    does not cover."""
    fake = _hands_out(monkeypatch, FakeSocket())
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)

    device = Pixoo(host="10.0.0.5", mac="11:22:33:44:55:66", port=1)
    device.connect()

    assert device.socket is fake
    assert fake.sent_messages == [
        bytes([0x69, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x01])
    ]

    device.disconnect()

    assert fake.sent_messages[-1] == bytes([0x96, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66])
    assert device.socket is None


def test_connect_host_mode_handshake_failure_clears_socket(monkeypatch):
    """A failing 0x69 handshake is recorded like any other connection failure
    instead of raising out of connect()."""
    _hands_out(monkeypatch, FakeSocket(send_error=OSError(errno.EPIPE, "broken pipe")))
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)

    device = Pixoo(host="10.0.0.5", mac="11:22:33:44:55:66", port=1)
    device.connect()

    assert device.socket is None
    assert device.socket_errno == errno.EPIPE


# --- reconnect() ---


@pytest.mark.parametrize(
    ("host", "skip_ping"),
    [(None, True), ("10.0.0.5", None)],
    ids=["direct-without-a-ping", "proxy-pinging-without-a-socket"],
)
def test_reconnect_gives_up_after_exhausting_retries(monkeypatch, caplog, host, skip_ping):
    """Via the proxy, the reply check copes with a missing socket and still
    reaches the retry limit."""
    caplog.set_level(logging.ERROR)
    device = Pixoo(host=host, mac="11:22:33:44:55:66")
    _hands_out(monkeypatch, FakeSocket(connect_error=OSError(errno.ECONNREFUSED, "refused")))
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)

    result = device.reconnect(skipPing=skip_ping)

    assert result is False
    assert device.socket is None
    assert "giving up after 3 attempts" in caplog.text


def test_reconnect_waits_before_every_retry_and_stays_within_budget(monkeypatch):
    """Every retry waits after disconnect(), as bluetooth answers an instant
    reconnect with EBUSY, and all attempts together stay within a time budget."""
    slept = []
    fake = _hands_out(monkeypatch, FakeSocket(connect_error=OSError(errno.EHOSTDOWN, "host is down")))
    monkeypatch.setattr(divoom_module.time, "sleep", slept.append)

    device = Pixoo(mac="11:22:33:44:55:66")

    assert device.reconnect(skipPing=True) is False
    # 0.5 settles after each attempt, 1/2/3 back off before each retry
    assert slept == [0.5, 1, 0.5, 2, 0.5, 3, 0.5]
    assert fake.timeouts() == [10, 3, 3, 3]
    assert sum(slept) + sum(fake.timeouts()) < 30


def test_reconnect_pings_after_rebuilding_the_connection(monkeypatch, caplog):
    """A rebuilt proxy connection counts only once the ping confirms the
    proxy's bluetooth link, so the next command does not get lost."""
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


def test_reconnect_ignores_an_errno_from_an_earlier_failure(caplog):
    """An errno left over from an earlier call does not tear down a healthy
    link."""
    device, recorder, server_sock = make_connected_device(Pixoo)
    socket_before = device.socket
    device.socket_errno = errno.ECONNRESET # left over from an earlier call
    try:
        with caplog.at_level(logging.WARNING):
            result = device.reconnect(skipPing=True)
    finally:
        device.disconnect()
        server_sock.close()

    assert result is True
    assert socket_before is recorder
    assert "connection lost" not in caplog.text


@pytest.mark.parametrize("host", [None, "10.0.0.5"], ids=["ping", "proxy-handshake"])
def test_reconnect_treats_a_timeout_as_a_failure(monkeypatch, host):
    """A timed out ping or proxy handshake counts as a failure, although a
    timeout carries no errno."""
    _hands_out(monkeypatch, FakeSocket(send_error=TimeoutError("timed out")))
    monkeypatch.setattr(divoom_module.time, "sleep", lambda *_args: None)
    monkeypatch.setattr(divoom_module.select, "select", lambda r, w, x, t: ([], w, []))

    device = Pixoo(host=host, mac="11:22:33:44:55:66")

    assert device.reconnect() is False
    assert device.socket_errno == errno.ETIMEDOUT


# --- the ping window ---


def test_send_ping_skips_stale_replies_via_proxy():
    """Replies to earlier commands still waiting in the socket are skipped, so
    the ping sees the proxy's 0x96."""
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


# --- per-device defaults ---


def test_senddelay_defaults_are_per_device_family():
    """Only Divoom128 paces its writes, as only it can ask for a chunk again.
    Checked on the classes, since the other tests set senddelay by hand."""
    assert Divoom.senddelay == 0
    assert Divoom128.senddelay == 0.015


@pytest.mark.parametrize(("host", "expected"), [(None, 0.5), ("10.0.0.5", 1.0)])
def test_resend_window_allows_for_the_proxy_delay(host, expected):
    assert MiniToo(host=host, mac="11:22:33:44:55:66").resendwindow == expected


# --- pacing ---


def test_send_payload_paces_every_write(monkeypatch):
    """send_payload pauses once per message, after the write."""
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


@pytest.mark.parametrize("host", [None, "10.0.0.5"])
def test_send_payload_does_not_pace_a_classic_device(monkeypatch, host):
    """senddelay describes the device, not the transport. Read off the class,
    as support.py zeroes it."""
    slept = []
    monkeypatch.setattr(divoom_module.time, "sleep", slept.append)
    device, _, server_sock = make_connected_device(Pixoo, host=host)
    device.senddelay = type(device).senddelay
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


# --- write window and aborts ---


@pytest.mark.parametrize("host", [None, "10.0.0.5"])
def test_send_payload_waits_for_the_link_to_take_more(monkeypatch, host):
    """A device pushing back gets the socket's full 3s timeout to take more
    data, on both paths."""
    device, _, server_sock = make_connected_device(Pixoo, host=host)
    timeouts = _record_select_timeouts(monkeypatch, writes=True)
    try:
        device.send_command("set brightness", [50])
    finally:
        device.disconnect()
        server_sock.close()

    assert timeouts == [3]


def test_send_payload_aborts_when_socket_not_writable(monkeypatch, caplog):
    """A send buffer that stays full aborts with an error instead of dropping
    the message silently. Without a write, nothing is paced."""
    caplog.set_level(logging.ERROR)
    slept = []
    monkeypatch.setattr(divoom_module.time, "sleep", slept.append)
    device, recorder, server_sock = make_connected_device(Pixoo)
    device.senddelay = 0.015
    monkeypatch.setattr(divoom_module.select, "select", lambda *a, **kw: ([], [], []))
    try:
        with pytest.raises(TimeoutError):
            device.send_command("set brightness", [50])
    finally:
        device.disconnect()
        server_sock.close()

    assert device.socket_errno == 98
    assert recorder.sent_messages == []
    assert slept == []
    assert "socket not writable" in caplog.text


def test_show_image_stops_after_an_undeliverable_chunk(monkeypatch):
    """The chunk stream carries a total size and an index, so a gap cannot be
    recovered from. Sending the rest is wasted effort on a dead link."""
    device, recorder, server_sock = make_connected_device(Pixoo)
    real_select = divoom_module.select.select
    remaining = [2] # let the first chunks out, then have the link go quiet

    def stalling_select(rlist, wlist, xlist, timeout):
        if wlist and not rlist:
            if remaining[0] <= 0: return ([], [], [])
            remaining[0] -= 1
        return real_select(rlist, wlist, xlist, timeout)

    monkeypatch.setattr(divoom_module.select, "select", stalling_select)
    try:
        with pytest.raises(TimeoutError):
            device.show_image(os.path.join(PIXELART_DIR, "ha16.gif"))
    finally:
        device.disconnect()
        server_sock.close()

    assert len(recorder.sent_messages) == 2


def test_show_image_reports_a_link_that_went_away_mid_transfer():
    """A socket that disappears mid-animation makes show_image raise instead
    of reporting success."""
    device, recorder, server_sock = make_connected_device(Pixoo)
    real_sendall = recorder.sendall

    def sendall(data):
        real_sendall(data)
        if len(recorder.sent_messages) == 2:
            device.socket = None # what a concurrent disconnect() does

    recorder.sendall = sendall
    try:
        with pytest.raises(OSError) as excinfo:
            device.show_image(os.path.join(PIXELART_DIR, "ha16.gif"))
    finally:
        device.disconnect()
        server_sock.close()

    assert excinfo.value.errno == errno.ENOTCONN
    assert "truncated after 2 chunks" in str(excinfo.value)
    assert len(recorder.sent_messages) == 2


# --- reading back ---


def _record_skip_read(monkeypatch):
    """The skipRead every command reaches send_payload with, in order."""
    real_send_payload = Divoom.send_payload
    flags = []

    def recording(self, payload, skipRead=None, timeout=0.2):
        flags.append(skipRead)
        return real_send_payload(self, payload, skipRead=skipRead, timeout=timeout)

    monkeypatch.setattr(divoom_module.Divoom, "send_payload", recording)
    return flags


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (lambda device: device.send_ping(), [False]),
        (lambda device: device.send_brightness(42), [True]),
        (lambda device: device.show_light(color=[0x20, 0x40, 0x60]), [None]),
    ],
    ids=["send_ping", "send_brightness", "show_light"],
)
def test_only_the_ping_waits_for_a_reply(monkeypatch, call, expected):
    """Only send_ping sets skipRead=False. Every other call site sends without
    waiting or keeps the default, which reads only with debug logging. No golden
    covers this, as skipRead changes no byte on the wire."""
    flags = _record_skip_read(monkeypatch)
    device, _, server_sock = make_connected_device(
        Pixoo, responder=_answer_pings_with(DEVICE_REPLY))
    try:
        call(device)
    finally:
        device.disconnect()
        server_sock.close()

    assert flags == expected


@pytest.mark.parametrize(
    ("device_cls", "responder", "image"),
    [(Pixoo, None, "ha16.gif"), (MiniToo, media_responder, "ha32.gif")],
    ids=["classic", "divoom128"],
)
def test_show_image_never_blocks_between_chunks(monkeypatch, device_cls, responder, image):
    """No chunk may wait for a reply inside send_payload. The 128 devices do read
    between chunks - receive(timeout=0) to serve resend requests - but that read is
    non-blocking and sits beside the write, not inside it."""
    flags = _record_skip_read(monkeypatch)
    device, recorder, server_sock = make_connected_device(device_cls, responder=responder)
    try:
        device.show_image(os.path.join(PIXELART_DIR, image))
    finally:
        device.disconnect()
        server_sock.close()

    assert len(recorder.sent_messages) > 1
    assert flags == [True] * len(recorder.sent_messages)


@pytest.mark.parametrize(
    ("level", "read_timeouts", "reads_back"),
    [(logging.INFO, [], False), (logging.DEBUG, [0.2], True)],
    ids=["info", "debug"],
)
def test_debug_logging_turns_a_default_command_into_a_read(
        monkeypatch, level, read_timeouts, reads_back):
    """With debug logging, a default command waits for a reply and returns its
    bytes instead of the byte count, which reconnect() branches on."""
    logger = logging.getLogger("read-gate-{0}".format(logging.getLevelName(level)))
    logger.setLevel(level)
    device, _, server_sock = make_connected_device(
        Pixoo, responder=_answer_pings_with(DEVICE_REPLY), logger=logger)
    timeouts = _record_select_timeouts(monkeypatch)
    try:
        result = device.send_command("set brightness", [50])
    finally:
        device.disconnect()
        server_sock.close()

    assert timeouts == read_timeouts
    assert result == (DEVICE_REPLY if reads_back else 8)
