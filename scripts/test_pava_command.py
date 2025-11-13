#!/usr/bin/env python3
"""
Test script to verify C{ch}:PAVA? MEAN command format.

This script:
- Scans for USBTMC oscilloscopes via OscilloscopeService
- Connects to the first available device
- Tests C{ch}:PAVA? MEAN command for channels 1-4
- Parses the response format: "C4:PAVA MEAN,9.040000E+00V"
- Extracts the mean value in volts
"""

import sys
import os
import time
import re


def parse_pava_response(response: str) -> tuple[float, str]:
    """Parse PAVA response to extract mean value.
    
    Expected format: "C4:PAVA MEAN,9.040000E+00V"
    
    Args:
        response: Raw response string from oscilloscope
        
    Returns:
        Tuple of (mean_value_volts, error_message)
        If parsing fails, returns (None, error_message)
    """
    if not response:
        return None, "Empty response"
    
    response = response.strip()
    
    # Pattern: C{ch}:PAVA MEAN,{value}V
    # Value can be in scientific notation: 9.040000E+00 or 9.04E+00 or 9.04
    pattern = r'C\d+:PAVA\s+MEAN,([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)V?'
    match = re.search(pattern, response, re.IGNORECASE)
    
    if match:
        try:
            value_str = match.group(1)
            value = float(value_str)
            return value, None
        except ValueError as e:
            return None, f"Failed to convert value '{value_str}' to float: {e}"
    
    # Fallback: try to extract any number followed by V
    pattern_fallback = r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*V'
    match_fallback = re.search(pattern_fallback, response, re.IGNORECASE)
    if match_fallback:
        try:
            value_str = match_fallback.group(1)
            value = float(value_str)
            return value, None
        except ValueError as e:
            return None, f"Failed to convert fallback value '{value_str}' to float: {e}"
    
    return None, f"Could not parse PAVA response: {response}"


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

        def query_pava(channel_num: int, retries: int = 3, delay_s: float = 0.5):
            """Query PAVA MEAN using C{ch}:PAVA? MEAN format."""
            cmd = f"C{channel_num}:PAVA? MEAN"
            
            print(f"  Querying {cmd}...")
            last_err = None
            last_resp = None
            for attempt in range(retries):
                try:
                    time.sleep(delay_s)
                    resp = service.send_command(cmd)
                    last_resp = resp
                    if resp is None:
                        last_err = RuntimeError("No response (None returned)")
                        print(f"    Attempt {attempt + 1}/{retries}: No response")
                        if attempt < retries - 1:
                            continue
                        else:
                            print(f"  ERROR: No response after {retries} attempts")
                            return None
                    
                    print(f"    Raw response (attempt {attempt + 1}): {repr(resp)}")
                    
                    # Check if response is empty or just whitespace
                    if not resp or not resp.strip():
                        last_err = RuntimeError("Empty response")
                        print(f"    Attempt {attempt + 1}/{retries}: Empty response")
                        if attempt < retries - 1:
                            continue
                        else:
                            print(f"  ERROR: Empty response after {retries} attempts")
                            return None
                    
                    # Parse response
                    value, error = parse_pava_response(resp)
                    if error:
                        if attempt < retries - 1:
                            last_err = RuntimeError(error)
                            print(f"    Attempt {attempt + 1}/{retries}: Parse error - {error}")
                            continue
                        else:
                            print(f"  ERROR: {error}")
                            return None
                    
                    print(f"  ✓ Parsed mean value: {value} V")
                    return value
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    print(f"    Attempt {attempt + 1}/{retries}: Exception - {e}")
                    if attempt < retries - 1:
                        time.sleep(delay_s)
                    else:
                        print(f"  ERROR: Exception after {retries} attempts: {e}")
            
            # Final error message with last response
            error_msg = f"Failed to query {cmd} after {retries} attempts"
            if last_err:
                error_msg += f": {last_err}"
            if last_resp is not None:
                error_msg += f" (last response: {repr(last_resp)})"
            print(f"  ERROR: {error_msg}")
            return None

        print("\n=== Testing PAVA MEAN Command ===")
        print("Note: Channel must be enabled and have signal for valid measurement")
        
        # Check oscilloscope run state
        print("\n=== Checking Oscilloscope State ===")
        try:
            # Check if oscilloscope is running or stopped
            # Some oscilloscopes use TRMD? to check trigger mode
            trmd_resp = service.send_command("TRMD?")
            print(f"TRMD? (Trigger Mode): {trmd_resp}")
            
            # Try to check run state (some scopes use :RUN? or :STOP?)
            # For Siglent, we can check by trying to start/stop
            print("\nSetting oscilloscope to AUTO mode...")
            service.send_command("TRMD AUTO")
            time.sleep(0.5)
            
            print("Starting acquisition (if not already running)...")
            # Try to ensure we're in run mode
            service.send_command("TRMD AUTO")
            time.sleep(1.0)  # Wait for acquisition to start
            
            print("Waiting 2 seconds for data acquisition...")
            time.sleep(2.0)
            
            print("Stopping acquisition...")
            service.send_command("*STOP")
            time.sleep(0.5)  # Wait for stop to complete
            
        except Exception as e:
            print(f"Warning: Could not check/set oscilloscope state: {e}")
        
        results = {}
        for ch in [1, 2, 3, 4]:
            try:
                # First check if channel is enabled
                tra_cmd = f"C{ch}:TRA?"
                tra_resp = service.send_command(tra_cmd)
                if tra_resp:
                    tra_str = tra_resp.strip().upper()
                    is_enabled = 'ON' in tra_str or tra_str == '1' or 'TRUE' in tra_str
                    print(f"\nChannel {ch}: {'ENABLED' if is_enabled else 'DISABLED'}")
                    
                    if is_enabled:
                        # Try querying PAVA multiple times with different states
                        print(f"  Testing PAVA after STOP...")
                        value = query_pava(ch)
                        if value is not None:
                            results[ch] = value
                        else:
                            # Try starting acquisition again and querying
                            print(f"  Retrying: Starting acquisition and querying...")
                            service.send_command("TRMD AUTO")
                            time.sleep(1.0)
                            value = query_pava(ch)
                            if value is not None:
                                results[ch] = value
                            else:
                                # Try with RUN command
                                print(f"  Retrying: Using RUN command...")
                                try:
                                    service.send_command("RUN")
                                    time.sleep(1.0)
                                    value = query_pava(ch)
                                    results[ch] = value
                                except Exception:
                                    results[ch] = None
                    else:
                        print(f"  Skipping PAVA query for disabled channel {ch}")
                        results[ch] = None
                else:
                    print(f"\nChannel {ch}: Could not query trace status")
                    results[ch] = None
            except Exception as e:
                print(f"\nChannel {ch}: Error - {e}")
                results[ch] = None

        print("\n=== Results Summary ===")
        all_none = True
        for ch, value in results.items():
            if value is not None:
                all_none = False
                print(f"  CH{ch}: {value} V")
            else:
                print(f"  CH{ch}: No valid measurement")
        
        if all_none:
            print("\nWARNING: No valid measurements obtained. Ensure:")
            print("  - At least one channel is enabled (C{ch}:TRA ON)")
            print("  - Channel has signal connected")
            print("  - Oscilloscope is in appropriate acquisition mode")
            print("  - Data has been acquired (oscilloscope has captured waveform)")
            print("\nTroubleshooting:")
            print("  1. Try running: TRMD AUTO (to start auto trigger mode)")
            print("  2. Wait a few seconds for acquisition")
            print("  3. Then try: *STOP (to stop acquisition)")
            print("  4. Then query: C{ch}:PAVA? MEAN")
            return 1
        
        print("\nRESULT: PAVA command test completed successfully")
        print("\nNote: PAVA command typically works after:")
        print("  - Channel is enabled (C{ch}:TRA ON)")
        print("  - Acquisition has been started (TRMD AUTO or RUN)")
        print("  - Data has been captured (wait a few seconds)")
        print("  - Acquisition is stopped (*STOP)")
        print("  - Then query PAVA (C{ch}:PAVA? MEAN)")
        return 0

    finally:
        try:
            if 'service' in locals():
                service.cleanup()
                print("\nDisconnected and cleaned up")
        except Exception as e:  # noqa: BLE001
            print(f"WARN: Cleanup issue: {e}")


if __name__ == '__main__':
    raise SystemExit(main())

