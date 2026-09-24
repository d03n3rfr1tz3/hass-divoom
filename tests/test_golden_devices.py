"""Golden-master tests: every case in tests/cases.py must send byte-for-byte
the traffic recorded in tests/goldens/. After an intended output change,
regenerate them with `python tests/record_goldens.py` and review the diff.

Exceptions:
- show_text is compared structurally (message count, lengths, headers), as
  FreeType hinting at small font sizes differs between the Windows and Linux
  Pillow wheels. Escaping devices are compared unescaped, since a shifted
  pixel can change the escaped length.
- The media cases of the 128x128 devices are zstd streams, which are not
  byte-stable across libzstd versions. tests/test_divoom128_media.py checks
  them instead.
"""
from __future__ import annotations

import os

import pytest

from custom_components.divoom.devices.divoom import DivoomUnsupportedError
from tests.cases import DEVICE_CLASSES, DEVICE_RESPONDERS, all_cases, is_media_case
from tests.support import (
    GOLDEN_DIR,
    format_golden,
    make_connected_device,
    parse_golden,
    unescape_message,
)

CASE_IDS = [
    (device_type, case_name)
    for device_type in DEVICE_CLASSES
    for case_name, _ in all_cases()
    if not is_media_case(device_type, case_name)
]

# see module docstring
TEXT_RENDERING_CASES = {"show_text"}
HEADER_LENGTH = 4


@pytest.mark.parametrize(
    "device_type, case_name", CASE_IDS, ids=[f"{d}-{c}" for d, c in CASE_IDS]
)
def test_golden_master(device_type, case_name):
    device_cls = DEVICE_CLASSES[device_type]
    case_fn = dict(all_cases())[case_name]

    device_dir = os.path.join(GOLDEN_DIR, device_type)
    assert os.path.isdir(device_dir), (
        f"no goldens recorded for {device_type}. "
        "Run `python tests/record_goldens.py` to generate them."
    )

    expected = ""
    golden_path = os.path.join(device_dir, f"{case_name}.txt")
    if os.path.exists(golden_path):
        with open(golden_path, "r", encoding="ascii") as f:
            expected = f.read()

    device, recorder, server_sock = make_connected_device(
        device_cls, responder=DEVICE_RESPONDERS.get(device_type))
    try:
        case_fn(device)
    except DivoomUnsupportedError:
        pass # a refused mode sends nothing, so the golden stays empty
    finally:
        device.disconnect()
        server_sock.close()

    if case_name in TEXT_RENDERING_CASES:
        expected_messages = parse_golden(expected)
        actual_messages = recorder.sent_messages
        assert len(actual_messages) == len(expected_messages)
        if device.escapePayload:
            expected_messages = [unescape_message(m) for m in expected_messages]
            actual_messages = [unescape_message(m) for m in actual_messages]
        for expected_message, actual_message in zip(expected_messages, actual_messages):
            assert len(actual_message) == len(expected_message)
            assert actual_message[:HEADER_LENGTH] == expected_message[:HEADER_LENGTH]
    else:
        assert format_golden(recorder.sent_messages) == expected
