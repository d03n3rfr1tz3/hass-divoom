"""Provides class Pixoo64 that encapsulates the Pixoo 64 Bluetooth communication."""

from .divoom import Divoom

class Pixoo64(Divoom):
    """Class Pixoo64 encapsulates the Pixoo 64 Bluetooth communication."""
    def __init__(self, host=None, port=1, logger=None):
        self.type = "Pixoo64"
        self.size = 64
        Divoom.__init__(self, host, port, logger)