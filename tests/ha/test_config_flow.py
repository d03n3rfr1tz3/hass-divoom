"""HA integration tests for the divoom config flow (user step + zeroconf step)."""
from __future__ import annotations

import ipaddress

import pytest

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.divoom.const import (
    CONF_DEVICE_TYPE,
    CONF_ESCAPE_PAYLOAD,
    CONF_MEDIA_DIR,
    CONF_MEDIA_DIR_DEFAULT,
    DOMAIN,
)
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME, CONF_PORT

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


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

    await hass.async_block_till_done()


async def test_zeroconf_step_with_properties_creates_entry(hass):
    """Happy path: zeroconf discovery info carries both properties, so the
    device type and name are auto-detected from the mDNS name."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=make_zeroconf_info(
            {"device_mac": "11:22:33:44:55:66", "device_name": "Pixoo-573A"}
        ),
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "device_port"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PORT: 1}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "device_type"
    # auto-detected from the "Pixoo-573A" name prefix
    device_type_key = next(
        key for key in result["data_schema"].schema if key == CONF_DEVICE_TYPE
    )
    assert device_type_key.default() == "pixoo"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_TYPE: "pixoo"}
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
