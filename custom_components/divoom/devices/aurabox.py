"""Provides class Aurabox that encapsulates the Aurabox Bluetooth communication."""

from .divoom import Divoom

class Aurabox(Divoom):
    """Class Aurabox encapsulates the Aurabox Bluetooth communication."""
    def __init__(self, host=None, mac=None, port=1, escapePayload=True, logger=None):
        self.type = "Aurabox"
        self.screensize = 10
        self.chunksize = 182
        self.colorpalette = [
            [  0,   0,   0],
            [255,   0,   0],
            [  0, 255,   0],
            [255, 255,   0],
            [  0,   0, 255],
            [255,   0, 255],
            [  0, 255, 255],
            [255, 255, 255]
        ]
        if escapePayload == None: escapePayload = True
        Divoom.__init__(self, host, mac, port, escapePayload, logger)
        
    def get_color(self, color):
         if color[0] <=   5: color[0] =   0
         if color[1] <=   5: color[1] =   0
         if color[2] <=   5: color[2] =   0
         if color[0] >= 250: color[0] = 255
         if color[1] >= 250: color[1] = 255
         if color[2] >= 250: color[2] = 255
         if color in self.colorpalette:
            return self.colorpalette.index(color)
         return -1

    def make_frame(self, frame):
        length = len(frame)
        return [frame, length]

    def make_framepart(self, lsum, index, framePart):
        header = []
        header += [0x00, 0x0A, 0x0A, 0x04] # Fixed header
        if index >= 0:
            header += index.to_bytes(1, byteorder='little') # Pixoo-Max expects more
        return header + framePart

    def process_frame(self, pixels, colors, colorCount, framesCount, time, needsFlags):
        result = []
        if framesCount > 1:
            result += time.to_bytes(1, byteorder='little')
        for pixelset in self.chunks(pixels, 2):
            color1 = self.get_color(colors[pixelset[0]])
            color2 = self.get_color(colors[pixelset[1]])
            result += [((color1 if color1 >= 0 else 0) << 4) | (color2 if color2 >= 0 else 0)]
        return result

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

        args = [0x01]
        result = self.send_command("set view", args)

        if value is not None:
            if value == False or value == 0:
                self.send_command("set temp unit", [0x00])
            if value == True or value == 1:
                self.send_command("set temp unit", [0x01])

        return result

    def show_light(self, color, brightness=None, power=None):
        """Show light on the Divoom device in the color"""
        if isinstance(brightness, str): brightness = int(brightness)

        if brightness is not None:
            self.send_brightness(brightness)
        
        args = [0x02]
        result = self.send_command("set view", args)

        if color is not None:
            colorIndex = self.get_color(color)
            if colorIndex >= 0:
                self.send_command("set light color", colorIndex.to_bytes(1, byteorder='big'))
            else: self.logger.warning("{0}: this device does not support RGB values. please chose from one of the following colors: {1}".format(self.type, ', '.join(str(x) for x in self.colorpalette)))
        
        return result

    def show_effects(self, number):
        """Show effects on the Divoom device"""
        if number == None: return
        if isinstance(number, str): number = int(number)

        args += (4 + number).to_bytes(1, byteorder='big')
        return self.send_command("set view", args)

    def show_visualization(self, number, color1=None, color2=None):
        """Show visualization on the Divoom device"""

        args = [0x03]
        args += number.to_bytes(1, byteorder='big')
        return self.send_command("set view", args)

    def show_timer(self, value=None):
        self.logger.warning("{0}: this device does not support timer view.".format(self.type))

    def show_scoreboard(self, blue=None, red=None):
        self.logger.warning("{0}: this device does not support scoreboard view.".format(self.type))

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
