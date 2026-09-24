"""The bluetooth dependencies count as already set up, because their real
setup needs a system DBus, which neither Windows nor typical CI runners have.
HA skips any dependency already listed in hass.config.components.
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
    """Hand the config flow a fixed set of local bluetooth adapters, as listing
    them for real needs DBus as well. Tests may adjust its dict."""

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

    Entry setup starts connect() as a background task, so it may run after a
    narrower patch has already ended. Tests that need connect() to have run
    wait with async_block_till_done(wait_background_tasks=True)."""
    with patch.object(DivoomNotificationService, "connect") as connect:
        yield connect


@pytest.fixture(autouse=True)
def _blocked_device_sockets():
    """Make any real device socket fail loudly instead of hanging.

    Only the `socket` name inside the device module is replaced, by a copy of
    the real module whose socket class raises. HA and the event loop keep
    their real sockets."""
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
    """Point hass.config.path() at a throwaway directory, so the migration
    reads and writes real files outside the developer's own configuration."""
    hass.config.config_dir = str(tmp_path)
    return tmp_path
