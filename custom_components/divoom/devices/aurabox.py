"""Provides class Aurabox that encapsulates the Aurabox Bluetooth communication."""

from .divoom import Divoom

class Aurabox(Divoom):
    """Class Aurabox encapsulates the Aurabox Bluetooth communication."""
    def __init__(self, host=None, mac=None, port=1, escapePayload=True, logger=None):
        self.type = "Aurabox"
        self.screensize = 10
        self.chunksize = 182
        self.colorpalette = [
            [000, 000, 000],
            [255, 000, 000],
            [000, 255, 000],
            [255, 255, 000],
            [000, 000, 255],
            [255, 000, 255],
            [000, 255, 255],
            [255, 255, 255]
        ]
        if escapePayload == None: escapePayload = True
        Divoom.__init__(self, host, mac, port, escapePayload, logger)
        
    def get_color(self, color):
         if color in self.colorpalette:
            return self.colorpalette.index(color)
         return 0

    def make_frame(self, frame):
        length = len(frame)
        return [frame, length]

    def process_frame(self, pixels, colors, colorCount, framesCount, time, paletteFlag, needsFlags):
        result = []
        if framesCount > 1:
            result += time.to_bytes(1, byteorder='little')
        for pixelset in self.chunks(pixels, 2):
            color1 = colors[pixelset[0]]
            color2 = colors[pixelset[1]]
            colorIndex1 = self.get_color(color1)
            colorIndex2 = self.get_color(color2)
            result += [(colorIndex1>>4) + (colorIndex2>>4)]
        return result

    def process_pixels(self, pixels, colors):
        result = []
        for pixel in pixels:
            result += colors[pixel]
        return result
    
    def send_on(self):
        self.logger.warning("{0}: this device does not support light view.".format(self.type))
    
    def send_off(self):
        """Sets the display off of the Divoom device"""
        args = [0x02]
        return self.send_command("set view", args)

    def send_brightness(self, value=None):
        """Send brightness to the Divoom device"""
        if value == None: return
        if isinstance(value, str): value = int(value)
        
        args = []
        if value >= 75:
            args += (210).to_bytes(1, byteorder='big')
        elif value >= 25:
            args += (63).to_bytes(1, byteorder='big')
        else:
            args += (0).to_bytes(1, byteorder='big')
        return self.send_command("set lightness", args, skipRead=True)

    def show_clock(self, clock=None, twentyfour=None, weather=None, temp=None, calendar=None, color=None, hot=None):
        """Show clock on the Divoom device in the color"""
        if twentyfour == None: twentyfour = True

        args = [0x00]
        args += [0x01 if twentyfour == True or twentyfour == 1 else 0x00]
        if not color is None:
            args += self.convert_color(color)
        return self.send_command("set view", args)

    def show_temperature(self, value=None, color=None):
        """Show temperature on the Divoom device in the color"""
        if value == None: value = False

        args = [0x01]
        args += [0x01 if value == True or value == 1 else 0x00]
        if not color is None:
            args += self.convert_color(color)
        return self.send_command("set view", args)

    def show_light(self, color, brightness=None, power=None):
        self.logger.warning("{0}: this device does not support light view.".format(self.type))

    def show_timer(self, value=None):
        """Show timer tool on the Divoom device"""
        if value == None: value = 2
        if isinstance(value, str): value = int(value)

        args = [0x06]
        args += value.to_bytes(1, byteorder='big')
        return self.send_command("set view", args)

    def show_scoreboard(self, blue=None, red=None):
        """Show scoreboard on the Divoom device with specific score"""
        if blue == None: blue = 0
        if isinstance(blue, str): blue = int(blue)
        if red == None: red = 0
        if isinstance(red, str): red = int(red)

        args = [0x07]
        args += red.to_bytes(2, byteorder='little')
        args += blue.to_bytes(2, byteorder='little')
        return self.send_command("set view", args)

    def show_lyrics(self):
        self.logger.warning("{0}: this device does not support lyrics view.".format(self.type))

    def show_equalizer(self, number, audioMode=False, backgroundMode=False, streamMode=False):
        self.logger.warning("{0}: this device does not support the music equalizer mode.".format(self.type))

    def show_countdown(self, value=None, countdown=None):
        self.logger.warning("{0}: this device does not support the countdown mode.".format(self.type))

    def show_noise(self, value=None):
        self.logger.warning("{0}: this device does not support the noise mode.".format(self.type))

    def send_keyboard(self, value=None):
        self.logger.warning("{0}: this device does not support changing the keyboard light.".format(self.type))
