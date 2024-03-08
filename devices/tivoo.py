"""Provides class Tivoo that encapsulates the Tivoo Bluetooth communication."""

from .divoom import Divoom

class Tivoo(Divoom):
    """Class Tivoo encapsulates the Tivoo Bluetooth communication."""
    def __init__(self, host=None, port=1, escapePayload=False, logger=None):
        self.type = "Tivoo"
        self.size = 16
        Divoom.__init__(self, host, port, escapePayload, logger)
        
    def send_keyboard(self, value=None):
        self.logger.warning("{0}: this device does not support changing the keyboard light.".format(self.type))
