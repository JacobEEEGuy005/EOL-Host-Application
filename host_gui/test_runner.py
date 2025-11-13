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
        if act.get('type') == 'Phase Current Test':
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
            if act.get('type') == 'Digital Logic Test' and act.get('can_id') is not None:
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

                # Import AdapterFrame at function level (unified pattern)
                try:
                    from backend.adapters.interface import Frame as AdapterFrame
                except ImportError:
                    AdapterFrame = None

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
            elif act.get('type') == 'Analog Sweep Test' and act.get('dac_can_id') is not None:
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

                # Import AdapterFrame at function level (unified pattern)
                try:
                    from backend.adapters.interface import Frame as AdapterFrame
                except ImportError:
                    AdapterFrame = None

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
                if test.get('type') == 'Analog Sweep Test':
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
            elif act.get('type') == 'Analog Static Test':
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
            elif act.get('type') == 'Temperature Validation Test':
                # Temperature Validation Test execution:
                # 1) Collect feedback signal values during dwell time
                # 2) Calculate average
                # 3) Compare: |average - reference_temperature| <= tolerance -> PASS
                
                # Extract parameters
                feedback_msg_id = act.get('feedback_signal_source')
                feedback_signal = act.get('feedback_signal')
                reference_temp_c = float(act.get('reference_temperature_c', 0))
                tolerance_c = float(act.get('tolerance_c', 0))
                dwell_ms = int(act.get('dwell_time_ms', 0))
                
                # Validate parameters
                if not all([feedback_msg_id, feedback_signal]):
                    return False, "Missing required Temperature Validation Test parameters (feedback_signal_source, feedback_signal)"
                
                if tolerance_c < 0:
                    return False, "Tolerance must be non-negative"
                
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
                
                # Step 1: Collect data during dwell time
                temperature_values = []
                start_time = time.time()
                end_time = start_time + (dwell_ms / 1000.0)
                
                logger.info(f"Temperature Validation Test: Collecting temperature data for {dwell_ms}ms...")
                
                while time.time() < end_time:
                    # Read feedback signal (temperature)
                    try:
                        if self.signal_service is not None:
                            ts, temp_val = self.signal_service.get_latest_signal(feedback_msg_id, feedback_signal)
                        elif self.gui is not None:
                            ts, temp_val = self.gui.get_latest_signal(feedback_msg_id, feedback_signal)
                        else:
                            ts, temp_val = (None, None)
                        
                        if temp_val is not None:
                            try:
                                temp_float = float(temp_val)
                                temperature_values.append(temp_float)
                                
                                # Update real-time display with latest value (feedback signal, not current signal)
                                if self.gui is not None and hasattr(self.gui, 'feedback_signal_label'):
                                    try:
                                        self.gui.feedback_signal_label.setText(f"{temp_float:.2f} °C")
                                    except Exception as e:
                                        logger.debug(f"Failed to update feedback signal label: {e}")
                                elif self.label_update_callback:
                                    # Fallback: use callback if GUI not available (should update feedback label)
                                    try:
                                        self.label_update_callback(f"{temp_float:.2f} °C")
                                    except Exception as e:
                                        logger.debug(f"Failed to update label: {e}")
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading temperature signal: {e}")
                    
                    # Process events and sleep
                    try:
                        QtCore.QCoreApplication.processEvents()
                    except Exception:
                        pass
                    time.sleep(SLEEP_INTERVAL_SHORT)
                
                # Step 2: Check if any data was collected
                if not temperature_values:
                    return False, f"No temperature data received during dwell time ({dwell_ms}ms). Check CAN connection and signal configuration."
                
                # Step 3: Calculate average
                temperature_avg = sum(temperature_values) / len(temperature_values)
                
                # Step 4: Compare and determine pass/fail
                difference = abs(temperature_avg - reference_temp_c)
                passed = difference <= tolerance_c
                
                # Build info string
                info = f"Reference: {reference_temp_c:.2f} °C, Measured Avg: {temperature_avg:.2f} °C, "
                info += f"Difference: {difference:.2f} °C, Tolerance: {tolerance_c:.2f} °C"
                info += f"\nSamples collected: {len(temperature_values)}"
                
                if not passed:
                    info += f"\nFAIL: Difference {difference:.2f} °C exceeds tolerance {tolerance_c:.2f} °C"
                else:
                    info += f"\nPASS: Difference {difference:.2f} °C within tolerance {tolerance_c:.2f} °C"
                
                # Store results for display
                test_name = test.get('name', '<unnamed>')
                result_data = {
                    'reference_temperature_c': reference_temp_c,
                    'measured_avg_c': temperature_avg,
                    'difference_c': difference,
                    'tolerance_c': tolerance_c,
                    'samples': len(temperature_values),
                    'temperature_values': temperature_values
                }
                
                # Store in temporary storage for retrieval by _on_test_finished
                if self.gui is not None:
                    if not hasattr(self.gui, '_test_result_data_temp'):
                        self.gui._test_result_data_temp = {}
                    self.gui._test_result_data_temp[test_name] = result_data
                
                logger.info(f"Temperature Validation Test completed: {'PASS' if passed else 'FAIL'}")
                return passed, info
            elif act.get('type') == 'Analog PWM Sensor':
                # Analog PWM Sensor Test execution:
                # 1) Collect PWM frequency and duty cycle signals during acquisition time
                # 2) Calculate averages for both signals
                # 3) Compare both averages with reference values
                # 4) PASS if both parameters are within tolerance, FAIL otherwise
                
                # Extract parameters
                feedback_msg_id = act.get('feedback_signal_source')
                pwm_frequency_signal = act.get('feedback_pwm_frequency_signal')
                duty_signal = act.get('feedback_duty_signal')
                reference_pwm_frequency = float(act.get('reference_pwm_frequency', 0))
                reference_duty = float(act.get('reference_duty', 0))
                pwm_frequency_tolerance = float(act.get('pwm_frequency_tolerance', 0))
                duty_tolerance = float(act.get('duty_tolerance', 0))
                acquisition_ms = int(act.get('acquisition_time_ms', 0))
                
                # Validate parameters
                if not all([feedback_msg_id, pwm_frequency_signal, duty_signal]):
                    return False, "Missing required Analog PWM Sensor Test parameters (feedback_signal_source, feedback_pwm_frequency_signal, feedback_duty_signal)"
                
                if pwm_frequency_tolerance < 0:
                    return False, "PWM frequency tolerance must be non-negative"
                
                if duty_tolerance < 0:
                    return False, "Duty tolerance must be non-negative"
                
                if acquisition_ms <= 0:
                    return False, "Acquisition time must be positive"
                
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
                
                # Step 1: Collect data during acquisition time
                pwm_frequency_values = []
                duty_values = []
                start_time = time.time()
                end_time = start_time + (acquisition_ms / 1000.0)
                
                logger.info(f"Analog PWM Sensor Test: Collecting PWM frequency and duty cycle data for {acquisition_ms}ms...")
                
                while time.time() < end_time:
                    # Read PWM frequency signal
                    try:
                        if self.signal_service is not None:
                            ts_freq, freq_val = self.signal_service.get_latest_signal(feedback_msg_id, pwm_frequency_signal)
                        elif self.gui is not None:
                            ts_freq, freq_val = self.gui.get_latest_signal(feedback_msg_id, pwm_frequency_signal)
                        else:
                            ts_freq, freq_val = (None, None)
                        
                        if freq_val is not None:
                            try:
                                freq_float = float(freq_val)
                                pwm_frequency_values.append(freq_float)
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading PWM frequency signal: {e}")
                    
                    # Read duty signal
                    try:
                        if self.signal_service is not None:
                            ts_duty, duty_val = self.signal_service.get_latest_signal(feedback_msg_id, duty_signal)
                        elif self.gui is not None:
                            ts_duty, duty_val = self.gui.get_latest_signal(feedback_msg_id, duty_signal)
                        else:
                            ts_duty, duty_val = (None, None)
                        
                        if duty_val is not None:
                            try:
                                duty_float = float(duty_val)
                                duty_values.append(duty_float)
                                
                                # Update real-time display with both values (use latest frequency if available)
                                latest_freq = pwm_frequency_values[-1] if pwm_frequency_values else None
                                if latest_freq is not None:
                                    display_text = f"Freq: {latest_freq:.2f} Hz, Duty: {duty_float:.2f} %"
                                    if self.gui is not None and hasattr(self.gui, 'feedback_signal_label'):
                                        try:
                                            self.gui.feedback_signal_label.setText(display_text)
                                        except Exception as e:
                                            logger.debug(f"Failed to update feedback signal label: {e}")
                                    elif self.label_update_callback:
                                        try:
                                            self.label_update_callback(display_text)
                                        except Exception as e:
                                            logger.debug(f"Failed to update label: {e}")
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading duty signal: {e}")
                    
                    # Process events and sleep
                    try:
                        QtCore.QCoreApplication.processEvents()
                    except Exception:
                        pass
                    time.sleep(SLEEP_INTERVAL_SHORT)
                
                # Step 2: Check if data was collected for both signals
                if not pwm_frequency_values:
                    return False, f"No PWM frequency data received during acquisition time ({acquisition_ms}ms). Check CAN connection and signal configuration."
                
                if not duty_values:
                    return False, f"No duty cycle data received during acquisition time ({acquisition_ms}ms). Check CAN connection and signal configuration."
                
                # Step 3: Calculate averages
                pwm_frequency_avg = sum(pwm_frequency_values) / len(pwm_frequency_values)
                duty_avg = sum(duty_values) / len(duty_values)
                
                # Step 4: Compare with reference values and determine pass/fail
                frequency_difference = abs(pwm_frequency_avg - reference_pwm_frequency)
                duty_difference = abs(duty_avg - reference_duty)
                
                frequency_ok = frequency_difference <= pwm_frequency_tolerance
                duty_ok = duty_difference <= duty_tolerance
                
                passed = frequency_ok and duty_ok
                
                # Build info string
                info = f"PWM Frequency: Ref={reference_pwm_frequency:.2f} Hz, Measured={pwm_frequency_avg:.2f} Hz, "
                info += f"Diff={frequency_difference:.2f} Hz, Tol={pwm_frequency_tolerance:.2f} Hz ({'PASS' if frequency_ok else 'FAIL'}) | "
                info += f"Duty: Ref={reference_duty:.2f} %, Measured={duty_avg:.2f} %, "
                info += f"Diff={duty_difference:.2f} %, Tol={duty_tolerance:.2f} % ({'PASS' if duty_ok else 'FAIL'})"
                
                logger.info(f"Analog PWM Sensor Test completed: {'PASS' if passed else 'FAIL'}")
                return passed, info
            elif act.get('type') == 'External 5V Test':
                # External 5V Test execution:
                # 1) Send trigger with value 0 (disable External 5V)
                # 2) Wait for pre-dwell time
                # 3) Collect EOL and Feedback signal values during dwell time
                # 4) Send trigger with value 1 (enable External 5V)
                # 5) Wait for pre-dwell time
                # 6) Collect EOL and Feedback signal values during dwell time (clear plot first)
                # 7) Send trigger with value 0 (disable External 5V)
                # 8) Calculate averages for both phases
                # 9) Compare: |feedback_avg - eol_avg| <= tolerance for both phases -> PASS
                
                # Extract parameters
                trigger_msg_id = act.get('ext_5v_test_trigger_source')
                trigger_signal = act.get('ext_5v_test_trigger_signal')
                eol_msg_id = act.get('eol_ext_5v_measurement_source')
                eol_signal = act.get('eol_ext_5v_measurement_signal')
                feedback_msg_id = act.get('feedback_signal_source')
                feedback_signal = act.get('feedback_signal')
                tolerance_mv = float(act.get('tolerance_mv', 0))
                pre_dwell_ms = int(act.get('pre_dwell_time_ms', 0))
                dwell_ms = int(act.get('dwell_time_ms', 0))
                
                # Validate parameters
                if not all([trigger_msg_id, trigger_signal, eol_msg_id, eol_signal, feedback_msg_id, feedback_signal]):
                    return False, "Missing required External 5V Test parameters"
                
                if tolerance_mv < 0:
                    return False, "Tolerance must be non-negative"
                
                if pre_dwell_ms < 0:
                    return False, "Pre-dwell time must be non-negative"
                
                if dwell_ms <= 0:
                    return False, "Dwell time must be positive"
                
                # Import AdapterFrame at function level (unified pattern)
                try:
                    from backend.adapters.interface import Frame as AdapterFrame
                except ImportError:
                    AdapterFrame = None
                
                def _nb_sleep(sec: float) -> None:
                    """Non-blocking sleep that processes Qt events."""
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
                
                def _send_trigger(value: int) -> bool:
                    """Send trigger signal with specified value (0=disable, 1=enable)."""
                    try:
                        dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded())
                        if dbc_available:
                            msg = self.dbc_service.find_message_by_id(trigger_msg_id)
                            if msg is not None:
                                # Include DeviceID if required by the message (default to 0)
                                device_id = act.get('device_id', 0)
                                signal_values = {'DeviceID': device_id, trigger_signal: value}
                                
                                # Check if signal is multiplexed and get MessageType from multiplexer_ids
                                # (Same logic as Fan Control Test - only set MessageType if signal is actually multiplexed)
                                mux_value = None
                                for sig in msg.signals:
                                    if sig.name == trigger_signal and getattr(sig, 'multiplexer_ids', None):
                                        mux_value = sig.multiplexer_ids[0]
                                        break
                                
                                # Only set MessageType if signal is actually multiplexed (same as Fan Control Test)
                                if mux_value is not None:
                                    signal_values['MessageType'] = mux_value
                                
                                frame_data = self.dbc_service.encode_message(msg, signal_values)
                            else:
                                logger.warning(f"Could not find message for CAN ID 0x{trigger_msg_id:X}")
                                return False
                        else:
                            # Fallback: raw encoding
                            frame_data = bytes([value & 0xFF])
                        
                        if AdapterFrame is not None:
                            frame = AdapterFrame(can_id=trigger_msg_id, data=frame_data)
                        else:
                            class F: pass
                            frame = F()
                            frame.can_id = trigger_msg_id
                            frame.data = frame_data
                            frame.timestamp = time.time()
                        
                        if self.can_service is not None and self.can_service.is_connected():
                            self.can_service.send_frame(frame)
                            logger.info(f"External 5V Test: Sent trigger signal {trigger_signal}={value}")
                            return True
                        return False
                    except Exception as e:
                        logger.error(f"Failed to send trigger: {e}")
                        return False
                
                def _collect_data_phase(phase_name: str, clear_plot: bool = False) -> tuple[list, list]:
                    """Collect data during dwell time for a phase.
                    
                    Returns:
                        Tuple of (eol_values, feedback_values)
                    """
                    if clear_plot and self.plot_clear_callback is not None:
                        self.plot_clear_callback()
                    
                    eol_values = []
                    feedback_values = []
                    start_time = time.time()
                    end_time = start_time + (dwell_ms / 1000.0)
                    
                    logger.info(f"External 5V Test ({phase_name}): Collecting data for {dwell_ms}ms...")
                    
                    while time.time() < end_time:
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
                                    eol_float = float(eol_val)
                                    eol_values.append(eol_float)
                                    # Update plot with EOL value (as "Current Signal")
                                    if self.plot_update_callback is not None:
                                        # Use feedback value if available, otherwise use EOL value for x-axis
                                        fb_val_for_plot = feedback_values[-1] if feedback_values else eol_float
                                        self.plot_update_callback(fb_val_for_plot, eol_float, 'EOL')
                                except (ValueError, TypeError):
                                    pass
                        except Exception as e:
                            logger.debug(f"Error reading EOL signal: {e}")
                        
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
                                    fb_float = float(fb_val)
                                    feedback_values.append(fb_float)
                                    # Update plot with Feedback value (as "Feedback Signal")
                                    if self.plot_update_callback is not None:
                                        eol_val_for_plot = eol_values[-1] if eol_values else fb_float
                                        self.plot_update_callback(fb_float, eol_val_for_plot, 'Feedback')
                                except (ValueError, TypeError):
                                    pass
                        except Exception as e:
                            logger.debug(f"Error reading feedback signal: {e}")
                        
                        # Update labels for real-time monitoring
                        if self.label_update_callback is not None:
                            fb_display = feedback_values[-1] if feedback_values else None
                            eol_display = eol_values[-1] if eol_values else None
                            if fb_display is not None:
                                self.label_update_callback(f"Feedback Signal: {fb_display:.2f} mV")
                            if eol_display is not None:
                                self.label_update_callback(f"Current Signal: {eol_display:.2f} mV")
                        
                        # Process events and sleep
                        try:
                            QtCore.QCoreApplication.processEvents()
                        except Exception:
                            pass
                        time.sleep(SLEEP_INTERVAL_SHORT)
                    
                    return eol_values, feedback_values
                
                # Phase 1: Disabled state
                logger.info("External 5V Test: Phase 1 - Disabling External 5V...")
                if not _send_trigger(0):
                    return False, "Failed to send disable trigger"
                
                logger.info(f"External 5V Test: Waiting {pre_dwell_ms}ms for system stabilization (disabled)...")
                _nb_sleep(pre_dwell_ms / 1000.0)
                
                eol_values_disabled, feedback_values_disabled = _collect_data_phase("Disabled", clear_plot=False)
                
                # Phase 2: Enabled state
                logger.info("External 5V Test: Phase 2 - Enabling External 5V...")
                if not _send_trigger(1):
                    return False, "Failed to send enable trigger"
                
                logger.info(f"External 5V Test: Waiting {pre_dwell_ms}ms for system stabilization (enabled)...")
                _nb_sleep(pre_dwell_ms / 1000.0)
                
                eol_values_enabled, feedback_values_enabled = _collect_data_phase("Enabled", clear_plot=True)
                
                # Disable again
                logger.info("External 5V Test: Disabling External 5V...")
                _send_trigger(0)
                
                # Calculate averages for both phases
                if not eol_values_disabled or not feedback_values_disabled:
                    return False, f"No data collected during disabled phase (EOL samples: {len(eol_values_disabled)}, Feedback samples: {len(feedback_values_disabled)})"
                
                if not eol_values_enabled or not feedback_values_enabled:
                    return False, f"No data collected during enabled phase (EOL samples: {len(eol_values_enabled)}, Feedback samples: {len(feedback_values_enabled)})"
                
                eol_avg_disabled = sum(eol_values_disabled) / len(eol_values_disabled)
                feedback_avg_disabled = sum(feedback_values_disabled) / len(feedback_values_disabled)
                
                eol_avg_enabled = sum(eol_values_enabled) / len(eol_values_enabled)
                feedback_avg_enabled = sum(feedback_values_enabled) / len(feedback_values_enabled)
                
                # Compare for both phases
                difference_disabled = abs(feedback_avg_disabled - eol_avg_disabled)
                difference_enabled = abs(feedback_avg_enabled - eol_avg_enabled)
                
                passed_disabled = difference_disabled <= tolerance_mv
                passed_enabled = difference_enabled <= tolerance_mv
                passed = passed_disabled and passed_enabled
                
                # Build info string
                info = f"Disabled Phase:\n"
                info += f"  Feedback Avg: {feedback_avg_disabled:.2f} mV, EOL Avg: {eol_avg_disabled:.2f} mV\n"
                info += f"  Difference: {difference_disabled:.2f} mV, Tolerance: {tolerance_mv:.2f} mV - {'PASS' if passed_disabled else 'FAIL'}\n"
                info += f"  Samples: EOL={len(eol_values_disabled)}, Feedback={len(feedback_values_disabled)}\n\n"
                info += f"Enabled Phase:\n"
                info += f"  Feedback Avg: {feedback_avg_enabled:.2f} mV, EOL Avg: {eol_avg_enabled:.2f} mV\n"
                info += f"  Difference: {difference_enabled:.2f} mV, Tolerance: {tolerance_mv:.2f} mV - {'PASS' if passed_enabled else 'FAIL'}\n"
                info += f"  Samples: EOL={len(eol_values_enabled)}, Feedback={len(feedback_values_enabled)}\n\n"
                
                if not passed:
                    if not passed_disabled:
                        info += f"FAIL: Disabled phase difference {difference_disabled:.2f} mV exceeds tolerance {tolerance_mv:.2f} mV\n"
                    if not passed_enabled:
                        info += f"FAIL: Enabled phase difference {difference_enabled:.2f} mV exceeds tolerance {tolerance_mv:.2f} mV\n"
                else:
                    info += f"PASS: Both phases within tolerance"
                
                # Store results for display
                test_name = test.get('name', '<unnamed>')
                result_data = {
                    'disabled': {
                        'feedback_avg': feedback_avg_disabled,
                        'eol_avg': eol_avg_disabled,
                        'difference': difference_disabled,
                        'feedback_samples': len(feedback_values_disabled),
                        'eol_samples': len(eol_values_disabled),
                        'feedback_values': feedback_values_disabled,
                        'eol_values': eol_values_disabled,
                        'phase': 'disabled'
                    },
                    'enabled': {
                        'feedback_avg': feedback_avg_enabled,
                        'eol_avg': eol_avg_enabled,
                        'difference': difference_enabled,
                        'feedback_samples': len(feedback_values_enabled),
                        'eol_samples': len(eol_values_enabled),
                        'feedback_values': feedback_values_enabled,
                        'eol_values': eol_values_enabled,
                        'phase': 'enabled'
                    },
                    'tolerance': tolerance_mv,
                    'passed': passed
                }
                
                # Store in temporary storage for retrieval by _on_test_finished
                if self.gui is not None:
                    if not hasattr(self.gui, '_test_result_data_temp'):
                        self.gui._test_result_data_temp = {}
                    self.gui._test_result_data_temp[test_name] = result_data
                
                logger.info(f"External 5V Test completed: {'PASS' if passed else 'FAIL'}")
                return passed, info
            
            elif act.get('type') == 'Fan Control Test':
                # Fan Control Test execution:
                # 1) Send Fan Test Trigger Signal = 1 to enable fan
                # 2) Wait up to Test Timeout for Fan Enabled Signal to become 1
                # 3) If Fan Enabled Signal ≠ 1 within Test Timeout → FAIL
                # 4) After Fan Enabled Signal = 1 verified, start dwell time
                # 5) During dwell time: Collect Fan Tach Feedback Signal and Fan Fault Feedback Signal continuously
                # 6) Display Fan Tach Signal Value in Real-Time Monitoring (Feedback Signal Value) continuously
                # 7) After dwell time: Check latest values
                # 8) Pass if: Fan Tach Feedback Signal = 1 AND Fan Fault Feedback Signal = 0
                
                # Extract parameters
                trigger_msg_id = act.get('fan_test_trigger_source')
                trigger_signal = act.get('fan_test_trigger_signal')
                feedback_msg_id = act.get('fan_control_feedback_source')
                fan_enabled_signal = act.get('fan_enabled_signal')
                fan_tach_signal = act.get('fan_tach_feedback_signal')
                fan_fault_signal = act.get('fan_fault_feedback_signal')
                dwell_ms = int(act.get('dwell_time_ms', 0))
                timeout_ms = int(act.get('test_timeout_ms', 0))
                
                # Validate parameters
                if not all([trigger_msg_id, trigger_signal, feedback_msg_id, fan_enabled_signal, 
                           fan_tach_signal, fan_fault_signal]):
                    return False, "Missing required Fan Control Test parameters"
                
                if dwell_ms <= 0:
                    return False, "Dwell time must be positive"
                
                if timeout_ms <= 0:
                    return False, "Test timeout must be positive"
                
                # Import AdapterFrame at function level (unified pattern)
                try:
                    from backend.adapters.interface import Frame as AdapterFrame
                except ImportError:
                    AdapterFrame = None
                
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
                
                # Helper function to encode and send CAN message
                def _encode_and_send_fan(signals: dict, msg_id: int) -> bytes:
                    """Encode signals to CAN message bytes."""
                    encode_data = {'DeviceID': 0}  # always include DeviceID
                    mux_value = None
                    data_bytes = b''
                    
                    # Use DbcService if available
                    dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded())
                    if dbc_available:
                        target_msg = self.dbc_service.find_message_by_id(msg_id)
                    else:
                        target_msg = None
                    
                    if target_msg is None:
                        logger.warning(f"Could not find message for CAN ID 0x{msg_id:X} - DBC may not be loaded or message missing")
                    
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
                    
                    return data_bytes
                
                # Step 1: Send Fan Test Trigger Signal = 1 to enable fan
                logger.info(f"Fan Control Test: Sending trigger signal to enable fan...")
                try:
                    signals = {trigger_signal: 1}
                    data_bytes = _encode_and_send_fan(signals, trigger_msg_id)
                    
                    if not data_bytes:
                        return False, "Failed to encode fan trigger message"
                    
                    # Use CanService.send_frame() with Frame object (same pattern as other tests)
                    if self.can_service is not None and self.can_service.is_connected():
                        f = AdapterFrame(can_id=trigger_msg_id, data=data_bytes, timestamp=time.time())
                        logger.debug(f"Sending fan trigger frame: can_id=0x{trigger_msg_id:X} data={data_bytes.hex()}")
                        try:
                            success = self.can_service.send_frame(f)
                            if not success:
                                logger.warning(f"send_frame returned False for can_id=0x{trigger_msg_id:X}")
                            else:
                                logger.info(f"Sent fan trigger signal (1) on message 0x{trigger_msg_id:X}, signal: {trigger_signal}")
                        except Exception as e:
                            logger.error(f"Failed to send frame via service: {e}", exc_info=True)
                            return False, f"Failed to send fan trigger signal: {e}"
                    elif self.gui is not None:
                        # Fallback: use GUI's CAN service
                        if hasattr(self.gui, 'can_service') and self.gui.can_service and self.gui.can_service.is_connected():
                            f = AdapterFrame(can_id=trigger_msg_id, data=data_bytes, timestamp=time.time())
                            logger.debug(f"Sending fan trigger frame: can_id=0x{trigger_msg_id:X} data={data_bytes.hex()}")
                            try:
                                success = self.gui.can_service.send_frame(f)
                                if not success:
                                    logger.warning(f"send_frame returned False for can_id=0x{trigger_msg_id:X}")
                                else:
                                    logger.info(f"Sent fan trigger signal (1) on message 0x{trigger_msg_id:X}, signal: {trigger_signal}")
                            except Exception as e:
                                logger.error(f"Failed to send frame via GUI service: {e}", exc_info=True)
                                return False, f"Failed to send fan trigger signal: {e}"
                        else:
                            return False, "CAN service not available. Cannot send fan trigger signal."
                    else:
                        return False, "CAN service not available. Cannot send fan trigger signal."
                except Exception as e:
                    logger.error(f"Failed to send fan trigger signal: {e}")
                    return False, f"Failed to send fan trigger signal: {e}"
                
                # Step 2: Wait up to Test Timeout for Fan Enabled Signal to become 1
                logger.info(f"Fan Control Test: Waiting for fan enabled signal (timeout: {timeout_ms}ms)...")
                fan_enabled_verified = False
                timeout_start = time.time()
                timeout_end = timeout_start + (timeout_ms / 1000.0)
                
                while time.time() < timeout_end:
                    try:
                        # Read Fan Enabled Signal
                        if self.signal_service is not None:
                            ts, enabled_val = self.signal_service.get_latest_signal(feedback_msg_id, fan_enabled_signal)
                        elif self.gui is not None:
                            ts, enabled_val = self.gui.get_latest_signal(feedback_msg_id, fan_enabled_signal)
                        else:
                            ts, enabled_val = (None, None)
                        
                        if enabled_val is not None:
                            try:
                                enabled_int = int(float(enabled_val))
                                if enabled_int == 1:
                                    fan_enabled_verified = True
                                    logger.info("Fan enabled signal verified (value = 1)")
                                    break
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading fan enabled signal: {e}")
                    
                    # Process events and sleep
                    try:
                        QtCore.QCoreApplication.processEvents()
                    except Exception:
                        pass
                    time.sleep(SLEEP_INTERVAL_SHORT)
                
                # Step 3: Check if fan enabled was verified
                if not fan_enabled_verified:
                    return False, f"Fan enabled signal did not reach 1 within timeout ({timeout_ms}ms). Check fan control configuration."
                
                # Step 4: After verification, start dwell time and collect data
                logger.info(f"Fan Control Test: Collecting fan tach and fault signals for {dwell_ms}ms...")
                fan_tach_values = []
                fan_fault_values = []
                start_time = time.time()
                end_time = start_time + (dwell_ms / 1000.0)
                
                while time.time() < end_time:
                    # Read Fan Tach Feedback Signal
                    try:
                        if self.signal_service is not None:
                            ts_tach, tach_val = self.signal_service.get_latest_signal(feedback_msg_id, fan_tach_signal)
                        elif self.gui is not None:
                            ts_tach, tach_val = self.gui.get_latest_signal(feedback_msg_id, fan_tach_signal)
                        else:
                            ts_tach, tach_val = (None, None)
                        
                        if tach_val is not None:
                            try:
                                tach_float = float(tach_val)
                                fan_tach_values.append(tach_float)
                                
                                # Update real-time display with latest value (feedback signal, not current signal)
                                if self.gui is not None and hasattr(self.gui, 'feedback_signal_label'):
                                    try:
                                        self.gui.feedback_signal_label.setText(f"{tach_float:.2f}")
                                    except Exception as e:
                                        logger.debug(f"Failed to update feedback signal label: {e}")
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading fan tach signal: {e}")
                    
                    # Read Fan Fault Feedback Signal
                    try:
                        if self.signal_service is not None:
                            ts_fault, fault_val = self.signal_service.get_latest_signal(feedback_msg_id, fan_fault_signal)
                        elif self.gui is not None:
                            ts_fault, fault_val = self.gui.get_latest_signal(feedback_msg_id, fan_fault_signal)
                        else:
                            ts_fault, fault_val = (None, None)
                        
                        if fault_val is not None:
                            try:
                                fault_float = float(fault_val)
                                fan_fault_values.append(fault_float)
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading fan fault signal: {e}")
                    
                    # Process events and sleep
                    try:
                        QtCore.QCoreApplication.processEvents()
                    except Exception:
                        pass
                    time.sleep(SLEEP_INTERVAL_SHORT)
                
                # Step 5: Disable fan by sending trigger signal = 0
                logger.info(f"Fan Control Test: Disabling fan (sending trigger signal = 0)...")
                try:
                    signals = {trigger_signal: 0}
                    data_bytes = _encode_and_send_fan(signals, trigger_msg_id)
                    
                    if not data_bytes:
                        logger.warning("Failed to encode fan disable message, but continuing with test evaluation")
                    else:
                        # Use CanService.send_frame() with Frame object
                        if self.can_service is not None and self.can_service.is_connected():
                            f = AdapterFrame(can_id=trigger_msg_id, data=data_bytes, timestamp=time.time())
                            logger.debug(f"Sending fan disable frame: can_id=0x{trigger_msg_id:X} data={data_bytes.hex()}")
                            try:
                                success = self.can_service.send_frame(f)
                                if not success:
                                    logger.warning(f"send_frame returned False for fan disable (can_id=0x{trigger_msg_id:X})")
                                else:
                                    logger.info(f"Sent fan disable signal (0) on message 0x{trigger_msg_id:X}, signal: {trigger_signal}")
                            except Exception as e:
                                logger.warning(f"Failed to send fan disable frame via service: {e}")
                        elif self.gui is not None:
                            # Fallback: use GUI's CAN service
                            if hasattr(self.gui, 'can_service') and self.gui.can_service and self.gui.can_service.is_connected():
                                f = AdapterFrame(can_id=trigger_msg_id, data=data_bytes, timestamp=time.time())
                                logger.debug(f"Sending fan disable frame: can_id=0x{trigger_msg_id:X} data={data_bytes.hex()}")
                                try:
                                    success = self.gui.can_service.send_frame(f)
                                    if not success:
                                        logger.warning(f"send_frame returned False for fan disable (can_id=0x{trigger_msg_id:X})")
                                    else:
                                        logger.info(f"Sent fan disable signal (0) on message 0x{trigger_msg_id:X}, signal: {trigger_signal}")
                                except Exception as e:
                                    logger.warning(f"Failed to send fan disable frame via GUI service: {e}")
                        else:
                            logger.warning("CAN service not available. Cannot send fan disable signal.")
                except Exception as e:
                    logger.warning(f"Failed to send fan disable signal: {e} (continuing with test evaluation)")
                
                # Step 6: Check if any data was collected
                if not fan_tach_values:
                    return False, f"No fan tach data received during dwell time ({dwell_ms}ms). Check CAN connection and signal configuration."
                
                if not fan_fault_values:
                    return False, f"No fan fault data received during dwell time ({dwell_ms}ms). Check CAN connection and signal configuration."
                
                # Step 7: Use latest values for pass/fail determination
                latest_tach = fan_tach_values[-1]
                latest_fault = fan_fault_values[-1]
                
                # Step 8: Determine pass/fail
                # Pass if: Fan Tach Feedback Signal = 1 AND Fan Fault Feedback Signal = 0
                tach_ok = (int(float(latest_tach)) == 1)
                fault_ok = (int(float(latest_fault)) == 0)
                passed = tach_ok and fault_ok
                
                # Build info string
                info = f"Fan Tach Signal (latest): {latest_tach:.2f} (expected: 1), "
                info += f"Fan Fault Signal (latest): {latest_fault:.2f} (expected: 0)"
                info += f"\nTach samples collected: {len(fan_tach_values)}, Fault samples collected: {len(fan_fault_values)}"
                
                if not passed:
                    if not tach_ok:
                        info += f"\nFAIL: Fan Tach Signal is {latest_tach:.2f} (expected 1)"
                    if not fault_ok:
                        info += f"\nFAIL: Fan Fault Signal is {latest_fault:.2f} (expected 0)"
                else:
                    info += f"\nPASS: Fan Tach Signal = 1 and Fan Fault Signal = 0"
                
                # Store results for display
                test_name = test.get('name', '<unnamed>')
                result_data = {
                    'fan_tach_latest': latest_tach,
                    'fan_fault_latest': latest_fault,
                    'fan_tach_samples': len(fan_tach_values),
                    'fan_fault_samples': len(fan_fault_values),
                    'fan_tach_values': fan_tach_values,
                    'fan_fault_values': fan_fault_values,
                    'passed': passed
                }
                
                # Store in temporary storage for retrieval by _on_test_finished
                if self.gui is not None:
                    if not hasattr(self.gui, '_test_result_data_temp'):
                        self.gui._test_result_data_temp = {}
                    self.gui._test_result_data_temp[test_name] = result_data
                
                logger.info(f"Fan Control Test completed: {'PASS' if passed else 'FAIL'}")
                return passed, info
            elif act.get('type') == 'DC Bus Sensing':
                # DC Bus Sensing Test execution:
                # 1) Check if oscilloscope channel is ON (C{ch}:TRA?), if not, turn it ON (C{ch}:TRA ON) and verify
                # 2) Send TRMD AUTO to oscilloscope and start logging CAN feedback signal
                # 3) Wait for dwell time
                # 4) Stop oscilloscope acquisition (*STOP) and stop logging CAN feedback signal
                # 5) Obtain average value from oscilloscope using C{ch}:PAVA? MEAN
                # 6) Obtain average from CAN feedback signal
                # 7) Compare both averages: |osc_avg - can_avg| <= tolerance -> PASS
                
                # Extract parameters
                osc_channel_name = act.get('oscilloscope_channel')
                feedback_msg_id = act.get('feedback_signal_source')
                feedback_signal = act.get('feedback_signal')
                dwell_ms = int(act.get('dwell_time_ms', 0))
                tolerance_v = float(act.get('tolerance_v', 0))
                
                # Validate parameters
                if not all([osc_channel_name, feedback_msg_id, feedback_signal]):
                    return False, "Missing required DC Bus Sensing Test parameters (oscilloscope_channel, feedback_signal_source, feedback_signal)"
                
                if tolerance_v < 0:
                    return False, "Tolerance must be non-negative"
                
                if dwell_ms <= 0:
                    return False, "Dwell time must be positive"
                
                # Check oscilloscope service availability
                if self.oscilloscope_service is None or not self.oscilloscope_service.is_connected():
                    return False, "Oscilloscope not connected. Please connect oscilloscope before running DC Bus Sensing test."
                
                # Get oscilloscope configuration
                osc_config = None
                if self.gui is not None and hasattr(self.gui, '_oscilloscope_config'):
                    osc_config = self.gui._oscilloscope_config
                else:
                    return False, "Oscilloscope configuration not available. Please configure oscilloscope first."
                
                # Get channel number from channel name
                channel_num = self.oscilloscope_service.get_channel_number_from_name(osc_channel_name, osc_config)
                if channel_num is None:
                    return False, f"Channel '{osc_channel_name}' not found in oscilloscope configuration or not enabled"
                
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
                
                # Step 1: Check if channel is ON, turn ON if needed
                logger.info(f"DC Bus Sensing Test: Checking channel {channel_num} ({osc_channel_name})...")
                try:
                    tra_response = self.oscilloscope_service.send_command(f"C{channel_num}:TRA?")
                    if tra_response is None:
                        return False, f"Failed to query channel {channel_num} trace status"
                    
                    tra_str = tra_response.strip().upper()
                    is_on = 'ON' in tra_str or tra_str == '1' or 'TRUE' in tra_str
                    
                    if not is_on:
                        logger.info(f"Channel {channel_num} is OFF, turning ON...")
                        self.oscilloscope_service.send_command(f"C{channel_num}:TRA ON")
                        time.sleep(0.2)  # Small delay for command processing
                        
                        # Verify it's now ON
                        tra_response = self.oscilloscope_service.send_command(f"C{channel_num}:TRA?")
                        if tra_response is None:
                            return False, f"Failed to verify channel {channel_num} trace status after enabling"
                        
                        tra_str = tra_response.strip().upper()
                        is_on = 'ON' in tra_str or tra_str == '1' or 'TRUE' in tra_str
                        if not is_on:
                            return False, f"Failed to enable channel {channel_num} trace"
                        
                        logger.info(f"Channel {channel_num} enabled successfully")
                    else:
                        logger.info(f"Channel {channel_num} is already ON")
                except Exception as e:
                    return False, f"Error checking/enabling channel {channel_num}: {e}"
                
                # Step 2: Send TRMD AUTO and start logging CAN feedback signal
                logger.info("DC Bus Sensing Test: Starting oscilloscope acquisition (TRMD AUTO)...")
                try:
                    self.oscilloscope_service.send_command("TRMD AUTO")
                    time.sleep(0.2)  # Small delay for command processing
                except Exception as e:
                    return False, f"Failed to start oscilloscope acquisition: {e}"
                
                # Start collecting CAN feedback signal values
                can_feedback_values = []
                collecting_can_data = True
                
                logger.info(f"DC Bus Sensing Test: Collecting CAN feedback signal for {dwell_ms}ms...")
                start_time = time.time()
                end_time = start_time + (dwell_ms / 1000.0)
                
                # Step 3: Collect CAN data during dwell time
                while time.time() < end_time and collecting_can_data:
                    try:
                        if self.signal_service is not None:
                            ts_fb, fb_val = self.signal_service.get_latest_signal(feedback_msg_id, feedback_signal)
                        elif self.gui is not None:
                            ts_fb, fb_val = self.gui.get_latest_signal(feedback_msg_id, feedback_signal)
                        else:
                            ts_fb, fb_val = (None, None)
                        
                        if fb_val is not None:
                            try:
                                # Convert to volts if needed (assuming CAN signal might be in mV)
                                fb_float = float(fb_val)
                                # If value seems to be in mV (large values > 1000), convert to V
                                if abs(fb_float) > 1000:
                                    fb_float = fb_float / 1000.0
                                can_feedback_values.append(fb_float)
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading CAN feedback signal: {e}")
                    
                    # Process events and sleep
                    try:
                        QtCore.QCoreApplication.processEvents()
                    except Exception:
                        pass
                    time.sleep(SLEEP_INTERVAL_SHORT)
                
                # Step 4: Stop oscilloscope acquisition and stop logging
                collecting_can_data = False
                logger.info("DC Bus Sensing Test: Stopping oscilloscope acquisition...")
                try:
                    # Use *STOP as per requirements (not just STOP)
                    self.oscilloscope_service.send_command("*STOP")
                    # Wait longer for acquisition to fully stop and data to be processed
                    time.sleep(0.5)  # Increased delay for command processing
                except Exception as e:
                    logger.warning(f"Failed to stop oscilloscope acquisition: {e} (continuing with analysis)")
                
                # Step 5: Obtain average from oscilloscope
                # Note: PAVA command may need additional time after STOP for oscilloscope to process data
                logger.info(f"DC Bus Sensing Test: Querying oscilloscope average (C{channel_num}:PAVA? MEAN)...")
                time.sleep(0.3)  # Additional delay before querying PAVA
                osc_avg = self.oscilloscope_service.query_pava_mean(channel_num)
                if osc_avg is None:
                    return False, f"Failed to obtain average value from oscilloscope channel {channel_num}"
                
                # Step 6: Calculate average from CAN feedback signal
                if not can_feedback_values:
                    return False, f"No CAN feedback data collected during dwell time ({dwell_ms}ms). Check CAN connection and signal configuration."
                
                can_avg = sum(can_feedback_values) / len(can_feedback_values)
                
                # Step 7: Compare and determine pass/fail
                difference = abs(osc_avg - can_avg)
                passed = difference <= tolerance_v
                
                # Build info string
                info = f"Oscilloscope Average: {osc_avg:.4f} V, CAN Average: {can_avg:.4f} V, "
                info += f"Difference: {difference:.4f} V, Tolerance: {tolerance_v:.4f} V"
                info += f"\nCAN samples collected: {len(can_feedback_values)}"
                
                if not passed:
                    info += f"\nFAIL: Difference {difference:.4f} V exceeds tolerance {tolerance_v:.4f} V"
                else:
                    info += f"\nPASS: Difference {difference:.4f} V within tolerance {tolerance_v:.4f} V"
                
                # Store results for display
                test_name = test.get('name', '<unnamed>')
                result_data = {
                    'oscilloscope_avg': osc_avg,
                    'can_avg': can_avg,
                    'difference': difference,
                    'tolerance': tolerance_v,
                    'can_samples': len(can_feedback_values),
                    'can_values': can_feedback_values,
                    'oscilloscope_channel': osc_channel_name,
                    'channel_number': channel_num
                }
                
                # Store in temporary storage for retrieval by _on_test_finished
                if self.gui is not None:
                    if not hasattr(self.gui, '_test_result_data_temp'):
                        self.gui._test_result_data_temp = {}
                    self.gui._test_result_data_temp[test_name] = result_data
                
                logger.info(f"DC Bus Sensing Test completed: {'PASS' if passed else 'FAIL'}")
                return passed, info
            elif act.get('type') == 'Output Current Calibration':
                # Output Current Calibration Test execution:
                # 1) Verify oscilloscope setup (TDIV, TRA, probe attenuation)
                # 2) Generate current setpoints array
                # 3) Initialize plot
                # 4) Send test trigger to DUT
                # 5) For each setpoint:
                #    a. Send current setpoint
                #    b. Wait pre-acquisition time
                #    c. Start CAN logging and oscilloscope acquisition
                #    d. Collect data during acquisition time
                #    e. Stop data collection
                #    f. Calculate averages and update plot
                # 6) Disable test mode
                # 7) Perform linear regression and calculate gain error
                # 8) Determine pass/fail
                
                # Extract parameters
                test_trigger_source = act.get('test_trigger_source')
                test_trigger_signal = act.get('test_trigger_signal')
                test_trigger_signal_value = act.get('test_trigger_signal_value')
                current_setpoint_signal = act.get('current_setpoint_signal')
                feedback_msg_id = act.get('feedback_signal_source')
                feedback_signal = act.get('feedback_signal')
                osc_channel_name = act.get('oscilloscope_channel')
                osc_timebase = act.get('oscilloscope_timebase')
                min_current = float(act.get('minimum_test_current', 0))
                max_current = float(act.get('maximum_test_current', 0))
                step_current = float(act.get('step_current', 0))
                pre_acq_ms = int(act.get('pre_acquisition_time_ms', 0))
                acq_ms = int(act.get('acquisition_time_ms', 0))
                tolerance_percent = float(act.get('tolerance_percent', 0))
                
                # Validate parameters
                if not all([test_trigger_source, test_trigger_signal, test_trigger_signal_value is not None,
                           current_setpoint_signal, feedback_msg_id, feedback_signal, osc_channel_name, osc_timebase]):
                    return False, "Missing required Output Current Calibration Test parameters"
                
                if not (0 <= test_trigger_signal_value <= 255):
                    return False, f"Test trigger signal value must be in range 0-255, got {test_trigger_signal_value}"
                
                if min_current < 0 or max_current < 0:
                    return False, "Minimum and maximum test current must be non-negative"
                
                if max_current < min_current:
                    return False, f"Maximum test current ({max_current}) must be >= minimum ({min_current})"
                
                if step_current < 0.1:
                    return False, f"Step current must be >= 0.1 A, got {step_current}"
                
                if pre_acq_ms < 0:
                    return False, "Pre-acquisition time must be non-negative"
                
                if acq_ms <= 0:
                    return False, "Acquisition time must be positive"
                
                if tolerance_percent < 0:
                    return False, "Tolerance must be non-negative"
                
                # Check oscilloscope service availability
                if self.oscilloscope_service is None or not self.oscilloscope_service.is_connected():
                    return False, "Oscilloscope not connected. Please connect oscilloscope before running Output Current Calibration test."
                
                # Check DBC service availability
                if self.dbc_service is None or not self.dbc_service.is_loaded():
                    return False, "Output Current Calibration requires DBC file to be loaded"
                
                # Get oscilloscope configuration
                osc_config = None
                if self.gui is not None and hasattr(self.gui, '_oscilloscope_config'):
                    osc_config = self.gui._oscilloscope_config
                else:
                    return False, "Oscilloscope configuration not available. Please configure oscilloscope first."
                
                # Get channel number from channel name
                channel_num = self.oscilloscope_service.get_channel_number_from_name(osc_channel_name, osc_config)
                if channel_num is None:
                    return False, f"Channel '{osc_channel_name}' not found in oscilloscope configuration or not enabled"
                
                # Import AdapterFrame at function level (unified pattern)
                try:
                    from backend.adapters.interface import Frame as AdapterFrame
                except ImportError:
                    AdapterFrame = None
                
                def _nb_sleep(sec: float) -> None:
                    """Non-blocking sleep that processes Qt events."""
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
                
                # Step 1: Verify oscilloscope setup
                logger.info(f"Output Current Calibration: Verifying oscilloscope setup...")
                try:
                    # Check connection
                    if not self.oscilloscope_service.is_connected():
                        return False, "Oscilloscope not connected"
                    
                    # Set and verify timebase
                    logger.info(f"Setting oscilloscope timebase to {osc_timebase}...")
                    self.oscilloscope_service.send_command(f"TDIV {osc_timebase}")
                    time.sleep(0.2)
                    
                    tdiv_response = self.oscilloscope_service.send_command("TDIV?")
                    if tdiv_response is None:
                        return False, "Failed to verify oscilloscope timebase"
                    
                    # Parse timebase response (format may vary, check if it contains our value)
                    tdiv_str = tdiv_response.strip().upper()
                    if osc_timebase.upper() not in tdiv_str:
                        logger.warning(f"Timebase verification: expected {osc_timebase}, got {tdiv_response}")
                        # Continue anyway, might be a parsing issue
                    
                    # Enable channel and verify
                    logger.info(f"Enabling channel {channel_num} ({osc_channel_name})...")
                    tra_response = self.oscilloscope_service.send_command(f"C{channel_num}:TRA?")
                    if tra_response is None:
                        return False, f"Failed to query channel {channel_num} trace status"
                    
                    tra_str = tra_response.strip().upper()
                    is_on = 'ON' in tra_str or tra_str == '1' or 'TRUE' in tra_str
                    
                    if not is_on:
                        logger.info(f"Channel {channel_num} is OFF, turning ON...")
                        self.oscilloscope_service.send_command(f"C{channel_num}:TRA ON")
                        time.sleep(0.2)
                        
                        # Verify it's now ON
                        tra_response = self.oscilloscope_service.send_command(f"C{channel_num}:TRA?")
                        if tra_response is None:
                            return False, f"Failed to verify channel {channel_num} trace status after enabling"
                        
                        tra_str = tra_response.strip().upper()
                        is_on = 'ON' in tra_str or tra_str == '1' or 'TRUE' in tra_str
                        if not is_on:
                            return False, f"Failed to enable channel {channel_num} trace"
                        
                        logger.info(f"Channel {channel_num} enabled successfully")
                    else:
                        logger.info(f"Channel {channel_num} is already ON")
                    
                    # Verify probe attenuation (optional check)
                    # Get channel config from oscilloscope config
                    channel_config = None
                    if osc_config and 'channels' in osc_config:
                        for ch_key, ch_cfg in osc_config['channels'].items():
                            if ch_cfg.get('name') == osc_channel_name:
                                channel_config = ch_cfg
                                break
                    
                    if channel_config and 'probe_attenuation' in channel_config:
                        expected_attenuation = channel_config['probe_attenuation']
                        # Query actual attenuation (if supported by oscilloscope)
                        # Note: Some oscilloscopes may not support this query, so we'll skip if it fails
                        try:
                            attn_response = self.oscilloscope_service.send_command(f"C{channel_num}:ATTN?")
                            if attn_response:
                                # Parse attenuation from response
                                import re
                                attn_match = re.search(r'([\d.]+)', attn_response)
                                if attn_match:
                                    actual_attenuation = float(attn_match.group(1))
                                    if abs(actual_attenuation - expected_attenuation) > 0.1:
                                        logger.warning(f"Probe attenuation mismatch: expected {expected_attenuation}, got {actual_attenuation}")
                        except Exception as e:
                            logger.debug(f"Could not verify probe attenuation: {e}")
                    
                    logger.info("Oscilloscope setup verified successfully")
                except Exception as e:
                    return False, f"Failed to verify oscilloscope setup: {e}"
                
                # Step 2: Generate current setpoints array
                logger.info(f"Generating current setpoints from {min_current}A to {max_current}A with step {step_current}A...")
                current_setpoints = []
                current = min_current
                while current <= max_current + 0.001:  # Add small epsilon for floating point comparison
                    current_setpoints.append(round(current, 3))
                    current += step_current
                
                if not current_setpoints:
                    return False, "No current setpoints generated. Check minimum, maximum, and step current values."
                
                logger.info(f"Generated {len(current_setpoints)} setpoints: {current_setpoints}")
                
                # Initialize plot
                if self.plot_clear_callback is not None:
                    self.plot_clear_callback()
                
                # Initialize plot labels and title for Output Current Calibration
                test_name = test.get('name', '')
                if self.gui is not None and hasattr(self.gui, '_initialize_output_current_plot'):
                    try:
                        self.gui._initialize_output_current_plot(test_name)
                    except Exception as e:
                        logger.debug(f"Failed to initialize Output Current Calibration plot: {e}")
                
                if self.label_update_callback is not None:
                    self.label_update_callback("Output Current Calibration: Initializing...")
                
                # Initialize data storage
                can_averages = []
                osc_averages = []
                setpoint_values = []
                
                # Step 3: Send test trigger to DUT
                logger.info(f"Sending test trigger to DUT (signal={test_trigger_signal}, value={test_trigger_signal_value})...")
                try:
                    # Find message and encode
                    trigger_msg = self.dbc_service.find_message_by_id(test_trigger_source)
                    if trigger_msg is None:
                        return False, f"Test trigger message (ID: 0x{test_trigger_source:X}) not found in DBC"
                    
                    # Build signal values dict - include required signals (DeviceID, MessageType) if they exist
                    signal_values = {}
                    
                    # Get all signals from the message to check for required ones
                    all_signals = self.dbc_service.get_message_signals(trigger_msg)
                    signal_names = [sig.name for sig in all_signals]
                    
                    # Include DeviceID if it exists (default to 0)
                    if 'DeviceID' in signal_names:
                        signal_values['DeviceID'] = 0
                    
                    # Check if test_trigger_signal is multiplexed and get MessageType from multiplexer_ids
                    mux_value = None
                    for sig in all_signals:
                        if sig.name == test_trigger_signal and getattr(sig, 'multiplexer_ids', None):
                            mux_value = sig.multiplexer_ids[0]
                            break
                    
                    # Only set MessageType if signal is actually multiplexed
                    if mux_value is not None:
                        signal_values['MessageType'] = mux_value
                        logger.info(f"Using MessageType={mux_value} from multiplexor for {test_trigger_signal}")
                    elif 'MessageType' in signal_names:
                        # If MessageType exists but signal is not multiplexed, use default 0
                        signal_values['MessageType'] = 0
                    
                    # Add the signal we actually want to set (only test_trigger_signal for initial trigger)
                    signal_values[test_trigger_signal] = test_trigger_signal_value
                    # Note: current_setpoint_signal is sent separately in the setpoint loop, not in the initial trigger
                    
                    frame_data = self.dbc_service.encode_message(trigger_msg, signal_values)
                    if AdapterFrame is not None:
                        frame = AdapterFrame(can_id=test_trigger_source, data=frame_data)
                    else:
                        # Fallback if AdapterFrame not available
                        class Frame:
                            def __init__(self, can_id, data):
                                self.can_id = can_id
                                self.data = data
                        frame = Frame(can_id=test_trigger_source, data=frame_data)
                    
                    if not self.can_service.send_frame(frame):
                        return False, "Failed to send test trigger message to DUT"
                    
                    logger.info("Test trigger sent successfully")
                    _nb_sleep(0.5)  # Small delay for DUT to initialize
                except Exception as e:
                    return False, f"Failed to send test trigger: {e}"
                
                # Step 4: Iterate through current setpoints
                test_name = test.get('name', '<unnamed>')
                for setpoint_idx, setpoint in enumerate(current_setpoints):
                    logger.info(f"Testing setpoint {setpoint_idx + 1}/{len(current_setpoints)}: {setpoint}A")
                    
                    # 4a. Send current setpoint
                    try:
                        # Build signal values dict - include required signals (DeviceID, MessageType) if they exist
                        signal_values = {}
                        
                        # Get all signals from the message to check for required ones
                        all_signals = self.dbc_service.get_message_signals(trigger_msg)
                        signal_names = [sig.name for sig in all_signals]
                        
                        # Include DeviceID if it exists (default to 0)
                        if 'DeviceID' in signal_names:
                            signal_values['DeviceID'] = 0
                        
                        # Check if current_setpoint_signal is multiplexed and get MessageType from multiplexer_ids
                        # If not, check if test_trigger_signal is multiplexed (use same MessageType as trigger)
                        mux_value = None
                        for sig in all_signals:
                            if sig.name == current_setpoint_signal and getattr(sig, 'multiplexer_ids', None):
                                mux_value = sig.multiplexer_ids[0]
                                break
                        
                        # If current_setpoint_signal is not multiplexed, check test_trigger_signal
                        if mux_value is None:
                            for sig in all_signals:
                                if sig.name == test_trigger_signal and getattr(sig, 'multiplexer_ids', None):
                                    mux_value = sig.multiplexer_ids[0]
                                    break
                        
                        # Only set MessageType if signal is actually multiplexed
                        if mux_value is not None:
                            signal_values['MessageType'] = mux_value
                        elif 'MessageType' in signal_names:
                            # If MessageType exists but signal is not multiplexed, use default 0
                            signal_values['MessageType'] = 0
                        
                        # Add the signal we actually want to set
                        signal_values[current_setpoint_signal] = setpoint
                        
                        frame_data = self.dbc_service.encode_message(trigger_msg, signal_values)
                        if AdapterFrame is not None:
                            frame = AdapterFrame(can_id=test_trigger_source, data=frame_data)
                        else:
                            # Fallback if AdapterFrame not available
                            class Frame:
                                def __init__(self, can_id, data):
                                    self.can_id = can_id
                                    self.data = data
                            frame = Frame(can_id=test_trigger_source, data=frame_data)
                        
                        if not self.can_service.send_frame(frame):
                            logger.warning(f"Failed to send current setpoint {setpoint}A, continuing...")
                            continue
                        
                        logger.info(f"Sent current setpoint: {setpoint}A")
                    except Exception as e:
                        logger.warning(f"Failed to send current setpoint {setpoint}A: {e}, continuing...")
                        continue
                    
                    # 4b. Wait for pre-acquisition time
                    logger.info(f"Waiting {pre_acq_ms}ms for current to stabilize...")
                    _nb_sleep(pre_acq_ms / 1000.0)
                    
                    # 4c. Start data acquisition
                    logger.info(f"Starting data acquisition for {acq_ms}ms...")
                    can_feedback_values = []
                    collecting_can_data = True
                    
                    try:
                        # Start oscilloscope acquisition
                        self.oscilloscope_service.send_command("TRMD AUTO")
                        time.sleep(0.2)
                    except Exception as e:
                        logger.warning(f"Failed to start oscilloscope acquisition: {e}, continuing...")
                    
                    # 4d. Collect data during acquisition time
                    start_time = time.time()
                    end_time = start_time + (acq_ms / 1000.0)
                    
                    while time.time() < end_time and collecting_can_data:
                        try:
                            if self.signal_service is not None:
                                ts_fb, fb_val = self.signal_service.get_latest_signal(feedback_msg_id, feedback_signal)
                            elif self.gui is not None:
                                ts_fb, fb_val = self.gui.get_latest_signal(feedback_msg_id, feedback_signal)
                            else:
                                ts_fb, fb_val = (None, None)
                            
                            if fb_val is not None:
                                try:
                                    fb_float = float(fb_val)
                                    can_feedback_values.append(fb_float)
                                except (ValueError, TypeError):
                                    pass
                        except Exception as e:
                            logger.debug(f"Error reading CAN feedback signal: {e}")
                        
                        try:
                            QtCore.QCoreApplication.processEvents()
                        except Exception:
                            pass
                        time.sleep(SLEEP_INTERVAL_SHORT)
                    
                    # 4e. Stop data acquisition
                    collecting_can_data = False
                    logger.info("Stopping data acquisition...")
                    try:
                        self.oscilloscope_service.send_command("STOP")
                        time.sleep(0.5)  # Wait for acquisition to stop
                    except Exception as e:
                        logger.warning(f"Failed to stop oscilloscope acquisition: {e}")
                    
                    # 4f. Analyze data and update plot
                    if not can_feedback_values:
                        logger.warning(f"No CAN data collected at setpoint {setpoint}A, skipping...")
                        continue
                    
                    # Calculate CAN average
                    can_avg = sum(can_feedback_values) / len(can_feedback_values)
                    
                    # Query oscilloscope average
                    time.sleep(0.3)  # Additional delay before querying PAVA
                    osc_avg = self.oscilloscope_service.query_pava_mean(channel_num)
                    if osc_avg is None:
                        logger.warning(f"Failed to obtain oscilloscope average at setpoint {setpoint}A, skipping...")
                        continue
                    
                    # Store data
                    can_averages.append(can_avg)
                    osc_averages.append(osc_avg)
                    setpoint_values.append(setpoint)
                    
                    logger.info(f"Setpoint {setpoint}A: CAN avg={can_avg:.4f}A, Osc avg={osc_avg:.4f}A")
                    
                    # Update plot
                    if self.plot_update_callback is not None:
                        self.plot_update_callback(osc_avg, can_avg, test_name)
                    
                    if self.label_update_callback is not None:
                        self.label_update_callback(f"Output Current Calibration: Setpoint {setpoint_idx + 1}/{len(current_setpoints)} ({setpoint}A) - CAN: {can_avg:.3f}A, Osc: {osc_avg:.3f}A")
                
                # Step 5: Disable test mode
                logger.info("Disabling test mode at DUT...")
                try:
                    # Build signal values dict - include required signals (DeviceID, MessageType) if they exist
                    signal_values = {}
                    
                    # Get all signals from the message to check for required ones
                    all_signals = self.dbc_service.get_message_signals(trigger_msg)
                    signal_names = [sig.name for sig in all_signals]
                    
                    # Include DeviceID if it exists (default to 0)
                    if 'DeviceID' in signal_names:
                        signal_values['DeviceID'] = 0
                    
                    # Check if test_trigger_signal is multiplexed and get MessageType from multiplexer_ids
                    mux_value = None
                    for sig in all_signals:
                        if sig.name == test_trigger_signal and getattr(sig, 'multiplexer_ids', None):
                            mux_value = sig.multiplexer_ids[0]
                            break
                    
                    # Only set MessageType if signal is actually multiplexed
                    if mux_value is not None:
                        signal_values['MessageType'] = mux_value
                    elif 'MessageType' in signal_names:
                        # If MessageType exists but signal is not multiplexed, use default 0
                        signal_values['MessageType'] = 0
                    
                    # Add the signal we actually want to set
                    signal_values[test_trigger_signal] = 0  # Disable test mode
                    
                    frame_data = self.dbc_service.encode_message(trigger_msg, signal_values)
                    if AdapterFrame is not None:
                        frame = AdapterFrame(can_id=test_trigger_source, data=frame_data)
                    else:
                        # Fallback if AdapterFrame not available
                        class Frame:
                            def __init__(self, can_id, data):
                                self.can_id = can_id
                                self.data = data
                        frame = Frame(can_id=test_trigger_source, data=frame_data)
                    self.can_service.send_frame(frame)
                    logger.info("Test mode disabled")
                except Exception as e:
                    logger.warning(f"Failed to disable test mode: {e}")
                
                # Step 6: Perform linear regression and calculate gain error
                if len(can_averages) < 2:
                    return False, f"Insufficient data points collected. Need at least 2 setpoints, got {len(can_averages)}. Check CAN connection and signal configuration."
                
                logger.info(f"Performing linear regression on {len(can_averages)} data points...")
                
                # Linear regression: Y = slope * X + intercept
                # X = oscilloscope averages (reference)
                # Y = CAN averages (DUT measurements)
                try:
                    # Try using numpy if available
                    try:
                        import numpy as np
                        # Use numpy polyfit for linear regression (degree 1)
                        coeffs = np.polyfit(osc_averages, can_averages, 1)
                        slope = float(coeffs[0])
                        intercept = float(coeffs[1])
                    except ImportError:
                        # Manual linear regression calculation
                        n = len(osc_averages)
                        sum_x = sum(osc_averages)
                        sum_y = sum(can_averages)
                        sum_xy = sum(osc_averages[i] * can_averages[i] for i in range(n))
                        sum_x2 = sum(x * x for x in osc_averages)
                        
                        denominator = n * sum_x2 - sum_x * sum_x
                        if abs(denominator) < 1e-10:
                            return False, "Cannot perform linear regression: data points are collinear or insufficient variation"
                        
                        slope = (n * sum_xy - sum_x * sum_y) / denominator
                        intercept = (sum_y - slope * sum_x) / n
                    
                    # Calculate gain error
                    ideal_slope = 1.0
                    gain_error = abs(slope - ideal_slope) * 100.0
                    adjustment_factor = 1.0 / slope if abs(slope) > 1e-10 else None
                    
                    # Determine pass/fail
                    passed = gain_error <= tolerance_percent
                    
                    # Build info string
                    info = f"Linear Regression Results:\n"
                    info += f"  Slope: {slope:.6f} (ideal: 1.0)\n"
                    info += f"  Intercept: {intercept:.6f} A\n"
                    info += f"  Gain Error: {gain_error:.4f}%\n"
                    if adjustment_factor is not None:
                        info += f"  Adjustment Factor: {adjustment_factor:.6f}\n"
                    info += f"  Tolerance: {tolerance_percent:.4f}%\n"
                    info += f"  Data Points: {len(can_averages)}\n"
                    info += f"\nSetpoint Results:\n"
                    for i, (sp, can_avg, osc_avg) in enumerate(zip(setpoint_values, can_averages, osc_averages)):
                        info += f"  {sp}A: CAN={can_avg:.4f}A, Osc={osc_avg:.4f}A\n"
                    
                    if passed:
                        info += f"\nPASS: Gain error {gain_error:.4f}% within tolerance {tolerance_percent:.4f}%"
                    else:
                        info += f"\nFAIL: Gain error {gain_error:.4f}% exceeds tolerance {tolerance_percent:.4f}%"
                    
                    # Store results for display
                    result_data = {
                        'slope': slope,
                        'intercept': intercept,
                        'gain_error': gain_error,
                        'adjustment_factor': adjustment_factor,
                        'tolerance_percent': tolerance_percent,
                        'data_points': len(can_averages),
                        'setpoint_values': setpoint_values,
                        'can_averages': can_averages,
                        'osc_averages': osc_averages,
                        'oscilloscope_channel': osc_channel_name,
                        'channel_number': channel_num
                    }
                    
                    # Store plot data for reports (osc_averages as X, can_averages as Y)
                    if self.gui is not None:
                        if not hasattr(self.gui, '_test_plot_data_temp'):
                            self.gui._test_plot_data_temp = {}
                        self.gui._test_plot_data_temp[test_name] = {
                            'osc_averages': list(osc_averages),
                            'can_averages': list(can_averages),
                            'setpoint_values': list(setpoint_values),
                            'slope': slope,
                            'intercept': intercept,
                            'gain_error': gain_error,
                            'adjustment_factor': adjustment_factor,
                            'tolerance_percent': tolerance_percent
                        }
                    
                    if self.gui is not None:
                        if not hasattr(self.gui, '_test_result_data_temp'):
                            self.gui._test_result_data_temp = {}
                        self.gui._test_result_data_temp[test_name] = result_data
                    
                    logger.info(f"Output Current Calibration Test completed: {'PASS' if passed else 'FAIL'}")
                    return passed, info
                    
                except Exception as e:
                    logger.error(f"Failed to calculate calibration parameters: {e}", exc_info=True)
                    return False, f"Failed to calculate calibration parameters: {e}. Check data quality."
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


