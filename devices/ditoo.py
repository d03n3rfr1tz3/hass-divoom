"""Provides class Ditoo that encapsulates the Ditoo Bluetooth communication."""

from .divoom import Divoom

class Ditoo(Divoom):
    """Class Ditoo encapsulates the Ditoo Bluetooth communication."""
    def __init__(self, host=None, port=1, logger=None):
        self.type = "Ditoo"
        self.size = 16
        Divoom.__init__(self, host, port, logger)