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
import pytest


@pytest.fixture(autouse=True)
def _skip_bluetooth_dependency_setup(hass):
    hass.config.components.add("bluetooth_adapters")
    hass.config.components.add("bluetooth")
