"""Domain services for divoom, one per device mode."""
import logging, re
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from homeassistant.const import CONF_MAC
from .const import CONF_ENTRY_ID, DOMAIN
from .devices.divoom import DivoomUnsupportedError
from .notify import (
    PARAM_ALARMMODE,
    PARAM_AUDIOMODE,
    PARAM_BACKGROUND_COLOR,
    PARAM_BACKGROUNDMODE,
    PARAM_BRIGHTNESS,
    PARAM_CALENDAR,
    PARAM_CLOCK,
    PARAM_COLOR,
    PARAM_COUNTDOWN,
    PARAM_FILE,
    PARAM_FONT,
    PARAM_FOREGROUND_COLOR,
    PARAM_FREQUENCY,
    PARAM_HOT,
    PARAM_NUMBER,
    PARAM_PLAYER1,
    PARAM_PLAYER2,
    PARAM_RAW,
    PARAM_SIZE,
    PARAM_SLEEPMODE,
    PARAM_STREAMMODE,
    PARAM_TEMP,
    PARAM_TEXT,
    PARAM_TIME,
    PARAM_TRIGGERMODE,
    PARAM_TWENTYFOUR,
    PARAM_UNIT,
    PARAM_VALUE,
    PARAM_VOLUME,
    PARAM_WEATHER,
    PARAM_WEEKDAY,
    WEATHER_MODES,
)

_LOGGER = logging.getLogger(__package__)

TARGET_SCHEMA = {
    vol.Required(CONF_ENTRY_ID): cv.string,
}

RGB = vol.All(
    [vol.All(vol.Coerce(int), vol.Range(min=0, max=255))], vol.Length(min=3, max=3)
)

PERCENT = vol.All(vol.Coerce(int), vol.Range(min=0, max=100))

# the upper bounds are what the protocol packs the value into, not how many
# styles/effects/designs a concrete device offers
BYTE = vol.All(vol.Coerce(int), vol.Range(min=0, max=255))
WORD = vol.All(vol.Coerce(int), vol.Range(min=0, max=65535))

# beyond 15 show_clock deactivates the clock instead of picking a style
CLOCK = vol.All(vol.Coerce(int), vol.Range(min=0, max=15))

# the FM broadcast bands in use worldwide, from OIRT up to ITU
FREQUENCY = vol.All(vol.Coerce(float), vol.Range(min=64, max=108))

KEYBOARD_VALUES = ["previous", "toggle", "next"]
GAMECONTROL_VALUES = ["go", "left", "right", "up", "down", "ok"]
TEMPERATURE_UNITS = ["°C", "°F"]

# a plain number from the UI, or the combined "25°C" the README documents
TEMPERATURE = vol.Any(
    vol.Coerce(float),
    vol.All(cv.string, vol.Match(r"^\s*-?\d+([.,]\d+)?\s*°?\s*[CF]\s*$", re.IGNORECASE)),
)

SERVICE_SCHEMAS = {
    "clock": vol.Schema({
        **TARGET_SCHEMA,
        vol.Optional(PARAM_CLOCK): CLOCK,
        vol.Optional(PARAM_TWENTYFOUR): cv.boolean,
        vol.Optional(PARAM_WEATHER): cv.boolean,
        vol.Optional(PARAM_TEMP): cv.boolean,
        vol.Optional(PARAM_CALENDAR): cv.boolean,
        vol.Optional(PARAM_COLOR): RGB,
        vol.Optional(PARAM_HOT): cv.boolean,
    }),
    "light": vol.Schema({
        **TARGET_SCHEMA,
        vol.Optional(PARAM_BRIGHTNESS): PERCENT,
        vol.Optional(PARAM_COLOR): RGB,
    }),
    "on": vol.Schema({
        **TARGET_SCHEMA,
    }),
    "off": vol.Schema({
        **TARGET_SCHEMA,
    }),
    "brightness": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_BRIGHTNESS): PERCENT,
    }),
    "image": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_FILE): cv.string,
        vol.Optional(PARAM_TIME): WORD,
    }),
    "text": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_TEXT): cv.string,
        vol.Optional(PARAM_FONT): cv.string,
        # the font size goes to PIL, not into a byte, so there is nothing to cap
        vol.Optional(PARAM_SIZE): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional(PARAM_TIME): WORD,
        vol.Optional(PARAM_FOREGROUND_COLOR): RGB,
        vol.Optional(PARAM_BACKGROUND_COLOR): RGB,
    }),
    "design": vol.Schema({
        **TARGET_SCHEMA,
        vol.Optional(PARAM_NUMBER): BYTE,
    }),
    "effects": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_NUMBER): BYTE,
    }),
    "visualization": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_NUMBER): BYTE,
        vol.Optional(PARAM_FOREGROUND_COLOR): RGB,
        vol.Optional(PARAM_BACKGROUND_COLOR): RGB,
    }),
    "signal": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_NUMBER): BYTE,
    }),
    "alarm": vol.Schema({
        **TARGET_SCHEMA,
        vol.Optional(PARAM_NUMBER): BYTE,
        vol.Optional(PARAM_VALUE): cv.string,
        vol.Optional(PARAM_WEEKDAY): cv.weekdays,
        vol.Optional(PARAM_ALARMMODE): BYTE,
        vol.Optional(PARAM_TRIGGERMODE): BYTE,
        vol.Optional(PARAM_FREQUENCY): FREQUENCY,
        vol.Optional(PARAM_VOLUME): PERCENT,
    }),
    "countdown": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_VALUE): cv.boolean,
        vol.Optional(PARAM_COUNTDOWN): cv.string,
    }),
    "timer": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_VALUE): cv.boolean,
    }),
    "memorial": vol.Schema({
        **TARGET_SCHEMA,
        vol.Optional(PARAM_NUMBER): BYTE,
        vol.Optional(PARAM_VALUE): cv.string,
        vol.Optional(PARAM_TEXT): cv.string,
    }),
    "scoreboard": vol.Schema({
        **TARGET_SCHEMA,
        vol.Optional(PARAM_PLAYER1): WORD,
        vol.Optional(PARAM_PLAYER2): WORD,
    }),
    "noise": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_VALUE): cv.boolean,
    }),
    "sleep": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_VALUE): cv.boolean,
        vol.Optional(PARAM_TIME): BYTE,
        vol.Optional(PARAM_SLEEPMODE): BYTE,
        vol.Optional(PARAM_FREQUENCY): FREQUENCY,
        vol.Optional(PARAM_VOLUME): PERCENT,
        vol.Optional(PARAM_COLOR): RGB,
        vol.Optional(PARAM_BRIGHTNESS): PERCENT,
    }),
    "datetime": vol.Schema({
        **TARGET_SCHEMA,
        vol.Optional(PARAM_VALUE): cv.string,
    }),
    "equalizer": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_NUMBER): BYTE,
        vol.Optional(PARAM_AUDIOMODE): cv.boolean,
        vol.Optional(PARAM_BACKGROUNDMODE): cv.boolean,
        vol.Optional(PARAM_STREAMMODE): cv.boolean,
    }),
    "volume": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_VOLUME): PERCENT,
    }),
    "playstate": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_VALUE): cv.boolean,
    }),
    "radio": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_VALUE): cv.boolean,
        vol.Optional(PARAM_FREQUENCY): FREQUENCY,
    }),
    "lyrics": vol.Schema({
        **TARGET_SCHEMA,
    }),
    "keyboard": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_VALUE): vol.In(KEYBOARD_VALUES),
    }),
    "game": vol.Schema({
        **TARGET_SCHEMA,
        vol.Optional(PARAM_VALUE): BYTE,
    }),
    "gamecontrol": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_VALUE): vol.In(GAMECONTROL_VALUES),
    }),
    "weather": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_VALUE): TEMPERATURE,
        vol.Optional(PARAM_UNIT): vol.In(TEMPERATURE_UNITS),
        vol.Optional(PARAM_WEATHER): vol.Any(vol.In(WEATHER_MODES), BYTE),
    }),
    "temperature": vol.Schema({
        **TARGET_SCHEMA,
        vol.Optional(PARAM_VALUE): vol.In(TEMPERATURE_UNITS),
        vol.Optional(PARAM_COLOR): RGB,
    }),
    "raw": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_RAW): vol.All(cv.ensure_list, vol.Length(min=1)),
    }),
    "connect": vol.Schema({
        **TARGET_SCHEMA,
    }),
    "disconnect": vol.Schema({
        **TARGET_SCHEMA,
    }),
}

def _resolve_target(hass: HomeAssistant, data):
    entry_id = data[CONF_ENTRY_ID]
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"entry_id": entry_id},
        )

    loadedServices = hass.data.get(DOMAIN, {}).get('loaded', {})
    mac = entry.data.get(CONF_MAC)
    if mac not in loadedServices:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"title": entry.title},
        )

    return loadedServices[mac]

def _make_handler(mode: str):
    async def _handle(call: ServiceCall) -> None:
        service = _resolve_target(call.hass, call.data)
        params = {key: value for key, value in call.data.items() if key != CONF_ENTRY_ID}

        try:
            result = await call.hass.async_add_executor_job(service.call_mode, mode, params)
        except DivoomUnsupportedError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="mode_unsupported",
                translation_placeholders={"device": err.device, "mode": mode},
            ) from err

        if not result:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="mode_failed",
                translation_placeholders={"mode": mode},
            )

    return _handle

@callback
def async_setup_services(hass: HomeAssistant) -> None:
    for mode, schema in SERVICE_SCHEMAS.items():
        hass.services.async_register(DOMAIN, mode, _make_handler(mode), schema=schema)

    _LOGGER.debug("Divoom: successfully registered {} services".format(len(SERVICE_SCHEMAS)))
