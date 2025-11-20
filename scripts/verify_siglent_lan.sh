#!/bin/bash
#
# Quick verification script for Siglent SDS1104X-U LAN connection
# This script performs basic network connectivity tests
#
# Usage:
#   ./scripts/verify_siglent_lan.sh [oscilloscope_ip]
#
# Example:
#   ./scripts/verify_siglent_lan.sh 192.168.1.100
#

set -e

# Default IP if not provided
DEFAULT_IP="192.168.1.100"
OSC_IP="${1:-$DEFAULT_IP}"
OSC_PORT="5555"

echo "============================================================"
echo "Siglent SDS1104X-U LAN Connection Verification"
echo "============================================================"
echo ""
echo "Oscilloscope IP: $OSC_IP"
echo "Port: $OSC_PORT"
echo ""

# Check if IP address is provided
if [ -z "$1" ]; then
    echo "⚠ No IP address provided, using default: $DEFAULT_IP"
    echo "   Usage: $0 <oscilloscope_ip>"
    echo ""
fi

# Test 1: Ping test
echo "Test 1: Network Connectivity (Ping)"
echo "----------------------------------------"
if ping -c 3 -W 2 "$OSC_IP" > /dev/null 2>&1; then
    echo "✓ Ping successful - Network connectivity OK"
    ping -c 3 "$OSC_IP" | tail -1
else
    echo "✗ Ping failed - No network connectivity"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check Ethernet cable connection"
    echo "  2. Verify IP address is correct"
    echo "  3. Ensure both devices are on the same network"
    echo "  4. Check oscilloscope LAN settings"
    exit 1
fi
echo ""

# Test 2: Port connectivity
echo "Test 2: Port Connectivity (Port $OSC_PORT)"
echo "----------------------------------------"
if command -v nc > /dev/null 2>&1; then
    if nc -zv -w 2 "$OSC_IP" "$OSC_PORT" > /dev/null 2>&1; then
        echo "✓ Port $OSC_PORT is accessible"
    else
        echo "✗ Port $OSC_PORT is not accessible"
        echo ""
        echo "Troubleshooting:"
        echo "  1. Verify SCPI over LAN is enabled on oscilloscope"
        echo "  2. Check port number (default: 5555)"
        echo "  3. Check firewall settings"
        exit 1
    fi
elif command -v telnet > /dev/null 2>&1; then
    if timeout 2 telnet "$OSC_IP" "$OSC_PORT" > /dev/null 2>&1; then
        echo "✓ Port $OSC_PORT is accessible"
    else
        echo "✗ Port $OSC_PORT is not accessible"
        exit 1
    fi
else
    echo "⚠ Cannot test port (nc or telnet not available)"
    echo "  Install netcat: sudo apt-get install netcat"
fi
echo ""

# Test 3: PyVISA connection test
echo "Test 3: PyVISA SCPI Communication"
echo "----------------------------------------"
if command -v python3 > /dev/null 2>&1; then
    if python3 -c "import pyvisa" > /dev/null 2>&1; then
        echo "✓ PyVISA is installed"
        
        # Run Python connection test
        python3 << EOF
import sys
import pyvisa

try:
    resource = f"TCPIP::${OSC_IP}::${OSC_PORT}::INSTR"
    print(f"  Connecting to: {resource}")
    
    rm = pyvisa.ResourceManager()
    device = rm.open_resource(resource)
    device.timeout = 5000
    
    idn = device.query('*IDN?')
    print(f"✓ SCPI communication successful")
    print(f"  Device: {idn.strip()}")
    
    device.close()
    sys.exit(0)
except ImportError:
    print("✗ PyVISA not installed")
    print("  Install: pip install PyVISA PyVISA-py")
    sys.exit(1)
except Exception as e:
    print(f"✗ SCPI communication failed: {e}")
    print("")
    print("Troubleshooting:")
    print("  1. Verify SCPI over LAN is enabled")
    print("  2. Check oscilloscope is not in a special mode")
    print("  3. Try increasing timeout")
    sys.exit(1)
EOF
        
        if [ $? -eq 0 ]; then
            echo ""
            echo "============================================================"
            echo "✓ All tests passed! LAN connection is working correctly."
            echo "============================================================"
            echo ""
            echo "You can now use the oscilloscope with:"
            echo "  python scripts/test_lan_oscilloscope.py --ip $OSC_IP"
            exit 0
        else
            exit 1
        fi
    else
        echo "✗ PyVISA is not installed"
        echo ""
        echo "Install PyVISA:"
        echo "  pip install PyVISA PyVISA-py"
        exit 1
    fi
else
    echo "⚠ Python3 not found, skipping PyVISA test"
    echo ""
    echo "============================================================"
    echo "Basic connectivity tests completed"
    echo "============================================================"
    echo ""
    echo "For full SCPI test, install Python3 and PyVISA:"
    echo "  pip install PyVISA PyVISA-py"
    echo "  python scripts/test_lan_oscilloscope.py --ip $OSC_IP"
    exit 0
fi

