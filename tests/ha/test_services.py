"""HA integration tests for services.py: the divoom.* domain services.

Like test_notify.py these swap a unittest.mock.Mock() in for the device, so
no socket is ever involved - what's asserted is which show_*/send_* call
reaches the mock, and how the service layer resolves its target and reports
failures.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
import voluptuous as vol

from homeassistant.const import CONF_MAC
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml, parse_yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.divoom import notify as notify_module
from custom_components.divoom.const import CONF_ENTRY_ID, DOMAIN
from custom_components.divoom.devices.aurabox import Aurabox
from custom_components.divoom.devices.backpack import Backpack
from custom_components.divoom.devices.ditoo import Ditoo
from custom_components.divoom.devices.divoom import DivoomUnsupportedError
from custom_components.divoom.devices.pixoo import Pixoo
from custom_components.divoom.devices.timeboxmini import TimeboxMini
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


async def test_clock_service_rejects_negative_style(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "clock", {CONF_ENTRY_ID: entry.entry_id, "clock": -1}, blocking=True
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
        DOMAIN, "clock", {CONF_ENTRY_ID: entry.entry_id, "clock": 1}, blocking=True
    )

    service._device.show_clock.assert_called_once_with(
        clock=1, twentyfour=None, weather=None, temp=None, calendar=None,
        color=None, hot=None,
    )


async def test_clock_service_reconnects_first(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)

    await hass.services.async_call(
        DOMAIN, "clock", {CONF_ENTRY_ID: entry.entry_id, "clock": 1}, blocking=True
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
            DOMAIN, "clock", {CONF_ENTRY_ID: entry.entry_id, "clock": 1}, blocking=True
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


# (mode, service params, notify data, device method, expected args, expected kwargs)
# text/visualization deliberately use the packed `color` form on the notify
# side, so the parity test also covers the legacy way of passing both colors.
DISPATCH_CASES = [
    (
        "light",
        {"brightness": 75, "color": [250, 0, 0]},
        {"brightness": 75, "color": [250, 0, 0]},
        "show_light", (), {"color": [250, 0, 0], "brightness": 75, "power": True},
    ),
    ("on", {}, {}, "send_on", (), {}),
    ("off", {}, {}, "send_off", (), {}),
    (
        "brightness",
        {"brightness": 100}, {"brightness": 100},
        "send_brightness", (), {"value": 100},
    ),
    (
        "image",
        {"file": "ha16.gif", "time": 80}, {"file": "ha16.gif", "time": 80},
        "show_image", (os.path.join("pixelart", "ha16.gif"),), {"time": 80},
    ),
    (
        "text",
        {"text": "Hi Divoom", "font": "divoom.ttf", "size": 16, "time": 100,
         "foreground_color": [250, 0, 0], "background_color": [0, 0, 0]},
        {"text": "Hi Divoom", "font": "divoom.ttf", "size": 16, "time": 100,
         "color": [[250, 0, 0], [0, 0, 0]]},
        "show_text", ("Hi Divoom", os.path.join("fonts", "divoom.ttf")),
        {"size": 16, "time": 100, "color1": [250, 0, 0], "color2": [0, 0, 0]},
    ),
    (
        "text",
        {"text": "Hi Divoom", "background_color": [0, 0, 0]},
        {"text": "Hi Divoom", "color": [None, [0, 0, 0]]},
        "show_text", ("Hi Divoom", None),
        {"size": None, "time": None, "color1": None, "color2": [0, 0, 0]},
    ),
    ("design", {"number": 2}, {"number": 2}, "show_design", (), {"number": 2}),
    ("effects", {"number": 2}, {"number": 2}, "show_effects", (), {"number": 2}),
    (
        "visualization",
        {"number": 2, "foreground_color": [250, 0, 0], "background_color": [0, 0, 0]},
        {"number": 2, "color": [[250, 0, 0], [0, 0, 0]]},
        "show_visualization", (), {"number": 2, "color1": [250, 0, 0], "color2": [0, 0, 0]},
    ),
    (
        "signal",
        {"number": 2}, {"number": 2},
        "show_signal", (), {"number": 2, "color1": None, "color2": None},
    ),
    (
        "alarm",
        {"number": 0, "value": "07:30:00", "weekday": ["mon", "tue"], "alarmmode": 0,
         "triggermode": 0, "frequency": 100.3, "volume": 75},
        {"number": 0, "value": "07:30:00", "weekday": ["mon", "tue"], "alarmmode": 0,
         "triggermode": 0, "frequency": 100.3, "volume": 75},
        "show_alarm", (),
        {"number": 0, "time": "07:30:00", "weekdays": ["mon", "tue"], "alarmMode": 0,
         "triggerMode": 0, "frequency": 100.3, "volume": 75},
    ),
    (
        "countdown",
        {"value": True, "countdown": "00:01:30"}, {"value": True, "countdown": "00:01:30"},
        "show_countdown", (), {"value": True, "countdown": "00:01:30"},
    ),
    ("timer", {"value": True}, {"value": True}, "show_timer", (), {"value": True}),
    (
        "memorial",
        {"number": 0, "value": "2000-12-31 00:00:00", "text": "Happy New Year!"},
        {"number": 0, "value": "2000-12-31 00:00:00", "text": "Happy New Year!"},
        "show_memorial", (),
        {"number": 0, "value": "2000-12-31 00:00:00", "text": "Happy New Year!", "animate": True},
    ),
    (
        "scoreboard",
        {"player1": 2, "player2": 1}, {"player1": 2, "player2": 1},
        "show_scoreboard", (), {"blue": 2, "red": 1},
    ),
    ("noise", {"value": True}, {"value": True}, "show_noise", (), {"value": True}),
    (
        "sleep",
        {"value": True, "time": 30, "sleepmode": 4, "volume": 10,
         "color": [255, 255, 0], "brightness": 50, "frequency": 100.3},
        {"value": True, "time": 30, "sleepmode": 4, "volume": 10,
         "color": [255, 255, 0], "brightness": 50, "frequency": 100.3},
        "show_sleep", (True, 30, 4, 10, [255, 255, 0], 50, 100.3), {},
    ),
    (
        "datetime",
        {"value": "2024-12-31 18:30:00"}, {"value": "2024-12-31 18:30:00"},
        "send_datetime", (), {"value": "2024-12-31 18:30:00"},
    ),
    (
        "equalizer",
        {"number": 2, "audiomode": True, "backgroundmode": False, "streammode": False},
        {"number": 2, "audiomode": True, "backgroundmode": False, "streammode": False},
        "show_equalizer", (),
        {"number": 2, "audioMode": True, "backgroundMode": False, "streamMode": False},
    ),
    ("volume", {"volume": 75}, {"volume": 75}, "send_volume", (), {"value": 75}),
    ("playstate", {"value": True}, {"value": True}, "send_playstate", (), {"value": True}),
    (
        "radio",
        {"value": True, "frequency": 100.3}, {"value": True, "frequency": 100.3},
        "show_radio", (), {"value": True, "frequency": 100.3},
    ),
    ("lyrics", {}, {}, "show_lyrics", (), {}),
    ("keyboard", {"value": "next"}, {"value": "next"}, "send_keyboard", (), {"value": "next"}),
    ("game", {"value": 2}, {"value": 2}, "show_game", (), {"value": 2}),
    (
        "gamecontrol",
        {"value": "go"}, {"value": "go"},
        "send_gamecontrol", (), {"value": "go"},
    ),
    (
        "weather",
        {"value": 25, "unit": "°C", "weather": "rainy"},
        {"value": 25, "unit": "°C", "weather": "rainy"},
        "send_weather", (), {"value": 25.0, "weather": 6, "unit": "°C"},
    ),
    (
        "temperature",
        {"value": "°F", "color": [250, 0, 0]}, {"value": "°F", "color": [250, 0, 0]},
        "show_temperature", (), {"value": "°F", "color": [250, 0, 0]},
    ),
    (
        "raw",
        {"raw": [0x74, 0x64]}, {"raw": [0x74, 0x64]},
        "send_command", (), {"command": 0x74, "args": [0x64]},
    ),
    ("connect", {}, {}, "connect", (), {}),
    ("disconnect", {}, {}, "disconnect", (), {}),
]

DISPATCH_IDS = [
    "{}-{}".format(case[0], index) for index, case in enumerate(DISPATCH_CASES)
]


@pytest.mark.parametrize(
    "mode,params,notify_data,method,args,kwargs", DISPATCH_CASES, ids=DISPATCH_IDS
)
async def test_service_dispatches_to_device(hass, mode, params, notify_data, method, args, kwargs):
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)

    await hass.services.async_call(
        DOMAIN, mode, {CONF_ENTRY_ID: entry.entry_id, **params}, blocking=True
    )

    getattr(service._device, method).assert_called_once_with(*args, **kwargs)


@pytest.mark.parametrize(
    "mode,params,notify_data,method,args,kwargs", DISPATCH_CASES, ids=DISPATCH_IDS
)
async def test_notify_and_service_paths_match(hass, mode, params, notify_data, method, args, kwargs):
    """Both entry points go through call_mode, so the device must not be able
    to tell them apart."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry, via_service = register_device(hass)
    via_notify = make_mocked_service()

    await hass.services.async_call(
        DOMAIN, mode, {CONF_ENTRY_ID: entry.entry_id, **params}, blocking=True
    )
    via_notify.send_message(data={"mode": mode, **notify_data})

    assert via_service._device.mock_calls == via_notify._device.mock_calls


@pytest.mark.parametrize(
    "mode,params",
    [
        ("clock", {}),
        ("light", {}),
        ("brightness", {}),
        ("image", {}),
        ("text", {}),
        ("design", {}),
        ("effects", {}),
        ("visualization", {}),
        ("signal", {}),
        ("countdown", {}),
        ("timer", {}),
        ("noise", {}),
        ("sleep", {}),
        ("equalizer", {}),
        ("volume", {}),
        ("playstate", {}),
        ("radio", {}),
        ("keyboard", {}),
        ("gamecontrol", {}),
        ("weather", {}),
        ("temperature", {}),
        ("raw", {}),
    ],
)
async def test_service_requires_mandatory_field(hass, mode, params):
    """Without these the device call would be a silent no-op or the device
    default would pick for the caller, so the schema has to reject the call
    instead of letting it look successful."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, mode, {CONF_ENTRY_ID: entry.entry_id, **params}, blocking=True
        )

    assert service._device.mock_calls == []


@pytest.mark.parametrize("mode", ["on", "off"])
async def test_on_off_services_take_no_parameters(hass, mode):
    assert await async_setup_component(hass, DOMAIN, {})
    entry, _ = register_device(hass)

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, mode, {CONF_ENTRY_ID: entry.entry_id, "brightness": 50}, blocking=True
        )


async def test_image_outside_media_directory_raises(hass):
    """_resolve_path rejects the traversal, call_mode returns False - on the
    service path that has to become a visible error, not just a log line."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)

    with pytest.raises(HomeAssistantError) as error:
        await hass.services.async_call(
            DOMAIN,
            "image",
            {CONF_ENTRY_ID: entry.entry_id, "file": "../../secrets.yaml"},
            blocking=True,
        )

    assert error.value.translation_key == "mode_failed"
    service._device.show_image.assert_not_called()


async def test_brightness_zero_is_sent(hass):
    """0 is a legitimate brightness. It used to fall through the truthy `or`
    chain in notify.py down to None, where send_brightness returns silently."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)

    await hass.services.async_call(
        DOMAIN, "brightness", {CONF_ENTRY_ID: entry.entry_id, "brightness": 0}, blocking=True
    )

    service._device.send_brightness.assert_called_once_with(value=0)


@pytest.mark.parametrize("key", ["brightness", "number", "value"])
def test_brightness_accepts_any_of_its_three_keys(key):
    """The notify path deliberately tolerates the wrong key. Fixing the falsy-0
    bug must not narrow that down to `brightness` only."""
    service = make_mocked_service()

    service.call_mode("brightness", {key: 0})

    service._device.send_brightness.assert_called_once_with(value=0)


@pytest.mark.parametrize(
    "mode,method", [("text", "show_text"), ("visualization", "show_visualization")]
)
def test_notify_accepts_separate_color_params(mode, method):
    """The service layer has one field per color, so call_mode has to take
    them separately too - notify users get the same choice."""
    service = make_mocked_service()

    service.call_mode(mode, {
        "text": "Hi Divoom", "number": 2,
        "foreground_color": [250, 0, 0], "background_color": [0, 0, 0],
    })

    kwargs = getattr(service._device, method).call_args.kwargs
    assert kwargs["color1"] == [250, 0, 0]
    assert kwargs["color2"] == [0, 0, 0]


def test_separate_color_params_win_over_packed_color():
    service = make_mocked_service()

    service.call_mode("visualization", {
        "number": 2, "color": [[1, 1, 1], [2, 2, 2]], "background_color": [0, 0, 0],
    })

    service._device.show_visualization.assert_called_once_with(
        number=2, color1=[1, 1, 1], color2=[0, 0, 0]
    )


@pytest.mark.parametrize("time_value", ["07:30", "07:30:00"])
def test_alarm_accepts_both_time_formats(time_value):
    """The time: selector emits hh:mm:ss, existing automations use hh:mm.
    Both have to reach the device as the same two bytes."""
    device = Pixoo(mac="11:22:33:44:55:66")
    device.send_command = Mock()

    device.show_alarm(number=0, time=time_value)

    args = device.send_command.call_args.args[1]
    assert args[2:4] == [7, 30]


@pytest.mark.parametrize(
    "countdown_value,expected",
    [
        ("01:30", [1, 30]),  # mm:ss, as documented in the README
        ("00:01:30", [1, 30]),  # hh:mm:ss, as the time: selector emits it
        ("01:30:00", [30, 0]),  # the hours are dropped
    ],
)
def test_countdown_reads_minutes_and_seconds_from_the_end(countdown_value, expected):
    """The countdown takes mm:ss, so a three-part value has to be read from
    the back - reading it from the front turned the hours into minutes."""
    device = Pixoo(mac="11:22:33:44:55:66")
    device.send_command = Mock()

    device.show_countdown(value=1, countdown=countdown_value)

    args = device.send_command.call_args.args[1]
    assert args[2:4] == expected


@pytest.mark.parametrize(
    "alias,number", [("previous", -1), ("toggle", 0), ("next", 1)]
)
def test_keyboard_aliases_match_numbers(alias, number):
    """The select: field sends spoken names, the notify path and older
    automations send -1/0/1 - both have to produce the same command."""
    by_alias = Ditoo(mac="11:22:33:44:55:66")
    by_alias.send_command = Mock()
    by_number = Ditoo(mac="11:22:33:44:55:66")
    by_number.send_command = Mock()

    by_alias.send_keyboard(value=alias)
    by_number.send_keyboard(value=number)

    assert by_alias.send_command.call_args == by_number.send_command.call_args


@pytest.mark.parametrize("mode", ["connect", "disconnect"])
async def test_connect_and_disconnect_services_skip_the_reconnect(hass, mode):
    """call_mode reconnects before every mode but these two - reconnecting
    first would make disconnect open the socket it is about to close."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)

    await hass.services.async_call(
        DOMAIN, mode, {CONF_ENTRY_ID: entry.entry_id}, blocking=True
    )

    service._device.reconnect.assert_not_called()


def _weather_calls(**kwargs):
    device = Pixoo(mac="11:22:33:44:55:66")
    device.send_command = Mock()

    device.send_weather(**kwargs)

    return device.send_command.call_args_list


def _temperature_byte(calls):
    return calls[0].args[1][0]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"value": "25°C"},
        {"value": "25 °c"},
        {"value": 25, "unit": "°C"},
        {"value": "77°F"},
        {"value": 77, "unit": "°F"},
        {"value": "77°F", "unit": "°C", "extra": 77},
    ],
)
def test_weather_value_accepts_number_and_unit(kwargs):
    """The UI splits temperature into a number and an optional unit, older
    automations pack both into one string - every spelling has to end up as
    the same celsius byte. An explicit unit wins over the one in the string,
    which is why the last case sends 77 rather than converting it."""
    expected = kwargs.pop("extra", 25)

    assert _temperature_byte(_weather_calls(**kwargs)) == expected


def test_weather_without_unit_leaves_the_device_setting_alone():
    """A bare number says nothing about celsius or fahrenheit, so "set temp
    type" must not be guessed - the device keeps whatever it is set to."""
    calls = _weather_calls(value=25)

    assert [call.args[0] for call in calls] == ["set temp"]


@pytest.mark.parametrize("device_cls", [Aurabox, TimeboxMini])
@pytest.mark.parametrize("unit,number", [("°C", 0), ("°F", 1)])
def test_temperature_unit_aliases_match_numbers(device_cls, unit, number):
    """The select: field sends °C/°F, the notify path and older automations
    send 0/1 - both show_temperature implementations have to agree."""
    by_alias = device_cls(mac="11:22:33:44:55:66")
    by_alias.send_command = Mock()
    by_number = device_cls(mac="11:22:33:44:55:66")
    by_number.send_command = Mock()

    by_alias.show_temperature(value=unit)
    by_number.show_temperature(value=number)

    assert by_alias.send_command.call_args_list == by_number.send_command.call_args_list


async def test_unsupported_mode_raises_a_translated_error(hass):
    """A mode the device cannot do must reach the UI as an error - over the
    service path a silent warning would look like success."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry, service = register_device(hass)
    service._device.show_radio.side_effect = DivoomUnsupportedError("Pixoo", "showing the radio")

    with pytest.raises(HomeAssistantError) as error:
        await hass.services.async_call(
            DOMAIN, "radio", {CONF_ENTRY_ID: entry.entry_id, "value": True}, blocking=True
        )

    assert error.value.translation_key == "mode_unsupported"
    assert error.value.translation_placeholders == {"device": "Pixoo", "mode": "radio"}


def test_notify_path_continues_on_unsupported_modes():
    """Backwards compatibility: notify.<device> behaved like this before the
    services existed and must keep doing so."""
    service = make_mocked_service()
    service._device.show_radio.side_effect = DivoomUnsupportedError("Pixoo", "showing the radio")

    assert service.send_message("radio", data={"value": True}) is True


def test_call_mode_raises_without_continue_on_error():
    """The default has to be the strict one, whoever calls it - only the
    legacy notify path opts out."""
    service = make_mocked_service()
    service._device.show_radio.side_effect = DivoomUnsupportedError("Pixoo", "showing the radio")

    with pytest.raises(DivoomUnsupportedError):
        service.call_mode("radio", {"value": True})

    assert service.call_mode("radio", {"value": True}, continue_on_error=True) is True


def test_unsupported_warns_before_it_raises(caplog):
    """The log line is unchanged from before the exception existed, so log
    based troubleshooting keeps working."""
    device = Pixoo(mac="11:22:33:44:55:66")

    with pytest.raises(DivoomUnsupportedError):
        device.show_radio(True)

    assert "Pixoo: this device does not support showing the radio." in caplog.text


def test_signal_is_backpack_only():
    """Both modes send the same view number, but only the backpack has the
    traffic signal and only the others have a microphone."""
    backpack = Backpack(mac="11:22:33:44:55:66")
    backpack.send_command = Mock()
    pixoo = Pixoo(mac="11:22:33:44:55:66")
    pixoo.send_command = Mock()

    backpack.show_signal(1, color1=[1, 2, 3], color2=[4, 5, 6])
    pixoo.show_visualization(1, color1=[1, 2, 3], color2=[4, 5, 6])

    assert backpack.send_command.call_args == pixoo.send_command.call_args

    with pytest.raises(DivoomUnsupportedError):
        backpack.show_visualization(1)
    with pytest.raises(DivoomUnsupportedError):
        pixoo.show_signal(1)


@pytest.mark.parametrize("device_cls", [Aurabox, TimeboxMini])
def test_temperature_is_aurabox_and_timeboxmini_only(device_cls):
    """Only these two have a temperature channel - everywhere else the mode
    used to switch the clock instead, which is a setting change nobody asked
    for, so it has to be refused rather than guessed."""
    device = device_cls(mac="11:22:33:44:55:66")
    device.send_command = Mock()

    device.show_temperature(value="°C")

    assert device.send_command.call_args_list[0].args[0] == "set view"

    with pytest.raises(DivoomUnsupportedError):
        Pixoo(mac="11:22:33:44:55:66").show_temperature(value="°C")


def test_every_valid_mode_has_a_service():
    """A mode reachable through notify but not registered as a service would
    stay invisible in the UI without anything failing."""
    assert set(SERVICE_SCHEMAS) == set(VALID_MODES)


def test_device_examples_match_the_service_schemas():
    """The example files are the first thing users copy from, so every block
    in them has to be a call the action schema actually accepts."""
    checked = 0
    for path in sorted((COMPONENT_PATH / "devices").glob("*.txt")):
        for block in path.read_text(encoding="utf-8").split("\n\n"):
            if "action:" not in block:
                continue

            example = parse_yaml(block)
            mode = example["action"].removeprefix("{}.".format(DOMAIN))
            assert mode in SERVICE_SCHEMAS, (path.name, example["action"])

            SERVICE_SCHEMAS[mode](example["data"])
            checked += 1

    assert checked == 241 # every block, not just the ones that happened to parse


def _number_selector(field_definition):
    return field_definition.get("selector", {}).get("number")


def _range_of(validator):
    """Dig the vol.Range out of a vol.All(Coerce(...), Range(...)) chain."""
    for inner in getattr(validator, "validators", ()):
        if isinstance(inner, vol.Range):
            return inner
    return None


SERVICES_YAML = load_yaml(str(COMPONENT_PATH / "services.yaml"))

# a payload per mode that satisfies every vol.Required, so a schema rejection
# in the bounds tests below can only come from the field under test
VALID_PARAMS = {}
for _case in DISPATCH_CASES:
    VALID_PARAMS.setdefault(_case[0], _case[1])

NUMBER_FIELDS = [
    (mode, field)
    for mode, definition in SERVICES_YAML.items()
    for field, field_definition in definition["fields"].items()
    if _number_selector(field_definition) is not None
]
NUMBER_IDS = ["{}.{}".format(mode, field) for mode, field in NUMBER_FIELDS]


@pytest.mark.parametrize("mode,field", NUMBER_FIELDS, ids=NUMBER_IDS)
def test_services_yaml_number_bounds_match_the_schema(mode, field):
    """A bound the UI enforces but the schema doesn't (or the other way
    round) lets the frontend offer values the call then rejects."""
    selector = _number_selector(SERVICES_YAML[mode]["fields"][field])
    bounds = _range_of(SERVICE_SCHEMAS[mode].schema[field])

    # weather.value is bounded on the celsius-converted value, so neither side
    # can name a limit - either both carry one and agree, or neither does
    if bounds is None:
        assert selector.get("min") is None, (mode, field)
        assert selector.get("max") is None, (mode, field)
        return

    assert selector.get("min") == bounds.min, (mode, field)
    assert selector.get("max") == bounds.max, (mode, field)


BOUNDED_NUMBER_FIELDS = [
    (mode, field) for mode, field in NUMBER_FIELDS
    if _number_selector(SERVICES_YAML[mode]["fields"][field]).get("max") is not None
]
BOUNDED_NUMBER_IDS = [
    "{}.{}".format(mode, field) for mode, field in BOUNDED_NUMBER_FIELDS
]


@pytest.mark.parametrize("mode,field", BOUNDED_NUMBER_FIELDS, ids=BOUNDED_NUMBER_IDS)
def test_number_fields_stop_at_the_protocol_limit(mode, field):
    """Above the width the protocol packs the value into, to_bytes would
    raise OverflowError deep in the executor thread - the schema has to
    catch it first, while the limit itself still has to be reachable."""
    limit = _number_selector(SERVICES_YAML[mode]["fields"][field])["max"]
    schema = SERVICE_SCHEMAS[mode]
    payload = {CONF_ENTRY_ID: "entry", **VALID_PARAMS.get(mode, {})}

    schema({**payload, field: limit})

    with pytest.raises(vol.Invalid):
        schema({**payload, field: limit + 1})


def test_selector_options_are_translated():
    """HA looks up select: options under a top-level "selector" block. A
    missing entry there shows the raw values in the UI without any error."""
    strings = json.loads((COMPONENT_PATH / "strings.json").read_text(encoding="utf-8"))

    found = 0
    for mode, definition in SERVICES_YAML.items():
        for field, field_definition in definition["fields"].items():
            selector = field_definition.get("selector", {}).get("select")
            if selector is None:
                continue

            key = selector.get("translation_key")
            if key is None:
                assert all(isinstance(option, str) for option in selector["options"])
                continue

            assert key in strings["selector"], (mode, field)
            assert set(strings["selector"][key]["options"]) == set(selector["options"])
            found += 1

    assert found


# hassfest's rule for every key in strings.json and translations/*.json
TRANSLATION_KEY = re.compile(r"^[a-z0-9]([a-z0-9_-]*[a-z0-9])?$")


def _keys(node):
    for key, value in node.items():
        yield key
        if isinstance(value, dict):
            yield from _keys(value)


def test_translation_keys_are_valid():
    """Select options become JSON keys under "selector", and hassfest only
    accepts [a-z0-9-_] there. "°C" passes every test in this file and still
    fails the whole validation in CI, so the rule is checked here too."""
    for path in [COMPONENT_PATH / "strings.json", *(COMPONENT_PATH / "translations").glob("*.json")]:
        document = json.loads(path.read_text(encoding="utf-8"))
        invalid = [key for key in _keys(document) if not TRANSLATION_KEY.match(key)]
        assert invalid == [], (path.name, invalid)


def test_every_service_field_is_a_known_notify_param():
    """Every service field is passed straight into call_mode's data dict. A
    name call_mode doesn't know would be silently ignored - the call would
    look successful and do nothing."""
    notify_params = {
        value for name, value in vars(notify_module).items()
        if name.startswith("PARAM_") and isinstance(value, str)
    }

    for mode, schema in SERVICE_SCHEMAS.items():
        fields = {str(marker) for marker in schema.schema} - {CONF_ENTRY_ID}
        assert fields <= notify_params, (mode, fields - notify_params)


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
        "mode_unsupported",
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
