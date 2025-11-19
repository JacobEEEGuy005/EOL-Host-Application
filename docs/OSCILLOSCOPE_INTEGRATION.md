# Oscilloscope Integration

## Overview

The EOL Host Application integrates with USBTMC-compatible oscilloscopes via the `OscilloscopeService`. This service provides a high-level interface for connecting to oscilloscopes, configuring channels, and retrieving waveform data.

## Supported Oscilloscopes

- **Siglent SDS1104X-U** (primary, tested)
- Other USBTMC-compatible oscilloscopes

## OscilloscopeService

The `OscilloscopeService` class (`host_gui/services/oscilloscope_service.py`) provides:

- Device scanning and connection
- Channel configuration (enable/disable, probe attenuation, units)
- Timebase configuration
- SCPI command/query interface
- Waveform data retrieval
- PAVA MEAN queries for average voltage measurements

## Prerequisites

### Required Libraries

- **PyVISA**: For USBTMC communication
  ```bash
  pip install pyvisa
  ```

### Optional Libraries

- **pyusb**: For enhanced USB device detection (optional)

### System Requirements

- Linux: May require udev rules for USB device access
- Windows: PyVISA should handle device access automatically
- macOS: PyVISA should handle device access automatically

## Basic Usage

### Initialization

```python
from host_gui.services.oscilloscope_service import OscilloscopeService

osc_service = OscilloscopeService()
```

### Scanning for Devices

```python
devices = osc_service.scan_for_devices()
if devices:
    print(f"Found {len(devices)} oscilloscope(s):")
    for device in devices:
        print(f"  - {device}")
else:
    print("No oscilloscopes found")
```

### Connecting

```python
if devices:
    resource = devices[0]
    if osc_service.connect(resource):
        print("Connected successfully")
        # Get device info
        info = osc_service.get_device_info()
        print(f"Device: {info}")
    else:
        print("Connection failed")
```

### Disconnecting

```python
osc_service.disconnect()
```

## Channel Configuration

### Single Channel Configuration

```python
# Configure channel 1
success = osc_service.configure_channel(
    channel=1,
    enabled=True,
    probe_attenuation=10.0,  # 10x probe
    unit='A'  # Unit label (oscilloscope measures voltage, unit is for reference)
)

if success:
    print("Channel 1 configured successfully")
else:
    print("Channel 1 configuration failed")
```

### Full Configuration

```python
config = {
    'channels': {
        'CH1': {
            'enabled': True,
            'probe_attenuation': 10.0,
            'unit': 'A',
            'channel_name': 'Phase V Current'
        },
        'CH2': {
            'enabled': True,
            'probe_attenuation': 10.0,
            'unit': 'A',
            'channel_name': 'Phase W Current'
        },
        'CH3': {
            'enabled': False
        },
        'CH4': {
            'enabled': False
        }
    },
    'acquisition': {
        'timebase_ms': 10.0  # 10ms per division
    }
}

success, errors = osc_service.apply_configuration(config)
if success:
    print("Configuration applied successfully")
else:
    print(f"Configuration errors: {errors}")
```

## SCPI Commands

### Sending Commands

```python
# Set trigger mode to AUTO
osc_service.send_command("TRMD AUTO")

# Set timebase to 10ms per division
osc_service.send_command("TDIV 0.01")

# Set channel 1 vertical division to 2V per division
osc_service.send_command("C1:VDIV 2")

# Set channel 1 offset to -1V
osc_service.send_command("C1:OFST -1")
```

### Querying Values

```python
# Query timebase
tdiv = osc_service.send_command("TDIV?")
print(f"Timebase: {tdiv}")

# Query channel 1 vertical division
vdiv = osc_service.send_command("C1:VDIV?")
print(f"Channel 1 VDIV: {vdiv}")

# Query channel 1 offset
ofst = osc_service.send_command("C1:OFST?")
print(f"Channel 1 offset: {ofst}")

# Query channel 1 trace status
tra = osc_service.send_command("C1:TRA?")
print(f"Channel 1 trace: {tra}")
```

## PAVA MEAN Queries

PAVA (Parameter Average) MEAN queries return the average voltage value for a channel:

```python
# Query PAVA MEAN for channel 1
mean_value = osc_service.query_pava_mean(channel=1, retries=3)
if mean_value is not None:
    print(f"Channel 1 average: {mean_value} V")
else:
    print("Failed to query PAVA MEAN")
```

The `query_pava_mean()` method:
- Sends `C{channel}:PAVA? MEAN` command
- Parses response to extract mean value in volts
- Retries on failure (default: 3 retries)
- Returns `None` if query fails

## Waveform Retrieval

Waveform data can be retrieved using SCPI commands:

```python
# Retrieve waveform for channel 1
osc_service.send_command("C1:WF? ALL")
waveform_data = osc_service.oscilloscope.read_raw()
```

**Note**: Waveform retrieval is typically handled by specialized services like `PhaseCurrentService` which use `WaveformDecoder` for parsing.

## Configuration Files

Oscilloscope configurations can be stored in JSON files:

### Configuration File Format

```json
{
  "channels": {
    "CH1": {
      "enabled": true,
      "probe_attenuation": 10.0,
      "unit": "A",
      "channel_name": "Phase V Current"
    },
    "CH2": {
      "enabled": true,
      "probe_attenuation": 10.0,
      "unit": "A",
      "channel_name": "Phase W Current"
    },
    "CH3": {
      "enabled": false
    },
    "CH4": {
      "enabled": false
    }
  },
  "acquisition": {
    "timebase_ms": 10.0
  }
}
```

### Loading Configuration

```python
import json

with open('oscilloscope_config.json', 'r') as f:
    config = json.load(f)

success, errors = osc_service.apply_configuration(config)
```

## Integration with Tests

### Phase Current Test

The Phase Current Test uses `OscilloscopeService` for:
- Validating oscilloscope settings before test
- Configuring channels for each test point
- Retrieving waveform data
- Querying PAVA MEAN values

```python
from host_gui.services.phase_current_service import PhaseCurrentTestStateMachine

# PhaseCurrentTestStateMachine uses OscilloscopeService internally
state_machine = PhaseCurrentTestStateMachine(gui=self, test=test_config)
success, info = state_machine.run()
```

### DC Bus Sensing Test

The DC Bus Sensing Test uses `OscilloscopeService` for:
- DC bus voltage measurement
- Waveform analysis

## Error Handling

### Connection Errors

```python
if not osc_service.connect(resource):
    print("Connection failed - check:")
    print("  1. Oscilloscope is powered on")
    print("  2. USB cable is connected")
    print("  3. PyVISA is installed")
    print("  4. Device permissions (Linux: udev rules)")
```

### Command Errors

```python
response = osc_service.send_command("INVALID_COMMAND")
if response is None:
    print("Command failed or timed out")
```

### Query Errors

```python
mean_value = osc_service.query_pava_mean(channel=1)
if mean_value is None:
    print("PAVA query failed - check:")
    print("  1. Channel is enabled")
    print("  2. Oscilloscope is connected")
    print("  3. Signal is present on channel")
```

## Troubleshooting

### Device Not Found

**Problem**: `scan_for_devices()` returns empty list

**Solutions**:
1. Check USB connection
2. Verify PyVISA installation: `pip install pyvisa`
3. Check device permissions (Linux):
   ```bash
   # Add udev rule for USBTMC devices
   sudo nano /etc/udev/rules.d/99-usbtmc.rules
   # Add: SUBSYSTEM=="usb", MODE="0666"
   sudo udevadm control --reload-rules
   ```
4. Try manual resource string: `USB0::0x1234::0x5678::INSTR`

### Connection Timeout

**Problem**: Connection succeeds but commands timeout

**Solutions**:
1. Increase timeout: `osc_service.oscilloscope.timeout = 10000` (10 seconds)
2. Check oscilloscope is responsive (try `*IDN?` command manually)
3. Verify USBTMC driver is installed

### Configuration Errors

**Problem**: `apply_configuration()` returns errors

**Solutions**:
1. Verify channel numbers are 1-4
2. Check probe attenuation values are reasonable (0.1 to 1000)
3. Verify timebase values are in valid range
4. Check oscilloscope supports all commands

### PAVA Query Returns None

**Problem**: `query_pava_mean()` returns `None`

**Solutions**:
1. Verify channel is enabled: `osc_service.send_command("C1:TRA?")`
2. Check signal is present on channel
3. Verify oscilloscope is in correct mode (not stopped)
4. Try increasing retries: `query_pava_mean(channel=1, retries=5)`

## Best Practices

1. **Always Check Connection**: Verify `is_connected()` before sending commands
2. **Handle Errors**: Check return values and handle `None` responses
3. **Use Configuration Files**: Store oscilloscope configs in JSON files
4. **Validate Settings**: Use `apply_configuration()` to validate settings
5. **Cleanup**: Always call `disconnect()` when done
6. **Timeout Settings**: Set appropriate timeouts for long operations
7. **Retry Logic**: Use retry logic for critical operations (PAVA queries)
8. **Error Messages**: Provide meaningful error messages to users

## Example: Complete Workflow

```python
from host_gui.services.oscilloscope_service import OscilloscopeService
import json

# Initialize service
osc_service = OscilloscopeService()

# Scan for devices
devices = osc_service.scan_for_devices()
if not devices:
    print("No oscilloscopes found")
    exit(1)

# Connect
if not osc_service.connect(devices[0]):
    print("Connection failed")
    exit(1)

# Load configuration
with open('oscilloscope_config.json', 'r') as f:
    config = json.load(f)

# Apply configuration
success, errors = osc_service.apply_configuration(config)
if not success:
    print(f"Configuration errors: {errors}")
    osc_service.disconnect()
    exit(1)

# Query PAVA MEAN for channel 1
mean_value = osc_service.query_pava_mean(channel=1)
if mean_value is not None:
    print(f"Channel 1 average: {mean_value} V")
else:
    print("Failed to query PAVA MEAN")

# Cleanup
osc_service.disconnect()
```

## Related Documentation

- [Service Architecture](SERVICE_ARCHITECTURE.md) - OscilloscopeService details
- [Test Type System Overview](TEST_TYPE_SYSTEM_OVERVIEW.md) - Test types using oscilloscope
- [Phase Current Test](../docs/Test%20Type%20Request/Phase%20Current%20Test.md) - Phase current test details

