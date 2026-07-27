"""Domain services for divoom, one per device mode."""
import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from homeassistant.const import CONF_MAC
from .const import CONF_ENTRY_ID, DOMAIN
from .notify import (
    PARAM_CALENDAR,
    PARAM_CLOCK,
    PARAM_COLOR,
    PARAM_HOT,
    PARAM_TEMP,
    PARAM_TWENTYFOUR,
    PARAM_WEATHER,
)

_LOGGER = logging.getLogger(__package__)

TARGET_SCHEMA = {
    vol.Required(CONF_ENTRY_ID): cv.string,
}

RGB = vol.All(
    [vol.All(vol.Coerce(int), vol.Range(min=0, max=255))], vol.Length(min=3, max=3)
)

SERVICE_SCHEMAS = {
    "clock": vol.Schema({
        **TARGET_SCHEMA,
        vol.Optional(PARAM_CLOCK): vol.All(vol.Coerce(int), vol.Range(min=0, max=15)),
        vol.Optional(PARAM_TWENTYFOUR): cv.boolean,
        vol.Optional(PARAM_WEATHER): cv.boolean,
        vol.Optional(PARAM_TEMP): cv.boolean,
        vol.Optional(PARAM_CALENDAR): cv.boolean,
        vol.Optional(PARAM_COLOR): RGB,
        vol.Optional(PARAM_HOT): cv.boolean,
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

        result = await call.hass.async_add_executor_job(service.call_mode, mode, params)
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
