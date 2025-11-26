# SCPI Commands Reference

This document lists all SCPI (Standard Commands for Programmable Instruments) commands used in the EOL Host Application codebase for oscilloscope communication.

## Overview

The codebase uses SCPI commands to communicate with Siglent SDS1104X-U and other compatible oscilloscopes via both USB (USBTMC) and LAN (TCPIP) interfaces.

## Command Categories

### 1. Standard SCPI Commands

These are IEEE 488.2 standard commands supported by all SCPI-compliant instruments.

| Command | Type | Description | Usage in Codebase |
|---------|------|-------------|-------------------|
| `*IDN?` | Query | Query device identification | Used in connection tests, device discovery |
| `*RST` | Write | Reset device to default state | Used in troubleshooting examples |
| `*STOP` | Write | Stop acquisition | Used extensively in test sequences |

**Example Usage:**
```python
# Query device identification
idn = device.query('*IDN?')
# Response format: "MANUFACTURER,MODEL,SERIAL,VERSION"

# Reset device
device.write('*RST')

# Stop acquisition
device.write('*STOP')
```

### 2. Trigger Mode Commands

Commands for controlling oscilloscope trigger mode.

| Command | Type | Description | Usage in Codebase |
|---------|------|-------------|-------------------|
| `TRMD AUTO` | Write | Set trigger mode to AUTO | Used before starting measurements |
| `TRMD?` | Query | Query current trigger mode | Used to check oscilloscope state |

**Example Usage:**
```python
# Set trigger mode to AUTO
device.write('TRMD AUTO')

# Query trigger mode
trmd = device.query('TRMD?')
```

### 3. Timebase Commands

Commands for setting and querying the horizontal timebase.

| Command | Type | Description | Usage in Codebase |
|---------|------|-------------|-------------------|
| `TDIV {value}` | Write | Set timebase (seconds per division) | Used to configure oscilloscope timebase |
| `TDIV?` | Query | Query current timebase | Used to verify timebase settings |

**Example Usage:**
```python
# Set timebase to 10ms per division
device.write('TDIV 0.01')

# Query timebase
tdiv = device.query('TDIV?')
# Response format: "TDIV 1.000000E-02" or "TDIV 0.01"
```

**Note:** Timebase values are in seconds per division. Common values:
- `0.001` = 1ms/div
- `0.01` = 10ms/div
- `0.1` = 100ms/div
- `1.0` = 1s/div

### 4. Channel Trace Commands

Commands for enabling/disabling channel display.

| Command | Type | Description | Usage in Codebase |
|---------|------|-------------|-------------------|
| `C{ch}:TRA ON` | Write | Enable channel trace | Used to enable channels for measurement |
| `C{ch}:TRA OFF` | Write | Disable channel trace | Used to disable unused channels |
| `C{ch}:TRA?` | Query | Query channel trace status | Used to verify channel state |

**Example Usage:**
```python
# Enable channel 1
device.write('C1:TRA ON')

# Disable channel 2
device.write('C2:TRA OFF')

# Query channel 1 status
tra = device.query('C1:TRA?')
# Response format: "C1:TRA ON" or "C1:TRA OFF"
```

**Channel Numbers:** `{ch}` can be 1, 2, 3, or 4.

### 5. Channel Probe Attenuation Commands

Commands for querying probe attenuation settings.

| Command | Type | Description | Usage in Codebase |
|---------|------|-------------|-------------------|
| `C{ch}:ATTN?` | Query | Query probe attenuation | Used to verify probe settings |

**Example Usage:**
```python
# Query channel 1 probe attenuation
attn = device.query('C1:ATTN?')
# Response format: "C1:ATTN 811.97" or "ATTN 10.0"
# Value is the attenuation ratio (e.g., 10.0 for 10x probe)
```

**Note:** Probe attenuation is typically read-only on the oscilloscope. The value represents the attenuation ratio (1.0, 10.0, 100.0, etc.).

### 6. Channel Vertical Division Commands

Commands for setting and querying vertical scale (volts per division).

| Command | Type | Description | Usage in Codebase |
|---------|------|-------------|-------------------|
| `C{ch}:VDIV {value}` | Write | Set vertical division (V/div) | Used to configure channel scale |
| `C{ch}:VDIV?` | Query | Query vertical division | Used to verify channel settings |

**Example Usage:**
```python
# Set channel 1 to 2V per division
device.write('C1:VDIV 2')

# Query channel 1 vertical division
vdiv = device.query('C1:VDIV?')
# Response format: "C1:VDIV 2.000000E+00" or "C1:VDIV 2.0"
```

### 7. Channel Vertical Offset Commands

Commands for setting and querying vertical offset.

| Command | Type | Description | Usage in Codebase |
|---------|------|-------------|-------------------|
| `C{ch}:OFST {value}` | Write | Set vertical offset (volts) | Used to adjust channel baseline |
| `C{ch}:OFST?` | Query | Query vertical offset | Used to verify channel settings |

**Example Usage:**
```python
# Set channel 1 offset to -1V
device.write('C1:OFST -1')

# Query channel 1 offset
ofst = device.query('C1:OFST?')
# Response format: "C1:OFST -1.000000E+00" or "C1:OFST -1.0"
```

### 8. PAVA MEAN Commands

Commands for querying parameter average (mean voltage) values.

| Command | Type | Description | Usage in Codebase |
|---------|------|-------------|-------------------|
| `C{ch}:PAVA? MEAN` | Query | Query average voltage for channel | Used extensively for voltage measurements |

**Example Usage:**
```python
# Query average voltage for channel 1
pava = device.query('C1:PAVA? MEAN')
# Response format: "C1:PAVA MEAN,9.040000E+00V" or "C4:PAVA MEAN,9.04V"
```

**Important Notes:**
- PAVA commands require the channel to be enabled (`C{ch}:TRA ON`)
- Oscilloscope must have acquired data (run acquisition first)
- Typically used after stopping acquisition (`*STOP`)
- Response parsing: Extract numeric value from format `C{ch}:PAVA MEAN,{value}V`

**Response Parsing Example:**
```python
import re

response = "C1:PAVA MEAN,9.040000E+00V"
pattern = r'C\d+:PAVA\s+MEAN,([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)V?'
match = re.search(pattern, response, re.IGNORECASE)
if match:
    mean_voltage = float(match.group(1))  # 9.04
```

### 9. Waveform Commands

Commands for retrieving waveform data.

| Command | Type | Description | Usage in Codebase |
|---------|------|-------------|-------------------|
| `C{ch}:WF? ALL` | Query | Query complete waveform data | Used for detailed waveform analysis |

**Example Usage:**
```python
# Retrieve waveform for channel 1
device.write('C1:WF? ALL')
waveform_data = device.read_raw()  # Binary data
```

**Important Notes:**
- Returns binary data in SCPI binary block format
- Data includes waveform descriptor header followed by sample data
- Requires parsing using `WaveformDecoder` class
- Large data transfer - may require increased timeout (10+ seconds)

**Waveform Data Format:**
- Header: SCPI binary block header (e.g., `#9000...`)
- Descriptor: Binary structure with waveform parameters
- Data: Binary sample values (byte or word format)

### 10. Run/Stop Commands

Commands for controlling acquisition.

| Command | Type | Description | Usage in Codebase |
|---------|------|-------------|-------------------|
| `RUN` | Write | Start acquisition | Used to start measurements |
| `STOP` | Write | Stop acquisition | Used to stop measurements |

**Example Usage:**
```python
# Start acquisition
device.write('RUN')

# Stop acquisition
device.write('STOP')
```

**Note:** `STOP` is equivalent to `*STOP` for most oscilloscopes.

## Command Usage Patterns

### Typical Measurement Sequence

```python
# 1. Configure channels
device.write('C1:TRA ON')
device.write('C1:VDIV 2')
device.write('C1:OFST 0')

# 2. Set timebase
device.write('TDIV 0.01')  # 10ms/div

# 3. Set trigger mode
device.write('TRMD AUTO')

# 4. Start acquisition
device.write('RUN')
time.sleep(2.0)  # Wait for data acquisition

# 5. Stop acquisition
device.write('*STOP')
time.sleep(0.3)  # Wait for processing

# 6. Query average voltage
pava = device.query('C1:PAVA? MEAN')
```

### Channel Configuration Pattern

```python
# Enable and configure channel
device.write(f'C{channel}:TRA ON')
device.write(f'C{channel}:VDIV {vdiv_value}')
device.write(f'C{channel}:OFST {offset_value}')

# Verify configuration
tra = device.query(f'C{channel}:TRA?')
vdiv = device.query(f'C{channel}:VDIV?')
ofst = device.query(f'C{channel}:OFST?')
attn = device.query(f'C{channel}:ATTN?')
```

## Response Parsing

### Common Response Formats

1. **Numeric Values:**
   - Scientific notation: `1.000000E-02`
   - Decimal: `0.01`
   - With units: `2.000000E+00V`

2. **Status Values:**
   - ON/OFF: `C1:TRA ON`
   - Numeric: `1` or `0`

3. **IDN Response:**
   - Format: `MANUFACTURER,MODEL,SERIAL,VERSION`
   - Example: `SIGLENT TECHNOLOGIES,SDS1104X-U,SN123456,1.2.3`

### Parsing Helpers

The codebase includes regex patterns for parsing responses:

```python
import re

REGEX_ATTN = re.compile(r'ATTN\s+([\d.]+)', re.IGNORECASE)
REGEX_TDIV = re.compile(r'TDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_VDIV = re.compile(r'VDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_OFST = re.compile(r'OFST\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_PAVA = re.compile(r'C\d+:PAVA\s+MEAN,([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)V?', re.IGNORECASE)
```

## Error Handling

### Common Issues

1. **Timeout Errors:**
   - Increase timeout for large data transfers (waveform data)
   - Default: 5000ms, use 10000ms+ for waveforms

2. **PAVA Query Failures:**
   - Ensure channel is enabled
   - Ensure data has been acquired
   - Try stopping acquisition before querying

3. **Connection Errors:**
   - Verify network connectivity (LAN)
   - Check USB connection (USB)
   - Verify SCPI over LAN is enabled (LAN)

## Testing

Use the test script to verify all commands:

```bash
# Test all SCPI commands via LAN
python scripts/test_scpi_commands_lan.py --ip 192.168.1.100

# Auto-discover and test
python scripts/test_scpi_commands_lan.py
```

## References

- [Siglent SDS1104X-U Programming Manual](https://siglent.com)
- IEEE 488.2 Standard Commands for Programmable Instruments
- SCPI (Standard Commands for Programmable Instruments) Standard

## Command Summary Table

| Category | Commands | Total |
|----------|----------|-------|
| Standard | `*IDN?`, `*RST`, `*STOP` | 3 |
| Trigger | `TRMD AUTO`, `TRMD?` | 2 |
| Timebase | `TDIV {value}`, `TDIV?` | 2 |
| Channel Trace | `C{ch}:TRA ON/OFF`, `C{ch}:TRA?` | 3 |
| Attenuation | `C{ch}:ATTN?` | 1 |
| Vertical Division | `C{ch}:VDIV {value}`, `C{ch}:VDIV?` | 2 |
| Vertical Offset | `C{ch}:OFST {value}`, `C{ch}:OFST?` | 2 |
| PAVA | `C{ch}:PAVA? MEAN` | 1 |
| Waveform | `C{ch}:WF? ALL` | 1 |
| Run/Stop | `RUN`, `STOP` | 2 |

**Total Unique Commands: 19**

