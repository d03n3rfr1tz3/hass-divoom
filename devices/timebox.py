"""Provides class Timebox that encapsulates the Timebox Bluetooth communication."""

from .divoom import Divoom

class Timebox(Divoom):
    """Class Timebox encapsulates the Timebox Bluetooth communication."""
    def __init__(self, host=None, port=1, escapePayload=False, logger=None):
        self.type = "Timebox"
        self.size = 16
        Divoom.__init__(self, host, port, escapePayload, logger)
        
    def show_countdown(self, value=None, countdown=None):
        self.logger.warning("{0}: this device does not support showing the countdown.".format(self.type))

    def show_noise(self, value=None):
        self.logger.warning("{0}: this device does not support showing the noise meter.".format(self.type))

    def show_timer(self, value=None):
        self.logger.warning("{0}: this device does not support showing the timer.".format(self.type))

    def send_keyboard(self, value=None):
        self.logger.warning("{0}: this device does not support changing the keyboard light.".format(self.type))
