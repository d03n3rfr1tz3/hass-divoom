"""Regenerates the golden-master files under tests/goldens/ from the
CURRENTLY installed code.

Only run this after an intentionally approved output change, and only for
the specific device/case whose behaviour actually changed. Never run it to
"fix" a failing golden-master test without first confirming the new bytes
are correct.

Usage (from the repository root): python tests/record_goldens.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from tests.cases import DEVICE_CLASSES, all_cases  # noqa: E402
from tests.support import GOLDEN_DIR, format_golden, make_connected_device  # noqa: E402


def record_all() -> None:
    for device_type, device_cls in DEVICE_CLASSES.items():
        out_dir = os.path.join(GOLDEN_DIR, device_type)
        os.makedirs(out_dir, exist_ok=True)
        for case_name, case_fn in all_cases():
            device, recorder, server_sock = make_connected_device(device_cls)
            try:
                case_fn(device)
            finally:
                device.disconnect()
                server_sock.close()

            golden_path = os.path.join(out_dir, f"{case_name}.txt")
            with open(golden_path, "w", encoding="ascii") as f:
                f.write(format_golden(recorder.sent_messages))
            print(f"wrote {golden_path} ({len(recorder.sent_messages)} messages)")


if __name__ == "__main__":
    record_all()
