"""Provides class Aurabox that encapsulates the Aurabox Bluetooth communication."""

from .divoom import Divoom

class Aurabox(Divoom):
    """Class Aurabox encapsulates the Aurabox Bluetooth communication."""
    def __init__(self, host=None, mac=None, port=1, escapePayload=False, logger=None):
        self.type = "Aurabox"
        self.size = 10
        Divoom.__init__(self, host, mac, port, escapePayload, logger)
        
    def show_scoreboard(self, blue=None, red=None):
        """Show scoreboard on the Divoom device with specific score"""
        if blue == None: blue = 0
        if isinstance(blue, str): blue = int(blue)
        if red == None: red = 0
        if isinstance(red, str): red = int(red)

        args = [0x06, 0x00]
        args += red.to_bytes(2, byteorder='little')
        args += blue.to_bytes(2, byteorder='little')
        return self.send_command("set view", args)

    def show_lyrics(self):
        self.logger.warning("{0}: this device does not support lyrics view.".format(self.type))

    def send_keyboard(self, value=None):
        self.logger.warning("{0}: this device does not support changing the keyboard light.".format(self.type))
