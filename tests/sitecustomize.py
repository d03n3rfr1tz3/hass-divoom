"""Local Windows test-environment shim, auto-imported by Python's `site`
module at interpreter startup (before pytest or anything else runs).

homeassistant.runner unconditionally imports the POSIX-only stdlib module
`fcntl` (used only for a single-instance pidfile lock when actually running
the HA server - never during component/unit testing). Without this shim,
`pytest_homeassistant_custom_component` cannot even be loaded as a pytest
plugin on Windows, before any test collection happens. Real platforms (CI
runs on Linux) keep using the real `fcntl` module untouched.

Also swaps the default asyncio event loop policy for the Selector one, and
patches `socket.socketpair` to bypass pytest-socket. Both address the same
underlying problem: `pytest_homeassistant_custom_component.plugins` installs
its own unconditional `pytest_runtest_setup()` hook that calls
`pytest_socket.disable_socket(allow_unix_socket=True)` before every single
test, no matter what fixtures/markers that test uses. On POSIX this is
harmless for asyncio, because a loop's self-pipe is created with a native
AF_UNIX `socketpair()` syscall that bypasses the patched `socket.socket`
class entirely. Windows has no native socketpair syscall, so the stdlib falls
back to `_fallback_socketpair()`, a pure-Python implementation that opens a
loopback AF_INET connection *through* `socket.socket(...)` - which
pytest-socket then blocks with `SocketBlockedError`, breaking every test that
merely uses an async fixture (e.g. `hass`). The event loop policy swap
(`HassEventLoopPolicy` inherits from whatever `asyncio.DefaultEventLoopPolicy`
resolves to at class-definition time, and that patch has to land before
`homeassistant.runner` is imported) just picks the simpler Selector loop; the
`socket.socketpair` patch is what actually avoids the block, by rebuilding
the same loopback-pair logic against a `socket.socket` reference captured
before pytest-socket can ever monkeypatch it.
"""
import sys

if sys.platform == "win32":
    import asyncio
    import socket
    import types

    asyncio.DefaultEventLoopPolicy = asyncio.WindowsSelectorEventLoopPolicy

    _real_socket_cls = socket.socket

    def _real_socketpair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
        if family == socket.AF_INET:
            host = "127.0.0.1"
        elif family == socket.AF_INET6:
            host = "::1"
        else:
            raise ValueError("Only AF_INET and AF_INET6 are supported")
        if type != socket.SOCK_STREAM:
            raise ValueError("Only SOCK_STREAM is supported")

        lsock = _real_socket_cls(family, type, proto)
        try:
            lsock.bind((host, 0))
            lsock.listen()
            addr, port = lsock.getsockname()[:2]
            csock = _real_socket_cls(family, type, proto)
            try:
                csock.setblocking(False)
                try:
                    csock.connect((addr, port))
                except (BlockingIOError, InterruptedError):
                    pass
                csock.setblocking(True)
                # lsock.accept() would internally call the module-level
                # `socket(...)` name to wrap the accepted fd, which resolves
                # to whatever pytest-socket has patched `socket.socket` to by
                # then. Use the private fd-only accept and wrap it ourselves
                # with the captured real class instead.
                fd, _ = lsock._accept()
                ssock = _real_socket_cls(family, type, proto, fileno=fd)
            except OSError:
                csock.close()
                raise
        finally:
            lsock.close()
        return ssock, csock

    socket.socketpair = _real_socketpair

    if "fcntl" not in sys.modules:
        _fcntl_shim = types.ModuleType("fcntl")
        _fcntl_shim.LOCK_EX = 2
        _fcntl_shim.LOCK_NB = 4
        _fcntl_shim.flock = lambda fd, operation: None
        sys.modules["fcntl"] = _fcntl_shim

    if "resource" not in sys.modules:
        _resource_shim = types.ModuleType("resource")
        _resource_shim.RLIMIT_NOFILE = 7
        _resource_shim.getrlimit = lambda resource_id: (2048, 2048)
        _resource_shim.setrlimit = lambda resource_id, limits: None
        sys.modules["resource"] = _resource_shim
