# Siglent SDS1104X-U LAN Setup Guide

This guide explains how to enable LAN (Ethernet) connectivity on the Siglent SDS1104X-U oscilloscope and verify the connection from a Raspberry Pi 5.

## Table of Contents

1. [Enabling LAN on Siglent SDS1104X-U](#enabling-lan-on-siglent-sds1104x-u)
2. [Network Configuration](#network-configuration)
3. [Raspberry Pi 5 Network Setup](#raspberry-pi-5-network-setup)
4. [Verifying Connection on Raspberry Pi 5](#verifying-connection-on-raspberry-pi-5)
5. [Troubleshooting](#troubleshooting)

---

## Enabling LAN on Siglent SDS1104X-U

### Step 1: Access Network Settings

1. **Power on** the oscilloscope
2. Press the **Utility** button (top menu bar)
3. Navigate to **I/O** → **LAN Settings** (or **Network Settings**)
4. The network configuration menu will appear

### Step 2: Configure Network Mode

You have two options:

#### Option A: DHCP (Automatic IP Assignment) - Recommended

1. Set **IP Mode** to **DHCP**
2. The oscilloscope will automatically obtain an IP address from your router
3. Note the assigned IP address (displayed on screen)
4. Press **Apply** or **OK** to save

#### Option B: Static IP (Manual Configuration)

1. Set **IP Mode** to **Static** (or **Manual**)
2. Configure the following:
   - **IP Address**: e.g., `192.168.1.100` (must be on same subnet as your Pi)
   - **Subnet Mask**: e.g., `255.255.255.0`
   - **Gateway**: e.g., `192.168.1.1` (your router's IP)
   - **DNS**: Optional, can use gateway IP or `8.8.8.8`
3. Press **Apply** or **OK** to save

### Step 3: Enable SCPI over LAN

1. In the **LAN Settings** menu, ensure **SCPI** or **SCPI over LAN** is **Enabled**
2. Note the **Port** number (default is **5555** for Siglent devices)
3. Save settings

### Step 4: Connect Ethernet Cable

1. Connect an Ethernet cable from the oscilloscope's LAN port to:
   - Your router/switch (if using DHCP), OR
   - Directly to Raspberry Pi 5 (if using static IP)
2. Wait a few seconds for the link to establish
3. Check the oscilloscope display for network status indicators

### Step 5: Verify IP Address

1. In the **LAN Settings** menu, confirm the current IP address
2. Write down this IP address - you'll need it for connection

---

## Network Configuration

### For Raspberry Pi 5

> **Important**: If you're using Raspberry Pi 5 with both WiFi and Ethernet interfaces, see the detailed [Raspberry Pi 5 Network Setup](#raspberry-pi-5-network-setup) section below for complete configuration instructions, including how to maintain internet access while connecting to the oscilloscope.

#### Option 1: Connect via Router/Switch (Recommended)

1. Connect both devices to the same network/router
2. Ensure both devices are on the same subnet (e.g., `192.168.1.x`)
3. No additional configuration needed if using DHCP

#### Option 2: Direct Connection (Static IP)

If connecting directly (no router) and you're using **only Ethernet** (no WiFi):

1. **Configure Raspberry Pi 5 static IP**:
   ```bash
   sudo nano /etc/dhcpcd.conf
   ```
   
   Add at the end:
   ```
   interface eth0
   static ip_address=192.168.1.10/24
   static routers=192.168.1.1
   static domain_name_servers=8.8.8.8
   ```
   
   Save and restart networking:
   ```bash
   sudo systemctl restart dhcpcd
   ```

2. **Configure oscilloscope** with static IP:
   - IP: `192.168.1.100`
   - Subnet: `255.255.255.0`
   - Gateway: `192.168.1.1` (or leave blank)

3. **Connect Ethernet cable** directly between devices

**Note**: If you have both WiFi and Ethernet active, use NetworkManager method described in the [Raspberry Pi 5 Network Setup](#raspberry-pi-5-network-setup) section to prevent routing conflicts.

---

## Raspberry Pi 5 Network Setup

This section provides detailed instructions for configuring network interfaces on Raspberry Pi 5, specifically for scenarios where you need to maintain internet access via WiFi (`wlan0`) while connecting to the oscilloscope via Ethernet (`eth0`).

### Understanding Dual Network Interface Setup

When using Raspberry Pi 5 with both WiFi and Ethernet:

- **WiFi (wlan0)**: Typically used for internet access and general network connectivity
- **Ethernet (eth0)**: Used for direct connection to the oscilloscope on a different subnet

**Important**: If both interfaces are active, Linux routing determines which interface is used based on the destination IP address and routing table. Proper configuration ensures:
- Internet traffic uses `wlan0` (default route)
- Oscilloscope traffic (e.g., `192.168.1.100`) uses `eth0` (subnet-specific route)

### Prerequisites

1. **Check NetworkManager is installed**:
   ```bash
   which nmcli
   ```
   If not installed:
   ```bash
   sudo apt update
   sudo apt install network-manager
   ```

2. **Check current network interfaces**:
   ```bash
   ip addr show
   nmcli device status
   ```

3. **Identify your WiFi connection name**:
   ```bash
   nmcli connection show --active
   ```

### Method 1: Using NetworkManager (nmcli) - Recommended

NetworkManager is the modern way to manage network connections on Raspberry Pi OS and provides better control over routing behavior.

#### Step 1: Check Existing Ethernet Connection

```bash
nmcli connection show
```

Look for an existing Ethernet connection (usually named "Wired connection 1" or similar). If one exists, note its name. If not, we'll create a new one.

#### Step 2: Create or Modify Ethernet Connection

**Option A: Modify Existing Connection**

If an Ethernet connection already exists:

```bash
# Replace "Wired connection 1" with your actual connection name
nmcli connection modify "Wired connection 1" \
    ipv4.method manual \
    ipv4.addresses 192.168.1.10/24 \
    ipv4.never-default yes
```

**Option B: Create New Connection**

If no Ethernet connection exists:

```bash
nmcli connection add \
    type ethernet \
    con-name "Oscilloscope Connection" \
    ifname eth0 \
    ipv4.method manual \
    ipv4.addresses 192.168.1.10/24 \
    ipv4.never-default yes
```

**Critical Setting Explanation**:
- `ipv4.never-default yes`: **This is essential!** It prevents `eth0` from becoming the default route, which would break internet access. Without this setting, connecting `eth0` may cause your system to lose internet connectivity.

#### Step 3: Verify Connection Configuration

```bash
# Replace with your connection name
nmcli connection show "Wired connection 1" | grep -E "(ipv4.addresses|ipv4.never-default|ipv4.method)"
```

**Expected output**:
```
ipv4.method:                            manual
ipv4.addresses:                         192.168.1.10/24
ipv4.never-default:                     yes
```

#### Step 4: Connect the Ethernet Interface

```bash
# Connect using the connection name
nmcli device connect eth0
# OR activate the specific connection
nmcli connection up "Wired connection 1"
```

#### Step 5: Verify Network Configuration

**Check eth0 has IP address**:
```bash
ip addr show eth0
```

**Expected output**:
```
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ...
    inet 192.168.1.10/24 brd 192.168.1.255 scope global noprefixroute eth0
```

**Check routing table**:
```bash
ip route show
```

**Expected output** (example):
```
default via 192.168.68.1 dev wlan0 proto dhcp src 192.168.68.115 metric 600
192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.10 metric 100
192.168.68.0/24 dev wlan0 proto kernel scope link src 192.168.68.115 metric 600
```

**Key points**:
- Default route should go through `wlan0` (for internet access)
- `192.168.1.0/24` route should go through `eth0` (for oscilloscope)

**Verify routing to oscilloscope**:
```bash
ip route get 192.168.1.100
```

**Expected output**:
```
192.168.1.100 dev eth0 src 192.168.1.10 uid 1000
```

**Verify internet routing still works**:
```bash
ip route get 8.8.8.8
ping -c 2 8.8.8.8
```

**Expected output**:
```
8.8.8.8 via 192.168.68.1 dev wlan0 src 192.168.68.115 uid 1000
```

### Method 2: Using dhcpcd (Legacy Method)

If you prefer using `dhcpcd` (traditional Raspberry Pi method):

#### Step 1: Edit dhcpcd Configuration

```bash
sudo nano /etc/dhcpcd.conf
```

#### Step 2: Add Ethernet Configuration

Add at the end of the file:

```
# Oscilloscope connection - do not use as default route
interface eth0
static ip_address=192.168.1.10/24
static routers=
static domain_name_servers=
nogateway
```

**Important**: 
- `static routers=` (empty) prevents setting a default gateway
- `nogateway` ensures eth0 doesn't become the default route

#### Step 3: Restart Networking

```bash
sudo systemctl restart dhcpcd
```

#### Step 4: Verify Configuration

```bash
ip addr show eth0
ip route show
```

### Network Configuration Summary

#### Typical Setup

| Interface | IP Address | Subnet | Purpose | Default Route |
|-----------|------------|--------|---------|---------------|
| `wlan0` | `192.168.68.115` | `192.168.68.0/24` | Internet access | ✅ Yes |
| `eth0` | `192.168.1.10` | `192.168.1.0/24` | Oscilloscope | ❌ No |

#### IP Address Planning

- **Oscilloscope IP**: `192.168.1.100` (configured on oscilloscope)
- **Raspberry Pi eth0 IP**: `192.168.1.10` (configured on Pi)
- **Subnet Mask**: `255.255.255.0` (`/24`)
- **Gateway**: Not needed for direct connection (leave empty)

### Verifying Dual Network Setup

Run these commands to verify your configuration:

```bash
# 1. Check both interfaces are up
ip addr show wlan0
ip addr show eth0

# 2. Check routing table
ip route show

# 3. Verify oscilloscope uses eth0
ip route get 192.168.1.100

# 4. Verify internet uses wlan0
ip route get 8.8.8.8

# 5. Test connectivity
ping -c 2 192.168.1.100  # Oscilloscope via eth0
ping -c 2 8.8.8.8         # Internet via wlan0
```

### Common NetworkManager Commands

```bash
# List all connections
nmcli connection show

# List active connections
nmcli connection show --active

# Show connection details
nmcli connection show "Wired connection 1"

# Connect/disconnect interface
nmcli device connect eth0
nmcli device disconnect eth0

# Activate/deactivate connection
nmcli connection up "Wired connection 1"
nmcli connection down "Wired connection 1"

# Modify connection (example: change IP)
nmcli connection modify "Wired connection 1" ipv4.addresses 192.168.1.10/24

# Delete connection
nmcli connection delete "Wired connection 1"
```

### Troubleshooting Network Configuration

#### Problem: Internet Access Lost When Connecting eth0

**Symptoms**: After connecting `eth0`, you lose internet connectivity even though `wlan0` is still connected.

**Root Cause**: `eth0` connection is configured to become the default route, overriding `wlan0`.

**Solution**:
```bash
# Set never-default to yes
nmcli connection modify "Wired connection 1" ipv4.never-default yes

# Remove gateway if set
nmcli connection modify "Wired connection 1" ipv4.gateway ""

# Reconnect
nmcli connection down "Wired connection 1"
nmcli connection up "Wired connection 1"
```

**Verify fix**:
```bash
ip route show
# Default route should show wlan0, not eth0
```

#### Problem: eth0 Doesn't Get IP Address

**Symptoms**: `eth0` shows as connected but has no IP address.

**Solutions**:
1. **Check connection is activated**:
   ```bash
   nmcli device status
   nmcli connection show --active
   ```

2. **Manually activate connection**:
   ```bash
   nmcli connection up "Wired connection 1"
   ```

3. **Check connection configuration**:
   ```bash
   nmcli connection show "Wired connection 1" | grep ipv4
   ```

4. **Verify physical connection**:
   ```bash
   ip link show eth0
   # Should show "state UP"
   ```

#### Problem: Traffic to Oscilloscope Uses Wrong Interface

**Symptoms**: `ip route get 192.168.1.100` shows traffic going through `wlan0` instead of `eth0`.

**Solutions**:
1. **Verify eth0 has correct IP and subnet**:
   ```bash
   ip addr show eth0
   # Should show 192.168.1.10/24
   ```

2. **Check routing table has subnet route**:
   ```bash
   ip route show
   # Should show: 192.168.1.0/24 dev eth0
   ```

3. **If route is missing, reconnect eth0**:
   ```bash
   nmcli connection down "Wired connection 1"
   nmcli connection up "Wired connection 1"
   ```

#### Problem: Connection Drops After Reboot

**Symptoms**: `eth0` doesn't connect automatically after system restart.

**Solutions**:
1. **Enable autoconnect**:
   ```bash
   nmcli connection modify "Wired connection 1" connection.autoconnect yes
   ```

2. **Verify autoconnect setting**:
   ```bash
   nmcli connection show "Wired connection 1" | grep autoconnect
   ```

#### Problem: Multiple Default Routes

**Symptoms**: `ip route show` shows multiple default routes, causing routing confusion.

**Solutions**:
1. **Check all connections**:
   ```bash
   nmcli connection show | grep -E "(ipv4.never-default|ipv4.gateway)"
   ```

2. **Ensure only wlan0 has default route**:
   ```bash
   # Set never-default on eth0
   nmcli connection modify "Wired connection 1" ipv4.never-default yes
   
   # Verify wlan0 doesn't have never-default
   nmcli connection show "Ergon Main Office" | grep never-default
   # Should show: ipv4.never-default: no
   ```

### Network Interface Priority and Metrics

Linux uses route metrics to determine which interface to use when multiple routes exist. Lower metrics have higher priority.

**Default metrics** (typical):
- `wlan0`: metric 600 (from DHCP)
- `eth0`: metric 100 (manual configuration)

**To adjust metrics** (if needed):
```bash
# Set eth0 metric (higher = lower priority for default route)
nmcli connection modify "Wired connection 1" ipv4.route-metric 200

# Set wlan0 metric (lower = higher priority for default route)
nmcli connection modify "Ergon Main Office" ipv4.route-metric 100
```

**Note**: With `ipv4.never-default yes` on eth0, metrics don't matter for default route selection, but they can affect other routing decisions.

### Best Practices

1. **Always set `ipv4.never-default yes`** on `eth0` when using it only for oscilloscope connection
2. **Use static IPs** for direct connections (more reliable than DHCP)
3. **Use different subnets** for WiFi and Ethernet to avoid routing conflicts
4. **Test connectivity** after any network configuration changes
5. **Document your IP addresses** for easy reference

### Quick Configuration Checklist

- [ ] WiFi (`wlan0`) connected and has internet access
- [ ] Ethernet connection profile created/modified with:
  - [ ] Static IP: `192.168.1.10/24`
  - [ ] `ipv4.never-default: yes`
  - [ ] No gateway configured (or empty gateway)
- [ ] `eth0` interface connected and has IP address
- [ ] Routing table shows:
  - [ ] Default route via `wlan0`
  - [ ] `192.168.1.0/24` route via `eth0`
- [ ] Verification tests pass:
  - [ ] `ip route get 192.168.1.100` uses `eth0`
  - [ ] `ip route get 8.8.8.8` uses `wlan0`
  - [ ] Ping to oscilloscope works
  - [ ] Ping to internet works

---

## Verifying Connection on Raspberry Pi 5

### Method 1: Using the Test Script (Recommended)

The project includes a test script specifically for LAN oscilloscope connections:

#### Prerequisites

1. Install required Python packages:
   ```bash
   pip install PyVISA PyVISA-py
   ```

2. Ensure you're in the project directory:
   ```bash
   cd /home/hp/Github_Local_Repository/EOL-Host-Application
   ```

#### Test with Auto-Discovery

```bash
python scripts/test_lan_oscilloscope.py
```

This will:
- Scan for TCPIP oscilloscope resources
- Connect to the first available device
- Query device identification (*IDN?)
- Display connection status

#### Test with Specific IP Address

If auto-discovery doesn't work, specify the IP address manually:

```bash
python scripts/test_lan_oscilloscope.py --ip 192.168.1.100
```

Replace `192.168.1.100` with your oscilloscope's actual IP address.

#### Test with Custom Port

If using a non-standard port:

```bash
python scripts/test_lan_oscilloscope.py --ip 192.168.1.100 --port 5555
```

### Method 2: Basic Network Connectivity Test

#### Step 1: Ping the Oscilloscope

```bash
ping -c 4 192.168.1.100
```

Replace `192.168.1.100` with your oscilloscope's IP address.

**Expected output:**
```
PING 192.168.1.100 (192.168.1.100) 56(84) bytes of data.
64 bytes from 192.168.1.100: icmp_seq=1 ttl=64 time=0.123 ms
64 bytes from 192.168.1.100: icmp_seq=2 ttl=64 time=0.098 ms
...
```

If ping fails, check:
- Ethernet cable connection
- IP address is correct
- Both devices on same network

#### Step 2: Test Port Connectivity

```bash
telnet 192.168.1.100 5555
```

Or using `nc` (netcat):
```bash
nc -zv 192.168.1.100 5555
```

**Expected output:**
```
Connection to 192.168.1.100 5555 port [tcp/*] succeeded!
```

If connection fails, verify:
- SCPI over LAN is enabled on oscilloscope
- Port 5555 is correct
- Firewall is not blocking the port

#### Step 3: Test SCPI Communication

Using Python with PyVISA:

```bash
python3
```

```python
import pyvisa

# Create resource string
resource = "TCPIP::192.168.1.100::5555::INSTR"

# Initialize ResourceManager
rm = pyvisa.ResourceManager()

# Open connection
device = rm.open_resource(resource)
device.timeout = 5000  # 5 second timeout

# Query device identification
idn = device.query('*IDN?')
print(f"Device: {idn}")

# Close connection
device.close()
```

**Expected output:**
```
Device: SIGLENT TECHNOLOGIES,SDS1104X-U,<serial_number>,<firmware_version>
```

### Method 3: Using PyVISA Resource List

List all available resources:

```bash
python3
```

```python
import pyvisa

rm = pyvisa.ResourceManager()
resources = rm.list_resources()
print("Available resources:")
for res in resources:
    print(f"  - {res}")
```

Look for resources starting with `TCPIP::`:
```
Available resources:
  - TCPIP::192.168.1.100::5555::INSTR
```

---

## Troubleshooting

### Problem: Ping Fails

**Symptoms**: `ping` command shows "Destination Host Unreachable" or "Request timeout"

**Solutions**:
1. **Check physical connection**: Ensure Ethernet cable is securely connected
2. **Verify IP addresses**: Both devices must be on the same subnet
   ```bash
   # Check Pi's IP
   ip addr show eth0
   
   # Check oscilloscope IP (from oscilloscope display)
   ```
3. **Check network mode**: Ensure both devices are using the same network configuration (DHCP or static)
4. **Try different cable**: Test with a known-good Ethernet cable
5. **Check router/switch**: If using a router, ensure it's functioning properly

### Problem: Port 5555 Not Accessible

**Symptoms**: Ping works but `telnet` or `nc` fails to connect

**Solutions**:
1. **Verify SCPI over LAN is enabled** on the oscilloscope:
   - Utility → I/O → LAN Settings → SCPI: Enabled
2. **Check port number**: Default is 5555, verify in oscilloscope settings
3. **Check firewall** on Raspberry Pi:
   ```bash
   sudo ufw status
   sudo ufw allow 5555/tcp  # If firewall is active
   ```
4. **Restart oscilloscope**: Power cycle the oscilloscope after enabling SCPI

### Problem: PyVISA Connection Fails

**Symptoms**: `test_lan_oscilloscope.py` shows connection error

**Solutions**:
1. **Install PyVISA properly**:
   ```bash
   pip install --upgrade PyVISA PyVISA-py
   ```
2. **Check resource string format**:
   ```
   TCPIP::<IP_ADDRESS>::<PORT>::INSTR
   ```
3. **Increase timeout**:
   ```python
   device.timeout = 10000  # 10 seconds
   ```
4. **Verify oscilloscope is responsive**:
   - Check oscilloscope display for any error messages
   - Try rebooting the oscilloscope
5. **Check for multiple network interfaces**:
   ```bash
   ip addr show
   ```
   Ensure you're using the correct interface
6. **Verify network routing** (see [Raspberry Pi 5 Network Setup](#raspberry-pi-5-network-setup) section):
   ```bash
   ip route get <oscilloscope_ip>
   ```
   Should show traffic using `eth0`, not `wlan0`

### Problem: Auto-Discovery Doesn't Find Device

**Symptoms**: `test_lan_oscilloscope.py` reports "No TCPIP resources found"

**Solutions**:
1. **Use manual IP connection**:
   ```bash
   python scripts/test_lan_oscilloscope.py --ip <oscilloscope_ip>
   ```
2. **Check PyVISA backend**:
   ```python
   import pyvisa
   rm = pyvisa.ResourceManager()
   print(rm)  # Should show backend information
   ```
3. **Verify network connectivity** first with `ping`
4. **Check oscilloscope network status** on the device display

### Problem: *IDN? Query Fails

**Symptoms**: Connection opens but `*IDN?` query returns error

**Solutions**:
1. **Check SCPI is enabled**: Utility → I/O → LAN Settings → SCPI: Enabled
2. **Verify oscilloscope is not in a special mode** (e.g., firmware update mode)
3. **Try basic SCPI commands**:
   ```python
   device.write("*RST")  # Reset
   device.query("*IDN?")  # Query ID
   ```
4. **Check oscilloscope firmware version**: Older firmware may have SCPI limitations

### Problem: Connection Works Intermittently

**Symptoms**: Connection works sometimes but fails at other times

**Solutions**:
1. **Check network stability**: Use `ping -c 100` to test for packet loss
2. **Check for IP conflicts**: Ensure no other device has the same IP
3. **Use static IP** instead of DHCP for more reliable connections
4. **Check cable quality**: Use a high-quality Ethernet cable
5. **Check for network congestion**: If on a busy network, consider direct connection

### Problem: Losing Internet Access When Connecting eth0

**Symptoms**: After connecting `eth0` to the oscilloscope, you lose internet connectivity even though WiFi (`wlan0`) is still connected. Applications like Cursor AI, web browsers, or package managers cannot access the internet.

**Root Cause**: The `eth0` connection is configured to become the default route, overriding `wlan0`'s default route. This happens when:
- `ipv4.never-default` is set to `no` (or not set)
- A gateway is configured on `eth0`
- NetworkManager assigns `eth0` as the default route due to routing metrics

**Solutions**:

1. **Set `never-default` flag** (Primary fix):
   ```bash
   # Find your ethernet connection name
   nmcli connection show
   
   # Set never-default to yes
   nmcli connection modify "Wired connection 1" ipv4.never-default yes
   
   # Remove gateway if configured
   nmcli connection modify "Wired connection 1" ipv4.gateway ""
   
   # Reconnect to apply changes
   nmcli connection down "Wired connection 1"
   nmcli connection up "Wired connection 1"
   ```

2. **Verify the fix**:
   ```bash
   # Check routing table - default should be wlan0
   ip route show | grep default
   # Should show: default via <wlan0_gateway> dev wlan0
   
   # Test internet connectivity
   ping -c 2 8.8.8.8
   
   # Verify oscilloscope still uses eth0
   ip route get 192.168.1.100
   # Should show: 192.168.1.100 dev eth0
   ```

3. **If using dhcpcd** (alternative method):
   Edit `/etc/dhcpcd.conf`:
   ```
   interface eth0
   static ip_address=192.168.1.10/24
   static routers=
   nogateway
   ```
   Then restart: `sudo systemctl restart dhcpcd`

**Prevention**: Always configure `eth0` with `ipv4.never-default yes` when using it only for oscilloscope connection. See the [Raspberry Pi 5 Network Setup](#raspberry-pi-5-network-setup) section for detailed configuration instructions.

### Additional Debugging Commands

#### Check Network Interface Status
```bash
ip link show eth0
ethtool eth0
```

#### Check Routing Table
```bash
ip route show
```

#### Monitor Network Traffic
```bash
sudo tcpdump -i eth0 host 192.168.1.100
```

#### Test with Different Tools
```bash
# Using curl (if oscilloscope supports HTTP)
curl http://192.168.1.100

# Using nmap to scan ports
nmap -p 5555 192.168.1.100
```

---

## Quick Reference

### Default Settings for Siglent SDS1104X-U

- **Default Port**: 5555
- **Protocol**: SCPI over TCP/IP
- **Resource String Format**: `TCPIP::<IP>::5555::INSTR`
- **SCPI Command**: `*IDN?` (query device identification)

### Common IP Ranges

- **Home Router**: Usually `192.168.1.x` or `192.168.0.x`
- **Direct Connection**: Use `192.168.1.x` with subnet `255.255.255.0`

### Useful Commands Summary

```bash
# Test network connectivity
ping -c 4 <oscilloscope_ip>

# Test port connectivity
nc -zv <oscilloscope_ip> 5555

# Run connection test script
python scripts/test_lan_oscilloscope.py --ip <oscilloscope_ip>

# Check PyVISA installation
python3 -c "import pyvisa; print(pyvisa.__version__)"

# Network configuration (Raspberry Pi 5)
nmcli connection show                    # List all connections
nmcli device status                      # Show device status
ip route show                           # Show routing table
ip route get <ip_address>                # Check which interface is used
```

---

## Next Steps

Once LAN connection is verified:

1. **Use in your application**: The `OscilloscopeService` can connect using TCPIP resource strings:
   ```python
   resource = "TCPIP::192.168.1.100::5555::INSTR"
   osc_service.connect(resource)
   ```

2. **Configure oscilloscope**: Use `scripts/configure_siglent_oscilloscope.py` with your configuration files

3. **Run tests**: Execute your test plans that use the oscilloscope

For more information, see:
- [Oscilloscope Integration Guide](OSCILLOSCOPE_INTEGRATION.md)
- [Test Script Documentation](../scripts/test_lan_oscilloscope.py)

