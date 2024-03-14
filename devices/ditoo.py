"""Provides class Ditoo that encapsulates the Ditoo Bluetooth communication."""

from .divoom import Divoom

class Ditoo(Divoom):
    """Class Ditoo encapsulates the Ditoo Bluetooth communication."""
    def __init__(self, host=None, port=1, escapePayload=False, logger=None):
        self.type = "Ditoo"
        self.size = 16
        Divoom.__init__(self, host, port, escapePayload, logger)
        
    def show_scoreboard(self, blue=None, red=None):
        """Show scoreboard on the Divoom device with specific score"""
        if blue == None: blue = 0
        if isinstance(blue, str): blue = int(blue)
        if red == None: red = 0
        if isinstance(red, str): red = int(red)

        args = [0x01, 0x01]
        args += red.to_bytes(2, byteorder='little')
        args += blue.to_bytes(2, byteorder='little')
        self.send_command("set tool", args)

    def show_lyrics(self):
        """Show lyrics on the Divoom device with specific score"""

        args = [0x06, 0x00, 0x00, 0x00]
        self.send_command("set view", args)
