"""Provides class Tiivoo2 that encapsulates the Divoom Tiivoo 2 Bluetooth communication."""

from .divoom128 import Divoom128

class Tiivoo2(Divoom128):
    """Class Tiivoo2 encapsulates the Divoom Tiivoo 2 Bluetooth communication."""

    def __init__(self, host=None, mac=None, port=1, escapePayload=False, logger=None):
        self.type = "Tiivoo2"
        Divoom128.__init__(self, host, mac, port, escapePayload, logger)
