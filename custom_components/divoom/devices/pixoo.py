"""Provides class Pixoo that encapsulates the Pixoo Bluetooth communication."""

from .divoom import Divoom

class Pixoo(Divoom):
    """Class Pixoo encapsulates the Pixoo Bluetooth communication."""
    def __init__(self, host=None, mac=None, port=1, escapePayload=False, logger=None):
        self.type = "Pixoo"
        self.size = 16
        Divoom.__init__(self, host, mac, port, escapePayload, logger)
        
    def send_volume(self, value=None):
        self.logger.warning("{0}: this device does not support sending the volume.".format(self.type))

    def send_playstate(self, value=None):
        self.logger.warning("{0}: this device does not support sending the play/pause state.".format(self.type))

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

    def show_alarm(self, number=None, time=None, weekdays=None, alarmMode=None, triggerMode=None, frequency=None, volume=None):
        Divoom.show_alarm(self, number=number, time=time, weekdays=weekdays, alarmMode=0, triggerMode=0, frequency=0, volume=1)

    def show_radio(self, value=None, frequency=None):
        self.logger.warning("{0}: this device does not support showing the radio.".format(self.type))

    def send_keyboard(self, value=None):
        self.logger.warning("{0}: this device does not support changing the keyboard light.".format(self.type))
