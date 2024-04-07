"""Config flow for divoom device integration."""
import logging
import voluptuous as vol

from typing import Any
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from homeassistant.data_entry_flow import AbortFlow, FlowResult

from homeassistant.components.bluetooth import (
    BluetoothServiceInfo,
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)

from homeassistant.const import CONF_NAME, CONF_MAC, CONF_PORT
from .const import CONF_DEVICE_TYPE, CONF_MEDIA_DIR, CONF_MEDIA_DIR_DEFAULT, CONF_ESCAPE_PAYLOAD, DOMAIN  # pylint:disable=unused-import

_LOGGER = logging.getLogger(__package__)

@config_entries.HANDLERS.register(DOMAIN)
class DivoomBluetoothConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Divoom Bluetooth config flow."""
    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._discovered_devices: dict[str, BluetoothServiceInfo] = {}
        self._device_name = None
        self._device_mac = None
        self._device_port = 1
        self._device_type = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""

        if user_input is None or CONF_MAC not in user_input:

            for discovery_info in async_discovered_service_info(self.hass, False):
                if discovery_info.address in self._discovered_devices:
                    continue

                self._discovered_devices[discovery_info.address] = discovery_info

            discovered_titles = {
                address: "{} ({})".format(discovery.name, discovery.address)
                for (address, discovery) in self._discovered_devices.items()
            }
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_MAC): vol.In(discovered_titles),
                        vol.Optional(CONF_PORT, default=1): cv.port
                    }
                ),
            )
        
        if CONF_MAC in user_input:
            self._device_name = self._discovered_devices[user_input[CONF_MAC]].name
            self._device_mac = user_input[CONF_MAC]

        if CONF_PORT in user_input:
            self._device_port = user_input[CONF_PORT]

        await self.async_set_unique_id(self._device_mac)
        await self.async_check_uniqueness()

        self.context["title_placeholders"] = {
            "name": self._device_name,
            "mac": self._device_mac,
        }
        return await self.async_step_device_type()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle a flow initialized by bluetooth discovery."""

        self._device_name = discovery_info.name
        self._device_mac = discovery_info.address

        await self.async_set_unique_id(self._device_mac)
        await self.async_check_uniqueness()

        self.context["title_placeholders"] = {
            "name": self._device_name,
            "mac": self._device_mac,
        }
        return await self.async_step_device_port()

    async def async_step_device_port(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the flow step to choose the Port for the Divoom device."""

        if user_input is not None:
            if CONF_PORT in user_input:
                self._device_port = user_input[CONF_PORT]

            return await self.async_step_device_type()

        return self.async_show_form(
            step_id="device_port",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PORT, default=1): cv.port
                }
            ),
        )
    
    async def async_step_device_type(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the flow step to choose the Port for the Divoom device."""

        if user_input is not None:
            if CONF_DEVICE_TYPE in user_input:
                self._device_type = user_input[CONF_DEVICE_TYPE]

            return await self.async_step_confirm()

        device_type = ""
        if self._device_name.startswith("PixooMax") or self._device_name.startswith("Pixoo Max"):
            device_type = "pixoomax"
        elif self._device_name.startswith("Pixoo"):
            device_type = "pixoo"
        elif self._device_name.startswith("Ditoo"):
            device_type = "ditoo"
        elif self._device_name.startswith("TimeboxMini") or self._device_name.startswith("Timebox Mini"):
            device_type = "timeboxmini"
        elif self._device_name.startswith("Timebox"):
            device_type = "timebox"
        elif self._device_name.startswith("Tivoo"):
            device_type = "tivoo"
        self._device_type = device_type

        device_types = [
            "ditoo",
            "pixoo",
            "pixoomax",
            "timebox",
            "timeboxmini",
            "tivoo"
        ]
        return self.async_show_form(
            step_id="device_type",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_TYPE, default=device_type): vol.In(device_types)
                }
            ),
        )
    
    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the flow step to confirm the Divoom device."""

        if user_input is not None:
            return self.async_create_entry(
                title="Divoom {}".format(self._device_name),
                data={
                    CONF_NAME: "Divoom {}".format(self._device_name),
                    CONF_MAC: self._device_mac,
                    CONF_PORT: self._device_port,
                    CONF_DEVICE_TYPE: self._device_type,
                    CONF_MEDIA_DIR: CONF_MEDIA_DIR_DEFAULT,
                    CONF_ESCAPE_PAYLOAD: False
                },
            )

        return self.async_show_form(
            step_id="confirm",
        )
    
    async def async_check_uniqueness(self) -> bool:
        self._abort_if_unique_id_configured()
        self._async_abort_entries_match({ CONF_MAC: self._device_mac })
        _LOGGER.debug("Divoom: checked uniqueness of {} ({}) successfully via configs from the UI configuration".format(self._device_name, self._device_mac))

        self.hass.data.setdefault(DOMAIN, {})
        domainConfig = self.hass.data.get(DOMAIN)
        domainConfig.setdefault('loaded', {})

        loadedServices = domainConfig.get('loaded')
        if self._device_mac in loadedServices:
            _LOGGER.debug("Divoom: checked uniqueness of {} ({}) unsuccessfully via configs from the configuration.yaml".format(self._device_name, self._device_mac))
            raise AbortFlow("already_configured")

        _LOGGER.debug("Divoom: checked uniqueness of {} ({}) successfully via configs from the configuration.yaml".format(self._device_name, self._device_mac))
