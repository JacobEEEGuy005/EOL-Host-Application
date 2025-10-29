SocketCAN smoke-test and setup
=============================

This document shows how to run the `scripts/socketcan_smoke_test.py` smoke-test on a Linux machine
that exposes a SocketCAN interface (for example a Raspberry Pi or a Linux desktop with `vcan` set up).

Creating a virtual CAN interface (vcan0) for testing

1. Load the vcan kernel module (requires root):

   sudo modprobe vcan

2. Create a vcan device and bring it up:

   sudo ip link add dev vcan0 type vcan
   sudo ip link set up vcan0

Verify it exists:

   ip -details link show vcan0

Running the smoke test

From the repository root run:

```bash
python scripts/socketcan_smoke_test.py --channel vcan0 --timeout 3.0
```

You should see output similar to:

```
Opening SocketCAN adapter channel= vcan0
Sending test frame id=0x100 data=010203
Listening for replies for 3.0 seconds...
Received 0 frame(s)
```

Notes & troubleshooting

- If you are using a real CAN interface (e.g. can0), you may need root privileges or to add your user to
  a group allowed to access CAN devices. On some systems `sudo` is required.
- For Raspberry Pi with a USB-to-CAN adapter, use the kernel SocketCAN driver or the adapter's vendor driver and set `--channel` accordingly (e.g. can0).
- The smoke-test is designed to be low-risk and only transmits a single test frame.
