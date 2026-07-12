"""Golden-master tests: every case in tests/cases.py must produce byte-for-
byte the same Bluetooth traffic as recorded in tests/goldens/.

If a test here fails after an intentional, approved code change, regenerate
the affected golden file(s) with `python tests/record_goldens.py` and review
the diff before trusting it - see the plan's "Byte-Identität" rule.
"""
from __future__ import annotations

import os

import pytest

from tests.cases import DEVICE_CLASSES, all_cases
from tests.support import GOLDEN_DIR, format_golden, make_connected_device

CASE_IDS = [
    (device_type, case_name)
    for device_type in DEVICE_CLASSES
    for case_name, _ in all_cases()
]


@pytest.mark.parametrize(
    "device_type, case_name", CASE_IDS, ids=[f"{d}-{c}" for d, c in CASE_IDS]
)
def test_golden_master(device_type, case_name):
    device_cls = DEVICE_CLASSES[device_type]
    case_fn = dict(all_cases())[case_name]

    golden_path = os.path.join(GOLDEN_DIR, device_type, f"{case_name}.txt")
    assert os.path.exists(golden_path), (
        f"golden file missing: {golden_path}. "
        "Run `python tests/record_goldens.py` to generate it."
    )
    with open(golden_path, "r", encoding="ascii") as f:
        expected = f.read()

    device, recorder, server_sock = make_connected_device(device_cls)
    try:
        case_fn(device)
    finally:
        device.disconnect()
        server_sock.close()

    assert format_golden(recorder.sent_messages) == expected
