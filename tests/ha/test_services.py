"""HA integration tests for services.py: the divoom.* domain services.

Like test_notify.py these swap a unittest.mock.Mock() in for the device, so
no socket is ever involved - what's asserted is which show_*/send_* call
reaches the mock, and how the service layer resolves its target and reports
failures.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
import voluptuous as vol

from homeassistant.const import CONF_MAC
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.divoom.const import CONF_ENTRY_ID, DOMAIN
from custom_components.divoom.notify import VALID_MODES
from custom_components.divoom.services import SERVICE_SCHEMAS, _resolve_target

from .test_notify import make_mocked_service

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

COMPONENT_PATH = Path(__file__).parents[2] / "custom_components" / "divoom"


def register_device(hass, mac="11:22:33:44:55:66", loaded=True):
    """Put a mocked device behind a config entry, the way async_setup_entry
    plus the notify platform would."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_MAC: mac}, title="Divoom Test")
    entry.add_to_hass(hass)

    service = make_mocked_service()
    if loaded:
        hass.data.setdefault(DOMAIN, {}).setdefault("loaded", {})[mac] = service

    return entry, service


async def test_async_setup_registers_clock_service(hass):
    """Services are registered in async_setup, so they exist even with no
    config entry at all - a call then fails with a readable message instead
    of "unknown service"."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, "clock")


async def test_resolve_target_returns_loaded_device_for_entry(hass):
    entry, service = register_device(hass)

    assert _resolve_target(hass, {CONF_ENTRY_ID: entry.entry_id}) is service


async def test_resolve_target_unknown_entry_raises(hass):
    register_device(hass)

    with pytest.raises(ServiceValidationError) as error:
        _resolve_target(hass, {CONF_ENTRY_ID: "not-a-real-entry-id"})

    assert error.value.translation_key == "entry_not_found"


async def test_resolve_target_entry_of_another_domain_raises(hass):
    """async_get_entry looks up across all domains, so an entry_id belonging
    to some other integration must not resolve here."""
    foreign = MockConfigEntry(domain="not_divoom", data={CONF_MAC: "11:22:33:44:55:66"})
    foreign.add_to_hass(hass)
    register_device(hass)

    with pytest.raises(ServiceValidationError) as error:
        _resolve_target(hass, {CONF_ENTRY_ID: foreign.entry_id})

    assert error.value.translation_key == "entry_not_found"


async def test_resolve_target_entry_without_loaded_device_raises(hass):
    """The entry exists but its device never made it into hass.data - the
    notify platform failed to set up, or the entry was unloaded."""
    entry, _ = register_device(hass, loaded=False)

    with pytest.raises(ServiceValidationError) as error:
        _resolve_target(hass, {CONF_ENTRY_ID: entry.entry_id})

    assert error.value.translation_key == "entry_not_loaded"


async def test_clock_service_requires_entry_id(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    register_device(hass)

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "clock", {"clock": 1}, blocking=True)


async def test_clock_service_rejects_out_of_range_style(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "clock", {CONF_ENTRY_ID: entry.entry_id, "clock": 99}, blocking=True
        )

    service._device.show_clock.assert_not_called()


async def test_clock_service_calls_show_clock_off_the_event_loop(hass):
    """call_mode does blocking socket I/O, so the service handler has to hand
    it to an executor thread rather than run it on the event loop."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)

    loop_thread = threading.get_ident()
    calling_threads = []
    service._device.show_clock.side_effect = lambda **kwargs: calling_threads.append(
        threading.get_ident()
    )

    await hass.services.async_call(
        DOMAIN,
        "clock",
        {CONF_ENTRY_ID: entry.entry_id, "clock": 1, "calendar": True, "color": [250, 0, 0]},
        blocking=True,
    )

    service._device.show_clock.assert_called_once_with(
        clock=1, twentyfour=None, weather=None, temp=None, calendar=True,
        color=[250, 0, 0], hot=None,
    )
    assert calling_threads != [loop_thread]


async def test_clock_service_omits_unset_fields(hass):
    """services.yaml deliberately carries no `default:` values - an untouched
    field has to arrive as None, or the service path would send commands the
    notify path doesn't (show_clock only emits "set time type" when
    twentyfour is not None, and "set hot" when hot is not None)."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)

    await hass.services.async_call(
        DOMAIN, "clock", {CONF_ENTRY_ID: entry.entry_id}, blocking=True
    )

    service._device.show_clock.assert_called_once_with(
        clock=None, twentyfour=None, weather=None, temp=None, calendar=None,
        color=None, hot=None,
    )


async def test_clock_service_reconnects_first(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)

    await hass.services.async_call(
        DOMAIN, "clock", {CONF_ENTRY_ID: entry.entry_id}, blocking=True
    )

    service._device.reconnect.assert_called_once_with(skipPing=False)


async def test_clock_service_raises_when_call_mode_fails(hass):
    """A False from call_mode has to surface in the UI. The notify path can
    only log it, but a service call has somewhere to throw."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)
    service.call_mode = Mock(return_value=False)

    with pytest.raises(HomeAssistantError) as error:
        await hass.services.async_call(
            DOMAIN, "clock", {CONF_ENTRY_ID: entry.entry_id}, blocking=True
        )

    assert error.value.translation_key == "mode_failed"


async def test_notify_and_service_clock_paths_produce_identical_show_clock_call(hass):
    """The whole point of extracting call_mode: both entry points share one
    lock, one reconnect and one dispatch, so the same parameters must reach
    the device identically either way."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry, via_service = register_device(hass)
    via_notify = make_mocked_service()

    params = {
        "clock": 1,
        "twentyfour": True,
        "weather": False,
        "temp": False,
        "calendar": True,
        "color": [250, 0, 0],
        "hot": False,
    }

    await hass.services.async_call(
        DOMAIN, "clock", {CONF_ENTRY_ID: entry.entry_id, **params}, blocking=True
    )
    via_notify.send_message(data={"mode": "clock", **params})

    assert via_service._device.mock_calls == via_notify._device.mock_calls


def test_services_yaml_strings_and_translations_stay_in_sync():
    """services.yaml, the voluptuous schemas and the ten string files are
    maintained by hand and drift easily. Every mode added in a later step
    passes through here."""
    services_yaml = load_yaml(str(COMPONENT_PATH / "services.yaml"))
    strings = json.loads((COMPONENT_PATH / "strings.json").read_text(encoding="utf-8"))

    assert set(services_yaml) == set(SERVICE_SCHEMAS)

    for mode, definition in services_yaml.items():
        assert mode in VALID_MODES, mode

        yaml_fields = definition["fields"]
        schema_fields = {str(marker): marker for marker in SERVICE_SCHEMAS[mode].schema}
        assert set(yaml_fields) == set(schema_fields), mode

        for field, marker in schema_fields.items():
            required_in_yaml = yaml_fields[field].get("required", False)
            assert required_in_yaml == isinstance(marker, vol.Required), (mode, field)

        described = strings["services"][mode]
        assert described["name"] and described["description"]
        assert set(described["fields"]) == set(yaml_fields), mode
        for field, texts in described["fields"].items():
            assert texts["name"] and texts["description"], (mode, field)

    # every translation_key raised by services.py must be translatable
    assert set(strings["exceptions"]) == {
        "entry_not_found",
        "entry_not_loaded",
        "mode_failed",
    }

    reference = _flatten(strings)
    for path in sorted((COMPONENT_PATH / "translations").glob("*.json")):
        translation = json.loads(path.read_text(encoding="utf-8"))
        assert _flatten(translation) == reference, path.name


def _flatten(node, prefix=""):
    keys = set()
    for key, value in node.items():
        name = "{}.{}".format(prefix, key) if prefix else key
        if isinstance(value, dict):
            keys |= _flatten(value, name)
        else:
            keys.add(name)
    return keys
