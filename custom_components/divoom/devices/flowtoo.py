"""Provides class FlowToo that encapsulates the Divoom FlowToo Bluetooth communication."""

from PIL import Image, ImageChops

from .divoom128 import Divoom128

class FlowToo(Divoom128):
    """Class FlowToo encapsulates the Divoom FlowToo Bluetooth communication."""

    MEDIA_WINDOW_LOG = 16

    def __init__(self, adapter=None, host=None, mac=None, port=1, escapePayload=False, logger=None):
        self.type = "FlowToo"
        Divoom128.__init__(self, adapter, host, mac, port, escapePayload, logger)

    def _pixels(self, img):
        """Wire bytes of one quantized frame, RGB565 big-endian on this device.
        The bands occupy disjoint bits, so ImageChops.add never carries."""
        r, g, b = img.split()
        hi = ImageChops.add(r.point(lambda v: v & 0xf8), g.point(lambda v: v >> 5))
        lo = ImageChops.add(g.point(lambda v: (v & 0x1c) << 3), b.point(lambda v: v >> 3))
        return Image.merge("LA", (hi, lo)).tobytes()
