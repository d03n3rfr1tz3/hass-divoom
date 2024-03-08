"""Provides class PixooMax that encapsulates the Pixoo Max Bluetooth communication."""

from .divoom import Divoom

class PixooMax(Divoom):
    """Class PixooMax encapsulates the Pixoo Max Bluetooth communication."""
    def __init__(self, host=None, port=1, escapePayload=False, logger=None):
        self.type = "PixooMax"
        self.size = 32
        Divoom.__init__(self, host, port, escapePayload, logger)
        
    def send_volume(self, value=None):
        self.logger.warning("{0}: this device does not support sending the volume.".format(self.type))

    def send_playstate(self, value=None):
        self.logger.warning("{0}: this device does not support sending the play/pause state.".format(self.type))

    def show_radio(self, value=None, frequency=None):
        self.logger.warning("{0}: this device does not support showing the radio.".format(self.type))

    def send_keyboard(self, value=None):
        self.logger.warning("{0}: this device does not support changing the keyboard light.".format(self.type))
