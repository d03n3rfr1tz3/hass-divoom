"""Provides class Pixoo64 that encapsulates the Pixoo 64 Bluetooth communication."""

from .divoom import Divoom

class Pixoo64(Divoom):
    """Class Pixoo64 encapsulates the Pixoo 64 Bluetooth communication."""
    def __init__(self, host=None, port=1, logger=None):
        self.type = "Pixoo64"
        self.size = 64
        Divoom.__init__(self, host, port, logger)
        
    def send_volume(self, value=None):
        self.logger.warning("{0}: this device does not support sending the volume.".format(self.type))

    def send_playstate(self, value=None):
        self.logger.warning("{0}: this device does not support sending the play/pause state.".format(self.type))

    def show_radio(self, value=None):
        self.logger.warning("{0}: this device does not support showing the radio.".format(self.type))
