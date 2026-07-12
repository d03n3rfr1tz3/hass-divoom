"""Registry of golden-master test cases exercised against every Divoom
device. Shared by tests/test_golden_devices.py (assertions) and
tests/record_goldens.py (golden generation) so both use the exact same
device/case set.
"""
from __future__ import annotations

import os

from custom_components.divoom.devices.aurabox import Aurabox
from custom_components.divoom.devices.backpack import Backpack
from custom_components.divoom.devices.ditoo import Ditoo
from custom_components.divoom.devices.ditoomic import DitooMic
from custom_components.divoom.devices.pixoo import Pixoo
from custom_components.divoom.devices.pixoomax import PixooMax
from custom_components.divoom.devices.timebox import Timebox
from custom_components.divoom.devices.timeboxmini import TimeboxMini
from custom_components.divoom.devices.timoo import Timoo
from custom_components.divoom.devices.tivoo import Tivoo

DEVICE_CLASSES = {
    "Aurabox": Aurabox,
    "Backpack": Backpack,
    "Ditoo": Ditoo,
    "DitooMic": DitooMic,
    "Pixoo": Pixoo,
    "PixooMax": PixooMax,
    "Timebox": Timebox,
    "TimeboxMini": TimeboxMini,
    "Timoo": Timoo,
    "Tivoo": Tivoo,
}

PIXELART_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "pixelart"))
FONT_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "divoom", "fonts", "arial.ttf"
))


def pixelart_files() -> list[str]:
    """List every file under pixelart/, sorted, so files added later are
    picked up automatically instead of relying on a hardcoded name list."""
    return sorted(
        name for name in os.listdir(PIXELART_DIR)
        if os.path.isfile(os.path.join(PIXELART_DIR, name))
    )


FIXED_CASES = {
    "show_clock": lambda d: d.show_clock(
        clock=3, twentyfour=True, weather=True, temp=True, calendar=True,
        color=[10, 20, 30], hot=True,
    ),
    "show_light": lambda d: d.show_light(color=[255, 0, 128], brightness=77, power=True),
    "show_effects": lambda d: d.show_effects(2),
    "show_visualization": lambda d: d.show_visualization(1, color1=[1, 2, 3], color2=[4, 5, 6]),
    "show_scoreboard": lambda d: d.show_scoreboard(blue=12, red=34),
    "show_alarm": lambda d: d.show_alarm(
        number=1, time="07:30", weekdays=["mon", "wed", "fri"],
        alarmMode=1, triggerMode=1, frequency=101.1, volume=80,
    ),
    "show_sleep": lambda d: d.show_sleep(
        value=True, sleeptime=45, sleepmode=1, volume=50,
        color=[9, 9, 9], brightness=60, frequency=99.5,
    ),
    "show_countdown": lambda d: d.show_countdown(value=True, countdown="00:30"),
    "show_timer": lambda d: d.show_timer(5),
    "show_noise": lambda d: d.show_noise(True),
    "show_memorial": lambda d: d.show_memorial(
        number=2, value="2024-05-06T12:00:00", text="Test", animate=True,
    ),
    "send_brightness": lambda d: d.send_brightness(42),
    "send_volume": lambda d: d.send_volume(60),
    "send_weather": lambda d: d.send_weather("22°C", weather=3),
    "send_datetime": lambda d: d.send_datetime("2024-01-02T03:04:05"),
    "send_playstate": lambda d: d.send_playstate(True),
    "show_radio": lambda d: d.show_radio(True, frequency=101.3),
    "show_text": lambda d: d.show_text("HA", FONT_PATH, color1=[255, 255, 255], color2=[1, 1, 1]),
}


def image_case_name(filename: str) -> str:
    stem = os.path.splitext(filename)[0]
    return f"show_image_{stem}"


def make_image_case(filename: str):
    path = os.path.join(PIXELART_DIR, filename)
    return lambda d: d.show_image(path)


def all_cases():
    """Yield (case_name, callable) for every fixed case plus one show_image
    case per file currently in pixelart/."""
    for name, fn in FIXED_CASES.items():
        yield name, fn
    for filename in pixelart_files():
        yield image_case_name(filename), make_image_case(filename)
