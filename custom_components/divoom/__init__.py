"""The divoom component."""
import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.components.notify import SERVICE_NOTIFY
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

from homeassistant.const import CONF_NAME, CONF_MAC, CONF_PORT, Platform
from .const import CONF_DEVICE_TYPE, CONF_MEDIA_DIR, CONF_MEDIA_DIR_DEFAULT, CONF_ESCAPE_PAYLOAD, DOMAIN, PLATFORMS  # pylint:disable=unused-import

_LOGGER = logging.getLogger(__package__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_MAC): cv.string,
                vol.Optional(CONF_PORT, default=1): cv.port,
                vol.Required(CONF_DEVICE_TYPE): cv.string,
                vol.Required(CONF_MEDIA_DIR, default=CONF_MEDIA_DIR_DEFAULT): cv.string,
                vol.Optional(CONF_ESCAPE_PAYLOAD, default=False): cv.boolean
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Divoom from a config."""

    hass.data.setdefault(DOMAIN, {})

    _LOGGER.debug("Divoom: successfully setup a config")
    return True

async def async_setup_entry(hass: HomeAssistant, config: ConfigEntry) -> bool:
    """Set the config entry up."""

    mac = config.data[CONF_MAC]
    name = config.data[CONF_NAME]

    for platform in PLATFORMS:
        hass.async_create_task(async_load_platform(hass, platform, DOMAIN, config.data, config.data))

    await hass.config_entries.async_forward_entry_setups(
        config, [platform for platform in PLATFORMS if platform != Platform.NOTIFY]
    )

    _LOGGER.debug("Divoom: successfully setup a config entry for {} ({})".format(name, mac))
    return True

async def async_unload_entry(hass: HomeAssistant, config: ConfigEntry) -> bool:
    """Unload a config entry."""

    mac = config.data[CONF_MAC]
    name = config.data[CONF_NAME]

    hass.data.setdefault(DOMAIN, {})
    domainConfig = hass.data.get(DOMAIN)
    domainConfig.setdefault('loaded', {})

    loadedServices = domainConfig.get('loaded')
    if mac in loadedServices:
        loadedServices[mac].disconnect()
        del loadedServices[mac]

    hass.services.async_remove(SERVICE_NOTIFY, slugify(name))
    await hass.config_entries.async_unload_platforms(
        config, [platform for platform in PLATFORMS if platform != Platform.NOTIFY]
    )

    _LOGGER.debug("Divoom: successfully unloaded a config entry for {} ({})".format(name, mac))
    return True
