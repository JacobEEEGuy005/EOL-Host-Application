# PCAN Adapter — Hardware notes

This document summarizes how to run the PCAN smoke test and configure the system for the PCAN adapter used by this project.

Requirements
- Windows with PEAK PCAN drivers (PCANBasic) installed (recommended for PCAN-USB dongles).
- python 3.11+ and `python-can` installed in your project virtualenv (e.g. `pip install python-can`).
- Repository checked out and working directory at repo root when running the smoke test so `backend` imports resolve.

Environment variables
- `PCAN_CHANNEL`: Optional. Default used by the adapter is `PCAN_USBBUS1`. Override to match your system.
- `PCAN_BITRATE`: Optional. Example `500000` (for 500 kbps).

Smoke test
1. From the repository root, run (cmd.exe):

```cmd
python scripts\pcan_smoke_test.py --channel PCAN_USBBUS1 --bitrate 500000 --id 0x100 --data 010203 --timeout 5
```

2. The script will:
   - Open the PCAN adapter.
   - Send one frame with the specified ID/data.
   - Listen for incoming frames for the specified timeout and print any that arrive.

Troubleshooting
- "Failed to open PCAN adapter" — usually means PCAN drivers aren't installed or `python-can` does not support `pcan` on your platform. On Windows, install PEAK drivers.
- Permissions — run the script with a user that has access to the hardware device.
- If you see many frames (as in our verification run), the hardware is communicating and the adapter is working.

If you run the script and paste the output here, I will help interpret it and add further diagnostic tooling if needed.
