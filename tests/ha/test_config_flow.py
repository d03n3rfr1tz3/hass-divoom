"""HA integration tests for the divoom config flow (user step + zeroconf
step), per the plan's Paket 1c. The zeroconf cases with a missing
device_mac/device_name property used to be marked xfail: the original code
crashed on them (unguarded .get(...).lower()). Paket 2 changes this to a
graceful abort/fallback (see async_step_zeroconf), so these now assert the
new behaviour directly.
"""
from __future__ import annotations

import ipaddress

import pytest

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.divoom.const import CONF_DEVICE_TYPE, DOMAIN
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_PORT

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
        data={CONF_MAC: "11:22:33:44:55:66", CONF_PORT: 1, CONF_HOST: ""},
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
    assert result["data"][CONF_MAC] == "11:22:33:44:55:66"
    assert result["data"][CONF_DEVICE_TYPE] == "pixoo"


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
