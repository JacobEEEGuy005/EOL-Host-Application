r"""PCAN smoke test script

Usage (Windows cmd):
    python scripts\pcan_smoke_test.py --channel PCAN_USBBUS1 --bitrate 500000 --id 0x100 --data 010203 --timeout 5

The script will:
- open the PCAN adapter via `backend.adapters.pcan.PcanAdapter`
- send a single frame
- listen for frames for the specified timeout and print them

Notes:
- Requires PCAN drivers and python-can with the PCAN backend installed on the machine running the script.
- On Windows ensure PEAK drivers (PCANBasic) are installed and `python-can` supports 'pcan' bustype.
"""
from __future__ import annotations

import argparse
import binascii
import time
# typing.Optional not required here

import pathlib

# Ensure the repository root is on sys.path so `backend` imports resolve when running
# the script from the repo root.
ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from backend.adapters.pcan import PcanAdapter
from backend.adapters.interface import Frame


def parse_args():
    p = argparse.ArgumentParser(description="PCAN smoke test: send a frame and listen for replies")
    p.add_argument("--channel", default=None, help="PCAN channel (env PCAN_CHANNEL or e.g. PCAN_USBBUS1)")
    p.add_argument("--bitrate", type=int, default=None, help="Optional bitrate (e.g. 500000)")
    p.add_argument("--id", default="0x100", help="CAN ID to send (hex) e.g. 0x100")
    p.add_argument("--data", default="", help="Hex payload (e.g. 010203)")
    p.add_argument("--timeout", type=float, default=5.0, help="Time in seconds to listen for replies")
    return p.parse_args()


def main():
    args = parse_args()

    can_id = int(args.id, 0)
    data = binascii.unhexlify(args.data) if args.data else b""

    adapter = PcanAdapter(channel=args.channel, bitrate=args.bitrate)
    print(f"Opening PCAN adapter (channel={adapter.channel}, bitrate={adapter.bitrate})")
    try:
        adapter.open()
    except Exception as e:
        print("Failed to open PCAN adapter:", e)
        print("Ensure PCAN drivers are installed and python-can supports the 'pcan' bustype.")
        sys.exit(2)

    try:
        f = Frame(can_id=can_id, data=data, timestamp=None)
        print(f"Sending frame id=0x{f.can_id:x} data={f.data.hex()}")
        try:
            adapter.send(f)
        except Exception as e:
            print("Send failed:", e)
            print("If running on hardware, verify permissions/drivers.")
            adapter.close()
            sys.exit(3)

        print(f"Listening for replies for {args.timeout} seconds...")
        deadline = time.time() + args.timeout
        seen = 0
        while time.time() < deadline:
            frame = adapter.recv(timeout=1.0)
            if frame is None:
                continue
            seen += 1
            print(f"Received frame #{seen}: id=0x{frame.can_id:x} data={frame.data.hex()} ts={frame.timestamp}")

        if seen == 0:
            print("No frames received within timeout")
        else:
            print(f"Received {seen} frame(s)")

    finally:
        adapter.close()


if __name__ == "__main__":
    main()
