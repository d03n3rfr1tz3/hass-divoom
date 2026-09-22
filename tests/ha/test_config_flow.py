"""HA integration tests for the divoom config flow (user step + zeroconf step)."""
from __future__ import annotations

import ipaddress
from types import SimpleNamespace

import pytest

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.divoom.const import (
    CONF_ADAPTER,
    CONF_DEVICE_TYPE,
    CONF_ESCAPE_PAYLOAD,
    CONF_MEDIA_DIR,
    CONF_MEDIA_DIR_DEFAULT,
    DOMAIN,
)
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME, CONF_PORT

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def make_bluetooth_info(source: str) -> SimpleNamespace:
    """The three attributes async_step_bluetooth reads. A real
    BluetoothServiceInfoBleak would additionally need a BLEDevice and
    advertisement data, which the step never looks at."""
    return SimpleNamespace(name="Pixoo-573A", address="11:22:33:44:55:66", source=source)


def make_zeroconf_info(properties: dict) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ipaddress.ip_address("10.0.0.42"),
        ip_addresses=[ipaddress.ip_address("10.0.0.42")],
        port=7777,
        hostname="pixoo-573a.local.",
        type="_divoom_esp32._tcp.local.",
        name="Pixoo-573A._divoom_esp32._tcp.local.",
        properties=properties,
    )


async def test_user_step_with_known_mac_creates_entry(hass):
    """Supplying CONF_MAC directly skips discovery and jumps straight to
    the device_type step (device_port is only reached via bluetooth/
    zeroconf discovery, which pre-populates _device_name for its
    name-prefix autodetection)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_MAC: "11:22:33:44:55:AA", CONF_PORT: 1, CONF_HOST: ""},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "device_type"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_TYPE: "pixoo"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC] == "11:22:33:44:55:aa"
    assert result["data"][CONF_DEVICE_TYPE] == "pixoo"
    assert result["data"][CONF_ADAPTER] is None

    await hass.async_block_till_done()


async def test_user_step_with_adapter_stores_it_lowercased(hass):
    """The adapter is compared against the discovery source and written into a
    bind() call, so it is normalized the same way the MAC is."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={
            CONF_MAC: "11:22:33:44:55:AA",
            CONF_PORT: 1,
            CONF_ADAPTER: "AA:BB:CC:DD:EE:FF",
            CONF_HOST: "",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_TYPE: "pixoo"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ADAPTER] == "aa:bb:cc:dd:ee:ff"

    await hass.async_block_till_done()


async def test_bluetooth_step_suggests_the_discovering_adapter(hass):
    """The adapter that saw the device is the one it is paired with, so it is
    the obvious default for the connection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=make_bluetooth_info("AA:BB:CC:DD:EE:FF"),
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "device_port"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PORT: 1}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_TYPE: "pixoo"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ADAPTER] == "aa:bb:cc:dd:ee:ff"

    await hass.async_block_till_done()


async def test_bluetooth_step_ignores_a_remote_scanner_as_adapter(hass):
    """A device seen through an ESPHome proxy carries that proxy as source.
    Binding a local socket to it would fail, so it must not be taken over."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=make_bluetooth_info("11:11:11:11:11:11"),
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PORT: 1}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_TYPE: "pixoo"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ADAPTER] is None

    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("device_name", "device_type"),
    [
        ("Pixoo-573A", "pixoo"),
        ("Divoom MiniToo-App", "minitoo"),
        ("Divoom Tiivoo 2-Light", "tiivoo2"),
        ("Divoom FlowToo-App", "flowtoo"),
    ],
)
async def test_zeroconf_step_with_properties_creates_entry(hass, device_name, device_type):
    """Happy path: zeroconf discovery info carries both properties, so the
    device type and name are auto-detected from the mDNS name."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=make_zeroconf_info(
            {"device_mac": "11:22:33:44:55:66", "device_name": device_name}
        ),
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "device_port"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PORT: 1}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "device_type"
    # auto-detected from the advertised name prefix
    device_type_key = next(
        key for key in result["data_schema"].schema if key == CONF_DEVICE_TYPE
    )
    assert device_type_key.default() == device_type

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_TYPE: device_type}
    )

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC] == "11:22:33:44:55:66"

    await hass.async_block_till_done()


async def test_zeroconf_step_missing_device_mac_is_handled(hass):
    """A missing device_mac property can't be recovered from - the flow
    aborts instead of crashing on discovery_info.properties.get(...).lower()."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=make_zeroconf_info({"device_name": "Pixoo-573A"}),
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "invalid_discovery_info"


async def test_zeroconf_step_missing_device_name_is_handled(hass):
    """A missing device_name property falls back to "Device" instead of
    crashing on self._device_name.lower() in async_step_device_port."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=make_zeroconf_info({"device_mac": "11:22:33:44:55:66"}),
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "device_port"


async def test_reconfigure_updates_connection_and_keeps_identity(hass):
    """Reconfigure changes host, port and device type only. The MAC is the
    unique_id and the name is what the service names derive from."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="11:22:33:44:55:66",
        title="Divoom Pixoo",
        data={
            CONF_NAME: "Divoom Pixoo",
            CONF_HOST: "10.0.0.42",
            CONF_MAC: "11:22:33:44:55:66",
            CONF_PORT: 1,
            CONF_DEVICE_TYPE: "pixoo",
            CONF_MEDIA_DIR: CONF_MEDIA_DIR_DEFAULT,
            CONF_ESCAPE_PAYLOAD: None,
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PORT: 2, CONF_DEVICE_TYPE: "ditoo"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] is None
    assert entry.data[CONF_PORT] == 2
    assert entry.data[CONF_DEVICE_TYPE] == "ditoo"
    assert entry.data[CONF_MAC] == "11:22:33:44:55:66"
    assert entry.data[CONF_NAME] == "Divoom Pixoo"

    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.mark.parametrize(
    ("adapter_input", "expected_adapter"),
    [
        ({CONF_ADAPTER: "AA:BB:CC:DD:EE:FF"}, "AA:BB:CC:DD:EE:FF"),
        ({}, None),
    ],
)
async def test_reconfigure_sets_and_clears_the_adapter(hass, adapter_input, expected_adapter):
    """Reconfigure is the only way to pick another adapter or to hand the
    choice back to the system, so leaving the field out has to clear it. Entries
    created before the option existed carry no adapter key at all."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="11:22:33:44:55:66",
        title="Divoom Pixoo",
        data={
            CONF_NAME: "Divoom Pixoo",
            CONF_MAC: "11:22:33:44:55:66",
            CONF_PORT: 1,
            CONF_DEVICE_TYPE: "pixoo",
            CONF_MEDIA_DIR: CONF_MEDIA_DIR_DEFAULT,
            CONF_ESCAPE_PAYLOAD: None,
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PORT: 1, CONF_DEVICE_TYPE: "pixoo", **adapter_input},
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_ADAPTER] == expected_adapter

    await hass.async_block_till_done(wait_background_tasks=True)
