"""The divoom component."""
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType

from homeassistant.const import Platform
from .const import DOMAIN, PLATFORMS  # pylint:disable=unused-import

_LOGGER = logging.getLogger(__package__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Divoom from a config."""

    hass.data.setdefault(DOMAIN, {})

    _LOGGER.debug("Divoom: successfully setup a config")
    return True

async def async_setup_entry(hass: HomeAssistant, config: ConfigEntry) -> bool:
    """Set the config entry up."""

    for platform in PLATFORMS:
        hass.async_create_task(async_load_platform(hass, platform, DOMAIN, {}, config))
    
    await hass.config_entries.async_forward_entry_setups(
        config, [platform for platform in PLATFORMS if platform != Platform.NOTIFY]
    )
    
    _LOGGER.debug("Divoom: successfully setup a config entry")
    return True

async def async_unload_entry(hass: HomeAssistant, config: ConfigEntry) -> bool:
    """Unload a config entry."""
    
    _LOGGER.debug("Divoom: unloading a config entry")
    return await hass.config_entries.async_unload_platforms(config, PLATFORMS)
