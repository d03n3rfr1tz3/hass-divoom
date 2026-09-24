"""divoom's manifest.json declares "bluetooth_adapters" as a dependency,
which itself depends on "bluetooth". Driving a config flow via
hass.config_entries.flow.async_init() makes HA resolve and really set up
that whole chain first - and homeassistant.components.bluetooth's setup
loads adapter history via bluetooth_adapters' DBus code path, which needs
a running system DBus daemon (BlueZ). That's not available here (no DBus
on Windows at all - dbus_fast's import fails outright there - and typical
CI runners don't have one either), so real setup crashes with
`TypeError: 'NoneType' object is not callable` deep in dbus_fast/bluez
unpacking, regardless of platform.

None of that matters for what these tests actually exercise (config_flow's
own step logic: MAC/name parsing, uniqueness checks, form navigation) - the
flow never touches the bluetooth manager directly, it only receives already
-constructed discovery info. So we take the same escape hatch HA's own
dependency resolver checks first (setup.py's `_async_process_dependencies`:
`if dep in hass.config.components: continue`) and mark the dependency as
already set up, which skips ever running its real async_setup().
"""
import socket
import types
from unittest.mock import patch

import pytest
from bluetooth_adapters import ADAPTER_ADDRESS

from custom_components.divoom import config_flow as divoom_config_flow
from custom_components.divoom.devices import divoom as divoom_device
from custom_components.divoom.notify import DivoomNotificationService


@pytest.fixture(autouse=True)
def _skip_bluetooth_dependency_setup(hass):
    hass.config.components.add("bluetooth_adapters")
    hass.config.components.add("bluetooth")


@pytest.fixture(autouse=True)
def local_adapters():
    """Hand the config flow a fixed set of local bluetooth adapters.

    Listing them for real goes through the same DBus code path as the
    dependency setup above, which is not available here. Tests that care about
    the adapters take this fixture and adjust its dict."""

    class _Adapters:
        def __init__(self):
            self.adapters = {
                "hci0": {ADAPTER_ADDRESS: "AA:BB:CC:DD:EE:FF"},
                "hci1": {ADAPTER_ADDRESS: "AA:BB:CC:DD:EE:00"},
            }

        async def refresh(self):
            pass

    adapters = _Adapters()
    with patch.object(divoom_config_flow, "get_adapters", lambda: adapters):
        yield adapters


@pytest.fixture(autouse=True)
def _no_discovered_devices():
    """The device form lists what the bluetooth manager has seen, and that
    manager is never set up here (see above)."""
    with patch.object(divoom_config_flow, "async_discovered_service_info", return_value=[]):
        yield


@pytest.fixture(autouse=True)
def _patched_device_connect():
    """Keep every HA test from opening a real connection to a device.

    Setting up a config entry loads the legacy notify platform through
    `hass.async_create_task(async_load_platform(...))` (__init__.py), and
    async_get_service() then starts connect() as a background task. So no test
    controls *when* connect() runs. Patching it only around the flow call that
    creates the entry leaves a window for the real socket.connect() to run
    afterwards and block an executor thread past the end of the test.

    Patching it for the whole test closes that window regardless of timing.
    Tests that need connect() to have happened wait for it with
    async_block_till_done(wait_background_tasks=True)."""
    with patch.object(DivoomNotificationService, "connect") as connect:
        yield connect


@pytest.fixture(autouse=True)
def _blocked_device_sockets():
    """Backstop for _patched_device_connect: make any real device socket a
    loud, immediate failure instead of a 130s hang.

    Only the `socket` name inside the device module is swapped, never the
    stdlib module itself - HA, aiohttp and the event loop need real sockets.
    The stand-in copies everything from the real module (so `socket.error` and
    the AF_*/BTPROTO_* constants keep working, and divoom.py's `except
    socket.error` behaves unchanged) and replaces only the socket class.
    Divoom.connect() is the single place that constructs one; no subclass
    overrides it, and reconnect() goes through it as well."""
    attempts = []

    class _BlockedSocket:
        def __init__(self, *args, **kwargs):
            attempts.append(args)
            raise AssertionError(
                "divoom device code opened a real socket: socket.socket{0}".format(args)
            )

    shim = types.ModuleType("socket")
    shim.__dict__.update(socket.__dict__)
    shim.socket = _BlockedSocket

    with patch.object(divoom_device, "socket", shim):
        yield

    assert not attempts, "divoom device code opened real sockets: {0}".format(attempts)


@pytest.fixture
def config_dir(hass, tmp_path):
    """Point hass.config.path() at a throwaway directory.

    Config.config_dir is a plain attribute and path() just joins onto it, so
    this is all it takes to let the migration read and write real files
    without going near the developer's own configuration.
    """
    hass.config.config_dir = str(tmp_path)
    return tmp_path
