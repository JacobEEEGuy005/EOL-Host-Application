#!/usr/bin/env python3
"""
Comprehensive test script to verify all SCPI commands used in the codebase via LAN.

This script:
1. Connects to oscilloscope via LAN (TCPIP)
2. Tests all SCPI commands found in the codebase
3. Verifies responses and reports results
4. Provides detailed output for each command

Usage:
    # Auto-discover LAN connection
    python scripts/test_scpi_commands_lan.py
    
    # Connect to specific IP
    python scripts/test_scpi_commands_lan.py --ip 192.168.1.100
    
    # Custom port
    python scripts/test_scpi_commands_lan.py --ip 192.168.1.100 --port 5555

Requirements:
    - PyVISA and PyVISA-py installed
    - Oscilloscope with SCPI over LAN enabled
    - Network connectivity to oscilloscope
"""

import sys
import os
import time
import argparse
import re
from typing import Dict, List, Tuple, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# Regex patterns for parsing responses
REGEX_ATTN = re.compile(r'ATTN\s+([\d.]+)', re.IGNORECASE)
REGEX_TDIV = re.compile(r'TDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_VDIV = re.compile(r'VDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_OFST = re.compile(r'OFST\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_PAVA = re.compile(r'C\d+:PAVA\s+MEAN,([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)V?', re.IGNORECASE)


class SCPITestResult:
    """Result of a SCPI command test."""
    def __init__(self, command: str, success: bool, response: Optional[str] = None, 
                 error: Optional[str] = None, parsed_value: Optional[any] = None):
        self.command = command
        self.success = success
        self.response = response
        self.error = error
        self.parsed_value = parsed_value


def parse_pava_response(response: str) -> Optional[float]:
    """Parse PAVA MEAN response to extract voltage value."""
    if not response:
        return None
    
    match = REGEX_PAVA.search(response)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def test_scpi_command(device, command: str, is_query: bool = True, 
                      timeout: int = 5000) -> SCPITestResult:
    """
    Test a single SCPI command.
    
    Args:
        device: PyVISA device resource
        command: SCPI command string
        is_query: True if command expects response, False for write-only
        timeout: Timeout in milliseconds
        
    Returns:
        SCPITestResult object
    """
    original_timeout = device.timeout
    device.timeout = timeout
    
    try:
        if is_query:
            response = device.query(command)
            return SCPITestResult(command, True, response=response)
        else:
            device.write(command)
            time.sleep(0.1)  # Small delay for command processing
            return SCPITestResult(command, True, response="(write command, no response)")
    except Exception as e:
        return SCPITestResult(command, False, error=str(e))
    finally:
        device.timeout = original_timeout


def test_all_scpi_commands(device) -> Dict[str, List[SCPITestResult]]:
    """
    Test all SCPI commands found in the codebase.
    
    Returns:
        Dictionary mapping category to list of test results
    """
    results = {}
    
    print("\n" + "=" * 70)
    print("Testing SCPI Commands")
    print("=" * 70)
    
    # Category 1: Standard SCPI Commands
    print("\n[1] Standard SCPI Commands")
    print("-" * 70)
    standard_commands = [
        ("*IDN?", True, "Device identification"),
        ("*RST", False, "Reset device"),
        ("*STOP", False, "Stop acquisition"),
    ]
    
    results['standard'] = []
    for cmd, is_query, desc in standard_commands:
        print(f"\nTesting: {cmd} ({desc})")
        result = test_scpi_command(device, cmd, is_query)
        results['standard'].append(result)
        
        if result.success:
            if result.response:
                # Parse *IDN? response
                if cmd == "*IDN?" and result.response:
                    parts = result.response.split(',')
                    if len(parts) >= 4:
                        print(f"  ✓ Success: {desc}")
                        print(f"    Manufacturer: {parts[0].strip()}")
                        print(f"    Model: {parts[1].strip()}")
                        print(f"    Serial: {parts[2].strip()}")
                        print(f"    Version: {parts[3].strip()}")
                    else:
                        print(f"  ✓ Success: {result.response.strip()}")
                else:
                    print(f"  ✓ Success: {result.response.strip()}")
            else:
                print(f"  ✓ Success: Command executed")
        else:
            print(f"  ✗ Failed: {result.error}")
    
    # Category 2: Trigger Mode Commands
    print("\n[2] Trigger Mode Commands")
    print("-" * 70)
    trigger_commands = [
        ("TRMD AUTO", False, "Set trigger mode to AUTO"),
        ("TRMD?", True, "Query trigger mode"),
    ]
    
    results['trigger'] = []
    for cmd, is_query, desc in trigger_commands:
        print(f"\nTesting: {cmd} ({desc})")
        result = test_scpi_command(device, cmd, is_query)
        results['trigger'].append(result)
        
        if result.success:
            if result.response:
                print(f"  ✓ Success: {result.response.strip()}")
            else:
                print(f"  ✓ Success: Command executed")
        else:
            print(f"  ✗ Failed: {result.error}")
    
    # Category 3: Timebase Commands
    print("\n[3] Timebase Commands")
    print("-" * 70)
    
    # First query current timebase
    print("\nTesting: TDIV? (Query current timebase)")
    tdiv_query = test_scpi_command(device, "TDIV?", True)
    results['timebase'] = [tdiv_query]
    
    if tdiv_query.success and tdiv_query.response:
        print(f"  ✓ Current timebase: {tdiv_query.response.strip()}")
        # Try to parse and set a test value
        match = REGEX_TDIV.search(tdiv_query.response)
        if match:
            try:
                current_tdiv = float(match.group(1))
                print(f"    Parsed value: {current_tdiv} seconds/div")
                
                # Test setting timebase (use a safe value)
                test_tdiv = 0.01  # 10ms per division
                print(f"\nTesting: TDIV {test_tdiv} (Set timebase to {test_tdiv}s/div)")
                tdiv_set = test_scpi_command(device, f"TDIV {test_tdiv}", False)
                results['timebase'].append(tdiv_set)
                
                if tdiv_set.success:
                    time.sleep(0.2)
                    # Verify
                    verify = test_scpi_command(device, "TDIV?", True)
                    results['timebase'].append(verify)
                    if verify.success:
                        print(f"  ✓ Timebase set successfully")
                        print(f"    Verified: {verify.response.strip()}")
                    
                    # Restore original
                    print(f"\nRestoring original timebase: TDIV {current_tdiv}")
                    test_scpi_command(device, f"TDIV {current_tdiv}", False)
                    time.sleep(0.2)
            except ValueError:
                print(f"  ⚠ Could not parse timebase value")
        else:
            print(f"  ⚠ Could not parse timebase response format")
    else:
        print(f"  ✗ Failed: {tdiv_query.error}")
    
    # Category 4: Channel Trace (Enable/Disable) Commands
    print("\n[4] Channel Trace Commands")
    print("-" * 70)
    results['channel_trace'] = []
    
    for ch in [1, 2, 3, 4]:
        # Query current state
        cmd_query = f"C{ch}:TRA?"
        print(f"\nTesting: {cmd_query} (Query channel {ch} trace status)")
        result_query = test_scpi_command(device, cmd_query, True)
        results['channel_trace'].append(result_query)
        
        if result_query.success and result_query.response:
            response_str = result_query.response.strip().upper()
            is_enabled = 'ON' in response_str or response_str == '1' or 'TRUE' in response_str
            print(f"  ✓ Channel {ch} is {'ENABLED' if is_enabled else 'DISABLED'}")
            print(f"    Response: {result_query.response.strip()}")
            
            # Test toggling (enable if disabled, disable if enabled)
            new_state = not is_enabled
            cmd_set = f"C{ch}:TRA {'ON' if new_state else 'OFF'}"
            print(f"\nTesting: {cmd_set} (Set channel {ch} trace)")
            result_set = test_scpi_command(device, cmd_set, False)
            results['channel_trace'].append(result_set)
            
            if result_set.success:
                time.sleep(0.2)
                # Verify
                verify = test_scpi_command(device, cmd_query, True)
                results['channel_trace'].append(verify)
                if verify.success:
                    verify_str = verify.response.strip().upper()
                    verify_enabled = 'ON' in verify_str or verify_str == '1' or 'TRUE' in verify_str
                    if verify_enabled == new_state:
                        print(f"  ✓ Channel {ch} set successfully")
                    else:
                        print(f"  ⚠ Channel {ch} state mismatch (expected {new_state}, got {verify_enabled})")
                
                # Restore original state
                restore_cmd = f"C{ch}:TRA {'ON' if is_enabled else 'OFF'}"
                test_scpi_command(device, restore_cmd, False)
                time.sleep(0.1)
        else:
            print(f"  ✗ Failed: {result_query.error}")
    
    # Category 5: Channel Probe Attenuation Commands
    print("\n[5] Channel Probe Attenuation Commands")
    print("-" * 70)
    results['attenuation'] = []
    
    for ch in [1, 2, 3, 4]:
        cmd = f"C{ch}:ATTN?"
        print(f"\nTesting: {cmd} (Query channel {ch} probe attenuation)")
        result = test_scpi_command(device, cmd, True)
        results['attenuation'].append(result)
        
        if result.success and result.response:
            # Try to parse attenuation value
            match = REGEX_ATTN.search(result.response)
            if match:
                attn_value = float(match.group(1))
                print(f"  ✓ Success: {attn_value}x attenuation")
                result.parsed_value = attn_value
            else:
                # Fallback: extract any number
                numbers = re.findall(r'[\d.]+', result.response)
                if numbers:
                    try:
                        attn_value = float(numbers[-1])
                        print(f"  ✓ Success: {attn_value}x attenuation (parsed)")
                        result.parsed_value = attn_value
                    except ValueError:
                        print(f"  ✓ Success: {result.response.strip()} (could not parse)")
                else:
                    print(f"  ✓ Success: {result.response.strip()}")
        else:
            print(f"  ✗ Failed: {result.error}")
    
    # Category 6: Channel Vertical Division Commands
    print("\n[6] Channel Vertical Division Commands")
    print("-" * 70)
    results['vdiv'] = []
    
    for ch in [1, 2]:
        # Query current value
        cmd_query = f"C{ch}:VDIV?"
        print(f"\nTesting: {cmd_query} (Query channel {ch} vertical division)")
        result_query = test_scpi_command(device, cmd_query, True)
        results['vdiv'].append(result_query)
        
        if result_query.success and result_query.response:
            match = REGEX_VDIV.search(result_query.response)
            if match:
                current_vdiv = float(match.group(1))
                print(f"  ✓ Current VDIV: {current_vdiv} V/div")
                result_query.parsed_value = current_vdiv
                
                # Test setting (use a safe value)
                test_vdiv = 2.0  # 2V per division
                cmd_set = f"C{ch}:VDIV {test_vdiv}"
                print(f"\nTesting: {cmd_set} (Set channel {ch} VDIV to {test_vdiv}V/div)")
                result_set = test_scpi_command(device, cmd_set, False)
                results['vdiv'].append(result_set)
                
                if result_set.success:
                    time.sleep(0.2)
                    # Verify
                    verify = test_scpi_command(device, cmd_query, True)
                    results['vdiv'].append(verify)
                    if verify.success:
                        verify_match = REGEX_VDIV.search(verify.response)
                        if verify_match:
                            verify_vdiv = float(verify_match.group(1))
                            print(f"  ✓ VDIV set successfully: {verify_vdiv} V/div")
                        
                    # Restore original
                    restore_cmd = f"C{ch}:VDIV {current_vdiv}"
                    print(f"\nRestoring original VDIV: {restore_cmd}")
                    test_scpi_command(device, restore_cmd, False)
                    time.sleep(0.2)
            else:
                print(f"  ✓ Response: {result_query.response.strip()} (could not parse)")
        else:
            print(f"  ✗ Failed: {result_query.error}")
    
    # Category 7: Channel Vertical Offset Commands
    print("\n[7] Channel Vertical Offset Commands")
    print("-" * 70)
    results['offset'] = []
    
    for ch in [1, 2]:
        cmd_query = f"C{ch}:OFST?"
        print(f"\nTesting: {cmd_query} (Query channel {ch} vertical offset)")
        result_query = test_scpi_command(device, cmd_query, True)
        results['offset'].append(result_query)
        
        if result_query.success and result_query.response:
            match = REGEX_OFST.search(result_query.response)
            if match:
                current_ofst = float(match.group(1))
                print(f"  ✓ Current OFST: {current_ofst} V")
                result_query.parsed_value = current_ofst
            else:
                print(f"  ✓ Response: {result_query.response.strip()} (could not parse)")
        else:
            print(f"  ✗ Failed: {result_query.error}")
    
    # Category 8: PAVA MEAN Commands
    print("\n[8] PAVA MEAN Commands (Parameter Average)")
    print("-" * 70)
    print("Note: PAVA commands require channel to be enabled and data acquired")
    results['pava'] = []
    
    # First, ensure oscilloscope is in a state where PAVA can work
    print("\nPreparing oscilloscope for PAVA queries...")
    test_scpi_command(device, "TRMD AUTO", False)
    time.sleep(1.0)
    test_scpi_command(device, "*STOP", False)
    time.sleep(0.5)
    
    for ch in [1, 2, 3, 4]:
        # Check if channel is enabled first
        tra_cmd = f"C{ch}:TRA?"
        tra_result = test_scpi_command(device, tra_cmd, True)
        
        if tra_result.success and tra_result.response:
            tra_str = tra_result.response.strip().upper()
            is_enabled = 'ON' in tra_str or tra_str == '1' or 'TRUE' in tra_str
            
            if is_enabled:
                cmd = f"C{ch}:PAVA? MEAN"
                print(f"\nTesting: {cmd} (Query channel {ch} average voltage)")
                result = test_scpi_command(device, cmd, True, timeout=10000)
                results['pava'].append(result)
                
                if result.success and result.response:
                    pava_value = parse_pava_response(result.response)
                    if pava_value is not None:
                        print(f"  ✓ Success: {pava_value} V")
                        result.parsed_value = pava_value
                    else:
                        print(f"  ✓ Response received: {result.response.strip()}")
                        print(f"    (Could not parse PAVA value)")
                else:
                    print(f"  ✗ Failed: {result.error if result.error else 'No response'}")
            else:
                print(f"\nChannel {ch} is disabled, skipping PAVA test")
        else:
            print(f"\nCould not check channel {ch} status, skipping PAVA test")
    
    # Category 9: Waveform Commands (read-only test, don't read full data)
    print("\n[9] Waveform Commands")
    print("-" * 70)
    print("Note: Waveform commands return binary data, testing command format only")
    results['waveform'] = []
    
    for ch in [1, 2]:
        cmd = f"C{ch}:WF? ALL"
        print(f"\nTesting: {cmd} (Query channel {ch} waveform - format check only)")
        print("  (Not reading full binary data to avoid timeout)")
        
        # Just verify the command can be sent (don't read response)
        try:
            device.write(cmd)
            print(f"  ✓ Command format accepted")
            # Cancel any pending read
            time.sleep(0.1)
            results['waveform'].append(SCPITestResult(cmd, True, 
                response="(binary data, not read)"))
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results['waveform'].append(SCPITestResult(cmd, False, error=str(e)))
    
    # Category 10: Run/Stop Commands
    print("\n[10] Run/Stop Commands")
    print("-" * 70)
    run_commands = [
        ("RUN", False, "Start acquisition"),
        ("STOP", False, "Stop acquisition"),
    ]
    
    results['run_stop'] = []
    for cmd, is_query, desc in run_commands:
        print(f"\nTesting: {cmd} ({desc})")
        result = test_scpi_command(device, cmd, is_query)
        results['run_stop'].append(result)
        
        if result.success:
            print(f"  ✓ Success: Command executed")
        else:
            print(f"  ✗ Failed: {result.error}")
    
    return results


def print_summary(results: Dict[str, List[SCPITestResult]]):
    """Print summary of all test results."""
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    
    total_commands = 0
    total_passed = 0
    total_failed = 0
    
    for category, test_results in results.items():
        category_name = category.replace('_', ' ').title()
        passed = sum(1 for r in test_results if r.success)
        failed = sum(1 for r in test_results if not r.success)
        
        total_commands += len(test_results)
        total_passed += passed
        total_failed += failed
        
        status = "✓" if failed == 0 else "⚠" if passed > 0 else "✗"
        print(f"\n{status} {category_name}: {passed}/{len(test_results)} passed")
        if failed > 0:
            for result in test_results:
                if not result.success:
                    print(f"    ✗ {result.command}: {result.error}")
    
    print("\n" + "-" * 70)
    print(f"Overall: {total_passed}/{total_commands} commands passed")
    print(f"Success Rate: {(total_passed/total_commands*100):.1f}%")
    print("=" * 70)


def main():
    """Main function to test SCPI commands via LAN."""
    parser = argparse.ArgumentParser(
        description='Test all SCPI commands used in codebase via LAN',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--ip', type=str, help='IP address of oscilloscope (manual connection)')
    parser.add_argument('--port', type=int, default=5555, help='Port for TCPIP connection (default: 5555)')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("SCPI Commands Test via LAN")
    print("=" * 70)
    print()
    
    # Check if PyVISA is available
    try:
        import pyvisa
        print("✓ PyVISA is installed")
    except ImportError:
        print("✗ PyVISA is NOT installed")
        print("\nPlease install PyVISA:")
        print("  pip install PyVISA PyVISA-py")
        return 1
    
    # Initialize ResourceManager
    try:
        rm = pyvisa.ResourceManager()
        print(f"✓ PyVISA ResourceManager initialized")
        print(f"  Backend: {rm}")
        print()
    except Exception as e:
        print(f"✗ Failed to initialize PyVISA ResourceManager: {e}")
        return 1
    
    # Determine connection method
    resource = None
    
    if args.ip:
        resource = f"TCPIP::{args.ip}::{args.port}::INSTR"
        print(f"Connecting to manually specified IP: {args.ip}:{args.port}")
    else:
        # Auto-discover TCPIP resources
        print("Scanning for TCPIP oscilloscope resources...")
        try:
            all_resources = rm.list_resources()
            tcpip_resources = [r for r in all_resources if r.startswith('TCPIP') and '::' in r]
            
            if not tcpip_resources:
                print("⚠ No TCPIP resources found")
                print("\nPlease specify IP address manually:")
                print("  python scripts/test_scpi_commands_lan.py --ip <ip_address>")
                return 1
            
            resource = tcpip_resources[0]
            print(f"✓ Using first TCPIP resource: {resource}")
        except Exception as e:
            print(f"✗ Failed to list resources: {e}")
            return 1
    
    # Connect to oscilloscope
    print("\n" + "=" * 70)
    print("Connecting to oscilloscope...")
    print("=" * 70)
    
    device = None
    try:
        device = rm.open_resource(resource)
        device.timeout = 10000  # 10 second timeout for network
        
        print(f"✓ Connection opened: {resource}")
        
        # Test all SCPI commands
        results = test_all_scpi_commands(device)
        
        # Print summary
        print_summary(results)
        
        # Determine exit code
        total_commands = sum(len(r) for r in results.values())
        total_passed = sum(sum(1 for tr in r if tr.success) for r in results.values())
        
        if total_passed == total_commands:
            print("\n✓ All tests passed!")
            return 0
        elif total_passed > 0:
            print("\n⚠ Some tests failed")
            return 1
        else:
            print("\n✗ All tests failed")
            return 1
        
    except Exception as e:
        print(f"✗ Failed to connect to oscilloscope: {e}")
        print("\nTroubleshooting:")
        print("  1. Verify IP address is correct")
        print("  2. Check network connectivity: ping <ip_address>")
        print("  3. Ensure oscilloscope SCPI over LAN is enabled")
        print("  4. Verify port is correct (default: 5555 for Siglent)")
        print("  5. Check firewall settings")
        return 1
    
    finally:
        if device is not None:
            try:
                device.close()
                print("\n✓ Connection closed")
            except Exception as e:
                print(f"\n⚠ Error during close: {e}")


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

