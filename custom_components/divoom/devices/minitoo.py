"""Provides class MiniToo that encapsulates the Divoom MiniToo Bluetooth communication.

The MiniToo is a 128x128 color LCD, not a 16x16 LED matrix. Its custom media is
pushed with the newer SPP_APP_NEW_GIF_CMD2020 (0x8b) command: RGB888 frames,
Zstandard-compressed (window_log=17, matching the Android app), wrapped in a start
packet plus 256-byte chunks. Channel/tool commands (clock, brightness, on/off, ...)
share the base protocol, so only the pixel-push path is overridden here.

Protocol reverse-engineered by https://github.com/alvinunreal/divoom-minitoo-osx
"""

import time
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .divoom import Divoom

try:
    _LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # Pillow < 9.1
    _LANCZOS = Image.LANCZOS


class MiniToo(Divoom):
    """Class MiniToo encapsulates the Divoom MiniToo Bluetooth communication."""

    def __init__(self, host=None, mac=None, port=1, escapePayload=False, logger=None):
        self.type = "MiniToo"
        self.screensize = 128
        self.chunksize = 256
        self.colorpalette = None
        if escapePayload == None: escapePayload = False
        Divoom.__init__(self, host, mac, port, escapePayload, logger)

    # --- internals -------------------------------------------------------

    def _await_request(self, timeout=2.0):
        """Wait for the device's 'ready for animation' request (contains 04 8b 55)
        after the start packet. Streaming chunks before the device asks for them is
        why the first send after the device idled or changed face got dropped."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.receive()
            if b"\x04\x8b\x55" in bytes(self.message_buf):
                self.drop_message_buffer()
                return True
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
        """Encode RGB frames into a MiniToo media payload.

        Layout (from decompiled W2.c.f()):
          25 <frame_count_u8> <speed_ms_be16> <row_blocks_u8> <col_blocks_u8>
          <zstd_len_be32> <zstd_frame>
        Pixels are concatenated RGB888 frames, zstd level 17, window_log 17.
        """
        import zstandard as zstd  # only MiniToo needs it; keep it out of base import

        if not images: raise ValueError("at least one frame is required")
        if len(images) > 255: images = images[:255]  # frame_count is one byte
        blocks = self.screensize // 16
        raw = b"".join(img.tobytes("raw", "RGB") for img in images)

        compressor = zstd.ZstdCompressor(
            compression_params=zstd.ZstdCompressionParameters.from_level(
                17, window_log=17, write_content_size=True))
        zbytes = compressor.compress(raw)

        header = bytes([0x25, len(images)]) + speed.to_bytes(2, "big") \
            + bytes([blocks, blocks]) + len(zbytes).to_bytes(4, "big")
        return header + zbytes

    def _fit(self, img):
        """EXIF-transpose, RGB, center-crop square, resize to the 128x128 grid."""
        img = ImageOps.exif_transpose(img).convert("RGB")
        side = min(img.size)
        left = (img.width - side) // 2
        top = (img.height - side) // 2
        return img.crop((left, top, left + side, top + side)).resize(
            (self.screensize, self.screensize), _LANCZOS)

    def _send_packets(self, packets, delay=0.012):
        """Send the start packet, wait for the device to request the animation,
        then stream the chunks — matching the app's real handshake."""
        self.drop_message_buffer()
        result = self.send_command("set gif", packets[0], skipRead=True)
        self._await_request()
        for packet in packets[1:]:
            result = self.send_command("set gif", packet, skipRead=True)
            time.sleep(delay)
        self.clear_input_buffer() # swallow the final ACK
        return result

    def send_media(self, images, speed=1000):
        """Send frames to the Divoom device as one zstd compressed animation"""
        return self._send_packets(self._build_packets(self._encode_media(images, speed)))

    # --- overrides -------------------------------------------------------

    def checksum(self, payload):
        """Compute the payload checksum, always masked to 16 bits like the app does.
        A full media chunk can sum past 0xffff, where the base would widen it to four
        bytes and corrupt the frame."""
        csum = []
        csum += (sum(payload) & 0xffff).to_bytes(2, byteorder='little')
        return csum

    def show_image(self, file, time=None):
        """Show a still image or animated GIF on the MiniToo."""
        with Image.open(file) as img:
            n = getattr(img, "n_frames", 1)
            if n > 1:
                frames, durations = [], []
                for i in range(min(n, 255)):
                    img.seek(i)
                    frames.append(self._fit(img.convert("RGB")))
                    durations.append(img.info.get("duration", 100))
                speed = max(1, int(sum(durations) / len(durations)))
            else:
                frames, speed = [self._fit(img)], 1000
        return self.send_media(frames, speed=speed)

    def show_text(self, text, font, size=None, time=None, color1=None, color2=None):
        """Render wrapped, centered text into a 128x128 frame and show it."""
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
        for line in lines:
            lw = drw.textlength(line, font=fnt)
            drw.text(((S - lw) // 2, y), line, font=fnt, fill=tuple(color1))
            y += line_h

        return self.send_media([img], speed=1000)
