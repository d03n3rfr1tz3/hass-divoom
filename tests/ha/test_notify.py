"""HA integration tests for notify.py, per the plan's Paket 1c: service
setup via async_get_service, and send_message's mode dispatch. The dispatch
tests swap in a unittest.mock.Mock() for DivoomNotificationService._device,
skipping DivoomNotificationService.__init__ entirely (it picks a real device
class and constructs a real socket-backed object) - so these run with no
socket involved at all, only asserting which show_*/send_* call reaches the
mock and with what arguments.
"""
from __future__ import annotations

import logging
import os
from unittest.mock import Mock, patch

import pytest

from homeassistant.components.notify import ATTR_DATA

from custom_components.divoom.const import CONF_DEVICE_TYPE, CONF_MEDIA_DIR, DOMAIN
from custom_components.divoom.notify import (
    PARAM_COLOR,
    PARAM_FILE,
    PARAM_FONT,
    PARAM_MODE,
    PARAM_NUMBER,
    PARAM_RAW,
    PARAM_TEXT,
    PARAM_TIME,
    PARAM_VALUE,
    PARAM_WEATHER,
    DivoomNotificationService,
    async_get_service,
)
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_PORT


def make_mocked_service(media_directory="pixelart", font_directory="fonts"):
    """A DivoomNotificationService with a Mock() in place of a real device,
    bypassing __init__ (which would instantiate a real, socket-backed
    device class)."""
    service = DivoomNotificationService.__new__(DivoomNotificationService)
    service._device = Mock()
    service._media_directory = media_directory
    service._font_directory = font_directory
    return service


async def test_async_get_service_registers_and_picks_device_class(hass):
    """Service setup wires up the right device class for device_type and
    registers the service under its MAC in hass.data. connect() is patched
    out: it would open a real Bluetooth RFCOMM socket, which is out of
    scope here (and pytest-socket blocks connect() to any non-localhost
    host anyway, regardless of platform) - async_get_service's own wiring
    is what's under test, not the socket connection itself."""
    with patch.object(DivoomNotificationService, "connect"):
        service = await async_get_service(
            hass,
            {
                CONF_MAC: "11:22:33:44:55:66",
                CONF_PORT: 1,
                CONF_DEVICE_TYPE: "pixoo",
                CONF_MEDIA_DIR: "pixelart",
            },
        )

    assert type(service._device).__name__ == "Pixoo"
    assert hass.data[DOMAIN]["loaded"]["11:22:33:44:55:66"] is service


async def test_async_get_service_invalid_device_type_logs_device_type(hass, caplog):
    """The error message used to format media_directory into the
    "device_type {0} does not exist" string instead of device_type itself."""
    caplog.set_level(logging.ERROR)
    with patch.object(DivoomNotificationService, "connect"):
        service = await async_get_service(
            hass,
            {
                CONF_MAC: "11:22:33:44:55:66",
                CONF_PORT: 1,
                CONF_DEVICE_TYPE: "not-a-real-device-type",
                CONF_MEDIA_DIR: "pixelart",
            },
        )

    assert service._device is None
    assert "not-a-real-device-type" in caplog.text


def test_del_and_exit_are_noop_when_device_is_none():
    """__init__ leaves _device as None for an unrecognised device_type;
    __del__/__exit__ used to call self._device.disconnect() unconditionally
    and crash with AttributeError in that case."""
    service = DivoomNotificationService.__new__(DivoomNotificationService)
    service._device = None

    service.__del__()
    service.__exit__(None, None, None)


def test_send_message_text_mode_splits_color_and_calls_show_text():
    service = make_mocked_service()

    result = service.send_message(
        data={
            PARAM_MODE: "text",
            PARAM_TEXT: "hello",
            PARAM_COLOR: [[255, 0, 0], [0, 255, 0]],
        }
    )

    assert result is True
    service._device.show_text.assert_called_once_with(
        "hello", None, size=None, time=None, color1=[255, 0, 0], color2=[0, 255, 0]
    )


def test_send_message_visualization_mode_splits_color_and_calls_show_visualization():
    service = make_mocked_service()

    result = service.send_message(
        data={
            PARAM_MODE: "visualization",
            PARAM_NUMBER: 3,
            PARAM_COLOR: [[1, 2, 3]],
        }
    )

    assert result is True
    service._device.show_visualization.assert_called_once_with(
        number=3, color1=[1, 2, 3], color2=None
    )


@pytest.mark.parametrize(
    ("weather_value", "expected_weathernum"),
    [
        ("rainy", 6),
        ("unknown-condition", None),
        (2.6, 3),
        (7, 7),
    ],
)
def test_send_message_weather_mode_converts_weather_value(
    weather_value, expected_weathernum
):
    service = make_mocked_service()

    result = service.send_message(
        data={PARAM_MODE: "weather", PARAM_VALUE: "22°C", PARAM_WEATHER: weather_value}
    )

    assert result is True
    service._device.send_weather.assert_called_once_with(
        value="22°C", weather=expected_weathernum
    )


def test_send_message_image_mode_joins_media_directory_and_calls_show_image():
    service = make_mocked_service(media_directory="/media/pixelart")

    result = service.send_message(
        data={PARAM_MODE: "image", PARAM_FILE: "smiley32.gif", PARAM_TIME: 5}
    )

    assert result is True
    service._device.show_image.assert_called_once_with(
        os.path.join("/media/pixelart", "smiley32.gif"), time=5
    )


def test_send_message_image_mode_without_file_logs_and_returns_false():
    service = make_mocked_service(media_directory="/media/pixelart")

    result = service.send_message(data={PARAM_MODE: "image"})

    assert result is False
    service._device.show_image.assert_not_called()


def test_send_message_image_mode_rejects_path_traversal():
    """os.path.join drops the base directory entirely for an absolute
    filename, and '../' can walk back out of a relative one - both used to
    let a service call read any file the HA process can access."""
    service = make_mocked_service(media_directory="/media/pixelart")

    result = service.send_message(
        data={PARAM_MODE: "image", PARAM_FILE: "../../../etc/passwd"}
    )

    assert result is False
    service._device.show_image.assert_not_called()


def test_send_message_text_mode_without_font_still_calls_show_text():
    """font is optional - PARAM_FONT absent must not be treated as a
    traversal rejection."""
    service = make_mocked_service()

    result = service.send_message(data={PARAM_MODE: "text", PARAM_TEXT: "hello"})

    assert result is True
    service._device.show_text.assert_called_once_with(
        "hello", None, size=None, time=None, color1=None, color2=None
    )


def test_send_message_text_mode_rejects_font_path_traversal():
    service = make_mocked_service(font_directory="/opt/divoom/fonts")

    result = service.send_message(
        data={PARAM_MODE: "text", PARAM_TEXT: "hello", PARAM_FONT: "../../../etc/passwd"}
    )

    assert result is False
    service._device.show_text.assert_not_called()


def test_send_message_raw_mode_without_raw_logs_and_returns_false():
    service = make_mocked_service()

    result = service.send_message(data={PARAM_MODE: "raw"})

    assert result is False
    service._device.send_command.assert_not_called()


def test_send_message_connect_mode_does_not_reconnect_first():
    service = make_mocked_service()

    result = service.send_message(data={PARAM_MODE: "connect"})

    assert result is True
    service._device.connect.assert_called_once_with()
    service._device.reconnect.assert_not_called()


def test_send_message_disconnect_mode_does_not_reconnect_first():
    service = make_mocked_service()

    result = service.send_message(data={PARAM_MODE: "disconnect"})

    assert result is True
    service._device.disconnect.assert_called_once_with()
    service._device.reconnect.assert_not_called()


def test_send_message_other_modes_reconnect_first():
    service = make_mocked_service()

    service.send_message(data={PARAM_MODE: "on"})

    service._device.reconnect.assert_called_once_with(skipPing=False)
    service._device.send_on.assert_called_once_with()


def test_send_message_invalid_mode_logs_and_returns_false():
    service = make_mocked_service()

    result = service.send_message(data={PARAM_MODE: "not-a-real-mode"})

    assert result is False
    # unknown modes still reconnect first (that check runs before the mode
    # dispatch), but no show_*/send_* call is ever reached for them
    service._device.reconnect.assert_called_once_with(skipPing=False)
    assert len(service._device.mock_calls) == 1


def test_send_message_empty_message_and_no_data_returns_false():
    service = make_mocked_service()

    result = service.send_message()

    assert result is False
    assert service._device.mock_calls == []
