from typing import Final
from homeassistant.const import Platform

PLATFORMS = [Platform.NOTIFY]
DOMAIN: Final = "divoom"

CONF_DEVICE_TYPE: Final = 'device_type'
CONF_MEDIA_DIR: Final = 'media_directory'
CONF_MEDIA_DIR_DEFAULT: Final = "pixelart"
CONF_ESCAPE_PAYLOAD: Final = 'escape_payload'