# PCAN Smoke Test

This folder contains a small smoke test to exercise the `PcanAdapter` against a physical PCAN USB device.

Requirements
- Windows machine with PEAK PCAN drivers (PCANBasic) installed or a Linux/RPi with a supported PCAN backend.
- python-can installed with PCAN support (e.g. `pip install python-can`).
- The project virtualenv should have the repository installed or be run from the repo root so imports work.

Usage (Windows, cmd.exe)

```cmd
python scripts\pcan_smoke_test.py --channel PCAN_USBBUS1 --bitrate 500000 --id 0x100 --data 010203 --timeout 5
```

Example flow
- The script opens the `PcanAdapter` using environment or CLI args.
- It sends a single frame (ID/data) and listens for replies for the timeout period.
- Any received frames are printed to stdout.

Troubleshooting
- If the script errors with "Failed to open PCAN adapter" or similar, verify that:
  - The PEAK drivers are installed and the device is visible.
  - `python-can` supports the `pcan` bustype on your platform.
  - On Windows, run the script with a user that has permission to access the device.

If you want, run this script and paste the output here; I will interpret it and update the adapter or tests as needed.
