"""SocketCAN smoke-test script.

Usage (Linux with vcan0 or can0 configured):
  python scripts/socketcan_smoke_test.py --channel vcan0 --timeout 2.0

This script opens the SocketCAN adapter, sends a test frame and listens for replies.
"""
from __future__ import annotations

import time
import argparse

from backend.adapters.socketcan import SocketCanAdapter
from backend.adapters.interface import Frame


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--channel", default=None)
    p.add_argument("--timeout", type=float, default=2.0)
    args = p.parse_args()

    a = SocketCanAdapter(channel=args.channel)
    print("Opening SocketCAN adapter channel=", args.channel)
    a.open()

    f = Frame(can_id=0x100, data=b"\x01\x02\x03")
    print("Sending test frame id=0x100 data=010203")
    a.send(f)

    print(f"Listening for replies for {args.timeout} seconds...")
    start = time.time()
    count = 0
    while time.time() - start < args.timeout:
        r = a.recv(timeout=0.5)
        if r is None:
            continue
        count += 1
        print(f"Received frame #{count}: id=0x{r.can_id:x} data={r.data.hex()} ts={r.timestamp}")

    print(f"Received {count} frame(s)")
    a.close()


if __name__ == "__main__":
    main()
