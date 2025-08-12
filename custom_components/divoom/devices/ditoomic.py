"""Provides class DitooMic that encapsulates the DitooMic Bluetooth communication."""

from .divoom import Divoom

class DitooMic(Divoom):
    """Class DitooMic encapsulates the DitooMic Bluetooth communication."""
    def __init__(self, host=None, mac=None, port=1, escapePayload=False, logger=None):
        self.type = "DitooMic"
        self.screensize = 16
        self.chunksize = 200
        self.colorpalette = None
        if escapePayload == None: escapePayload = False
        Divoom.__init__(self, host, mac, port, escapePayload, logger)
        
    def show_equalizer(self, number, audioMode=False, backgroundMode=False, streamMode=False):
        """Show equalizer on the Divoom device"""
        if number == None: return
        if isinstance(number, str): number = int(number)

        args = [0x1E, 0x01]
        args += [0x01 if streamMode else 0x00]
        args += [0x01 if audioMode else 0x00]
        args += [0x01 if backgroundMode else 0x00]
        args += number.to_bytes(1, byteorder='little')
        args += [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00] # some of these might be the landscape, but the app doesnt send them in fake mode
        result = self.send_command("set design", args)
        return result

    def send_keyboard(self, value=None):
        """Send keyboard command on the Divoom device"""
        if value == None: return
        if isinstance(value, str): value = int(value)

        if value == 0: # toggle keyboard
            args = [0x02]
            return self.send_command("set keyboard", args, skipRead=True)
        elif value >= 1: # switch to next keyboard effect
            args = [0x01]
            return self.send_command("set keyboard", args, skipRead=True)
        elif value <= -1: # switch to prev keyboard effect
            args = [0x00]
            return self.send_command("set keyboard", args, skipRead=True)

    def show_lyrics(self):
        """Show lyrics on the Divoom device with specific score"""

        args = [0x06, 0x00, 0x00, 0x00]
        return self.send_command("set view", args)

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
