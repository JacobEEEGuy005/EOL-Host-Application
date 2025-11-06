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
from typing import Optional, Dict, Any
from pathlib import Path

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
                attn_match = re.search(r'ATTN\s+([\d.]+)', resp, re.IGNORECASE)
                if attn_match:
                    c1_attn = float(attn_match.group(1))
                    logger.info(f"C1:ATTN? = {c1_attn}")
                else:
                    # Fallback: extract last number
                    numbers = re.findall(r'([\d.]+)', resp)
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
                attn_match = re.search(r'ATTN\s+([\d.]+)', resp, re.IGNORECASE)
                if attn_match:
                    c2_attn = float(attn_match.group(1))
                    logger.info(f"C2:ATTN? = {c2_attn}")
                else:
                    # Fallback: extract last number
                    numbers = re.findall(r'([\d.]+)', resp)
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
            logger.info("Setting TDIV:1")
            self.oscilloscope_service.send_command("TDIV:1")
            time.sleep(0.2)
            
            # Readback TDIV?
            resp = self.oscilloscope_service.send_command("TDIV?")
            if resp is None:
                logger.error("TDIV? - No response")
                return False
            
            # Parse timebase value
            tdiv_match = re.search(r'TDIV\s+([\d.]+)', resp, re.IGNORECASE)
            if tdiv_match:
                tdiv_value = float(tdiv_match.group(1))
            else:
                # Fallback: extract number
                numbers = re.findall(r'([\d.]+)', resp)
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
                vdiv_match = re.search(r'VDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', resp, re.IGNORECASE)
                if vdiv_match:
                    try:
                        c1_vdiv = float(vdiv_match.group(1))
                    except ValueError:
                        errors.append(f"C1:VDIV? - Could not convert to float: {vdiv_match.group(1)}")
                        c1_vdiv = None
                else:
                    # Fallback: try to find any number (including exponential) in the response
                    numbers = re.findall(r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', resp)
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
                vdiv_match = re.search(r'VDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', resp, re.IGNORECASE)
                if vdiv_match:
                    try:
                        c2_vdiv = float(vdiv_match.group(1))
                    except ValueError:
                        errors.append(f"C2:VDIV? - Could not convert to float: {vdiv_match.group(1)}")
                        c2_vdiv = None
                else:
                    # Fallback: try to find any number (including exponential) in the response
                    numbers = re.findall(r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', resp)
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
            # Wait 4 seconds
            time.sleep(4.0)
            
            # Send STOP command
            logger.info("Sending STOP command to stop data acquisition")
            self.oscilloscope_service.send_command("STOP")
            time.sleep(0.2)
            
            logger.info("Data acquisition stopped")
            self.state = TestState.DONE
            return True
            
        except Exception as e:
            logger.error(f"Failed in wait_and_stop: {e}", exc_info=True)
            return False
    
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

