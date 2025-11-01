# Debugging Guide

This guide explains how to enable and view debug messages for troubleshooting the EOL Host Application.

## Enabling Debug Logging

The application uses Python's `logging` module. Debug messages can be enabled by setting environment variables or modifying logging configuration.

### Method 1: Environment Variable (Recommended)

Set the `LOG_LEVEL` environment variable before running the application:

**Windows (Command Prompt):**
```cmd
set LOG_LEVEL=DEBUG
python host_gui/main.py
```

**Windows (PowerShell):**
```powershell
$env:LOG_LEVEL="DEBUG"
python host_gui/main.py
```

**Linux/Mac:**
```bash
export LOG_LEVEL=DEBUG
python host_gui/main.py
```

### Method 2: Direct Logging Configuration

You can also modify the logging level directly in `host_gui/main.py` around line 38:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## Where to View Log Messages

### Console/Terminal Output

By default, log messages are printed to the console/terminal where the application was launched:

- **Windows**: Command Prompt or PowerShell window
- **Linux/Mac**: Terminal window

Look for messages prefixed with timestamps, module names, and log levels:
```
2024-01-15 10:30:45,123 - host_gui.main - INFO - Starting host GUI
2024-01-15 10:30:45,456 - host_gui.services.signal_service - DEBUG - SignalService decoded 5 signals
```

### Common Debug Messages for Signal View

When debugging Signal View issues, look for these messages:

1. **DBC Loading:**
   - `DBC loaded successfully via service: <filename>`
   - `Synced legacy DBC load into DbcService: <filename>`

2. **Frame Reception:**
   - `Received frame: ID=0x<can_id>`
   - `Processing frame in _add_frame_row`

3. **Signal Decoding:**
   - `SignalService decoded <N> signals from frame 0x<can_id>`
   - `SignalService returned no signals for frame 0x<can_id>`
   - `DBC service loaded: True/False, Legacy DBC: True/False`

4. **Error Messages:**
   - `Failed to decode message 0x<can_id>: <error>`
   - `No message found in DBC for CAN ID 0x<can_id>`
   - `SignalService decode failed, falling back to legacy`

## Troubleshooting Signal View

If signals are not appearing in Signal View:

1. **Check DBC is loaded:**
   - Look for "DBC loaded successfully" messages
   - Verify `DBC service loaded: True` in debug logs

2. **Check frames are being received:**
   - Look for "Received frame" or "Processing frame" messages
   - Verify CAN adapter is connected and receiving traffic

3. **Check signal decoding:**
   - Look for "SignalService decoded N signals" messages
   - If you see "returned no signals", check:
     - Is the CAN ID in the DBC?
     - Is the frame data valid?
     - Are there any decode errors?

4. **Check legacy fallback:**
   - If service decode fails, should fall back to legacy decode
   - Look for "falling back to legacy" messages

## Saving Logs to File

To save logs to a file for later analysis:

```python
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('eol_host_debug.log'),
        logging.StreamHandler()  # Also print to console
    ]
)
```

Or redirect output when launching:
```bash
python host_gui/main.py > debug.log 2>&1
```

## Signal View Debug Checklist

- [ ] DBC file is loaded (check log for "DBC loaded successfully")
- [ ] CAN adapter is connected and receiving frames
- [ ] Frames are being decoded (check for "decoded N signals" messages)
- [ ] CAN IDs in received frames match messages in DBC
- [ ] No decode errors in logs
- [ ] Signal table widget exists and is visible

