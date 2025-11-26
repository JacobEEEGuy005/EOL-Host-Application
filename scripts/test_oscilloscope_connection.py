#!/usr/bin/env python3
"""
Unified test script to discover and connect to oscilloscope via LAN (preferred) or USB.

This script:
1. First scans for TCPIP/LAN oscilloscope resources (preferred method)
2. Falls back to USB/USBTMC resources if LAN is not available
3. Connects to the first available device
4. Queries device identification
5. Tests basic communication
6. Reports connection type and status

Usage:
    # Auto-discover and connect (LAN preferred, USB fallback)
    python scripts/test_oscilloscope_connection.py
    
    # Force LAN connection with specific IP
    python scripts/test_oscilloscope_connection.py --ip 192.168.1.100
    
    # Force USB connection only
    python scripts/test_oscilloscope_connection.py --usb-only
    
    # Specify custom port for LAN (default: 5555)
    python scripts/test_oscilloscope_connection.py --ip 192.168.1.100 --port 5555

Requirements:
    - PyVISA and PyVISA-py installed
    - For LAN: Oscilloscope with SCPI over LAN enabled and network connectivity
    - For USB: USB device connected and recognized by the system
"""

import sys
import os
import time
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def check_lan_connection(rm, ip=None, port=5555):
    """
    Check for LAN/TCPIP oscilloscope connections.
    
    Args:
        rm: PyVISA ResourceManager instance
        ip: Optional IP address for manual connection
        port: Port number for TCPIP connection (default: 5555)
        
    Returns:
        tuple: (resource_string, connection_type) or (None, None) if not found
    """
    print("=" * 70)
    print("Checking LAN/TCPIP Connection (Preferred Method)")
    print("=" * 70)
    print()
    
    if ip:
        # Manual IP connection
        resource = f"TCPIP::{ip}::{port}::INSTR"
        print(f"Attempting manual LAN connection to: {ip}:{port}")
        print(f"Resource string: {resource}")
        return resource, "LAN_MANUAL"
    
    # Auto-discover TCPIP resources
    print("Scanning for TCPIP oscilloscope resources...")
    print("-" * 70)
    
    try:
        all_resources = rm.list_resources()
        print(f"Found {len(all_resources)} total resource(s)")
        
        # Filter for TCPIP resources
        tcpip_resources = [r for r in all_resources if r.startswith('TCPIP') and '::' in r]
        
        if not tcpip_resources:
            print("⚠ No TCPIP resources found via auto-discovery")
            print("\nLAN connection not available.")
            return None, None
        
        print(f"Found {len(tcpip_resources)} TCPIP resource(s):")
        for i, res in enumerate(tcpip_resources, 1):
            print(f"  {i}. {res}")
        
        # Use first TCPIP resource
        resource = tcpip_resources[0]
        print(f"\n✓ Using first TCPIP resource: {resource}")
        return resource, "LAN_AUTO"
        
    except Exception as e:
        print(f"✗ Failed to list resources: {e}")
        return None, None


def check_usb_connection(rm):
    """
    Check for USB/USBTMC oscilloscope connections.
    
    Args:
        rm: PyVISA ResourceManager instance
        
    Returns:
        tuple: (resource_string, connection_type) or (None, None) if not found
    """
    print("\n" + "=" * 70)
    print("Checking USB/USBTMC Connection (Fallback Method)")
    print("=" * 70)
    print()
    
    print("Scanning for USB/USBTMC oscilloscope resources...")
    print("-" * 70)
    
    try:
        all_resources = rm.list_resources()
        print(f"Found {len(all_resources)} total resource(s)")
        
        # Filter for USB resources
        usb_resources = []
        for r in all_resources:
            # Check for USB resources (USB, USB0, USB1, etc.)
            if r.startswith('USB') and '::' in r:
                usb_resources.append(r)
        
        if not usb_resources:
            print("⚠ No USB/USBTMC resources found")
            print("\nUSB connection not available.")
            return None, None
        
        print(f"Found {len(usb_resources)} USB/USBTMC resource(s):")
        for i, res in enumerate(usb_resources, 1):
            print(f"  {i}. {res}")
        
        # Use first USB resource
        resource = usb_resources[0]
        print(f"\n✓ Using first USB resource: {resource}")
        return resource, "USB"
        
    except Exception as e:
        print(f"✗ Failed to list USB resources: {e}")
        return None, None


def test_connection(rm, resource, connection_type):
    """
    Test connection to oscilloscope and query device information.
    
    Args:
        rm: PyVISA ResourceManager instance
        resource: Resource string to connect to
        connection_type: Type of connection (LAN_AUTO, LAN_MANUAL, USB)
        
    Returns:
        tuple: (success: bool, device_info: str or None)
    """
    print("\n" + "=" * 70)
    print(f"Testing {connection_type} Connection")
    print("=" * 70)
    print()
    
    device = None
    device_info = None
    
    try:
        # Set timeout based on connection type
        timeout = 10000 if connection_type.startswith("LAN") else 5000
        
        device = rm.open_resource(resource)
        device.timeout = timeout
        
        print(f"✓ Connection opened: {resource}")
        print(f"  Connection type: {connection_type}")
        print(f"  Timeout: {timeout}ms")
        
        # Query device identification
        print("\nQuerying device identification (*IDN?)...")
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
            
            # Test basic SCPI command
            print("\nTesting basic SCPI communication...")
            try:
                # Try a simple query
                response = device.query('*IDN?')
                if response:
                    print("✓ SCPI communication test successful")
                else:
                    print("⚠ SCPI query returned empty response")
            except Exception as e:
                print(f"⚠ SCPI communication test warning: {e}")
            
        except Exception as e:
            print(f"✗ IDN query failed: {e}")
            print("  Connection established but device may not respond to *IDN?")
            return False, None
        
        return True, device_info
        
    except Exception as e:
        print(f"✗ Failed to connect to oscilloscope: {e}")
        print("\nTroubleshooting:")
        if connection_type.startswith("LAN"):
            print("  1. Verify IP address is correct (if manual)")
            print("  2. Check network connectivity: ping <ip_address>")
            print("  3. Ensure oscilloscope SCPI over LAN is enabled")
            print("  4. Verify port is correct (default: 5555 for Siglent)")
            print("  5. Check firewall settings")
            print("  6. Verify eth0 is connected and configured correctly")
        else:
            print("  1. Verify USB cable is connected")
            print("  2. Check USB device is powered on")
            print("  3. Verify USB drivers are installed")
            print("  4. Check user permissions for USB device access")
            print("  5. Try: lsusb to verify device is detected")
        return False, None
        
    finally:
        # Clean disconnect
        if device is not None:
            try:
                device.close()
                print("\n✓ Connection closed cleanly")
            except Exception as e:
                print(f"⚠ Error during close: {e}")


def main():
    """Main function to discover and connect to oscilloscope."""
    parser = argparse.ArgumentParser(
        description='Discover and connect to oscilloscope via LAN (preferred) or USB',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-discover (LAN preferred, USB fallback)
  python scripts/test_oscilloscope_connection.py
  
  # Force LAN with specific IP
  python scripts/test_oscilloscope_connection.py --ip 192.168.1.100
  
  # USB only
  python scripts/test_oscilloscope_connection.py --usb-only
        """
    )
    parser.add_argument('--ip', type=str, help='IP address of oscilloscope (forces LAN connection)')
    parser.add_argument('--port', type=int, default=5555, help='Port for TCPIP connection (default: 5555)')
    parser.add_argument('--usb-only', action='store_true', help='Only check for USB connections (skip LAN)')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("Oscilloscope Connection Test")
    print("=" * 70)
    print()
    print("Connection Priority:")
    print("  1. LAN/TCPIP (Preferred)")
    print("  2. USB/USBTMC (Fallback)")
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
    connection_type = None
    device_info = None
    
    # Step 1: Try LAN connection (unless USB-only mode)
    if not args.usb_only:
        resource, connection_type = check_lan_connection(rm, args.ip, args.port)
    
    # Step 2: Fall back to USB if LAN not available
    if resource is None:
        resource, connection_type = check_usb_connection(rm)
    
    # Step 3: If still no connection found
    if resource is None:
        print("\n" + "=" * 70)
        print("No Oscilloscope Connection Found")
        print("=" * 70)
        print()
        print("Troubleshooting:")
        print()
        print("For LAN connection:")
        print("  1. Ensure oscilloscope SCPI over LAN is enabled")
        print("  2. Verify network connectivity (ping oscilloscope IP)")
        print("  3. Check eth0 is connected and configured")
        print("  4. Try manual IP: python scripts/test_oscilloscope_connection.py --ip <ip_address>")
        print()
        print("For USB connection:")
        print("  1. Verify USB cable is connected")
        print("  2. Check oscilloscope is powered on")
        print("  3. Verify USB drivers: lsusb")
        print("  4. Check permissions: ls -l /dev/usbtmc*")
        print("  5. Try: sudo modprobe usbtmc")
        print()
        return 1
    
    # Step 4: Test the connection
    success, device_info = test_connection(rm, resource, connection_type)
    
    if not success:
        return 1
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"  Connection Type: {connection_type}")
    print(f"  Resource: {resource}")
    if device_info:
        print(f"  Device: {device_info}")
    print(f"  Status: ✓ Connection test completed successfully")
    print()
    
    # Connection type summary
    print("Connection Details:")
    if connection_type.startswith("LAN"):
        print("  ✓ Using LAN/TCPIP connection (Preferred method)")
        print("  ✓ Network-based communication")
        if connection_type == "LAN_AUTO":
            print("  ✓ Auto-discovered via PyVISA")
        else:
            print("  ✓ Manual IP connection")
    else:
        print("  ✓ Using USB/USBTMC connection (Fallback method)")
        print("  ✓ Direct USB communication")
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

