"""Provides class Pixoo that encapsulates the Pixoo Bluetooth communication."""

from .divoom import Divoom

class Pixoo(Divoom):
    """Class Pixoo encapsulates the Pixoo Bluetooth communication."""
    def __init__(self, host=None, port=1, logger=None):
        self.type = "Pixoo"
        self.size = 16
        Divoom.__init__(self, host, port, logger)