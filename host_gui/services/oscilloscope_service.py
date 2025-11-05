"""
Service for managing oscilloscope connections via USBTMC.

This service provides a high-level interface for:
- Scanning for available USBTMC oscilloscopes
- Connecting/disconnecting oscilloscopes
- Managing oscilloscope-specific configuration
- Clean termination of connections

Supports Siglent SDS1104X-U and other USBTMC-compatible oscilloscopes.
"""
import logging
import os
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

try:
    import pyvisa
    pyvisa_available = True
except ImportError:
    pyvisa = None
    pyvisa_available = False
    logger.warning("PyVISA not available - oscilloscope functionality disabled")


class OscilloscopeService:
    """Service for managing oscilloscope connections via USBTMC.
    
    Attributes:
        resource_manager: PyVISA ResourceManager instance (None if PyVISA unavailable)
        oscilloscope: Currently connected oscilloscope resource (None when disconnected)
        connected_resource: Resource string of currently connected oscilloscope
        available_resources: List of available USBTMC resources
    """
    
    def __init__(self):
        """Initialize the oscilloscope service."""
        self.resource_manager: Optional[object] = None
        self.oscilloscope: Optional[object] = None
        self.connected_resource: Optional[str] = None
        self.available_resources: List[str] = []
        
        if pyvisa_available:
            try:
                self.resource_manager = pyvisa.ResourceManager()
                logger.info("OscilloscopeService initialized with PyVISA")
            except Exception as e:
                logger.error(f"Failed to initialize PyVISA ResourceManager: {e}", exc_info=True)
                self.resource_manager = None
        else:
            logger.warning("OscilloscopeService initialized without PyVISA support")
    
    def scan_for_devices(self) -> List[str]:
        """Scan for available USBTMC oscilloscopes.
        
        Uses multiple detection methods:
        1. PyVISA list_resources() - primary method
        2. Check /dev/usbtmc* device files - fallback if PyVISA doesn't auto-detect
        3. Direct USB device detection via pyusb - for constructing resource strings
        
        Returns:
            List of resource strings for available USBTMC devices.
            Empty list if PyVISA unavailable or scan fails.
        """
        self.available_resources = []
        
        if not pyvisa_available or self.resource_manager is None:
            logger.warning("Cannot scan for devices: PyVISA not available")
            return []
        
        try:
            # Method 1: List all resources via PyVISA
            resources = self.resource_manager.list_resources()
            logger.debug(f"PyVISA found {len(resources)} total resources")
            
            # Filter for USBTMC devices (USB::* or USB0::*)
            usbtmc_resources = []
            for resource in resources:
                # Check if it's a USBTMC resource (USB:: or USB0::, USB1::, etc.)
                if resource.startswith('USB') and '::' in resource:
                    # Try to identify oscilloscopes (Siglent, etc.)
                    try:
                        # Open briefly to query identification
                        temp_resource = self.resource_manager.open_resource(resource)
                        try:
                            temp_resource.timeout = 2000  # 2 second timeout
                            # Query IDN (Identification) command
                            idn = temp_resource.query('*IDN?')
                            logger.info(f"Found USBTMC device: {resource} - {idn.strip()}")
                            usbtmc_resources.append(resource)
                        except Exception as e:
                            # Even if IDN fails, add it as USBTMC if it starts with USB
                            logger.debug(f"Found USBTMC resource (IDN query failed): {e}")
                            usbtmc_resources.append(resource)
                        finally:
                            temp_resource.close()
                    except Exception as e:
                        logger.debug(f"Could not query resource {resource}: {e}")
                        # Still add it as potential USBTMC device
                        if 'USBTMC' in str(resource) or resource.startswith('USB'):
                            usbtmc_resources.append(resource)
            
            # Method 2: Check for /dev/usbtmc* device files if PyVISA didn't find anything
            if not usbtmc_resources:
                import glob
                usbtmc_files = glob.glob('/dev/usbtmc*')
                if usbtmc_files:
                    logger.info(f"PyVISA didn't auto-detect, but found {len(usbtmc_files)} /dev/usbtmc* device file(s)")
                    # Try to construct resource strings from device files
                    # This requires querying the device to get vendor/product/serial
                    for usbtmc_file in usbtmc_files:
                        try:
                            # Try direct file access to get IDN
                            import struct
                            with open(usbtmc_file, 'rb+', buffering=0) as f:
                                cmd = b'*IDN?\n'
                                f.write(cmd)
                                
                                # Read USBTMC response header (12 bytes)
                                header = f.read(12)
                                if len(header) == 12:
                                    transfer_size = struct.unpack('>I', header[4:8])[0]
                                    data_size = min(transfer_size, 256)
                                    data = f.read(data_size)
                                    idn = data.decode('ascii', errors='ignore').strip()
                                    
                                    if idn and ',' in idn:
                                        parts = idn.split(',')
                                        logger.info(f"Found device via {usbtmc_file}: {idn}")
                                        
                                        # Try to find USB device to get vendor/product IDs
                                        try:
                                            import usb.core
                                            # Common Siglent vendor ID
                                            dev = usb.core.find(idVendor=0xf4ec)
                                            if dev:
                                                vendor_id = f"{dev.idVendor:04x}"
                                                product_id = f"{dev.idProduct:04x}"
                                                serial = parts[2].strip() if len(parts) >= 3 else ""
                                                
                                                # Construct resource string
                                                if serial:
                                                    resource_str = f"USB0::{int(vendor_id, 16)}::{int(product_id, 16)}::{serial}::0::INSTR"
                                                else:
                                                    resource_str = f"USB0::{int(vendor_id, 16)}::{int(product_id, 16)}::INSTR"
                                                
                                                # Verify it works with PyVISA
                                                try:
                                                    test_resource = self.resource_manager.open_resource(resource_str)
                                                    test_resource.timeout = 2000
                                                    test_idn = test_resource.query('*IDN?')
                                                    test_resource.close()
                                                    usbtmc_resources.append(resource_str)
                                                    logger.info(f"Verified resource string: {resource_str}")
                                                except Exception:
                                                    # If PyVISA doesn't work, still add the resource string
                                                    # The GUI can try to connect anyway
                                                    usbtmc_resources.append(resource_str)
                                                    logger.debug(f"Resource string constructed but PyVISA verification failed")
                                        except (ImportError, Exception) as e:
                                            logger.debug(f"Could not construct resource string from USB device: {e}")
                        except PermissionError:
                            logger.warning(f"Permission denied accessing {usbtmc_file} - may need udev rules")
                        except Exception as e:
                            logger.debug(f"Could not access {usbtmc_file}: {e}")
            
            self.available_resources = usbtmc_resources
            logger.info(f"Found {len(usbtmc_resources)} USBTMC oscilloscope(s)")
            return usbtmc_resources
            
        except Exception as e:
            logger.error(f"Error scanning for USBTMC devices: {e}", exc_info=True)
            return []
    
    def connect(self, resource: str) -> bool:
        """Connect to an oscilloscope.
        
        Args:
            resource: Resource string (e.g., 'USB::0x1234::0x5678::INSTR')
            
        Returns:
            True if connection successful, False otherwise
        """
        if not pyvisa_available or self.resource_manager is None:
            logger.error("Cannot connect: PyVISA not available")
            return False
        
        if self.oscilloscope is not None:
            logger.warning("Already connected to an oscilloscope, disconnecting first")
            self.disconnect()
        
        try:
            logger.info(f"Connecting to oscilloscope: {resource}")
            self.oscilloscope = self.resource_manager.open_resource(resource)
            
            # Set timeout (5 seconds)
            self.oscilloscope.timeout = 5000
            
            # Query identification to verify connection
            try:
                idn = self.oscilloscope.query('*IDN?')
                logger.info(f"Connected to oscilloscope: {idn}")
                self.connected_resource = resource
                return True
            except Exception as e:
                logger.warning(f"Connected but IDN query failed: {e}")
                # Still consider it connected
                self.connected_resource = resource
                return True
                
        except Exception as e:
            logger.error(f"Failed to connect to oscilloscope {resource}: {e}", exc_info=True)
            self.oscilloscope = None
            self.connected_resource = None
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the oscilloscope."""
        if self.oscilloscope is not None:
            try:
                logger.info("Disconnecting from oscilloscope")
                self.oscilloscope.close()
                logger.info("Oscilloscope disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting oscilloscope: {e}", exc_info=True)
            finally:
                self.oscilloscope = None
                self.connected_resource = None
    
    def is_connected(self) -> bool:
        """Check if connected to an oscilloscope.
        
        Returns:
            True if connected, False otherwise
        """
        return self.oscilloscope is not None
    
    def get_device_info(self) -> Optional[str]:
        """Get identification string from connected oscilloscope.
        
        Returns:
            Identification string (e.g., manufacturer, model) or None if not connected
        """
        if not self.is_connected():
            return None
        
        try:
            return self.oscilloscope.query('*IDN?')
        except Exception as e:
            logger.warning(f"Failed to query device info: {e}")
            return None
    
    def send_command(self, command: str) -> Optional[str]:
        """Send a SCPI command to the oscilloscope.
        
        Args:
            command: SCPI command string
            
        Returns:
            Response string if command expects response, None otherwise
        """
        if not self.is_connected():
            logger.error("Cannot send command: not connected")
            return None
        
        try:
            if command.endswith('?'):
                # Query command - expects response
                return self.oscilloscope.query(command)
            else:
                # Write command - no response
                self.oscilloscope.write(command)
                return None
        except Exception as e:
            logger.error(f"Error sending command '{command}': {e}", exc_info=True)
            return None
    
    def cleanup(self) -> None:
        """Clean up resources. Call this when shutting down."""
        self.disconnect()
        if self.resource_manager is not None:
            try:
                self.resource_manager.close()
            except Exception:
                pass
            self.resource_manager = None

