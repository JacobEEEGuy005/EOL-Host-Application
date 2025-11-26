wait_for_pr_ci.py
-----------------

This small helper script polls GitHub Actions workflow runs for a branch or pull
request and waits until the latest run completes. It's intended to support a
developer workflow where new commits are pushed and you want to wait for CI
before pushing further commits.

Requirements
- Python 3.8+
- `requests` library (`pip install requests`)
- A GitHub personal access token available in the environment as `GITHUB_TOKEN`
  (scopes: `repo` and `workflow` are sufficient).

Example
-------
Set your token and run for the current branch:

```powershell
$env:GITHUB_TOKEN = "ghp_..."
python .\scripts\wait_for_pr_ci.py --branch feature/stage-1-backend-core --timeout 600
```

Or monitor a PR by number:

```powershell
python .\scripts\wait_for_pr_ci.py --pr 6
```

Behavior
- Exit code 0: latest run succeeded
- Exit code 2: latest run completed with non-success conclusion
- Exit code 3: timed out waiting
- Exit code 4/5: misconfiguration or API error

push_and_wait.py
----------------

Small wrapper that pushes the current branch and waits for the associated CI
run to complete. The script prefers the GitHub CLI (`gh`) to find and watch the
workflow run; if `gh` is not available it falls back to `wait_for_pr_ci.py` and
requires `GITHUB_TOKEN` in the environment.

Usage examples:

```powershell
python .\scripts\push_and_wait.py
python .\scripts\push_and_wait.py --branch feature/serve-ws-test
```

Exit codes mirror the underlying wait helpers (0 = success, non-zero = failure).

Oscilloscope Test Scripts
--------------------------

test_oscilloscope_connection.py
--------------------------------

Unified test script to discover and connect to oscilloscope via LAN (preferred) or USB (fallback).

This script automatically:
1. First checks for LAN/TCPIP connections (preferred method)
2. Falls back to USB/USBTMC connections if LAN is not available
3. Tests the connection and reports which type was used

Usage:
```bash
# Auto-discover (LAN preferred, USB fallback)
python scripts/test_oscilloscope_connection.py

# Force LAN with specific IP
python scripts/test_oscilloscope_connection.py --ip 192.168.1.100

# USB only (skip LAN check)
python scripts/test_oscilloscope_connection.py --usb-only

# Custom port for LAN
python scripts/test_oscilloscope_connection.py --ip 192.168.1.100 --port 5555
```

Requirements:
- PyVISA and PyVISA-py installed (`pip install PyVISA PyVISA-py`)
- For LAN: Oscilloscope with SCPI over LAN enabled, network connectivity
- For USB: USB device connected and recognized by the system

The script will:
- Display connection type (LAN_AUTO, LAN_MANUAL, or USB)
- Query device identification (*IDN?)
- Test basic SCPI communication
- Provide troubleshooting information if connection fails

test_lan_oscilloscope.py
------------------------

Legacy script for LAN-only oscilloscope connections. For unified LAN/USB testing,
use `test_oscilloscope_connection.py` instead.

This script only checks for TCPIP/LAN connections and does not fall back to USB.

Usage:
```bash
# Auto-discover LAN connections
python scripts/test_lan_oscilloscope.py

# Connect to specific IP
python scripts/test_lan_oscilloscope.py --ip 192.168.1.100
```

test_scpi_commands_lan.py
-------------------------

Comprehensive test script to verify all SCPI commands used in the codebase via LAN.

This script tests all 19 SCPI commands found in the codebase, organized into 10 categories:
1. Standard SCPI Commands (*IDN?, *RST, *STOP)
2. Trigger Mode Commands (TRMD AUTO, TRMD?)
3. Timebase Commands (TDIV, TDIV?)
4. Channel Trace Commands (C{ch}:TRA ON/OFF, C{ch}:TRA?)
5. Channel Probe Attenuation (C{ch}:ATTN?)
6. Channel Vertical Division (C{ch}:VDIV, C{ch}:VDIV?)
7. Channel Vertical Offset (C{ch}:OFST, C{ch}:OFST?)
8. PAVA MEAN Commands (C{ch}:PAVA? MEAN)
9. Waveform Commands (C{ch}:WF? ALL)
10. Run/Stop Commands (RUN, STOP)

Usage:
```bash
# Auto-discover LAN connection and test all commands
python scripts/test_scpi_commands_lan.py

# Connect to specific IP and test
python scripts/test_scpi_commands_lan.py --ip 192.168.1.100

# Custom port
python scripts/test_scpi_commands_lan.py --ip 192.168.1.100 --port 5555
```

The script will:
- Connect to oscilloscope via LAN
- Test each SCPI command category
- Verify responses and parse values where applicable
- Provide detailed output for each command
- Generate a summary report with success/failure counts

For a complete reference of all SCPI commands, see: `docs/SCPI_COMMANDS_REFERENCE.md`
