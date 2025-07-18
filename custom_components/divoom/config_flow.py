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

from homeassistant.helpers.service_info.zeroconf import (
    ZeroconfServiceInfo,
)

from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from homeassistant.const import CONF_NAME, CONF_HOST, CONF_MAC, CONF_PORT
from .const import CONF_DEVICE_TYPE, CONF_MEDIA_DIR, CONF_MEDIA_DIR_DEFAULT, CONF_ESCAPE_PAYLOAD, DOMAIN  # pylint:disable=unused-import

_LOGGER = logging.getLogger(__package__)

@config_entries.HANDLERS.register(DOMAIN)
class DivoomBluetoothConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Divoom Bluetooth config flow."""
    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._discovered_devices: dict[str, BluetoothServiceInfo] = {}
        self._device_host = None
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

                device_name = discovery_info.name.lower()
                if "aurabox" in device_name or "timebox" in device_name or "ditoo" in device_name or "pixoo" in device_name or "timoo" in device_name or "tivoo" in device_name or "divoom" in device_name:
                    self._discovered_devices[discovery_info.address] = discovery_info

            discovered_titles = [
                SelectOptionDict(value=address, label="{} ({})".format(discovery.name, discovery.address))
                for (address, discovery) in self._discovered_devices.items()
            ]
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_MAC): SelectSelector(
                            SelectSelectorConfig(
                                mode=SelectSelectorMode.DROPDOWN,
                                options=discovered_titles,
                                custom_value=True,
                                multiple=False,
                                sort=True,
                            ),
                        ),
                        vol.Optional(CONF_PORT, default=1): cv.port,
                        vol.Optional(CONF_HOST, default=""): cv.string
                    }
                ),
            )
        
        if CONF_HOST in user_input and user_input[CONF_HOST] != "":
            self._device_host = user_input[CONF_HOST]

        if CONF_MAC in user_input:
            if user_input[CONF_MAC] in self._discovered_devices:
                self._device_name = self._discovered_devices[user_input[CONF_MAC]].name
            else:
                self._device_name = "Device"
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

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle a flow initialized by zeroconf discovery."""

        self._device_host = discovery_info.host
        self._device_mac = discovery_info.properties.get("device_mac")
        self._device_name = discovery_info.properties.get("device_name")

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

        device_port = 1
        device_name = self._device_name.lower()
        if device_name.startswith("aurabox"):
            device_port = 4
        elif device_name.startswith("ditoomic") or device_name.startswith("ditoo-mic") or device_name.startswith("ditoo mic"):
            device_port = 2
        elif device_name.startswith("ditoo") or device_name.startswith("divoom-ditoo") or device_name.startswith("divoom ditoo"):
            device_port = 2
        elif device_name.startswith("timeboxmini") or device_name.startswith("timebox-mini") or device_name.startswith("timebox mini"):
            device_port = 4
        elif device_name.startswith("timoo"):
            device_port = 2

        return self.async_show_form(
            step_id="device_port",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PORT, default=device_port): cv.port
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

        device_type = None
        device_name = self._device_name.lower()
        if device_name.startswith("aurabox"):
            device_type = "aurabox"
        elif device_name.startswith("pixoo-backpack") or device_name.startswith("pixoo-slingbag") or device_name.startswith("divoom-backpack"):
            device_type = "backpack"
        elif device_name.startswith("ditoomic") or device_name.startswith("ditoo-mic") or device_name.startswith("ditoo mic"):
            device_type = "ditoomic"
        elif device_name.startswith("ditoo") or device_name.startswith("divoom-ditoo") or device_name.startswith("divoom ditoo"):
            device_type = "ditoo"
        elif device_name.startswith("pixoomax") or device_name.startswith("pixoo-max") or device_name.startswith("pixoo max"):
            device_type = "pixoomax"
        elif device_name.startswith("pixoo"):
            device_type = "pixoo"
        elif device_name.startswith("timeboxmini") or device_name.startswith("timebox-mini") or device_name.startswith("timebox mini"):
            device_type = "timeboxmini"
        elif device_name.startswith("timebox"):
            device_type = "timebox"
        elif device_name.startswith("timoo"):
            device_type = "timoo"
        elif device_name.startswith("tivoo"):
            device_type = "tivoo"
        self._device_type = device_type

        device_types = [
            SelectOptionDict(value="aurabox", label="Aurabox"),
            SelectOptionDict(value="backpack", label="Backpack"),
            SelectOptionDict(value="ditoo", label="Ditoo"),
            SelectOptionDict(value="ditoomic", label="Ditoo Mic"),
            SelectOptionDict(value="pixoo", label="Pixoo"),
            SelectOptionDict(value="pixoomax", label="Pixoo Max"),
            SelectOptionDict(value="timebox", label="Timebox"),
            SelectOptionDict(value="timeboxmini", label="Timebox Mini"),
            SelectOptionDict(value="timoo", label="Timoo"),
            SelectOptionDict(value="tivoo", label="Tivoo"),
        ]
        return self.async_show_form(
            step_id="device_type",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_TYPE, default=device_type): SelectSelector(
                        SelectSelectorConfig(
                            mode=SelectSelectorMode.LIST,
                            options=device_types,
                            custom_value=False,
                            multiple=False,
                            sort=True,
                        ),
                    ),
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
                    CONF_HOST: self._device_host,
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
