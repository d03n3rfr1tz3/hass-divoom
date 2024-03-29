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
from homeassistant.const import CONF_MAC, CONF_PORT

_LOGGER = logging.getLogger(__package__)

CONF_DEVICE_TYPE = 'device_type'
CONF_MEDIA_DIR = 'media_directory'
CONF_ESCAPE_PAYLOAD = 'escape_payload'

PARAM_MODE = 'mode'
PARAM_TEXT = 'text'
PARAM_VALUE = 'value'

PARAM_CLOCK = 'clock'
PARAM_WEATHER = 'weather'
PARAM_TEMP = 'temp'
PARAM_CALENDAR = 'calendar'
PARAM_HOT = 'hot'

PARAM_ALARMMODE = 'alarmmode'
PARAM_TRIGGERMODE = 'triggermode'
PARAM_BRIGHTNESS = 'brightness'
PARAM_COLOR = 'color'
PARAM_COUNTDOWN = 'countdown'
PARAM_FREQUENCY = 'frequency'
PARAM_NUMBER = 'number'
PARAM_WEEKDAY = 'weekday'
PARAM_VOLUME = 'volume'

PARAM_PLAYER1 = 'player1'
PARAM_PLAYER2 = 'player2'

PARAM_FILE = 'file'

PARAM_RAW = 'raw'

VALID_MODES = {'on', 'off', 'connect', 'disconnect', 'clock', 'light', 'effects', 'visualization', 'scoreboard', 'lyrics', 'design', 'image', 'brightness', 'datetime', 'game', 'gamecontrol', 'keyboard', 'playstate', 'radio', 'volume', 'weather', 'countdown', 'noise', 'timer', 'alarm', 'memorial', 'raw'}
WEATHER_MODES = {
    'clear-night': 1, 
    'cloudy': 3, 
    'exceptional': 3, 
    'fog': 9, 
    'hail': 6, 
    'lightning': 5, 
    'lightning-rainy': 5, 
    'partlycloudy': 3, 
    'pouring': 6, 
    'rainy': 6, 
    'snowy': 8, 
    'snowy-rainy': 8, 
    'sunny': 1, 
    'windy': 3, 
    'windy-variant': 3
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_MAC): cv.string,
    vol.Optional(CONF_PORT, default=1): cv.port,
    vol.Required(CONF_DEVICE_TYPE): cv.string,
    vol.Required(CONF_MEDIA_DIR, default="pixelart"): cv.string,
    vol.Optional(CONF_ESCAPE_PAYLOAD, default=False): cv.boolean
})

def get_service(hass, config, discovery_info=None):
    """Get the Divoom notification service."""
    
    mac = config[CONF_MAC]
    port = config[CONF_PORT]
    device_type = config[CONF_DEVICE_TYPE]
    media_directory = hass.config.path(config[CONF_MEDIA_DIR])
    escape_payload = config[CONF_ESCAPE_PAYLOAD]
    
    return DivoomNotificationService(mac, port, device_type, media_directory, escape_payload)


class DivoomNotificationService(BaseNotificationService):
    """Implement the notification service for Divoom."""

    def __init__(self, mac, port, device_type, media_directory, escape_payload):
        self._media_directory = media_directory

        if device_type == 'pixoo':
            from .devices.pixoo import Pixoo
            self._device = Pixoo(host=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'pixoomax':
            from .devices.pixoomax import PixooMax
            self._device = PixooMax(host=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'timebox':
            from .devices.timebox import Timebox
            self._device = Timebox(host=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'tivoo':
            from .devices.tivoo import Tivoo
            self._device = Tivoo(host=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'ditoo':
            from .devices.ditoo import Ditoo
            self._device = Ditoo(host=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if self._device is None:
            _LOGGER.error("device_type {0} does not exist, divoom will not work".format(media_directory))
        elif not os.path.isdir(media_directory):
            _LOGGER.error("media_directory {0} does not exist, divoom may not work properly".format(media_directory))
        
        self._device.connect()

    def __del__(self):
        self._device.disconnect()

    def __exit__(self, type, value, traceback):
        self._device.disconnect()

    def send_message(self, message="", **kwargs):
        if kwargs.get(ATTR_MESSAGE) is None and kwargs.get(ATTR_DATA) is None:
            _LOGGER.error("Service call needs a message type")
            return False
        
        data = kwargs.get(ATTR_DATA) or {}
        mode = data.get(PARAM_MODE) or message
        
        if mode != "connect" and mode != "disconnect":
            skipPing = True if mode == "gamecontrol" or mode == "raw" else False
            self._device.reconnect(skipPing=skipPing)

        if mode == 'on':
            self._device.show_light(color=[0x01, 0x01, 0x01], brightness=100, power=True)

        elif mode == 'off':
            self._device.show_light(color=[0x01, 0x01, 0x01], brightness=0, power=False)
        
        elif mode == "connect":
            self._device.connect()

        elif mode == "disconnect":
            self._device.disconnect()

        elif mode == "brightness":
            value = data.get(PARAM_BRIGHTNESS) or data.get(PARAM_NUMBER) or data.get(PARAM_VALUE)
            self._device.send_brightness(value=value)

        elif mode == "volume":
            value = data.get(PARAM_VOLUME) or data.get(PARAM_NUMBER) or data.get(PARAM_VALUE)
            self._device.send_volume(value=value)

        elif mode == "keyboard":
            value = data.get(PARAM_VALUE)
            self._device.send_keyboard(value=value)

        elif mode == "playstate":
            value = data.get(PARAM_VALUE)
            self._device.send_playstate(value=value)

        elif mode == "datetime":
            value = data.get(PARAM_VALUE)
            self._device.send_datetime(value=value)

        elif mode == "weather":
            value = data.get(PARAM_VALUE)
            weather = data.get(PARAM_WEATHER)

            weathernum = None
            if isinstance(weather, int):
                weathernum = weather
            elif isinstance(weather, float):
                weathernum = round(weather)
            elif isinstance(weather, str):
                weathernum = WEATHER_MODES.get(weather) or None

            self._device.send_weather(value=value, weather=weathernum)

        elif mode == "clock":
            clock = data.get(PARAM_CLOCK)
            weather = data.get(PARAM_WEATHER)
            temp = data.get(PARAM_TEMP)
            calendar = data.get(PARAM_CALENDAR)
            color = data.get(PARAM_COLOR)
            hot = data.get(PARAM_HOT)
            self._device.show_clock(clock=clock, weather=weather, temp=temp, calendar=calendar, color=color, hot=hot)

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

        elif mode == "lyrics":
            self._device.show_lyrics()

        elif mode == "design":
            number = data.get(PARAM_NUMBER)
            self._device.show_design(number=number)

        elif mode == "image":
            image_file = data.get(PARAM_FILE)
            image_path = os.path.join(self._media_directory, image_file)
            self._device.show_image(image_path)

        elif mode == "countdown":
            value = data.get(PARAM_VALUE)
            countdown = data.get(PARAM_COUNTDOWN)
            self._device.show_countdown(value=value, countdown=countdown)

        elif mode == "noise":
            value = data.get(PARAM_VALUE)
            self._device.show_noise(value=value)

        elif mode == "timer":
            value = data.get(PARAM_VALUE)
            self._device.show_timer(value=value)

        elif mode == "alarm":
            number = data.get(PARAM_NUMBER)
            time = data.get(PARAM_VALUE)
            weekdays = data.get(PARAM_WEEKDAY)
            alarm_mode = data.get(PARAM_ALARMMODE)
            trigger_mode = data.get(PARAM_TRIGGERMODE)
            frequency = data.get(PARAM_FREQUENCY)
            volume = data.get(PARAM_VOLUME)
            self._device.show_alarm(number=number, time=time, weekdays=weekdays, alarmMode=alarm_mode, triggerMode=trigger_mode, frequency=frequency, volume=volume)

        elif mode == "memorial":
            number = data.get(PARAM_NUMBER)
            value = data.get(PARAM_VALUE)
            text = data.get(PARAM_TEXT)
            self._device.show_memorial(number=number, value=value, text=text, animate=True)

        elif mode == "radio":
            value = data.get(PARAM_VALUE)
            frequency = data.get(PARAM_FREQUENCY)
            self._device.show_radio(value=value, frequency=frequency)

        elif mode == "game":
            value = data.get(PARAM_VALUE)
            self._device.show_game(value=value)

        elif mode == "gamecontrol":
            value = data.get(PARAM_VALUE)
            self._device.send_gamecontrol(value=value)

        elif mode == "raw":
            raw = data.get(PARAM_RAW)
            self._device.send_command(command=raw[0], args=raw[1:])

        else:
            _LOGGER.error("Invalid mode '{0}', must be one of 'on', 'off', 'connect', 'disconnect', 'clock', 'light', 'effects', 'visualization', 'scoreboard', 'lyrics', 'design', 'image', 'brightness', 'datetime', 'game', 'gamecontrol', 'keyboard', 'playstate', 'radio', 'volume', 'weather', 'countdown', 'noise', 'timer', 'alarm', 'memorial', 'raw'".format(mode))
            return False
        
        return True
