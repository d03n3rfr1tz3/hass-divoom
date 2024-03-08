"""Provides class Pixoo that encapsulates the Pixoo Bluetooth communication."""

from .divoom import Divoom

class Pixoo(Divoom):
    """Class Pixoo encapsulates the Pixoo Bluetooth communication."""
    def __init__(self, host=None, port=1, escapePayload=False, logger=None):
        self.type = "Pixoo"
        self.size = 16
        Divoom.__init__(self, host, port, escapePayload, logger)
        
    def send_volume(self, value=None):
        self.logger.warning("{0}: this device does not support sending the volume.".format(self.type))

    def send_playstate(self, value=None):
        self.logger.warning("{0}: this device does not support sending the play/pause state.".format(self.type))

    def show_countdown(self, value=None, countdown=None):
        self.logger.warning("{0}: this device does not support showing the countdown.".format(self.type))

    def show_noise(self, value=None):
        self.logger.warning("{0}: this device does not support showing the noise meter.".format(self.type))

    def show_timer(self, value=None):
        self.logger.warning("{0}: this device does not support showing the timer.".format(self.type))

    def show_radio(self, value=None, frequency=None):
        self.logger.warning("{0}: this device does not support showing the radio.".format(self.type))

    def send_keyboard(self, value=None):
        self.logger.warning("{0}: this device does not support changing the keyboard light.".format(self.type))
