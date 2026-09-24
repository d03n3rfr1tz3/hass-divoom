"""Provides class Divoom128 that encapsulates the 128x128 LCD Bluetooth communication.

Media goes out via the 0x8b command as Zstandard-compressed RGB888 frames, split
into a start packet and 256-byte chunks that stream once the device asks for
them. All other commands share the base protocol.

Protocol reverse-engineered by https://github.com/alvinunreal/divoom-minitoo-osx
"""

import datetime, json, time
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .divoom import Divoom

MEDIA_MAX_BYTES = 307200 # largest compressed payload the protocol carries


class Divoom128(Divoom):
    """Class Divoom128 encapsulates the 128x128 LCD Bluetooth communication."""

    maxframes = 92 # frame limit of the app editor
    senddelay = 0.015
    MEDIA_WINDOW_LOG = 17
    REQUEST_MARK = b"\x04\x8b\x55"

    def __init__(self, adapter=None, host=None, mac=None, port=1, escapePayload=False, logger=None):
        self.screensize = 128
        self.chunksize = 256
        self.resendwindow = 1.0 if host else 0.5
        self.colorpalette = None
        if escapePayload == None: escapePayload = False
        Divoom.__init__(self, adapter, host, mac, port, escapePayload, logger)

    # --- internals -------------------------------------------------------

    def _await_request(self, timeout=2.0):
        """Wait for the device to ask for the animation after the start packet.
        Chunks streamed before it asks are dropped."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.receive()
            if self._take_request() is not None:
                return True # keep the rest of the buffer for _serve_resends
        self.drop_message_buffer()
        return False

    def _build_packets(self, payload):
        """Command bodies for a media payload: start packet, then chunk packets."""
        total = len(payload).to_bytes(4, "little")
        packets = [b"\x00" + total]  # start
        for seq, off in enumerate(range(0, len(payload), self.chunksize)):
            chunk = payload[off:off + self.chunksize]
            packets.append(b"\x01" + total + seq.to_bytes(2, "little") + chunk)
        return packets

    def _encode_media(self, images, speed):
        """Encode RGB frames into a media payload.

        Layout:
          25 <frame_count_u8> <speed_ms_be16> <row_blocks_u8> <col_blocks_u8>
          <zstd_len_be32> <zstd_frame>
        Pixels are the concatenated frames as _pixels encodes them, zstd level 20.
        """
        import zstandard as zstd  # only these devices need it; keep it out of base import

        if not images: raise ValueError("at least one frame is required")
        blocks = self.screensize // 16

        compressor = zstd.ZstdCompressor(
            compression_params=zstd.ZstdCompressionParameters.from_level(
                20, window_log=self.MEDIA_WINDOW_LOG, write_content_size=True))

        # Thin the animation out evenly until it fits, stretching speed by the
        # same factor to keep the cycle length. A single frame always fits.
        count = len(images)
        keep = min(count, self.maxframes)
        pixels = {} # quantize each frame once across thinning rounds
        while True:
            picked = self.pick_frames(count, keep)
            for i in picked:
                if i not in pixels: pixels[i] = self._pixels(self._quantize(images[i]))
            zbytes = compressor.compress(b"".join(pixels[i] for i in picked))
            if len(zbytes) <= MEDIA_MAX_BYTES or keep == 1: break
            keep = max(1, min(keep - 1, keep * MEDIA_MAX_BYTES // len(zbytes)))
        if keep < count:
            speed = max(1, min(0xffff, round(speed * count / keep)))
            self.logger.warning("{0}: animation has {1} frames, keeping {2}".format(self.type, count, keep))

        header = bytes([0x25, len(picked)]) + speed.to_bytes(2, "big") \
            + bytes([blocks, blocks]) + len(zbytes).to_bytes(4, "big")
        return header + zbytes

    def _fit(self, img):
        """EXIF-transpose, flatten onto black, center-crop square, resize to the
        128x128 grid. Sizes dividing 128 scale with NEAREST to keep pixel art sharp."""
        img = ImageOps.exif_transpose(img).convert("RGBA")
        img = Image.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, 255)), img).convert("RGB")
        side = min(img.size)
        left = (img.width - side) // 2
        top = (img.height - side) // 2
        resample = Image.Resampling.NEAREST if self.screensize % side == 0 else Image.Resampling.LANCZOS
        return img.crop((left, top, left + side, top + side)).resize(
            (self.screensize, self.screensize), resample)

    def _pixels(self, img):
        """Wire bytes of one quantized frame."""
        return img.tobytes("raw", "RGB")

    def _quantize(self, img):
        """Reduce to at most 255 colors before compressing. Dithering is off on
        purpose: it would add noise and grow the zstd stream."""
        return img.quantize(colors=255, dither=Image.Dither.NONE).convert("RGB")

    def _send_packets(self, packets):
        """Send the start packet, wait for the device to request the animation,
        then stream the chunks. The device may ask for single chunks again while
        streaming and shortly after, so keep listening instead of draining."""
        self.drop_message_buffer()
        result = self.send_command("set gif", packets[0], skipRead=True)
        if not self._await_request():
            self.logger.warning("{0}: no request for the animation, sending anyway".format(self.type))
        budget = len(packets) # cap resends; a chatty device must not loop forever
        for packet in packets[1:]:
            result = self.send_command("set gif", packet, skipRead=True)
            self.receive(timeout=0)
            budget = self._serve_resends(packets, budget)
        deadline = time.time() + self.resendwindow
        while budget > 0 and time.time() < deadline:
            if self.receive(timeout=0.05) > 0:
                budget = self._serve_resends(packets, budget)
        self.drop_message_buffer()
        return result

    def _serve_resends(self, packets, budget):
        """Answer pending resend requests, returning the remaining budget. The
        device counts chunk packets only, so its index i is our packets[1 + i]."""
        while budget > 0:
            request = self._take_request()
            if request is None: break
            flag, index = request
            if flag == 0x01 and 0 <= index < len(packets) - 1:
                self.logger.debug("{0}: resending chunk {1}".format(self.type, index))
                self.send_command("set gif", packets[1 + index], skipRead=True)
                budget -= 1
            # flag 0 mid-stream, or an index we never sent: nothing to do
        return budget

    def _take_request(self):
        """Pop the next request out of the input buffer as (flag, index).

        Wire format: 04 8b 55 <flag> [index LE16]. flag 0 asks for the animation
        and carries no index, flag 1 asks for the chunk at index again."""
        buf = bytes(self.message_buf)
        at = buf.find(self.REQUEST_MARK)
        if at < 0 or len(buf) < at + 4: return None
        flag = buf[at + 3]
        if flag != 0x01:
            self.message_buf = list(buf[at + 4:])
            return flag, 0
        if len(buf) < at + 6: return None # index not fully arrived yet
        self.message_buf = list(buf[at + 6:])
        return flag, int.from_bytes(buf[at + 4:at + 6], "little")

    def send_json(self, payload):
        """Send a JSON request over SPP, the way the app mirrors its cloud calls"""
        return self.send_command("set json", list(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")))

    def send_media(self, images, speed=1000):
        """Send frames to the Divoom device as one zstd compressed animation"""
        if (self.socket == None): return
        return self._send_packets(self._build_packets(self._encode_media(images, speed)))

    # --- overrides -------------------------------------------------------

    def checksum(self, payload):
        """Compute the payload checksum, always masked to 16 bits. A full media
        chunk can sum past 0xffff, where the base would widen it to four bytes and
        corrupt the frame."""
        csum = []
        csum += (sum(payload) & 0xffff).to_bytes(2, byteorder='little')
        return csum

    def send_brightness(self, value=None):
        """Send brightness, as opcode and as the app's Channel/SetBrightness request"""
        result = super().send_brightness(value)
        if value != None: self.send_json({"Command": "Channel/SetBrightness", "Brightness": int(value)})
        return result

    def send_datetime(self, value=None):
        """Send date and time, as opcode and as the app's Device/SetUTC request"""
        result = super().send_datetime(value)
        clock = datetime.datetime.now() if value == None else datetime.datetime.fromisoformat(value)
        self.send_json({"Command": "Device/SetUTC", "Utc": int(clock.timestamp()), "Time": clock.strftime("%Y-%m-%d %H:%M:%S")})
        return result

    def show_clock(self, clock=None, clock_id=None, twentyfour=None, weather=None, temp=None, calendar=None, color=None, hot=None):
        """Show clock by id, the app's Channel/SetClockSelectId request. These devices
        have no styles, so the remaining parameters are ignored."""
        if clock_id == None:
            self.logger.warning("{0}: clock needs clock_id".format(self.type))
            return None
        return self.send_json({"Command": "Channel/SetClockSelectId", "ClockId": int(clock_id)})

    def show_image(self, file, time=None):
        """Show a still image or animated GIF on the Divoom device."""
        with Image.open(file) as img:
            n = getattr(img, "n_frames", 1)
            if n > 1:
                frames, durations = [], []
                for i in range(n):
                    img.seek(i)
                    frames.append(self._fit(img))
                    durations.append(img.info.get("duration", 100))
                speed = max(1, int(sum(durations) / len(durations) if time is None else time))
            else:
                frames, speed = [self._fit(img)], 1000
        return self.send_media(frames, speed=speed)

    def show_lyrics(self, effect=None, background=None):
        """Show lyrics, the app's Lyric/Enter request, followed by Lyric/SetConfig
        when both effect and background are given."""
        result = self.send_json({"Command": "Lyric/Enter"})
        if effect == None and background == None: return result
        if effect == None or background == None:
            self.logger.warning("{0}: lyrics config needs both effect and background".format(self.type))
            return result
        return self.send_json({"Command": "Lyric/SetConfig", "TextEffect": int(effect), "Background": int(background)})

    def show_scoreboard(self, blue=None, red=None):
        """Show scoreboard, the app's set tool request with red and blue score"""
        if blue == None: blue = 0
        if isinstance(blue, str): blue = int(blue)
        if red == None: red = 0
        if isinstance(red, str): red = int(red)

        args = [0x01, 0x01]
        args += red.to_bytes(2, byteorder='little')
        args += blue.to_bytes(2, byteorder='little')
        return self.send_command("set tool", args)

    def show_sleep(self, value=None, sleeptime=None, sleepmode=None, volume=None, color=None, brightness=None, frequency=None, volumes=None):
        """Show sleep mode, the app's WhiteNoise/Set request with one volume per sound.
        Without its own volume, the slot picked by sleepmode gets volume. Color,
        brightness and frequency are ignored."""
        if sleeptime == None: sleeptime = 120
        slots = [0] * 8
        if volume != None and sleepmode != None and 0 <= int(sleepmode) < len(slots): slots[int(sleepmode)] = int(volume)
        for index, slot in enumerate((volumes or [])[:len(slots)]):
            if slot != None: slots[index] = int(slot)
        return self.send_json({"Command": "WhiteNoise/Set", "EndStatus": 0, "OnOff": 1 if value == True or value == 1 else 0, "Time": int(sleeptime), "Volume": slots})

    def show_text(self, text, font, size=None, time=None, color1=None, color2=None):
        """Render wrapped, centered text into a 128x128 frame and show it. Text
        taller than the screen scrolls up from the bottom instead."""
        if color1 is None or len(color1) < 3: color1 = [0xff, 0xff, 0xff]
        if color2 is None or len(color2) < 3: color2 = [0x00, 0x00, 0x00]
        S = self.screensize
        fontSize = int(size) if size else 24

        fnt = ImageFont.load_default(fontSize)
        try:
            if font is not None: fnt = ImageFont.truetype(font, fontSize)
        except OSError:
            pass

        img = Image.new("RGB", (S, S), tuple(color2))
        drw = ImageDraw.Draw(img)

        # greedy word-wrap to the screen width (with a small margin)
        max_w = S - 4
        words, lines, cur = str(text).split(), [], ""
        for w in words:
            trial = w if cur == "" else cur + " " + w
            if drw.textlength(trial, font=fnt) <= max_w or cur == "":
                cur = trial
            else:
                lines.append(cur); cur = w
        if cur: lines.append(cur)
        if not lines: lines = [""]

        ascent, descent = fnt.getmetrics()
        line_h = ascent + descent
        total_h = line_h * len(lines)
        y = max(0, (S - total_h) // 2)
        if total_h > S:
            img = Image.new("RGB", (S, S + total_h + S), tuple(color2))
            drw = ImageDraw.Draw(img)
            y = S
        for line in lines:
            lw = drw.textlength(line, font=fnt)
            drw.text(((S - lw) // 2, y), line, font=fnt, fill=tuple(color1))
            y += line_h

        if total_h <= S: return self.send_media([img], speed=1000)
        step = max(S // 16, -(-(total_h + S) // (self.maxframes - 1)))
        frames = [img.crop((0, top, S, top + S)) for top in range(0, total_h + S + 1, step)]
        return self.send_media(frames, speed=100 if time is None else max(1, int(time)))
