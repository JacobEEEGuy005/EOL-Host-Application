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
from typing import Optional, List, Dict, Tuple, Any

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
    
    def configure_channel(self, channel: int, enabled: bool, probe_attenuation: float, unit: str) -> bool:
        """Configure a single oscilloscope channel.
        
        Args:
            channel: Channel number (1-4)
            enabled: Enable/disable channel
            probe_attenuation: Probe attenuation ratio (e.g., 1.0, 10.0, 100.0)
            unit: Unit string ('V' or 'A') - Note: Oscilloscope measures voltage only
        
        Returns:
            True if configuration successful and verified, False otherwise
        """
        if not self.is_connected():
            logger.error("Cannot configure channel: oscilloscope not connected")
            return False
        
        if channel < 1 or channel > 4:
            logger.error(f"Invalid channel number: {channel} (must be 1-4)")
            return False
        
        try:
            channel_name = f"CHAN{channel}"
            errors = []
            
            # Configure channel display (enable/disable)
            try:
                disp_cmd = f":{channel_name}:DISP {'ON' if enabled else 'OFF'}"
                self.oscilloscope.write(disp_cmd)
                logger.debug(f"Sent command: {disp_cmd}")
                
                # Read back and verify
                readback = self.oscilloscope.query(f":{channel_name}:DISP?")
                readback_enabled = readback.strip().upper() in ['1', 'ON', 'TRUE']
                if readback_enabled != enabled:
                    errors.append(f"Channel {channel} display mismatch: set={enabled}, readback={readback_enabled}")
                    logger.warning(f"Channel {channel} display readback mismatch")
                else:
                    logger.debug(f"Channel {channel} display verified: {enabled}")
            except Exception as e:
                errors.append(f"Channel {channel} display configuration failed: {e}")
                logger.error(f"Failed to configure channel {channel} display: {e}", exc_info=True)
            
            if enabled:
                # Configure probe attenuation
                try:
                    probe_cmd = f":{channel_name}:PROB {probe_attenuation}"
                    self.oscilloscope.write(probe_cmd)
                    logger.debug(f"Sent command: {probe_cmd}")
                    
                    # Read back and verify (allow small tolerance for floating point)
                    readback = self.oscilloscope.query(f":{channel_name}:PROB?")
                    try:
                        readback_att = float(readback.strip())
                        if abs(readback_att - probe_attenuation) > 0.01:
                            errors.append(f"Channel {channel} probe attenuation mismatch: set={probe_attenuation}, readback={readback_att}")
                            logger.warning(f"Channel {channel} probe attenuation readback mismatch")
                        else:
                            logger.debug(f"Channel {channel} probe attenuation verified: {probe_attenuation}")
                    except ValueError:
                        errors.append(f"Channel {channel} probe attenuation readback invalid: {readback}")
                        logger.warning(f"Channel {channel} probe attenuation readback invalid: {readback}")
                except Exception as e:
                    errors.append(f"Channel {channel} probe attenuation configuration failed: {e}")
                    logger.error(f"Failed to configure channel {channel} probe attenuation: {e}", exc_info=True)
                
                # Configure unit (oscilloscope measures voltage only, but we store unit for reference)
                try:
                    # Oscilloscope units are typically VOLT or AMP, but Siglent may only support VOLT
                    # Store unit in config but always set to VOLT on scope
                    unit_cmd = f":{channel_name}:UNIT VOLT"
                    self.oscilloscope.write(unit_cmd)
                    logger.debug(f"Sent command: {unit_cmd} (unit={unit} stored in config, scope set to VOLT)")
                    
                    # Read back and verify
                    readback = self.oscilloscope.query(f":{channel_name}:UNIT?")
                    readback_unit = readback.strip().upper()
                    if 'VOLT' not in readback_unit:
                        logger.warning(f"Channel {channel} unit readback unexpected: {readback_unit}")
                    else:
                        logger.debug(f"Channel {channel} unit verified: VOLT (config unit={unit})")
                except Exception as e:
                    # Some oscilloscopes may not support UNIT command, log but don't fail
                    logger.debug(f"Channel {channel} unit command not supported or failed: {e}")
            
            if errors:
                logger.error(f"Channel {channel} configuration completed with errors: {errors}")
                return False
            
            logger.info(f"Channel {channel} configured successfully: enabled={enabled}, probe={probe_attenuation}, unit={unit}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring channel {channel}: {e}", exc_info=True)
            return False
    
    def configure_trigger(self, channel: str, trigger_type: str, trigger_setting: str, noise_reject: bool) -> bool:
        """Configure oscilloscope trigger settings.
        
        Args:
            channel: Trigger channel ('CH1', 'CH2', 'CH3', 'CH4')
            trigger_type: Trigger type ('Edge' - fixed)
            trigger_setting: Trigger slope ('Rising', 'Falling', 'Alternate')
            noise_reject: Enable noise rejection (True/False)
        
        Returns:
            True if configuration successful and verified, False otherwise
        """
        if not self.is_connected():
            logger.error("Cannot configure trigger: oscilloscope not connected")
            return False
        
        if trigger_type != 'Edge':
            logger.warning(f"Trigger type '{trigger_type}' not supported, using Edge")
            trigger_type = 'Edge'
        
        # Map trigger setting to SCPI command
        slope_map = {
            'Rising': 'RISING',
            'Falling': 'FALLING',
            'Alternate': 'ALTERNATE'
        }
        slope_scpi = slope_map.get(trigger_setting, 'RISING')
        
        try:
            errors = []
            
            # Configure trigger mode (Edge)
            try:
                mode_cmd = ":TRIG:MODE EDGE"
                self.oscilloscope.write(mode_cmd)
                logger.debug(f"Sent command: {mode_cmd}")
                
                # Read back and verify
                readback = self.oscilloscope.query(":TRIG:MODE?")
                if 'EDGE' not in readback.upper():
                    errors.append(f"Trigger mode mismatch: set=EDGE, readback={readback}")
                    logger.warning(f"Trigger mode readback mismatch")
                else:
                    logger.debug("Trigger mode verified: EDGE")
            except Exception as e:
                errors.append(f"Trigger mode configuration failed: {e}")
                logger.error(f"Failed to configure trigger mode: {e}", exc_info=True)
            
            # Configure trigger source channel
            try:
                source_cmd = f":TRIG:EDGE:SOUR {channel}"
                self.oscilloscope.write(source_cmd)
                logger.debug(f"Sent command: {source_cmd}")
                
                # Read back and verify
                readback = self.oscilloscope.query(":TRIG:EDGE:SOUR?")
                readback_ch = readback.strip().upper()
                if channel.upper() not in readback_ch:
                    errors.append(f"Trigger source mismatch: set={channel}, readback={readback_ch}")
                    logger.warning(f"Trigger source readback mismatch")
                else:
                    logger.debug(f"Trigger source verified: {channel}")
            except Exception as e:
                errors.append(f"Trigger source configuration failed: {e}")
                logger.error(f"Failed to configure trigger source: {e}", exc_info=True)
            
            # Configure trigger slope
            try:
                slope_cmd = f":TRIG:EDGE:SLOP {slope_scpi}"
                self.oscilloscope.write(slope_cmd)
                logger.debug(f"Sent command: {slope_cmd}")
                
                # Read back and verify
                readback = self.oscilloscope.query(":TRIG:EDGE:SLOP?")
                readback_slope = readback.strip().upper()
                if slope_scpi.upper() not in readback_slope:
                    errors.append(f"Trigger slope mismatch: set={slope_scpi}, readback={readback_slope}")
                    logger.warning(f"Trigger slope readback mismatch")
                else:
                    logger.debug(f"Trigger slope verified: {slope_scpi}")
            except Exception as e:
                errors.append(f"Trigger slope configuration failed: {e}")
                logger.error(f"Failed to configure trigger slope: {e}", exc_info=True)
            
            # Configure noise reject
            try:
                noise_cmd = f":TRIG:EDGE:NOIS {'ON' if noise_reject else 'OFF'}"
                self.oscilloscope.write(noise_cmd)
                logger.debug(f"Sent command: {noise_cmd}")
                
                # Read back and verify
                readback = self.oscilloscope.query(":TRIG:EDGE:NOIS?")
                readback_noise = readback.strip().upper() in ['1', 'ON', 'TRUE']
                if readback_noise != noise_reject:
                    errors.append(f"Trigger noise reject mismatch: set={noise_reject}, readback={readback_noise}")
                    logger.warning(f"Trigger noise reject readback mismatch")
                else:
                    logger.debug(f"Trigger noise reject verified: {noise_reject}")
            except Exception as e:
                errors.append(f"Trigger noise reject configuration failed: {e}")
                logger.error(f"Failed to configure trigger noise reject: {e}", exc_info=True)
            
            if errors:
                logger.error(f"Trigger configuration completed with errors: {errors}")
                return False
            
            logger.info(f"Trigger configured successfully: channel={channel}, type={trigger_type}, setting={trigger_setting}, noise_reject={noise_reject}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring trigger: {e}", exc_info=True)
            return False
    
    def apply_configuration(self, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Apply full oscilloscope configuration from dictionary.
        
        Args:
            config: Configuration dictionary with 'channels' and 'trigger' keys
        
        Returns:
            Tuple of (success: bool, errors: List[str])
            success: True if all configurations applied successfully
            errors: List of error messages for failed configurations
        """
        if not self.is_connected():
            return False, ["Oscilloscope not connected"]
        
        errors = []
        
        # Validate configuration structure
        if 'channels' not in config:
            return False, ["Configuration missing 'channels' key"]
        if 'trigger' not in config:
            return False, ["Configuration missing 'trigger' key"]
        
        # Configure each channel
        channels_config = config['channels']
        for ch_key in ['CH1', 'CH2', 'CH3', 'CH4']:
            if ch_key not in channels_config:
                continue
            
            ch_config = channels_config[ch_key]
            channel_num = int(ch_key[2])  # Extract number from 'CH1', 'CH2', etc.
            
            enabled = ch_config.get('enabled', False)
            probe_attenuation = ch_config.get('probe_attenuation', 1.0)
            unit = ch_config.get('unit', 'V')
            
            success = self.configure_channel(channel_num, enabled, probe_attenuation, unit)
            if not success:
                errors.append(f"Failed to configure {ch_key}")
        
        # Configure trigger
        trigger_config = config['trigger']
        trigger_channel = trigger_config.get('channel', 'CH1')
        trigger_type = trigger_config.get('type', 'Edge')
        trigger_setting = trigger_config.get('setting', 'Rising')
        noise_reject = trigger_config.get('noise_reject', False)
        
        success = self.configure_trigger(trigger_channel, trigger_type, trigger_setting, noise_reject)
        if not success:
            errors.append("Failed to configure trigger")
        
        overall_success = len(errors) == 0
        if overall_success:
            logger.info("Oscilloscope configuration applied successfully")
        else:
            logger.warning(f"Oscilloscope configuration applied with {len(errors)} error(s): {errors}")
        
        return overall_success, errors
    
    def get_channel_names(self, config: Optional[Dict[str, Any]] = None) -> List[str]:
        """Get list of enabled channel names from configuration.
        
        Used by Test Configurator for dropdown population.
        
        Args:
            config: Optional configuration dictionary. If None, returns empty list.
        
        Returns:
            List of channel names (e.g., ['Phase W Current', 'Phase V Current'])
        """
        if config is None:
            return []
        
        channel_names = []
        if 'channels' in config:
            for ch_key in ['CH1', 'CH2', 'CH3', 'CH4']:
                if ch_key in config['channels']:
                    ch_config = config['channels'][ch_key]
                    if ch_config.get('enabled', False):
                        channel_name = ch_config.get('channel_name', '').strip()
                        if channel_name:
                            channel_names.append(channel_name)
        
        return channel_names
    
    def cleanup(self) -> None:
        """Clean up resources. Call this when shutting down."""
        self.disconnect()
        if self.resource_manager is not None:
            try:
                self.resource_manager.close()
            except Exception:
                pass
            self.resource_manager = None

