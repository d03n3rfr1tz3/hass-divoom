"""Provides class Timebox that encapsulates the Timebox Bluetooth communication."""

from .divoom import Divoom

class Timebox(Divoom):
    """Class Timebox encapsulates the Timebox Bluetooth communication."""
    def __init__(self, host=None, mac=None, port=1, escapePayload=False, logger=None):
        self.type = "Timebox"
        self.screensize = 16
        self.chunksize = 200
        self.colorpalette = None
        if escapePayload == None: escapePayload = False
        Divoom.__init__(self, host, mac, port, escapePayload, logger)
        
    def show_scoreboard(self, blue=None, red=None):
        """Show scoreboard on the Divoom device with specific score"""
        if blue == None: blue = 0
        if isinstance(blue, str): blue = int(blue)
        if red == None: red = 0
        if isinstance(red, str): red = int(red)

        args = [0x01, 0x01]
        args += red.to_bytes(2, byteorder='little')
        args += blue.to_bytes(2, byteorder='little')
        return self.send_command("set tool", args)

    def show_lyrics(self):
        """Show lyrics on the Divoom device with specific score"""

        args = [0x06, 0x00, 0x00, 0x00]
        return self.send_command("set view", args)

    def show_equalizer(self, number, audioMode=False, backgroundMode=False, streamMode=False):
        self.logger.warning("{0}: this device does not support the music equalizer mode.".format(self.type))

    def send_keyboard(self, value=None):
        self.logger.warning("{0}: this device does not support changing the keyboard light.".format(self.type))
