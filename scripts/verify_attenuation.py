#!/usr/bin/env python3
"""
Verify oscilloscope CH1 and CH2 probe attenuation equals 811.97 and trace is displayed.

This script:
- Scans for USBTMC oscilloscopes via OscilloscopeService
- Connects to the first available device
- Queries C1:ATTN? and C2:ATTN? to verify attenuation
- Queries C1:TRA? and C2:TRA? to verify trace is displayed (ON)
- Compares readback to target values
- Prints results and exits non-zero on mismatch or errors
"""

import sys
import os
import time
import re


def main() -> int:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    services_path = os.path.join(repo_root, 'host_gui', 'services')
    sys.path.insert(0, services_path)

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('oscilloscope_service', os.path.join(services_path, 'oscilloscope_service.py'))
        osc_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(osc_module)  # type: ignore
        Service = getattr(osc_module, 'OscilloscopeService')
    except Exception as e:
        print(f"ERROR: Failed to import OscilloscopeService: {e}")
        return 2

    service = Service()

    try:
        print("Scanning for devices...")
        devices = service.scan_for_devices()
        if not devices:
            print("ERROR: No USBTMC devices found")
            return 2

        target = devices[0]
        print(f"Connecting to: {target}")
        if not service.connect(target):
            print("ERROR: Failed to connect to oscilloscope")
            return 2

        # Small delay to let I/O settle
        time.sleep(0.2)

        # Confirm identity
        idn = service.send_command("*IDN?")
        print(f"*IDN?: {idn}")

        def query_atten(channel_num: int, retries: int = 3, delay_s: float = 0.25):
            """Query attenuation using C1:ATTN? format."""
            cmd = f"C{channel_num}:ATTN?"
            
            print(f"\n  Querying {cmd}...")
            last_err = None
            for _ in range(retries):
                try:
                    time.sleep(delay_s)
                    resp = service.send_command(cmd)
                    if resp is None:
                        last_err = RuntimeError("No response")
                        continue
                    print(f"    Raw response: {repr(resp)}")
                    
                    # Parse response - extract number after "ATTN "
                    s = resp.strip()
                    attn_match = re.search(r'ATTN\s+([\d.]+)', s, re.IGNORECASE)
                    if attn_match:
                        value = float(attn_match.group(1))
                        print(f"  Parsed: {value}")
                        return value
                    else:
                        # Fallback: find all numbers and take the last one (avoiding channel number)
                        all_numbers = re.findall(r'([\d.]+)', s)
                        if all_numbers:
                            # Take the last number (should be the attenuation value)
                            value = float(all_numbers[-1])
                            print(f"  Parsed: {value}")
                            return value
                        else:
                            value = float(s)
                            print(f"  Parsed: {value}")
                            return value
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    time.sleep(delay_s)
            raise RuntimeError(f"Failed to query {cmd}: {last_err}")

        def query_trace(channel_num: int, retries: int = 3, delay_s: float = 0.25):
            """Query trace display status using C1:TRA? format."""
            cmd = f"C{channel_num}:TRA?"
            
            print(f"\n  Querying {cmd}...")
            last_err = None
            for _ in range(retries):
                try:
                    time.sleep(delay_s)
                    resp = service.send_command(cmd)
                    if resp is None:
                        last_err = RuntimeError("No response")
                        continue
                    print(f"    Raw response: {repr(resp)}")
                    
                    # Parse response - expect ON/OFF or 1/0
                    s = resp.strip()
                    # Check if response contains ON, OFF, 1, or 0
                    s_upper = s.upper()
                    if 'ON' in s_upper or s_upper == '1' or 'TRUE' in s_upper:
                        value = True
                    elif 'OFF' in s_upper or s_upper == '0' or 'FALSE' in s_upper:
                        value = False
                    else:
                        # Try to extract from formats like "C1:TRA ON" or "C1:TRA 1"
                        tra_match = re.search(r'TRA\s+(\w+)', s, re.IGNORECASE)
                        if tra_match:
                            tra_val = tra_match.group(1).upper()
                            value = tra_val in ['ON', '1', 'TRUE']
                        else:
                            # Default: try to parse as boolean from the string
                            value = s_upper in ['ON', '1', 'TRUE']
                    print(f"  Parsed: {value}")
                    return value
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    time.sleep(delay_s)
            raise RuntimeError(f"Failed to query {cmd}: {last_err}")

        target_value = 811.97
        tolerance = 0.02  # acceptable absolute tolerance

        print("\n=== Verifying Attenuation ===")
        ch1_atten = query_atten(1)
        print(f"C1:ATTN? -> {ch1_atten}")
        ch2_atten = query_atten(2)
        print(f"C2:ATTN? -> {ch2_atten}")

        print("\n=== Verifying Trace Display ===")
        ch1_trace = query_trace(1)
        print(f"C1:TRA? -> {ch1_trace} ({'ON' if ch1_trace else 'OFF'})")
        ch2_trace = query_trace(2)
        print(f"C2:TRA? -> {ch2_trace} ({'ON' if ch2_trace else 'OFF'})")

        # Check results
        atten_ok1 = abs(ch1_atten - target_value) <= tolerance
        atten_ok2 = abs(ch2_atten - target_value) <= tolerance
        trace_ok1 = ch1_trace is True
        trace_ok2 = ch2_trace is True

        all_ok = atten_ok1 and atten_ok2 and trace_ok1 and trace_ok2

        print("\n=== Results ===")
        if all_ok:
            print("RESULT: PASS - All verifications passed")
            print(f"  - CH1 attenuation: {ch1_atten} (expected {target_value})")
            print(f"  - CH2 attenuation: {ch2_atten} (expected {target_value})")
            print(f"  - CH1 trace: {'ON' if ch1_trace else 'OFF'} (expected ON)")
            print(f"  - CH2 trace: {'ON' if ch2_trace else 'OFF'} (expected ON)")
            return 0
        else:
            print("RESULT: FAIL - Some verifications failed")
            if not atten_ok1:
                print(f"  - CH1 attenuation mismatch: expected {target_value}, got {ch1_atten}")
            if not atten_ok2:
                print(f"  - CH2 attenuation mismatch: expected {target_value}, got {ch2_atten}")
            if not trace_ok1:
                print(f"  - CH1 trace not displayed: expected ON, got {'ON' if ch1_trace else 'OFF'}")
            if not trace_ok2:
                print(f"  - CH2 trace not displayed: expected ON, got {'ON' if ch2_trace else 'OFF'}")
            return 1

    finally:
        try:
            if 'service' in locals():
                service.cleanup()
                print("Disconnected and cleaned up")
        except Exception as e:  # noqa: BLE001
            print(f"WARN: Cleanup issue: {e}")


if __name__ == '__main__':
    raise SystemExit(main())


