"""Switching states and sending images or animations to a divoom device."""
import logging, os
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_MESSAGE,
    ATTR_TITLE,
    PLATFORM_SCHEMA,
    BaseNotificationService
)
from homeassistant.const import CONF_MAC

_LOGGER = logging.getLogger(__name__)

CONF_DEVICE_TYPE = 'device_type'
CONF_MEDIA_DIR = 'media_directory'

PARAM_MODE = 'mode'
PARAM_BRIGHTNESS = 'brightness'
PARAM_COLOR = 'color'
PARAM_NUMBER = 'number'

PARAM_CLOCK = 'clock'
PARAM_WEATHER = 'weather'
PARAM_TEMP = 'temp'
PARAM_CALENDAR = 'calendar'

PARAM_PLAYER1 = 'player1'
PARAM_PLAYER2 = 'player2'

PARAM_FILE = 'file'

PARAM_RAW = 'raw'

VALID_MODES = {'on', 'off', 'clock', 'light', 'effects', 'visualization', 'scoreboard', 'design', 'image'}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_MAC): cv.string,
    vol.Required(CONF_DEVICE_TYPE): cv.string,
    vol.Required(CONF_MEDIA_DIR, default="pixelart"): cv.string,
})

def get_service(hass, config, discovery_info=None):
    """Get the Divoom notification service."""
    
    mac = config[CONF_MAC]
    device_type = config[CONF_DEVICE_TYPE]
    media_directory = hass.config.path(config[CONF_MEDIA_DIR])
    
    return DivoomNotificationService(mac, device_type, media_directory)


class DivoomNotificationService(BaseNotificationService):
    """Implement the notification service for Divoom."""

    def __init__(self, mac, device_type, media_directory):
        if device_type == 'pixoo':
            from .devices.pixoo import Pixoo
            self._mac = mac
            self._media_directory = media_directory
            self._device = Pixoo(host=mac, logger=_LOGGER)
            self._device.connect()
        
        if self._device is None:
            _LOGGER.error("device_type {0} does not exist, divoom will not work".format(media_directory))
        elif not os.path.isdir(media_directory):
            _LOGGER.error("media_directory {0} does not exist, divoom may not work properly".format(media_directory))


    def send_message(self, message="", **kwargs):
        if kwargs.get(ATTR_DATA) is None:
            _LOGGER.error("Service call needs a message type")
            return False
        
        self._device.reconnect()
        data = kwargs.get(ATTR_DATA)
        mode = data.get(PARAM_MODE)
        
        if mode == False or mode == 'off':
            self._device.show_light(color=[0x01, 0x01, 0x01], brightness=0, power=False)
        
        elif mode == 'on':
            self._device.show_light(color=[0x01, 0x01, 0x01], brightness=100, power=True)

        elif mode == "clock":
            clock = data.get(PARAM_CLOCK)
            weather = data.get(PARAM_WEATHER)
            temp = data.get(PARAM_TEMP)
            calendar = data.get(PARAM_CALENDAR)
            color = data.get(PARAM_COLOR)
            self._device.show_clock(clock=clock, weather=weather, temp=temp, calendar=calendar, color=color)

        elif mode == "light":
            brightness = data.get(PARAM_BRIGHTNESS)
            color = data.get(PARAM_COLOR)
            self._device.show_light(color=color, brightness=brightness, power=True)

        elif mode == "effects":
            number = data.get(PARAM_NUMBER)
            self._device.show_effects(number=number)

        elif mode == "visualization":
            number = data.get(PARAM_NUMBER)
            self._device.show_visualization(number=number)

        elif mode == "scoreboard":
            player1 = data.get(PARAM_PLAYER1)
            player2 = data.get(PARAM_PLAYER2)
            self._device.show_scoreboard(blue=player1, red=player2)

        elif mode == "design":
            self._device.show_design()

        elif mode == "image":
            image_file = data.get(PARAM_FILE)
            image_path = os.path.join(self._media_directory, image_file)
            self._device.show_image(image_path)

        else:
            _LOGGER.error("Invalid mode '{0}', must be one of 'on', 'off', 'clock', 'light', 'weather', 'temp', 'calendar', 'effects', 'visualization', 'scoreboard', 'image'".format(mode))
            return False
        
        return True
