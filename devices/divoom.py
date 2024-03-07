"""Provides class Divoom that encapsulates the Divoom Bluetooth communication."""

import logging, math, itertools, select, socket, time, datetime
from PIL import Image

class Divoom:
    """Class Divoom encapsulates the Divoom Bluetooth communication."""
    
    COMMANDS = {
        "set date time": 0x18,
        "set temp type": 0x2b,
        "set time type": 0x2c,
        "set image": 0x44,
        "set view": 0x45,
        "get view": 0x46,
        "set animation frame": 0x49,
        "set temp": 0x5f,
        "set brightness": 0x74
    }

    logger = None
    socket = None
    socket_errno = 0
    message_buf = []
    
    host = None
    port = 1

    def __init__(self, host=None, port=1, logger=None):
        self.host = host
        self.port = port
        
        if logger is None:
            logger = logging.getLogger(self.type)
        self.logger = logger

    def __exit__(self, type, value, traceback):
        self.close()

    def connect(self):
        """Open a connection to the Divoom device."""
        self.socket = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        
        try:
            self.socket.connect((self.host, self.port))
            self.socket.setblocking(0)
            self.socket_errno = 0
        except socket.error as error:
            self.socket_errno = error.errno

    def close(self):
        """Closes the connection to the Divoom device."""
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except:
            pass
        self.socket.close()
        self.socket = None

    def reconnect(self):
        """Reconnects the connection to the Divoom device, if needed."""
        try:
            self.send_ping()
        except socket.error as error:
            self.socket_errno = error.errno
        
        retries = 1
        while self.socket_errno > 0 and retries <= 5:
            self.logger.warning("{0}: connection lost (errno = {1}). Trying to reconnect for the {2} time.".format(self.type, self.socket_errno, retries))
            if retries > 1:
                time.sleep(1 * retries)
            if not self.socket is None:
                self.close()
            self.connect()
            retries += 1

    def receive(self, num_bytes=1024):
        """Receive n bytes of data from the Divoom device and put it in the input buffer. Returns the number of bytes received."""
        ready = select.select([self.socket], [], [], 0.1)
        if ready[0]:
            data = self.socket.recv(num_bytes)
            self.message_buf += data
            return len(data)
        else:
            return 0

    def send_raw(self, data):
        """Send raw data to the Divoom device."""
        try:
            return self.socket.send(data)
        except socket.error as error:
            self.socket_errno = error.errno
            raise

    def send_payload(self, payload):
        """Send raw payload to the Divoom device. (Will be escaped, checksumed and messaged between 0x01 and 0x02."""
        msg = self.make_message(payload)
        try:
            self.logger.debug("{0} PAYLOAD: {1}".format(self.type, ' '.join([hex(b) for b in msg])))
            return self.socket.send(bytes(msg))
        except socket.error as error:
            self.socket_errno = error.errno
            raise

    def send_command(self, command, args=None):
        """Send command with optional arguments"""
        if args is None:
            args = []
        if isinstance(command, str):
            command = self.COMMANDS[command]
        length = len(args)+3
        payload = []
        payload += length.to_bytes(2, byteorder='little')
        payload += [command]
        payload += args
        self.send_payload(payload)

    def drop_message_buffer(self):
        """Drop all dat currently in the message buffer,"""
        self.message_buf = []
    
    def checksum(self, payload):
        """Compute the payload checksum. Returned as list with LSM, MSB"""
        length = sum(payload)
        csum = []
        csum += length.to_bytes(2, byteorder='little')
        return csum

    def chunks(self, lst, n):
        """Yield successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    def escape_payload(self, payload):
        """Escaping is not needed anymore as some smarter guys found out"""
        if self.type == "Pixoo" or self.type == "PixooMax" or self.type == "Pixoo64":
            return payload
        
        """Escape the payload. It is not allowed to have occurrences of the codes
        0x01, 0x02 and 0x03. They must be escaped by a leading 0x03 followed by 0x04,
        0x05 or 0x06 respectively"""
        escpayload = []
        for payload_data in payload:
            escpayload += \
                [0x03, payload_data + 0x03] if payload_data in range(0x01, 0x04) else [payload_data]
        return escpayload

    def make_message(self, payload):
        """Make a complete message from the payload data. Add leading 0x01 and
        trailing check sum and 0x02 and escape the payload"""
        cs_payload = payload + self.checksum(payload)
        escaped_payload = self.escape_payload(cs_payload)
        return [0x01] + escaped_payload + [0x02]

    def convert_color(self, color):
        return color[0].to_bytes(1, byteorder='big') + color[1].to_bytes(1, byteorder='big') + color[2].to_bytes(1, byteorder='big')

    def make_frame(self, frame):
        length = len(frame)+3
        header = [0xAA]
        header += length.to_bytes(2, byteorder='little')
        return [header + frame, length]

    def make_framepart(self, lsum, index, framePart):
        header = []
        header += lsum.to_bytes(2, byteorder='little')
        header += [index]
        return header + framePart

    def process_image(self, image):
        frames = []
        with Image.open(image) as img:
            
            picture_frames = []
            palette = img.getpalette()
            try:
                while True:
                    try:
                        if img.mode in ("L", "LA", "P", "PA") and not img.getpalette():
                            img.putpalette(palette)
                    except ValueError as error:
                        self.logger.warning("{0}: error while trying to put palette into GIF frames. {1}".format(self.type, error))

                    duration = img.info['duration']
                    new_frame = Image.new('RGBA', img.size)
                    new_frame.paste(img, (0, 0), img.convert('RGBA'))
                    picture_frames.append([new_frame, duration])

                    img.seek(img.tell() + 1)
            except EOFError:
                pass
            
            for pair in picture_frames:
                picture_frame = pair[0]
                time = pair[1]
                
                colors = []
                pixels = [None]*self.size*self.size
                
                if time is None:
                    time = 0
                
                for pos in itertools.product(range(self.size), range(self.size)):
                    y, x = pos
                    r, g, b, a = picture_frame.getpixel((x, y))
                    if [r, g, b] not in colors:
                        colors.append([r, g, b])
                    color_index = colors.index([r, g, b])
                    pixels[x + self.size * y] = color_index
                
                colorCount = len(colors)
                if colorCount >= 256:
                    colorCount = 0
                
                timeCode = [0x00, 0x00]
                if len(picture_frames) > 1:
                    timeCode = time.to_bytes(2, byteorder='little')
                
                frame = []
                frame += timeCode
                frame += [0x00]
                frame += colorCount.to_bytes(1, byteorder='big')
                for color in colors:
                    frame += self.convert_color(color)
                frame += self.process_pixels(pixels, colors)
                frames.append(frame)
        
        result = []
        for frame in frames:
            result.append(self.make_frame(frame))
        
        return result

    def process_pixels(self, pixels, colors):
        """Correctly transform each pixel information based on https://github.com/RomRider/node-divoom-timebox-evo/blob/master/PROTOCOL.md#pixel-string-pixel_data """
        bitsPerPixel = math.ceil(math.log(len(colors)) / math.log(2))
        if bitsPerPixel == 0:
            bitsPerPixel = 1
        
        pixelString = ""
        for pixel in pixels:
            pixelBits = "{0:b}".format(pixel).zfill(8)
            pixelString += pixelBits[::-1][:bitsPerPixel:]
        
        chunkSize = 8
        pixelChunks = []
        for i in range(0, len(pixelString), chunkSize):
            pixelChunks += [pixelString[i:i+chunkSize]]
        
        result = []
        for pixel in pixelChunks:
            result += [int(pixel[::-1], 2)]
        
        return result

    def send_ping(self):
        """Send a ping (actually it's requesting current view) to the Divoom device to check connectivity"""
        self.send_command("get view")

    def send_brightness(self, value=None):
        """Send brightness to the Divoom device"""
        if value == None: return
        
        args = []
        args += value.to_bytes(1, byteorder='big')
        self.send_command("set brightness", args)

    def send_weather(self, value=None, weather=None):
        """Send weather to the Divoom device"""
        if value == None: return
        if weather == None: weather = 0

        args = []
        args += int(round(float(value[0:-2]))).to_bytes(1, byteorder='big', signed=True)
        args += weather.to_bytes(1, byteorder='big')
        self.send_command("set temp", args)

        if value[-2] == "°C":
            self.send_command("set temp type", [0x00])
        if value[-2] == "°F":
            self.send_command("set temp type", [0x01])

    def send_datetime(self, value=None):
        """Send date and time information to the Divoom device"""
        if value == None:
            clock = datetime.datetime.now()
        else:
            clock = datetime.datetime.fromisoformat(value)

        args = []
        args += int(clock.year % 100).to_bytes(1, byteorder='big')
        args += int(clock.year / 100).to_bytes(1, byteorder='big')
        args += clock.month.to_bytes(1, byteorder='big')
        args += clock.day.to_bytes(1, byteorder='big')
        args += clock.hour.to_bytes(1, byteorder='big')
        args += clock.minute.to_bytes(1, byteorder='big')
        args += clock.second.to_bytes(1, byteorder='big')
        self.send_command("set date time", args)

    def show_clock(self, clock=None, weather=None, temp=None, calendar=None, color=None):
        """Show clock on the Divoom device in the color"""
        if clock == None: clock = 0
        if weather == None: weather = 0
        if temp == None: temp = 0
        if calendar == None: calendar = 0

        args = [0x00, 0x01]
        if clock >= 0 and clock <= 9:
            args += clock.to_bytes(1, byteorder='big') # clock mode/style
            args += [0x01] # clock activated
        else:
            args += [0x00, 0x00] # clock mode/style = 0 and clock deactivated
        args += weather.to_bytes(1, byteorder='big')
        args += temp.to_bytes(1, byteorder='big')
        args += calendar.to_bytes(1, byteorder='big')
        if not color is None:
            args += self.convert_color(color)
        self.send_command("set view", args)

    def show_light(self, color, brightness=None, power=None):
        """Show light on the Divoom device in the color"""
        if brightness == None: brightness = 100
        if power == None: power = 1

        args = [0x01]
        if color is None:
            args += [0xFF, 0xFF, 0xFF]
            args += brightness.to_bytes(1, byteorder='big')
            args += [0x01]
        else:
            args += self.convert_color(color)
            args += brightness.to_bytes(1, byteorder='big')
            args += [0x00]
        args += [0x01 if power == True else 0x00, 0x00, 0x00, 0x00]
        self.send_command("set view", args)

    def show_effects(self, number):
        """Show effects on the Divoom device"""
        if number == None: return

        args = [0x03]
        args += number.to_bytes(1, byteorder='big')
        self.send_command("set view", args)

    def show_visualization(self, number):
        """Show visualization on the Divoom device"""
        if number == None: return

        args = [0x04]
        args += number.to_bytes(1, byteorder='big')
        self.send_command("set view", args)

    def show_design(self):
        """Show design on the Divoom device"""
        args = [0x05]
        self.send_command("set view", args)

    def show_scoreboard(self, blue=None, red=None):
        """Show scoreboard on the Divoom device with specific score"""
        if blue == None: blue = 0
        if red == None: red = 0

        args = [0x06, 0x00]
        args += red.to_bytes(2, byteorder='little')
        args += blue.to_bytes(2, byteorder='little')
        self.send_command("set view", args)

    def show_image(self, file):
        """Show image or animation on the Divoom device"""
        frames = self.process_image(file)
        framesCount = len(frames)
        
        if framesCount > 1:
            """Sending as Animation"""
            frameParts = []
            framePartsSize = 0
            
            for pair in frames:
                frameParts += pair[0]
                framePartsSize += pair[1]
            
            index = 0
            for framePart in self.chunks(frameParts, 200):
                frame = self.make_framepart(framePartsSize, index, framePart)
                self.send_command("set animation frame", frame)
                index += 1
        
        elif framesCount == 1:
            """Sending as Image"""
            pair = frames[0]
            frame = [0x00, 0x0A, 0x0A, 0x04] + pair[0]
            self.send_command("set image", frame)

    def clear_input_buffer(self):
        """Read all input from Divoom device and remove from buffer. """
        while self.receive() > 0:
            self.drop_message_buffer()

    def clear_input_buffer_quick(self):
        """Quickly read most input from Divoom device and remove from buffer. """
        while self.receive(512) == 512:
            self.drop_message_buffer()
