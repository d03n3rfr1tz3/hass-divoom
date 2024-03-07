"""Provides class Timebox that encapsulates the Timebox Bluetooth communication."""

from .divoom import Divoom

class Timebox(Divoom):
    """Class Timebox encapsulates the Timebox Bluetooth communication."""
    def __init__(self, host=None, port=1, logger=None):
        self.type = "Timebox"
        self.size = 16
        Divoom.__init__(self, host, port, logger)
        
    def show_radio(self, value=None):
        self.logger.warning("{0}: this device does not support showing the radio.".format(self.type))
