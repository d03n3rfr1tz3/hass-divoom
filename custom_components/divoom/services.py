"""Domain services for divoom, one per device mode."""
import logging, os, re
from collections import Counter
import aiohttp
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_set_service_schema
from homeassistant.util import slugify
from homeassistant.util.yaml import load_yaml_dict

from homeassistant.const import CONF_MAC, CONF_NAME
from .const import CONF_DEVICE, CONF_DEVICE_TYPE, DOMAIN
from .devices.divoom import DivoomUnsupportedError
from .notify import (
    PARAM_ALARMMODE,
    PARAM_AUDIOMODE,
    PARAM_BACKGROUND,
    PARAM_BACKGROUND_COLOR,
    PARAM_BACKGROUNDMODE,
    PARAM_BRIGHTNESS,
    PARAM_CALENDAR,
    PARAM_CLOCK,
    PARAM_CLOCK_ID,
    PARAM_COLOR,
    PARAM_COUNTDOWN,
    PARAM_EFFECT,
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
    PARAM_VOLUME1,
    PARAM_VOLUME2,
    PARAM_VOLUME3,
    PARAM_VOLUME4,
    PARAM_VOLUME5,
    PARAM_VOLUME6,
    PARAM_VOLUME7,
    PARAM_VOLUME8,
    PARAM_WEATHER,
    PARAM_WEEKDAY,
    WEATHER_MODES,
)

_LOGGER = logging.getLogger(__package__)

SERVICES_YAML = os.path.join(os.path.dirname(__file__), "services.yaml")

TARGET_SCHEMA = {
    vol.Required(CONF_DEVICE): cv.string,
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

# the clock id the MiniToo picks from, unrelated to the style above
CLOCK_ID = vol.All(vol.Coerce(int), vol.Range(min=0))

# device types that pick clocks by id instead of style
CLOCK_ID_TYPES = {"minitoo"}
CLOCK_CATALOG_URL = "https://app.divoom-gz.com/Channel/{}"
CLOCK_CATEGORIES = ("Normal", "Nature&Weather", "Retro", "Ambient", "Plan", "Music Reactive", "Pixel Art", "HOLIDAYS")
CLOCK_PAGE_SIZE = 30

# device types that take one volume per white noise sound in sleep mode
WHITENOISE_TYPES = {"minitoo"}

# device types that take a text effect and background for lyrics
LYRIC_CONFIG_TYPES = {"minitoo"}
LYRIC_EFFECT = vol.All(vol.Coerce(int), vol.Range(min=0, max=5))
LYRIC_BACKGROUND = vol.All(vol.Coerce(int), vol.Range(min=0, max=20))

# the FM broadcast bands in use worldwide, from OIRT up to ITU
FREQUENCY = vol.All(vol.Coerce(float), vol.Range(min=64, max=108))

KEYBOARD_VALUES = ["previous", "toggle", "next"]
PLAYSTATE_VALUES = ["previous", "pause", "play", "next"]
RADIO_VALUES = ["bluetooth", "fm", "linein", "sdcard", "usb"]
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
        vol.Optional(PARAM_CLOCK_ID): CLOCK_ID,
        vol.Optional(PARAM_TWENTYFOUR): cv.boolean,
        vol.Optional(PARAM_WEATHER): cv.boolean,
        vol.Optional(PARAM_TEMP): cv.boolean,
        vol.Optional(PARAM_CALENDAR): cv.boolean,
        vol.Optional(PARAM_COLOR): RGB,
        vol.Optional(PARAM_HOT): cv.boolean,
    }),
    "light": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_BRIGHTNESS): PERCENT,
        vol.Optional(PARAM_COLOR): RGB,
        vol.Optional(PARAM_EFFECT): BYTE,
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
        vol.Required(PARAM_NUMBER): BYTE,
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
        vol.Optional(PARAM_VOLUME1): PERCENT,
        vol.Optional(PARAM_VOLUME2): PERCENT,
        vol.Optional(PARAM_VOLUME3): PERCENT,
        vol.Optional(PARAM_VOLUME4): PERCENT,
        vol.Optional(PARAM_VOLUME5): PERCENT,
        vol.Optional(PARAM_VOLUME6): PERCENT,
        vol.Optional(PARAM_VOLUME7): PERCENT,
        vol.Optional(PARAM_VOLUME8): PERCENT,
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
        vol.Required(PARAM_VALUE): vol.Any(vol.In(PLAYSTATE_VALUES), cv.boolean),
    }),
    "radio": vol.Schema({
        **TARGET_SCHEMA,
        vol.Required(PARAM_VALUE): vol.Any(vol.In(RADIO_VALUES), cv.boolean),
        vol.Optional(PARAM_FREQUENCY): FREQUENCY,
    }),
    "lyrics": vol.Schema({
        **TARGET_SCHEMA,
        vol.Optional(PARAM_EFFECT): LYRIC_EFFECT,
        vol.Optional(PARAM_BACKGROUND): LYRIC_BACKGROUND,
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
        vol.Required(PARAM_VALUE): vol.In(TEMPERATURE_UNITS),
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

SERVICE_RULES = {
    "clock": cv.has_at_least_one_key(PARAM_CLOCK, PARAM_CLOCK_ID),
}

def device_slug(entry) -> str:
    """The name the device is addressed by, unchanged by renaming the entry."""
    return slugify(entry.data.get(CONF_NAME) or entry.title)

def _find_entry(hass: HomeAssistant, device: str):
    """The entry a device value points at, by name, by slug or by raw id."""
    entry = hass.config_entries.async_get_entry(device)
    if entry is not None and entry.domain == DOMAIN:
        return entry

    slug = slugify(device)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if slug in (device_slug(entry), slugify(entry.title)):
            return entry

    return None

def _resolve_target(hass: HomeAssistant, data):
    device = data[CONF_DEVICE]
    entry = _find_entry(hass, device)
    if entry is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"device": device},
        )

    loadedServices = hass.data.get(DOMAIN, {}).get('loaded', {})
    mac = entry.data.get(CONF_MAC)
    if mac not in loadedServices:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_loaded",
            translation_placeholders={"title": entry.title},
        )

    return loadedServices[mac]

def _make_handler(mode: str):
    async def _handle(call: ServiceCall) -> None:
        service = _resolve_target(call.hass, call.data)
        params = {key: value for key, value in call.data.items() if key != CONF_DEVICE}

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
        if mode in SERVICE_RULES: schema = vol.All(schema, SERVICE_RULES[mode])
        hass.services.async_register(DOMAIN, mode, _make_handler(mode), schema=schema)

    _LOGGER.debug("Divoom: successfully registered {} services".format(len(SERVICE_SCHEMAS)))

def _device_options(hass: HomeAssistant):
    """The configured devices, as the UI dropdown wants them."""
    return [
        {"value": device_slug(entry), "label": entry.title}
        for entry in hass.config_entries.async_entries(DOMAIN)
    ]

def _dropdown(options):
    return {"select": {
        "options": options,
        "mode": "dropdown",
        "custom_value": True,
        "sort": True,
    }}

async def _fetch_clock_options(hass: HomeAssistant):
    """The clocks of the public Divoom catalog, as the UI dropdown wants them."""
    session = async_get_clientsession(hass)

    async def post(command, body=None):
        async with session.post(CLOCK_CATALOG_URL.format(command), json=body, timeout=aiohttp.ClientTimeout(total=10)) as response:
            response.raise_for_status()
            return await response.json(content_type=None)

    labels = {}
    for dial_type in (await post("GetDialType")).get("DialTypeList", []):
        category = dial_type.split("（")[0].strip()
        if category not in CLOCK_CATEGORIES: continue

        for page in range(1, 51):
            dials = (await post("GetDialList", {"DialType": dial_type, "Page": page})).get("DialList", [])
            for dial in dials:
                name = dial["Name"].replace("\\'", "'").strip()
                labels.setdefault(dial["ClockId"], "{} · {}".format(category, name))
            if len(dials) < CLOCK_PAGE_SIZE: break

    counts = Counter(labels.values())
    return [
        {"value": str(clock_id), "label": label if counts[label] == 1 else "{} ({})".format(label, clock_id)}
        for clock_id, label in labels.items()
    ]

async def _load_clock_options(hass: HomeAssistant) -> None:
    domainConfig = hass.data[DOMAIN]
    try:
        clocks = await _fetch_clock_options(hass)
    except Exception as err: # only UI sugar, the number field works without it
        _LOGGER.warning("Divoom: clock catalog unavailable: {}".format(err))
        return
    finally:
        domainConfig.pop('clocks_task', None)

    if clocks:
        domainConfig['clocks'] = clocks
        await async_refresh_service_descriptions(hass)

def _clock_fields(fields, types, clocks):
    """Keep the sections the configured device types understand."""
    fields = dict(fields)
    if not types & CLOCK_ID_TYPES:
        fields.pop("catalog")
    elif clocks:
        catalog = fields["catalog"]
        clock_id = {**catalog["fields"][PARAM_CLOCK_ID], "selector": _dropdown(clocks)}
        fields["catalog"] = {**catalog, "fields": {**catalog["fields"], PARAM_CLOCK_ID: clock_id}}
    if types <= CLOCK_ID_TYPES:
        fields.pop("classic")
    return fields

def _drop_section(fields, section, types, supported):
    """Drop a section none of the configured device types understands."""
    if types & supported: return fields
    return {key: value for key, value in fields.items() if key != section}

async def async_refresh_service_descriptions(hass: HomeAssistant) -> None:
    """Point the device field at the devices that actually exist.

    services.yaml can only describe a static field, so the picker is built here
    instead - it lists the configured devices and writes the same slug a
    handwritten automation would use. The clock, white noise and lyrics sections
    follow the configured device types, and clock_id offers the Divoom catalog
    once it has loaded.
    """
    domainConfig = hass.data.setdefault(DOMAIN, {})
    descriptions = domainConfig.get('descriptions')
    if descriptions is None:
        descriptions = await hass.async_add_executor_job(load_yaml_dict, SERVICES_YAML)
        domainConfig['descriptions'] = descriptions

    entries = hass.config_entries.async_entries(DOMAIN)
    types = {entry.data.get(CONF_DEVICE_TYPE) for entry in entries}
    clocks = domainConfig.get('clocks')
    if types & CLOCK_ID_TYPES and clocks is None and 'clocks_task' not in domainConfig:
        domainConfig['clocks_task'] = hass.async_create_background_task(_load_clock_options(hass), "divoom clock catalog", eager_start=False)

    selector = _dropdown(_device_options(hass))

    for mode, description in descriptions.items():
        fields = description.get("fields", {})
        if entries:
            fields = {**fields, CONF_DEVICE: {**fields[CONF_DEVICE], "selector": selector}}
            if mode == "clock": fields = _clock_fields(fields, types, clocks)
            if mode == "sleep": fields = _drop_section(fields, "whitenoise", types, WHITENOISE_TYPES)
            if mode == "lyrics": fields = _drop_section(fields, "style", types, LYRIC_CONFIG_TYPES)
        async_set_service_schema(hass, DOMAIN, mode, {**description, "fields": fields})
