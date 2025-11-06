#!/usr/bin/env python3
"""
Phase Current Testing State Machine Script

This script implements a state machine for Phase Current Calibration testing:
1. Connects to oscilloscope
2. Connects to CAN (Canalystii, Channel 0, 500kbps)
3. Loads DBC file for decoding
4. Gets Iq_ref from user input
5. Verifies and configures oscilloscope
6. Executes test sequence with state machine
"""

import os
import sys
import time
import logging
import re
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import numpy for optimized array operations (optional but recommended)
try:
    import numpy as np
    numpy_available = True
except ImportError:
    numpy = None
    numpy_available = False

# Pre-compile regex patterns for better performance
REGEX_ATTN = re.compile(r'ATTN\s+([\d.]+)', re.IGNORECASE)
REGEX_TDIV = re.compile(r'TDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_VDIV = re.compile(r'VDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_OFST = re.compile(r'OFST\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_NUMBER = re.compile(r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)')
REGEX_NUMBER_SIMPLE = re.compile(r'([\d.]+)')

# Import matplotlib for plotting (optional)
try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib_available = True
except ImportError:
    matplotlib = None
    plt = None
    matplotlib_available = False

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import services directly (avoid __init__.py which imports PySide6-dependent modules)
import importlib.util

# Import OscilloscopeService
osc_spec = importlib.util.spec_from_file_location(
    "oscilloscope_service",
    project_root / "host_gui" / "services" / "oscilloscope_service.py"
)
osc_module = importlib.util.module_from_spec(osc_spec)
osc_spec.loader.exec_module(osc_module)
OscilloscopeService = osc_module.OscilloscopeService

# Import CanService
can_spec = importlib.util.spec_from_file_location(
    "can_service",
    project_root / "host_gui" / "services" / "can_service.py"
)
can_module = importlib.util.module_from_spec(can_spec)
can_spec.loader.exec_module(can_module)
CanService = can_module.CanService

# Import DbcService
dbc_spec = importlib.util.spec_from_file_location(
    "dbc_service",
    project_root / "host_gui" / "services" / "dbc_service.py"
)
dbc_module = importlib.util.module_from_spec(dbc_spec)
dbc_spec.loader.exec_module(dbc_module)
DbcService = dbc_module.DbcService

# Import Frame
from backend.adapters.interface import Frame

# Import waveform retrieval functions from retrieve_waveform_data.py
waveform_spec = importlib.util.spec_from_file_location(
    "retrieve_waveform_data",
    project_root / "scripts" / "retrieve_waveform_data.py"
)
waveform_module = importlib.util.module_from_spec(waveform_spec)
waveform_spec.loader.exec_module(waveform_module)
WaveformDecoder = waveform_module.WaveformDecoder
query_vertical_gain = waveform_module.query_vertical_gain
query_vertical_offset = waveform_module.query_vertical_offset
analyze_steady_state = waveform_module.analyze_steady_state
apply_lowpass_filter = waveform_module.apply_lowpass_filter
retrieve_waveform = waveform_module.retrieve_waveform

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestState(Enum):
    """State machine states for Phase Current Testing."""
    INIT = "INIT"
    VERIFY_CONFIG = "VERIFY_CONFIG"
    CONFIGURE_TIMEBASE = "CONFIGURE_TIMEBASE"
    CONFIGURE_VERTICAL = "CONFIGURE_VERTICAL"
    STOP_ACQUISITION = "STOP_ACQUISITION"
    START_ACQUISITION = "START_ACQUISITION"
    SEND_TRIGGER = "SEND_TRIGGER"
    WAIT_AND_STOP = "WAIT_AND_STOP"
    RETRIEVE_WAVEFORMS = "RETRIEVE_WAVEFORMS"
    DONE = "DONE"
    ERROR = "ERROR"


class PhaseCurrentTestStateMachine:
    """State machine for Phase Current Calibration testing."""
    
    def __init__(self, iq_ref: float, tolerance: float = 0.1):
        """Initialize the state machine.
        
        Args:
            iq_ref: Iq reference value in Amperes
            tolerance: Tolerance for vertical scale verification (default: 0.1)
        """
        self.iq_ref = iq_ref
        self.tolerance = tolerance
        self.state = TestState.INIT
        
        # Services
        self.oscilloscope_service: Optional[OscilloscopeService] = None
        self.can_service: Optional[CanService] = None
        self.dbc_service: Optional[DbcService] = None
        
        # State data
        self.osc_resource: Optional[str] = None
        self.command_message = None  # Will be set when DBC is loaded
        self.ip_status_message = None  # Will be set when DBC is loaded
        
        # CAN data logging
        self.collecting_can_data = False
        self.collected_frames = []  # List of (timestamp, frame) tuples
        
    def run(self) -> bool:
        """Run the state machine until completion or error.
        
        Returns:
            True if test completed successfully, False otherwise
        """
        logger.info("=" * 70)
        logger.info("Phase Current Testing State Machine - Starting")
        logger.info(f"Iq_ref: {self.iq_ref} A")
        logger.info("=" * 70)
        
        try:
            while self.state != TestState.DONE and self.state != TestState.ERROR:
                logger.info(f"\n--- State: {self.state.value} ---")
                
                if self.state == TestState.INIT:
                    success = self._state_init()
                elif self.state == TestState.VERIFY_CONFIG:
                    success = self._state_verify_config()
                elif self.state == TestState.CONFIGURE_TIMEBASE:
                    success = self._state_configure_timebase()
                elif self.state == TestState.CONFIGURE_VERTICAL:
                    success = self._state_configure_vertical()
                elif self.state == TestState.STOP_ACQUISITION:
                    success = self._state_stop_acquisition()
                elif self.state == TestState.START_ACQUISITION:
                    success = self._state_start_acquisition()
                elif self.state == TestState.SEND_TRIGGER:
                    success = self._state_send_trigger()
                elif self.state == TestState.WAIT_AND_STOP:
                    success = self._state_wait_and_stop()
                elif self.state == TestState.RETRIEVE_WAVEFORMS:
                    success = self._state_retrieve_waveforms()
                else:
                    logger.error(f"Unknown state: {self.state}")
                    self.state = TestState.ERROR
                    success = False
                
                if not success:
                    logger.error(f"State {self.state.value} failed")
                    self.state = TestState.ERROR
                    break
                
                # Small delay between states
                time.sleep(0.1)
            
            if self.state == TestState.DONE:
                logger.info("\n" + "=" * 70)
                logger.info("Phase Current Testing - COMPLETED SUCCESSFULLY")
                logger.info("=" * 70)
                return True
            else:
                logger.error("\n" + "=" * 70)
                logger.error("Phase Current Testing - FAILED")
                logger.error("=" * 70)
                return False
                
        except Exception as e:
            logger.error(f"Unexpected error in state machine: {e}", exc_info=True)
            self.state = TestState.ERROR
            return False
        finally:
            self._cleanup()
    
    def _state_init(self) -> bool:
        """Initialize: Connect to oscilloscope, CAN, and load DBC."""
        logger.info("Initializing connections...")
        
        # Initialize oscilloscope service
        try:
            self.oscilloscope_service = OscilloscopeService()
            if self.oscilloscope_service.resource_manager is None:
                logger.error("OscilloscopeService: PyVISA ResourceManager not available")
                return False
            
            # Scan for devices
            devices = self.oscilloscope_service.scan_for_devices()
            if not devices:
                logger.error("No oscilloscope devices found")
                return False
            
            logger.info(f"Found {len(devices)} oscilloscope device(s)")
            self.osc_resource = devices[0]
            logger.info(f"Connecting to: {self.osc_resource}")
            
            if not self.oscilloscope_service.connect(self.osc_resource):
                logger.error("Failed to connect to oscilloscope")
                return False
            
            device_info = self.oscilloscope_service.get_device_info()
            if device_info:
                logger.info(f"Connected to oscilloscope: {device_info.strip()}")
        except Exception as e:
            logger.error(f"Failed to initialize oscilloscope: {e}", exc_info=True)
            return False
        
        # Initialize CAN service
        try:
            self.can_service = CanService(channel='0', bitrate=500)  # Channel 0, 500kbps
            logger.info("Connecting to Canalystii (Channel 0, 500kbps)...")
            
            try:
                if not self.can_service.connect('Canalystii'):
                    logger.error("Failed to connect to Canalystii")
                    return False
                logger.info("Connected to Canalystii")
            except Exception as can_err:
                error_msg = str(can_err)
                if 'canalystii' in error_msg.lower() or 'ModuleNotFoundError' in str(type(can_err).__name__):
                    logger.error("=" * 70)
                    logger.error("CANALYSTII PACKAGE NOT INSTALLED")
                    logger.error("=" * 70)
                    logger.error("The 'canalystii' Python package is required to use Canalystii hardware.")
                    logger.error("Please install it using one of the following methods:")
                    logger.error("  1. pip install canalystii")
                    logger.error("  2. Or use a virtual environment: python3 -m venv venv && source venv/bin/activate && pip install canalystii")
                    logger.error("=" * 70)
                raise
        except Exception as e:
            logger.error(f"Failed to initialize CAN service: {e}", exc_info=True)
            return False
        
        # Load DBC file
        try:
            dbc_path = project_root / 'docs' / 'can_specs' / 'eol_firmware.dbc'
            if not dbc_path.exists():
                logger.error(f"DBC file not found: {dbc_path}")
                return False
            
            self.dbc_service = DbcService()
            if not self.dbc_service.load_dbc_file(str(dbc_path)):
                logger.error("Failed to load DBC file")
                return False
            
            logger.info(f"Loaded DBC file: {dbc_path}")
            
            # Find Command message (ID 272 = 0x110)
            self.command_message = self.dbc_service.find_message_by_id(272)
            if self.command_message is None:
                logger.error("Command message (ID 272) not found in DBC")
                return False
            
            logger.info(f"Found Command message: {self.command_message.name}")
            
            # Find IP_Status_Data message (ID 250 = 0xFA)
            self.ip_status_message = self.dbc_service.find_message_by_id(250)
            if self.ip_status_message is None:
                logger.error("IP_Status_Data message (ID 250) not found in DBC")
                return False
            
            logger.info(f"Found IP_Status_Data message: {self.ip_status_message.name}")
        except Exception as e:
            logger.error(f"Failed to load DBC: {e}", exc_info=True)
            return False
        
        self.state = TestState.VERIFY_CONFIG
        return True
    
    def _state_verify_config(self) -> bool:
        """Verify oscilloscope configuration: Check C1:TRA?, C2:TRA?, C1:ATTN?, C2:ATTN?."""
        logger.info("Verifying oscilloscope configuration...")
        
        if not self.oscilloscope_service.is_connected():
            logger.error("Oscilloscope not connected")
            return False
        
        errors = []
        
        # Check C1:TRA?
        try:
            time.sleep(0.2)
            resp = self.oscilloscope_service.send_command("C1:TRA?")
            if resp is None:
                errors.append("C1:TRA? - No response")
            else:
                c1_tra = resp.strip().upper()
                is_on = 'ON' in c1_tra or c1_tra == '1' or 'TRUE' in c1_tra
                logger.info(f"C1:TRA? = {resp.strip()} (ON={is_on})")
                if not is_on:
                    errors.append("C1 trace is OFF")
        except Exception as e:
            errors.append(f"C1:TRA? query failed: {e}")
        
        # Check C2:TRA?
        try:
            time.sleep(0.2)
            resp = self.oscilloscope_service.send_command("C2:TRA?")
            if resp is None:
                errors.append("C2:TRA? - No response")
            else:
                c2_tra = resp.strip().upper()
                is_on = 'ON' in c2_tra or c2_tra == '1' or 'TRUE' in c2_tra
                logger.info(f"C2:TRA? = {resp.strip()} (ON={is_on})")
                if not is_on:
                    errors.append("C2 trace is OFF")
        except Exception as e:
            errors.append(f"C2:TRA? query failed: {e}")
        
        # Check C1:ATTN?
        try:
            time.sleep(0.2)
            resp = self.oscilloscope_service.send_command("C1:ATTN?")
            if resp is None:
                errors.append("C1:ATTN? - No response")
            else:
                # Parse attenuation value
                attn_match = REGEX_ATTN.search(resp)
                if attn_match:
                    c1_attn = float(attn_match.group(1))
                    logger.info(f"C1:ATTN? = {c1_attn}")
                else:
                    # Fallback: extract last number
                    numbers = REGEX_NUMBER_SIMPLE.findall(resp)
                    if numbers:
                        c1_attn = float(numbers[-1])
                        logger.info(f"C1:ATTN? = {c1_attn} (parsed from: {resp.strip()})")
                    else:
                        errors.append(f"C1:ATTN? - Could not parse: {resp.strip()}")
        except Exception as e:
            errors.append(f"C1:ATTN? query failed: {e}")
        
        # Check C2:ATTN?
        try:
            time.sleep(0.2)
            resp = self.oscilloscope_service.send_command("C2:ATTN?")
            if resp is None:
                errors.append("C2:ATTN? - No response")
            else:
                # Parse attenuation value
                attn_match = REGEX_ATTN.search(resp)
                if attn_match:
                    c2_attn = float(attn_match.group(1))
                    logger.info(f"C2:ATTN? = {c2_attn}")
                else:
                    # Fallback: extract last number
                    numbers = REGEX_NUMBER_SIMPLE.findall(resp)
                    if numbers:
                        c2_attn = float(numbers[-1])
                        logger.info(f"C2:ATTN? = {c2_attn} (parsed from: {resp.strip()})")
                    else:
                        errors.append(f"C2:ATTN? - Could not parse: {resp.strip()}")
        except Exception as e:
            errors.append(f"C2:ATTN? query failed: {e}")
        
        if errors:
            logger.error(f"Configuration verification failed: {errors}")
            return False
        
        logger.info("Oscilloscope configuration verified successfully")
        self.state = TestState.CONFIGURE_TIMEBASE
        return True
    
    def _state_configure_timebase(self) -> bool:
        """Configure timebase: Set TDIV:1, verify with TDIV?."""
        logger.info("Configuring timebase...")
        
        if not self.oscilloscope_service.is_connected():
            logger.error("Oscilloscope not connected")
            return False
        
        try:
            # Set TDIV:1 (1 second per division)
            logger.info("Setting TDIV:500MS")
            self.oscilloscope_service.send_command("TDIV:500MS")
            time.sleep(0.2)
            
            # Readback TDIV?
            resp = self.oscilloscope_service.send_command("TDIV?")
            if resp is None:
                logger.error("TDIV? - No response")
                return False
            
            # Parse timebase value
            tdiv_match = REGEX_TDIV.search(resp)
            if tdiv_match:
                tdiv_value = float(tdiv_match.group(1))
            else:
                # Fallback: extract number
                numbers = REGEX_NUMBER_SIMPLE.findall(resp)
                if numbers:
                    tdiv_value = float(numbers[-1])
                else:
                    logger.error(f"TDIV? - Could not parse: {resp.strip()}")
                    return False
            
            logger.info(f"TDIV? = {tdiv_value} (expected: 1.0)")
            
            # Verify (allow small tolerance)
            if abs(tdiv_value - 1.0) > 0.01:
                logger.warning(f"Timebase mismatch: set=1.0, readback={tdiv_value}")
                # Continue anyway, but log warning
            else:
                logger.info("Timebase configured successfully")
            
            self.state = TestState.CONFIGURE_VERTICAL
            return True
            
        except Exception as e:
            logger.error(f"Failed to configure timebase: {e}", exc_info=True)
            return False
    
    def _state_configure_vertical(self) -> bool:
        """Configure vertical scale: Set C1:VDIV <Iq_ref>, C2:VDIV <Iq_ref>, verify with tolerance."""
        logger.info(f"Configuring vertical scale (Iq_ref={self.iq_ref} A)...")
        
        if not self.oscilloscope_service.is_connected():
            logger.error("Oscilloscope not connected")
            return False
        
        errors = []
        
        # Set C1:VDIV <Iq_ref>
        try:
            logger.info(f"Setting C1:VDIV {self.iq_ref}")
            self.oscilloscope_service.send_command(f"C1:VDIV {self.iq_ref}")
            time.sleep(0.2)
            
            # Readback C1:VDIV?
            resp = self.oscilloscope_service.send_command("C1:VDIV?")
            print(resp)
            if resp is None:
                errors.append("C1:VDIV? - No response")
            else:
                # Parse vertical scale value (handles exponential format like 1.5e-2, 5.0e+1)
                # Pattern matches: optional sign, digits, optional decimal, optional exponent
                vdiv_match = REGEX_VDIV.search(resp)
                if vdiv_match:
                    try:
                        c1_vdiv = float(vdiv_match.group(1))
                    except ValueError:
                        errors.append(f"C1:VDIV? - Could not convert to float: {vdiv_match.group(1)}")
                        c1_vdiv = None
                else:
                    # Fallback: try to find any number (including exponential) in the response
                    numbers = REGEX_NUMBER.findall(resp)
                    if numbers:
                        try:
                            c1_vdiv = float(numbers[-1])
                        except ValueError:
                            errors.append(f"C1:VDIV? - Could not convert to float: {numbers[-1]}")
                            c1_vdiv = None
                    else:
                        errors.append(f"C1:VDIV? - Could not parse: {resp.strip()}")
                        c1_vdiv = None
                
                if c1_vdiv is not None:
                    logger.info(f"C1:VDIV? = {c1_vdiv} (expected: {self.iq_ref})")
                    if abs(c1_vdiv - self.iq_ref) > self.tolerance:
                        errors.append(f"C1:VDIV mismatch: set={self.iq_ref}, readback={c1_vdiv}, tolerance={self.tolerance}")
        except Exception as e:
            errors.append(f"C1:VDIV configuration failed: {e}")
        
        # Set C2:VDIV <Iq_ref>
        try:
            logger.info(f"Setting C2:VDIV {self.iq_ref}")
            self.oscilloscope_service.send_command(f"C2:VDIV {self.iq_ref}")
            time.sleep(0.2)
            
            # Readback C2:VDIV?
            resp = self.oscilloscope_service.send_command("C2:VDIV?")
            print(resp)
            if resp is None:
                errors.append("C2:VDIV? - No response")
            else:
                # Parse vertical scale value (handles exponential format like 1.5e-2, 5.0e+1)
                # Pattern matches: optional sign, digits, optional decimal, optional exponent
                vdiv_match = REGEX_VDIV.search(resp)
                if vdiv_match:
                    try:
                        c2_vdiv = float(vdiv_match.group(1))
                    except ValueError:
                        errors.append(f"C2:VDIV? - Could not convert to float: {vdiv_match.group(1)}")
                        c2_vdiv = None
                else:
                    # Fallback: try to find any number (including exponential) in the response
                    numbers = REGEX_NUMBER.findall(resp)
                    if numbers:
                        try:
                            c2_vdiv = float(numbers[-1])
                        except ValueError:
                            errors.append(f"C2:VDIV? - Could not convert to float: {numbers[-1]}")
                            c2_vdiv = None
                    else:
                        errors.append(f"C2:VDIV? - Could not parse: {resp.strip()}")
                        c2_vdiv = None
                
                if c2_vdiv is not None:
                    logger.info(f"C2:VDIV? = {c2_vdiv} (expected: {self.iq_ref})")
                    if abs(c2_vdiv - self.iq_ref) > self.tolerance:
                        errors.append(f"C2:VDIV mismatch: set={self.iq_ref}, readback={c2_vdiv}, tolerance={self.tolerance}")
        except Exception as e:
            errors.append(f"C2:VDIV configuration failed: {e}")
        
        if errors:
            logger.error(f"Vertical scale configuration failed: {errors}")
            return False
        
        logger.info("Vertical scale configured successfully")
        self.state = TestState.STOP_ACQUISITION
        return True
    
    def _state_stop_acquisition(self) -> bool:
        """Stop acquisition: Send STOP, wait 2 seconds."""
        logger.info("Stopping acquisition...")
        
        if not self.oscilloscope_service.is_connected():
            logger.error("Oscilloscope not connected")
            return False
        
        try:
            # Send STOP command
            logger.info("Sending STOP command")
            self.oscilloscope_service.send_command("STOP")
            time.sleep(0.2)
            
            # Wait 2 seconds
            logger.info("Waiting 2 seconds...")
            time.sleep(2.0)
            
            logger.info("Acquisition stopped")
            self.state = TestState.START_ACQUISITION
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop acquisition: {e}", exc_info=True)
            return False
    
    def _state_start_acquisition(self) -> bool:
        """Start acquisition: Send TRMD AUTO, wait 1 second."""
        logger.info("Starting acquisition...")
        
        if not self.oscilloscope_service.is_connected():
            logger.error("Oscilloscope not connected")
            return False
        
        try:
            # Send TRMD AUTO command
            logger.info("Sending TRMD AUTO command")
            self.oscilloscope_service.send_command("TRMD AUTO")
            time.sleep(0.2)
            
            # Wait 1 second
            logger.info("Waiting 1 second...")
            time.sleep(1.0)
            
            logger.info("Acquisition started")
            self.state = TestState.SEND_TRIGGER
            return True
            
        except Exception as e:
            logger.error(f"Failed to start acquisition: {e}", exc_info=True)
            return False
    
    def _state_send_trigger(self) -> bool:
        """Send test trigger: Mctrl_Phase_I_Test_Enable=1, Mctrl_Set_Iq_Ref=<user input>, Mctrl_Set_Id_Ref=0."""
        logger.info("Sending test trigger message...")
        
        if not self.can_service.is_connected():
            logger.error("CAN service not connected")
            return False
        
        if self.command_message is None:
            logger.error("Command message not found")
            return False
        
        try:
            # Encode message with signal values
            # MessageType 20 (m20) is the multiplexor for phase current test signals
            signal_values = {
                'DeviceID': 0x03,  # IPC_Hardware = 0x03
                'MessageType': 20,  # MessageType 20 (m20) for phase current test
                'Mctrl_Phase_I_Test_Enable': 1,
                'Mctrl_Set_Iq_Ref': self.iq_ref,
                'Mctrl_Set_Id_Ref': 0.0
            }
            
            # Encode using DBC service
            frame_data = self.dbc_service.encode_message(self.command_message, signal_values)
            
            # Create and send frame
            frame = Frame(
                can_id=272,  # 0x110
                data=frame_data,
                timestamp=None
            )
            
            logger.info(f"Sending CAN frame: ID=0x{frame.can_id:X}, signals={signal_values}")
            
            if not self.can_service.send_frame(frame):
                logger.error("Failed to send CAN frame")
                return False
            
            logger.info("Test trigger message sent successfully")
            
            # Try to set hardware CAN filter for IP_Status_Data (CAN ID 250) if supported
            # Use CanService.set_filters() which provides proper abstraction
            if hasattr(self.can_service, 'set_filters'):
                try:
                    # Set hardware filter to only receive CAN ID 250 (0xFA)
                    # Standard CAN ID mask: 0x7FF for 11-bit IDs, extended=False for standard CAN
                    filter_set = self.can_service.set_filters([{'can_id': 250, 'can_mask': 0x7FF, 'extended': False}])
                    if filter_set:
                        logger.info("Enabled CAN hardware filter for ID 250 (IP_Status_Data)")
                    else:
                        logger.debug("CAN adapter does not support hardware filters (using software filtering)")
                except Exception as e:
                    logger.debug(f"Could not set CAN hardware filters (using software filtering): {e}")
            else:
                logger.debug("CAN service does not support filter configuration (using software filtering)")
            
            # Start collecting CAN data for PhaseVCurrent and PhaseWCurrent
            logger.info("Starting CAN data collection for PhaseVCurrent and PhaseWCurrent...")
            self.collecting_can_data = True
            self.collected_frames = []
            
            self.state = TestState.WAIT_AND_STOP
            return True
            
        except Exception as e:
            logger.error(f"Failed to send trigger message: {e}", exc_info=True)
            return False
    
    def _state_wait_and_stop(self) -> bool:
        """Wait 4 seconds, then send STOP to stop data acquisition."""
        logger.info("Waiting 4 seconds before stopping acquisition...")
        
        if not self.oscilloscope_service.is_connected():
            logger.error("Oscilloscope not connected")
            return False
        
        try:
            # Wait 4 seconds while collecting CAN data
            # Poll for CAN frames during this time
            start_time = time.time()
            while time.time() - start_time < 4.0:
                # Get frames from CAN service (non-blocking)
                frame = self.can_service.get_frame(timeout=None)  # Non-blocking
                if frame:
                    if self.collecting_can_data and frame.can_id == 250:
                        # Only collect IP_Status_Data frames (CAN ID 250)
                        # Use frame timestamp if available, otherwise use current time
                        frame_timestamp = getattr(frame, 'timestamp', None) or time.time()
                        self.collected_frames.append((frame_timestamp, frame))
                    # If frame doesn't match or we're not collecting, continue immediately
                    # to check for next frame without sleeping
                else:
                    # Only sleep when queue is empty to avoid busy-waiting
                    # Use shorter sleep for better responsiveness
                    time.sleep(0.001)  # 1ms sleep when no frames available
            
            # Stop collecting CAN data
            self.collecting_can_data = False
            logger.info(f"Collected {len(self.collected_frames)} IP_Status_Data frames")
            
            # Send STOP command
            logger.info("Sending STOP command to stop data acquisition")
            self.oscilloscope_service.send_command("STOP")
            time.sleep(0.2)
            
            # Process collected CAN data
            self._process_can_data()
            
            logger.info("Data acquisition stopped")
            self.state = TestState.RETRIEVE_WAVEFORMS
            return True
            
        except Exception as e:
            logger.error(f"Failed in wait_and_stop: {e}", exc_info=True)
            return False
    
    def _retrieve_channel_waveform(self, channel: int) -> Optional[bytes]:
        """Retrieve waveform data for a specific channel.
        
        Args:
            channel: Channel number (1 or 2)
            
        Returns:
            Binary waveform data or None if retrieval fails
        """
        if not self.oscilloscope_service.is_connected():
            logger.error("Oscilloscope not connected")
            return None
        
        try:
            logger.info(f"Retrieving Channel {channel} waveform data (C{channel}:WF? ALL)...")
            
            oscilloscope = self.oscilloscope_service.oscilloscope
            
            # Set timeout for large data transfer
            original_timeout = oscilloscope.timeout
            oscilloscope.timeout = 10000  # 10 seconds for large waveform data
            
            try:
                import struct
                
                # Send query command - waveform data is binary
                oscilloscope.write(f"C{channel}:WF? ALL")
                
                # Read binary data - may need to read in chunks for large waveforms
                raw_data = b''
                max_reads = 1000  # Safety limit
                
                # Read first chunk to see format
                try:
                    first_chunk = oscilloscope.read_raw()
                    raw_data += first_chunk
                    logger.info(f"Read first chunk: {len(first_chunk)} bytes")
                except Exception as e:
                    logger.error(f"Failed to read first chunk: {e}")
                    return None
                
                # Check if it's SCPI binary block format
                if len(raw_data) >= 2 and raw_data[0] == ord('#'):
                    # Parse length from SCPI header
                    num_digits = int(chr(raw_data[1]))
                    if 1 <= num_digits <= 9:
                        length_str = raw_data[2:2+num_digits].decode('ascii')
                        total_length = int(length_str)
                        header_size = 2 + num_digits
                        logger.info(f"SCPI binary block format: total length={total_length}, header={header_size}")
                        
                        # Read remaining data
                        remaining = total_length + header_size - len(raw_data) + 1  # +1 for newline
                        if remaining > 0:
                            logger.info(f"Reading remaining {remaining} bytes...")
                            read_count = 0
                            while len(raw_data) < total_length + header_size + 1 and read_count < max_reads:
                                try:
                                    chunk = oscilloscope.read_raw()
                                    if not chunk:
                                        break
                                    raw_data += chunk
                                    read_count += 1
                                    if read_count % 10 == 0:
                                        logger.debug(f"Read {len(raw_data)} bytes so far...")
                                except Exception as e:
                                    logger.warning(f"Error reading chunk: {e}")
                                    break
                else:
                    # Direct binary - read until we get WAVEDESC and then parse to determine length
                    logger.info("Direct binary format, reading in chunks...")
                    read_count = 0
                    while read_count < max_reads:
                        try:
                            chunk = oscilloscope.read_raw()
                            if not chunk:
                                break
                            raw_data += chunk
                            read_count += 1
                            # Check if we have enough to parse WAVEDESC
                            if len(raw_data) >= 400:
                                wavedesc_pos = raw_data.find(b'WAVEDESC')
                                if wavedesc_pos >= 0:
                                    # Try to parse WAVE_ARRAY_1 length to know how much more to read
                                    try:
                                        wave_array_1_offset = wavedesc_pos + 60
                                        if len(raw_data) >= wave_array_1_offset + 4:
                                            wave_array_1_length = struct.unpack('<I', 
                                                raw_data[wave_array_1_offset:wave_array_1_offset + 4])[0]
                                            wave_descriptor_length = struct.unpack('<I',
                                                raw_data[wavedesc_pos + 36:wavedesc_pos + 40])[0]
                                            user_text_length = struct.unpack('<I',
                                                raw_data[wavedesc_pos + 40:wavedesc_pos + 44])[0]
                                            
                                            expected_total = (wavedesc_pos + wave_descriptor_length + 
                                                             user_text_length + wave_array_1_length)
                                            if len(raw_data) >= expected_total:
                                                logger.info(f"Read complete waveform: {len(raw_data)} bytes")
                                                break
                                    except Exception:
                                        pass
                        except Exception as e:
                            logger.debug(f"Read complete or error: {e}")
                            break
                
                logger.info(f"Retrieved {len(raw_data)} bytes of raw data total")
                
                # Parse SCPI binary block format: #<n><length><data>
                if len(raw_data) < 2 or raw_data[0] != ord('#'):
                    # Data might be direct binary (no SCPI header)
                    # Check if it starts with WAVEDESC
                    if raw_data[:8].startswith(b'WAVEDESC'):
                        logger.info("Waveform data is direct binary (starts with WAVEDESC)")
                        return raw_data
                    else:
                        logger.warning("Waveform data doesn't start with '#' or 'WAVEDESC'")
                        # Try to find WAVEDESC in the data
                        wavedesc_pos = raw_data.find(b'WAVEDESC')
                        if wavedesc_pos >= 0:
                            logger.info(f"Found WAVEDESC at position {wavedesc_pos}, extracting from there")
                            return raw_data[wavedesc_pos:]
                        return raw_data
                
                # Parse SCPI binary block format
                if raw_data[0] == ord('#'):
                    # Extract length digits
                    num_digits = int(chr(raw_data[1]))
                    if num_digits < 1 or num_digits > 9:
                        logger.warning(f"Invalid number of length digits: {num_digits}")
                        return raw_data
                    
                    # Extract length
                    length_str = raw_data[2:2+num_digits].decode('ascii')
                    data_length = int(length_str)
                    
                    # Extract actual binary data (skip header: '#' + num_digits + length_str)
                    header_size = 2 + num_digits
                    waveform_data = raw_data[header_size:header_size + data_length]
                    
                    # Handle potential newline terminator (SCPI standard)
                    if len(raw_data) > header_size + data_length:
                        remaining = raw_data[header_size + data_length:]
                        if remaining.startswith(b'\n') or remaining.startswith(b'\r\n'):
                            logger.debug("Removed newline terminator from waveform data")
                    
                    if len(waveform_data) != data_length:
                        logger.warning(f"Expected {data_length} bytes, got {len(waveform_data)} bytes")
                        # Use what we have if it's close
                        if abs(len(waveform_data) - data_length) <= 2:  # Allow small difference for terminator
                            logger.info(f"Using {len(waveform_data)} bytes (close to expected {data_length})")
                        else:
                            logger.error(f"Data length mismatch too large, cannot proceed")
                            return None
                    
                    logger.info(f"Extracted {len(waveform_data)} bytes of waveform data from SCPI binary block")
                    return waveform_data
                else:
                    # Direct binary data (already handled above)
                    return raw_data
                
            finally:
                # Restore original timeout
                oscilloscope.timeout = original_timeout
                    
        except Exception as e:
            logger.error(f"Error retrieving Channel {channel} waveform: {e}", exc_info=True)
            return None
    
    def _process_channel_cpu_ops(self, waveform_data: bytes, vertical_gain: Optional[float], 
                                  vertical_offset: Optional[float], channel: int) -> Tuple[Optional[float], Optional[float], Optional[int], Optional[int]]:
        """Process CPU-intensive operations for a channel: decode, filter, and analyze.
        
        This method is designed to be called in parallel for multiple channels.
        
        Args:
            waveform_data: Raw binary waveform data
            vertical_gain: Vertical gain value (from query)
            vertical_offset: Vertical offset value (from query)
            channel: Channel number (for logging)
            
        Returns:
            Tuple of (steady_avg, steady_std, steady_start, steady_end) or
            (None, None, None, None) if processing fails
        """
        try:
            # Decode waveform
            decoder = WaveformDecoder(waveform_data)
            descriptor, time_values, voltage_values = decoder.decode(
                vertical_gain=vertical_gain,
                vertical_offset=vertical_offset
            )
            logger.info(f"CH{channel} decoded: {len(voltage_values)} points")
            
            # Apply 10kHz low-pass filter
            try:
                filtered = apply_lowpass_filter(time_values, voltage_values, cutoff_freq=10000.0)
                logger.info(f"CH{channel} filter applied: {len(filtered)} points")
            except Exception as e:
                logger.warning(f"Failed to filter CH{channel}: {e}, using unfiltered data")
                filtered = voltage_values
            
            # Analyze steady state
            steady_avg = None
            steady_std = None
            steady_start = None
            steady_end = None
            try:
                steady_start, steady_end, steady_avg, steady_std = analyze_steady_state(
                    time_values, filtered,
                    variance_threshold_percent=5.0,
                    skip_initial_percent=30.0
                )
                logger.info(f"CH{channel} Steady State: {steady_avg:.6f} V (std: {steady_std:.6f} V)")
            except Exception as e:
                logger.error(f"Failed to analyze CH{channel} steady state: {e}", exc_info=True)
            
            return (steady_avg, steady_std, steady_start, steady_end)
            
        except Exception as e:
            logger.error(f"Error processing CH{channel} CPU operations: {e}", exc_info=True)
            return (None, None, None, None)
    
    def _state_retrieve_waveforms(self) -> bool:
        """Retrieve and analyze CH1 and CH2 waveforms, compute steady state averages.
        
        Optimized: Parallelizes processing after waveform retrieval.
        """
        logger.info("Retrieving and analyzing oscilloscope waveforms...")
        
        if not self.oscilloscope_service.is_connected():
            logger.error("Oscilloscope not connected")
            return False
        
        try:
            # Retrieve waveforms sequentially (oscilloscope communication must be sequential)
            logger.info("")
            logger.info("=" * 70)
            logger.info("Retrieving Channel Waveforms (Sequential)")
            logger.info("=" * 70)
            
            ch1_waveform_data = self._retrieve_channel_waveform(1)
            if ch1_waveform_data is None:
                logger.error("Failed to retrieve CH1 waveform")
                return False
            
            ch2_waveform_data = self._retrieve_channel_waveform(2)
            if ch2_waveform_data is None:
                logger.error("Failed to retrieve CH2 waveform")
                return False
            
            # Query vertical parameters sequentially (oscilloscope I/O must be sequential)
            logger.info("")
            logger.info("=" * 70)
            logger.info("Querying Vertical Parameters (Sequential)")
            logger.info("=" * 70)
            
            # Query CH1 vertical gain and offset
            logger.info("Querying CH1 vertical gain and offset...")
            ch1_vertical_gain = None
            ch1_vertical_offset = None
            try:
                resp = self.oscilloscope_service.send_command("C1:VDIV?")
                if resp:
                    vdiv_match = REGEX_VDIV.search(resp)
                    if vdiv_match:
                        ch1_vertical_gain = float(vdiv_match.group(1))
                    else:
                        numbers = REGEX_NUMBER.findall(resp)
                        if numbers:
                            ch1_vertical_gain = float(numbers[-1])
                
                resp = self.oscilloscope_service.send_command("C1:OFST?")
                if resp:
                    ofst_match = REGEX_OFST.search(resp)
                    if ofst_match:
                        ch1_vertical_offset = float(ofst_match.group(1))
                    else:
                        numbers = REGEX_NUMBER.findall(resp)
                        if numbers:
                            ch1_vertical_offset = float(numbers[-1])
            except Exception as e:
                logger.warning(f"Failed to query CH1 vertical parameters: {e}")
            
            # Query CH2 vertical gain and offset
            logger.info("Querying CH2 vertical gain and offset...")
            ch2_vertical_gain = None
            ch2_vertical_offset = None
            try:
                resp = self.oscilloscope_service.send_command("C2:VDIV?")
                if resp:
                    vdiv_match = REGEX_VDIV.search(resp)
                    if vdiv_match:
                        ch2_vertical_gain = float(vdiv_match.group(1))
                    else:
                        numbers = REGEX_NUMBER.findall(resp)
                        if numbers:
                            ch2_vertical_gain = float(numbers[-1])
                
                resp = self.oscilloscope_service.send_command("C2:OFST?")
                if resp:
                    ofst_match = REGEX_OFST.search(resp)
                    if ofst_match:
                        ch2_vertical_offset = float(ofst_match.group(1))
                    else:
                        numbers = REGEX_NUMBER.findall(resp)
                        if numbers:
                            ch2_vertical_offset = float(numbers[-1])
            except Exception as e:
                logger.warning(f"Failed to query CH2 vertical parameters: {e}")
            
            # Process CPU-intensive operations in parallel (decode, filter, analyze)
            logger.info("")
            logger.info("=" * 70)
            logger.info("Processing Channels in Parallel (Decode, Filter, Analyze)")
            logger.info("=" * 70)
            
            results = {}
            with ThreadPoolExecutor(max_workers=2) as executor:
                # Submit both channels for parallel CPU processing
                future_to_channel = {
                    executor.submit(self._process_channel_cpu_ops, ch1_waveform_data, ch1_vertical_gain, ch1_vertical_offset, 1): 1,
                    executor.submit(self._process_channel_cpu_ops, ch2_waveform_data, ch2_vertical_gain, ch2_vertical_offset, 2): 2
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_channel):
                    channel = future_to_channel[future]
                    try:
                        result = future.result()
                        results[channel] = result
                    except Exception as e:
                        logger.error(f"CH{channel} processing failed: {e}", exc_info=True)
                        results[channel] = (None, None, None, None)
            
            # Extract results
            ch1_steady_avg, ch1_steady_std, ch1_steady_start, ch1_steady_end = results.get(1, (None, None, None, None))
            ch2_steady_avg, ch2_steady_std, ch2_steady_start, ch2_steady_end = results.get(2, (None, None, None, None))
            
            # Print results
            logger.info("")
            logger.info("=" * 70)
            logger.info("OSCILLOSCOPE WAVEFORM ANALYSIS RESULTS")
            logger.info("=" * 70)
            
            print("\n" + "=" * 70)
            print("OSCILLOSCOPE WAVEFORM ANALYSIS RESULTS")
            print("=" * 70)
            
            if ch1_steady_avg is not None:
                logger.info(f"Channel 1 Steady State Average: {ch1_steady_avg:.6f} V")
                logger.info(f"Channel 1 Steady State Std Dev: {ch1_steady_std:.6e} V")
                print(f"Channel 1 Steady State Average: {ch1_steady_avg:.6f} V")
                print(f"Channel 1 Steady State Std Dev: {ch1_steady_std:.6e} V")
            else:
                logger.warning("Channel 1 steady state analysis failed")
                print("Channel 1 steady state analysis failed")
            
            if ch2_steady_avg is not None:
                logger.info(f"Channel 2 Steady State Average: {ch2_steady_avg:.6f} V")
                logger.info(f"Channel 2 Steady State Std Dev: {ch2_steady_std:.6e} V")
                print(f"Channel 2 Steady State Average: {ch2_steady_avg:.6f} V")
                print(f"Channel 2 Steady State Std Dev: {ch2_steady_std:.6e} V")
            else:
                logger.warning("Channel 2 steady state analysis failed")
                print("Channel 2 steady state analysis failed")
            
            print("=" * 70 + "\n")
            logger.info("=" * 70)
            
            self.state = TestState.DONE
            return True
            
        except Exception as e:
            logger.error(f"Failed to retrieve waveforms: {e}", exc_info=True)
            return False
    
    def _detect_steady_state_regions(self, phase_v_values: List[float], 
                                     phase_w_values: List[float], 
                                     timestamps: List[float]) -> Tuple[Optional[int], Optional[int]]:
        """Detect steady state regions by analyzing data characteristics.
        
        This method analyzes the phase current data to intelligently identify:
        - Ramp-up period: When values are changing/increasing
        - Steady-state period: When values are stable
        - Ramp-down period: When values are decreasing
        
        Uses multiple techniques:
        1. Moving window variance analysis
        2. Rate of change (derivative) detection
        3. Statistical stability detection
        
        Args:
            phase_v_values: List of Phase V current values
            phase_w_values: List of Phase W current values
            timestamps: List of timestamps for each data point
            
        Returns:
            Tuple of (ramp_up_end_index, ramp_down_start_index) or (None, None) if detection fails
        """
        import statistics
        
        total_points = len(phase_v_values)
        if total_points < 10:
            logger.warning(f"Insufficient data points ({total_points}) for steady state detection")
            return None, None
        
        # First, identify and discard initial low current period (<1A)
        # Find the start of actual ramp-up when current exceeds 1A (absolute value)
        # Optimized: use NumPy for vectorized operations
        current_threshold = 1.0  # Amperes
        
        if numpy_available:
            phase_v_array = np.array(phase_v_values)
            phase_w_array = np.array(phase_w_values)
            abs_v_array = np.abs(phase_v_array)
            abs_w_array = np.abs(phase_w_array)
            # Find first index where either exceeds threshold
            mask = (abs_v_array >= current_threshold) | (abs_w_array >= current_threshold)
            if np.any(mask):
                initial_discard_end = int(np.argmax(mask))
            else:
                initial_discard_end = 0
        else:
            initial_discard_end = 0
            for i in range(total_points):
                # Check if either phase current exceeds threshold (absolute value)
                abs_v = abs(phase_v_values[i])
                abs_w = abs(phase_w_values[i])
                if abs_v >= current_threshold or abs_w >= current_threshold:
                    initial_discard_end = i
                    break
        
        # If no point exceeds threshold, use first point as start
        if initial_discard_end == 0 and (abs(phase_v_values[0]) >= current_threshold or 
                                         abs(phase_w_values[0]) >= current_threshold):
            initial_discard_end = 0
        
        # Log initial discard information
        if initial_discard_end > 0:
            logger.info(f"Discarding initial {initial_discard_end} points with current < {current_threshold} A")
            logger.debug(f"  Initial period: V range [{min(abs(v) for v in phase_v_values[:initial_discard_end]):.3f}, "
                        f"{max(abs(v) for v in phase_v_values[:initial_discard_end]):.3f}] A, "
                        f"W range [{min(abs(w) for w in phase_w_values[:initial_discard_end]):.3f}, "
                        f"{max(abs(w) for w in phase_w_values[:initial_discard_end]):.3f}] A")
        
        # Slice data to start from ramp-up beginning
        analysis_start = initial_discard_end
        phase_v_analysis = phase_v_values[analysis_start:]
        phase_w_analysis = phase_w_values[analysis_start:]
        timestamps_analysis = timestamps[analysis_start:] if len(timestamps) > analysis_start else timestamps
        
        analysis_points = len(phase_v_analysis)
        if analysis_points < 10:
            logger.warning(f"Insufficient data points ({analysis_points}) after discarding initial low current period")
            return None, None
        
        # Calculate window size for moving statistics (use 5% of remaining data or minimum 5 points)
        window_size = max(5, int(analysis_points * 0.05))
        window_size = min(window_size, analysis_points // 4)  # Don't use more than 25% of data
        
        logger.info(f"Analyzing {analysis_points} data points (after discarding {initial_discard_end} initial points) with window size {window_size}")
        
        # Calculate moving averages and standard deviations for both phases
        # Also calculate rate of change (derivative approximation)
        # Optimized: use NumPy for vectorized operations when available
        if numpy_available:
            phase_v_array = np.array(phase_v_analysis, dtype=np.float64)
            phase_w_array = np.array(phase_w_analysis, dtype=np.float64)
            
            # Calculate rate of change using NumPy diff (much faster)
            if len(timestamps_analysis) > 1:
                dt_array = np.diff(timestamps_analysis)
                # Handle zero or negative dt
                dt_array = np.where(dt_array > 0, dt_array, 1.0)
            else:
                dt_array = np.array([1.0])
            
            dv_array = np.diff(phase_v_array)
            dw_array = np.diff(phase_w_array)
            rate_of_change_v_array = np.abs(dv_array / dt_array)
            rate_of_change_w_array = np.abs(dw_array / dt_array)
            # Pad with zero at the beginning
            rate_of_change_v = [0.0] + rate_of_change_v_array.tolist()
            rate_of_change_w = [0.0] + rate_of_change_w_array.tolist()
            
            # Calculate moving window standard deviations using NumPy
            # Use a more efficient approach with rolling window
            moving_std_v = []
            moving_std_w = []
            half_window = window_size // 2
            
            for i in range(analysis_points):
                start_idx = max(0, i - half_window)
                end_idx = min(analysis_points, i + half_window + 1)
                window_v = phase_v_array[start_idx:end_idx]
                window_w = phase_w_array[start_idx:end_idx]
                
                if len(window_v) > 1:
                    std_v = float(np.std(window_v))
                    std_w = float(np.std(window_w))
                else:
                    std_v = 0.0
                    std_w = 0.0
                
                moving_std_v.append(std_v)
                moving_std_w.append(std_w)
        else:
            # Fallback to Python implementation
            moving_std_v = []
            moving_std_w = []
            rate_of_change_v = []
            rate_of_change_w = []
            
            for i in range(analysis_points):
                # Moving window statistics
                start_idx = max(0, i - window_size // 2)
                end_idx = min(analysis_points, i + window_size // 2 + 1)
                window_v = phase_v_analysis[start_idx:end_idx]
                window_w = phase_w_analysis[start_idx:end_idx]
                
                # Calculate standard deviation in window
                if len(window_v) > 1:
                    std_v = statistics.stdev(window_v)
                    std_w = statistics.stdev(window_w)
                else:
                    std_v = 0.0
                    std_w = 0.0
                
                moving_std_v.append(std_v)
                moving_std_w.append(std_w)
                
                # Calculate rate of change (derivative approximation)
                if i > 0:
                    # Use time difference if available, otherwise assume uniform spacing
                    if len(timestamps_analysis) > i and timestamps_analysis[i] > timestamps_analysis[i-1]:
                        dt = timestamps_analysis[i] - timestamps_analysis[i-1]
                    else:
                        dt = 1.0  # Assume 1 unit time
                    
                    dv_dt = abs((phase_v_analysis[i] - phase_v_analysis[i-1]) / dt)
                    dw_dt = abs((phase_w_analysis[i] - phase_w_analysis[i-1]) / dt)
                else:
                    dv_dt = 0.0
                    dw_dt = 0.0
                
                rate_of_change_v.append(dv_dt)
                rate_of_change_w.append(dw_dt)
        
        # Calculate thresholds for stability
        # Use median + scaled median absolute deviation for robust threshold
        # Optimized: use NumPy for statistics when available
        if numpy_available:
            def median_absolute_deviation(data_array):
                if len(data_array) == 0:
                    return 0.0
                median = np.median(data_array)
                deviations = np.abs(data_array - median)
                return float(np.median(deviations))
        else:
            def median_absolute_deviation(data):
                if not data:
                    return 0.0
                median = statistics.median(data)
                deviations = [abs(x - median) for x in data]
                return statistics.median(deviations) if deviations else 0.0
        
        # Combined metrics for both phases
        if numpy_available:
            combined_std = ((np.array(moving_std_v) + np.array(moving_std_w)) / 2.0).tolist()
            combined_rate = ((np.array(rate_of_change_v) + np.array(rate_of_change_w)) / 2.0).tolist()
            combined_std_array = np.array(combined_std)
            combined_rate_array = np.array(combined_rate)
            
            # Calculate stability thresholds using NumPy
            median_std = float(np.median(combined_std_array))
            mad_std = median_absolute_deviation(combined_std_array)
            std_threshold = median_std + 2.0 * mad_std  # Threshold for "stable" variance
            
            median_rate = float(np.median(combined_rate_array))
            mad_rate = median_absolute_deviation(combined_rate_array)
            rate_threshold = median_rate + 2.0 * mad_rate  # Threshold for "stable" rate of change
        else:
            combined_std = [(v + w) / 2.0 for v, w in zip(moving_std_v, moving_std_w)]
            combined_rate = [(v + w) / 2.0 for v, w in zip(rate_of_change_v, rate_of_change_w)]
            
            # Calculate stability thresholds
            median_std = statistics.median(combined_std)
            mad_std = median_absolute_deviation(combined_std)
            std_threshold = median_std + 2.0 * mad_std  # Threshold for "stable" variance
            
            median_rate = statistics.median(combined_rate)
            mad_rate = median_absolute_deviation(combined_rate)
            rate_threshold = median_rate + 2.0 * mad_rate  # Threshold for "stable" rate of change
        
        logger.debug(f"Stability thresholds - Std: {std_threshold:.4f}, Rate: {rate_threshold:.4f}")
        
        # Find ramp-up end (start of steady state)
        # Look for point where both std and rate of change drop below thresholds
        # Start from beginning and find first stable region
        # Note: These indices are relative to the analysis_start
        ramp_up_end_relative = None
        stable_window_count = 0
        required_stable_points = max(3, window_size // 2)
        
        for i in range(window_size, analysis_points - window_size):
            # Check if this point and surrounding points are stable
            is_stable_std = combined_std[i] <= std_threshold
            is_stable_rate = combined_rate[i] <= rate_threshold
            
            if is_stable_std and is_stable_rate:
                stable_window_count += 1
                if stable_window_count >= required_stable_points:
                    ramp_up_end_relative = i - required_stable_points
                    break
            else:
                stable_window_count = 0
        
        # If no clear ramp-up end found, use a conservative estimate
        if ramp_up_end_relative is None:
            # Find point where rate of change first drops significantly
            for i in range(window_size, analysis_points // 2):
                if combined_rate[i] <= rate_threshold:
                    # Check if next few points are also stable
                    if all(combined_rate[j] <= rate_threshold 
                           for j in range(i, min(i + required_stable_points, analysis_points))):
                        ramp_up_end_relative = i
                        break
        
        # Fallback: use 10% of remaining data if still not found
        if ramp_up_end_relative is None:
            ramp_up_end_relative = max(1, int(analysis_points * 0.1))
            logger.warning(f"Could not detect ramp-up end, using conservative estimate: {ramp_up_end_relative}")
        
        # Find ramp-down start (end of steady state)
        # Look backwards from end for point where std or rate increases
        # Note: These indices are relative to the analysis_start
        ramp_down_start_relative = None
        stable_window_count = 0
        
        for i in range(analysis_points - window_size, ramp_up_end_relative + window_size, -1):
            # Check if this point and surrounding points are stable
            is_stable_std = combined_std[i] <= std_threshold
            is_stable_rate = combined_rate[i] <= rate_threshold
            
            if is_stable_std and is_stable_rate:
                stable_window_count += 1
                if stable_window_count >= required_stable_points:
                    ramp_down_start_relative = i + required_stable_points
                    break
            else:
                stable_window_count = 0
        
        # If no clear ramp-down start found, look for increasing rate of change
        if ramp_down_start_relative is None:
            for i in range(analysis_points - window_size, ramp_up_end_relative + window_size, -1):
                if combined_rate[i] > rate_threshold * 1.5:  # Significant increase
                    # Check if this is sustained (look at points after i)
                    check_end = min(i + required_stable_points, analysis_points)
                    if all(combined_rate[j] > rate_threshold 
                           for j in range(i, check_end)):
                        ramp_down_start_relative = i
                        break
        
        # Fallback: use 90% of remaining data if still not found
        if ramp_down_start_relative is None:
            ramp_down_start_relative = min(analysis_points - 1, int(analysis_points * 0.9))
            logger.warning(f"Could not detect ramp-down start, using conservative estimate: {ramp_down_start_relative}")
        
        # Ensure we have a valid steady state region
        if ramp_up_end_relative >= ramp_down_start_relative:
            # Use middle 60% of remaining data as fallback
            ramp_up_end_relative = int(analysis_points * 0.2)
            ramp_down_start_relative = int(analysis_points * 0.8)
            logger.warning("Steady state region too small, using fallback boundaries")
        
        # Convert relative indices back to absolute indices (accounting for initial discard)
        ramp_up_end = analysis_start + ramp_up_end_relative
        ramp_down_start = analysis_start + ramp_down_start_relative
        
        # Log detection results
        steady_state_points = ramp_down_start - ramp_up_end
        logger.info(f"Steady state detection results:")
        if initial_discard_end > 0:
            logger.info(f"  Initial low current discarded: {initial_discard_end} points ({initial_discard_end/total_points*100:.1f}%)")
        logger.info(f"  Ramp-up end: index {ramp_up_end} ({ramp_up_end/total_points*100:.1f}%)")
        logger.info(f"  Ramp-down start: index {ramp_down_start} ({ramp_down_start/total_points*100:.1f}%)")
        logger.info(f"  Steady state points: {steady_state_points} ({steady_state_points/total_points*100:.1f}%)")
        
        # Calculate and log statistics of detected regions
        if initial_discard_end > 0:
            initial_v = phase_v_values[:initial_discard_end]
            initial_w = phase_w_values[:initial_discard_end]
            logger.debug(f"  Initial low current: {len(initial_v)} points, V range: [{min(initial_v):.3f}, {max(initial_v):.3f}] A, "
                        f"W range: [{min(initial_w):.3f}, {max(initial_w):.3f}] A")
        
        if ramp_up_end > initial_discard_end:
            ramp_up_v = phase_v_values[initial_discard_end:ramp_up_end]
            ramp_up_w = phase_w_values[initial_discard_end:ramp_up_end]
            logger.debug(f"  Ramp-up: {len(ramp_up_v)} points, V range: [{min(ramp_up_v):.3f}, {max(ramp_up_v):.3f}] A, "
                        f"W range: [{min(ramp_up_w):.3f}, {max(ramp_up_w):.3f}] A")
        
        steady_v = phase_v_values[ramp_up_end:ramp_down_start]
        steady_w = phase_w_values[ramp_up_end:ramp_down_start]
        if steady_v:
            logger.debug(f"  Steady state: {len(steady_v)} points, V range: [{min(steady_v):.3f}, {max(steady_v):.3f}] A, "
                        f"W range: [{min(steady_w):.3f}, {max(steady_w):.3f}] A")
        
        if ramp_down_start < total_points:
            ramp_down_v = phase_v_values[ramp_down_start:]
            ramp_down_w = phase_w_values[ramp_down_start:]
            logger.debug(f"  Ramp-down: {len(ramp_down_v)} points, V range: [{min(ramp_down_v):.3f}, {max(ramp_down_v):.3f}] A, "
                        f"W range: [{min(ramp_down_w):.3f}, {max(ramp_down_w):.3f}] A")
        
        return ramp_up_end, ramp_down_start
    
    def _process_can_data(self) -> None:
        """Process collected CAN data to extract steady-state PhaseVCurrent and PhaseWCurrent.
        
        Discards data during ramp up and ramp down periods, then calculates
        average steady-state current values.
        """
        if not self.collected_frames:
            logger.warning("No CAN data collected to process")
            return
        
        if self.ip_status_message is None:
            logger.error("IP_Status_Data message not available for decoding")
            return
        
        logger.info("=" * 70)
        logger.info("Processing CAN Data - Phase Current Analysis")
        logger.info("=" * 70)
        
        # Pre-allocate lists with estimated size for better performance
        estimated_frames = len(self.collected_frames)
        phase_v_values = []
        phase_w_values = []
        timestamps = []
        # Reserve space if possible (Python lists don't have reserve, but this documents intent)
        
        # Extract PhaseVCurrent and PhaseWCurrent from collected frames
        decode_errors = 0
        for timestamp, frame in self.collected_frames:
            # Quick validation before decoding
            if not hasattr(frame, 'data') or not frame.data or len(frame.data) == 0:
                decode_errors += 1
                continue
            
            try:
                # Decode the frame using DBC service
                decoded = self.dbc_service.decode_message(self.ip_status_message, frame.data)
                
                # Check for required signals before appending
                if 'PhaseVCurrent' in decoded and 'PhaseWCurrent' in decoded:
                    phase_v_values.append(decoded['PhaseVCurrent'])
                    phase_w_values.append(decoded['PhaseWCurrent'])
                    timestamps.append(timestamp)
                else:
                    # Missing required signals - log only if unexpected
                    decode_errors += 1
                    logger.debug(f"Frame at {timestamp} missing PhaseVCurrent or PhaseWCurrent signals")
            except Exception as e:
                # Only log if it's not a common/expected error
                decode_errors += 1
                error_str = str(e)
                if 'PhaseVCurrent' not in error_str and 'PhaseWCurrent' not in error_str:
                    logger.debug(f"Failed to decode frame at {timestamp}: {e}")
                continue
        
        if decode_errors > 0:
            logger.debug(f"Encountered {decode_errors} decode errors or missing signals (out of {len(self.collected_frames)} frames)")
        
        if not phase_v_values or not phase_w_values:
            logger.warning("No valid PhaseVCurrent/PhaseWCurrent data found in collected frames")
            return
        
        logger.info(f"Total data points collected: {len(phase_v_values)}")
        
        # Analyze data to intelligently detect steady state regions
        # This replaces hardcoded 20%/80% discard logic with data-driven analysis
        ramp_up_end, ramp_down_start = self._detect_steady_state_regions(
            phase_v_values, phase_w_values, timestamps
        )
        
        if ramp_up_end is None or ramp_down_start is None:
            logger.warning("Could not identify steady state regions from data")
            return
        
        if ramp_up_end >= ramp_down_start:
            logger.warning("Not enough data points to identify steady state")
            return
        
        # Extract steady state data based on detected boundaries
        steady_state_v = phase_v_values[ramp_up_end:ramp_down_start]
        steady_state_w = phase_w_values[ramp_up_end:ramp_down_start]
        
        if not steady_state_v or not steady_state_w:
            logger.warning("No steady state data available after filtering")
            return
        
        # Calculate averages - optimized with NumPy when available
        if numpy_available:
            steady_v_array = np.array(steady_state_v, dtype=np.float64)
            steady_w_array = np.array(steady_state_w, dtype=np.float64)
            avg_phase_v = float(np.mean(steady_v_array))
            avg_phase_w = float(np.mean(steady_w_array))
            
            # Calculate standard deviations for quality check
            try:
                std_phase_v = float(np.std(steady_v_array)) if len(steady_state_v) > 1 else 0.0
                std_phase_w = float(np.std(steady_w_array)) if len(steady_state_w) > 1 else 0.0
            except Exception:
                std_phase_v = 0.0
                std_phase_w = 0.0
        else:
            # Fallback to Python implementation
            avg_phase_v = sum(steady_state_v) / len(steady_state_v)
            avg_phase_w = sum(steady_state_w) / len(steady_state_w)
            
            # Calculate standard deviations for quality check
            import statistics
            try:
                std_phase_v = statistics.stdev(steady_state_v) if len(steady_state_v) > 1 else 0.0
                std_phase_w = statistics.stdev(steady_state_w) if len(steady_state_w) > 1 else 0.0
            except Exception:
                std_phase_v = 0.0
                std_phase_w = 0.0
        
        # Print results
        total_points = len(phase_v_values)
        logger.info("")
        logger.info("=" * 70)
        logger.info("STEADY STATE CURRENT ANALYSIS RESULTS")
        logger.info("=" * 70)
        logger.info(f"Total data points: {total_points}")
        logger.info(f"Ramp up period (discarded): {ramp_up_end} points ({ramp_up_end/total_points*100:.1f}%)")
        logger.info(f"Steady state period: {len(steady_state_v)} points ({len(steady_state_v)/total_points*100:.1f}%)")
        logger.info(f"Ramp down period (discarded): {total_points - ramp_down_start} points ({(total_points - ramp_down_start)/total_points*100:.1f}%)")
        logger.info("")
        logger.info(f"Average Phase V Current: {avg_phase_v:.3f} A (std: {std_phase_v:.3f} A)")
        logger.info(f"Average Phase W Current: {avg_phase_w:.3f} A (std: {std_phase_w:.3f} A)")
        logger.info("")
        logger.info("=" * 70)
        
        # Also print to console for easy visibility
        print("\n" + "=" * 70)
        print("STEADY STATE CURRENT ANALYSIS RESULTS")
        print("=" * 70)
        print(f"Average Phase V Current: {avg_phase_v:.3f} A")
        print(f"Average Phase W Current: {avg_phase_w:.3f} A")
        print("=" * 70 + "\n")
        
        # Plot the phase currents vs time
        self._plot_phase_currents(timestamps, phase_v_values, phase_w_values, 
                                   ramp_up_end, ramp_down_start)
    
    def _plot_phase_currents(self, timestamps: List[float], phase_v_values: List[float], 
                             phase_w_values: List[float], ramp_up_end: int, ramp_down_start: int) -> None:
        """Plot PhaseVCurrent and PhaseWCurrent vs time.
        
        Args:
            timestamps: List of timestamps for each data point
            phase_v_values: List of PhaseVCurrent values
            phase_w_values: List of PhaseWCurrent values
            ramp_up_end: Index where ramp up ends (steady state starts)
            ramp_down_start: Index where steady state ends (ramp down starts)
        """
        if not matplotlib_available:
            logger.warning("Matplotlib not available - skipping plot generation")
            logger.warning("Install matplotlib to enable plotting: pip install matplotlib")
            return
        
        if not timestamps or not phase_v_values or not phase_w_values:
            logger.warning("No data available for plotting")
            return
        
        try:
            # Calculate relative time (seconds from first timestamp)
            if len(timestamps) > 1:
                start_time = timestamps[0]
                time_relative = [(t - start_time) for t in timestamps]
            else:
                time_relative = [0.0]
            
            # Create figure with subplots
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
            
            # Plot Phase V Current
            ax1.plot(time_relative, phase_v_values, 'b-', linewidth=1.5, label='Phase V Current', alpha=0.7)
            
            # Identify initial low current period (<1A) to show as discarded
            current_threshold = 1.0
            initial_discard_end = 0
            for i in range(len(phase_v_values)):
                if abs(phase_v_values[i]) >= current_threshold or abs(phase_w_values[i]) >= current_threshold:
                    initial_discard_end = i
                    break
            
            # Plot regions: Red for discarded (initial low current, ramp-up, and ramp-down), Green for steady-state
            # Initial low current region (discarded): from start to where current exceeds 1A
            if initial_discard_end > 0 and initial_discard_end < len(time_relative):
                ax1.axvspan(time_relative[0], time_relative[initial_discard_end],
                           alpha=0.3, color='orange', label='Initial Low Current <1A (discarded)')
            
            # Ramp-up region (discarded): from initial_discard_end to ramp_up_end
            if ramp_up_end > initial_discard_end and ramp_up_end < len(time_relative):
                ax1.axvspan(time_relative[initial_discard_end], time_relative[ramp_up_end],
                           alpha=0.3, color='red', label='Ramp Up (discarded)')
            
            # Steady-state region (used): from ramp_up_end to ramp_down_start
            if ramp_up_end < ramp_down_start and ramp_down_start <= len(time_relative):
                steady_start_idx = min(ramp_up_end, len(time_relative) - 1)
                steady_end_idx = min(ramp_down_start - 1, len(time_relative) - 1)
                if steady_start_idx <= steady_end_idx:
                    ax1.axvspan(time_relative[steady_start_idx], time_relative[steady_end_idx],
                               alpha=0.3, color='green', label='Steady State (used)')
            
            # Ramp-down region (discarded): from ramp_down_start to end
            if ramp_down_start < len(time_relative):
                ax1.axvspan(time_relative[ramp_down_start], time_relative[-1],
                           alpha=0.3, color='red', label='Ramp Down (discarded)')
            
            ax1.set_ylabel('Phase V Current (A)', fontsize=12)
            ax1.set_title('Phase Currents vs Time (from CAN Data)', fontsize=14, fontweight='bold')
            ax1.grid(True, alpha=0.3)
            ax1.legend(loc='best')
            
            # Plot Phase W Current
            ax2.plot(time_relative, phase_w_values, 'r-', linewidth=1.5, label='Phase W Current', alpha=0.7)
            
            # Plot regions: Red for discarded (initial low current, ramp-up, and ramp-down), Green for steady-state
            # Initial low current region (discarded): from start to where current exceeds 1A
            if initial_discard_end > 0 and initial_discard_end < len(time_relative):
                ax2.axvspan(time_relative[0], time_relative[initial_discard_end],
                           alpha=0.3, color='orange', label='Initial Low Current <1A (discarded)')
            
            # Ramp-up region (discarded): from initial_discard_end to ramp_up_end
            if ramp_up_end > initial_discard_end and ramp_up_end < len(time_relative):
                ax2.axvspan(time_relative[initial_discard_end], time_relative[ramp_up_end],
                           alpha=0.3, color='red', label='Ramp Up (discarded)')
            
            # Steady-state region (used): from ramp_up_end to ramp_down_start
            if ramp_up_end < ramp_down_start and ramp_down_start <= len(time_relative):
                steady_start_idx = min(ramp_up_end, len(time_relative) - 1)
                steady_end_idx = min(ramp_down_start - 1, len(time_relative) - 1)
                if steady_start_idx <= steady_end_idx:
                    ax2.axvspan(time_relative[steady_start_idx], time_relative[steady_end_idx],
                               alpha=0.3, color='green', label='Steady State (used)')
            
            # Ramp-down region (discarded): from ramp_down_start to end
            if ramp_down_start < len(time_relative):
                ax2.axvspan(time_relative[ramp_down_start], time_relative[-1],
                           alpha=0.3, color='red', label='Ramp Down (discarded)')
            
            ax2.set_xlabel('Time (seconds)', fontsize=12)
            ax2.set_ylabel('Phase W Current (A)', fontsize=12)
            ax2.grid(True, alpha=0.3)
            ax2.legend(loc='best')
            
            # Adjust layout
            plt.tight_layout()
            
            # Save plot to file
            plot_filename = f'phase_currents_plot_{int(time.time())}.png'
            plt.savefig(plot_filename, dpi=150, bbox_inches='tight')
            logger.info(f"Plot saved to: {plot_filename}")
            print(f"\nPlot saved to: {plot_filename}")
            
            # Show plot (blocking to ensure window stays open)
            try:
                # Check if we have a display
                import os
                has_display = ('DISPLAY' in os.environ or 
                             sys.platform == 'win32' or 
                             sys.platform == 'darwin')
                
                if has_display:
                    logger.info("Displaying plot window...")
                    print("\n" + "=" * 70)
                    print("DISPLAYING PLOT WINDOW")
                    print("=" * 70)
                    print("A plot window should appear showing Phase V and Phase W currents vs time.")
                    print("Close the plot window to continue.")
                    print("=" * 70 + "\n")
                    plt.show(block=True)  # Block to keep window open until user closes it
                    logger.info("Plot window closed by user")
                    print("Plot window closed.\n")
                else:
                    plt.close()
                    logger.info("No display available - plot saved only")
                    print("No display available - plot saved to file only")
            except Exception as e:
                # If display is not available, just save the file
                plt.close()
                logger.warning(f"Could not display plot (saved to file): {e}")
                print(f"Could not display plot window: {e}")
                print(f"Plot saved to file: {plot_filename}")
            
        except Exception as e:
            logger.error(f"Failed to create plot: {e}", exc_info=True)
            try:
                plt.close('all')
            except Exception:
                pass
    
    def _cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up resources...")
        
        if self.oscilloscope_service:
            try:
                self.oscilloscope_service.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up oscilloscope: {e}")
        
        if self.can_service:
            try:
                self.can_service.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting CAN: {e}")


def main():
    """Main entry point."""
    # Get Iq_ref from user input
    try:
        iq_ref_str = input("Enter Iq_ref value (in Amperes): ").strip()
        iq_ref = float(iq_ref_str)
    except (ValueError, KeyboardInterrupt) as e:
        logger.error(f"Invalid input or cancelled: {e}")
        return 1
    
    # Optional: Get tolerance from user (default: 0.1)
    try:
        tolerance_str = input("Enter tolerance for vertical scale verification (default: 0.1): ").strip()
        tolerance = float(tolerance_str) if tolerance_str else 0.1
    except (ValueError, KeyboardInterrupt):
        tolerance = 0.1
    
    # Create and run state machine
    state_machine = PhaseCurrentTestStateMachine(iq_ref=iq_ref, tolerance=tolerance)
    success = state_machine.run()
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

