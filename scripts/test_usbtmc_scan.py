#!/usr/bin/env python3
"""
Test script to scan for USBTMC devices.

This script scans for available USBTMC oscilloscopes and other instruments
connected via USB and displays their identification information.

Usage:
    python scripts/test_usbtmc_scan.py

Requirements:
    - PyVISA and PyVISA-py installed
    - USB device connected and recognized by the system
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def main():
    """Main function to scan for USBTMC devices."""
    print("=" * 70)
    print("USBTMC Device Scanner")
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
    
    # List all resources
    try:
        all_resources = rm.list_resources()
        print(f"Found {len(all_resources)} total resource(s)")
        print()
        
        if not all_resources:
            print("No resources found. Please check:")
            print("  1. USB device is connected")
            print("  2. USB device is powered on")
            print("  3. USB drivers are installed (if required)")
            print("  4. User has permissions to access USB devices")
            return 0
    except Exception as e:
        print(f"✗ Failed to list resources: {e}")
        return 1
    
    # Try to find USB device directly using vendor/product IDs
    print("Attempting direct USB device detection...")
    try:
        import usb.core
        usb_device = usb.core.find(idVendor=0xf4ec, idProduct=0x1012)
        if usb_device:
            print(f"✓ Found USB device: Vendor=0x{usb_device.idVendor:04x}, Product=0x{usb_device.idProduct:04x}")
            # Try to construct resource string manually
            try:
                serial = usb.util.get_string(usb_device, usb_device.iSerialNumber)
                print(f"  Serial: {serial}")
            except:
                serial = None
                print("  Serial: (not available)")
    except ImportError:
        print("  (pyusb not available for direct USB access)")
    except Exception as e:
        print(f"  (Could not access USB device directly: {e})")
    
    # Check for /dev/usbtmc* devices
    import glob
    usbtmc_files = glob.glob('/dev/usbtmc*')
    if usbtmc_files:
        print(f"\n✓ Found USBTMC device files: {usbtmc_files}")
        for usbtmc_file in usbtmc_files:
            import stat
            import os
            file_stat = os.stat(usbtmc_file)
            perms = stat.filemode(file_stat.st_mode)
            print(f"  {usbtmc_file}: {perms} (owner: {file_stat.st_uid})")
            if file_stat.st_uid != 0 or (file_stat.st_mode & stat.S_IROTH) == 0:
                print(f"    ⚠ Permission issue - may need chmod or udev rule")
    else:
        print("\n⚠ No /dev/usbtmc* device files found")
        print("  Try: sudo modprobe usbtmc")
    
    # Filter and display USBTMC devices
    usbtmc_devices = []
    print("\nScanning PyVISA resources for USBTMC devices...")
    print("-" * 70)
    
    for resource in all_resources:
        # Check if it's a USB resource
        if resource.startswith('USB') and '::' in resource:
            print(f"\nFound USB resource: {resource}")
            
            # Try to open and query identification
            try:
                device = rm.open_resource(resource)
                try:
                    # Set a short timeout for queries
                    device.timeout = 2000  # 2 seconds
                    
                    # Query identification
                    idn = device.query('*IDN?')
                    print(f"  Type: USBTMC")
                    print(f"  Identification: {idn.strip()}")
                    
                    # Parse IDN (format: Manufacturer,Model,Serial,Version)
                    parts = idn.split(',')
                    if len(parts) >= 4:
                        print(f"  Manufacturer: {parts[0].strip()}")
                        print(f"  Model: {parts[1].strip()}")
                        print(f"  Serial: {parts[2].strip()}")
                        print(f"  Version: {parts[3].strip()}")
                    
                    usbtmc_devices.append({
                        'resource': resource,
                        'idn': idn.strip(),
                        'parts': parts
                    })
                    print(f"  ✓ Successfully queried device")
                    
                except Exception as e:
                    print(f"  ⚠ USBTMC resource but IDN query failed: {e}")
                    # Still add as potential USBTMC device
                    usbtmc_devices.append({
                        'resource': resource,
                        'idn': None,
                        'parts': []
                    })
                finally:
                    device.close()
                    
            except Exception as e:
                print(f"  ⚠ Could not open resource: {e}")
                # Still add as potential USBTMC device
                if 'USBTMC' in str(resource) or resource.startswith('USB'):
                    usbtmc_devices.append({
                        'resource': resource,
                        'idn': None,
                        'parts': []
                    })
        else:
            # Not a USB resource, skip or show briefly
            print(f"  Skipping non-USBTMC resource: {resource}")
    
    print()
    print("-" * 70)
    print(f"\nSummary:")
    print(f"  Total resources found: {len(all_resources)}")
    print(f"  USBTMC devices found: {len(usbtmc_devices)}")
    print()
    
    # Try direct access to /dev/usbtmc* device files if PyVISA didn't find them
    if not usbtmc_devices and usbtmc_files:
        print("\nTrying direct access to /dev/usbtmc* device files...")
        import struct
        for usbtmc_file in usbtmc_files:
            try:
                print(f"  Testing direct file access: {usbtmc_file}")
                with open(usbtmc_file, 'rb+', buffering=0) as f:
                    # Send *IDN? command
                    cmd = b'*IDN?\n'
                    f.write(cmd)
                    
                    # Read USBTMC response header (12 bytes)
                    header = f.read(12)
                    if len(header) == 12:
                        # Parse USBTMC header
                        # btag, btag_inverse, msgid (2 bytes), transfer_size (4 bytes), reserved (4 bytes)
                        transfer_size = struct.unpack('>I', header[4:8])[0]
                        # Read data (limit to reasonable size)
                        data_size = min(transfer_size, 256)
                        data = f.read(data_size)
                        idn = data.decode('ascii', errors='ignore').strip()
                        
                        # Try to get full IDN by reading more if needed
                        if len(idn) < transfer_size:
                            remaining = f.read(transfer_size - len(idn))
                            idn += remaining.decode('ascii', errors='ignore').strip()
                        
                        # Clean up IDN string
                        idn = idn.split('\n')[0].strip()
                        
                        if idn and ',' in idn:
                            print(f"    ✓ Success! Device responded via direct file access")
                            print(f"    IDN: {idn}")
                            parts = idn.split(',')
                            
                            # Construct a resource string that might work
                            if len(parts) >= 3:
                                serial = parts[2].strip()
                                resource_str = f"USB0::0xf4ec::0x1012::{serial}::INSTR"
                            else:
                                resource_str = f"USB0::0xf4ec::0x1012::INSTR"
                            
                            usbtmc_devices.append({
                                'resource': resource_str,
                                'idn': idn,
                                'parts': parts,
                                'device_file': usbtmc_file,
                                'access_method': 'direct_file'
                            })
                            break
            except PermissionError:
                print(f"    ✗ Permission denied - need udev rules or run with sudo")
                print(f"    Try: sudo chmod 666 {usbtmc_file}")
            except Exception as e:
                print(f"    ✗ Error accessing {usbtmc_file}: {e}")
        
        # Also try PyVISA resource strings if we got device info
        if usbtmc_devices:
            print("\nTrying PyVISA resource strings with discovered information...")
            for device_info in usbtmc_devices[:]:  # Copy list to avoid modification during iteration
                if device_info.get('access_method') == 'direct_file':
                    test_resources = [
                        device_info['resource'],
                        f"USB::0xf4ec::0x1012::{device_info['parts'][2] if len(device_info['parts']) >= 3 else ''}::INSTR",
                        f"USB0::0xf4ec::0x1012::INSTR",
                    ]
                    
                    for test_resource in test_resources:
                        if not test_resource or '::INSTR' not in test_resource:
                            continue
                        try:
                            print(f"  Trying PyVISA: {test_resource}")
                            device = rm.open_resource(test_resource)
                            device.timeout = 2000
                            idn = device.query('*IDN?')
                            print(f"    ✓ PyVISA connection successful! IDN: {idn.strip()}")
                            # Update resource to use PyVISA method
                            device_info['resource'] = test_resource
                            device_info['access_method'] = 'pyvisa'
                            device.close()
                            break
                        except Exception as e:
                            print(f"    ✗ PyVISA failed: {type(e).__name__}")
                            continue
    
    if usbtmc_devices:
        print("\nUSBTMC Devices:")
        print("-" * 70)
        for i, device in enumerate(usbtmc_devices, 1):
            print(f"\n{i}. Resource: {device['resource']}")
            if device['idn']:
                print(f"   IDN: {device['idn']}")
                if len(device['parts']) >= 2:
                    print(f"   → {device['parts'][0].strip()} {device['parts'][1].strip()}")
            else:
                print(f"   (IDN query failed or not supported)")
        print()
        print("✓ USBTMC devices detected successfully!")
        return 0
    else:
        print("⚠ No USBTMC devices found.")
        print("\nTroubleshooting:")
        print("  1. Ensure oscilloscope is powered on and connected via USB")
        print("  2. Check USB cable connection")
        print("  3. Verify device is recognized by system:")
        print("     - Linux: lsusb")
        print("     - Check dmesg for USB device messages")
        print("  4. Ensure user has permissions (may need to add user to dialout group)")
        print("  5. Try running with sudo (not recommended for production)")
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

