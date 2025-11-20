#!/usr/bin/env python3
"""
Test script to discover and connect to oscilloscope via LAN/Ethernet.

NOTE: For a unified test script that checks both LAN (preferred) and USB (fallback)
      connections, use: scripts/test_oscilloscope_connection.py

This script:
1. Scans for TCPIP oscilloscope resources
2. Connects to the first available device (or manually specified IP)
3. Queries device identification
4. Waits 3 seconds
5. Closes connection cleanly

Usage:
    # Auto-discover and connect
    python scripts/test_lan_oscilloscope.py
    
    # Connect to specific IP address
    python scripts/test_lan_oscilloscope.py --ip 192.168.1.100
    
    # Specify custom port (default: 5555)
    python scripts/test_lan_oscilloscope.py --ip 192.168.1.100 --port 5555

Requirements:
    - PyVISA and PyVISA-py installed
    - Oscilloscope with SCPI over LAN enabled
    - Network connectivity to oscilloscope
"""

import sys
import os
import time
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def main():
    """Main function to discover and connect to LAN oscilloscope."""
    parser = argparse.ArgumentParser(
        description='Discover and connect to oscilloscope via LAN',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--ip', type=str, help='IP address of oscilloscope (manual connection)')
    parser.add_argument('--port', type=int, default=5555, help='Port for TCPIP connection (default: 5555)')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("LAN Oscilloscope Discovery and Connection Test")
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
    device_info = None
    
    if args.ip:
        # Manual IP connection
        resource = f"TCPIP::{args.ip}::{args.port}::INSTR"
        print(f"Connecting to manually specified IP: {args.ip}:{args.port}")
        print(f"Resource string: {resource}")
    else:
        # Auto-discover TCPIP resources
        print("Scanning for TCPIP oscilloscope resources...")
        print("-" * 70)
        
        try:
            all_resources = rm.list_resources()
            print(f"Found {len(all_resources)} total resource(s)")
            
            # Filter for TCPIP resources
            tcpip_resources = [r for r in all_resources if r.startswith('TCPIP') and '::' in r]
            
            if not tcpip_resources:
                print("\n⚠ No TCPIP resources found via auto-discovery")
                print("\nPlease specify IP address manually:")
                print("  python scripts/test_lan_oscilloscope.py --ip <ip_address>")
                print("\nOr ensure:")
                print("  1. Oscilloscope SCPI over LAN is enabled")
                print("  2. Oscilloscope is on the same network")
                print("  3. Firewall allows connections on port 5555")
                return 1
            
            print(f"Found {len(tcpip_resources)} TCPIP resource(s):")
            for i, res in enumerate(tcpip_resources, 1):
                print(f"  {i}. {res}")
            
            # Use first TCPIP resource
            resource = tcpip_resources[0]
            print(f"\nUsing first TCPIP resource: {resource}")
            
        except Exception as e:
            print(f"✗ Failed to list resources: {e}")
            return 1
    
    # Connect to oscilloscope
    print("\n" + "-" * 70)
    print("Connecting to oscilloscope...")
    print("-" * 70)
    
    device = None
    try:
        device = rm.open_resource(resource)
        device.timeout = 5000  # 5 second timeout for network
        
        print(f"✓ Connection opened: {resource}")
        
        # Query device identification
        print("\nQuerying device identification...")
        try:
            idn = device.query('*IDN?')
            print(f"✓ Device identification received:")
            print(f"  {idn.strip()}")
            
            # Parse IDN
            parts = idn.split(',')
            if len(parts) >= 4:
                print(f"\n  Manufacturer: {parts[0].strip()}")
                print(f"  Model: {parts[1].strip()}")
                print(f"  Serial: {parts[2].strip()}")
                print(f"  Version: {parts[3].strip()}")
            
            device_info = idn.strip()
            
        except Exception as e:
            print(f"⚠ IDN query failed: {e}")
            print("  Connection established but device may not respond to *IDN?")
        
        # Wait 3 seconds
        print("\n" + "-" * 70)
        print("Connection established. Waiting 3 seconds...")
        print("-" * 70)
        
        for i in range(3, 0, -1):
            print(f"  Closing in {i} second(s)...", end='\r')
            time.sleep(1)
        print("  Closing connection...        ")
        
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
        # Clean disconnect
        if device is not None:
            print("\n" + "-" * 70)
            print("Closing connection...")
            print("-" * 70)
            try:
                device.close()
                print("✓ Connection closed cleanly")
            except Exception as e:
                print(f"⚠ Error during close: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"  Resource: {resource}")
    if device_info:
        print(f"  Device: {device_info}")
    print(f"  Status: Connection test completed successfully")
    print()
    
    return 0

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

