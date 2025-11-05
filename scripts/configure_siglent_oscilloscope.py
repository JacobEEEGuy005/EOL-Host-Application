#!/usr/bin/env python3
"""
Script to connect to Siglent Oscilloscope and configure it from a JSON file.

This script:
1. Scans for available USBTMC oscilloscopes
2. Connects to the first available Siglent oscilloscope
3. Loads configuration from oscilloscope_configs2.json
4. Applies the configuration to the oscilloscope
5. Verifies the configuration was applied successfully

Usage:
    python scripts/configure_siglent_oscilloscope.py [config_file_path]
    
    If config_file_path is not provided, defaults to:
    backend/data/oscilloscope_configs/oscilloscope_configs2.json
"""
import sys
import os
import json
import logging
import time

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import OscilloscopeService directly to avoid GUI dependencies
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "oscilloscope_service",
        os.path.join(project_root, "host_gui", "services", "oscilloscope_service.py")
    )
    osc_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(osc_module)
    OscilloscopeService = osc_module.OscilloscopeService
except Exception as e:
    logger.error(f"Failed to import OscilloscopeService: {e}")
    logger.error("Please ensure you are running from the project root directory")
    logger.error("Also ensure PyVISA and PyVISA-py are installed: pip install PyVISA PyVISA-py")
    sys.exit(1)


def load_configuration(config_path: str) -> dict:
    """Load oscilloscope configuration from JSON file.
    
    Args:
        config_path: Path to the configuration JSON file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If config file is invalid JSON
        ValueError: If config structure is invalid
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    logger.info(f"Loading configuration from: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Validate configuration structure
    if 'channels' not in config:
        raise ValueError("Configuration missing 'channels' key")
    if 'trigger' not in config:
        raise ValueError("Configuration missing 'trigger' key")
    
    # Validate and fix channel structure
    for ch_key in ['CH1', 'CH2', 'CH3', 'CH4']:
        if ch_key not in config['channels']:
            logger.warning(f"Channel {ch_key} not found in config, adding defaults")
            config['channels'][ch_key] = {
                'enabled': False,
                'channel_name': ch_key,
                'probe_attenuation': 1.0,
                'unit': 'V'
            }
        else:
            ch = config['channels'][ch_key]
            ch.setdefault('enabled', False)
            ch.setdefault('channel_name', ch_key)
            ch.setdefault('probe_attenuation', 1.0)
            ch.setdefault('unit', 'V')
    
    # Validate trigger structure
    trigger = config.get('trigger', {})
    trigger.setdefault('channel', 'CH1')
    trigger.setdefault('type', 'Edge')
    trigger.setdefault('setting', 'Rising')
    trigger.setdefault('noise_reject', False)
    config['trigger'] = trigger
    
    logger.info(f"Configuration loaded successfully: {config.get('name', 'Unnamed')}")
    return config


def find_siglent_oscilloscope(service: OscilloscopeService) -> str:
    """Find and return resource string for Siglent oscilloscope.
    
    Args:
        service: OscilloscopeService instance
        
    Returns:
        Resource string for the oscilloscope
        
    Raises:
        RuntimeError: If no Siglent oscilloscope found
    """
    logger.info("Scanning for USBTMC devices...")
    devices = service.scan_for_devices()
    
    if not devices:
        raise RuntimeError("No USBTMC devices found. Please ensure the oscilloscope is connected and powered on.")
    
    logger.info(f"Found {len(devices)} USBTMC device(s)")
    
    # Try to find Siglent device
    siglent_resource = None
    for device in devices:
        logger.info(f"Checking device: {device}")
        try:
            # Try to connect briefly to get device info
            temp_connected = service.connect(device)
            if temp_connected:
                device_info = service.get_device_info()
                if device_info:
                    logger.info(f"Device info: {device_info}")
                    # Check if it's a Siglent device
                    if 'siglent' in device_info.lower() or 'sds' in device_info.lower():
                        siglent_resource = device
                        logger.info(f"Found Siglent oscilloscope: {device}")
                        break
                service.disconnect()
        except Exception as e:
            logger.debug(f"Error checking device {device}: {e}")
            continue
    
    if not siglent_resource:
        # If no Siglent specifically found, use first device
        logger.warning("No Siglent device specifically identified, using first available device")
        siglent_resource = devices[0]
    
    return siglent_resource


def main():
    """Main function to configure oscilloscope."""
    # Determine config file path
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        # Try both possible filenames
        config_dir = os.path.join(project_root, 'backend', 'data', 'oscilloscope_configs')
        possible_files = [
            os.path.join(config_dir, 'oscilloscope_configs2.json'),
            os.path.join(config_dir, 'oscilloscope_config2.json'),
        ]
        config_path = None
        for possible_file in possible_files:
            if os.path.exists(possible_file):
                config_path = possible_file
                break
        
        if not config_path:
            # Default to oscilloscope_configs2.json (will show error if doesn't exist)
            config_path = possible_files[0]
    
    # Resolve relative paths
    if not os.path.isabs(config_path):
        config_path = os.path.join(project_root, config_path)
    
    try:
        # Load configuration
        config = load_configuration(config_path)
        
        # Initialize oscilloscope service
        logger.info("Initializing OscilloscopeService...")
        service = OscilloscopeService()
        
        if service.resource_manager is None:
            logger.error("PyVISA ResourceManager not available. Please install PyVISA and PyVISA-py:")
            logger.error("  pip install PyVISA PyVISA-py")
            sys.exit(1)
        
        # Find and connect to oscilloscope
        resource = find_siglent_oscilloscope(service)
        logger.info(f"Connecting to oscilloscope: {resource}")
        
        if not service.connect(resource):
            logger.error("Failed to connect to oscilloscope")
            sys.exit(1)
        
        device_info = service.get_device_info()
        if device_info:
            logger.info(f"Connected to: {device_info.strip()}")
        
        # Apply configuration
        logger.info("Applying configuration to oscilloscope...")
        logger.info("=" * 70)
        
        success, errors = service.apply_configuration(config)
        
        logger.info("=" * 70)
        
        if success:
            logger.info("✓ Configuration applied successfully!")
            
            # Print configuration summary
            logger.info("\nConfiguration Summary:")
            logger.info(f"  Name: {config.get('name', 'Unnamed')}")
            logger.info("\n  Channels:")
            for ch_key in ['CH1', 'CH2', 'CH3', 'CH4']:
                ch = config['channels'][ch_key]
                if ch.get('enabled', False):
                    logger.info(f"    {ch_key}: Enabled")
                    logger.info(f"      Name: {ch.get('channel_name', ch_key)}")
                    logger.info(f"      Probe Attenuation: {ch.get('probe_attenuation', 1.0)}")
                    logger.info(f"      Unit: {ch.get('unit', 'V')}")
                else:
                    logger.info(f"    {ch_key}: Disabled")
            
            trigger = config.get('trigger', {})
            logger.info("\n  Trigger:")
            logger.info(f"    Channel: {trigger.get('channel', 'CH1')}")
            logger.info(f"    Type: {trigger.get('type', 'Edge')}")
            logger.info(f"    Setting: {trigger.get('setting', 'Rising')}")
            logger.info(f"    Noise Reject: {trigger.get('noise_reject', False)}")
            
            logger.info("\n✓ Oscilloscope configuration completed successfully!")
            return 0
        else:
            logger.error("✗ Configuration application failed with errors:")
            for error in errors:
                logger.error(f"  - {error}")
            logger.warning("Some settings may not have been applied correctly")
            return 1
            
    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        logger.info(f"Please ensure the file exists at: {config_path}")
        return 1
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Invalid configuration: {e}")
        return 1
    except RuntimeError as e:
        logger.error(f"Runtime error: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1
    finally:
        # Clean up connection
        try:
            if 'service' in locals() and service.is_connected():
                logger.info("Disconnecting from oscilloscope...")
                service.disconnect()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")


if __name__ == '__main__':
    sys.exit(main())

