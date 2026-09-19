"""Provides class MiniToo that encapsulates the Divoom MiniToo Bluetooth communication."""

from .divoom128 import Divoom128

class MiniToo(Divoom128):
    """Class MiniToo encapsulates the Divoom MiniToo Bluetooth communication."""

    def __init__(self, host=None, mac=None, port=1, escapePayload=False, logger=None):
        self.type = "MiniToo"
        Divoom128.__init__(self, host, mac, port, escapePayload, logger)
