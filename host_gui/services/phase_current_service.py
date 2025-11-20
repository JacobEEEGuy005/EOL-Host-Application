"""
Phase Current Calibration Test Service.

This module provides the PhaseCurrentTestStateMachine class for executing
phase current calibration tests with oscilloscope and CAN data collection.
"""
import time
import logging
import struct
from typing import Optional, Tuple, Dict, Any, List

logger = logging.getLogger(__name__)

# Check for optional dependencies
try:
    import numpy as np
    numpy_available = True
except ImportError:
    numpy = None
    numpy_available = False

try:
    import matplotlib
    matplotlib_available = True
except ImportError:
    matplotlib_available = False

# Import utility functions
try:
    from host_gui.utils import (
        analyze_steady_state_can,
        apply_lowpass_filter,
        WaveformDecoder
    )
except ImportError:
    logger.error("Failed to import utility functions for phase current service")
    analyze_steady_state_can = None
    apply_lowpass_filter = None
    WaveformDecoder = None

# Pre-compile regex patterns for oscilloscope command parsing
import re
REGEX_ATTN = re.compile(r'ATTN\s+([\d.]+)', re.IGNORECASE)
REGEX_TDIV = re.compile(r'TDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_VDIV = re.compile(r'VDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_OFST = re.compile(r'OFST\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)

try:
    from PySide6 import QtCore
except ImportError:
    QtCore = None


class PhaseCurrentTestStateMachine:
    """State machine for Phase Current Calibration testing.
    
    This state machine handles the complete test sequence:
    1. Validate oscilloscope settings
    2. Prepare Iq_ref array
    3. Loop through each Iq_ref:
       - Configure vertical scale
       - Start acquisition and CAN logging
       - Send trigger message
       - Wait for test duration
       - Stop acquisition and logging
       - Analyze steady state
       - Store results
    4. Disable test mode
    """
    
    def __init__(self, gui: Any, test: Dict[str, Any]):
        """Initialize the state machine.
        
        Args:
            gui: BaseGUI instance for accessing services
            test: Test configuration dictionary
        """
        self.gui = gui
        self.test = test
        self.act = test.get('actuation', {})
        
        # Services
        self.oscilloscope_service = getattr(gui, 'oscilloscope_service', None)
        self.can_service = getattr(gui, 'can_service', None)
        self.dbc_service = getattr(gui, 'dbc_service', None)
        self.signal_service = getattr(gui, 'signal_service', None)
        
        # Test parameters
        self.min_iq = self.act.get('min_iq')
        self.max_iq = self.act.get('max_iq')
        self.step_iq = self.act.get('step_iq')
        self.ipc_test_duration_ms = self.act.get('ipc_test_duration_ms', 1000)
        
        # CAN message and signal configuration
        # Default to 272 (0x110) if not specified, matching test script
        self.cmd_msg_id = self.act.get('cmd_msg_id', 272)
        self.trigger_signal = self.act.get('trigger_test_signal', 'Mctrl_Phase_I_Test_Enable')
        self.iq_ref_signal = self.act.get('iq_ref_signal', 'Mctrl_Set_Iq_Ref')
        self.id_ref_signal = self.act.get('id_ref_signal', 'Mctrl_Set_Id_Ref')
        
        # Default to 250 (0xFA) if not specified, matching test script
        self.phase_current_can_id = self.act.get('phase_current_can_id', 250)
        self.phase_current_v_signal = self.act.get('phase_current_v_signal', 'PhaseVCurrent')
        self.phase_current_w_signal = self.act.get('phase_current_w_signal', 'PhaseWCurrent')
        
        # State data
        self.iq_ref_array: List[float] = []
        self.current_iq_index = 0
        self.results: List[Dict[str, Any]] = []  # List of (iq_ref, osc_ch1_avg, osc_ch2_avg, can_v_avg, can_w_avg)
        
        # CAN data collection
        self.collecting_can_data = False
        self.collected_signals: List[Tuple[float, float, float]] = []  # List of (timestamp, phase_v_value, phase_w_value) tuples
        
        # Oscilloscope waveform data
        self.ch1_waveform_data: Optional[bytes] = None
        self.ch2_waveform_data: Optional[bytes] = None
        
        # Message objects (cached after finding)
        self.command_message: Optional[Any] = None
        self.phase_current_message: Optional[Any] = None
        
        # Live plot data for Phase V and Phase W
        self.plot_can_v_avg: List[float] = []  # CAN Phase V averages
        self.plot_osc_v_avg: List[float] = []  # Oscilloscope Phase V averages (CH1)
        self.plot_can_w_avg: List[float] = []  # CAN Phase W averages
        self.plot_osc_w_avg: List[float] = []  # Oscilloscope Phase W averages (CH2)
        
        # Initialize live plots if matplotlib is available
        self._init_live_plots()
    
    def _init_live_plots(self) -> None:
        """Initialize live plots for Phase V and Phase W current comparison."""
        if not matplotlib_available:
            logger.debug("Matplotlib not available, skipping live plot initialization")
            return
        
        try:
            # Check if GUI has plot infrastructure
            if not hasattr(self.gui, 'plot_canvas') or self.gui.plot_canvas is None:
                logger.debug("GUI plot canvas not available, skipping live plot initialization")
                return
            
            # Clear existing plot
            if hasattr(self.gui, 'plot_axes') and self.gui.plot_axes is not None:
                self.gui.plot_axes.clear()
            
            # Create two subplots: Phase V and Phase W
            if not hasattr(self.gui, 'plot_figure') or self.gui.plot_figure is None:
                logger.debug("GUI plot figure not available, skipping live plot initialization")
                return
            
            self.gui.plot_figure.clear()
            
            # Create two subplots side by side
            self.gui.plot_axes_v = self.gui.plot_figure.add_subplot(121)  # Phase V
            self.gui.plot_axes_w = self.gui.plot_figure.add_subplot(122)  # Phase W
            
            # Initialize plot lines (scatter plots: Oscilloscope on X, CAN on Y)
            self.gui.plot_line_v, = self.gui.plot_axes_v.plot([], [], 'bo', markersize=6, label='Phase V')
            self.gui.plot_line_w, = self.gui.plot_axes_w.plot([], [], 'ro', markersize=6, label='Phase W')
            
            # Set labels and titles
            self.gui.plot_axes_v.set_xlabel('Average Phase V Current from Oscilloscope (A)')
            self.gui.plot_axes_v.set_ylabel('Average Phase V Current from CAN (A)')
            self.gui.plot_axes_v.set_title('Phase V: CAN vs Oscilloscope')
            self.gui.plot_axes_v.grid(True, alpha=0.3)
            # Add diagonal reference line (y=x) for Phase V
            self.gui.plot_axes_v.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
            # Legend removed for Phase Current test
            
            self.gui.plot_axes_w.set_xlabel('Average Phase W Current from Oscilloscope (A)')
            self.gui.plot_axes_w.set_ylabel('Average Phase W Current from CAN (A)')
            self.gui.plot_axes_w.set_title('Phase W: CAN vs Oscilloscope')
            self.gui.plot_axes_w.grid(True, alpha=0.3)
            # Add diagonal reference line (y=x) for Phase W
            self.gui.plot_axes_w.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
            # Legend removed for Phase Current test
            
            # Tight layout
            self.gui.plot_figure.tight_layout()
            
            # Update canvas
            self.gui.plot_canvas.draw()
            
            logger.info("Live plots initialized for Phase Current test")
        except Exception as e:
            logger.error(f"Failed to initialize live plots: {e}", exc_info=True)
    
    def _update_live_plots(self) -> None:
        """Update live plots with latest data point."""
        if not matplotlib_available:
            return
        
        try:
            if not hasattr(self.gui, 'plot_axes_v') or not hasattr(self.gui, 'plot_axes_w'):
                return
            
            # Get current data lengths
            num_points = len(self.plot_can_v_avg)
            if num_points == 0:
                return
            
            # Filter out NaN values for plotting
            can_v_valid = []
            osc_v_valid = []
            can_w_valid = []
            osc_w_valid = []
            
            for i in range(num_points):
                can_v = self.plot_can_v_avg[i]
                osc_v = self.plot_osc_v_avg[i]
                can_w = self.plot_can_w_avg[i]
                osc_w = self.plot_osc_w_avg[i]
                
                # Only include points where both CAN and Oscilloscope values are valid (not NaN)
                if (isinstance(can_v, (int, float)) and isinstance(osc_v, (int, float)) and
                    not (isinstance(can_v, float) and can_v != can_v) and  # can_v is not NaN
                    not (isinstance(osc_v, float) and osc_v != osc_v)):  # osc_v is not NaN
                    can_v_valid.append(can_v)
                    osc_v_valid.append(osc_v)
                
                if (isinstance(can_w, (int, float)) and isinstance(osc_w, (int, float)) and
                    not (isinstance(can_w, float) and can_w != can_w) and  # can_w is not NaN
                    not (isinstance(osc_w, float) and osc_w != osc_w)):  # osc_w is not NaN
                    can_w_valid.append(can_w)
                    osc_w_valid.append(osc_w)
            
            # Update Phase V plot (Oscilloscope on X, CAN on Y)
            if can_v_valid and osc_v_valid:
                self.gui.plot_line_v.set_data(osc_v_valid, can_v_valid)
                self.gui.plot_axes_v.relim()
                self.gui.plot_axes_v.autoscale()
            
            # Update Phase W plot (Oscilloscope on X, CAN on Y)
            if can_w_valid and osc_w_valid:
                self.gui.plot_line_w.set_data(osc_w_valid, can_w_valid)
                self.gui.plot_axes_w.relim()
                self.gui.plot_axes_w.autoscale()
            
            # Update canvas
            self.gui.plot_canvas.draw()
            self.gui.plot_canvas.draw_idle()
            
        except Exception as e:
            logger.error(f"Failed to update live plots: {e}", exc_info=True)
    
    def run(self) -> Tuple[bool, str]:
        """Execute the complete test sequence.
        
        Returns:
            Tuple of (success: bool, info: str)
        """
        try:
            # Step 1: Validate oscilloscope settings
            if not self._validate_oscilloscope_settings():
                return False, "Oscilloscope settings validation failed"
            
            # Step 2: Prepare Iq_ref array
            if not self._prepare_iq_ref_array():
                return False, "Failed to prepare Iq_ref array"
            
            if not self.iq_ref_array:
                return False, "No Iq_ref values to test"
            
            # Step 3-10: Loop through Iq_ref values
            for iq_ref in self.iq_ref_array:
                logger.info(f"Testing Iq_ref = {iq_ref} A")
                
                # Step 3: Set vertical division
                if not self._set_vertical_division(iq_ref):
                    logger.warning(f"Failed to set vertical division for Iq_ref={iq_ref}, continuing...")
                
                # Step 4: Start oscilloscope acquisition and CAN logging
                if not self._start_acquisition_and_logging():
                    logger.warning(f"Failed to start acquisition for Iq_ref={iq_ref}, continuing...")
                    continue
                
                # Step 5: Send trigger message
                if not self._send_trigger_message(iq_ref):
                    logger.warning(f"Failed to send trigger for Iq_ref={iq_ref}, continuing...")
                    self._stop_acquisition_and_logging()
                    continue
                
                # Step 6: Wait for test duration (collect CAN signals during wait)
                wait_start = time.time()
                wait_duration = self.ipc_test_duration_ms / 1000.0
                poll_interval = 0.1  # Poll every 100ms
                
                logger.info(f"Starting signal collection for {wait_duration:.2f}s (CAN ID: {self.phase_current_can_id}, "
                           f"Signals: {self.phase_current_v_signal}, {self.phase_current_w_signal})")
                
                while time.time() - wait_start < wait_duration:
                    # Collect decoded signals from SignalService cache during wait
                    # Note: Frames are decoded by _poll_frames() and cached in SignalService,
                    # so we collect from the cache instead of competing for raw frames
                    if self.collecting_can_data and self.signal_service:
                        try:
                            # Get latest signal values from cache
                            v_timestamp, v_val = self.signal_service.get_latest_signal(
                                self.phase_current_can_id, 
                                self.phase_current_v_signal
                            )
                            w_timestamp, w_val = self.signal_service.get_latest_signal(
                                self.phase_current_can_id,
                                self.phase_current_w_signal
                            )
                            
                            # Debug: Log if signals are missing
                            if v_val is None:
                                logger.debug(f"Phase V Current not found in cache (CAN ID: {self.phase_current_can_id}, Signal: {self.phase_current_v_signal})")
                            if w_val is None:
                                logger.debug(f"Phase W Current not found in cache (CAN ID: {self.phase_current_can_id}, Signal: {self.phase_current_w_signal})")
                            
                            # If both signals are available and we haven't collected this sample yet
                            if v_val is not None and w_val is not None:
                                # Use the most recent timestamp
                                signal_timestamp = max(
                                    v_timestamp or time.time(),
                                    w_timestamp or time.time()
                                )
                                
                                # Check if this is a new sample (avoid duplicates)
                                # Compare with last collected sample if available
                                is_new_sample = True
                                if self.collected_signals:
                                    last_timestamp, last_v, last_w = self.collected_signals[-1]
                                    # If timestamps are very close (< 1ms), likely the same sample
                                    if abs(signal_timestamp - last_timestamp) < 0.001:
                                        is_new_sample = False
                                
                                if is_new_sample:
                                    logger.info(f"Phase V Current: {v_val} A, Phase W Current: {w_val} A")
                                    self.collected_signals.append((signal_timestamp, v_val, w_val))
                                    
                                    # Update real-time monitoring
                                    if self.gui is not None:
                                        try:
                                            if hasattr(self.gui, 'update_monitor_signal_by_name'):
                                                self.gui.update_monitor_signal_by_name('dut_phase_v_current', v_val)
                                                self.gui.update_monitor_signal_by_name('dut_phase_w_current', w_val)
                                        except Exception as e:
                                            logger.debug(f"Failed to update phase current monitoring: {e}")
                        except Exception as e:
                            logger.warning(f"Failed to collect signals from cache: {e}", exc_info=True)
                    
                    # Process Qt events to keep UI responsive
                    if hasattr(self.gui, 'processEvents'):
                        self.gui.processEvents()
                    elif QtCore and hasattr(QtCore.QCoreApplication, 'processEvents'):
                        QtCore.QCoreApplication.processEvents()
                    
                    # Sleep to avoid excessive polling (frames are decoded by _poll_frames periodically)
                    time.sleep(poll_interval)
                
                # Step 7: Stop oscilloscope and CAN logging
                self._stop_acquisition_and_logging()
                
                # Step 8: Analyze data
                osc_ch1_avg, osc_ch2_avg, can_v_avg, can_w_avg = self._analyze_data()
                
                # Step 9: Append results
                self.results.append({
                    'iq_ref': iq_ref,
                    'osc_ch1_avg': osc_ch1_avg,
                    'osc_ch2_avg': osc_ch2_avg,
                    'can_v_avg': can_v_avg,
                    'can_w_avg': can_w_avg
                })
                
                # Store data for live plots
                if can_v_avg is not None:
                    self.plot_can_v_avg.append(can_v_avg)
                else:
                    self.plot_can_v_avg.append(float('nan'))
                
                if osc_ch1_avg is not None:
                    self.plot_osc_v_avg.append(osc_ch1_avg)
                else:
                    self.plot_osc_v_avg.append(float('nan'))
                
                if can_w_avg is not None:
                    self.plot_can_w_avg.append(can_w_avg)
                else:
                    self.plot_can_w_avg.append(float('nan'))
                
                if osc_ch2_avg is not None:
                    self.plot_osc_w_avg.append(osc_ch2_avg)
                else:
                    self.plot_osc_w_avg.append(float('nan'))
                
                # Update live plots
                self._update_live_plots()
                
                logger.info(f"Iq_ref={iq_ref}: OSC CH1={osc_ch1_avg}, CH2={osc_ch2_avg}, "
                          f"CAN V={can_v_avg}, W={can_w_avg}")
            
            # Step 11: Disable test mode
            self._disable_test_mode()
            
            # Store results for plotting and calculate gain error/correction
            if hasattr(self.gui, '_test_plot_data_temp'):
                test_name = self.test.get('name', 'phase_current_test')
                
                # Calculate gain error and correction factor for Phase V and Phase W
                gain_errors_v = []
                gain_corrections_v = []
                gain_errors_w = []
                gain_corrections_w = []
                
                for r in self.results:
                    osc_v = r.get('osc_ch1_avg')
                    can_v = r.get('can_v_avg')
                    osc_w = r.get('osc_ch2_avg')
                    can_w = r.get('can_w_avg')
                    
                    # Phase V gain error and correction
                    if osc_v is not None and can_v is not None and abs(osc_v) > 1e-10:
                        gain_error_v = ((can_v - osc_v) / osc_v) * 100.0
                        gain_errors_v.append(gain_error_v)
                        if abs(can_v) > 1e-10:
                            gain_correction_v = osc_v / can_v
                            gain_corrections_v.append(gain_correction_v)
                        else:
                            gain_corrections_v.append(float('nan'))
                    else:
                        gain_errors_v.append(float('nan'))
                        gain_corrections_v.append(float('nan'))
                    
                    # Phase W gain error and correction
                    if osc_w is not None and can_w is not None and abs(osc_w) > 1e-10:
                        gain_error_w = ((can_w - osc_w) / osc_w) * 100.0
                        gain_errors_w.append(gain_error_w)
                        if abs(can_w) > 1e-10:
                            gain_correction_w = osc_w / can_w
                            gain_corrections_w.append(gain_correction_w)
                        else:
                            gain_corrections_w.append(float('nan'))
                    else:
                        gain_errors_w.append(float('nan'))
                        gain_corrections_w.append(float('nan'))
                
                # Calculate average gain error and correction factor
                valid_errors_v = [e for e in gain_errors_v if not (isinstance(e, float) and (e != e or abs(e) == float('inf')))]
                valid_corrections_v = [c for c in gain_corrections_v if not (isinstance(c, float) and (c != c or abs(c) == float('inf')))]
                valid_errors_w = [e for e in gain_errors_w if not (isinstance(e, float) and (e != e or abs(e) == float('inf')))]
                valid_corrections_w = [c for c in gain_corrections_w if not (isinstance(c, float) and (c != c or abs(c) == float('inf')))]
                
                avg_gain_error_v = sum(valid_errors_v) / len(valid_errors_v) if valid_errors_v else None
                avg_gain_correction_v = sum(valid_corrections_v) / len(valid_corrections_v) if valid_corrections_v else None
                avg_gain_error_w = sum(valid_errors_w) / len(valid_errors_w) if valid_errors_w else None
                avg_gain_correction_w = sum(valid_corrections_w) / len(valid_corrections_w) if valid_corrections_w else None
                
                self.gui._test_plot_data_temp[test_name] = {
                    'iq_refs': [r['iq_ref'] for r in self.results],
                    'osc_ch1': [r['osc_ch1_avg'] for r in self.results],
                    'osc_ch2': [r['osc_ch2_avg'] for r in self.results],
                    'can_v': [r['can_v_avg'] for r in self.results],
                    'can_w': [r['can_w_avg'] for r in self.results],
                    'gain_errors_v': gain_errors_v,
                    'gain_corrections_v': gain_corrections_v,
                    'gain_errors_w': gain_errors_w,
                    'gain_corrections_w': gain_corrections_w,
                    'avg_gain_error_v': avg_gain_error_v,
                    'avg_gain_correction_v': avg_gain_correction_v,
                    'avg_gain_error_w': avg_gain_error_w,
                    'avg_gain_correction_w': avg_gain_correction_w
                }
            
            info = f"Completed {len(self.results)}/{len(self.iq_ref_array)} test points"
            return True, info
            
        except Exception as e:
            logger.error(f"Phase current test failed: {e}", exc_info=True)
            return False, f"Test execution error: {e}"
    
    def _validate_oscilloscope_settings(self) -> bool:
        """Validate oscilloscope settings against configuration.
        
        Returns:
            True if validation passes, False otherwise
        """
        if not self.oscilloscope_service or not self.oscilloscope_service.is_connected():
            logger.error("Oscilloscope not connected")
            return False
        
        if not hasattr(self.gui, '_oscilloscope_config'):
            logger.error("Oscilloscope configuration not available")
            return False
        
        errors = []
        config = self.gui._oscilloscope_config
        
        # Check enabled channels
        for ch_num in [1, 2]:
            ch_key = f'CH{ch_num}'
            channel_config = config.get('channels', {}).get(ch_key, {})
            expected_enabled = channel_config.get('enabled', False)
            
            if not expected_enabled:
                continue  # Skip disabled channels
            
            # Query trace status
            time.sleep(0.2)
            logger.debug(f"Checking trace status for channel {ch_num}")
            tra_response = self.oscilloscope_service.send_command(f"C{ch_num}:TRA?")
            if tra_response is None:
                errors.append(f"Channel {ch_num}: Failed to query trace status")
                continue
            
            # Parse response
            tra_str = tra_response.strip().upper()
            actual_enabled = 'ON' in tra_str or tra_str == '1' or 'TRUE' in tra_str
            logger.debug(f"Trace enable actual enabled: {actual_enabled}")
            if not actual_enabled:
                errors.append(f"Channel {ch_num}: Expected enabled but trace is OFF")
            
            # Check probe attenuation
            time.sleep(0.2)
            attn_response = self.oscilloscope_service.send_command(f"C{ch_num}:ATTN?")
            logger.debug(f"Attenuation response: {attn_response}")
            if attn_response is None:
                errors.append(f"Channel {ch_num}: Failed to query probe attenuation")
                continue
            
            expected_attenuation = channel_config.get('probe_attenuation', 1.0)
            attn_match = REGEX_ATTN.search(attn_response)
            if attn_match:
                actual_attenuation = float(attn_match.group(1))
                tolerance = 0.5
                if abs(actual_attenuation - expected_attenuation) > tolerance:
                    errors.append(f"Channel {ch_num}: Attenuation mismatch: "
                                f"expected={expected_attenuation}, actual={actual_attenuation}, "
                                f"tolerance={tolerance}")
            else:
                errors.append(f"Channel {ch_num}: Could not parse attenuation")
        
        # Check timebase
        time.sleep(0.2)
        tdiv_response = self.oscilloscope_service.send_command("TDIV?")
        logger.debug(f"Timebase response: {tdiv_response}")
        if tdiv_response is None:
            errors.append("Failed to query timebase")
        else:
            expected_timebase_ms = config.get('acquisition', {}).get('timebase_ms', 1.0)
            tdiv_match = REGEX_TDIV.search(tdiv_response)
            logger.debug(f"Timebase match: {tdiv_match}")
            if tdiv_match:
                actual_tdiv = float(tdiv_match.group(1))
                logger.debug(f"Actual timebase: {actual_tdiv}")
                # Convert TDIV (seconds per division) to milliseconds
                actual_timebase_ms = actual_tdiv * 1000.0
                if abs(actual_timebase_ms - expected_timebase_ms) > 0.01:
                    errors.append(f"Timebase mismatch: expected={expected_timebase_ms}ms, "
                                f"actual={actual_timebase_ms}ms")
            else:
                errors.append("Could not parse timebase")
        
        if errors:
            logger.error(f"Oscilloscope validation errors: {errors}")
            return False
        
        logger.info("Oscilloscope settings validated successfully")
        return True
    
    def _prepare_iq_ref_array(self) -> bool:
        """Prepare array of Iq_ref values from min, max, and step.
        
        Generates positive values from min_iq to max_iq, then negative values
        from -min_iq to -max_iq with the same step size.
        Example: min_iq=10, max_iq=50, step_iq=10 -> [10, 20, 30, 40, 50, -10, -20, -30, -40, -50]
        
        Returns:
            True if array prepared successfully, False otherwise
        """
        if self.min_iq is None or self.max_iq is None or self.step_iq is None:
            logger.error("Missing Iq_ref parameters (min_iq, max_iq, step_iq)")
            return False
        
        if self.step_iq <= 0:
            logger.error(f"Invalid step_iq: {self.step_iq}")
            return False
        
        # Generate array: positive values first, then negative values
        self.iq_ref_array = []
        
        # Generate positive values from min_iq to max_iq
        current = self.min_iq
        while current <= self.max_iq:
            self.iq_ref_array.append(current)
            current += self.step_iq
        
        # Generate negative values from -min_iq to -max_iq
        current = -self.min_iq
        while current >= -self.max_iq:
            self.iq_ref_array.append(current)
            current -= self.step_iq
        
        logger.info(f"Prepared Iq_ref array: {len(self.iq_ref_array)} values "
                   f"[positive: {self.min_iq} to {self.max_iq}, negative: {-self.min_iq} to {-self.max_iq}] "
                   f"with step {self.step_iq}")
        return True
    
    def _set_vertical_division(self, iq_ref: float) -> bool:
        """Set vertical division for both channels.
        
        Args:
            iq_ref: Current Iq reference value
            
        Returns:
            True if successful, False otherwise
        """
        if not self.oscilloscope_service or not self.oscilloscope_service.is_connected():
            return False
        
        # Use absolute value of iq_ref for vertical division
        vdiv_value = abs(iq_ref) / 2.0
        
        try:
            # Set C1:VDIV
            self.oscilloscope_service.send_command(f"C1:VDIV {vdiv_value}")
            time.sleep(0.2)
            
            # Set C2:VDIV
            self.oscilloscope_service.send_command(f"C2:VDIV {vdiv_value}")
            time.sleep(0.2)
            
            logger.info(f"Set vertical division to {vdiv_value} V/div for Iq_ref={iq_ref} A")
            return True
        except Exception as e:
            logger.error(f"Failed to set vertical division: {e}")
            return False
    
    def _start_acquisition_and_logging(self) -> bool:
        """Start oscilloscope acquisition and CAN data logging.
        
        Returns:
            True if successful, False otherwise
        """
        # Start oscilloscope acquisition
        if self.oscilloscope_service and self.oscilloscope_service.is_connected():
            try:
                self.oscilloscope_service.send_command("TRMD AUTO")
                time.sleep(0.2)
                logger.info("Started oscilloscope acquisition")
            except Exception as e:
                logger.error(f"Failed to start oscilloscope acquisition: {e}")
                return False
        
        # Start CAN data logging
        if self.can_service and self.can_service.is_connected():
            self.collecting_can_data = True
            self.collected_signals = []
            logger.info("Started CAN data logging")
        
        return True
    
    def _send_trigger_message(self, iq_ref: float) -> bool:
        """Send trigger message with test enable and Iq_ref.
        
        Args:
            iq_ref: Current Iq reference value
            
        Returns:
            True if successful, False otherwise
        """
        if not self.can_service or not self.can_service.is_connected():
            logger.error("CAN service not connected")
            return False
        
        if not self.dbc_service or not self.dbc_service.is_loaded():
            logger.error("DBC service not loaded")
            return False
        
        # Find command message if not cached
        if self.command_message is None:
            if self.cmd_msg_id is None:
                logger.error("Command message ID not specified")
                return False
            self.command_message = self.dbc_service.find_message_by_id(self.cmd_msg_id)
            if self.command_message is None:
                logger.error(f"Command message (ID {self.cmd_msg_id}) not found in DBC")
                return False
        
        try:
            # Encode message with signal values
            # MessageType 20 (m20) is the multiplexor for phase current test signals
            signal_values = {
                'DeviceID': 0x03,  # IPC_Hardware = 0x03
                'MessageType': 20,  # MessageType 20 (m20) for phase current test
                self.trigger_signal: 1,
                self.iq_ref_signal: iq_ref,
                self.id_ref_signal: 0.0
            }
            
            # Encode using DBC service
            frame_data = self.dbc_service.encode_message(self.command_message, signal_values)
            
            # Create and send frame
            from backend.adapters.interface import Frame
            frame = Frame(
                can_id=self.cmd_msg_id,
                data=frame_data,
                timestamp=None
            )
            
            logger.info(f"Sending trigger message: Iq_ref={iq_ref} A")
            if not self.can_service.send_frame(frame):
                logger.error("Failed to send trigger message")
                return False
            
            # Track sent command values for monitoring
            if self.gui is not None:
                try:
                    if hasattr(self.gui, 'track_sent_command_value'):
                        self.gui.track_sent_command_value('set_iq', iq_ref)
                        self.gui.track_sent_command_value('set_id', 0.0)  # id_ref is always 0.0 in current implementation
                except Exception as e:
                    logger.debug(f"Failed to track sent command values: {e}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to send trigger message: {e}", exc_info=True)
            return False
    
    def _stop_acquisition_and_logging(self) -> None:
        """Stop oscilloscope acquisition and CAN data logging."""
        # Stop oscilloscope
        if self.oscilloscope_service and self.oscilloscope_service.is_connected():
            try:
                self.oscilloscope_service.send_command("STOP")
                time.sleep(0.2)
                logger.info("Stopped oscilloscope acquisition")
            except Exception as e:
                logger.warning(f"Failed to stop oscilloscope: {e}")
        
        # Stop CAN data logging
        self.collecting_can_data = False
        logger.info(f"Stopped CAN data logging (collected {len(self.collected_signals)} signal samples)")
    
    def _analyze_data(self) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Analyze oscilloscope and CAN data to compute steady state averages.
        
        Returns:
            Tuple of (osc_ch1_avg, osc_ch2_avg, can_v_avg, can_w_avg)
        """
        osc_ch1_avg = None
        osc_ch2_avg = None
        can_v_avg = None
        can_w_avg = None
        
        # Analyze oscilloscope data
        try:
            osc_ch1_avg, osc_ch2_avg = self._analyze_oscilloscope_data()
        except Exception as e:
            logger.error(f"Failed to analyze oscilloscope data: {e}", exc_info=True)
        
        # Analyze CAN data
        try:
            can_v_avg, can_w_avg = self._analyze_can_data()
        except Exception as e:
            logger.error(f"Failed to analyze CAN data: {e}", exc_info=True)
        
        return osc_ch1_avg, osc_ch2_avg, can_v_avg, can_w_avg
    
    def _analyze_oscilloscope_data(self) -> Tuple[Optional[float], Optional[float]]:
        """Retrieve and analyze oscilloscope waveforms.
        
        Returns:
            Tuple of (ch1_avg, ch2_avg)
        """
        if not self.oscilloscope_service or not self.oscilloscope_service.is_connected():
            return None, None
        
        ch1_avg = None
        ch2_avg = None
        
        try:
            # Retrieve CH1 waveform
            ch1_data = self._retrieve_channel_waveform(1)
            if ch1_data:
                ch1_avg = self._analyze_waveform(ch1_data, 1)
            
            # Retrieve CH2 waveform
            ch2_data = self._retrieve_channel_waveform(2)
            if ch2_data:
                ch2_avg = self._analyze_waveform(ch2_data, 2)
        except Exception as e:
            logger.error(f"Failed to analyze oscilloscope waveforms: {e}", exc_info=True)
        
        return ch1_avg, ch2_avg
    
    def _retrieve_channel_waveform(self, channel: int) -> Optional[bytes]:
        """Retrieve waveform data for a specific channel.
        
        This method uses chunked reading to handle large waveform data transfers,
        similar to the test script implementation. It supports both SCPI binary
        block format and direct binary format.
        
        Args:
            channel: Channel number (1 or 2)
            
        Returns:
            Binary waveform data or None if retrieval fails
        """
        if not self.oscilloscope_service or not self.oscilloscope_service.is_connected():
            logger.error("Oscilloscope not connected")
            return None
        
        try:
            logger.info(f"Retrieving Channel {channel} waveform data (C{channel}:WF? ALL)...")
            
            oscilloscope = self.oscilloscope_service.oscilloscope
            
            # Set timeout for large data transfer
            original_timeout = oscilloscope.timeout
            oscilloscope.timeout = 10000  # 10 seconds for large waveform data
            
            try:
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
            logger.error(f"Error retrieving CH{channel} waveform: {e}", exc_info=True)
            return None
    
    def _analyze_waveform(self, waveform_data: bytes, channel: int) -> Optional[float]:
        """Analyze waveform data to compute steady state average.
        
        This method queries C{channel}:VDIV? and C{channel}:OFST? to get the
        vertical gain and offset, which are used to convert raw waveform values
        to physical voltage values using the formula:
        voltage = (vertical_gain * raw_value) / 25.0 - vertical_offset
        
        Args:
            waveform_data: Raw waveform data bytes
            channel: Channel number (1 or 2)
            
        Returns:
            Average voltage in steady state region, or None if analysis fails
        """
        if not WaveformDecoder:
            logger.error("WaveformDecoder not available")
            return None
        
        try:
            # Query vertical gain from C{channel}:VDIV?
            vdiv_resp = self.oscilloscope_service.send_command(f"C{channel}:VDIV?")
            vertical_gain = None
            if vdiv_resp:
                vdiv_match = REGEX_VDIV.search(vdiv_resp)
                if vdiv_match:
                    try:
                        vertical_gain = float(vdiv_match.group(1))
                        logger.info(f"CH{channel}: Queried VDIV = {vertical_gain} V/div")
                    except ValueError:
                        logger.warning(f"CH{channel}: Failed to parse VDIV response: {vdiv_resp}")
                else:
                    logger.warning(f"CH{channel}: VDIV response format not recognized: {vdiv_resp}")
            else:
                logger.warning(f"CH{channel}: No response from C{channel}:VDIV?")
            
            # Query vertical offset from C{channel}:OFST?
            ofst_resp = self.oscilloscope_service.send_command(f"C{channel}:OFST?")
            vertical_offset = None
            if ofst_resp:
                ofst_match = REGEX_OFST.search(ofst_resp)
                if ofst_match:
                    try:
                        vertical_offset = float(ofst_match.group(1))
                        logger.info(f"CH{channel}: Queried OFST = {vertical_offset} V")
                    except ValueError:
                        logger.warning(f"CH{channel}: Failed to parse OFST response: {ofst_resp}")
                else:
                    logger.warning(f"CH{channel}: OFST response format not recognized: {ofst_resp}")
            else:
                logger.warning(f"CH{channel}: No response from C{channel}:OFST?")
            
            # Decode waveform using queried vertical gain and offset
            # If query failed, decoder will fall back to descriptor values
            decoder = WaveformDecoder(waveform_data)
            descriptor, time_values, voltage_values = decoder.decode(
                vertical_gain=vertical_gain,
                vertical_offset=vertical_offset
            )
            
            # Log which values were used
            if vertical_gain is not None:
                logger.debug(f"CH{channel}: Using vertical gain from C{channel}:VDIV? = {vertical_gain} V/div")
            else:
                logger.debug(f"CH{channel}: Using vertical gain from descriptor = {descriptor.get('VERTICAL_GAIN', 'N/A')}")
            
            if vertical_offset is not None:
                logger.debug(f"CH{channel}: Using vertical offset from C{channel}:OFST? = {vertical_offset} V")
            else:
                logger.debug(f"CH{channel}: Using vertical offset from descriptor = {descriptor.get('VERTICAL_OFFSET', 'N/A')}")
            
            if not voltage_values or len(voltage_values) < 10:
                logger.warning(f"Insufficient waveform data for CH{channel}")
                return None
            
            # Apply 10kHz low-pass filter (matching test script)
            if not apply_lowpass_filter:
                logger.warning("apply_lowpass_filter not available, using unfiltered data")
                filtered_voltage_values = voltage_values
            else:
                try:
                    filtered_voltage_values = apply_lowpass_filter(
                        time_values, voltage_values, cutoff_freq=10000.0
                    )
                    logger.info(f"CH{channel} filter applied: {len(filtered_voltage_values)} points")
                except Exception as e:
                    logger.warning(f"Failed to filter CH{channel}: {e}, using unfiltered data")
                    filtered_voltage_values = voltage_values
            
            # Discard initial data points below threshold (after filtering)
            voltage_threshold = 2.0  # Volts
            initial_discard_end = 0
            total_points = len(filtered_voltage_values)
            
            if numpy_available:
                filtered_array = np.array(filtered_voltage_values)
                abs_array = np.abs(filtered_array)
                # Find first index where voltage exceeds threshold
                mask = abs_array >= voltage_threshold
                if np.any(mask):
                    initial_discard_end = int(np.argmax(mask))
                else:
                    initial_discard_end = 0
            else:
                # Manual search without numpy
                for i in range(total_points):
                    abs_voltage = abs(filtered_voltage_values[i])
                    if abs_voltage >= voltage_threshold:
                        initial_discard_end = i
                        break
            
            # If no point exceeds threshold, use first point as start
            if initial_discard_end == 0 and abs(filtered_voltage_values[0]) >= voltage_threshold:
                initial_discard_end = 0
            
            # Log initial discard information
            if initial_discard_end > 0:
                logger.info(f"CH{channel}: Discarding initial {initial_discard_end} points with voltage < {voltage_threshold} V (after filtering)")
                logger.debug(f"  Initial period: voltage range [{min(abs(v) for v in filtered_voltage_values[:initial_discard_end]):.6f}, "
                            f"{max(abs(v) for v in filtered_voltage_values[:initial_discard_end]):.6f}] V")
            
            # Slice data to start from threshold beginning
            analysis_start = initial_discard_end
            filtered_voltage_values = filtered_voltage_values[analysis_start:]
            time_values = time_values[analysis_start:]
            
            if not filtered_voltage_values or len(filtered_voltage_values) < 10:
                logger.warning(f"CH{channel}: After filtering initial low voltage data, insufficient data points for steady state analysis")
                return None
            
            # Analyze steady state using filtered and threshold-discarded data
            if not analyze_steady_state_can:
                logger.error("analyze_steady_state_can not available")
                return None
            
            start_idx, end_idx, avg, std = analyze_steady_state_can(
                time_values, filtered_voltage_values,
                variance_threshold_percent=5.0,
                skip_initial_percent=30.0
            )
            
            if avg is not None:
                logger.info(f"CH{channel} steady state: avg={avg:.6f} V, std={std:.6f} V")
                return avg
            else:
                logger.warning(f"Failed to find steady state for CH{channel}")
                return None
        except Exception as e:
            logger.error(f"Failed to analyze CH{channel} waveform: {e}", exc_info=True)
            return None
    
    def _analyze_can_data(self) -> Tuple[Optional[float], Optional[float]]:
        """Analyze CAN data to compute steady state averages.
        
        Returns:
            Tuple of (v_avg, w_avg)
        """
        if not self.collected_signals:
            logger.warning("No CAN signals collected")
            return None, None
        
        # Extract signal values and timestamps (already decoded)
        v_values = []
        w_values = []
        timestamps = []
        
        for timestamp, v_val, w_val in self.collected_signals:
            v_values.append(v_val)
            w_values.append(w_val)
            timestamps.append(timestamp)
        
        if not v_values or not w_values:
            logger.warning("No valid phase current data found in collected signals")
            return None, None
        
        # Filter out initial data points where Phase Current < 2A
        current_threshold = 2.0  # Amperes
        initial_discard_end = 0
        total_points = len(v_values)
        
        if numpy_available:
            v_array = np.array(v_values)
            w_array = np.array(w_values)
            abs_v_array = np.abs(v_array)
            abs_w_array = np.abs(w_array)
            # Find first index where either phase exceeds threshold
            mask = (abs_v_array >= current_threshold) | (abs_w_array >= current_threshold)
            if np.any(mask):
                initial_discard_end = int(np.argmax(mask))
            else:
                initial_discard_end = 0
        else:
            # Manual search without numpy
            for i in range(total_points):
                abs_v = abs(v_values[i])
                abs_w = abs(w_values[i])
                if abs_v >= current_threshold or abs_w >= current_threshold:
                    initial_discard_end = i
                    break
        
        # If no point exceeds threshold, use first point as start
        if initial_discard_end == 0 and (abs(v_values[0]) >= current_threshold or 
                                         abs(w_values[0]) >= current_threshold):
            initial_discard_end = 0
        
        # Log initial discard information
        if initial_discard_end > 0:
            logger.info(f"Discarding initial {initial_discard_end} points with current < {current_threshold} A")
            logger.debug(f"  Initial period: V range [{min(abs(v) for v in v_values[:initial_discard_end]):.3f}, "
                        f"{max(abs(v) for v in v_values[:initial_discard_end]):.3f}] A, "
                        f"W range [{min(abs(w) for w in w_values[:initial_discard_end]):.3f}, "
                        f"{max(abs(w) for w in w_values[:initial_discard_end]):.3f}] A")
        
        # Slice data to start from ramp-up beginning
        analysis_start = initial_discard_end
        v_values_filtered = v_values[analysis_start:]
        w_values_filtered = w_values[analysis_start:]
        timestamps_filtered = timestamps[analysis_start:]
        
        if not v_values_filtered or not w_values_filtered:
            logger.warning(f"After filtering initial low current data, insufficient data points for steady state analysis")
            return None, None
        
        # Analyze steady state on filtered data
        if not analyze_steady_state_can:
            logger.error("analyze_steady_state_can not available")
            return None, None
        
        v_start, v_end, v_avg, v_std = analyze_steady_state_can(timestamps_filtered, v_values_filtered)
        w_start, w_end, w_avg, w_std = analyze_steady_state_can(timestamps_filtered, w_values_filtered)
        
        logger.info(f"CAN analysis: V avg={v_avg}, W avg={w_avg}")
        return v_avg, w_avg
    
    def _disable_test_mode(self) -> None:
        """Send message to disable test mode."""
        if not self.can_service or not self.can_service.is_connected():
            return
        
        if not self.dbc_service or not self.dbc_service.is_loaded():
            return
        
        if self.command_message is None:
            return
        
        try:
            signal_values = {
                'DeviceID': 0x03,
                'MessageType': 20,
                self.trigger_signal: 0,
                self.iq_ref_signal: 0.0,
                self.id_ref_signal: 0.0
            }
            
            frame_data = self.dbc_service.encode_message(self.command_message, signal_values)
            from backend.adapters.interface import Frame
            frame = Frame(
                can_id=self.cmd_msg_id,
                data=frame_data,
                timestamp=None
            )
            
            self.can_service.send_frame(frame)
            logger.info("Sent disable test mode message")
        except Exception as e:
            logger.error(f"Failed to send disable message: {e}", exc_info=True)

