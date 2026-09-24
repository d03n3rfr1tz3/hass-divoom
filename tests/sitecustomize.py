"""Windows-only test shims, auto-imported by `site` before pytest starts.

- `fcntl`/`resource` stubs, as homeassistant.runner imports these POSIX-only modules.
- Selector event loop policy, which HassEventLoopPolicy inherits once defined.
- `socket.socketpair` on the unpatched socket class: Windows builds the event
  loop's self-pipe over loopback TCP, which pytest-socket would block.
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
                # lsock.accept() wraps the fd with the module-level socket
                # class, which pytest-socket may have patched by then
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
