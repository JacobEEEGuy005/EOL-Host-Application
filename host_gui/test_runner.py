"""
Test Runner for EOL Host Application.

This module contains the TestRunner class that encapsulates single-test execution logic.
Extracted from main.py for better modularity.
"""
import time
import logging
from typing import Optional, Tuple, Dict, Any, Callable

from PySide6 import QtCore, QtWidgets

logger = logging.getLogger(__name__)

# Import services and utilities
try:
    from host_gui.services.phase_current_service import PhaseCurrentTestStateMachine
except ImportError:
    logger.error("Failed to import PhaseCurrentTestStateMachine")
    PhaseCurrentTestStateMachine = None

# Import constants
try:
    from host_gui.constants import (
        CAN_ID_MIN, CAN_ID_MAX, DWELL_TIME_DEFAULT, DWELL_TIME_MIN,
        SLEEP_INTERVAL_SHORT, SLEEP_INTERVAL_MEDIUM, MSG_TYPE_SET_RELAY,
        DAC_VOLTAGE_MIN, DAC_VOLTAGE_MAX, DAC_SETTLING_TIME_MS, DATA_COLLECTION_PERIOD_MS,
        POLL_INTERVAL_MS
    )
except ImportError:
    logger.error("Failed to import constants")
    CAN_ID_MIN = 0
    CAN_ID_MAX = 0x1FFFFFFF
    DWELL_TIME_DEFAULT = 100
    DWELL_TIME_MIN = 10
    SLEEP_INTERVAL_SHORT = 0.01
    SLEEP_INTERVAL_MEDIUM = 0.1
    MSG_TYPE_SET_RELAY = 1
    DAC_VOLTAGE_MIN = 0
    DAC_VOLTAGE_MAX = 5000
    DAC_SETTLING_TIME_MS = 50
    DATA_COLLECTION_PERIOD_MS = 200
    POLL_INTERVAL_MS = 50

# Import adapter interface
try:
    from backend.adapters.interface import Frame as AdapterFrame
except ImportError:
    AdapterFrame = None


class TestRunner:
    """Lightweight test runner that encapsulates single-test execution logic.

    This class handles the execution of individual test cases, including:
    - Digital tests: Setting relay states and verifying feedback
    - Analog tests: Stepping DAC voltages and monitoring feedback signals
    - Phase Current Calibration: State machine-based oscilloscope and CAN data collection
    
    The TestRunner can be initialized with either:
    1. A GUI instance (legacy mode - services extracted from GUI)
    2. Services and callbacks directly (new decoupled mode)
    
    Attributes:
        gui: Optional reference to BaseGUI instance (for backward compatibility)
        can_service: CanService instance
        dbc_service: DbcService instance
        signal_service: SignalService instance
        oscilloscope_service: Optional oscilloscope service
        eol_hw_config: Optional EOL hardware configuration
        plot_update_callback: Optional callback for plot updates
        plot_clear_callback: Optional callback to clear plots
        label_update_callback: Optional callback to update UI labels
        oscilloscope_init_callback: Optional callback to initialize oscilloscope
    """
    
    def __init__(
        self,
        gui: Optional['BaseGUI'] = None,
        can_service: Optional[Any] = None,
        dbc_service: Optional[Any] = None,
        signal_service: Optional[Any] = None,
        oscilloscope_service: Optional[Any] = None,
        eol_hw_config: Optional[Dict[str, Any]] = None,
        plot_update_callback: Optional[Callable[[float, float, Optional[str]], None]] = None,
        plot_clear_callback: Optional[Callable[[], None]] = None,
        label_update_callback: Optional[Callable[[str], None]] = None,
        oscilloscope_init_callback: Optional[Callable[[Dict[str, Any]], bool]] = None
    ):
        """Initialize the TestRunner.
        
        Args:
            gui: Optional BaseGUI instance (for backward compatibility)
            can_service: Optional CanService instance (if not provided, extracted from GUI)
            dbc_service: Optional DbcService instance (if not provided, extracted from GUI)
            signal_service: Optional SignalService instance (if not provided, extracted from GUI)
            oscilloscope_service: Optional oscilloscope service
            eol_hw_config: Optional EOL hardware configuration dictionary
            plot_update_callback: Optional callback for plot updates (dac_voltage, feedback_value, test_name)
            plot_clear_callback: Optional callback to clear plots
            label_update_callback: Optional callback to update UI labels (text)
            oscilloscope_init_callback: Optional callback to initialize oscilloscope (test) -> bool
        """
        self.gui = gui
        
        # Extract services from GUI if not provided directly (backward compatibility)
        if gui is not None:
            self.can_service = can_service or getattr(gui, 'can_service', None)
            self.dbc_service = dbc_service or getattr(gui, 'dbc_service', None)
            self.signal_service = signal_service or getattr(gui, 'signal_service', None)
            self.oscilloscope_service = oscilloscope_service or getattr(gui, 'oscilloscope_service', None)
            self.eol_hw_config = eol_hw_config or getattr(gui, '_eol_hw_config', None)
            
            # Create callbacks from GUI methods if not provided
            if plot_update_callback is None and hasattr(gui, '_update_plot'):
                self.plot_update_callback = lambda dac, fb, name: gui._update_plot(dac, fb, name)
            else:
                self.plot_update_callback = plot_update_callback
            
            if plot_clear_callback is None and hasattr(gui, '_clear_plot'):
                self.plot_clear_callback = lambda: gui._clear_plot()
            else:
                self.plot_clear_callback = plot_clear_callback
            
            if label_update_callback is None and hasattr(gui, 'current_signal_label'):
                self.label_update_callback = lambda text: gui.current_signal_label.setText(str(text))
            else:
                self.label_update_callback = label_update_callback
            
            if oscilloscope_init_callback is None and hasattr(gui, '_initialize_oscilloscope_for_test'):
                self.oscilloscope_init_callback = lambda test: gui._initialize_oscilloscope_for_test(test)
            else:
                self.oscilloscope_init_callback = oscilloscope_init_callback
        else:
            # Direct service injection mode (fully decoupled)
            self.can_service = can_service
            self.dbc_service = dbc_service
            self.signal_service = signal_service
            self.oscilloscope_service = oscilloscope_service
            self.eol_hw_config = eol_hw_config or {}
            self.plot_update_callback = plot_update_callback
            self.plot_clear_callback = plot_clear_callback
            self.label_update_callback = label_update_callback
            self.oscilloscope_init_callback = oscilloscope_init_callback

    def run_single_test(self, test: Dict[str, Any], timeout: float = 1.0) -> Tuple[bool, str]:
        """Execute a single test using the same behavior as the previous
        BaseGUI._run_single_test implementation. 
        
        Args:
            test: Test configuration dictionary with 'name', 'actuation', etc.
            timeout: Timeout in seconds for feedback waiting
            
        Returns:
            Tuple of (success: bool, info: str)
        """
        # Ensure adapter running - check CanService
        adapter_available = (self.can_service is not None and self.can_service.is_connected())
        if not adapter_available:
            logger.error("Attempted to run test without adapter running")
            raise RuntimeError('Adapter not running')
        act = test.get('actuation', {})
        
        # Initialize oscilloscope before phase current tests
        if act.get('type') == 'phase_current_calibration':
            if self.oscilloscope_service and self.oscilloscope_init_callback:
                osc_init_success = self.oscilloscope_init_callback(test)
                if not osc_init_success:
                    logger.warning("Oscilloscope initialization failed, continuing test anyway")
            
            # Execute phase current test using state machine
            # Note: PhaseCurrentTestStateMachine still needs GUI reference for plot updates
            # This is a limitation that should be addressed in future refactoring
            try:
                # Use GUI if available, otherwise create a proxy
                gui_for_state_machine = self.gui
                if gui_for_state_machine is None:
                    # Create minimal proxy for PhaseCurrentTestStateMachine
                    # This is temporary until PhaseCurrentTestStateMachine is fully decoupled
                    gui_for_state_machine = self._create_gui_proxy()
                
                state_machine = PhaseCurrentTestStateMachine(gui_for_state_machine, test)
                
                # Store state machine reference if GUI is available
                if self.gui is not None:
                    self.gui._phase_current_state_machine = state_machine
                
                try:
                    success, info = state_machine.run()
                    return success, info
                finally:
                    # Clean up state machine reference
                    if self.gui is not None and hasattr(self.gui, '_phase_current_state_machine'):
                        delattr(self.gui, '_phase_current_state_machine')
            except Exception as e:
                logger.error(f"Phase current test execution failed: {e}", exc_info=True)
                return False, f"Phase current test error: {e}"
        
        try:
            if act.get('type') == 'digital' and act.get('can_id') is not None:
                can_id = act.get('can_id')
                
                # Validate CAN ID
                try:
                    can_id = int(can_id)
                    if not (CAN_ID_MIN <= can_id <= CAN_ID_MAX):
                        raise ValueError(f"Invalid digital test CAN ID: {can_id}")
                except (ValueError, TypeError) as e:
                    logger.error(f"Invalid CAN ID in digital test configuration: {e}")
                    return False, f"Invalid CAN ID: {can_id}"
                
                sig = act.get('signal')
                low_val = act.get('value_low', act.get('value'))
                high_val = act.get('value_high')
                
                # Validate dwell time
                try:
                    dwell_ms = int(act.get('dwell_ms', act.get('dac_dwell_ms', DWELL_TIME_DEFAULT)))
                    if dwell_ms < 0:
                        raise ValueError(f"Dwell time must be non-negative, got {dwell_ms}")
                    if dwell_ms == 0:
                        dwell_ms = DWELL_TIME_MIN
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid dwell time in digital test, using {DWELL_TIME_DEFAULT}ms: {e}")
                    dwell_ms = DWELL_TIME_DEFAULT

                def _encode_value_to_bytes(v):
                    # Try DBC encoding if available and signal specified
                    # Phase 1: Use DbcService if available
                    dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded())
                    if dbc_available and sig:
                        if self.dbc_service is not None:
                            msg = self.dbc_service.find_message_by_id(can_id)
                        else:
                            msg = None
                        if msg is not None:
                            try:
                                vv = v
                                try:
                                    if isinstance(vv, str) and vv.startswith('0x'):
                                        vv = int(vv, 16)
                                    elif isinstance(vv, str):
                                        vv = int(vv)
                                except Exception:
                                    pass
                                device_id = act.get('device_id', 0)
                                enc = {'DeviceID': device_id, 'MessageType': MSG_TYPE_SET_RELAY}
                                relay_signals = ['CMD_Relay_1', 'CMD_Relay_2', 'CMD_Relay_3', 'CMD_Relay_4']
                                for rs in relay_signals:
                                    enc[rs] = vv if rs == sig else 0
                                if self.dbc_service is not None:
                                    return self.dbc_service.encode_message(msg, enc)
                                else:
                                    return msg.encode(enc)
                            except Exception:
                                pass
                    # fallback raw
                    try:
                        if isinstance(v, str) and v.startswith('0x'):
                            return bytes.fromhex(v[2:])
                        else:
                            ival = int(v)
                            return bytes([ival & 0xFF])
                    except Exception:
                        return b''

                def _send_bytes(data_bytes):
                    if AdapterFrame is not None:
                        f = AdapterFrame(can_id=can_id, data=data_bytes)
                    else:
                        class F: pass
                        f = F(); f.can_id = can_id; f.data = data_bytes; f.timestamp = time.time()
                    try:
                        if self.can_service is not None and self.can_service.is_connected():
                            self.can_service.send_frame(f)
                    except Exception as e:
                        logger.debug(f"Failed to send frame: {e}")
                    # Loopback handled by adapter if supported
                    if self.can_service is not None and self.can_service.is_connected() and hasattr(self.can_service.adapter, 'loopback'):
                        try:
                            self.can_service.adapter.loopback(f)
                        except Exception as e:
                            logger.debug(f"Loopback not supported or failed: {e}")

                ok = False
                info = ''
                def _nb_sleep(sec: float):
                    end = time.time() + float(sec)
                    while time.time() < end:
                        try:
                            QtCore.QCoreApplication.processEvents()
                        except Exception:
                            pass
                        remaining = end - time.time()
                        if remaining <= 0:
                            break
                        time.sleep(min(SLEEP_INTERVAL_SHORT, remaining))

                def _parse_expected(v):
                    try:
                        if isinstance(v, str) and v.startswith('0x'):
                            return int(v, 16)
                        if isinstance(v, str):
                            return int(v)
                        return int(v)
                    except Exception:
                        return v

                def _wait_for_value(expected, duration_ms: int):
                    # Require the observed value to remain equal to `expected` for the
                    # remainder of the dwell window once it is first observed. This
                    # avoids passing on a single transient sample.
                    end = time.time() + (float(duration_ms) / 1000.0)
                    fb = test.get('feedback_signal')
                    fb_mid = test.get('feedback_message_id')
                    matched_start = None
                    poll = SLEEP_INTERVAL_SHORT
                    while time.time() < end:
                        QtCore.QCoreApplication.processEvents()
                        try:
                            if fb:
                                if fb_mid is not None:
                                    # Phase 1: Use SignalService if available
                                    if self.signal_service is not None:
                                        ts, val = self.signal_service.get_latest_signal(fb_mid, fb)
                                    elif self.gui is not None:
                                        ts, val = self.gui.get_latest_signal(fb_mid, fb)
                                    else:
                                        ts, val = (None, None)
                                else:
                                    # Legacy: search signal cache (deprecated - should use signal_service)
                                    if self.gui is not None and hasattr(self.gui, '_signal_values'):
                                        candidates = []
                                        for k, (t, v) in self.gui._signal_values.items():
                                            try:
                                                _cid, sname = k.split(':', 1)
                                            except Exception:
                                                continue
                                            if sname == fb:
                                                candidates.append((t, v))
                                        if candidates:
                                            candidates.sort(key=lambda x: x[0], reverse=True)
                                            ts, val = candidates[0]
                                        else:
                                            ts, val = (None, None)
                                    else:
                                        ts, val = (None, None)
                            else:
                                ts, val = (None, None)
                        except Exception:
                            ts, val = (None, None)

                        now = time.time()
                        # compare value to expected
                        is_match = False
                        if val is not None:
                            try:
                                if isinstance(val, (int, float)) and isinstance(expected, (int, float)):
                                    is_match = (val == expected)
                                else:
                                    is_match = (str(val) == str(expected))
                            except Exception:
                                is_match = (str(val) == str(expected))

                        if is_match:
                            # start or continue matched window
                            if matched_start is None:
                                matched_start = now
                            # if we reach end with matched_start set and no mismatch occurred,
                            # we'll accept below
                        else:
                            # if we've already started matching and now it's gone -> fail
                            if matched_start is not None:
                                return False, f"Value changed during dwell (last={val})"
                            # otherwise keep waiting for first match

                        time.sleep(poll)

                    # finished dwell window: success only if we saw a match that persisted
                    if matched_start is None:
                        return False, f"Did not observe expected value {expected} during dwell"
                    return True, f"{fb} sustained {expected}"

                expected_high = _parse_expected(high_val)
                expected_low = _parse_expected(low_val)

                # Minimal synchronous state-machine for the LOW->HIGH->LOW sequence.
                low_bytes = _encode_value_to_bytes(low_val)
                high_bytes = _encode_value_to_bytes(high_val)
                info_parts = []
                high_ok = False
                low_ok = False
                state = 'ENSURE_LOW'
                try:
                    while True:
                        if state == 'ENSURE_LOW':
                            _send_bytes(low_bytes)
                            _nb_sleep(SLEEP_INTERVAL_MEDIUM)
                            state = 'ACTUATE_HIGH'
                        elif state == 'ACTUATE_HIGH':
                            _send_bytes(high_bytes)
                            # wait for HIGH dwell (may return early on observation)
                            high_ok, high_info = _wait_for_value(expected_high, int(dwell_ms))
                            logger.debug(f'HIGH dwell: {high_info}')
                            logger.debug(f'High ok: {high_ok}')
                            if high_ok:
                                info_parts.append(f"HIGH observed: {high_info}")
                            else:
                                info_parts.append(f"HIGH missing: expected {expected_high}")
                            state = 'ENSURE_LOW_AFTER_HIGH'
                        elif state == 'ENSURE_LOW_AFTER_HIGH':
                            _send_bytes(low_bytes)
                            _nb_sleep(SLEEP_INTERVAL_MEDIUM)
                            state = 'WAIT_LOW_DWELL'
                        elif state == 'WAIT_LOW_DWELL':
                            low_ok, low_info = _wait_for_value(expected_low, int(dwell_ms))
                            logger.debug(f'LOW dwell: {low_info}')
                            logger.debug(f'Low ok: {low_ok}')
                            if low_ok:
                                info_parts.append(f"LOW observed: {low_info}")
                            else:
                                info_parts.append(f"LOW missing: expected {expected_low}")
                            break
                        else:
                            # unknown state -> abort
                            break
                finally:
                    try:
                        _send_bytes(low_bytes)
                        _nb_sleep(0.05)
                    except Exception:
                        pass

                ok = bool(high_ok and low_ok)
                logger.debug(f"Digital test result: {ok}")
                info = '; '.join(info_parts)
                # Return the computed result so callers receive the correct PASS/FAIL
                return ok, info
            elif act.get('type') == 'analog' and act.get('dac_can_id') is not None:
                # Analog test sequence:
                # 1) Disable MUX (mux_enable_signal = 0)
                # 2) Set MUX channel (mux_channel_signal = mux_channel_value)
                # 3) Set DAC to dac_min_mv using dac_command_signal
                # 4) Enable MUX
                # 5) Hold DAC output for dwell_ms
                # 6) Increase DAC by dac_step_mv until dac_max_mv, holding for dwell_ms at each step
                # 7) Set DAC output to 0mV and disable MUX
                can_id = act.get('dac_can_id')
                
                # Validate CAN ID
                try:
                    can_id = int(can_id)
                    if not (CAN_ID_MIN <= can_id <= CAN_ID_MAX):
                        raise ValueError(f"Invalid DAC CAN ID: {can_id}")
                except (ValueError, TypeError) as e:
                    logger.error(f"Invalid DAC CAN ID in test configuration: {e}")
                    return False, f"Invalid DAC CAN ID: {can_id}"
                
                mux_enable_sig = act.get('mux_enable_signal') or act.get('mux_enable')
                mux_channel_sig = act.get('mux_channel_signal') or act.get('mux_channel')
                mux_channel_value = act.get('mux_channel_value', act.get('mux_channel_value'))
                dac_cmd_sig = act.get('dac_command_signal') or act.get('dac_command')
                
                # Validate required parameters
                if not dac_cmd_sig:
                    logger.error("Analog test requires dac_command_signal but none provided")
                    return False, "Analog test failed: dac_command_signal is required but missing"
                
                # Log configuration for debugging
                logger.info(f"Analog test config: dac_can_id=0x{can_id:X}, dac_command_signal='{dac_cmd_sig}', "
                          f"mux_enable='{mux_enable_sig}', mux_channel='{mux_channel_sig}', "
                          f"mux_channel_value={mux_channel_value}")
                
                # Validate and parse DAC voltage parameters
                try:
                    dac_min = int(act.get('dac_min_mv', act.get('dac_min', DAC_VOLTAGE_MIN)))
                    if not (DAC_VOLTAGE_MIN <= dac_min <= DAC_VOLTAGE_MAX):
                        raise ValueError(f"DAC min {dac_min} out of range ({DAC_VOLTAGE_MIN}-{DAC_VOLTAGE_MAX} mV)")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid DAC min, using {DAC_VOLTAGE_MIN}: {e}")
                    dac_min = DAC_VOLTAGE_MIN
                    
                try:
                    dac_max = int(act.get('dac_max_mv', act.get('dac_max', dac_min)))
                    if not (DAC_VOLTAGE_MIN <= dac_max <= DAC_VOLTAGE_MAX):
                        raise ValueError(f"DAC max {dac_max} out of range ({DAC_VOLTAGE_MIN}-{DAC_VOLTAGE_MAX} mV)")
                    if dac_max < dac_min:
                        logger.warning(f"DAC max {dac_max} < min {dac_min}, swapping")
                        dac_max, dac_min = dac_min, dac_max
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid DAC max, using min: {e}")
                    dac_max = dac_min
                    
                try:
                    dac_step = int(act.get('dac_step_mv', act.get('dac_step', max(1, (dac_max - dac_min)))))
                    if dac_step <= 0:
                        raise ValueError(f"DAC step must be positive, got {dac_step}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid DAC step, using calculated: {e}")
                    dac_step = max(1, dac_max - dac_min)
                    
                try:
                    dwell_ms = int(act.get('dac_dwell_ms', act.get('dwell_ms', DWELL_TIME_DEFAULT)))
                    if dwell_ms < 0:
                        raise ValueError(f"Dwell time must be non-negative, got {dwell_ms}")
                    if dwell_ms == 0:
                        dwell_ms = DWELL_TIME_MIN
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid dwell time, using {DWELL_TIME_DEFAULT}ms: {e}")
                    dwell_ms = DWELL_TIME_DEFAULT

                def _nb_sleep(sec: float):
                    end = time.time() + float(sec)
                    while time.time() < end:
                        try:
                            QtCore.QCoreApplication.processEvents()
                        except Exception:
                            pass
                        remaining = end - time.time()
                        if remaining <= 0:
                            break
                        time.sleep(min(SLEEP_INTERVAL_SHORT, remaining))
                
                def _collect_data_points_during_dwell(dac_voltage: int, dwell_ms: int, dac_cmd_sig: str, fb_signal: str, fb_msg_id: int):
                    """Collect feedback data points during dwell time after settling period.
                    
                    Data collection strategy:
                    - Wait for DAC_SETTLING_TIME_MS after step change (settling period)
                    - Collect data for DATA_COLLECTION_PERIOD_MS (fixed period)
                    - Periodically resend DAC command every 50ms during collection
                    
                    The data collection period must be less than (Dwell Time - Settling Time)
                    to ensure it fits within the available dwell window.
                    
                    Args:
                        dac_voltage: Current DAC voltage command value (mV)
                        dwell_ms: Total dwell time in milliseconds
                        dac_cmd_sig: DAC command signal name
                        fb_signal: Feedback signal name to monitor
                        fb_msg_id: CAN ID of feedback message
                    """
                    if dwell_ms <= 0:
                        return
                    
                    # Validate that data collection period fits within dwell time
                    min_dwell_required = DAC_SETTLING_TIME_MS + DATA_COLLECTION_PERIOD_MS
                    if dwell_ms < min_dwell_required:
                        logger.warning(
                            f"Dwell time {dwell_ms}ms is too short for data collection "
                            f"(requires >= {min_dwell_required}ms: {DAC_SETTLING_TIME_MS}ms settling + {DATA_COLLECTION_PERIOD_MS}ms collection). "
                            f"Available collection window: {max(0, dwell_ms - DAC_SETTLING_TIME_MS)}ms"
                        )
                        # Adjust collection period to fit if possible, otherwise skip collection
                        available_collection_time = max(0, dwell_ms - DAC_SETTLING_TIME_MS)
                        if available_collection_time <= 0:
                            logger.warning(f"Skipping data collection - no time available after settling period")
                            return
                        # Use available time, but cap at DATA_COLLECTION_PERIOD_MS
                        actual_collection_period_ms = min(available_collection_time, DATA_COLLECTION_PERIOD_MS)
                        logger.debug(f"Adjusting collection period from {DATA_COLLECTION_PERIOD_MS}ms to {actual_collection_period_ms}ms to fit dwell time")
                    else:
                        actual_collection_period_ms = DATA_COLLECTION_PERIOD_MS
                    
                    # Command periodicity: 50ms
                    COMMAND_PERIOD_MS = 50
                    command_interval_sec = COMMAND_PERIOD_MS / 1000.0
                    
                    # Timing conversions
                    settling_time_sec = DAC_SETTLING_TIME_MS / 1000.0
                    collection_period_sec = actual_collection_period_ms / 1000.0
                    
                    start_time = time.time()
                    last_command_time = start_time
                    
                    # Send initial DAC command for this voltage level
                    try:
                        _encode_and_send({dac_cmd_sig: int(dac_voltage)})
                        step_change_time = time.time()  # Record when step change occurred
                        last_command_time = step_change_time
                        # Store DAC command timestamp for timestamp validation
                        # Only feedback values received after this timestamp will be used
                        dac_command_timestamp = step_change_time
                        logger.debug(
                            f"DAC command sent: voltage={dac_voltage}mV, "
                            f"command_timestamp={dac_command_timestamp}"
                        )
                    except Exception as e:
                        logger.debug(f"Error sending initial DAC command during dwell: {e}")
                        step_change_time = time.time()
                        dac_command_timestamp = step_change_time
                    
                    # Wait for settling period
                    settling_end_time = step_change_time + settling_time_sec
                    while time.time() < settling_end_time:
                        current_time = time.time()
                        
                        # Send DAC command every 50ms during settling (to ensure reception)
                        if (current_time - last_command_time) >= command_interval_sec:
                            try:
                                _encode_and_send({dac_cmd_sig: int(dac_voltage)})
                                last_command_time = current_time
                            except Exception as e:
                                logger.debug(f"Error sending DAC command during settling: {e}")
                        
                        # Process Qt events to keep UI responsive
                        try:
                            QtCore.QCoreApplication.processEvents()
                        except Exception:
                            pass
                        
                        time.sleep(SLEEP_INTERVAL_SHORT)
                    
                    # Calculate when the full dwell period ends
                    dwell_end_time = step_change_time + (dwell_ms / 1000.0)
                    
                    # Now collect data for the fixed collection period
                    collection_start_time = time.time()
                    collection_end_time = collection_start_time + collection_period_sec
                    
                    data_points_collected = 0
                    
                    # Phase 1: Data collection period (after settling, before end of collection period)
                    while time.time() < collection_end_time and time.time() < dwell_end_time:
                        current_time = time.time()
                        
                        # Send DAC command every 50ms during collection (periodic resend)
                        if (current_time - last_command_time) >= command_interval_sec:
                            try:
                                _encode_and_send({dac_cmd_sig: int(dac_voltage)})
                                last_command_time = current_time
                            except Exception as e:
                                logger.debug(f"Error sending DAC command during collection: {e}")
                        
                        # Collect feedback data points on every loop iteration during collection period
                        if fb_signal and fb_msg_id:
                            try:
                                # Use signal_service if available, otherwise fallback to GUI
                                if self.signal_service is not None:
                                    ts, fb_val = self.signal_service.get_latest_signal(fb_msg_id, fb_signal)
                                elif self.gui is not None:
                                    ts, fb_val = self.gui.get_latest_signal(fb_msg_id, fb_signal)
                                else:
                                    ts, fb_val = (None, None)
                                
                                if fb_val is not None:
                                    # Get measured DAC voltage from EOL configuration
                                    measured_dac_voltage = dac_voltage  # Default to commanded value
                                    if self.eol_hw_config and self.eol_hw_config.get('feedback_message_id'):
                                        try:
                                            eol_msg_id = self.eol_hw_config['feedback_message_id']
                                            eol_signal_name = self.eol_hw_config['measured_dac_signal']
                                            if self.signal_service is not None:
                                                ts_measured, measured_val = self.signal_service.get_latest_signal(eol_msg_id, eol_signal_name)
                                            elif self.gui is not None:
                                                ts_measured, measured_val = self.gui.get_latest_signal(eol_msg_id, eol_signal_name)
                                            else:
                                                ts_measured, measured_val = (None, None)
                                            
                                            if measured_val is not None:
                                                measured_dac_voltage = float(measured_val)
                                                logger.debug(
                                                    f"Using measured DAC voltage: {measured_dac_voltage}mV "
                                                    f"(commanded: {dac_voltage}mV)"
                                                )
                                            else:
                                                logger.debug(f"Measured DAC voltage not available, using commanded: {dac_voltage}mV")
                                        except Exception as e:
                                            logger.debug(f"Error reading measured DAC voltage: {e}, using commanded: {dac_voltage}mV")
                                    else:
                                        logger.debug(f"EOL config not available, using commanded DAC voltage: {dac_voltage}mV")
                                    
                                    # Timestamp validation: only use feedback values received AFTER the DAC command
                                    # This prevents using stale cached values from previous voltage steps
                                    # Allow small tolerance (-10ms) to handle timing precision issues
                                    TIMESTAMP_TOLERANCE_SEC = 0.01  # 10ms tolerance
                                    
                                    if ts is None:
                                        # No timestamp available - collect anyway but log warning
                                        # This can happen if frames don't have timestamps or cache is empty
                                        logger.info(
                                            f"Collecting feedback data point: DAC={measured_dac_voltage}mV (measured), "
                                            f"Feedback={fb_val} (no timestamp available)"
                                        )
                                        if self.plot_update_callback:
                                            self.plot_update_callback(measured_dac_voltage, fb_val, test_name)
                                        data_points_collected += 1
                                    elif ts >= (dac_command_timestamp - TIMESTAMP_TOLERANCE_SEC):
                                        # This feedback value is fresh enough (within tolerance window)
                                        # Note: Allow small negative difference to handle timing precision
                                        logger.debug(
                                            f"Collecting feedback data point: DAC={measured_dac_voltage}mV (measured), "
                                            f"Feedback={fb_val}, timestamp_age={(time.time() - ts)*1000:.1f}ms"
                                        )
                                        if self.plot_update_callback:
                                            self.plot_update_callback(measured_dac_voltage, fb_val, test_name)
                                        data_points_collected += 1
                                    else:
                                        # Stale feedback value - skip it (logged at debug level only if significant)
                                        age_ms = (dac_command_timestamp - ts) * 1000
                                        if age_ms > 50:  # Only log if more than 50ms old
                                            logger.debug(
                                                f"Skipping stale feedback value: timestamp {ts} is "
                                                f"{age_ms:.1f}ms older than DAC command time {dac_command_timestamp}"
                                            )
                            except Exception as e:
                                logger.debug(f"Error collecting feedback during dwell: {e}")
                        
                        # Process Qt events to keep UI responsive
                        try:
                            QtCore.QCoreApplication.processEvents()
                        except Exception:
                            pass
                        
                        # Small sleep to prevent busy waiting and allow other threads to process
                        # This is minimal to maximize collection rate while maintaining system responsiveness
                        time.sleep(SLEEP_INTERVAL_SHORT)
                    
                    # Phase 2: Continue holding DAC voltage for remaining dwell time (if any)
                    # This ensures the DAC voltage is held for the full dwell period, even after data collection ends
                    while time.time() < dwell_end_time:
                        current_time = time.time()
                        
                        # Send DAC command every 50ms to maintain the voltage level
                        if (current_time - last_command_time) >= command_interval_sec:
                            try:
                                _encode_and_send({dac_cmd_sig: int(dac_voltage)})
                                last_command_time = current_time
                            except Exception as e:
                                logger.debug(f"Error sending DAC command during hold period: {e}")
                        
                        # Process Qt events to keep UI responsive
                        try:
                            QtCore.QCoreApplication.processEvents()
                        except Exception:
                            pass
                        
                        time.sleep(SLEEP_INTERVAL_SHORT)
                    
                    logger.debug(
                        f"Collected {data_points_collected} data points during {actual_collection_period_ms}ms collection period "
                        f"(after {DAC_SETTLING_TIME_MS}ms settling), held DAC at {dac_voltage}mV for full {dwell_ms}ms dwell"
                    )

                def _encode_and_send(signals: dict):
                    # signals: mapping of signal name -> value
                    if not signals:
                        logger.warning("_encode_and_send called with empty signals dict")
                        return
                    
                    encode_data = {'DeviceID': 0}  # always include DeviceID
                    mux_value = None
                    data_bytes = b''
                    # Phase 1: Use DbcService if available
                    dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded())
                    if dbc_available:
                        if self.dbc_service is not None:
                            target_msg = self.dbc_service.find_message_by_id(can_id)
                        else:
                            target_msg = None
                    else:
                        target_msg = None
                    
                    if target_msg is None:
                        logger.warning(f"Could not find message for CAN ID 0x{can_id:X} - DBC may not be loaded or message missing")
                    
                    if target_msg is not None:
                        for sig_name in signals:
                            encode_data[sig_name] = signals[sig_name]
                            # check if this signal is muxed
                            for sig in target_msg.signals:
                                if sig.name == sig_name and getattr(sig, 'multiplexer_ids', None):
                                    mux_value = sig.multiplexer_ids[0]
                                    break
                        if mux_value is not None:
                            encode_data['MessageType'] = mux_value
                        else:
                            # If this message has a MessageType signal with defined choices,
                            # try to infer the correct selector for non-muxed commands
                            # (e.g. DAC commands require MessageType=18).
                            try:
                                mtype_sig = None
                                for s in target_msg.signals:
                                    if getattr(s, 'name', '') == 'MessageType':
                                        mtype_sig = s
                                        break
                                if mtype_sig is not None and 'MessageType' not in encode_data:
                                    choices = getattr(mtype_sig, 'choices', None) or {}
                                    # simple heuristics: match substrings from signal name to choice name
                                    for sig_name in signals:
                                        sname_up = str(sig_name).upper()
                                        for val, cname in (choices.items() if hasattr(choices, 'items') else []):
                                            try:
                                                if sname_up.find('DAC') != -1 and 'DAC' in str(cname).upper():
                                                    encode_data['MessageType'] = val
                                                    raise StopIteration
                                                if sname_up.find('MUX') != -1 and 'MUX' in str(cname).upper():
                                                    encode_data['MessageType'] = val
                                                    raise StopIteration
                                                if sname_up.find('RELAY') != -1 and 'RELAY' in str(cname).upper():
                                                    encode_data['MessageType'] = val
                                                    raise StopIteration
                                            except StopIteration:
                                                break
                                        if 'MessageType' in encode_data:
                                            break
                            except Exception:
                                pass
                        try:
                            if self.dbc_service is not None:
                                data_bytes = self.dbc_service.encode_message(target_msg, encode_data)
                            else:
                                data_bytes = target_msg.encode(encode_data)
                        except Exception:
                            # fallback to single byte
                            try:
                                if len(signals) == 1:
                                    v = list(signals.values())[0]
                                    data_bytes = bytes([int(v) & 0xFF])
                            except Exception:
                                data_bytes = b''
                    else:
                        try:
                            if len(signals) == 1:
                                v = list(signals.values())[0]
                                if isinstance(v, str) and v.startswith('0x'):
                                    data_bytes = bytes.fromhex(v[2:])
                                else:
                                    data_bytes = bytes([int(v) & 0xFF])
                        except Exception:
                            data_bytes = b''

                    # Update real-time monitoring: when commanding the DAC, show the commanded value
                    if self.label_update_callback:
                        try:
                            if dac_cmd_sig and dac_cmd_sig in signals:
                                self.label_update_callback(str(signals[dac_cmd_sig]))
                            elif len(signals) == 1:
                                # if a single signal is being sent, show its value
                                self.label_update_callback(str(list(signals.values())[0]))
                        except Exception as e:
                            logger.debug(f"Failed to update label: {e}")

                    # Phase 1: Use CanService if available
                    if self.can_service is not None and self.can_service.is_connected():
                        from backend.adapters.interface import Frame as AdapterFrame
                        f = AdapterFrame(can_id=can_id, data=data_bytes, timestamp=time.time())
                        logger.debug(f'Signals: {signals}')
                        logger.debug(f'Encode data: {encode_data}')
                        logger.debug(f"Sending frame via service: can_id=0x{can_id:X} data={data_bytes.hex()}")
                        try:
                            success = self.can_service.send_frame(f)
                            if not success:
                                logger.warning(f"send_frame returned False for can_id=0x{can_id:X}")
                        except Exception as e:
                            logger.error(f"Failed to send frame via service: {e}", exc_info=True)
                            raise  # Re-raise to allow caller to handle
                    else:
                        # Legacy: use direct adapter (should not happen - CanService should always be available)
                        logger.warning("CanService not available for frame sending")
                        if AdapterFrame is not None:
                            f = AdapterFrame(can_id=can_id, data=data_bytes)
                        else:
                            class F: pass
                            f = F(); f.can_id = can_id; f.data = data_bytes; f.timestamp = time.time()
                        logger.debug(f'Signals: {signals}')
                        logger.debug(f'Encode data: {encode_data}')
                        logger.debug(f"Sending frame: can_id=0x{can_id:X} data={data_bytes.hex()}")
                        # Note: Legacy path not fully implemented - should use CanService

                success = False
                info = ''
                # Get feedback signal info for plotting
                fb_signal = test.get('feedback_signal')
                fb_msg_id = test.get('feedback_message_id')
                test_name = test.get('name', 'Analog Test')
                
                # Clear plot before starting new analog test
                if self.plot_clear_callback:
                    try:
                        self.plot_clear_callback()
                    except Exception as e:
                        logger.debug(f"Failed to clear plot: {e}")
                
                # Clear signal cache before starting analog test to ensure fresh timestamps
                # This prevents stale cached feedback values from previous tests from being used
                try:
                    if self.signal_service is not None:
                        self.signal_service.clear_cache()
                        logger.debug("Cleared signal cache before starting analog test")
                except Exception as e:
                    logger.debug(f"Failed to clear signal cache before analog test: {e}")
                
                try:
                    # 1) Disable MUX
                    if mux_enable_sig:
                        try:
                            _encode_and_send({mux_enable_sig: 0})
                            _nb_sleep(SLEEP_INTERVAL_SHORT)
                        except Exception as e:
                            logger.warning(f"Failed to disable MUX: {e}", exc_info=True)
                            # Continue anyway - MUX may already be disabled
                    # 2) Set MUX channel
                    if mux_channel_sig and mux_channel_value is not None:
                        try:
                            _encode_and_send({mux_channel_sig: int(mux_channel_value)})
                            _nb_sleep(SLEEP_INTERVAL_SHORT)
                        except Exception as e:
                            logger.warning(f"Failed to set MUX channel: {e}", exc_info=True)
                            # Continue - may be optional depending on hardware
                    # 3) Set DAC to min (CRITICAL - must succeed)
                    try:
                        _encode_and_send({dac_cmd_sig: int(dac_min)})
                        _nb_sleep(SLEEP_INTERVAL_SHORT)
                    except Exception as e:
                        logger.error(f"Failed to set DAC to minimum: {e}", exc_info=True)
                        raise ValueError(f"Failed to send DAC command: {e}") from e
                    # 4) Enable MUX (send channel + enable together if channel known)
                    if mux_enable_sig:
                        try:
                            if mux_channel_sig and mux_channel_value is not None:
                                _encode_and_send({mux_enable_sig: 1, mux_channel_sig: int(mux_channel_value)})
                            else:
                                _encode_and_send({mux_enable_sig: 1})
                        except Exception as e:
                            logger.warning(f"Failed to enable MUX: {e}", exc_info=True)
                            # Continue - test may work without explicit MUX enable
                    # 5) Hold initial dwell and collect multiple feedback data points
                    # Continuously send DAC command (50ms period) and collect data during dwell
                    if dac_cmd_sig:
                        _collect_data_points_during_dwell(dac_min, dwell_ms, dac_cmd_sig, fb_signal, fb_msg_id)
                    else:
                        # Fallback if no DAC command signal (shouldn't happen in normal operation)
                        _nb_sleep(float(dwell_ms) / 1000.0)
                        if fb_signal and fb_msg_id:
                            try:
                                if self.signal_service is not None:
                                    ts, fb_val = self.signal_service.get_latest_signal(fb_msg_id, fb_signal)
                                elif self.gui is not None:
                                    ts, fb_val = self.gui.get_latest_signal(fb_msg_id, fb_signal)
                                else:
                                    ts, fb_val = (None, None)
                                
                                if fb_val is not None:
                                    # Get measured DAC voltage if configured
                                    measured_dac = dac_min
                                    if self.eol_hw_config and self.eol_hw_config.get('feedback_message_id'):
                                        try:
                                            eol_msg_id = self.eol_hw_config['feedback_message_id']
                                            eol_signal_name = self.eol_hw_config['measured_dac_signal']
                                            if self.signal_service is not None:
                                                _, measured_val = self.signal_service.get_latest_signal(eol_msg_id, eol_signal_name)
                                            elif self.gui is not None:
                                                _, measured_val = self.gui.get_latest_signal(eol_msg_id, eol_signal_name)
                                            else:
                                                _, measured_val = (None, None)
                                            
                                            if measured_val is not None:
                                                measured_dac = float(measured_val)
                                        except Exception as e:
                                            logger.debug(f"Failed to get signal value during analog test: {e}")
                                    if self.plot_update_callback:
                                        self.plot_update_callback(measured_dac, fb_val, test_name)
                            except Exception as e:
                                logger.debug(f"Error updating plot during analog test: {e}", exc_info=True)
                    
                    # 6) Ramp DAC up by step, holding for dwell each step
                    # During each step: continuously send DAC command (50ms period) and collect multiple data points
                    cur = int(dac_min)
                    while cur < int(dac_max):
                        cur = min(cur + int(dac_step), int(dac_max))
                        # Collect multiple data points during dwell, with periodic DAC command resends
                        if dac_cmd_sig:
                            _collect_data_points_during_dwell(cur, dwell_ms, dac_cmd_sig, fb_signal, fb_msg_id)
                        else:
                            # Fallback if no DAC command signal (shouldn't happen in normal operation)
                            _nb_sleep(float(dwell_ms) / 1000.0)
                            if fb_signal and fb_msg_id:
                                try:
                                    if self.signal_service is not None:
                                        ts, fb_val = self.signal_service.get_latest_signal(fb_msg_id, fb_signal)
                                    elif self.gui is not None:
                                        ts, fb_val = self.gui.get_latest_signal(fb_msg_id, fb_signal)
                                    else:
                                        ts, fb_val = (None, None)
                                    
                                    if fb_val is not None:
                                        # Get measured DAC voltage if configured
                                        measured_dac = cur
                                        if self.eol_hw_config and self.eol_hw_config.get('feedback_message_id'):
                                            try:
                                                eol_msg_id = self.eol_hw_config['feedback_message_id']
                                                eol_signal_name = self.eol_hw_config['measured_dac_signal']
                                                if self.signal_service is not None:
                                                    _, measured_val = self.signal_service.get_latest_signal(eol_msg_id, eol_signal_name)
                                                elif self.gui is not None:
                                                    _, measured_val = self.gui.get_latest_signal(eol_msg_id, eol_signal_name)
                                                else:
                                                    _, measured_val = (None, None)
                                                
                                                if measured_val is not None:
                                                    measured_dac = float(measured_val)
                                            except Exception as e:
                                                logger.debug(f"Failed to get signal value during analog test ramp: {e}")
                                        if self.plot_update_callback:
                                            self.plot_update_callback(measured_dac, fb_val, test_name)
                                except Exception as e:
                                    logger.debug(f"Error updating plot during analog test ramp: {e}", exc_info=True)
                    success = True
                    info = f"Analog actuation: held {dac_min}-{dac_max} step {dac_step} mV"
                except Exception as e:
                    success = False
                    info = f"Analog actuation failed: {e}"
                finally:
                    # Ensure we leave DAC at 0 and MUX disabled even if an exception occurred
                    try:
                        if dac_cmd_sig:
                            _encode_and_send({dac_cmd_sig: 0})
                            _nb_sleep(SLEEP_INTERVAL_SHORT)
                    except Exception as e:
                        logger.debug(f"Failed to clear signal cache: {e}")
                    try:
                        if mux_enable_sig:
                            # send disable; include channel if available to be explicit
                            if mux_channel_sig and mux_channel_value is not None:
                                _encode_and_send({mux_enable_sig: 0, mux_channel_sig: int(mux_channel_value)})
                            else:
                                _encode_and_send({mux_enable_sig: 0})
                            _nb_sleep(SLEEP_INTERVAL_SHORT)
                    except Exception as e:
                        logger.debug(f"Failed to disable multiplexor signal: {e}")
                # Capture and store plot data immediately for analog tests before returning
                # This prevents plot data from being lost when the next test clears the plot arrays
                if test.get('type') == 'analog':
                    test_name = test.get('name', '<unnamed>')
                    try:
                        if self.gui is not None and hasattr(self.gui, 'plot_dac_voltages') and hasattr(self.gui, 'plot_feedback_values'):
                            if self.gui.plot_dac_voltages and self.gui.plot_feedback_values:
                                plot_data = {
                                    'dac_voltages': list(self.gui.plot_dac_voltages),
                                    'feedback_values': list(self.gui.plot_feedback_values)
                                }
                                # Store plot data immediately in execution data (will be merged with other data later)
                                # Use a temporary key structure that _on_test_finished can access
                                if not hasattr(self.gui, '_test_plot_data_temp'):
                                    self.gui._test_plot_data_temp = {}
                                self.gui._test_plot_data_temp[test_name] = plot_data
                                logger.debug(f"Captured and stored plot data for {test_name}: {len(plot_data['dac_voltages'])} points")
                    except Exception as e:
                        logger.debug(f"Failed to capture plot data for {test_name}: {e}", exc_info=True)
                
                return success, info
            elif act.get('type') == 'analog_static':
                # Analog Static Test execution:
                # 1) Wait for pre-dwell time (system stabilization)
                # 2) Collect feedback and EOL signal values during dwell time
                # 3) Calculate averages
                # 4) Compare: |feedback_avg - eol_avg| <= tolerance -> PASS
                
                # Extract parameters
                feedback_msg_id = act.get('feedback_signal_source')
                feedback_signal = act.get('feedback_signal')
                eol_msg_id = act.get('eol_signal_source')
                eol_signal = act.get('eol_signal')
                tolerance_mv = float(act.get('tolerance_mv', 0))
                pre_dwell_ms = int(act.get('pre_dwell_time_ms', 0))
                dwell_ms = int(act.get('dwell_time_ms', 0))
                
                # Validate parameters
                if not all([feedback_msg_id, feedback_signal, eol_msg_id, eol_signal]):
                    return False, "Missing required Analog Static Test parameters"
                
                if tolerance_mv < 0:
                    return False, "Tolerance must be non-negative"
                
                if pre_dwell_ms < 0:
                    return False, "Pre-dwell time must be non-negative"
                
                if dwell_ms <= 0:
                    return False, "Dwell time must be positive"
                
                def _nb_sleep(sec: float) -> None:
                    """Non-blocking sleep that processes Qt events.
                    
                    Args:
                        sec: Sleep duration in seconds
                    """
                    end = time.time() + float(sec)
                    while time.time() < end:
                        try:
                            QtCore.QCoreApplication.processEvents()
                        except Exception as e:
                            logger.debug(f"Error processing Qt events during sleep: {e}")
                        remaining = end - time.time()
                        if remaining <= 0:
                            break
                        time.sleep(min(SLEEP_INTERVAL_SHORT, remaining))
                
                # Step 1: Wait for pre-dwell time (system stabilization)
                logger.info(f"Analog Static Test: Waiting {pre_dwell_ms}ms for system stabilization...")
                _nb_sleep(pre_dwell_ms / 1000.0)
                
                # Step 2: Collect data during dwell time
                feedback_values = []
                eol_values = []
                start_time = time.time()
                end_time = start_time + (dwell_ms / 1000.0)
                
                logger.info(f"Analog Static Test: Collecting data for {dwell_ms}ms...")
                
                while time.time() < end_time:
                    # Read feedback signal
                    try:
                        if self.signal_service is not None:
                            ts_fb, fb_val = self.signal_service.get_latest_signal(feedback_msg_id, feedback_signal)
                        elif self.gui is not None:
                            ts_fb, fb_val = self.gui.get_latest_signal(feedback_msg_id, feedback_signal)
                        else:
                            ts_fb, fb_val = (None, None)
                        
                        if fb_val is not None:
                            try:
                                feedback_values.append(float(fb_val))
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading feedback signal: {e}")
                    
                    # Read EOL signal
                    try:
                        if self.signal_service is not None:
                            ts_eol, eol_val = self.signal_service.get_latest_signal(eol_msg_id, eol_signal)
                        elif self.gui is not None:
                            ts_eol, eol_val = self.gui.get_latest_signal(eol_msg_id, eol_signal)
                        else:
                            ts_eol, eol_val = (None, None)
                        
                        if eol_val is not None:
                            try:
                                eol_values.append(float(eol_val))
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading EOL signal: {e}")
                    
                    # Process events and sleep
                    try:
                        QtCore.QCoreApplication.processEvents()
                    except Exception:
                        pass
                    time.sleep(SLEEP_INTERVAL_SHORT)
                
                # Step 3: Calculate averages
                if not feedback_values or not eol_values:
                    return False, f"No data collected during dwell time (Feedback samples: {len(feedback_values)}, EOL samples: {len(eol_values)})"
                
                feedback_avg = sum(feedback_values) / len(feedback_values)
                eol_avg = sum(eol_values) / len(eol_values)
                
                # Step 4: Compare and determine pass/fail
                difference = abs(feedback_avg - eol_avg)
                passed = difference <= tolerance_mv
                
                # Build info string
                info = f"Feedback Avg: {feedback_avg:.2f} mV, EOL Avg: {eol_avg:.2f} mV, "
                info += f"Difference: {difference:.2f} mV, Tolerance: {tolerance_mv:.2f} mV"
                info += f"\nFeedback samples: {len(feedback_values)}, EOL samples: {len(eol_values)}"
                
                if not passed:
                    info += f"\nFAIL: Difference {difference:.2f} mV exceeds tolerance {tolerance_mv:.2f} mV"
                else:
                    info += f"\nPASS: Difference {difference:.2f} mV within tolerance {tolerance_mv:.2f} mV"
                
                # Store results for display
                test_name = test.get('name', '<unnamed>')
                result_data = {
                    'feedback_avg': feedback_avg,
                    'eol_avg': eol_avg,
                    'difference': difference,
                    'tolerance': tolerance_mv,
                    'feedback_samples': len(feedback_values),
                    'eol_samples': len(eol_values),
                    'feedback_values': feedback_values,
                    'eol_values': eol_values
                }
                
                # Store in temporary storage for retrieval by _on_test_finished
                if self.gui is not None:
                    if not hasattr(self.gui, '_test_result_data_temp'):
                        self.gui._test_result_data_temp = {}
                    self.gui._test_result_data_temp[test_name] = result_data
                
                logger.info(f"Analog Static Test completed: {'PASS' if passed else 'FAIL'}")
                return passed, info
            else:
                pass
        except Exception as e:
            return False, f'Failed to send actuation: {e}'

        waited = 0.0
        poll_interval = POLL_INTERVAL_MS / 1000.0  # Convert ms to seconds
        observed_info = 'no feedback'
        while waited < timeout:
            QtCore.QCoreApplication.processEvents()
            time.sleep(poll_interval)
            waited += poll_interval
            fb = test.get('feedback_signal')
            try:
                # Legacy: Access frame table directly if GUI is available
                # This should be refactored to use a callback or service method in the future
                if self.gui is None or not hasattr(self.gui, 'frame_table'):
                    continue
                
                rows = self.gui.frame_table.rowCount()
                for r in range(max(0, rows-10), rows):
                    try:
                        can_id_item = self.gui.frame_table.item(r,1)
                        data_item = self.gui.frame_table.item(r,3)
                        if can_id_item is None or data_item is None:
                            continue
                        try:
                            row_can = int(can_id_item.text())
                        except Exception:
                            try:
                                row_can = int(can_id_item.text(), 0)
                            except Exception:
                                continue
                        raw_hex = data_item.text()
                        raw = bytes.fromhex(raw_hex) if raw_hex else b''
                        # Phase 1: Use services if available
                        dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded())
                        if dbc_available and fb:
                            if self.dbc_service is not None:
                                target_msg, target_sig = self.dbc_service.find_message_and_signal(row_can, fb)
                                if target_msg is not None and target_sig is not None:
                                    try:
                                        decoded = self.dbc_service.decode_message(target_msg, raw)
                                        observed_info = f"{fb}={decoded.get(fb)} (msg 0x{row_can:X})"
                                        return True, observed_info
                                    except Exception:
                                        pass
                            # Legacy fallback removed - should use dbc_service
                            # Note: _dbc_db was removed, this path should not be reached
                            pass
                        else:
                            observed_info = f'observed frame id=0x{row_can:X} data={raw.hex()}'
                            return True, observed_info
                    except Exception as e:
                        logger.debug(f"Failed to process frame from manual send: {e}", exc_info=True)
                        continue
            except Exception as e:
                logger.warning(f"Error processing manual CAN frame send: {e}", exc_info=True)

        return False, observed_info
    
    def _create_gui_proxy(self) -> Any:
        """Create a minimal GUI proxy object for PhaseCurrentTestStateMachine.
        
        This is a temporary solution until PhaseCurrentTestStateMachine is fully decoupled.
        The proxy provides the minimal interface needed by PhaseCurrentTestStateMachine.
        
        Returns:
            Proxy object with services and callbacks
        """
        class GUIProxy:
            def __init__(self, runner: 'TestRunner'):
                self.runner = runner
                self.oscilloscope_service = runner.oscilloscope_service
                self.can_service = runner.can_service
                self.dbc_service = runner.dbc_service
                self.signal_service = runner.signal_service
                self._oscilloscope_config = getattr(runner, '_oscilloscope_config', None)
                self._test_plot_data_temp = {}
                self.plot_canvas = None
                self.plot_figure = None
                self.plot_axes = None
                self.plot_axes_v = None
                self.plot_axes_w = None
                self.plot_line_v = None
                self.plot_line_w = None
            
            def processEvents(self):
                """Process Qt events if available."""
                try:
                    from PySide6 import QtCore
                    QtCore.QCoreApplication.processEvents()
                except Exception:
                    pass
            
            def get_latest_signal(self, can_id: int, signal_name: str) -> Tuple[Optional[float], Optional[Any]]:
                """Get latest signal value."""
                if self.runner.signal_service:
                    return self.runner.signal_service.get_latest_signal(can_id, signal_name)
                return None, None
        
        return GUIProxy(self)


