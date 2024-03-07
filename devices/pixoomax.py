"""Provides class PixooMax that encapsulates the Pixoo Max Bluetooth communication."""

from .divoom import Divoom

class PixooMax(Divoom):
    """Class PixooMax encapsulates the Pixoo Max Bluetooth communication."""
    def __init__(self, host=None, port=1, logger=None):
        self.type = "PixooMax"
        self.size = 32
        Divoom.__init__(self, host, port, logger)