"""Switching states and sending images or animations to a divoom device."""
import logging, os, socket
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from homeassistant.components.notify import (
    ATTR_DATA,
    PLATFORM_SCHEMA,
    BaseNotificationService
)

from homeassistant.const import CONF_HOST, CONF_MAC, CONF_PORT
from .const import CONF_DEVICE_TYPE, CONF_MEDIA_DIR, CONF_MEDIA_DIR_DEFAULT, CONF_ESCAPE_PAYLOAD, DOMAIN  # pylint:disable=unused-import

_LOGGER = logging.getLogger(__package__)

PARAM_MODE = 'mode'
PARAM_TEXT = 'text'
PARAM_VALUE = 'value'

PARAM_CLOCK = 'clock'
PARAM_TWENTYFOUR = 'twentyfour'
PARAM_WEATHER = 'weather'
PARAM_TEMP = 'temp'
PARAM_CALENDAR = 'calendar'
PARAM_HOT = 'hot'

PARAM_ALARMMODE = 'alarmmode'
PARAM_AUDIOMODE = 'audiomode'
PARAM_BACKGROUNDMODE = 'backgroundmode'
PARAM_STREAMMODE = 'streammode'
PARAM_TRIGGERMODE = 'triggermode'
PARAM_BRIGHTNESS = 'brightness'
PARAM_COLOR = 'color'
PARAM_COUNTDOWN = 'countdown'
PARAM_FREQUENCY = 'frequency'
PARAM_NUMBER = 'number'
PARAM_WEEKDAY = 'weekday'
PARAM_VOLUME = 'volume'

PARAM_SLEEPMODE = 'sleepmode'
PARAM_SLEEPTIME = 'time'

PARAM_PLAYER1 = 'player1'
PARAM_PLAYER2 = 'player2'

PARAM_FILE = 'file'

PARAM_RAW = 'raw'

VALID_MODES = [
    'alarm',
    'brightness',
    'clock',
    'connect',
    'countdown',
    'datetime',
    'design',
    'disconnect',
    'effects',
    'equalizer',
    'game',
    'gamecontrol',
    'image',
    'keyboard',
    'light',
    'lyrics',
    'memorial',
    'noise',
    'off',
    'on',
    'playstate',
    'radio',
    'raw',
    'scoreboard',
    'signal',
    'sleep',
    'timer',
    'visualization',
    'volume',
    'weather',
]

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
    vol.Optional(CONF_HOST): cv.string,
    vol.Required(CONF_MAC): cv.string,
    vol.Optional(CONF_PORT, default=1): cv.port,
    vol.Required(CONF_DEVICE_TYPE): cv.string,
    vol.Required(CONF_MEDIA_DIR, default=CONF_MEDIA_DIR_DEFAULT): cv.string,
    vol.Optional(CONF_ESCAPE_PAYLOAD, default=False): cv.boolean
})

async def async_get_service(
    hass: HomeAssistant,
    config: ConfigType,
    discovery_info: DiscoveryInfoType | None = None,
):
    """Get the Divoom notification service."""
    
    host = None
    mac = None
    port = 1
    device_type = "pixoo"
    media_directory = "pixelart"
    escape_payload = None

    if discovery_info is not None:
        if CONF_HOST in discovery_info: host = discovery_info[CONF_HOST]
        if CONF_MAC in discovery_info: mac = discovery_info[CONF_MAC]
        if CONF_PORT in discovery_info: port = discovery_info[CONF_PORT]
        if CONF_DEVICE_TYPE in discovery_info: device_type = discovery_info[CONF_DEVICE_TYPE]
        if CONF_MEDIA_DIR in discovery_info: media_directory = hass.config.path(discovery_info[CONF_MEDIA_DIR])
        if CONF_ESCAPE_PAYLOAD in discovery_info: escape_payload = discovery_info[CONF_ESCAPE_PAYLOAD]
    
    if config is not None:
        if CONF_HOST in config: host = config[CONF_HOST]
        if CONF_MAC in config: mac = config[CONF_MAC]
        if CONF_PORT in config: port = config[CONF_PORT]
        if CONF_DEVICE_TYPE in config: device_type = config[CONF_DEVICE_TYPE]
        if CONF_MEDIA_DIR in config: media_directory = hass.config.path(config[CONF_MEDIA_DIR])
        if CONF_ESCAPE_PAYLOAD in config: escape_payload = config[CONF_ESCAPE_PAYLOAD]
    
    notificationService = DivoomNotificationService(host, mac, port, device_type, media_directory, escape_payload)

    hass.data.setdefault(DOMAIN, {})
    domainConfig = hass.data.get(DOMAIN)
    domainConfig.setdefault('loaded', {})

    loadedServices = domainConfig.get('loaded')
    loadedServices[mac] = notificationService
    
    try:
        await hass.async_add_executor_job(notificationService.connect)
    except BrokenPipeError as error:
        _LOGGER.error("Error while initially connecting to the Divoom device. %s", error, exc_info=True, stack_info=True)
        pass
    except socket.error as error:
        _LOGGER.error("Error while initially connecting to the Divoom device. %s", error, exc_info=True, stack_info=True)
        pass

    return notificationService

class DivoomNotificationService(BaseNotificationService):
    """Implement the notification service for Divoom."""

    def __init__(self, host, mac, port, device_type, media_directory, escape_payload):
        assert mac is not None
        assert port is not None
        assert device_type is not None
        assert media_directory is not None

        self._device = None
        self._media_directory = media_directory

        if device_type == 'aurabox':
            from .devices.aurabox import Aurabox
            self._device = Aurabox(host=host, mac=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'backpack':
            from .devices.backpack import BackPack
            self._device = BackPack(host=host, mac=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'ditoo':
            from .devices.ditoo import Ditoo
            self._device = Ditoo(host=host, mac=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'ditoomic':
            from .devices.ditoomic import DitooMic
            self._device = DitooMic(host=host, mac=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'pixoo':
            from .devices.pixoo import Pixoo
            self._device = Pixoo(host=host, mac=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'pixoomax':
            from .devices.pixoomax import PixooMax
            self._device = PixooMax(host=host, mac=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'timebox':
            from .devices.timebox import Timebox
            self._device = Timebox(host=host, mac=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'timeboxmini':
            from .devices.timeboxmini import TimeboxMini
            self._device = TimeboxMini(host=host, mac=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'timoo':
            from .devices.timoo import Timoo
            self._device = Timoo(host=host, mac=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if device_type == 'tivoo':
            from .devices.tivoo import Tivoo
            self._device = Tivoo(host=host, mac=mac, port=port, escapePayload=escape_payload, logger=_LOGGER)
        
        if self._device is None:
            _LOGGER.error("device_type {0} does not exist, divoom will not work".format(media_directory))
        elif not os.path.isdir(media_directory):
            _LOGGER.error("media_directory {0} does not exist, divoom may not work properly".format(media_directory))

    def __del__(self):
        self._device.disconnect()

    def __exit__(self, type, value, traceback):
        self._device.disconnect()

    def connect(self):
        self._device.connect()

    def disconnect(self):
        self._device.disconnect()

    def send_message(self, message="", **kwargs):
        if message == "" and kwargs.get(ATTR_DATA) is None:
            _LOGGER.error("Service call needs more information")
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
            twentyfour = data.get(PARAM_TWENTYFOUR)
            weather = data.get(PARAM_WEATHER)
            temp = data.get(PARAM_TEMP)
            calendar = data.get(PARAM_CALENDAR)
            color = data.get(PARAM_COLOR)
            hot = data.get(PARAM_HOT)
            self._device.show_clock(clock=clock, twentyfour=twentyfour, weather=weather, temp=temp, calendar=calendar, color=color, hot=hot)

        elif mode == "light":
            brightness = data.get(PARAM_BRIGHTNESS)
            color = data.get(PARAM_COLOR)
            self._device.show_light(color=color, brightness=brightness, power=True)

        elif mode == "effects":
            number = data.get(PARAM_NUMBER)
            self._device.show_effects(number=number)

        elif mode == "signal" or mode == "visualization":
            number = data.get(PARAM_NUMBER)
            self._device.show_visualization(number=number)

        elif mode == "scoreboard":
            player1 = data.get(PARAM_PLAYER1)
            player2 = data.get(PARAM_PLAYER2)
            self._device.show_scoreboard(blue=player1, red=player2)

        elif mode == "lyrics":
            self._device.show_lyrics()

        elif mode == "equalizer":
            number = data.get(PARAM_NUMBER)
            audioMode = data.get(PARAM_AUDIOMODE)
            backgroundMode = data.get(PARAM_BACKGROUNDMODE)
            streamMode = data.get(PARAM_STREAMMODE)
            self._device.show_equalizer(number=number, audioMode=audioMode, backgroundMode=backgroundMode, streamMode=streamMode)

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

        elif mode == "sleep":
            sleepvalue = data.get(PARAM_VALUE)
            sleeptime = data.get(PARAM_SLEEPTIME)
            sleepmode = data.get(PARAM_SLEEPMODE)
            volume = data.get(PARAM_VOLUME)
            color = data.get(PARAM_COLOR)
            brightness = data.get(PARAM_BRIGHTNESS)
            frequency = data.get(PARAM_FREQUENCY)
            self._device.show_sleep(sleepvalue, sleeptime, sleepmode, volume, color, brightness, frequency)

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
            validModes = ""
            for validMode in VALID_MODES:
                if len(validModes) > 0: validModes += ", "
                validModes += "'{0}'".format(validMode)

            _LOGGER.error("Invalid mode '{0}'. Must be one of: {1}".format(mode, validModes))
            return False
        
        return True
