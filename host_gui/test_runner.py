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
        POLL_INTERVAL_MS, TEST_MODE_CONTINUOUS_MATCH_REQUIRED, TEST_MODE_TOTAL_TIMEOUT,
        TEST_MODE_SIGNAL_RESEND_INTERVAL
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
    TEST_MODE_CONTINUOUS_MATCH_REQUIRED = 5.0
    TEST_MODE_TOTAL_TIMEOUT = 30.0
    TEST_MODE_SIGNAL_RESEND_INTERVAL = 1.0

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
        oscilloscope_init_callback: Optional[Callable[[Dict[str, Any]], bool]] = None,
        monitor_signal_update_callback: Optional[Callable[[str, Optional[float]], None]] = None,
        monitor_signal_reset_callback: Optional[Callable[[], None]] = None
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
            monitor_signal_update_callback: Optional callback to update real-time monitor (key, value)
            monitor_signal_reset_callback: Optional callback to reset real-time monitor labels
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
            # Use thread-safe wrappers that check thread context
            if plot_update_callback is None and hasattr(gui, '_update_plot'):
                def _thread_safe_plot_update(dac: float, fb: float, name: Optional[str] = None):
                    """Thread-safe wrapper for plot update."""
                    if gui is None:
                        return
                    try:
                        current_thread = QtCore.QThread.currentThread()
                        main_thread = QtCore.QCoreApplication.instance().thread()
                        
                        if current_thread == main_thread:
                            # Main thread - call directly
                            gui._update_plot(dac, fb, name)
                        else:
                            # Background thread - use BlockingQueuedConnection to ensure immediate update
                            # This blocks until the main thread processes the update, ensuring real-time plot updates
                            try:
                                QtCore.QMetaObject.invokeMethod(
                                    gui,
                                    '_update_plot',
                                    QtCore.Qt.ConnectionType.BlockingQueuedConnection,
                                    QtCore.Q_ARG(float, dac),
                                    QtCore.Q_ARG(float, fb),
                                    QtCore.Q_ARG(str, name or '')
                                )
                            except Exception as e:
                                # If BlockingQueuedConnection fails (e.g., deadlock risk), fall back to QueuedConnection
                                logger.debug(f"BlockingQueuedConnection failed, falling back to QueuedConnection: {e}")
                                QtCore.QMetaObject.invokeMethod(
                                    gui,
                                    '_update_plot',
                                    QtCore.Qt.ConnectionType.QueuedConnection,
                                    QtCore.Q_ARG(float, dac),
                                    QtCore.Q_ARG(float, fb),
                                    QtCore.Q_ARG(str, name or '')
                                )
                                # Small sleep to allow main thread to process the queue
                                time.sleep(0.005)  # 5ms sleep to allow main thread to process
                    except Exception as e:
                        logger.debug(f"Failed to update plot: {e}")
                self.plot_update_callback = _thread_safe_plot_update
            else:
                self.plot_update_callback = plot_update_callback
            
            if plot_clear_callback is None and hasattr(gui, '_clear_plot'):
                def _thread_safe_plot_clear():
                    """Thread-safe wrapper for plot clear."""
                    if gui is None:
                        return
                    try:
                        current_thread = QtCore.QThread.currentThread()
                        main_thread = QtCore.QCoreApplication.instance().thread()
                        
                        if current_thread == main_thread:
                            # Main thread - call directly
                            gui._clear_plot()
                        else:
                            # Background thread - use QueuedConnection
                            QtCore.QMetaObject.invokeMethod(
                                gui,
                                '_clear_plot',
                                QtCore.Qt.ConnectionType.QueuedConnection
                            )
                    except Exception as e:
                        logger.debug(f"Failed to clear plot: {e}")
                self.plot_clear_callback = _thread_safe_plot_clear
            else:
                self.plot_clear_callback = plot_clear_callback
            
            if label_update_callback is None and hasattr(gui, '_update_signal_with_status'):
                # Use the new enhanced signal update method
                # Convert string to float if possible for proper formatting
                def safe_update_signal(text):
                    try:
                        # Try to convert to float for proper unit formatting
                        value = float(text) if isinstance(text, (str, int, float)) else text
                        gui._update_signal_with_status('current_signal', value)
                    except (ValueError, TypeError):
                        # If conversion fails, use as-is
                        gui._update_signal_with_status('current_signal', text)
                self.label_update_callback = safe_update_signal
            elif label_update_callback is None and hasattr(gui, 'current_signal_label'):
                # Fallback to old method for backwards compatibility (deprecated)
                # This path should not be used in new code - use update_monitor_signal() instead
                logger.warning("Using deprecated label_update_callback fallback - consider updating to use update_monitor_signal()")
                self.label_update_callback = lambda text: gui.current_signal_label.setText(str(text))
            else:
                self.label_update_callback = label_update_callback
            
            if oscilloscope_init_callback is None and hasattr(gui, '_initialize_oscilloscope_for_test'):
                self.oscilloscope_init_callback = lambda test: gui._initialize_oscilloscope_for_test(test)
            else:
                self.oscilloscope_init_callback = oscilloscope_init_callback
            
            if monitor_signal_update_callback is None and hasattr(gui, 'update_monitor_signal'):
                self.monitor_signal_update_callback = lambda key, val: gui.update_monitor_signal(key, val)
            else:
                self.monitor_signal_update_callback = monitor_signal_update_callback
            
            if monitor_signal_reset_callback is None and hasattr(gui, 'reset_monitor_signals'):
                self.monitor_signal_reset_callback = lambda: gui.reset_monitor_signals()
            else:
                self.monitor_signal_reset_callback = monitor_signal_reset_callback
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
            self.monitor_signal_update_callback = monitor_signal_update_callback
            self.monitor_signal_reset_callback = monitor_signal_reset_callback
        
        # Reference to TestExecutionThread for thread-safe signal-based updates
        self._execution_thread = None
    
    def set_execution_thread(self, thread):
        """Set reference to TestExecutionThread for signal-based updates.
        
        Args:
            thread: TestExecutionThread instance
        """
        self._execution_thread = thread
    
    def reset_monitor_signals(self) -> None:
        """Reset real-time monitor labels (if callback available)."""
        if getattr(self, 'monitor_signal_reset_callback', None):
            try:
                self.monitor_signal_reset_callback()
            except Exception as e:
                logger.debug(f"Failed to reset monitor signals: {e}")

    def update_monitor_signal(self, key: str, value: Optional[float]) -> None:
        """Update real-time monitor label for the specified key.
        
        This method is thread-safe: if called from a background thread (TestExecutionThread),
        it uses Qt signals to safely update the GUI. If called from the main thread,
        it calls the callback directly.
        """
        # Check if we're in a background thread and have a thread reference
        if hasattr(self, '_execution_thread') and self._execution_thread is not None:
            # Check if we're in the main thread
            try:
                from PySide6 import QtCore
                current_thread = QtCore.QThread.currentThread()
                main_thread = QtCore.QCoreApplication.instance().thread()
                
                if current_thread != main_thread:
                    # We're in a background thread - use signal for thread-safe GUI update
                    try:
                        # Convert None to 0.0 for signal emission (signals don't support Optional)
                        signal_value = value if value is not None else 0.0
                        self._execution_thread.monitor_signal_update.emit(key, signal_value)
                        return
                    except Exception as e:
                        logger.debug(f"Failed to emit monitor signal update '{key}': {e}")
            except Exception as e:
                logger.debug(f"Failed to check thread context: {e}")
        
        # Fallback: call callback directly (main thread or no thread reference)
        if getattr(self, 'monitor_signal_update_callback', None):
            try:
                self.monitor_signal_update_callback(key, value)
            except Exception as e:
                logger.debug(f"Failed to update monitor signal '{key}': {e}")

    def check_test_mode(self, test: Dict[str, Any], quick_check: bool = False) -> Tuple[bool, str]:
        """Check if DUT is in correct test mode before test execution.
        
        First sends the test mode value to DUT using Set DUT Test Mode Signal,
        then reads the DUT Test Status Signal from EOL HW Config and compares it
        with the test's test_mode value. Must match continuously for the required duration.
        
        Args:
            test: Test configuration dictionary with 'test_mode' field
            quick_check: If True, do a quick check (single read) instead of full validation.
                        Use this when test mode matches previous test and you just want to verify
                        it's still correct. Returns immediately if match, otherwise returns False.
            
        Returns:
            Tuple of (success: bool, message: str)
            - success: True if test mode matches continuously for required duration, False otherwise
            - message: Description of the result
        """
        import time
        import logging
        logger = logging.getLogger(__name__)
        
        # Define non-blocking sleep helper
        def _nb_sleep(sec: float):
            """Non-blocking sleep that processes Qt events."""
            end = time.time() + float(sec)
            while time.time() < end:
                remaining = end - time.time()
                if remaining <= 0:
                    break
                time.sleep(min(SLEEP_INTERVAL_SHORT, remaining))
        
        # Get test_mode from test profile (default 0)
        test_mode = test.get('test_mode', 0)
        
        # Get DUT Test Status Signal info from eol_hw_config
        if not self.eol_hw_config:
            logger.info("No EOL HW config - skipping test mode check")
            return True, "No EOL HW config - skipping test mode check"
        
        # Get EOL Command Message info for sending test mode
        eol_cmd_msg_id = self.eol_hw_config.get('eol_command_message_id')
        set_dut_test_mode_signal = self.eol_hw_config.get('set_dut_test_mode_signal')
        
        # Get DUT Feedback Message info for checking test status
        dut_feedback_msg_id = self.eol_hw_config.get('dut_feedback_message_id')
        dut_test_status_signal = self.eol_hw_config.get('dut_test_status_signal')
        
        # Quick check: If test mode matches previous test, do a single read to verify it's still correct
        if quick_check:
            if not dut_feedback_msg_id or not dut_test_status_signal:
                # Can't do quick check without feedback signal, fall through to full check
                logger.debug("Quick check requested but feedback signal not configured, doing full check")
            else:
                # Do a single read to check if signal already matches
                if self.signal_service:
                    ts, val = self.signal_service.get_latest_signal(
                        dut_feedback_msg_id, 
                        dut_test_status_signal
                    )
                elif self.gui:
                    ts, val = self.gui.get_latest_signal(
                        dut_feedback_msg_id,
                        dut_test_status_signal
                    )
                else:
                    logger.debug("Quick check requested but no signal service available, doing full check")
                    val = None
                
                if val is not None:
                    try:
                        signal_value = int(float(val))
                        if signal_value == test_mode:
                            logger.info(f"Quick test mode check passed: DUT is already in mode {test_mode}")
                            return True, f"DUT Test Mode already matches ({test_mode})"
                        else:
                            logger.debug(f"Quick check failed: signal={signal_value}, expected={test_mode}, doing full check")
                    except (ValueError, TypeError):
                        logger.debug("Quick check failed: invalid signal value, doing full check")
                else:
                    logger.debug("Quick check failed: signal not available, doing full check")
        
        # Step 1: Send test mode value to DUT using Set DUT Test Mode Signal
        next_resend_time = None
        if eol_cmd_msg_id and set_dut_test_mode_signal:
            send_success, send_msg = self.send_test_mode_command(test_mode)
            if not send_success:
                return False, send_msg
            # Schedule next resend 1 second from now
            next_resend_time = time.time() + TEST_MODE_SIGNAL_RESEND_INTERVAL
            logger.debug(f"Initial test mode command sent: {test_mode}, next resend scheduled at {next_resend_time:.2f}")
            # Small delay to allow DUT to process the command
            _nb_sleep(0.1)
        else:
            logger.info("EOL Command Message or Set DUT Test Mode Signal not configured - skipping test mode command")
        
        # Step 2: Check if DUT Test Status Signal matches
        if not dut_feedback_msg_id or not dut_test_status_signal:
            # If we sent the command but can't check, assume success
            if eol_cmd_msg_id and set_dut_test_mode_signal:
                logger.info("DUT Test Status Signal not configured - assuming test mode was set successfully")
                return True, "Test mode command sent (status check not configured)"
            else:
                logger.info("DUT Test Status Signal not configured - skipping check")
                return True, "DUT Test Status Signal not configured - skipping check"
        
        logger.info(f"Checking DUT test mode: expected={test_mode}, signal={dut_test_status_signal} (CAN ID: 0x{dut_feedback_msg_id:X})")
        
        # Monitor signal for up to total timeout, requiring continuous match for required duration
        total_timeout = TEST_MODE_TOTAL_TIMEOUT  # seconds - total time to wait
        continuous_match_required = TEST_MODE_CONTINUOUS_MATCH_REQUIRED  # seconds - must match continuously for this duration
        check_interval = 0.1  # check every 100ms
        start_time = time.time()
        match_start_time = None
        last_value = None
        
        while time.time() - start_time < total_timeout:
            current_time = time.time()
            
            # Periodically re-send test mode command until match confirmed
            # This happens first to ensure we keep sending even if signal reading fails
            if next_resend_time is not None and current_time >= next_resend_time:
                resend_success, resend_msg = self.send_test_mode_command(test_mode)
                if resend_success:
                    # Schedule next resend exactly 1 second from now
                    next_resend_time = current_time + TEST_MODE_SIGNAL_RESEND_INTERVAL
                    logger.debug(f"Re-sent test mode command: {test_mode} (periodic 1Hz), next resend at {next_resend_time:.2f}")
                else:
                    logger.warning(f"Failed to resend test mode command: {resend_msg}")
                    # Schedule retry after interval even if failed
                    next_resend_time = current_time + TEST_MODE_SIGNAL_RESEND_INTERVAL
            
            # Read signal value
            if self.signal_service:
                ts, val = self.signal_service.get_latest_signal(
                    dut_feedback_msg_id, 
                    dut_test_status_signal
                )
            elif self.gui:
                ts, val = self.gui.get_latest_signal(
                    dut_feedback_msg_id,
                    dut_test_status_signal
                )
            else:
                logger.warning("No signal service or GUI available for test mode check")
                return False, "No signal service available for test mode check"
            
            if val is None:
                # Signal not available yet
                match_start_time = None
                last_value = None
                _nb_sleep(check_interval)
                continue
            
            # Compare with test_mode
            try:
                signal_value = int(float(val))
                last_value = signal_value
                
                if signal_value == test_mode:
                    if match_start_time is None:
                        match_start_time = time.time()
                        logger.debug(f"Test mode match started: {signal_value} == {test_mode}")
                    
                    # Check if we've matched continuously for required duration
                    elapsed_match_time = time.time() - match_start_time
                    if elapsed_match_time >= continuous_match_required:
                        logger.info(f"Test mode check passed: DUT is in mode {test_mode} (matched for {elapsed_match_time:.1f}s within {time.time() - start_time:.1f}s total)")
                        return True, f"DUT Test Mode matches ({test_mode})"
                else:
                    # Mismatch - reset match timer
                    if match_start_time is not None:
                        logger.debug(f"Test mode mismatch detected: {signal_value} != {test_mode}, resetting match timer")
                    match_start_time = None
            except (ValueError, TypeError) as e:
                logger.warning(f"Error converting signal value to int: {val}, error: {e}")
                match_start_time = None
                last_value = None
            
            _nb_sleep(check_interval)
        
        # Failed to achieve required continuous match within total timeout
        elapsed_total = time.time() - start_time
        error_msg = f"DUT Test Mode mismatch: expected {test_mode}, got {last_value if last_value is not None else 'N/A'}. No continuous match for {continuous_match_required}s within {total_timeout}s timeout (elapsed: {elapsed_total:.1f}s)."
        logger.warning(error_msg)
        return False, error_msg

    def send_test_mode_command(self, test_mode_value: int) -> Tuple[bool, str]:
        """Send test mode command to DUT without validation.
        
        This method sends a test mode value to the DUT using the Set DUT Test Mode Signal
        from EOL HW Config. It does not perform validation - it only sends the command.
        This is useful for sending Idle (0) command between tests or after sequence completion.
        
        Args:
            test_mode_value: Test mode value to send (0-3, typically 0 for Idle)
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        import time
        import logging
        logger = logging.getLogger(__name__)
        
        # Define non-blocking sleep helper
        def _nb_sleep(sec: float):
            """Non-blocking sleep that processes Qt events."""
            end = time.time() + float(sec)
            while time.time() < end:
                remaining = end - time.time()
                if remaining <= 0:
                    break
                time.sleep(min(SLEEP_INTERVAL_SHORT, remaining))
        
        # Get DUT Test Status Signal info from eol_hw_config
        if not self.eol_hw_config:
            logger.info("No EOL HW config - cannot send test mode command")
            return False, "No EOL HW config - cannot send test mode command"
        
        # Get EOL Command Message info for sending test mode
        eol_cmd_msg_id = self.eol_hw_config.get('eol_command_message_id')
        set_dut_test_mode_signal = self.eol_hw_config.get('set_dut_test_mode_signal')
        
        if not eol_cmd_msg_id or not set_dut_test_mode_signal:
            logger.info("EOL Command Message or Set DUT Test Mode Signal not configured - cannot send test mode command")
            return False, "EOL Command Message or Set DUT Test Mode Signal not configured"
        
        logger.info(f"Sending test mode {test_mode_value} to DUT using signal {set_dut_test_mode_signal} (CAN ID: 0x{eol_cmd_msg_id:X})")
        
        try:
            # Check if CAN service and DBC service are available
            if not self.can_service or not self.can_service.is_connected():
                logger.warning("CAN service not connected - cannot send test mode command")
                return False, "CAN service not connected - cannot send test mode command"
            
            if not self.dbc_service or not self.dbc_service.is_loaded():
                logger.warning("DBC service not loaded - cannot encode test mode command")
                return False, "DBC service not loaded - cannot encode test mode command"
            
            # Find the command message
            cmd_msg = self.dbc_service.find_message_by_id(eol_cmd_msg_id)
            if cmd_msg is None:
                logger.warning(f"Could not find message for CAN ID 0x{eol_cmd_msg_id:X}")
                return False, f"Could not find message for CAN ID 0x{eol_cmd_msg_id:X}"
            
            # Prepare signal values for encoding
            signal_values = {}
            mux_value = None
            
            # Check if signal is multiplexed
            for sig in getattr(cmd_msg, 'signals', []):
                if sig.name == set_dut_test_mode_signal:
                    if getattr(sig, 'multiplexer_ids', None):
                        mux_value = sig.multiplexer_ids[0]
                    break
            
            # Set MessageType if signal is multiplexed
            if mux_value is not None:
                signal_values['MessageType'] = mux_value
            
            # Add DeviceID if message requires it (check if DeviceID signal exists)
            for sig in getattr(cmd_msg, 'signals', []):
                if sig.name == 'DeviceID':
                    signal_values['DeviceID'] = 0  # Default device ID, adjust if needed
                    break
            
            # Set the test mode signal value
            signal_values[set_dut_test_mode_signal] = test_mode_value
            
            # Encode the message
            if self.dbc_service is None:
                return False, "DBC service not available"
            frame_data = self.dbc_service.encode_message(cmd_msg, signal_values)
            
            # Create and send frame
            if AdapterFrame is None:
                return False, "AdapterFrame not available"
            frame = AdapterFrame(
                can_id=eol_cmd_msg_id,
                data=frame_data,
                timestamp=None
            )
            
            if self.can_service is None or not self.can_service.send_frame(frame):
                logger.error(f"Failed to send test mode command to DUT")
                return False, "Failed to send test mode command to DUT"
            
            logger.info(f"Successfully sent test mode {test_mode_value} to DUT")
            
            # Small delay to allow DUT to process the command
            _nb_sleep(0.1)
            
            return True, f"Test mode {test_mode_value} command sent successfully"
            
        except Exception as e:
            logger.error(f"Error sending test mode command: {e}", exc_info=True)
            return False, f"Error sending test mode command: {e}"

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
            # Phase Current Test requires oscilloscope - validate it's available
            if self.oscilloscope_service is None or not self.oscilloscope_service.is_connected():
                return False, "Oscilloscope not connected. Phase Current Test requires oscilloscope connection."
            
            if self.oscilloscope_init_callback:
                osc_init_success = self.oscilloscope_init_callback(test)
                if not osc_init_success:
                    logger.warning("Oscilloscope initialization failed, but continuing test")
                    # Note: We continue anyway as the state machine may handle initialization internally
            
            # Execute phase current test using state machine
            # Note: PhaseCurrentTestStateMachine still needs GUI reference for plot updates
            # This is a limitation that should be addressed in future refactoring
            state_machine = None
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
                    # Validate state machine completed successfully
                    if success is None:
                        logger.warning("Phase Current Test state machine returned None for success, treating as failure")
                        return False, info or "Phase Current Test state machine did not return success status"
                    return success, info
                except Exception as e:
                    logger.error(f"Phase Current Test state machine execution failed: {e}", exc_info=True)
                    return False, f"Phase current test state machine error: {e}"
                finally:
                    # Clean up state machine reference
                    if self.gui is not None and hasattr(self.gui, '_phase_current_state_machine'):
                        try:
                            delattr(self.gui, '_phase_current_state_machine')
                        except Exception as e:
                            logger.debug(f"Failed to clean up state machine reference: {e}")
            except Exception as e:
                logger.error(f"Phase current test execution failed: {e}", exc_info=True)
                return False, f"Phase current test error: {e}"
            finally:
                # Additional cleanup: ensure state machine is properly cleaned up
                if state_machine is not None and self.gui is not None:
                    try:
                        if hasattr(self.gui, '_phase_current_state_machine'):
                            if self.gui._phase_current_state_machine == state_machine:
                                delattr(self.gui, '_phase_current_state_machine')
                    except Exception as e:
                        logger.debug(f"Additional cleanup failed: {e}")
        
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

                # Capture QtCore in local scope for nested functions
                from PySide6 import QtCore as LocalQtCore

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
                    """Send CAN frame with improved error handling."""
                    if AdapterFrame is not None:
                        f = AdapterFrame(can_id=can_id, data=data_bytes)
                    else:
                        class F: pass
                        f = F(); f.can_id = can_id; f.data = data_bytes; f.timestamp = time.time()
                    try:
                        if self.can_service is not None and self.can_service.is_connected():
                            success = self.can_service.send_frame(f)
                            if not success:
                                logger.warning(f"send_frame returned False for CAN ID 0x{can_id:X}, signal: {sig}")
                        else:
                            logger.warning(f"CAN service not connected, cannot send frame for CAN ID 0x{can_id:X}")
                    except Exception as e:
                        logger.error(f"Failed to send frame for CAN ID 0x{can_id:X}, signal: {sig}: {e}", exc_info=True)
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
                    fb = test.get('feedback_signal')
                    fb_mid = test.get('feedback_message_id')
                    
                    # Validate feedback signal configuration
                    if not fb:
                        return False, "Feedback signal not configured in test"
                    
                    end = time.time() + (float(duration_ms) / 1000.0)
                    matched_start = None
                    poll = SLEEP_INTERVAL_SHORT
                    max_iterations = int((duration_ms / 1000.0) / poll) + 100  # Safety limit
                    iteration_count = 0
                    
                    while time.time() < end and iteration_count < max_iterations:
                        iteration_count += 1
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
                                    # Fallback: try to use signal_service if available (even without message ID)
                                    if self.signal_service is not None:
                                        # Try to find signal by name only (less efficient but works)
                                        # Note: This is a fallback - proper usage requires message_id
                                        logger.debug(f"Feedback signal '{fb}' has no message ID, attempting fallback lookup via signal_service")
                                        # Search through all cached signals for matching name
                                        all_signals = self.signal_service.get_all_signals()
                                        candidates = []
                                        for signal_key, (t, v) in all_signals.items():
                                            try:
                                                if ':' in signal_key:
                                                    _, sname = signal_key.split(':', 1)
                                                    if sname == fb:
                                                        candidates.append((t, v))
                                            except Exception:
                                                continue
                                        if candidates:
                                            candidates.sort(key=lambda x: x[0], reverse=True)
                                            ts, val = candidates[0]
                                            logger.debug(f"Found signal '{fb}' via fallback lookup")
                                        else:
                                            ts, val = (None, None)
                                            logger.debug(f"Signal '{fb}' not found in signal_service cache")
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
                max_state_transitions = 10  # Safety limit to prevent infinite loops
                state_transition_count = 0
                
                def _track_sent_command_value_thread_safe(key: str, value):
                    """Thread-safe wrapper for track_sent_command_value."""
                    if self.gui is not None and hasattr(self.gui, 'track_sent_command_value'):
                        try:
                            current_thread = LocalQtCore.QThread.currentThread()
                            main_thread = LocalQtCore.QCoreApplication.instance().thread()
                            
                            if current_thread == main_thread:
                                # Main thread - call directly
                                self.gui.track_sent_command_value(key, value)
                            else:
                                # Background thread - use QueuedConnection
                                LocalQtCore.QMetaObject.invokeMethod(
                                    self.gui,
                                    'track_sent_command_value',
                                    LocalQtCore.Qt.ConnectionType.QueuedConnection,
                                    LocalQtCore.Q_ARG(str, key),
                                    LocalQtCore.Q_ARG(float, value)
                                )
                        except Exception as e:
                            logger.debug(f"Failed to track sent command value '{key}': {e}")
                
                try:
                    while state_transition_count < max_state_transitions:
                        state_transition_count += 1
                        
                        if state == 'ENSURE_LOW':
                            _send_bytes(low_bytes)
                            # Track sent command value for monitoring (thread-safe)
                            _track_sent_command_value_thread_safe('applied_input', _parse_expected(low_val))
                            _nb_sleep(SLEEP_INTERVAL_MEDIUM)
                            state = 'ACTUATE_HIGH'
                        elif state == 'ACTUATE_HIGH':
                            _send_bytes(high_bytes)
                            # Track sent command value for monitoring (thread-safe)
                            _track_sent_command_value_thread_safe('applied_input', _parse_expected(high_val))
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
                            # Track sent command value for monitoring (thread-safe)
                            _track_sent_command_value_thread_safe('applied_input', _parse_expected(low_val))
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
                            logger.error(f"Unknown state in Digital Logic Test state machine: {state}")
                            info_parts.append(f"ERROR: Unknown state {state}")
                            break
                    
                    if state_transition_count >= max_state_transitions:
                        logger.error(f"Digital Logic Test exceeded maximum state transitions ({max_state_transitions})")
                        info_parts.append(f"ERROR: State machine exceeded maximum transitions")
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
                mux_channel_value = act.get('mux_channel_value')
                dac_cmd_sig = act.get('dac_command_signal') or act.get('dac_command')
                
                # Validate required parameters
                if not dac_cmd_sig:
                    logger.error("Analog test requires dac_command_signal but none provided")
                    return False, "Analog test failed: dac_command_signal is required but missing"
                
                # Validate MUX channel value if MUX is configured
                if mux_channel_sig and mux_channel_value is not None:
                    try:
                        mux_channel_int = int(mux_channel_value)
                        if mux_channel_int < 0:
                            logger.warning(f"MUX channel value ({mux_channel_int}) is negative, may cause issues")
                        # Typical MUX channels are 0-15, but we don't enforce strict limit
                        if mux_channel_int > 31:
                            logger.warning(f"MUX channel value ({mux_channel_int}) is unusually large (>31), may indicate configuration error")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid MUX channel value ({mux_channel_value}): {e}")
                        mux_channel_value = 0  # Default to 0 if invalid
                
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
                    
                    # Validate dwell time is sufficient for data collection
                    # Data collection period is typically DATA_COLLECTION_PERIOD_MS
                    if dwell_ms < DATA_COLLECTION_PERIOD_MS:
                        logger.warning(
                            f"Dwell time ({dwell_ms}ms) is less than data collection period ({DATA_COLLECTION_PERIOD_MS}ms). "
                            f"May not collect sufficient data."
                        )
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
                    - Optimized: Uses 25ms loop interval and batches plot updates every 50ms
                    
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
                    
                    # Optimization: Use larger loop interval to reduce iteration overhead
                    # Changed from SLEEP_INTERVAL_SHORT (5ms) to 25ms for better performance
                    DATA_COLLECTION_LOOP_INTERVAL_MS = 25
                    data_collection_loop_interval_sec = DATA_COLLECTION_LOOP_INTERVAL_MS / 1000.0
                    
                    # Optimization: Batch plot updates every 50ms instead of every iteration
                    PLOT_UPDATE_INTERVAL_MS = 50
                    plot_update_interval_sec = PLOT_UPDATE_INTERVAL_MS / 1000.0
                    
                    # Timing conversions
                    settling_time_sec = DAC_SETTLING_TIME_MS / 1000.0
                    collection_period_sec = actual_collection_period_ms / 1000.0
                    
                    start_time = time.time()
                    last_command_time = start_time
                    last_plot_update_time = start_time
                    last_event_process_time = start_time
                    
                    # Batch collection: store data points and update plot periodically
                    batched_data_points = []  # List of (dac_voltage, fb_value) tuples
                    
                    # Send initial DAC command for this voltage level
                    # Note: MUX signals should NOT be included here - they require MessageType=17,
                    # while DAC requires MessageType=18. MUX state is set separately at test start.
                    try:
                        dac_signals = {dac_cmd_sig: int(dac_voltage)}
                        _encode_and_send(dac_signals)
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
                        # Note: MUX signals are NOT included - they require different MessageType
                        if (current_time - last_command_time) >= command_interval_sec:
                            try:
                                dac_signals = {dac_cmd_sig: int(dac_voltage)}
                                _encode_and_send(dac_signals)
                                last_command_time = current_time
                            except Exception as e:
                                logger.debug(f"Error sending DAC command during settling: {e}")
                        
                        time.sleep(data_collection_loop_interval_sec)
                    
                    # Calculate when the full dwell period ends
                    dwell_end_time = step_change_time + (dwell_ms / 1000.0)
                    
                    # Now collect data for the fixed collection period
                    collection_start_time = time.time()
                    collection_end_time = collection_start_time + collection_period_sec
                    
                    data_points_collected = 0
                    
                    # Phase 1: Data collection period (after settling, before end of collection period)
                    # Optimization: Use larger loop interval and batch plot updates
                    while time.time() < collection_end_time and time.time() < dwell_end_time:
                        current_time = time.time()
                        
                        # Send DAC command every 50ms during collection (periodic resend)
                        # Note: MUX signals are NOT included - they require different MessageType
                        if (current_time - last_command_time) >= command_interval_sec:
                            try:
                                dac_signals = {dac_cmd_sig: int(dac_voltage)}
                                _encode_and_send(dac_signals)
                                last_command_time = current_time
                            except Exception as e:
                                logger.debug(f"Error sending DAC command during collection: {e}")
                        
                        # Collect feedback data points (optimized: less frequent checks)
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
                                        # Batch the data point instead of updating plot immediately
                                        batched_data_points.append((measured_dac_voltage, fb_val))
                                        data_points_collected += 1
                                    elif ts >= (dac_command_timestamp - TIMESTAMP_TOLERANCE_SEC):
                                        # This feedback value is fresh enough (within tolerance window)
                                        # Note: Allow small negative difference to handle timing precision
                                        logger.debug(
                                            f"Collecting feedback data point: DAC={measured_dac_voltage}mV (measured), "
                                            f"Feedback={fb_val}, timestamp_age={(time.time() - ts)*1000:.1f}ms"
                                        )
                                        # Batch the data point instead of updating plot immediately
                                        batched_data_points.append((measured_dac_voltage, fb_val))
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
                        
                        # Optimization: Batch plot updates every 50ms instead of every iteration
                        if (current_time - last_plot_update_time) >= plot_update_interval_sec:
                            if batched_data_points and self.plot_update_callback:
                                # Update plot with all batched points in batch mode
                                # This reduces canvas redraws and auto-scaling operations
                                try:
                                    # Add all points first - each will queue a plot update via callback
                                    for dac_val, fb_val in batched_data_points:
                                        try:
                                            self.plot_update_callback(dac_val, fb_val, test_name)
                                        except Exception as e:
                                            logger.debug(f"Error updating plot with batched point: {e}")
                                    
                                    # After queuing all plot updates via BlockingQueuedConnection,
                                    # they have already been processed in the main thread with draw()
                                    # Force a single canvas update after all batched points are added
                                    # Use direct access if in main thread
                                    if self.gui is not None and hasattr(self.gui, 'plot_canvas') and self.gui.plot_canvas is not None:
                                        try:
                                            current_thread = QtCore.QThread.currentThread()
                                            main_thread = QtCore.QCoreApplication.instance().thread()
                                            
                                            if current_thread == main_thread:
                                                # Main thread - update directly with immediate draw
                                                if hasattr(self.gui, 'plot_line') and self.gui.plot_line is not None:
                                                    if hasattr(self.gui, 'plot_dac_voltages') and hasattr(self.gui, 'plot_feedback_values'):
                                                        self.gui.plot_line.set_data(self.gui.plot_dac_voltages, self.gui.plot_feedback_values)
                                                if hasattr(self.gui, 'plot_axes') and self.gui.plot_axes is not None:
                                                    self.gui.plot_axes.relim()
                                                    self.gui.plot_axes.autoscale()
                                                # Use draw() for immediate update during test
                                                self.gui.plot_canvas.draw()
                                            # Background thread: updates already processed via BlockingQueuedConnection
                                        except Exception as e:
                                            logger.debug(f"Error finalizing batched plot update: {e}")
                                except Exception as e:
                                    logger.debug(f"Error updating plot with batched points: {e}")
                                batched_data_points.clear()
                            last_plot_update_time = current_time
                        
                        # Optimization: Use larger sleep interval (25ms instead of 5ms)
                        # This reduces loop iteration overhead while maintaining good data collection rate
                        time.sleep(data_collection_loop_interval_sec)
                    
                    # Flush any remaining batched data points
                    if batched_data_points and self.plot_update_callback:
                        try:
                            # Add all remaining points
                            for dac_val, fb_val in batched_data_points:
                                try:
                                    self.plot_update_callback(dac_val, fb_val, test_name)
                                except Exception as e:
                                    logger.debug(f"Error updating plot with final batched point: {e}")
                            
                            # Force final canvas update after all points are added
                            # Updates already processed via BlockingQueuedConnection, just ensure final redraw
                            if self.gui is not None and hasattr(self.gui, 'plot_canvas') and self.gui.plot_canvas is not None:
                                try:
                                    current_thread = QtCore.QThread.currentThread()
                                    main_thread = QtCore.QCoreApplication.instance().thread()
                                    
                                    if current_thread == main_thread:
                                        # Main thread - update directly with immediate draw
                                        if hasattr(self.gui, 'plot_line') and self.gui.plot_line is not None:
                                            if hasattr(self.gui, 'plot_dac_voltages') and hasattr(self.gui, 'plot_feedback_values'):
                                                self.gui.plot_line.set_data(self.gui.plot_dac_voltages, self.gui.plot_feedback_values)
                                        if hasattr(self.gui, 'plot_axes') and self.gui.plot_axes is not None:
                                            self.gui.plot_axes.relim()
                                            self.gui.plot_axes.autoscale()
                                        # Use draw() for immediate update
                                        self.gui.plot_canvas.draw()
                                    # Background thread: updates already processed via BlockingQueuedConnection
                                except Exception as e:
                                    logger.debug(f"Error finalizing final batched plot update: {e}")
                        except Exception as e:
                            logger.debug(f"Error flushing batched plot points: {e}")
                        batched_data_points.clear()
                    
                    # Phase 2: Continue holding DAC voltage for remaining dwell time (if any)
                    # This ensures the DAC voltage is held for the full dwell period, even after data collection ends
                    while time.time() < dwell_end_time:
                        current_time = time.time()
                        
                        # Send DAC command every 50ms to maintain the voltage level
                        # Note: MUX signals are NOT included - they require different MessageType
                        if (current_time - last_command_time) >= command_interval_sec:
                            try:
                                dac_signals = {dac_cmd_sig: int(dac_voltage)}
                                _encode_and_send(dac_signals)
                                last_command_time = current_time
                            except Exception as e:
                                logger.debug(f"Error sending DAC command during hold period: {e}")
                        
                        
                        time.sleep(SLEEP_INTERVAL_SHORT)
                    
                    # Validate that we collected some data points
                    if data_points_collected == 0:
                        logger.warning(
                            f"No feedback data points collected during {actual_collection_period_ms}ms collection period "
                            f"at DAC voltage {dac_voltage}mV. This may indicate a problem with feedback signal reception."
                        )
                    else:
                        logger.debug(
                            f"Collected {data_points_collected} data points during {actual_collection_period_ms}ms collection period "
                            f"(after {DAC_SETTLING_TIME_MS}ms settling), held DAC at {dac_voltage}mV for full {dwell_ms}ms dwell"
                        )
                    
                    return data_points_collected
                
                def _encode_and_send(signals: dict):
                    # signals: mapping of signal name -> value
                    nonlocal current_mux_enable, current_mux_channel, dac_frame_cache, last_cached_dac_voltage
                    
                    if not signals:
                        logger.warning("_encode_and_send called with empty signals dict")
                        return
                    
                    # Optimization: Check cache for DAC commands with same voltage
                    # This avoids expensive re-encoding when voltage hasn't changed
                    if dac_cmd_sig and dac_cmd_sig in signals:
                        dac_voltage_key = int(signals[dac_cmd_sig])
                        cache_key = (dac_voltage_key, current_mux_enable, current_mux_channel)
                        
                        if cache_key in dac_frame_cache and dac_voltage_key == last_cached_dac_voltage:
                            # Use cached encoded frame
                            cached_data_bytes = dac_frame_cache[cache_key]
                            try:
                                if self.can_service is not None and self.can_service.is_connected():
                                    if AdapterFrame is None:
                                        logger.error("AdapterFrame class not available")
                                        return
                                    f = AdapterFrame(can_id=can_id, data=cached_data_bytes, timestamp=time.time())
                                    success = self.can_service.send_frame(f) if self.can_service is not None else False
                                    if not success:
                                        logger.warning(f"send_frame returned False for can_id=0x{can_id:X} (cached)")
                                    
                                    # Update real-time monitoring
                                    if dac_cmd_sig in signals:
                                        try:
                                            dac_value_mv = signals[dac_cmd_sig]
                                            dac_value_v = float(dac_value_mv) / 1000.0
                                            self.update_monitor_signal('current_signal', dac_value_v)
                                        except Exception as e:
                                            logger.debug(f"Failed to update monitor signal: {e}")
                                    return
                            except Exception as e:
                                logger.debug(f"Error sending cached frame, falling back to encoding: {e}")
                                # Fall through to normal encoding if cache send fails
                    
                    encode_data = {'DeviceID': 0}  # always include DeviceID
                    mux_value = None
                    data_bytes = b''
                    # Phase 1: Use DbcService if available
                    dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded())
                    target_msg = None
                    if dbc_available:
                        try:
                            if self.dbc_service is not None:
                                target_msg = self.dbc_service.find_message_by_id(can_id)
                        except Exception as e:
                            logger.error(f"Error finding message for CAN ID 0x{can_id:X}: {e}", exc_info=True)
                            target_msg = None
                    
                    if target_msg is None:
                        logger.warning(f"Could not find message for CAN ID 0x{can_id:X} - DBC may not be loaded or message missing")
                    
                    if target_msg is not None:
                        # Defensive check: ensure target_msg has signals attribute
                        if not hasattr(target_msg, 'signals') or target_msg.signals is None:
                            logger.error(f"Message for CAN ID 0x{can_id:X} has no signals attribute - cannot encode")
                            target_msg = None
                    
                    if target_msg is not None:
                        # Check if message requires MUX signals (multiplexed message)
                        required_mux_signals = {}
                        try:
                            for sig in target_msg.signals:
                                # Defensive check: ensure signal has name attribute
                                if not hasattr(sig, 'name'):
                                    continue
                                # Check if signal is a multiplexor (MUX_Enable or MUX_Channel)
                                sig_name_lower = sig.name.lower()
                                if 'mux' in sig_name_lower:
                                    if 'enable' in sig_name_lower:
                                        required_mux_signals[sig.name] = ('enable', current_mux_enable)
                                    elif 'channel' in sig_name_lower:
                                        required_mux_signals[sig.name] = ('channel', current_mux_channel)
                        except Exception as e:
                            logger.error(f"Error processing signals for CAN ID 0x{can_id:X}: {e}", exc_info=True)
                            # Continue with empty required_mux_signals
                        
                        # Determine MessageType first based on signals being sent
                        determined_mux_value = None
                        
                        # Check if any signal in the signals dict has multiplexer_ids
                        try:
                            for sig_name in signals:
                                for sig in target_msg.signals:
                                    if not hasattr(sig, 'name'):
                                        continue
                                    if sig.name == sig_name and getattr(sig, 'multiplexer_ids', None):
                                        # Found a multiplexed signal - use its multiplexer_id
                                        multiplexer_ids = getattr(sig, 'multiplexer_ids', None)
                                        if multiplexer_ids and len(multiplexer_ids) > 0:
                                            determined_mux_value = multiplexer_ids[0]
                                            break
                                if determined_mux_value is not None:
                                    break
                        except Exception as e:
                            logger.error(f"Error determining MessageType from multiplexer_ids: {e}", exc_info=True)
                        
                        # If no multiplexed signal found, try to infer MessageType from signal names
                        if determined_mux_value is None:
                            try:
                                mtype_sig = None
                                for s in target_msg.signals:
                                    if getattr(s, 'name', '') == 'MessageType':
                                        mtype_sig = s
                                        break
                                if mtype_sig is not None:
                                    choices = getattr(mtype_sig, 'choices', None) or {}
                                    # simple heuristics: match substrings from signal name to choice name
                                    for sig_name in signals:
                                        sname_up = str(sig_name).upper()
                                        for val, cname in (choices.items() if hasattr(choices, 'items') else []):
                                            if sname_up.find('DAC') != -1 and 'DAC' in str(cname).upper():
                                                determined_mux_value = val
                                                break
                                            if sname_up.find('MUX') != -1 and 'MUX' in str(cname).upper():
                                                determined_mux_value = val
                                                break
                                            if sname_up.find('RELAY') != -1 and 'RELAY' in str(cname).upper():
                                                determined_mux_value = val
                                                break
                                        if determined_mux_value is not None:
                                            break
                            except Exception:
                                pass
                        
                        # Set MessageType if determined
                        if determined_mux_value is not None:
                            encode_data['MessageType'] = determined_mux_value
                        else:
                            # CRITICAL FIX: For multiplexed messages, MessageType is REQUIRED
                            # If we can't determine it, we need to check if the message is multiplexed
                            # and use fallback heuristics or fail with clear error
                            if target_msg is not None:
                                # Check if message has MessageType signal (indicates multiplexed message)
                                has_message_type_signal = any(sig.name == 'MessageType' for sig in target_msg.signals)
                                
                                # Check if any signal being sent is multiplexed
                                has_multiplexed_signal = False
                                for sig_name in signals:
                                    for sig in target_msg.signals:
                                        if sig.name == sig_name and getattr(sig, 'multiplexer_ids', None):
                                            has_multiplexed_signal = True
                                            break
                                    if has_multiplexed_signal:
                                        break
                                
                                # If message is multiplexed but MessageType not determined, use fallback
                                if has_message_type_signal or has_multiplexed_signal:
                                    # Try fallback with explicit signal name matching
                                    for sig_name in signals:
                                        sig_name_upper = str(sig_name).upper()
                                        if 'MUX' in sig_name_upper:
                                            # Default to MUX command type
                                            determined_mux_value = 17  # MSG_TYPE_SET_MUX
                                            encode_data['MessageType'] = determined_mux_value
                                            logger.debug(f"Fallback: Setting MessageType=17 for MUX signal '{sig_name}'")
                                            break
                                        elif 'DAC' in sig_name_upper:
                                            # Default to DAC command type
                                            determined_mux_value = 18  # MSG_TYPE_SET_DAC
                                            encode_data['MessageType'] = determined_mux_value
                                            logger.debug(f"Fallback: Setting MessageType=18 for DAC signal '{sig_name}'")
                                            break
                                        elif 'RELAY' in sig_name_upper:
                                            # Default to Relay command type
                                            determined_mux_value = 16  # MSG_TYPE_SET_RELAY
                                            encode_data['MessageType'] = determined_mux_value
                                            logger.debug(f"Fallback: Setting MessageType=16 for Relay signal '{sig_name}'")
                                            break
                                    
                                    # If still not set, this is an error condition - fail before encoding
                                    if 'MessageType' not in encode_data:
                                        error_msg = (
                                            f"Cannot determine MessageType for multiplexed message (CAN ID 0x{can_id:X}). "
                                            f"Signals: {list(signals.keys())}. "
                                            f"This is required for encoding multiplexed CAN messages."
                                        )
                                        logger.error(error_msg)
                                        raise ValueError(error_msg)
                        
                        # Update MUX state tracking when MUX signals are sent
                        if mux_enable_sig and mux_enable_sig in signals:
                            current_mux_enable = signals[mux_enable_sig]
                        if mux_channel_sig and mux_channel_sig in signals:
                            current_mux_channel = signals[mux_channel_sig]
                        
                        # Only add required_mux_signals if MessageType is 17 (MUX commands)
                        # MUX signals should NOT be added when MessageType is 18 (DAC commands) or other types
                        if determined_mux_value == 17:  # MSG_TYPE_SET_MUX = 17
                            for mux_sig_name, (mux_type, mux_val) in required_mux_signals.items():
                                if mux_sig_name not in encode_data:
                                    encode_data[mux_sig_name] = mux_val
                        
                        # Add signals from the signals dict, but filter out signals that aren't valid for the current MessageType
                        for sig_name in signals:
                            # Skip if this signal is not valid for the current MessageType
                            should_include = True
                            
                            # Check if this signal is multiplexed
                            try:
                                for sig in target_msg.signals:
                                    if not hasattr(sig, 'name') or sig.name != sig_name:
                                        continue
                                    multiplexer_ids = getattr(sig, 'multiplexer_ids', None)
                                    if multiplexer_ids:
                                        # Signal is multiplexed - only include if MessageType matches
                                        if determined_mux_value is not None:
                                            # Handle both list/tuple and single value cases
                                            if isinstance(multiplexer_ids, (list, tuple)):
                                                should_include = (determined_mux_value in multiplexer_ids)
                                            else:
                                                should_include = (determined_mux_value == multiplexer_ids)
                                        else:
                                            # No MessageType determined yet - include it and let cantools decide
                                            should_include = True
                                    # If signal has no multiplexer_ids, it's always included (e.g., DeviceID)
                                    break
                            except Exception as e:
                                logger.error(f"Error checking multiplexer_ids for signal '{sig_name}': {e}", exc_info=True)
                                # Default to including the signal if we can't check
                                should_include = True
                            
                            if should_include:
                                encode_data[sig_name] = signals[sig_name]
                        
                        # CRITICAL: Validate MessageType is set before encoding multiplexed messages
                        if target_msg is not None:
                            # Check if message requires MessageType
                            has_message_type = any(sig.name == 'MessageType' for sig in target_msg.signals)
                            if has_message_type and 'MessageType' not in encode_data:
                                error_msg = (
                                    f"MessageType is required for message (CAN ID 0x{can_id:X}) but was not set. "
                                    f"Signals being encoded: {list(encode_data.keys())}"
                                )
                                logger.error(error_msg)
                                raise ValueError(error_msg)
                        
                        # Final safety check before encoding - validate encode_data types
                        try:
                            # Validate encode_data contains valid types
                            for key, value in list(encode_data.items()):
                                if value is None:
                                    logger.warning(f"encode_data contains None value for '{key}', removing it")
                                    encode_data[key] = 0  # Default to 0 for None values
                                elif not isinstance(value, (int, float, str, bool)):
                                    logger.warning(f"encode_data contains invalid type for '{key}': {type(value)}, converting to int")
                                    try:
                                        encode_data[key] = int(value)
                                    except (ValueError, TypeError):
                                        encode_data[key] = 0
                        except Exception as e:
                            logger.error(f"Error validating encode_data: {e}", exc_info=True)
                        
                        try:
                            if self.dbc_service is not None:
                                data_bytes = self.dbc_service.encode_message(target_msg, encode_data)
                            else:
                                data_bytes = target_msg.encode(encode_data)
                            
                            # Optimization: Cache encoded frame for DAC commands
                            if dac_cmd_sig and dac_cmd_sig in signals:
                                dac_voltage_key = int(signals[dac_cmd_sig])
                                cache_key = (dac_voltage_key, current_mux_enable, current_mux_channel)
                                dac_frame_cache[cache_key] = data_bytes
                                last_cached_dac_voltage = dac_voltage_key
                                # Limit cache size to prevent memory growth (keep last 10 entries)
                                if len(dac_frame_cache) > 10:
                                    # Remove oldest entry (simple FIFO - remove first key)
                                    oldest_key = next(iter(dac_frame_cache))
                                    del dac_frame_cache[oldest_key]
                        except Exception as encode_error:
                            # Log the encode_data for debugging memory corruption issues
                            logger.error(
                                f"Encoding failed for CAN ID 0x{can_id:X}. "
                                f"encode_data: {encode_data}, "
                                f"signals: {signals}, "
                                f"error: {encode_error}",
                                exc_info=True
                            )
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
                    # Use proper monitoring system instead of legacy callback
                    if dac_cmd_sig and dac_cmd_sig in signals:
                        try:
                            dac_value_mv = signals[dac_cmd_sig]
                            # Convert to Volts for display (monitoring system handles formatting)
                            dac_value_v = float(dac_value_mv) / 1000.0
                            self.update_monitor_signal('current_signal', dac_value_v)
                        except Exception as e:
                            logger.debug(f"Failed to update monitor signal: {e}")

                    # Phase 1: Use CanService if available
                    if self.can_service is not None and self.can_service.is_connected():
                        if AdapterFrame is None:
                            logger.error("AdapterFrame class not available")
                            return False, "AdapterFrame class not available"
                        f = AdapterFrame(can_id=can_id, data=data_bytes, timestamp=time.time())
                        logger.debug(f'Signals: {signals}')
                        logger.debug(f'Encode data: {encode_data}')
                        logger.debug(f"Sending frame via service: can_id=0x{can_id:X} data={data_bytes.hex()}")
                        try:
                            success = self.can_service.send_frame(f) if self.can_service is not None else False
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
                
                # Track current MUX state for encoding (needed for multiplexed messages)
                # Initialize with default values
                current_mux_enable = 0
                current_mux_channel = mux_channel_value if mux_channel_value is not None else 0
                
                # Optimization: Cache for encoded DAC frames to avoid re-encoding same voltage
                # Key: (dac_voltage, mux_enable, mux_channel), Value: encoded_data_bytes
                dac_frame_cache = {}
                last_cached_dac_voltage = None
                
                # Track total data points collected across all voltage steps
                total_data_points_collected = 0
                
                # Clear plot before starting new analog test
                if self.plot_clear_callback:
                    try:
                        self.plot_clear_callback()
                    except Exception as e:
                        logger.debug(f"Failed to clear plot: {e}")
                
                # Initialize plot for Analog Sweep Test (thread-safe)
                test_type = test.get('type', '')
                if test_type == 'Analog Sweep Test':
                    test_name = test.get('name', '')
                    if self.gui is not None and hasattr(self.gui, '_initialize_analog_sweep_plot'):
                        try:
                            current_thread = QtCore.QThread.currentThread()
                            main_thread = QtCore.QCoreApplication.instance().thread()
                            
                            if current_thread == main_thread:
                                # Main thread - call directly
                                self.gui._initialize_analog_sweep_plot(test_name)
                            else:
                                # Background thread - use QueuedConnection
                                QtCore.QMetaObject.invokeMethod(
                                    self.gui,
                                    '_initialize_analog_sweep_plot',
                                    QtCore.Qt.ConnectionType.QueuedConnection,
                                    QtCore.Q_ARG(str, test_name)
                                )
                        except Exception as e:
                            logger.debug(f"Failed to initialize Analog Sweep Test plot: {e}")
                
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
                            current_mux_enable = 0  # Update state only after successful send
                            _nb_sleep(SLEEP_INTERVAL_SHORT)
                        except Exception as e:
                            logger.warning(f"Failed to disable MUX: {e}", exc_info=True)
                            # Continue anyway - MUX may already be disabled
                            # State may be inconsistent, but we'll try to set it correctly later
                    # 2) Set MUX channel
                    if mux_channel_sig and mux_channel_value is not None:
                        try:
                            mux_channel_int = int(mux_channel_value)
                            # Validate MUX channel value is non-negative
                            if mux_channel_int < 0:
                                logger.warning(f"Invalid MUX channel value: {mux_channel_int}, must be >= 0. Skipping MUX channel set.")
                            else:
                                current_mux_channel = mux_channel_int
                                _encode_and_send({mux_channel_sig: current_mux_channel})
                                _nb_sleep(SLEEP_INTERVAL_SHORT)
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid MUX channel value '{mux_channel_value}': {e}. Skipping MUX channel set.")
                            # Continue - may be optional depending on hardware
                        except Exception as e:
                            logger.warning(f"Failed to set MUX channel: {e}", exc_info=True)
                            # Continue - may be optional depending on hardware
                    # 3) Set DAC to min (CRITICAL - must succeed)
                    # Include MUX signals if message requires them (for multiplexed messages)
                    try:
                        dac_signals = {dac_cmd_sig: int(dac_min)}
                        # Note: MUX signals should NOT be included - they require MessageType=17, DAC requires MessageType=18
                        _encode_and_send(dac_signals)
                        _nb_sleep(SLEEP_INTERVAL_SHORT)
                    except Exception as e:
                        logger.error(f"Failed to set DAC to minimum: {e}", exc_info=True)
                        raise ValueError(f"Failed to send DAC command: {e}") from e
                    # 4) Enable MUX (send channel + enable together if channel known)
                    if mux_enable_sig:
                        try:
                            if mux_channel_sig and mux_channel_value is not None:
                                try:
                                    mux_channel_int = int(mux_channel_value)
                                    if mux_channel_int >= 0:
                                        _encode_and_send({mux_enable_sig: 1, mux_channel_sig: mux_channel_int})
                                        current_mux_enable = 1  # Update state only after successful send
                                        current_mux_channel = mux_channel_int
                                    else:
                                        logger.warning(f"Invalid MUX channel value: {mux_channel_int}, using enable only")
                                        _encode_and_send({mux_enable_sig: 1})
                                        current_mux_enable = 1
                                except (ValueError, TypeError):
                                    logger.warning(f"Invalid MUX channel value, using enable only")
                                    _encode_and_send({mux_enable_sig: 1})
                                    current_mux_enable = 1
                            else:
                                _encode_and_send({mux_enable_sig: 1})
                                current_mux_enable = 1  # Update state only after successful send
                        except Exception as e:
                            logger.warning(f"Failed to enable MUX: {e}", exc_info=True)
                            # Continue - test may work without explicit MUX enable
                            # State may be inconsistent, but test can continue
                    # 5) Hold initial dwell and collect multiple feedback data points
                    # Continuously send DAC command (50ms period) and collect data during dwell
                    if dac_cmd_sig:
                        points_collected = _collect_data_points_during_dwell(dac_min, dwell_ms, dac_cmd_sig, fb_signal, fb_msg_id)
                        total_data_points_collected += points_collected if points_collected else 0
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
                            points_collected = _collect_data_points_during_dwell(cur, dwell_ms, dac_cmd_sig, fb_signal, fb_msg_id)
                            total_data_points_collected += points_collected if points_collected else 0
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
                    # Validate that we collected feedback data (if feedback signal is configured)
                    if fb_signal and fb_msg_id:
                        if total_data_points_collected == 0:
                            logger.warning(
                                f"Analog Sweep Test: No feedback data points collected during entire test. "
                                f"This may indicate a problem with feedback signal reception or configuration."
                            )
                            success = False
                            info = f"Analog actuation failed: No feedback data collected (held {dac_min}-{dac_max} step {dac_step} mV)"
                        else:
                            success = True
                            info = f"Analog actuation: held {dac_min}-{dac_max} step {dac_step} mV, collected {total_data_points_collected} data points"
                    else:
                        # No feedback signal configured - test passes if commands were sent successfully
                        success = True
                        info = f"Analog actuation: held {dac_min}-{dac_max} step {dac_step} mV (no feedback signal configured)"
                except Exception as e:
                    success = False
                    info = f"Analog actuation failed: {e}"
                finally:
                    # Ensure we leave DAC at 0 and MUX disabled even if an exception occurred
                    try:
                        if dac_cmd_sig:
                            dac_signals = {dac_cmd_sig: 0}
                            # Note: MUX signals should NOT be included - they require MessageType=17, DAC requires MessageType=18
                            _encode_and_send(dac_signals)
                            _nb_sleep(SLEEP_INTERVAL_SHORT)
                    except Exception as e:
                        logger.debug(f"Failed to clear signal cache: {e}")
                    try:
                        if mux_enable_sig:
                            # send disable; include channel if available to be explicit
                            try:
                                if mux_channel_sig and mux_channel_value is not None:
                                    try:
                                        mux_channel_int = int(mux_channel_value)
                                        if mux_channel_int >= 0:
                                            _encode_and_send({mux_enable_sig: 0, mux_channel_sig: mux_channel_int})
                                            current_mux_enable = 0  # Update state only after successful send
                                            current_mux_channel = mux_channel_int
                                        else:
                                            _encode_and_send({mux_enable_sig: 0})
                                            current_mux_enable = 0
                                    except (ValueError, TypeError):
                                        _encode_and_send({mux_enable_sig: 0})
                                        current_mux_enable = 0
                                else:
                                    _encode_and_send({mux_enable_sig: 0})
                                    current_mux_enable = 0  # Update state only after successful send
                                _nb_sleep(SLEEP_INTERVAL_SHORT)
                            except Exception as e:
                                logger.warning(f"Failed to disable MUX in cleanup: {e}. Hardware may be left in enabled state.")
                                # Try to log this as a warning since cleanup failures are important
                    except Exception as e:
                        logger.warning(f"Failed to disable multiplexor signal in cleanup: {e}")
                # Capture and store plot data immediately for analog tests before returning
                # This prevents plot data from being lost when the next test clears the plot arrays
                if test.get('type') == 'Analog Sweep Test':
                    test_name = test.get('name', '<unnamed>')
                    try:
                        if self.gui is not None and hasattr(self.gui, 'plot_dac_voltages') and hasattr(self.gui, 'plot_feedback_values'):
                            if self.gui.plot_dac_voltages and self.gui.plot_feedback_values:
                                dac_voltages = list(self.gui.plot_dac_voltages)
                                feedback_values = list(self.gui.plot_feedback_values)
                                
                                # Calculate linear regression: feedback = slope * dac + intercept
                                # X-axis: DAC voltage, Y-axis: Feedback value
                                slope = None
                                intercept = None
                                if len(dac_voltages) >= 2 and len(feedback_values) >= 2:
                                    try:
                                        # Filter out invalid data points
                                        valid_dac = []
                                        valid_feedback = []
                                        min_len = min(len(dac_voltages), len(feedback_values))
                                        for i in range(min_len):
                                            dac_val = dac_voltages[i]
                                            fb_val = feedback_values[i]
                                            if (isinstance(dac_val, (int, float)) and isinstance(fb_val, (int, float)) and
                                                not (isinstance(dac_val, float) and dac_val != dac_val) and
                                                not (isinstance(fb_val, float) and fb_val != fb_val)):
                                                valid_dac.append(float(dac_val))
                                                valid_feedback.append(float(fb_val))
                                        
                                        if len(valid_dac) < 2:
                                            logger.warning(
                                                f"Analog Sweep Test: Insufficient valid data points for linear regression. "
                                                f"Need at least 2 valid points, got {len(valid_dac)}. Regression line will not be displayed."
                                            )
                                            slope = None
                                            intercept = None
                                        else:
                                            n = len(valid_dac)
                                            sum_x = sum(valid_dac)
                                            sum_y = sum(valid_feedback)
                                            sum_xy = sum(x * y for x, y in zip(valid_dac, valid_feedback))
                                            sum_x2 = sum(x * x for x in valid_dac)
                                            
                                            # Check for variance in DAC values (required for valid regression)
                                            dac_mean = sum_x / n
                                            dac_variance = sum((x - dac_mean) ** 2 for x in valid_dac) / n
                                            
                                            if dac_variance < 1e-10:
                                                logger.warning(
                                                    f"Analog Sweep Test: DAC values have no variance (all values are approximately {dac_mean:.2f}mV). "
                                                    f"Cannot calculate valid linear regression. Regression line will not be displayed."
                                                )
                                                slope = None
                                                intercept = None
                                            else:
                                                denominator = n * sum_x2 - sum_x * sum_x
                                                if abs(denominator) >= 1e-10:
                                                    slope = (n * sum_xy - sum_x * sum_y) / denominator
                                                    intercept = (sum_y - slope * sum_x) / n
                                                    
                                                    # Validate regression results (check for NaN or Inf)
                                                    if (isinstance(slope, float) and (slope != slope or abs(slope) == float('inf')) or
                                                        isinstance(intercept, float) and (intercept != intercept or abs(intercept) == float('inf'))):
                                                        logger.warning(
                                                            f"Analog Sweep Test: Invalid regression results (slope={slope}, intercept={intercept}). "
                                                            f"Regression line will not be displayed."
                                                        )
                                                        slope = None
                                                        intercept = None
                                                    else:
                                                        logger.info(f"Analog Sweep Test Linear Regression: Slope={slope:.6f}, Intercept={intercept:.6f}")
                                                        
                                                        # Add regression line to plot
                                                        if self.gui is not None and hasattr(self.gui, '_add_regression_line_to_plot'):
                                                            try:
                                                                self.gui._add_regression_line_to_plot(slope, intercept)
                                                            except Exception as e:
                                                                logger.debug(f"Failed to add regression line to plot: {e}")
                                                else:
                                                    logger.warning(
                                                        f"Analog Sweep Test: Regression denominator too small ({denominator:.2e}). "
                                                        f"Cannot calculate valid linear regression."
                                                    )
                                                    slope = None
                                                    intercept = None
                                    except Exception as e:
                                        logger.debug(f"Failed to calculate linear regression for Analog Sweep Test: {e}", exc_info=True)
                                
                                plot_data = {
                                    'dac_voltages': dac_voltages,
                                    'feedback_values': feedback_values,
                                    'slope': slope,
                                    'intercept': intercept
                                }
                                # Store plot data immediately in execution data (will be merged with other data later)
                                # Use a temporary key structure that _on_test_finished can access (thread-safe)
                                if self.gui is not None:
                                    try:
                                        # Safely access QtCore - may not be available in all contexts
                                        try:
                                            current_thread = QtCore.QThread.currentThread()
                                            main_thread = QtCore.QCoreApplication.instance().thread()
                                            
                                            if current_thread != main_thread:
                                                logger.debug(f"Storing plot data from background thread for '{test_name}'")
                                        except (AttributeError, NameError, RuntimeError):
                                            # QtCore not available or not initialized - skip thread check
                                            current_thread = None
                                            main_thread = None
                                            logger.debug(f"QtCore not available for thread check, storing plot data anyway")
                                        
                                        # Dictionary assignment is thread-safe in Python (GIL protects dict operations)
                                        if not hasattr(self.gui, '_test_plot_data_temp'):
                                            self.gui._test_plot_data_temp = {}
                                        self.gui._test_plot_data_temp[test_name] = plot_data
                                        logger.debug(f"Captured and stored plot data for {test_name}: {len(plot_data['dac_voltages'])} points")
                                    except Exception as e:
                                        logger.warning(f"Failed to store plot data for '{test_name}': {e}")
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
                
                if pre_dwell_ms > 60000:  # 60 seconds max
                    logger.warning(f"Pre-dwell time ({pre_dwell_ms}ms) is very large, may indicate configuration error")
                
                if dwell_ms <= 0:
                    return False, "Dwell time must be positive"
                
                if dwell_ms < 100:
                    logger.warning(f"Dwell time ({dwell_ms}ms) is very short, may not collect sufficient data")
                
                def _nb_sleep(sec: float) -> None:
                    """Non-blocking sleep that processes Qt events.
                    
                    Args:
                        sec: Sleep duration in seconds
                    """
                    end = time.time() + float(sec)
                    while time.time() < end:
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
                    
                    time.sleep(SLEEP_INTERVAL_SHORT)
                
                # Step 3: Calculate averages and validate data quality
                if not feedback_values or not eol_values:
                    return False, f"No data collected during dwell time (Feedback samples: {len(feedback_values)}, EOL samples: {len(eol_values)})"
                
                # Validate minimum sample count
                min_samples = max(5, int(dwell_ms / 200))  # At least 5 samples or 1 per 200ms
                if len(feedback_values) < min_samples:
                    logger.warning(f"Feedback signal collected only {len(feedback_values)} samples, expected at least {min_samples}")
                if len(eol_values) < min_samples:
                    logger.warning(f"EOL signal collected only {len(eol_values)} samples, expected at least {min_samples}")
                
                # Check for data quality issues (all zeros, all same value, etc.)
                feedback_unique = len(set(feedback_values))
                eol_unique = len(set(eol_values))
                
                if feedback_unique == 1:
                    logger.warning(f"Feedback signal has no variation (all values = {feedback_values[0]})")
                if eol_unique == 1:
                    logger.warning(f"EOL signal has no variation (all values = {eol_values[0]})")
                
                # Check for outliers (values more than 3 standard deviations from mean)
                if len(feedback_values) > 2:
                    import statistics
                    try:
                        fb_mean = statistics.mean(feedback_values)
                        fb_std = statistics.stdev(feedback_values) if len(feedback_values) > 1 else 0
                        outliers = [v for v in feedback_values if abs(v - fb_mean) > 3 * fb_std]
                        if outliers:
                            logger.warning(f"Found {len(outliers)} outlier(s) in feedback signal: {outliers[:5]}")
                    except Exception:
                        pass
                
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
                
                # Store in temporary storage for retrieval by _on_test_finished (thread-safe)
                # Note: Dictionary assignment is atomic in Python due to GIL, but we check thread for safety
                if self.gui is not None:
                    try:
                        current_thread = QtCore.QThread.currentThread()
                        main_thread = QtCore.QCoreApplication.instance().thread()
                        
                        if current_thread != main_thread:
                            logger.debug(f"Storing test result data from background thread for '{test_name}'")
                        
                        # Dictionary assignment is thread-safe in Python (GIL protects dict operations)
                        # But we ensure the attribute exists first
                        if not hasattr(self.gui, '_test_result_data_temp'):
                            # This assignment is safe even from background thread
                            self.gui._test_result_data_temp = {}
                        self.gui._test_result_data_temp[test_name] = result_data
                    except Exception as e:
                        logger.warning(f"Failed to store test result data for '{test_name}': {e}")
                
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
                
                # Validate reference temperature range (reasonable range: -40°C to 150°C)
                if not (-40.0 <= reference_temp_c <= 150.0):
                    logger.warning(f"Reference temperature ({reference_temp_c}°C) is outside typical range (-40°C to 150°C)")
                
                if dwell_ms <= 0:
                    return False, "Dwell time must be positive"
                
                if dwell_ms < 100:
                    logger.warning(f"Dwell time ({dwell_ms}ms) is very short, may not collect sufficient data")
                
                def _nb_sleep(sec: float) -> None:
                    """Non-blocking sleep that processes Qt events.
                    
                    Args:
                        sec: Sleep duration in seconds
                    """
                    end = time.time() + float(sec)
                    while time.time() < end:
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
                                
                                # Update real-time display with latest value (thread-safe)
                                self.update_monitor_signal('dut_temperature', temp_float)
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading temperature signal: {e}")
                    
                    time.sleep(SLEEP_INTERVAL_SHORT)
                
                # Step 2: Check if any data was collected
                if not temperature_values:
                    return False, f"No temperature data received during dwell time ({dwell_ms}ms). Check CAN connection and signal configuration."
                
                # Validate minimum sample count
                min_samples = max(5, int(dwell_ms / 200))  # At least 5 samples or 1 per 200ms
                if len(temperature_values) < min_samples:
                    logger.warning(f"Temperature signal collected only {len(temperature_values)} samples, expected at least {min_samples}")
                
                # Check for data quality issues
                temp_unique = len(set(temperature_values))
                if temp_unique == 1:
                    logger.warning(f"Temperature signal has no variation (all values = {temperature_values[0]}°C)")
                
                # Validate temperature values are in reasonable range
                invalid_temps = [t for t in temperature_values if not (-40.0 <= t <= 200.0)]
                if invalid_temps:
                    logger.warning(f"Found {len(invalid_temps)} temperature value(s) outside reasonable range (-40°C to 200°C): {invalid_temps[:5]}")
                
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
                
                # Store in temporary storage for retrieval by _on_test_finished (thread-safe)
                if self.gui is not None:
                    try:
                        current_thread = QtCore.QThread.currentThread()
                        main_thread = QtCore.QCoreApplication.instance().thread()
                        
                        if current_thread != main_thread:
                            logger.debug(f"Storing test result data from background thread for '{test_name}'")
                        
                        if not hasattr(self.gui, '_test_result_data_temp'):
                            self.gui._test_result_data_temp = {}
                        self.gui._test_result_data_temp[test_name] = result_data
                    except Exception as e:
                        logger.warning(f"Failed to store test result data for '{test_name}': {e}")
                
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
                
                # Validate reference PWM frequency range (0-100kHz)
                if not (0.0 <= reference_pwm_frequency <= 100000.0):
                    logger.warning(f"Reference PWM frequency ({reference_pwm_frequency} Hz) is outside typical range (0-100kHz)")
                
                # Validate reference duty cycle range (0-100%)
                if not (0.0 <= reference_duty <= 100.0):
                    return False, f"Reference duty cycle must be in range 0-100%, got {reference_duty}"
                
                if acquisition_ms <= 0:
                    return False, "Acquisition time must be positive"
                
                if acquisition_ms < 100:
                    logger.warning(f"Acquisition time ({acquisition_ms}ms) is very short, may not collect sufficient data")
                
                def _nb_sleep(sec: float) -> None:
                    """Non-blocking sleep that processes Qt events.
                    
                    Args:
                        sec: Sleep duration in seconds
                    """
                    end = time.time() + float(sec)
                    while time.time() < end:
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
                                
                                # Validate duty cycle range
                                if not (0.0 <= duty_float <= 100.0):
                                    logger.warning(f"Duty cycle value {duty_float}% is outside expected range (0-100%)")
                                
                                # Update real-time display with both values (thread-safe via monitor signal)
                                # Note: PWM test doesn't have a dedicated monitor signal, so we skip real-time updates
                                # The final results will be displayed after test completion
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading duty signal: {e}")
                    
                    time.sleep(SLEEP_INTERVAL_SHORT)
                
                # Step 2: Check if data was collected for both signals
                if not pwm_frequency_values:
                    return False, f"No PWM frequency data received during acquisition time ({acquisition_ms}ms). Check CAN connection and signal configuration."
                
                if not duty_values:
                    return False, f"No duty cycle data received during acquisition time ({acquisition_ms}ms). Check CAN connection and signal configuration."
                
                # Validate minimum sample count
                min_samples = max(5, int(acquisition_ms / 200))  # At least 5 samples or 1 per 200ms
                if len(pwm_frequency_values) < min_samples:
                    logger.warning(f"PWM frequency signal collected only {len(pwm_frequency_values)} samples, expected at least {min_samples}")
                if len(duty_values) < min_samples:
                    logger.warning(f"Duty cycle signal collected only {len(duty_values)} samples, expected at least {min_samples}")
                
                # Validate that both signals are from same message (check message IDs match)
                # Note: Both signals use feedback_msg_id, so they should be from same message
                # This is implicit in the current implementation
                
                # Step 3: Calculate averages
                pwm_frequency_avg = sum(pwm_frequency_values) / len(pwm_frequency_values)
                duty_avg = sum(duty_values) / len(duty_values)
                
                # Validate calculated averages are in reasonable range
                if not (0.0 <= pwm_frequency_avg <= 100000.0):
                    logger.warning(f"Calculated PWM frequency average ({pwm_frequency_avg} Hz) is outside typical range (0-100kHz)")
                if not (0.0 <= duty_avg <= 100.0):
                    logger.warning(f"Calculated duty cycle average ({duty_avg}%) is outside expected range (0-100%)")
                
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
                        remaining = end - time.time()
                        if remaining <= 0:
                            break
                        time.sleep(min(SLEEP_INTERVAL_SHORT, remaining))
                
                def _send_trigger(value: int) -> bool:
                    """Send trigger signal with specified value (0=disable, 1=enable)."""
                    try:
                        dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded())
                        frame_data = None
                        
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
                                
                                try:
                                    frame_data = self.dbc_service.encode_message(msg, signal_values)
                                    if not frame_data:
                                        logger.error(f"Failed to encode trigger signal {trigger_signal}={value} for CAN ID 0x{trigger_msg_id:X}")
                                        return False
                                except Exception as e:
                                    logger.error(f"Exception encoding trigger signal {trigger_signal}={value}: {e}", exc_info=True)
                                    return False
                            else:
                                logger.warning(f"Could not find message for CAN ID 0x{trigger_msg_id:X}")
                                return False
                        else:
                            # Fallback: raw encoding
                            frame_data = bytes([value & 0xFF])
                        
                        if frame_data is None:
                            logger.error(f"Failed to generate frame data for trigger signal {trigger_signal}={value}")
                            return False
                        
                        if AdapterFrame is not None:
                            frame = AdapterFrame(can_id=trigger_msg_id, data=frame_data)
                        else:
                            class F: pass
                            frame = F()
                            frame.can_id = trigger_msg_id
                            frame.data = frame_data
                            frame.timestamp = time.time()
                        
                        if self.can_service is not None and self.can_service.is_connected():
                            success = self.can_service.send_frame(frame)
                            if not success:
                                logger.warning(f"send_frame returned False for trigger signal {trigger_signal}={value}")
                                return False
                            logger.info(f"External 5V Test: Sent trigger signal {trigger_signal}={value}")
                            return True
                        else:
                            logger.error(f"CAN service not connected, cannot send trigger signal {trigger_signal}={value}")
                            return False
                    except Exception as e:
                        logger.error(f"Failed to send trigger: {e}", exc_info=True)
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
                        
                        # Update labels for real-time monitoring using proper monitoring system
                        fb_display = feedback_values[-1] if feedback_values else None
                        eol_display = eol_values[-1] if eol_values else None
                        if fb_display is not None:
                            try:
                                self.update_monitor_signal('dut_feedback_signal', fb_display)
                            except Exception as e:
                                logger.debug(f"Failed to update feedback signal: {e}")
                        if eol_display is not None:
                            try:
                                self.update_monitor_signal('eol_measured_signal', eol_display)
                            except Exception as e:
                                logger.debug(f"Failed to update EOL signal: {e}")
                        
                        time.sleep(SLEEP_INTERVAL_SHORT)
                    
                    return eol_values, feedback_values
                
                # Phase 1: Disabled state
                logger.info("External 5V Test: Phase 1 - Disabling External 5V...")
                try:
                    if not _send_trigger(0):
                        return False, "Failed to send disable trigger"
                    
                    logger.info(f"External 5V Test: Waiting {pre_dwell_ms}ms for system stabilization (disabled)...")
                    _nb_sleep(pre_dwell_ms / 1000.0)
                    
                    eol_values_disabled, feedback_values_disabled = _collect_data_phase("Disabled", clear_plot=False)
                    
                    # Validate Phase 1 data was collected
                    if not eol_values_disabled or not feedback_values_disabled:
                        logger.warning("External 5V Test: Phase 1 data collection incomplete, but continuing to Phase 2")
                    
                    # Phase 2: Enabled state
                    logger.info("External 5V Test: Phase 2 - Enabling External 5V...")
                    if not _send_trigger(1):
                        return False, "Failed to send enable trigger"
                    
                    logger.info(f"External 5V Test: Waiting {pre_dwell_ms}ms for system stabilization (enabled)...")
                    _nb_sleep(pre_dwell_ms / 1000.0)
                    
                    eol_values_enabled, feedback_values_enabled = _collect_data_phase("Enabled", clear_plot=True)
                finally:
                    # Always disable External 5V in cleanup, even if test fails
                    logger.info("External 5V Test: Cleanup - Disabling External 5V...")
                    try:
                        _send_trigger(0)
                    except Exception as e:
                        logger.warning(f"Failed to disable External 5V during cleanup: {e}")
                
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
                    """Non-blocking sleep (no Qt processEvents; safe for worker thread).

                    Args:
                        sec: Sleep duration in seconds
                    """
                    end = time.time() + float(sec)
                    while time.time() < end:
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
                        # Determine MessageType first based on signals being sent
                        determined_mux_value = None
                        for sig_name in signals:
                            for sig in target_msg.signals:
                                if sig.name == sig_name and getattr(sig, 'multiplexer_ids', None):
                                    determined_mux_value = sig.multiplexer_ids[0]
                                    break
                            if determined_mux_value is not None:
                                break
                        
                        # Set MessageType if determined
                        if determined_mux_value is not None:
                            encode_data['MessageType'] = determined_mux_value
                        
                        # Add signals from the signals dict, but filter out signals that aren't valid for the current MessageType
                        for sig_name in signals:
                            should_include = True
                            
                            # Check if this signal is multiplexed
                            for sig in target_msg.signals:
                                if sig.name == sig_name:
                                    multiplexer_ids = getattr(sig, 'multiplexer_ids', None)
                                    if multiplexer_ids:
                                        # Signal is multiplexed - only include if MessageType matches
                                        if determined_mux_value is not None:
                                            if isinstance(multiplexer_ids, (list, tuple)):
                                                should_include = (determined_mux_value in multiplexer_ids)
                                            else:
                                                should_include = (determined_mux_value == multiplexer_ids)
                                        else:
                                            should_include = True
                                    break
                            
                            if should_include:
                                encode_data[sig_name] = signals[sig_name]
                        
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
                
                # Helper function to send fan trigger
                def _send_fan_trigger(value: int) -> bool:
                    """Send fan trigger signal with specified value (0=disable, 1=enable)."""
                    try:
                        signals = {trigger_signal: value}
                        data_bytes = _encode_and_send_fan(signals, trigger_msg_id)
                        
                        if not data_bytes:
                            logger.error(f"Failed to encode fan trigger message (value={value})")
                            return False
                        
                        # Use CanService.send_frame() with Frame object
                        if self.can_service is not None and self.can_service.is_connected():
                            f = AdapterFrame(can_id=trigger_msg_id, data=data_bytes, timestamp=time.time())
                            logger.debug(f"Sending fan trigger frame: can_id=0x{trigger_msg_id:X} data={data_bytes.hex()}")
                            try:
                                success = self.can_service.send_frame(f)
                                if not success:
                                    logger.warning(f"send_frame returned False for can_id=0x{trigger_msg_id:X}")
                                    return False
                                else:
                                    logger.info(f"Sent fan trigger signal ({value}) on message 0x{trigger_msg_id:X}, signal: {trigger_signal}")
                                    return True
                            except Exception as e:
                                logger.error(f"Failed to send frame via service: {e}", exc_info=True)
                                return False
                        elif self.gui is not None:
                            # Fallback: use GUI's CAN service
                            if hasattr(self.gui, 'can_service') and self.gui.can_service and self.gui.can_service.is_connected():
                                f = AdapterFrame(can_id=trigger_msg_id, data=data_bytes, timestamp=time.time())
                                logger.debug(f"Sending fan trigger frame: can_id=0x{trigger_msg_id:X} data={data_bytes.hex()}")
                                try:
                                    success = self.gui.can_service.send_frame(f)
                                    if not success:
                                        logger.warning(f"send_frame returned False for can_id=0x{trigger_msg_id:X}")
                                        return False
                                    else:
                                        logger.info(f"Sent fan trigger signal ({value}) on message 0x{trigger_msg_id:X}, signal: {trigger_signal}")
                                        return True
                                except Exception as e:
                                    logger.error(f"Failed to send frame via GUI service: {e}", exc_info=True)
                                    return False
                            else:
                                logger.error("CAN service not available. Cannot send fan trigger signal.")
                                return False
                        else:
                            logger.error("CAN service not available. Cannot send fan trigger signal.")
                            return False
                    except Exception as e:
                        logger.error(f"Failed to send fan trigger signal: {e}", exc_info=True)
                        return False
                
                # Step 1: Send Fan Test Trigger Signal = 1 to enable fan
                logger.info(f"Fan Control Test: Sending trigger signal to enable fan...")
                try:
                    if not _send_fan_trigger(1):
                        return False, "Failed to send fan enable trigger"
                except Exception as e:
                    logger.error(f"Failed to send fan trigger signal: {e}", exc_info=True)
                    return False, f"Failed to send fan trigger signal: {e}"
                
                # Step 2: Wait up to Test Timeout for Fan Enabled Signal to become 1
                logger.info(f"Fan Control Test: Waiting for fan enabled signal (timeout: {timeout_ms}ms)...")
                fan_enabled_verified = False
                timeout_start = time.time()
                timeout_end = timeout_start + (timeout_ms / 1000.0)
                last_enabled_value = None
                enabled_stable_count = 0
                
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
                                # Check if value is stable (same value for multiple readings)
                                if enabled_int == last_enabled_value:
                                    enabled_stable_count += 1
                                else:
                                    enabled_stable_count = 0
                                    last_enabled_value = enabled_int
                                
                                if enabled_int == 1 and enabled_stable_count >= 2:
                                    fan_enabled_verified = True
                                    logger.info("Fan enabled signal verified (value = 1, stable)")
                                    break
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading fan enabled signal: {e}")
                    
                    time.sleep(SLEEP_INTERVAL_SHORT)
                
                # Step 3: Check if fan enabled was verified
                if not fan_enabled_verified:
                    # Cleanup: disable fan before returning
                    try:
                        _send_fan_trigger(0)
                    except Exception:
                        pass
                    return False, f"Fan enabled signal did not reach 1 within timeout ({timeout_ms}ms). Check fan control configuration."
                
                # Step 4: After verification, start dwell time and collect data
                logger.info(f"Fan Control Test: Collecting fan tach and fault signals for {dwell_ms}ms...")
                fan_tach_values = []
                fan_fault_values = []
                start_time = time.time()
                end_time = start_time + (dwell_ms / 1000.0)
                
                try:
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
                                    
                                    # Validate fan tach signal range (expected 0 or 1)
                                    if not (0.0 <= tach_float <= 1.0):
                                        logger.warning(f"Fan tach signal value {tach_float} is outside expected range (0-1)")
                                    
                                    # Update real-time display with latest value (thread-safe)
                                    self.update_monitor_signal('fan_tach_signal', tach_float)
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
                        
                        time.sleep(SLEEP_INTERVAL_SHORT)
                finally:
                    # Step 5: Always disable fan in cleanup, even if test fails
                    logger.info("Fan Control Test: Cleanup - Disabling fan...")
                    try:
                        _send_fan_trigger(0)
                    except Exception as e:
                        logger.warning(f"Failed to disable fan during cleanup: {e}")
                
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
                
                # Store in temporary storage for retrieval by _on_test_finished (thread-safe)
                if self.gui is not None:
                    try:
                        from PySide6 import QtCore as _Qt
                        current_thread = _Qt.QThread.currentThread()
                        main_thread = _Qt.QCoreApplication.instance().thread()
                        
                        if current_thread != main_thread:
                            logger.debug(f"Storing test result data from background thread for '{test_name}'")
                        
                        if not hasattr(self.gui, '_test_result_data_temp'):
                            self.gui._test_result_data_temp = {}
                        self.gui._test_result_data_temp[test_name] = result_data
                    except Exception as e:
                        logger.warning(f"Failed to store test result data for '{test_name}': {e}")
                
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
                    
                    # Verify channel is actually measuring (check if we can query it)
                    # This helps catch cases where channel is enabled but probe is disconnected
                    try:
                        # Try to query channel scale as a verification that channel is active
                        scale_response = self.oscilloscope_service.send_command(f"C{channel_num}:VDIV?")
                        if scale_response is None:
                            logger.warning(f"DC Bus Sensing: Could not query channel {channel_num} scale - channel may not be properly configured")
                        else:
                            logger.debug(f"DC Bus Sensing: Channel {channel_num} scale: {scale_response}")
                    except Exception as e:
                        logger.debug(f"DC Bus Sensing: Could not verify channel {channel_num} configuration: {e}")
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
                                fb_float = float(fb_val)
                                # Unit conversion: Check if signal is likely in mV (values > 1000) and convert to V
                                # Note: This is a heuristic - ideally signal units should be configured explicitly
                                # Typical DC bus voltages are 12V-800V, so values > 1000 are likely in mV
                                if abs(fb_float) > 1000:
                                    logger.debug(f"DC Bus Sensing: Converting CAN signal from {fb_float} mV to {fb_float/1000.0:.4f} V")
                                    fb_float = fb_float / 1000.0
                                # Validate value is in reasonable range for DC bus (0-1000V)
                                if not (0.0 <= abs(fb_float) <= 1000.0):
                                    logger.warning(f"DC Bus Sensing: CAN signal value {fb_float} V is outside typical DC bus range (0-1000V)")
                                can_feedback_values.append(fb_float)
                            except (ValueError, TypeError):
                                pass
                    except Exception as e:
                        logger.debug(f"Error reading CAN feedback signal: {e}")
                    
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
                
                # Validate oscilloscope response is numeric and in reasonable range
                try:
                    osc_avg_float = float(osc_avg)
                    if not (0.0 <= abs(osc_avg_float) <= 1000.0):
                        logger.warning(f"DC Bus Sensing: Oscilloscope average {osc_avg_float} V is outside typical DC bus range (0-1000V)")
                    osc_avg = osc_avg_float
                except (ValueError, TypeError) as e:
                    return False, f"Oscilloscope returned invalid average value: {osc_avg} (expected numeric value)"
                
                # Step 6: Calculate average from CAN feedback signal
                if not can_feedback_values:
                    return False, f"No CAN feedback data collected during dwell time ({dwell_ms}ms). Check CAN connection and signal configuration."
                
                # Validate minimum sample count
                min_samples = max(5, int(dwell_ms / 200))  # At least 5 samples or 1 per 200ms
                if len(can_feedback_values) < min_samples:
                    logger.warning(f"DC Bus Sensing: CAN signal collected only {len(can_feedback_values)} samples, expected at least {min_samples}")
                
                can_avg = sum(can_feedback_values) / len(can_feedback_values)
                
                # Validate calculated average is in reasonable range
                if not (0.0 <= abs(can_avg) <= 1000.0):
                    logger.warning(f"DC Bus Sensing: Calculated CAN average {can_avg} V is outside typical DC bus range (0-1000V)")
                
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
                
                # Store in temporary storage for retrieval by _on_test_finished (thread-safe)
                if self.gui is not None:
                    try:
                        current_thread = QtCore.QThread.currentThread()
                        main_thread = QtCore.QCoreApplication.instance().thread()
                        
                        if current_thread != main_thread:
                            logger.debug(f"Storing test result data from background thread for '{test_name}'")
                        
                        if not hasattr(self.gui, '_test_result_data_temp'):
                            self.gui._test_result_data_temp = {}
                        self.gui._test_result_data_temp[test_name] = result_data
                    except Exception as e:
                        logger.warning(f"Failed to store test result data for '{test_name}': {e}")
                
                logger.info(f"DC Bus Sensing Test completed: {'PASS' if passed else 'FAIL'}")
                return passed, info
            elif act.get('type') == 'Charged HV Bus Test':
                # Charged HV Bus Test execution:
                # 0) Pre-Test Safety Dialog (BEFORE any test execution)
                # 1) Get Output Current Trim Value (from previous test or fallback)
                # 2) Send Output Current Trim Value
                # 3) Send Output Current Setpoint
                # 4) Start CAN Data Logging
                # 5) Send Test Trigger
                # 6) Monitor Test Execution (until test_time_ms elapsed)
                # 7) Stop Test and Logging
                # 8) Analyze Logged CAN Data - PFC Regulation
                # 9) Analyze Logged CAN Data - PCMC Success
                # 10) Determine Pass/Fail
                
                # Step 0: Pre-Test Safety Dialog - MUST be shown BEFORE any test execution
                # Must be shown in main GUI thread (Qt requirement)
                logger.info("Charged HV Bus Test: Showing pre-test safety dialog BEFORE test execution...")
                dialog_result = None
                
                if self.gui is not None:
                    try:
                        from PySide6 import QtCore
                        from PySide6.QtWidgets import QMessageBox
                        
                        # Check if we're in the main thread
                        current_thread = QtCore.QThread.currentThread()
                        main_thread = QtCore.QCoreApplication.instance().thread()
                        
                        if current_thread == main_thread:
                            # We're in the main thread, show dialog directly
                            self.gui._show_charged_hv_bus_safety_dialog()
                            dialog_result = getattr(self.gui, '_charged_hv_bus_dialog_result', QMessageBox.No)
                        else:
                            # We're in a background thread, use BlockingQueuedConnection
                            # This will block the background thread until the dialog method returns
                            # Initialize result attribute if not present
                            if not hasattr(self.gui, '_charged_hv_bus_dialog_result'):
                                self.gui._charged_hv_bus_dialog_result = None
                            
                            # Clear previous result
                            self.gui._charged_hv_bus_dialog_result = None
                            
                            # Invoke dialog in main thread using BlockingQueuedConnection
                            # This blocks until the method completes
                            success = QtCore.QMetaObject.invokeMethod(
                                self.gui,
                                '_show_charged_hv_bus_safety_dialog',
                                QtCore.Qt.ConnectionType.BlockingQueuedConnection
                            )
                            
                            if success:
                                # After BlockingQueuedConnection returns, the method has completed
                                # Get the result that was stored
                                dialog_result = getattr(self.gui, '_charged_hv_bus_dialog_result', QMessageBox.No)
                                if dialog_result is None:
                                    logger.warning("Dialog result is None, defaulting to No")
                                    dialog_result = QMessageBox.No
                            else:
                                logger.warning("Failed to invoke dialog method, defaulting to No")
                                dialog_result = QMessageBox.No
                        
                        if dialog_result == QMessageBox.No:
                            # Request pause of test sequence - test will NOT execute
                            logger.info("Charged HV Bus Test: User declined safety check, pausing test sequence (test will not execute)")
                            
                            # Request pause safely from main thread using QMetaObject.invokeMethod
                            # This avoids threading issues that can cause segfaults
                            if self.gui is not None:
                                try:
                                    # Check if we're in the main thread
                                    current_thread = QtCore.QThread.currentThread()
                                    main_thread = QtCore.QCoreApplication.instance().thread()
                                    
                                    if current_thread == main_thread:
                                        # We're in the main thread, call directly
                                        if hasattr(self.gui, '_request_test_sequence_pause'):
                                            self.gui._request_test_sequence_pause()
                                    else:
                                        # We're in a background thread, use QueuedConnection (non-blocking)
                                        QtCore.QMetaObject.invokeMethod(
                                            self.gui,
                                            '_request_test_sequence_pause',
                                            QtCore.Qt.ConnectionType.QueuedConnection
                                        )
                                    logger.info("Charged HV Bus Test: Pause requested on test execution thread")
                                except Exception as e:
                                    logger.warning(f"Failed to request pause on test execution thread: {e}")
                            
                            return False, "Test sequence paused: User declined safety check. Please ensure hardware connections are ready and resume the test sequence."
                    except Exception as e:
                        logger.error(f"Failed to show pre-test safety dialog: {e}", exc_info=True)
                        # On error, default to No (don't execute test if we can't show dialog)
                        logger.warning("Dialog error - defaulting to No (test will not execute)")
                        return False, "Test sequence paused: Failed to show safety dialog. Please ensure hardware connections are ready and resume the test sequence."
                
                # If we reach here, user pressed Yes - continue with test execution
                logger.info("Charged HV Bus Test: User confirmed safety check, proceeding with test execution...")
                
                # Extract parameters (only after user confirms)
                cmd_msg_id = act.get('command_signal_source')
                trigger_signal = act.get('test_trigger_signal')
                trigger_value = act.get('test_trigger_signal_value')
                trim_signal = act.get('set_output_current_trim_signal')
                fallback_trim = act.get('fallback_output_current_trim_value', 100.0)
                setpoint_signal = act.get('set_output_current_setpoint_signal')
                output_current = act.get('output_test_current')
                feedback_msg_id = act.get('feedback_signal_source')
                dut_state_signal = act.get('dut_test_state_signal')
                enable_relay_signal = act.get('enable_relay_signal')
                enable_pfc_signal = act.get('enable_pfc_signal')
                pfc_power_good_signal = act.get('pfc_power_good_signal')
                pcmc_signal = act.get('pcmc_signal')
                psfb_fault_signal = act.get('psfb_fault_signal')
                test_time_ms = int(act.get('test_time_ms', 30000))
                
                # Validate parameters
                if not all([cmd_msg_id, trigger_signal, trigger_value is not None, trim_signal, 
                           setpoint_signal, output_current is not None, feedback_msg_id,
                           dut_state_signal, enable_relay_signal, enable_pfc_signal,
                           pfc_power_good_signal, pcmc_signal, psfb_fault_signal]):
                    return False, "Missing required Charged HV Bus Test parameters"
                
                if test_time_ms < 1000:
                    return False, "Test time must be >= 1000 ms"
                
                # Import AdapterFrame at function level
                try:
                    from backend.adapters.interface import Frame as AdapterFrame
                except ImportError:
                    AdapterFrame = None
                
                def _nb_sleep(sec: float) -> None:
                    """Non-blocking sleep that processes Qt events."""
                    end = time.time() + float(sec)
                    while time.time() < end:
                        remaining = end - time.time()
                        if remaining <= 0:
                            break
                        time.sleep(min(SLEEP_INTERVAL_SHORT, remaining))
                
                # Helper function to encode and send CAN message
                def _encode_and_send_charged_hv_bus(signals: dict, msg_id: int) -> bytes:
                    """Encode signals to CAN message bytes."""
                    encode_data = {'DeviceID': 0}
                    determined_mux_value = None
                    data_bytes = b''
                    
                    dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded())
                    if dbc_available:
                        target_msg = self.dbc_service.find_message_by_id(msg_id)
                    else:
                        target_msg = None
                    
                    if target_msg is None:
                        logger.warning(f"Could not find message for CAN ID 0x{msg_id:X}")
                    
                    if target_msg is not None:
                        # Determine MessageType first based on signals being sent
                        for sig_name in signals:
                            for sig in target_msg.signals:
                                if sig.name == sig_name and getattr(sig, 'multiplexer_ids', None):
                                    determined_mux_value = sig.multiplexer_ids[0]
                                    break
                            if determined_mux_value is not None:
                                break
                        
                        # Set MessageType if determined
                        if determined_mux_value is not None:
                            encode_data['MessageType'] = determined_mux_value
                        
                        # Add signals from the signals dict, but filter out signals that aren't valid for the current MessageType
                        for sig_name in signals:
                            should_include = True
                            
                            # Check if this signal is multiplexed
                            for sig in target_msg.signals:
                                if sig.name == sig_name:
                                    multiplexer_ids = getattr(sig, 'multiplexer_ids', None)
                                    if multiplexer_ids:
                                        # Signal is multiplexed - only include if MessageType matches
                                        if determined_mux_value is not None:
                                            if isinstance(multiplexer_ids, (list, tuple)):
                                                should_include = (determined_mux_value in multiplexer_ids)
                                            else:
                                                should_include = (determined_mux_value == multiplexer_ids)
                                        else:
                                            should_include = True
                                    break
                            
                            if should_include:
                                encode_data[sig_name] = signals[sig_name]
                        
                        try:
                            if self.dbc_service is not None:
                                data_bytes = self.dbc_service.encode_message(target_msg, encode_data)
                            else:
                                data_bytes = target_msg.encode(encode_data)
                        except Exception:
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
                
                monitor_signal_map = {}
                if enable_relay_signal:
                    monitor_signal_map[enable_relay_signal] = 'enable_relay'
                if enable_pfc_signal:
                    monitor_signal_map[enable_pfc_signal] = 'enable_pfc'
                if pfc_power_good_signal:
                    monitor_signal_map[pfc_power_good_signal] = 'pfc_power_good'

                # Step 1: Get Output Current Trim Value
                logger.info("Charged HV Bus Test: Step 1 - Getting output current trim value...")
                logger.info(f"Charged HV Bus Test: Fallback trim value from config: {fallback_trim:.2f}%")
                trim_value = fallback_trim
                trim_value_source = "fallback (config default)"
                
                # Try to get adjustment_factor from previous Output Current Calibration test
                if self.gui is not None:
                    # Strategy 1: Search through _tests list directly (most reliable)
                    # This finds tests that have been executed and have statistics stored
                    if hasattr(self.gui, '_tests') and hasattr(self.gui, '_test_execution_data'):
                        logger.info(f"Charged HV Bus Test: Searching through {len(self.gui._tests)} tests for Output Current Calibration test...")
                        
                        # Search in reverse order to get the most recent test first
                        found_calibration_test = False
                        for test in reversed(self.gui._tests):
                            test_name = test.get('name', '')
                            actuation = test.get('actuation', {})
                            test_type = actuation.get('type', '')
                            
                            if test_type == 'Output Current Calibration':
                                # Check if this test has execution data
                                if test_name in self.gui._test_execution_data:
                                    found_calibration_test = True
                                    exec_data = self.gui._test_execution_data[test_name]
                                    logger.info(f"Charged HV Bus Test: Found Output Current Calibration test '{test_name}' with execution data")
                                    
                                    # Check execution status
                                    exec_status = exec_data.get('status', 'Not Run')
                                    logger.info(f"Charged HV Bus Test: Test '{test_name}' execution status: {exec_status}")
                                    
                                    # Check if test passed and has adjustment_factor
                                    stats = exec_data.get('statistics', {})
                                    logger.info(f"Charged HV Bus Test: Statistics keys for '{test_name}': {list(stats.keys()) if stats else 'None'}")
                                    
                                    adjustment_factor = stats.get('adjustment_factor')
                                    test_passed_in_stats = stats.get('passed', False)
                                    
                                    # Check both status field and statistics passed field
                                    test_passed = (exec_status == 'PASS') or test_passed_in_stats
                                    
                                    logger.info(f"Charged HV Bus Test: adjustment_factor={adjustment_factor}, test_passed={test_passed} (status={exec_status}, stats.passed={test_passed_in_stats})")
                                    
                                    if adjustment_factor is not None:
                                        if test_passed:
                                            logger.info(f"Charged HV Bus Test: Extracted adjustment_factor = {adjustment_factor:.6f} from Output Current Calibration test '{test_name}'")
                                            logger.info(f"Charged HV Bus Test: Converting adjustment_factor to trim_value: {adjustment_factor:.6f} * 100.0 = {adjustment_factor * 100.0:.4f}%")
                                            trim_value = adjustment_factor * 100.0
                                            trim_value_source = f"Output Current Calibration test '{test_name}' (adjustment_factor={adjustment_factor:.6f})"
                                            logger.info(f"Charged HV Bus Test: ✓ Successfully extracted and calculated trim_value = {trim_value:.2f}% from passed Output Current Calibration test '{test_name}'")
                                            break
                                        else:
                                            logger.warning(f"Charged HV Bus Test: Found Output Current Calibration test '{test_name}' but it did not pass (status={exec_status}). Using fallback trim value.")
                                    else:
                                        logger.warning(f"Charged HV Bus Test: Found Output Current Calibration test '{test_name}' but adjustment_factor is None. Statistics keys: {list(stats.keys()) if stats else 'None'}")
                                else:
                                    logger.debug(f"Charged HV Bus Test: Found Output Current Calibration test '{test_name}' but no execution data yet.")
                        
                        if not found_calibration_test:
                            logger.warning("Charged HV Bus Test: No Output Current Calibration test found in _tests list with execution data.")
                    
                    # Strategy 2: Fallback - search through _test_execution_data by name (legacy approach)
                    if trim_value == fallback_trim and hasattr(self.gui, '_test_execution_data'):
                        logger.info(f"Charged HV Bus Test: Fallback search through {len(self.gui._test_execution_data)} tests in execution history...")
                        
                        for test_name, exec_data in reversed(list(self.gui._test_execution_data.items())):
                            # Look up test config from self._tests by name
                            test_config = None
                            if hasattr(self.gui, '_tests'):
                                for test in self.gui._tests:
                                    if test.get('name', '') == test_name:
                                        test_config = test
                                        break
                            
                            if test_config is None:
                                continue
                            
                            actuation = test_config.get('actuation', {})
                            if actuation.get('type') == 'Output Current Calibration':
                                stats = exec_data.get('statistics', {})
                                adjustment_factor = stats.get('adjustment_factor')
                                exec_status = exec_data.get('status', 'Not Run')
                                test_passed_in_stats = stats.get('passed', False)
                                test_passed = (exec_status == 'PASS') or test_passed_in_stats
                                
                                if adjustment_factor is not None and test_passed:
                                    logger.info(f"Charged HV Bus Test: Extracted adjustment_factor = {adjustment_factor:.6f} from Output Current Calibration test '{test_name}' (fallback search)")
                                    logger.info(f"Charged HV Bus Test: Converting adjustment_factor to trim_value: {adjustment_factor:.6f} * 100.0 = {adjustment_factor * 100.0:.4f}%")
                                    trim_value = adjustment_factor * 100.0
                                    trim_value_source = f"Output Current Calibration test '{test_name}' (fallback search, adjustment_factor={adjustment_factor:.6f})"
                                    logger.info(f"Charged HV Bus Test: ✓ Successfully extracted and calculated trim_value = {trim_value:.2f}% from passed Output Current Calibration test '{test_name}' (fallback search)")
                                    break
                    
                    # Fallback: Also check _test_result_data_temp (in case test just finished but _on_test_finished hasn't processed it yet)
                    if trim_value == fallback_trim and hasattr(self.gui, '_test_result_data_temp'):
                        logger.info(f"Charged HV Bus Test: Checking _test_result_data_temp as fallback (found {len(self.gui._test_result_data_temp)} tests)...")
                        for temp_test_name, result_data in self.gui._test_result_data_temp.items():
                            logger.debug(f"Charged HV Bus Test: Checking temp test '{temp_test_name}'...")
                            
                            # Look up test config to verify it's Output Current Calibration
                            test_config = None
                            if hasattr(self.gui, '_tests'):
                                for test in self.gui._tests:
                                    if test.get('name', '') == temp_test_name:
                                        test_config = test
                                        break
                            
                            if test_config is None:
                                logger.debug(f"Charged HV Bus Test: Test config not found for temp test '{temp_test_name}', skipping...")
                                continue
                            
                            actuation = test_config.get('actuation', {})
                            test_type = actuation.get('type', '')
                            logger.debug(f"Charged HV Bus Test: Temp test '{temp_test_name}' has type '{test_type}'")
                            
                            if test_type == 'Output Current Calibration':
                                logger.info(f"Charged HV Bus Test: Found Output Current Calibration test '{temp_test_name}' in temp storage")
                                
                                adjustment_factor = result_data.get('adjustment_factor')
                                logger.info(f"Charged HV Bus Test: adjustment_factor from temp storage: {adjustment_factor}")
                                
                                if adjustment_factor is not None:
                                    # Check if test passed (use second sweep gain error)
                                    second_sweep_gain_error = result_data.get('second_sweep_gain_error')
                                    tolerance_percent = result_data.get('tolerance_percent', 0)
                                    test_passed = False
                                    if second_sweep_gain_error is not None and tolerance_percent is not None:
                                        test_passed = abs(second_sweep_gain_error) <= tolerance_percent
                                    
                                    logger.info(f"Charged HV Bus Test: test_passed={test_passed} (second_sweep_gain_error={second_sweep_gain_error}, tolerance_percent={tolerance_percent})")
                                    
                                    if test_passed:
                                        logger.info(f"Charged HV Bus Test: Extracted adjustment_factor = {adjustment_factor:.6f} from Output Current Calibration test '{temp_test_name}' (temp storage)")
                                        logger.info(f"Charged HV Bus Test: Converting adjustment_factor to trim_value: {adjustment_factor:.6f} * 100.0 = {adjustment_factor * 100.0:.4f}%")
                                        trim_value = adjustment_factor * 100.0
                                        trim_value_source = f"Output Current Calibration test '{temp_test_name}' (temp storage, adjustment_factor={adjustment_factor:.6f})"
                                        logger.info(f"Charged HV Bus Test: ✓ Successfully extracted and calculated trim_value = {trim_value:.2f}% from passed Output Current Calibration test '{temp_test_name}' (temp storage)")
                                        break
                                    else:
                                        logger.warning(f"Charged HV Bus Test: Found Output Current Calibration test '{temp_test_name}' in temp storage but it did not pass.")
                                else:
                                    logger.warning(f"Charged HV Bus Test: Found Output Current Calibration test '{temp_test_name}' in temp storage but adjustment_factor is None. Result data keys: {list(result_data.keys()) if result_data else 'None'}")
                
                if trim_value == fallback_trim:
                    logger.info(f"Charged HV Bus Test: No Output Current Calibration test found or test did not pass. Using fallback trim value: {trim_value:.2f}%")
                
                # Validate trim value range (0-200%)
                if not (0.0 <= trim_value <= 200.0):
                    logger.warning(f"Charged HV Bus Test: Trim value {trim_value:.2f}% is outside expected range (0-200%). Proceeding anyway.")
                    # Clamp to valid range
                    if trim_value < 0.0:
                        trim_value = 0.0
                        logger.warning(f"Charged HV Bus Test: Trim value clamped to 0%")
                    elif trim_value > 200.0:
                        trim_value = 200.0
                        logger.warning(f"Charged HV Bus Test: Trim value clamped to 200%")
                
                # Log summary of trim value determination
                logger.info(f"Charged HV Bus Test: Trim value determination complete. Final trim_value = {trim_value:.2f}% (source: {trim_value_source})")
                
                # Step 2: Send Output Current Trim Value
                logger.info(f"Charged HV Bus Test: Step 2 - Sending output current trim value to DUT...")
                logger.info(f"Charged HV Bus Test: Preparing to send trim_value = {trim_value:.2f}% on signal '{trim_signal}' via CAN message 0x{cmd_msg_id:X}")
                try:
                    signals = {trim_signal: trim_value}
                    logger.debug(f"Charged HV Bus Test: Encoding signals for trim value: {signals}")
                    data_bytes = _encode_and_send_charged_hv_bus(signals, cmd_msg_id)
                    
                    if not data_bytes:
                        logger.error(f"Charged HV Bus Test: Failed to encode output current trim message. Signal: '{trim_signal}', Value: {trim_value:.2f}%, CAN ID: 0x{cmd_msg_id:X}")
                        return False, "Failed to encode output current trim message"
                    
                    logger.debug(f"Charged HV Bus Test: Encoded trim value message: {data_bytes.hex() if data_bytes else 'None'} ({len(data_bytes) if data_bytes else 0} bytes)")
                    
                    if self.can_service is not None and self.can_service.is_connected():
                        f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=time.time())
                        logger.debug(f"Charged HV Bus Test: Created CAN frame - ID: 0x{cmd_msg_id:X}, Data: {data_bytes.hex()}, Length: {len(data_bytes)} bytes")
                        try:
                            logger.info(f"Charged HV Bus Test: Attempting to send trim value frame via CAN service...")
                            success = self.can_service.send_frame(f)
                            if not success:
                                logger.error(f"Charged HV Bus Test: send_frame() returned False for trim value. CAN ID: 0x{cmd_msg_id:X}, Signal: '{trim_signal}', Value: {trim_value:.2f}%")
                                return False, f"Failed to send output current trim value: send_frame returned False"
                            else:
                                logger.info(f"Charged HV Bus Test: ✓ Successfully sent output current trim value ({trim_value:.2f}%) on CAN message 0x{cmd_msg_id:X}, signal: '{trim_signal}'")
                                logger.debug(f"Charged HV Bus Test: Trim value frame sent successfully. CAN ID: 0x{cmd_msg_id:X}, Data: {data_bytes.hex()}")
                        except Exception as e:
                            logger.error(f"Charged HV Bus Test: Exception while sending trim value frame: {e}", exc_info=True)
                            return False, f"Failed to send output current trim value: {e}"
                    elif self.gui is not None:
                        if hasattr(self.gui, 'can_service') and self.gui.can_service and self.gui.can_service.is_connected():
                            f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=time.time())
                            logger.debug(f"Charged HV Bus Test: Created CAN frame via GUI service - ID: 0x{cmd_msg_id:X}, Data: {data_bytes.hex()}, Length: {len(data_bytes)} bytes")
                            try:
                                logger.info(f"Charged HV Bus Test: Attempting to send trim value frame via GUI CAN service...")
                                success = self.gui.can_service.send_frame(f)
                                if not success:
                                    logger.error(f"Charged HV Bus Test: send_frame() returned False for trim value via GUI service. CAN ID: 0x{cmd_msg_id:X}, Signal: '{trim_signal}', Value: {trim_value:.2f}%")
                                    return False, f"Failed to send output current trim value: send_frame returned False"
                                else:
                                    logger.info(f"Charged HV Bus Test: ✓ Successfully sent output current trim value ({trim_value:.2f}%) on CAN message 0x{cmd_msg_id:X}, signal: '{trim_signal}' (via GUI service)")
                                    logger.debug(f"Charged HV Bus Test: Trim value frame sent successfully via GUI service. CAN ID: 0x{cmd_msg_id:X}, Data: {data_bytes.hex()}")
                            except Exception as e:
                                logger.error(f"Charged HV Bus Test: Exception while sending trim value frame via GUI service: {e}", exc_info=True)
                                return False, f"Failed to send output current trim value: {e}"
                        else:
                            logger.error(f"Charged HV Bus Test: GUI CAN service not available or not connected. Cannot send trim value.")
                            return False, "CAN service not available. Cannot send output current trim value."
                    else:
                        logger.error(f"Charged HV Bus Test: No GUI reference available. Cannot send trim value.")
                        return False, "CAN service not available. Cannot send output current trim value."
                except Exception as e:
                    logger.error(f"Charged HV Bus Test: Exception during trim value encoding/sending: {e}", exc_info=True)
                    return False, f"Failed to send output current trim value: {e}"
                
                _nb_sleep(SLEEP_INTERVAL_MEDIUM)
                
                # Step 3: Send Output Current Setpoint
                logger.info(f"Charged HV Bus Test: Sending output current setpoint ({output_current:.2f} A)...")
                try:
                    signals = {setpoint_signal: output_current}
                    data_bytes = _encode_and_send_charged_hv_bus(signals, cmd_msg_id)
                    
                    if not data_bytes:
                        return False, "Failed to encode output current setpoint message"
                    
                    if self.can_service is not None and self.can_service.is_connected():
                        f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=time.time())
                        try:
                            success = self.can_service.send_frame(f)
                            if not success:
                                logger.warning(f"send_frame returned False for setpoint (can_id=0x{cmd_msg_id:X})")
                            else:
                                logger.info(f"Sent output current setpoint ({output_current:.2f} A) on message 0x{cmd_msg_id:X}, signal: {setpoint_signal}")
                        except Exception as e:
                            logger.error(f"Failed to send setpoint frame: {e}", exc_info=True)
                            return False, f"Failed to send output current setpoint: {e}"
                    elif self.gui is not None:
                        if hasattr(self.gui, 'can_service') and self.gui.can_service and self.gui.can_service.is_connected():
                            f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=time.time())
                            try:
                                success = self.gui.can_service.send_frame(f)
                                if not success:
                                    logger.warning(f"send_frame returned False for setpoint (can_id=0x{cmd_msg_id:X})")
                                else:
                                    logger.info(f"Sent output current setpoint ({output_current:.2f} A) on message 0x{cmd_msg_id:X}, signal: {setpoint_signal}")
                            except Exception as e:
                                logger.error(f"Failed to send setpoint frame via GUI service: {e}", exc_info=True)
                                return False, f"Failed to send output current setpoint: {e}"
                        else:
                            return False, "CAN service not available. Cannot send output current setpoint."
                    else:
                        return False, "CAN service not available. Cannot send output current setpoint."
                except Exception as e:
                    logger.error(f"Failed to send output current setpoint: {e}")
                    return False, f"Failed to send output current setpoint: {e}"
                
                _nb_sleep(SLEEP_INTERVAL_MEDIUM)
                
                # Step 4: Start CAN Data Logging
                logger.info("Charged HV Bus Test: Starting CAN data logging...")
                logged_data = []  # List of dicts: {'timestamp': float, 'signal_name': str, 'value': float}
                
                # Step 5: Send Test Trigger
                logger.info(f"Charged HV Bus Test: Sending test trigger signal (value: {trigger_value})...")
                try:
                    signals = {trigger_signal: trigger_value}
                    data_bytes = _encode_and_send_charged_hv_bus(signals, cmd_msg_id)
                    
                    if not data_bytes:
                        return False, "Failed to encode test trigger message"
                    
                    trigger_timestamp = time.time()
                    
                    if self.can_service is not None and self.can_service.is_connected():
                        f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=trigger_timestamp)
                        try:
                            success = self.can_service.send_frame(f)
                            if not success:
                                logger.warning(f"send_frame returned False for test trigger (can_id=0x{cmd_msg_id:X})")
                            else:
                                logger.info(f"Sent test trigger signal (value: {trigger_value}) on message 0x{cmd_msg_id:X}, signal: {trigger_signal}")
                        except Exception as e:
                            logger.error(f"Failed to send test trigger frame: {e}", exc_info=True)
                            return False, f"Failed to send test trigger: {e}"
                    elif self.gui is not None:
                        if hasattr(self.gui, 'can_service') and self.gui.can_service and self.gui.can_service.is_connected():
                            f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=trigger_timestamp)
                            try:
                                success = self.gui.can_service.send_frame(f)
                                if not success:
                                    logger.warning(f"send_frame returned False for test trigger (can_id=0x{cmd_msg_id:X})")
                                else:
                                    logger.info(f"Sent test trigger signal (value: {trigger_value}) on message 0x{cmd_msg_id:X}, signal: {trigger_signal}")
                            except Exception as e:
                                logger.error(f"Failed to send test trigger frame via GUI service: {e}", exc_info=True)
                                return False, f"Failed to send test trigger: {e}"
                        else:
                            return False, "CAN service not available. Cannot send test trigger."
                    else:
                        return False, "CAN service not available. Cannot send test trigger."
                except Exception as e:
                    logger.error(f"Failed to send test trigger: {e}")
                    return False, f"Failed to send test trigger: {e}"
                
                # Step 6: Monitor Test Execution (until test_time_ms elapsed)
                logger.info(f"Charged HV Bus Test: Monitoring test execution for {test_time_ms}ms...")
                end_time = trigger_timestamp + (test_time_ms / 1000.0)
                fault_detected = False
                
                try:
                    while time.time() < end_time:
                        current_time = time.time()
                        
                        # Read all feedback signals
                        signals_to_read = [
                            (dut_state_signal, 'dut_test_state'),
                            (enable_relay_signal, 'enable_relay'),
                            (enable_pfc_signal, 'enable_pfc'),
                            (pfc_power_good_signal, 'pfc_power_good'),
                            (pcmc_signal, 'pcmc'),
                            (psfb_fault_signal, 'psfb_fault')
                        ]
                        
                        for signal_name, log_key in signals_to_read:
                            try:
                                if self.signal_service is not None:
                                    ts, val = self.signal_service.get_latest_signal(feedback_msg_id, signal_name)
                                elif self.gui is not None:
                                    ts, val = self.gui.get_latest_signal(feedback_msg_id, signal_name)
                                else:
                                    ts, val = (None, None)
                                
                                if val is not None:
                                    try:
                                        val_float = float(val)
                                        monitor_key = monitor_signal_map.get(signal_name)
                                        if monitor_key:
                                            self.update_monitor_signal(monitor_key, val_float)
                                        logged_data.append({
                                            'timestamp': current_time,
                                            'signal_name': log_key,
                                            'value': val_float
                                        })
                                        
                                        # Check for fault condition (DUT Test State = 7)
                                        if signal_name == dut_state_signal:
                                            if int(val_float) == 7:
                                                fault_detected = True
                                                logger.warning(f"Charged HV Bus Test: DUT fault detected (Test State = 7) at {current_time - trigger_timestamp:.2f}s")
                                    except (ValueError, TypeError):
                                        pass
                            except Exception as e:
                                logger.debug(f"Error reading signal {signal_name}: {e}")
                        
                        # If fault detected, stop immediately
                        if fault_detected:
                            logger.warning("Charged HV Bus Test: Fault detected, stopping test execution early")
                            break
                        
                        time.sleep(SLEEP_INTERVAL_SHORT)
                finally:
                    # Step 7: Always stop test and logging, even if fault detected or exception occurred
                    logger.info("Charged HV Bus Test: Stopping test and logging...")
                    try:
                        signals = {trigger_signal: 0}
                        data_bytes = _encode_and_send_charged_hv_bus(signals, cmd_msg_id)
                        
                        if data_bytes:
                            if self.can_service is not None and self.can_service.is_connected():
                                f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=time.time())
                                try:
                                    success = self.can_service.send_frame(f)
                                    if success:
                                        logger.info(f"Sent test stop signal (value: 0) on message 0x{cmd_msg_id:X}, signal: {trigger_signal}")
                                    else:
                                        logger.warning(f"Failed to send test stop signal: send_frame returned False")
                                except Exception as e:
                                    logger.warning(f"Failed to send test stop signal: {e}")
                            elif self.gui is not None:
                                if hasattr(self.gui, 'can_service') and self.gui.can_service and self.gui.can_service.is_connected():
                                    f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=time.time())
                                    try:
                                        success = self.gui.can_service.send_frame(f)
                                        if success:
                                            logger.info(f"Sent test stop signal (value: 0) on message 0x{cmd_msg_id:X}, signal: {trigger_signal}")
                                        else:
                                            logger.warning(f"Failed to send test stop signal: send_frame returned False")
                                    except Exception as e:
                                        logger.warning(f"Failed to send test stop signal: {e}")
                    except Exception as e:
                        logger.warning(f"Failed to send test stop signal during cleanup: {e}")
                    
                    _nb_sleep(SLEEP_INTERVAL_MEDIUM)
                
                # Step 8: Analyze Logged CAN Data - PFC Regulation
                logger.info("Charged HV Bus Test: Analyzing logged data for PFC Regulation...")
                pfc_regulation_success = False
                
                # Find timestamps where enable_pfc = 1
                enable_pfc_timestamps = []
                for entry in logged_data:
                    if entry['signal_name'] == 'enable_pfc' and int(entry['value']) == 1:
                        enable_pfc_timestamps.append(entry['timestamp'])
                
                # Check if pfc_power_good transitions from 0→1 after enable_pfc = 1
                for enable_pfc_ts in enable_pfc_timestamps:
                    # Find pfc_power_good values after this timestamp
                    pfc_power_good_values = []
                    for entry in logged_data:
                        if entry['signal_name'] == 'pfc_power_good' and entry['timestamp'] >= enable_pfc_ts:
                            pfc_power_good_values.append((entry['timestamp'], entry['value']))
                    
                    # Check if we have a transition from 0→1
                    if len(pfc_power_good_values) >= 2:
                        # Sort by timestamp
                        pfc_power_good_values.sort(key=lambda x: x[0])
                        # Check if first value is 0 and later value is 1
                        first_val = int(pfc_power_good_values[0][1])
                        for ts, val in pfc_power_good_values[1:]:
                            if first_val == 0 and int(val) == 1:
                                pfc_regulation_success = True
                                logger.info(f"Charged HV Bus Test: PFC Regulation successful (transition 0→1 detected)")
                                break
                        if pfc_regulation_success:
                            break
                
                if not pfc_regulation_success:
                    logger.warning("Charged HV Bus Test: PFC Regulation failed (no 0→1 transition detected)")
                
                # Step 9: Analyze Logged CAN Data - PCMC Success
                logger.info("Charged HV Bus Test: Analyzing logged data for PCMC Success...")
                pcmc_success = False
                
                # Get latest pcmc signal value
                pcmc_values = [entry for entry in logged_data if entry['signal_name'] == 'pcmc']
                if pcmc_values:
                    latest_pcmc = pcmc_values[-1]['value']
                    if int(latest_pcmc) == 1:
                        pcmc_success = True
                        logger.info("Charged HV Bus Test: PCMC Success (PCMC signal = 1)")
                    else:
                        logger.warning(f"Charged HV Bus Test: PCMC Success failed (PCMC signal = {latest_pcmc})")
                else:
                    logger.warning("Charged HV Bus Test: PCMC Success failed (no PCMC data collected)")
                
                # Check final DUT Test State
                dut_state_values = [entry for entry in logged_data if entry['signal_name'] == 'dut_test_state']
                final_dut_state = None
                if dut_state_values:
                    final_dut_state = int(dut_state_values[-1]['value'])
                
                # Step 10: Determine Pass/Fail
                passed = False
                if fault_detected:
                    passed = False
                    info = "Test failed: DUT fault detected (Test State = 7)"
                elif final_dut_state is not None and final_dut_state != trigger_value:
                    passed = False
                    info = f"Test failed: DUT Test State ({final_dut_state}) does not match trigger value ({trigger_value})"
                elif not pfc_regulation_success:
                    passed = False
                    info = "Test failed: PFC Regulation failed (PFC Power Good never transitioned from 0→1)"
                elif not pcmc_success:
                    passed = False
                    info = "Test failed: PCMC Success failed (PCMC signal ≠ 1)"
                else:
                    passed = True
                    info = "Test passed: PFC Regulation successful AND PCMC Success AND No fault detected"
                
                # Build detailed info string
                info += f"\nPFC Regulation: {'SUCCESS' if pfc_regulation_success else 'FAIL'}"
                info += f"\nPCMC Success: {'SUCCESS' if pcmc_success else 'FAIL'}"
                info += f"\nFault Detected: {'YES' if fault_detected else 'NO'}"
                if final_dut_state is not None:
                    info += f"\nFinal DUT Test State: {final_dut_state} (expected: {trigger_value})"
                info += f"\nTotal data points logged: {len(logged_data)}"
                
                # Store results for display
                test_name = test.get('name', '<unnamed>')
                result_data = {
                    'pfc_regulation_success': pfc_regulation_success,
                    'pcmc_success': pcmc_success,
                    'fault_detected': fault_detected,
                    'final_dut_state': final_dut_state,
                    'trigger_value': trigger_value,
                    'trim_value_used': trim_value,
                    'logged_data': logged_data,
                    'passed': passed
                }
                
                # Store in temporary storage for retrieval by _on_test_finished
                if self.gui is not None:
                    if not hasattr(self.gui, '_test_result_data_temp'):
                        self.gui._test_result_data_temp = {}
                    self.gui._test_result_data_temp[test_name] = result_data
                
                logger.info(f"Charged HV Bus Test completed: {'PASS' if passed else 'FAIL'}")
                return passed, info
            elif act.get('type') == 'Charger Functional Test':
                # Charger Functional Test execution:
                # 0) Pre-Test Safety Dialog (BEFORE any test execution)
                # 1) Get Output Current Trim Value (from previous test or fallback)
                # 2) Send Output Current Trim Value
                # 3) Send Output Current Setpoint
                # 4) Start CAN Data Logging and Send Test Trigger
                # 5) Monitor Test Execution (until test_time_ms elapsed)
                # 6) Stop Test and Logging
                # 7) Analyze Logged CAN Data - PFC Regulation
                # 8) Analyze Logged CAN Data - PCMC Success
                # 9) Analyze Logged CAN Data - Output Current Regulation
                # 10) Determine Pass/Fail
                
                # Step 0: Pre-Test Safety Dialog - MUST be shown BEFORE any test execution
                # Must be shown in main GUI thread (Qt requirement)
                logger.info("Charger Functional Test: Showing pre-test safety dialog BEFORE test execution...")
                dialog_result = None
                
                if self.gui is not None:
                    try:
                        from PySide6 import QtCore
                        from PySide6.QtWidgets import QMessageBox
                        
                        # Check if we're in the main thread
                        current_thread = QtCore.QThread.currentThread()
                        main_thread = QtCore.QCoreApplication.instance().thread()
                        
                        if current_thread == main_thread:
                            # We're in the main thread, show dialog directly
                            self.gui._show_charger_functional_safety_dialog()
                            dialog_result = getattr(self.gui, '_charger_functional_dialog_result', QMessageBox.No)
                        else:
                            # We're in a background thread, use BlockingQueuedConnection
                            # This will block the background thread until the dialog method returns
                            # Initialize result attribute if not present
                            if not hasattr(self.gui, '_charger_functional_dialog_result'):
                                self.gui._charger_functional_dialog_result = None
                            
                            # Clear previous result
                            self.gui._charger_functional_dialog_result = None
                            
                            # Invoke dialog in main thread using BlockingQueuedConnection
                            # This blocks until the method completes
                            success = QtCore.QMetaObject.invokeMethod(
                                self.gui,
                                '_show_charger_functional_safety_dialog',
                                QtCore.Qt.ConnectionType.BlockingQueuedConnection
                            )
                            
                            if success:
                                # After BlockingQueuedConnection returns, the method has completed
                                # Get the result that was stored
                                dialog_result = getattr(self.gui, '_charger_functional_dialog_result', QMessageBox.No)
                                if dialog_result is None:
                                    logger.warning("Dialog result is None, defaulting to No")
                                    dialog_result = QMessageBox.No
                            else:
                                logger.warning("Failed to invoke dialog method, defaulting to No")
                                dialog_result = QMessageBox.No
                        
                        if dialog_result == QMessageBox.No:
                            # Request pause of test sequence - test will NOT execute
                            logger.info("Charger Functional Test: User declined safety check, pausing test sequence (test will not execute)")
                            
                            # Request pause safely from main thread using QMetaObject.invokeMethod
                            # This avoids threading issues that can cause segfaults
                            if self.gui is not None:
                                try:
                                    # Check if we're in the main thread
                                    current_thread = QtCore.QThread.currentThread()
                                    main_thread = QtCore.QCoreApplication.instance().thread()
                                    
                                    if current_thread == main_thread:
                                        # We're in the main thread, call directly
                                        if hasattr(self.gui, '_request_test_sequence_pause'):
                                            self.gui._request_test_sequence_pause()
                                    else:
                                        # We're in a background thread, use QueuedConnection (non-blocking)
                                        QtCore.QMetaObject.invokeMethod(
                                            self.gui,
                                            '_request_test_sequence_pause',
                                            QtCore.Qt.ConnectionType.QueuedConnection
                                        )
                                    logger.info("Charger Functional Test: Pause requested on test execution thread")
                                except Exception as e:
                                    logger.warning(f"Failed to request pause on test execution thread: {e}")
                            
                            return False, "Test sequence paused: User declined safety check. Please ensure hardware connections are ready and resume the test sequence."
                    except Exception as e:
                        logger.error(f"Failed to show pre-test safety dialog: {e}", exc_info=True)
                        # On error, default to No (don't execute test if we can't show dialog)
                        logger.warning("Dialog error - defaulting to No (test will not execute)")
                        return False, "Test sequence paused: Failed to show safety dialog. Please ensure hardware connections are ready and resume the test sequence."
                
                # If we reach here, user pressed Yes - continue with test execution
                logger.info("Charger Functional Test: User confirmed safety check, proceeding with test execution...")
                
                # Extract parameters (only after user confirms)
                cmd_msg_id = act.get('command_signal_source')
                trigger_signal = act.get('test_trigger_signal')
                trigger_value = act.get('test_trigger_signal_value')
                trim_signal = act.get('set_output_current_trim_signal')
                fallback_trim = act.get('fallback_output_current_trim_value', 100.0)
                setpoint_signal = act.get('set_output_current_setpoint_signal')
                output_current = act.get('output_test_current')
                feedback_msg_id = act.get('feedback_signal_source')
                dut_state_signal = act.get('dut_test_state_signal')
                enable_relay_signal = act.get('enable_relay_signal')
                enable_pfc_signal = act.get('enable_pfc_signal')
                pfc_power_good_signal = act.get('pfc_power_good_signal')
                pcmc_signal = act.get('pcmc_signal')
                output_current_signal = act.get('output_current_signal')
                psfb_fault_signal = act.get('psfb_fault_signal')
                output_current_tolerance = act.get('output_current_tolerance', 0.5)
                test_time_ms = int(act.get('test_time_ms', 30000))
                
                # Validate parameters
                if not all([cmd_msg_id, trigger_signal, trigger_value is not None, trim_signal, 
                           setpoint_signal, output_current is not None, feedback_msg_id,
                           dut_state_signal, enable_relay_signal, enable_pfc_signal,
                           pfc_power_good_signal, pcmc_signal, output_current_signal, psfb_fault_signal]):
                    return False, "Missing required Charger Functional Test parameters"
                
                if test_time_ms < 1000:
                    return False, "Test time must be >= 1000 ms"
                
                if output_current_tolerance is None or output_current_tolerance < 0:
                    return False, "Output current tolerance must be >= 0"
                
                # Validate tolerance is reasonable (not too large compared to setpoint)
                if output_current > 0 and output_current_tolerance > output_current * 0.5:
                    logger.warning(f"Charger Functional Test: Output current tolerance ({output_current_tolerance}A) is > 50% of setpoint ({output_current}A), may be too lenient")
                
                # Validate test duration is sufficient for current regulation analysis
                if test_time_ms < 2000:
                    logger.warning(f"Charger Functional Test: Test duration ({test_time_ms}ms) is less than 2 seconds, may not provide sufficient data for current regulation analysis")
                
                monitor_signal_map = {}
                if enable_relay_signal:
                    monitor_signal_map[enable_relay_signal] = 'enable_relay'
                if enable_pfc_signal:
                    monitor_signal_map[enable_pfc_signal] = 'enable_pfc'
                if pfc_power_good_signal:
                    monitor_signal_map[pfc_power_good_signal] = 'pfc_power_good'
                if output_current_signal:
                    monitor_signal_map[output_current_signal] = 'output_current'
                
                # Import AdapterFrame at function level
                try:
                    from backend.adapters.interface import Frame as AdapterFrame
                except ImportError:
                    AdapterFrame = None
                
                def _nb_sleep(sec: float) -> None:
                    """Non-blocking sleep that processes Qt events."""
                    end = time.time() + float(sec)
                    while time.time() < end:
                        remaining = end - time.time()
                        if remaining <= 0:
                            break
                        time.sleep(min(SLEEP_INTERVAL_SHORT, remaining))
                
                # Helper function to encode and send CAN message
                def _encode_and_send_charger_functional(signals: dict, msg_id: int) -> bytes:
                    """Encode signals to CAN message bytes."""
                    encode_data = {'DeviceID': 0}
                    determined_mux_value = None
                    data_bytes = b''
                    
                    dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded())
                    if dbc_available:
                        target_msg = self.dbc_service.find_message_by_id(msg_id)
                    else:
                        target_msg = None
                    
                    if target_msg is None:
                        logger.warning(f"Could not find message for CAN ID 0x{msg_id:X}")
                    
                    if target_msg is not None:
                        # Determine MessageType first based on signals being sent
                        for sig_name in signals:
                            for sig in target_msg.signals:
                                if sig.name == sig_name and getattr(sig, 'multiplexer_ids', None):
                                    determined_mux_value = sig.multiplexer_ids[0]
                                    break
                            if determined_mux_value is not None:
                                break
                        
                        # Set MessageType if determined
                        if determined_mux_value is not None:
                            encode_data['MessageType'] = determined_mux_value
                        
                        # Add signals from the signals dict, but filter out signals that aren't valid for the current MessageType
                        for sig_name in signals:
                            should_include = True
                            
                            # Check if this signal is multiplexed
                            for sig in target_msg.signals:
                                if sig.name == sig_name:
                                    multiplexer_ids = getattr(sig, 'multiplexer_ids', None)
                                    if multiplexer_ids:
                                        # Signal is multiplexed - only include if MessageType matches
                                        if determined_mux_value is not None:
                                            if isinstance(multiplexer_ids, (list, tuple)):
                                                should_include = (determined_mux_value in multiplexer_ids)
                                            else:
                                                should_include = (determined_mux_value == multiplexer_ids)
                                        else:
                                            should_include = True
                                    break
                            
                            if should_include:
                                encode_data[sig_name] = signals[sig_name]
                        
                        try:
                            if self.dbc_service is not None:
                                data_bytes = self.dbc_service.encode_message(target_msg, encode_data)
                            else:
                                data_bytes = target_msg.encode(encode_data)
                        except Exception:
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
                
                # Step 1: Get Output Current Trim Value (same logic as Charged HV Bus Test)
                logger.info("Charger Functional Test: Step 1 - Getting output current trim value...")
                logger.info(f"Charger Functional Test: Fallback trim value from config: {fallback_trim:.2f}%")
                trim_value = fallback_trim
                trim_value_source = "fallback (config default)"
                
                # Try to get adjustment_factor from previous Output Current Calibration test
                if self.gui is not None:
                    # Strategy 1: Search through _tests list directly (most reliable)
                    if hasattr(self.gui, '_tests') and hasattr(self.gui, '_test_execution_data'):
                        logger.info(f"Charger Functional Test: Searching through {len(self.gui._tests)} tests for Output Current Calibration test...")
                        
                        found_calibration_test = False
                        for test in reversed(self.gui._tests):
                            test_name = test.get('name', '')
                            actuation = test.get('actuation', {})
                            test_type = actuation.get('type', '')
                            
                            if test_type == 'Output Current Calibration':
                                if test_name in self.gui._test_execution_data:
                                    found_calibration_test = True
                                    exec_data = self.gui._test_execution_data[test_name]
                                    stats = exec_data.get('statistics', {})
                                    adjustment_factor = stats.get('adjustment_factor')
                                    exec_status = exec_data.get('status', 'Not Run')
                                    test_passed_in_stats = stats.get('passed', False)
                                    test_passed = (exec_status == 'PASS') or test_passed_in_stats
                                    
                                    if adjustment_factor is not None and test_passed:
                                        trim_value = adjustment_factor * 100.0
                                        trim_value_source = f"Output Current Calibration test '{test_name}' (adjustment_factor={adjustment_factor:.6f})"
                                        logger.info(f"Charger Functional Test: ✓ Using trim_value = {trim_value:.2f}% from Output Current Calibration test '{test_name}'")
                                        break
                
                if trim_value == fallback_trim:
                    logger.info(f"Charger Functional Test: No Output Current Calibration test found or test did not pass. Using fallback trim value: {trim_value:.2f}%")
                
                # Validate trim value range (0-200%)
                if not (0.0 <= trim_value <= 200.0):
                    logger.warning(f"Charger Functional Test: Trim value {trim_value:.2f}% is outside expected range (0-200%). Proceeding anyway.")
                    # Clamp to valid range
                    if trim_value < 0.0:
                        trim_value = 0.0
                        logger.warning(f"Charger Functional Test: Trim value clamped to 0%")
                    elif trim_value > 200.0:
                        trim_value = 200.0
                        logger.warning(f"Charger Functional Test: Trim value clamped to 200%")
                
                # Step 2: Send Output Current Trim Value
                logger.info(f"Charger Functional Test: Step 2 - Sending output current trim value to DUT...")
                try:
                    signals = {trim_signal: trim_value}
                    data_bytes = _encode_and_send_charger_functional(signals, cmd_msg_id)
                    
                    if not data_bytes:
                        return False, "Failed to encode output current trim message"
                    
                    if self.can_service is not None and self.can_service.is_connected():
                        f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=time.time())
                        try:
                            success = self.can_service.send_frame(f)
                            if not success:
                                return False, f"Failed to send output current trim value: send_frame returned False"
                            else:
                                logger.info(f"Charger Functional Test: ✓ Sent output current trim value ({trim_value:.2f}%)")
                        except Exception as e:
                            return False, f"Failed to send output current trim value: {e}"
                    elif self.gui is not None:
                        if hasattr(self.gui, 'can_service') and self.gui.can_service and self.gui.can_service.is_connected():
                            f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=time.time())
                            try:
                                success = self.gui.can_service.send_frame(f)
                                if not success:
                                    return False, f"Failed to send output current trim value: send_frame returned False"
                                else:
                                    logger.info(f"Charger Functional Test: ✓ Sent output current trim value ({trim_value:.2f}%)")
                            except Exception as e:
                                return False, f"Failed to send output current trim value: {e}"
                        else:
                            return False, "CAN service not available. Cannot send output current trim value."
                    else:
                        return False, "CAN service not available. Cannot send output current trim value."
                except Exception as e:
                    logger.error(f"Charger Functional Test: Exception during trim value encoding/sending: {e}", exc_info=True)
                    return False, f"Failed to send output current trim value: {e}"
                
                _nb_sleep(SLEEP_INTERVAL_MEDIUM)
                
                # Step 3: Send Output Current Setpoint
                logger.info(f"Charger Functional Test: Step 3 - Sending output current setpoint ({output_current:.2f} A)...")
                try:
                    signals = {setpoint_signal: output_current}
                    data_bytes = _encode_and_send_charger_functional(signals, cmd_msg_id)
                    
                    if not data_bytes:
                        return False, "Failed to encode output current setpoint message"
                    
                    if self.can_service is not None and self.can_service.is_connected():
                        f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=time.time())
                        try:
                            success = self.can_service.send_frame(f)
                            if not success:
                                logger.warning(f"send_frame returned False for setpoint (can_id=0x{cmd_msg_id:X})")
                            else:
                                logger.info(f"Sent output current setpoint ({output_current:.2f} A)")
                        except Exception as e:
                            logger.error(f"Failed to send setpoint frame: {e}", exc_info=True)
                            return False, f"Failed to send output current setpoint: {e}"
                    elif self.gui is not None:
                        if hasattr(self.gui, 'can_service') and self.gui.can_service and self.gui.can_service.is_connected():
                            f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=time.time())
                            try:
                                success = self.gui.can_service.send_frame(f)
                                if not success:
                                    logger.warning(f"send_frame returned False for setpoint (can_id=0x{cmd_msg_id:X})")
                                else:
                                    logger.info(f"Sent output current setpoint ({output_current:.2f} A)")
                            except Exception as e:
                                logger.error(f"Failed to send setpoint frame via GUI service: {e}", exc_info=True)
                                return False, f"Failed to send output current setpoint: {e}"
                        else:
                            return False, "CAN service not available. Cannot send output current setpoint."
                    else:
                        return False, "CAN service not available. Cannot send output current setpoint."
                except Exception as e:
                    logger.error(f"Failed to send output current setpoint: {e}")
                    return False, f"Failed to send output current setpoint: {e}"
                
                _nb_sleep(SLEEP_INTERVAL_MEDIUM)
                
                # Step 4: Start CAN Data Logging and Send Test Trigger
                logger.info("Charger Functional Test: Starting CAN data logging...")
                logged_data = []  # List of dicts: {'timestamp': float, 'signal_name': str, 'value': float}
                
                logger.info(f"Charger Functional Test: Sending test trigger signal (value: {trigger_value})...")
                try:
                    signals = {trigger_signal: trigger_value}
                    data_bytes = _encode_and_send_charger_functional(signals, cmd_msg_id)
                    
                    if not data_bytes:
                        return False, "Failed to encode test trigger message"
                    
                    trigger_timestamp = time.time()
                    
                    if self.can_service is not None and self.can_service.is_connected():
                        f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=trigger_timestamp)
                        try:
                            success = self.can_service.send_frame(f)
                            if not success:
                                logger.warning(f"send_frame returned False for test trigger (can_id=0x{cmd_msg_id:X})")
                            else:
                                logger.info(f"Sent test trigger signal (value: {trigger_value})")
                        except Exception as e:
                            logger.error(f"Failed to send test trigger frame: {e}", exc_info=True)
                            return False, f"Failed to send test trigger: {e}"
                    elif self.gui is not None:
                        if hasattr(self.gui, 'can_service') and self.gui.can_service and self.gui.can_service.is_connected():
                            f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=trigger_timestamp)
                            try:
                                success = self.gui.can_service.send_frame(f)
                                if not success:
                                    logger.warning(f"send_frame returned False for test trigger (can_id=0x{cmd_msg_id:X})")
                                else:
                                    logger.info(f"Sent test trigger signal (value: {trigger_value})")
                            except Exception as e:
                                logger.error(f"Failed to send test trigger frame via GUI service: {e}", exc_info=True)
                                return False, f"Failed to send test trigger: {e}"
                        else:
                            return False, "CAN service not available. Cannot send test trigger."
                    else:
                        return False, "CAN service not available. Cannot send test trigger."
                except Exception as e:
                    logger.error(f"Failed to send test trigger: {e}")
                    return False, f"Failed to send test trigger: {e}"
                
                # Step 5: Monitor Test Execution (until test_time_ms elapsed)
                logger.info(f"Charger Functional Test: Monitoring test execution for {test_time_ms}ms...")
                end_time = trigger_timestamp + (test_time_ms / 1000.0)
                fault_detected = False
                
                try:
                    while time.time() < end_time:
                        current_time = time.time()
                        
                        # Read all feedback signals (including output_current_signal)
                        signals_to_read = [
                            (dut_state_signal, 'dut_test_state'),
                            (enable_relay_signal, 'enable_relay'),
                            (enable_pfc_signal, 'enable_pfc'),
                            (pfc_power_good_signal, 'pfc_power_good'),
                            (pcmc_signal, 'pcmc'),
                            (output_current_signal, 'output_current'),
                            (psfb_fault_signal, 'psfb_fault')
                        ]
                        
                        for signal_name, log_key in signals_to_read:
                            try:
                                if self.signal_service is not None:
                                    ts, val = self.signal_service.get_latest_signal(feedback_msg_id, signal_name)
                                elif self.gui is not None:
                                    ts, val = self.gui.get_latest_signal(feedback_msg_id, signal_name)
                                else:
                                    ts, val = (None, None)
                                
                                if val is not None:
                                    try:
                                        val_float = float(val)
                                        monitor_key = monitor_signal_map.get(signal_name)
                                        if monitor_key:
                                            self.update_monitor_signal(monitor_key, val_float)
                                        logged_data.append({
                                            'timestamp': current_time,
                                            'signal_name': log_key,
                                            'value': val_float
                                        })
                                        
                                        # Check for fault condition (DUT Test State = 7)
                                        if signal_name == dut_state_signal:
                                            if int(val_float) == 7:
                                                fault_detected = True
                                                logger.warning(f"Charger Functional Test: DUT fault detected (Test State = 7) at {current_time - trigger_timestamp:.2f}s")
                                    except (ValueError, TypeError):
                                        pass
                            except Exception as e:
                                logger.debug(f"Error reading signal {signal_name}: {e}")
                        
                        # If fault detected, stop immediately
                        if fault_detected:
                            logger.warning("Charger Functional Test: Fault detected, stopping test execution early")
                            break
                        
                        time.sleep(SLEEP_INTERVAL_SHORT)
                finally:
                    # Step 6: Always stop test and logging, even if fault detected or exception occurred
                    logger.info("Charger Functional Test: Stopping test and logging...")
                    try:
                        signals = {trigger_signal: 0}
                        data_bytes = _encode_and_send_charger_functional(signals, cmd_msg_id)
                        
                        if data_bytes:
                            if self.can_service is not None and self.can_service.is_connected():
                                f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=time.time())
                                try:
                                    success = self.can_service.send_frame(f)
                                    if success:
                                        logger.info(f"Sent test stop signal (value: 0)")
                                    else:
                                        logger.warning(f"Failed to send test stop signal: send_frame returned False")
                                except Exception as e:
                                    logger.warning(f"Failed to send test stop signal: {e}")
                            elif self.gui is not None:
                                if hasattr(self.gui, 'can_service') and self.gui.can_service and self.gui.can_service.is_connected():
                                    f = AdapterFrame(can_id=cmd_msg_id, data=data_bytes, timestamp=time.time())
                                    try:
                                        success = self.gui.can_service.send_frame(f)
                                        if success:
                                            logger.info(f"Sent test stop signal (value: 0)")
                                        else:
                                            logger.warning(f"Failed to send test stop signal: send_frame returned False")
                                    except Exception as e:
                                        logger.warning(f"Failed to send test stop signal: {e}")
                    except Exception as e:
                        logger.warning(f"Failed to send test stop signal during cleanup: {e}")
                    
                    _nb_sleep(SLEEP_INTERVAL_MEDIUM)
                
                # Step 7: Analyze Logged CAN Data - PFC Regulation
                logger.info("Charger Functional Test: Analyzing logged data for PFC Regulation...")
                pfc_regulation_success = False
                
                # Find timestamps where enable_pfc = 1
                enable_pfc_timestamps = []
                for entry in logged_data:
                    if entry['signal_name'] == 'enable_pfc' and int(entry['value']) == 1:
                        enable_pfc_timestamps.append(entry['timestamp'])
                
                # Check if pfc_power_good transitions from 1→0 after enable_pfc = 1 (PFC is regulating when signal is 0)
                for enable_pfc_ts in enable_pfc_timestamps:
                    # Find pfc_power_good values after this timestamp
                    pfc_power_good_values = []
                    for entry in logged_data:
                        if entry['signal_name'] == 'pfc_power_good' and entry['timestamp'] >= enable_pfc_ts:
                            pfc_power_good_values.append((entry['timestamp'], entry['value']))
                    
                    # Check if we have a transition from 1→0
                    if len(pfc_power_good_values) >= 2:
                        # Sort by timestamp
                        pfc_power_good_values.sort(key=lambda x: x[0])
                        # Check if first value is 1 and later value is 0 (PFC is regulating when signal is 0)
                        first_val = int(pfc_power_good_values[0][1])
                        for ts, val in pfc_power_good_values[1:]:
                            if first_val == 1 and int(val) == 0:
                                pfc_regulation_success = True
                                logger.info(f"Charger Functional Test: PFC Regulation successful (transition 1→0 detected, PFC is regulating when signal is 0)")
                                break
                        if pfc_regulation_success:
                            break
                
                if not pfc_regulation_success:
                    logger.warning("Charger Functional Test: PFC Regulation failed (no 1→0 transition detected, PFC is regulating when signal is 0)")
                
                # Step 8: Analyze Logged CAN Data - PCMC Success
                logger.info("Charger Functional Test: Analyzing logged data for PCMC Success...")
                pcmc_success = False
                
                # Get latest pcmc signal value
                pcmc_values = [entry for entry in logged_data if entry['signal_name'] == 'pcmc']
                if pcmc_values:
                    latest_pcmc = pcmc_values[-1]['value']
                    if int(latest_pcmc) == 1:
                        pcmc_success = True
                        logger.info("Charger Functional Test: PCMC Success (PCMC signal = 1)")
                    else:
                        logger.warning(f"Charger Functional Test: PCMC Success failed (PCMC signal = {latest_pcmc})")
                else:
                    logger.warning("Charger Functional Test: PCMC Success failed (no PCMC data collected)")
                
                # Step 9: Analyze Logged CAN Data - Output Current Regulation
                logger.info("Charger Functional Test: Analyzing logged data for Output Current Regulation...")
                current_regulation_success = False
                avg_current = None
                
                # Extract output current values from last 1 second
                test_end_time = trigger_timestamp + (test_time_ms / 1000.0)
                one_second_before_end = test_end_time - 1.0
                
                # Validate test duration is sufficient
                if test_time_ms < 1000:
                    logger.warning(f"Charger Functional Test: Test duration ({test_time_ms}ms) is less than 1 second, cannot use last 1 second for regulation analysis")
                    one_second_before_end = trigger_timestamp  # Use all data if test is too short
                
                output_current_values = []
                for entry in logged_data:
                    if entry['signal_name'] == 'output_current' and entry['timestamp'] >= one_second_before_end:
                        output_current_values.append(entry['value'])
                
                if not output_current_values:
                    # If no data in last 1 second, use all available data and log warning
                    logger.warning("Charger Functional Test: Less than 1 second of output current data available, using all available data")
                    output_current_values = [entry['value'] for entry in logged_data if entry['signal_name'] == 'output_current']
                
                # Validate minimum sample count for regulation analysis
                if output_current_values:
                    min_samples = max(5, int(len(output_current_values) * 0.5))  # At least 5 samples or 50% of available
                    if len(output_current_values) < min_samples:
                        logger.warning(f"Charger Functional Test: Only {len(output_current_values)} output current samples available for regulation analysis, expected at least {min_samples}")
                
                if output_current_values:
                    # Calculate average
                    avg_current = sum(output_current_values) / len(output_current_values)
                    error = abs(avg_current - output_current)
                    
                    if error <= output_current_tolerance:
                        current_regulation_success = True
                        logger.info(f"Charger Functional Test: Output Current Regulation successful (average = {avg_current:.3f}A, expected = {output_current:.3f}A, error = {error:.3f}A <= tolerance = {output_current_tolerance:.3f}A)")
                    else:
                        logger.warning(f"Charger Functional Test: Output Current Regulation failed (average = {avg_current:.3f}A, expected = {output_current:.3f}A, error = {error:.3f}A > tolerance = {output_current_tolerance:.3f}A)")
                else:
                    logger.warning("Charger Functional Test: Output Current Regulation failed (no output current data collected)")
                
                # Check final DUT Test State
                dut_state_values = [entry for entry in logged_data if entry['signal_name'] == 'dut_test_state']
                final_dut_state = None
                if dut_state_values:
                    final_dut_state = int(dut_state_values[-1]['value'])
                
                # Step 10: Determine Pass/Fail
                passed = False
                if fault_detected:
                    passed = False
                    info = "Test failed: DUT fault detected (Test State = 7)"
                elif final_dut_state is not None and final_dut_state != trigger_value:
                    passed = False
                    info = f"Test failed: DUT Test State ({final_dut_state}) does not match trigger value ({trigger_value})"
                elif not pfc_regulation_success:
                    passed = False
                    info = "Test failed: PFC Regulation failed (PFC Power Good never transitioned from 1→0, PFC is regulating when signal is 0)"
                elif not pcmc_success:
                    passed = False
                    info = "Test failed: PCMC Success failed (PCMC signal ≠ 1)"
                elif not current_regulation_success:
                    passed = False
                    if avg_current is not None:
                        error = abs(avg_current - output_current)
                        info = f"Test failed: Output Current Regulation failed (average = {avg_current:.3f}A, expected = {output_current:.3f}A ± {output_current_tolerance:.3f}A, error = {error:.3f}A)"
                    else:
                        info = "Test failed: Output Current Regulation failed (no output current data collected)"
                else:
                    passed = True
                    info = "Test passed: PFC Regulation successful AND PCMC Success AND Output Current Regulation successful AND No fault detected"
                
                # Build detailed info string
                info += f"\nPFC Regulation: {'SUCCESS' if pfc_regulation_success else 'FAIL'}"
                info += f"\nPCMC Success: {'SUCCESS' if pcmc_success else 'FAIL'}"
                info += f"\nOutput Current Regulation: {'SUCCESS' if current_regulation_success else 'FAIL'}"
                if avg_current is not None:
                    error = abs(avg_current - output_current)
                    info += f" (avg = {avg_current:.3f}A, expected = {output_current:.3f}A ± {output_current_tolerance:.3f}A, error = {error:.3f}A)"
                info += f"\nFault Detected: {'YES' if fault_detected else 'NO'}"
                if final_dut_state is not None:
                    info += f"\nFinal DUT Test State: {final_dut_state} (expected: {trigger_value})"
                info += f"\nTotal data points logged: {len(logged_data)}"
                
                # Store results for display
                test_name = test.get('name', '<unnamed>')
                result_data = {
                    'pfc_regulation_success': pfc_regulation_success,
                    'pcmc_success': pcmc_success,
                    'current_regulation_success': current_regulation_success,
                    'avg_output_current': avg_current,
                    'output_current_error': abs(avg_current - output_current) if avg_current is not None else None,
                    'fault_detected': fault_detected,
                    'final_dut_state': final_dut_state,
                    'trigger_value': trigger_value,
                    'trim_value_used': trim_value,
                    'logged_data': logged_data,
                    'passed': passed
                }
                
                # Store in temporary storage for retrieval by _on_test_finished
                if self.gui is not None:
                    if not hasattr(self.gui, '_test_result_data_temp'):
                        self.gui._test_result_data_temp = {}
                    self.gui._test_result_data_temp[test_name] = result_data
                
                logger.info(f"Charger Functional Test completed: {'PASS' if passed else 'FAIL'}")
                return passed, info
            elif act.get('type') == 'Phase Offset Calibration Test':
                # Phase Offset Calibration Test execution:
                # 1) Send Test Mode (e.g. 1 = Drive Mode) via EOL Set DUT Test Mode Signal (shared Test Mode field)
                # 2) Sample Phase V / Phase W offset signals for acquisition time (default 5s)
                # 3) Check both final offsets against lower/upper limits
                # 4) PASS if both within limits, otherwise FAIL
                test_mode = test.get('test_mode', 1)
                feedback_signal_source = act.get('feedback_signal_source')
                phase_v_offset_signal = act.get('phase_v_offset_signal')
                phase_w_offset_signal = act.get('phase_w_offset_signal')
                lower_limit = act.get('phase_offset_lower_limit')
                upper_limit = act.get('phase_offset_upper_limit')
                calibration_timeout_ms = act.get('calibration_timeout_ms', 5000)
                if calibration_timeout_ms is None:
                    calibration_timeout_ms = 5000
                calibration_timeout_sec = max(1.0, calibration_timeout_ms / 1000.0)
                if not all([feedback_signal_source is not None, phase_v_offset_signal, phase_w_offset_signal,
                            lower_limit is not None, upper_limit is not None]):
                    return False, "Missing required Phase Offset Calibration Test parameters"
                try:
                    lower_limit = float(lower_limit)
                    upper_limit = float(upper_limit)
                except (ValueError, TypeError):
                    return False, "Phase Offset Calibration Test: Invalid offset limits"
                if lower_limit > upper_limit:
                    return False, "Phase Offset Calibration Test: Offset lower limit must be <= upper limit"
                def _nb_sleep(sec: float) -> None:
                    end = time.time() + float(sec)
                    while time.time() < end:
                        remaining = end - time.time()
                        if remaining <= 0:
                            break
                        time.sleep(min(SLEEP_INTERVAL_SHORT, remaining))
                # Send Test Mode (e.g. 1 = Drive Mode) using EOL HW config -> Set DUT Test Mode Signal
                send_ok, send_msg = self.send_test_mode_command(test_mode)
                if not send_ok:
                    return False, f"Phase Offset Calibration Test: {send_msg}"
                logger.info(f"Phase Offset Calibration Test: Sent Test Mode {test_mode} (Drive Mode)")
                start_t = time.time()
                deadline = start_t + calibration_timeout_sec
                pv = None
                pw = None
                pv_samples = 0
                pw_samples = 0
                while time.time() < deadline:
                    try:
                        if self.signal_service is not None:
                            _, pv_val = self.signal_service.get_latest_signal(feedback_signal_source, phase_v_offset_signal)
                            _, pw_val = self.signal_service.get_latest_signal(feedback_signal_source, phase_w_offset_signal)
                        elif self.gui is not None:
                            _, pv_val = self.gui.get_latest_signal(feedback_signal_source, phase_v_offset_signal)
                            _, pw_val = self.gui.get_latest_signal(feedback_signal_source, phase_w_offset_signal)
                        else:
                            pv_val = None
                            pw_val = None
                        if pv_val is not None:
                            try:
                                pv = float(pv_val)
                                pv_samples += 1
                            except (ValueError, TypeError):
                                pass
                        if pw_val is not None:
                            try:
                                pw = float(pw_val)
                                pw_samples += 1
                            except (ValueError, TypeError):
                                pass

                        # Real-time monitoring updates during acquisition
                        if self.monitor_signal_update_callback:
                            try:
                                if pv is not None:
                                    self.update_monitor_signal('phase_v_offset', pv)
                                if pw is not None:
                                    self.update_monitor_signal('phase_w_offset', pw)
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"Phase Offset Calibration Test: sample error: {e}")
                    _nb_sleep(SLEEP_INTERVAL_SHORT)

                if pv is None or pw is None:
                    return False, f"Phase Offset Calibration Test: No valid offset readings (V samples={pv_samples}, W samples={pw_samples})"

                pv_ok = (lower_limit <= pv <= upper_limit)
                pw_ok = (lower_limit <= pw <= upper_limit)
                passed = bool(pv_ok and pw_ok)
                info = (f"Phase offsets after {int(calibration_timeout_ms)} ms: "
                        f"V={pv} ({'OK' if pv_ok else 'OUT'}), "
                        f"W={pw} ({'OK' if pw_ok else 'OUT'}), "
                        f"Limits=[{lower_limit}, {upper_limit}]")

                # Store result data for report/statistics
                test_name = test.get('name', '<unnamed>')
                result_data = {
                    'phase_v_offset': pv,
                    'phase_w_offset': pw,
                    'lower_limit': lower_limit,
                    'upper_limit': upper_limit,
                    'acquisition_time_ms': int(calibration_timeout_ms),
                    'passed': passed
                }
                if self.gui is not None:
                    if not hasattr(self.gui, '_test_result_data_temp'):
                        self.gui._test_result_data_temp = {}
                    self.gui._test_result_data_temp[test_name] = result_data

                if self.monitor_signal_update_callback:
                    try:
                        if pv is not None:
                            self.update_monitor_signal('phase_v_offset', pv)
                        if pw is not None:
                            self.update_monitor_signal('phase_w_offset', pw)
                    except Exception:
                        pass
                logger.info(f"Phase Offset Calibration Test completed: {'PASS' if passed else 'FAIL'}. {info}")
                return passed, info
            elif act.get('type') == 'Output Current Calibration':
                # Output Current Calibration Test execution:
                # 0) Pre-Test Safety Dialog - MUST be shown BEFORE any test execution
                # 1) Verify oscilloscope setup (TDIV, TRA, probe attenuation)
                # 2) Generate current setpoints array
                # 3) Initialize trim value at DUT
                # 4) Send initial current setpoint (first from array)
                # 5) Trigger test at DUT
                # 6) Collect data for first setpoint (wait, acquire, collect, analyze)
                # 7) For each remaining setpoint (starting from second):
                #    a. Send current setpoint
                #    b. Wait pre-acquisition time
                #    c. Start CAN logging and oscilloscope acquisition
                #    d. Collect data during acquisition time
                #    e. Stop data collection
                #    f. Calculate averages and update plot
                # 8) Disable test mode
                # 9) Calculate gain error and adjustment factor (point-by-point method, same as Phase Current Test)
                # 10) Determine pass/fail
                
                # Step 0: Pre-Test Safety Dialog - MUST be shown BEFORE any test execution
                # Must be shown in main GUI thread (Qt requirement)
                logger.info("Output Current Calibration Test: Showing pre-test safety dialog BEFORE test execution...")
                dialog_result = None
                
                if self.gui is None:
                    logger.error("Output Current Calibration Test: GUI is None, cannot show safety dialog")
                    return False, "Test sequence paused: Cannot show safety dialog (GUI not available). Please ensure hardware connections are ready and resume the test sequence."
                
                if self.gui is not None:
                    try:
                        from PySide6 import QtCore
                        from PySide6.QtWidgets import QMessageBox
                        
                        # Check if we're in the main thread
                        current_thread = QtCore.QThread.currentThread()
                        main_thread = QtCore.QCoreApplication.instance().thread()
                        
                        if current_thread == main_thread:
                            # We're in the main thread, show dialog directly
                            self.gui._show_output_current_calibration_safety_dialog()
                            dialog_result = getattr(self.gui, '_output_current_calibration_dialog_result', QMessageBox.No)
                        else:
                            # We're in a background thread, use BlockingQueuedConnection
                            # This will block the background thread until the dialog method returns
                            # Initialize result attribute if not present
                            if not hasattr(self.gui, '_output_current_calibration_dialog_result'):
                                self.gui._output_current_calibration_dialog_result = None
                            
                            # Clear previous result
                            self.gui._output_current_calibration_dialog_result = None
                            
                            # Invoke dialog in main thread using BlockingQueuedConnection
                            # This blocks until the method completes
                            success = QtCore.QMetaObject.invokeMethod(
                                self.gui,
                                '_show_output_current_calibration_safety_dialog',
                                QtCore.Qt.ConnectionType.BlockingQueuedConnection
                            )
                            
                            if success:
                                # After BlockingQueuedConnection returns, the method has completed
                                # Get the result that was stored
                                dialog_result = getattr(self.gui, '_output_current_calibration_dialog_result', QMessageBox.No)
                                if dialog_result is None:
                                    logger.warning("Dialog result is None, defaulting to No")
                                    dialog_result = QMessageBox.No
                            else:
                                logger.warning("Failed to invoke dialog method, defaulting to No")
                                dialog_result = QMessageBox.No
                        
                        if dialog_result == QMessageBox.No:
                            # Request pause of test sequence - test will NOT execute
                            logger.info("Output Current Calibration Test: User declined safety check, pausing test sequence (test will not execute)")
                            
                            # Request pause safely from main thread using QMetaObject.invokeMethod
                            # This avoids threading issues that can cause segfaults
                            if self.gui is not None:
                                try:
                                    # Check if we're in the main thread
                                    current_thread = QtCore.QThread.currentThread()
                                    main_thread = QtCore.QCoreApplication.instance().thread()
                                    
                                    if current_thread == main_thread:
                                        # We're in the main thread, call directly
                                        if hasattr(self.gui, '_request_test_sequence_pause'):
                                            self.gui._request_test_sequence_pause()
                                    else:
                                        # We're in a background thread, use QueuedConnection (non-blocking)
                                        QtCore.QMetaObject.invokeMethod(
                                            self.gui,
                                            '_request_test_sequence_pause',
                                            QtCore.Qt.ConnectionType.QueuedConnection
                                        )
                                    logger.info("Output Current Calibration Test: Pause requested on test execution thread")
                                except Exception as e:
                                    logger.warning(f"Failed to request pause on test execution thread: {e}")
                            
                            return False, "Test sequence paused: User declined safety check. Please ensure hardware connections are ready and resume the test sequence."
                    except Exception as e:
                        logger.error(f"Failed to show pre-test safety dialog: {e}", exc_info=True)
                        # On error, default to No (don't execute test if we can't show dialog)
                        logger.warning("Dialog error - defaulting to No (test will not execute)")
                        return False, "Test sequence paused: Failed to show safety dialog. Please ensure hardware connections are ready and resume the test sequence."
                
                # If we reach here, user pressed Yes - continue with test execution
                logger.info("Output Current Calibration Test: User confirmed safety check, proceeding with test execution...")
                
                # Extract parameters
                test_trigger_source = act.get('test_trigger_source')
                test_trigger_signal = act.get('test_trigger_signal')
                test_trigger_signal_value = act.get('test_trigger_signal_value')
                current_setpoint_signal = act.get('current_setpoint_signal')
                output_current_trim_signal = act.get('output_current_trim_signal')
                initial_trim_value = act.get('initial_trim_value')
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
                           current_setpoint_signal, output_current_trim_signal, initial_trim_value is not None,
                           feedback_msg_id, feedback_signal, osc_channel_name, osc_timebase]):
                    return False, "Missing required Output Current Calibration Test parameters"
                
                if not (0 <= test_trigger_signal_value <= 255):
                    return False, f"Test trigger signal value must be in range 0-255, got {test_trigger_signal_value}"
                
                try:
                    initial_trim_float = float(initial_trim_value)
                    if not (0.0 <= initial_trim_float <= 200.0):
                        return False, f"Initial trim value must be in range 0.0000-200.0000%, got {initial_trim_float}"
                except (ValueError, TypeError):
                    return False, f"Initial trim value must be a number, got {initial_trim_value}"
                
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
                
                # Validate setpoint array
                if len(current_setpoints) > 100:
                    logger.warning(f"Output Current Calibration: Generated {len(current_setpoints)} setpoints, which is very large. Test may take a long time.")
                if len(current_setpoints) < 2:
                    return False, f"Output Current Calibration: Need at least 2 setpoints for calibration, got {len(current_setpoints)}. Check minimum, maximum, and step current values."
                
                # Validate setpoint range
                if min(current_setpoints) < 0 or max(current_setpoints) > 50:
                    logger.warning(f"Output Current Calibration: Setpoint range ({min(current_setpoints)}A to {max(current_setpoints)}A) is outside typical range (0-50A)")
                
                logger.info(f"Generated {len(current_setpoints)} setpoints: {current_setpoints[:10]}{'...' if len(current_setpoints) > 10 else ''}")
                
                # Initialize plot
                if self.plot_clear_callback is not None:
                    self.plot_clear_callback()
                
                # Initialize plot labels and title for Output Current Calibration (thread-safe)
                test_name = test.get('name', '')
                if self.gui is not None and hasattr(self.gui, '_initialize_output_current_plot'):
                    try:
                        current_thread = QtCore.QThread.currentThread()
                        main_thread = QtCore.QCoreApplication.instance().thread()
                        
                        if current_thread == main_thread:
                            # Main thread - call directly
                            self.gui._initialize_output_current_plot(test_name)
                        else:
                            # Background thread - use QueuedConnection
                            QtCore.QMetaObject.invokeMethod(
                                self.gui,
                                '_initialize_output_current_plot',
                                QtCore.Qt.ConnectionType.QueuedConnection,
                                QtCore.Q_ARG(str, test_name)
                            )
                    except Exception as e:
                        logger.debug(f"Failed to initialize Output Current Calibration plot: {e}")
                
                if self.label_update_callback is not None:
                    self.label_update_callback("Output Current Calibration: Initializing...")
                
                # Initialize data storage
                can_averages = []
                osc_averages = []
                setpoint_values = []
                
                # Find message for encoding (used in multiple steps)
                trigger_msg = self.dbc_service.find_message_by_id(test_trigger_source)
                if trigger_msg is None:
                    return False, f"Test trigger message (ID: 0x{test_trigger_source:X}) not found in DBC"
                
                # Helper function to build signal values dict with required signals
                def _build_signal_values_dict(signals_to_set):
                    """Build signal values dict with DeviceID, MessageType, and specified signals."""
                    signal_values = {}
                    all_signals = self.dbc_service.get_message_signals(trigger_msg)
                    signal_names = [sig.name for sig in all_signals]
                    
                    # Include DeviceID if it exists (default to 0)
                    if 'DeviceID' in signal_names:
                        signal_values['DeviceID'] = 0
                    
                    # Determine MessageType from multiplexed signals
                    mux_value = None
                    for sig_name in signals_to_set.keys():
                        for sig in all_signals:
                            if sig.name == sig_name and getattr(sig, 'multiplexer_ids', None):
                                mux_value = sig.multiplexer_ids[0]
                                break
                        if mux_value is not None:
                            break
                    
                    # Only set MessageType if signal is actually multiplexed
                    if mux_value is not None:
                        signal_values['MessageType'] = mux_value
                    elif 'MessageType' in signal_names:
                        # If MessageType exists but signal is not multiplexed, use default 0
                        signal_values['MessageType'] = 0
                    
                    # Add the signals we want to set
                    signal_values.update(signals_to_set)
                    return signal_values
                
                # Step 3: Initialize trim value at DUT
                logger.info(f"Initializing trim value at DUT (signal={output_current_trim_signal}, value={initial_trim_value}%)...")
                try:
                    signal_values = _build_signal_values_dict({output_current_trim_signal: float(initial_trim_value)})
                    frame_data = self.dbc_service.encode_message(trigger_msg, signal_values)
                    if AdapterFrame is not None:
                        frame = AdapterFrame(can_id=test_trigger_source, data=frame_data)
                    else:
                        class Frame:
                            def __init__(self, can_id, data):
                                self.can_id = can_id
                                self.data = data
                        frame = Frame(can_id=test_trigger_source, data=frame_data)
                    
                    if not self.can_service.send_frame(frame):
                        return False, "Failed to send trim value initialization message to DUT"
                    
                    logger.info("Trim value initialized successfully")
                    _nb_sleep(0.2)  # Small delay
                except Exception as e:
                    return False, f"Failed to initialize trim value: {e}"
                
                # Helper function to disable test mode (used in cleanup)
                def _disable_test_mode():
                    """Disable test mode at DUT."""
                    try:
                        signal_values = _build_signal_values_dict({test_trigger_signal: 0})  # Disable test mode
                        frame_data = self.dbc_service.encode_message(trigger_msg, signal_values)
                        if AdapterFrame is not None:
                            frame = AdapterFrame(can_id=test_trigger_source, data=frame_data)
                        else:
                            class Frame:
                                def __init__(self, can_id, data):
                                    self.can_id = can_id
                                    self.data = data
                            frame = Frame(can_id=test_trigger_source, data=frame_data)
                        if self.can_service.send_frame(frame):
                            logger.info("Test mode disabled successfully")
                        else:
                            logger.warning("Failed to disable test mode: send_frame returned False")
                    except Exception as e:
                        logger.warning(f"Failed to disable test mode during cleanup: {e}")
                
                # Step 4: Send initial current setpoint (first from array)
                first_setpoint = current_setpoints[0]
                logger.info(f"Sending initial current setpoint: {first_setpoint}A...")
                try:
                    signal_values = _build_signal_values_dict({current_setpoint_signal: first_setpoint})
                    frame_data = self.dbc_service.encode_message(trigger_msg, signal_values)
                    if AdapterFrame is not None:
                        frame = AdapterFrame(can_id=test_trigger_source, data=frame_data)
                    else:
                        class Frame:
                            def __init__(self, can_id, data):
                                self.can_id = can_id
                                self.data = data
                        frame = Frame(can_id=test_trigger_source, data=frame_data)
                    
                    if not self.can_service.send_frame(frame):
                        return False, "Failed to send initial current setpoint message to DUT"
                    
                    # Track sent command value for monitoring (thread-safe)
                    if self.gui is not None and hasattr(self.gui, 'track_sent_command_value'):
                        try:
                            current_thread = QtCore.QThread.currentThread()
                            main_thread = QtCore.QCoreApplication.instance().thread()
                            
                            if current_thread == main_thread:
                                self.gui.track_sent_command_value('output_current_reference', first_setpoint)
                            else:
                                QtCore.QMetaObject.invokeMethod(
                                    self.gui,
                                    'track_sent_command_value',
                                    QtCore.Qt.ConnectionType.QueuedConnection,
                                    QtCore.Q_ARG(str, 'output_current_reference'),
                                    QtCore.Q_ARG(float, first_setpoint)
                                )
                        except Exception:
                            pass
                    
                    logger.info("Initial current setpoint sent successfully")
                    _nb_sleep(0.2)  # Small delay
                except Exception as e:
                    return False, f"Failed to send initial current setpoint: {e}"
                
                # Step 5: Trigger test at DUT
                logger.info(f"Sending test trigger to DUT (signal={test_trigger_signal}, value={test_trigger_signal_value})...")
                try:
                    signal_values = _build_signal_values_dict({test_trigger_signal: test_trigger_signal_value})
                    frame_data = self.dbc_service.encode_message(trigger_msg, signal_values)
                    if AdapterFrame is not None:
                        frame = AdapterFrame(can_id=test_trigger_source, data=frame_data)
                    else:
                        class Frame:
                            def __init__(self, can_id, data):
                                self.can_id = can_id
                                self.data = data
                        frame = Frame(can_id=test_trigger_source, data=frame_data)
                    
                    if not self.can_service.send_frame(frame):
                        return False, "Failed to send test trigger message to DUT"
                    
                    logger.info("Test trigger sent successfully")
                    _nb_sleep(0.2)  # Small delay for DUT to initialize
                except Exception as e:
                    return False, f"Failed to send test trigger: {e}"
                
                # Step 6: Collect data for first setpoint
                test_name = test.get('name', '<unnamed>')
                logger.info(f"Collecting data for first setpoint: {first_setpoint}A")
                
                # 6a. Wait for pre-acquisition time
                logger.info(f"Waiting {pre_acq_ms}ms for current to stabilize...")
                _nb_sleep(pre_acq_ms / 1000.0)
                
                # 6b. Start data acquisition
                logger.info(f"Starting data acquisition for {acq_ms}ms...")
                can_feedback_values = []
                collecting_can_data = True
                
                try:
                    # Start oscilloscope acquisition
                    self.oscilloscope_service.send_command("TRMD AUTO")
                    time.sleep(0.2)
                except Exception as e:
                    logger.warning(f"Failed to start oscilloscope acquisition: {e}, continuing...")
                
                # 6c. Collect data during acquisition time
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
                    
                    time.sleep(SLEEP_INTERVAL_SHORT)
                
                # 6d. Stop data acquisition
                collecting_can_data = False
                logger.info("Stopping data acquisition...")
                try:
                    self.oscilloscope_service.send_command("STOP")
                    time.sleep(0.5)  # Wait for acquisition to stop
                except Exception as e:
                    logger.warning(f"Failed to stop oscilloscope acquisition: {e}")
                
                # 6e. Analyze data and update plot for first setpoint
                if not can_feedback_values:
                    logger.warning(f"No CAN data collected at first setpoint {first_setpoint}A, skipping...")
                else:
                    # Calculate CAN average
                    can_avg = sum(can_feedback_values) / len(can_feedback_values)
                    
                    # Query oscilloscope average
                    time.sleep(0.3)  # Additional delay before querying PAVA
                    osc_avg = self.oscilloscope_service.query_pava_mean(channel_num)
                    if osc_avg is None:
                        logger.warning(f"Failed to obtain oscilloscope average at first setpoint {first_setpoint}A, skipping...")
                    else:
                        # Validate oscilloscope data quality
                        try:
                            osc_avg_float = float(osc_avg)
                            # Validate value is in reasonable range for output current (0-50A typical)
                            if not (0.0 <= abs(osc_avg_float) <= 60.0):
                                logger.warning(f"Output Current Calibration: Oscilloscope average {osc_avg_float}A at setpoint {first_setpoint}A is outside typical range (0-60A)")
                            osc_avg = osc_avg_float
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Output Current Calibration: Oscilloscope returned invalid average value: {osc_avg} (expected numeric value)")
                            osc_avg = None
                        
                        if osc_avg is not None:
                            # Validate CAN average is in reasonable range
                            if not (0.0 <= abs(can_avg) <= 60.0):
                                logger.warning(f"Output Current Calibration: CAN average {can_avg}A at setpoint {first_setpoint}A is outside typical range (0-60A)")
                            
                            # Store data
                            can_averages.append(can_avg)
                            osc_averages.append(osc_avg)
                            setpoint_values.append(first_setpoint)
                        
                        logger.info(f"First setpoint {first_setpoint}A: CAN avg={can_avg:.4f}A, Osc avg={osc_avg:.4f}A")
                        
                        # Update plot
                        if self.plot_update_callback is not None:
                            self.plot_update_callback(osc_avg, can_avg, test_name)
                        
                        if self.label_update_callback is not None:
                            self.label_update_callback(f"Output Current Calibration: Setpoint 1/{len(current_setpoints)} ({first_setpoint}A) - CAN: {can_avg:.3f}A, Osc: {osc_avg:.3f}A")
                
                # Step 7: Iterate through remaining current setpoints (starting from second)
                for setpoint_idx, setpoint in enumerate(current_setpoints[1:], start=1):
                    logger.info(f"Testing setpoint {setpoint_idx + 1}/{len(current_setpoints)}: {setpoint}A")
                    
                    # 7a. Send current setpoint
                    try:
                        signal_values = _build_signal_values_dict({current_setpoint_signal: setpoint})
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
                        
                        # Track sent command value for monitoring (thread-safe)
                        if self.gui is not None and hasattr(self.gui, 'track_sent_command_value'):
                            try:
                                current_thread = QtCore.QThread.currentThread()
                                main_thread = QtCore.QCoreApplication.instance().thread()
                                
                                if current_thread == main_thread:
                                    self.gui.track_sent_command_value('output_current_reference', setpoint)
                                else:
                                    QtCore.QMetaObject.invokeMethod(
                                        self.gui,
                                        'track_sent_command_value',
                                        QtCore.Qt.ConnectionType.QueuedConnection,
                                        QtCore.Q_ARG(str, 'output_current_reference'),
                                        QtCore.Q_ARG(float, setpoint)
                                    )
                            except Exception:
                                pass
                        
                        logger.info(f"Sent current setpoint: {setpoint}A")
                    except Exception as e:
                        logger.warning(f"Failed to send current setpoint {setpoint}A: {e}, continuing...")
                        continue
                    
                    # 7b. Wait for pre-acquisition time
                    logger.info(f"Waiting {pre_acq_ms}ms for current to stabilize...")
                    _nb_sleep(pre_acq_ms / 1000.0)
                    
                    # 7c. Start data acquisition
                    logger.info(f"Starting data acquisition for {acq_ms}ms...")
                    can_feedback_values = []
                    collecting_can_data = True
                    
                    try:
                        # Start oscilloscope acquisition
                        self.oscilloscope_service.send_command("TRMD AUTO")
                        time.sleep(0.2)
                    except Exception as e:
                        logger.warning(f"Failed to start oscilloscope acquisition: {e}, continuing...")
                    
                    # 7d. Collect data during acquisition time
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
                        
                        time.sleep(SLEEP_INTERVAL_SHORT)
                    
                    # 7e. Stop data acquisition
                    collecting_can_data = False
                    logger.info("Stopping data acquisition...")
                    try:
                        self.oscilloscope_service.send_command("STOP")
                        time.sleep(0.5)  # Wait for acquisition to stop
                    except Exception as e:
                        logger.warning(f"Failed to stop oscilloscope acquisition: {e}")
                    
                    # 7f. Analyze data and update plot
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
                    
                    # Validate oscilloscope data quality
                    try:
                        osc_avg_float = float(osc_avg)
                        # Validate value is in reasonable range for output current (0-50A typical)
                        if not (0.0 <= abs(osc_avg_float) <= 60.0):
                            logger.warning(f"Output Current Calibration: Oscilloscope average {osc_avg_float}A at setpoint {setpoint}A is outside typical range (0-60A)")
                        osc_avg = osc_avg_float
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Output Current Calibration: Oscilloscope returned invalid average value at setpoint {setpoint}A: {osc_avg} (expected numeric value)")
                        continue
                    
                    # Validate CAN average is in reasonable range
                    if not (0.0 <= abs(can_avg) <= 60.0):
                        logger.warning(f"Output Current Calibration: CAN average {can_avg}A at setpoint {setpoint}A is outside typical range (0-60A)")
                    
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
                
                # Step 8: Disable test mode (end of first sweep)
                logger.info("Disabling test mode at DUT (end of first sweep)...")
                try:
                    _disable_test_mode()
                except Exception as e:
                    logger.warning(f"Failed to disable test mode at end of first sweep: {e}")
                
                # Step 9: First Sweep Post-Analysis - Calculate gain error and adjustment factor (point-by-point method, same as Phase Current Test)
                if len(can_averages) < 2:
                    return False, f"Insufficient data points collected in first sweep. Need at least 2 setpoints, got {len(can_averages)}. Check CAN connection and signal configuration."
                
                logger.info(f"First Sweep: Calculating gain error and adjustment factor using point-by-point method on {len(can_averages)} data points...")
                
                # Calculate gain error and correction factor for each point (same as Phase Current Test)
                gain_errors = []
                gain_corrections = []
                
                for osc_avg, can_avg in zip(osc_averages, can_averages):
                    if osc_avg is not None and can_avg is not None and abs(osc_avg) > 1e-10:
                        # Calculate gain error: ((can - osc) / osc) * 100.0
                        gain_error = ((can_avg - osc_avg) / osc_avg) * 100.0
                        gain_errors.append(gain_error)
                        
                        # Calculate correction factor: osc / can
                        if abs(can_avg) > 1e-10:
                            gain_correction = osc_avg / can_avg
                            gain_corrections.append(gain_correction)
                        else:
                            gain_corrections.append(float('nan'))
                    else:
                        gain_errors.append(float('nan'))
                        gain_corrections.append(float('nan'))
                
                # Filter out invalid values (NaN, Inf)
                valid_errors = [e for e in gain_errors if not (isinstance(e, float) and (e != e or abs(e) == float('inf')))]
                valid_corrections = [c for c in gain_corrections if not (isinstance(c, float) and (c != c or abs(c) == float('inf')))]
                
                if len(valid_errors) < 1:
                    return False, "Insufficient valid data points for calculation in first sweep. Need at least 1 valid data point. Check data quality and ensure oscilloscope and CAN measurements are valid."
                
                # Calculate average gain error and average correction factor (same as Phase Current Test)
                first_sweep_gain_error = sum(valid_errors) / len(valid_errors) if valid_errors else None
                first_sweep_gain_adjustment_factor = sum(valid_corrections) / len(valid_corrections) if valid_corrections else None
                
                if first_sweep_gain_adjustment_factor is None:
                    return False, "Failed to calculate adjustment factor: no valid correction factors. Check first sweep data quality."
                
                # Validate adjustment factor is reasonable (typically 0.5 to 2.0, which corresponds to 50% to 200% trim)
                if not (0.5 <= abs(first_sweep_gain_adjustment_factor) <= 2.0):
                    logger.warning(f"Output Current Calibration: Adjustment factor {first_sweep_gain_adjustment_factor:.6f} is outside typical range (0.5-2.0), may indicate data quality issues")
                
                # Calculate trim value for second sweep: calculated_trim_value = 100 * gain_adjustment_factor
                calculated_trim_value = 100.0 * first_sweep_gain_adjustment_factor
                
                # Validate calculated trim value
                if not (0.0 <= calculated_trim_value <= 200.0):
                    return False, f"Calculated trim value ({calculated_trim_value:.4f}%) is out of valid range (0.0000-200.0000%). Check first sweep data quality."
                
                # For backward compatibility, calculate slope and intercept from linear regression (for display purposes only)
                # Filter out invalid data points for linear regression
                valid_osc_values = []
                valid_can_values = []
                for osc_avg, can_avg in zip(osc_averages, can_averages):
                    if (osc_avg is not None and can_avg is not None and 
                        isinstance(osc_avg, (int, float)) and isinstance(can_avg, (int, float)) and
                        not (isinstance(osc_avg, float) and (osc_avg != osc_avg or abs(osc_avg) == float('inf'))) and
                        not (isinstance(can_avg, float) and (can_avg != can_avg or abs(can_avg) == float('inf')))):
                        valid_osc_values.append(float(osc_avg))
                        valid_can_values.append(float(can_avg))
                
                first_sweep_slope = None
                first_sweep_intercept = None
                if len(valid_osc_values) >= 2:
                    try:
                        n = len(valid_osc_values)
                        sum_x = sum(valid_osc_values)
                        sum_y = sum(valid_can_values)
                        sum_xy = sum(x * y for x, y in zip(valid_osc_values, valid_can_values))
                        sum_x2 = sum(x * x for x in valid_osc_values)
                        
                        denominator = n * sum_x2 - sum_x * sum_x
                        if abs(denominator) >= 1e-10:
                            first_sweep_slope = (n * sum_xy - sum_x * sum_y) / denominator
                            first_sweep_intercept = (sum_y - first_sweep_slope * sum_x) / n
                    except Exception:
                        pass  # Keep slope and intercept as None if calculation fails
                
                logger.info(f"First Sweep Point-by-Point Results: Average Gain Error={first_sweep_gain_error:.4f}%, Average Adjustment Factor={first_sweep_gain_adjustment_factor:.6f}, Calculated Trim Value={calculated_trim_value:.4f}%")
                if first_sweep_slope is not None:
                    logger.info(f"First Sweep Linear Regression (for reference): Slope={first_sweep_slope:.6f}, Intercept={first_sweep_intercept:.6f}A")
                
                # Store first sweep plot data with label
                first_sweep_plot_label = f"First Sweep (Trim Value: {initial_trim_value}%)"
                if self.gui is not None:
                    if not hasattr(self.gui, '_test_plot_data_temp'):
                        self.gui._test_plot_data_temp = {}
                    if test_name not in self.gui._test_plot_data_temp:
                        self.gui._test_plot_data_temp[test_name] = {}
                    self.gui._test_plot_data_temp[test_name]['first_sweep'] = {
                        'osc_averages': list(osc_averages),
                        'can_averages': list(can_averages),
                        'setpoint_values': list(setpoint_values),
                        'slope': first_sweep_slope,  # For reference only (linear regression)
                        'intercept': first_sweep_intercept,  # For reference only (linear regression)
                        'gain_error': first_sweep_gain_error,  # Average gain error (point-by-point method)
                        'avg_gain_error': first_sweep_gain_error,  # Same as gain_error for consistency
                        'adjustment_factor': first_sweep_gain_adjustment_factor,  # Average adjustment factor (point-by-point method)
                        'trim_value': initial_trim_value,
                        'plot_label': first_sweep_plot_label
                    }
                
                # ========== SECOND SWEEP STARTS HERE ==========
                logger.info(f"Starting Second Sweep with calculated trim value: {calculated_trim_value:.4f}%")
                
                # Clear plot before second sweep
                if self.plot_clear_callback is not None:
                    self.plot_clear_callback()
                    logger.info("Plot cleared for second sweep")
                
                # Re-initialize plot for second sweep (thread-safe)
                if self.gui is not None and hasattr(self.gui, '_initialize_output_current_plot'):
                    try:
                        current_thread = QtCore.QThread.currentThread()
                        main_thread = QtCore.QCoreApplication.instance().thread()
                        
                        if current_thread == main_thread:
                            # Main thread - call directly
                            self.gui._initialize_output_current_plot(test_name)
                        else:
                            # Background thread - use QueuedConnection
                            QtCore.QMetaObject.invokeMethod(
                                self.gui,
                                '_initialize_output_current_plot',
                                QtCore.Qt.ConnectionType.QueuedConnection,
                                QtCore.Q_ARG(str, test_name)
                            )
                    except Exception as e:
                        logger.debug(f"Failed to initialize Output Current Calibration plot for second sweep: {e}")
                
                if self.label_update_callback is not None:
                    self.label_update_callback(f"Output Current Calibration: Starting Second Sweep (Trim: {calculated_trim_value:.4f}%)...")
                
                # Initialize data storage for second sweep
                second_can_averages = []
                second_osc_averages = []
                second_setpoint_values = []
                
                # Step 10: Initialize Second Sweep with Calculated Trim Value
                logger.info(f"Second Sweep: Initializing trim value at DUT (signal={output_current_trim_signal}, value={calculated_trim_value}%)...")
                try:
                    signal_values = _build_signal_values_dict({output_current_trim_signal: float(calculated_trim_value)})
                    frame_data = self.dbc_service.encode_message(trigger_msg, signal_values)
                    if AdapterFrame is not None:
                        frame = AdapterFrame(can_id=test_trigger_source, data=frame_data)
                    else:
                        class Frame:
                            def __init__(self, can_id, data):
                                self.can_id = can_id
                                self.data = data
                        frame = Frame(can_id=test_trigger_source, data=frame_data)
                    
                    if not self.can_service.send_frame(frame):
                        return False, "Failed to send calculated trim value initialization message to DUT for second sweep"
                    
                    logger.info("Second Sweep: Trim value initialized successfully")
                    _nb_sleep(0.2)  # Small delay
                except Exception as e:
                    return False, f"Failed to initialize calculated trim value for second sweep: {e}"
                
                # Step 11: Send Initial Current Setpoint for Second Sweep
                first_setpoint = current_setpoints[0]
                logger.info(f"Second Sweep: Sending initial current setpoint: {first_setpoint}A...")
                try:
                    signal_values = _build_signal_values_dict({current_setpoint_signal: first_setpoint})
                    frame_data = self.dbc_service.encode_message(trigger_msg, signal_values)
                    if AdapterFrame is not None:
                        frame = AdapterFrame(can_id=test_trigger_source, data=frame_data)
                    else:
                        class Frame:
                            def __init__(self, can_id, data):
                                self.can_id = can_id
                                self.data = data
                        frame = Frame(can_id=test_trigger_source, data=frame_data)
                    
                    if not self.can_service.send_frame(frame):
                        return False, "Failed to send initial current setpoint message to DUT for second sweep"
                    
                    logger.info("Second Sweep: Initial current setpoint sent successfully")
                    _nb_sleep(0.2)  # Small delay
                except Exception as e:
                    return False, f"Failed to send initial current setpoint for second sweep: {e}"
                
                # Step 12: Trigger Test at DUT for Second Sweep
                logger.info(f"Second Sweep: Sending test trigger to DUT (signal={test_trigger_signal}, value={test_trigger_signal_value})...")
                try:
                    signal_values = _build_signal_values_dict({test_trigger_signal: test_trigger_signal_value})
                    frame_data = self.dbc_service.encode_message(trigger_msg, signal_values)
                    if AdapterFrame is not None:
                        frame = AdapterFrame(can_id=test_trigger_source, data=frame_data)
                    else:
                        class Frame:
                            def __init__(self, can_id, data):
                                self.can_id = can_id
                                self.data = data
                        frame = Frame(can_id=test_trigger_source, data=frame_data)
                    
                    if not self.can_service.send_frame(frame):
                        return False, "Failed to send test trigger message to DUT for second sweep"
                    
                    logger.info("Second Sweep: Test trigger sent successfully")
                    _nb_sleep(0.2)  # Small delay for DUT to initialize
                except Exception as e:
                    return False, f"Failed to send test trigger for second sweep: {e}"
                
                # Step 13: Collect Data for First Setpoint (Second Sweep)
                logger.info(f"Second Sweep: Collecting data for first setpoint: {first_setpoint}A")
                
                # 13a. Wait for pre-acquisition time
                logger.info(f"Second Sweep: Waiting {pre_acq_ms}ms for current to stabilize...")
                _nb_sleep(pre_acq_ms / 1000.0)
                
                # 13b. Start data acquisition
                logger.info(f"Second Sweep: Starting data acquisition for {acq_ms}ms...")
                can_feedback_values = []
                collecting_can_data = True
                
                try:
                    # Start oscilloscope acquisition
                    self.oscilloscope_service.send_command("TRMD AUTO")
                    time.sleep(0.2)
                except Exception as e:
                    logger.warning(f"Failed to start oscilloscope acquisition: {e}, continuing...")
                
                # 13c. Collect data during acquisition time
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
                    
                    time.sleep(SLEEP_INTERVAL_SHORT)
                
                # 13d. Stop data acquisition
                collecting_can_data = False
                logger.info("Second Sweep: Stopping data acquisition...")
                try:
                    self.oscilloscope_service.send_command("STOP")
                    time.sleep(0.5)  # Wait for acquisition to stop
                except Exception as e:
                    logger.warning(f"Failed to stop oscilloscope acquisition: {e}")
                
                # 13e. Analyze data and update plot for first setpoint (second sweep)
                if not can_feedback_values:
                    logger.warning(f"Second Sweep: No CAN data collected at first setpoint {first_setpoint}A, skipping...")
                else:
                    # Calculate CAN average
                    can_avg = sum(can_feedback_values) / len(can_feedback_values)
                    
                    # Query oscilloscope average
                    time.sleep(0.3)  # Additional delay before querying PAVA
                    osc_avg = self.oscilloscope_service.query_pava_mean(channel_num)
                    if osc_avg is None:
                        logger.warning(f"Second Sweep: Failed to obtain oscilloscope average at first setpoint {first_setpoint}A, skipping...")
                    else:
                        # Store data
                        second_can_averages.append(can_avg)
                        second_osc_averages.append(osc_avg)
                        second_setpoint_values.append(first_setpoint)
                        
                        logger.info(f"Second Sweep - First setpoint {first_setpoint}A: CAN avg={can_avg:.4f}A, Osc avg={osc_avg:.4f}A")
                        
                        # Update plot
                        if self.plot_update_callback is not None:
                            self.plot_update_callback(osc_avg, can_avg, test_name)
                        
                        if self.label_update_callback is not None:
                            self.label_update_callback(f"Output Current Calibration (Second Sweep): Setpoint 1/{len(current_setpoints)} ({first_setpoint}A) - CAN: {can_avg:.3f}A, Osc: {osc_avg:.3f}A")
                
                # Step 14: For each remaining current setpoint in the array (second sweep, starting from the second setpoint)
                for setpoint_idx, setpoint in enumerate(current_setpoints[1:], start=1):
                    logger.info(f"Second Sweep: Testing setpoint {setpoint_idx + 1}/{len(current_setpoints)}: {setpoint}A")
                    
                    # 14a. Send current setpoint
                    try:
                        signal_values = _build_signal_values_dict({current_setpoint_signal: setpoint})
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
                            logger.warning(f"Second Sweep: Failed to send current setpoint {setpoint}A, continuing...")
                            continue
                        
                        logger.info(f"Second Sweep: Sent current setpoint: {setpoint}A")
                    except Exception as e:
                        logger.warning(f"Second Sweep: Failed to send current setpoint {setpoint}A: {e}, continuing...")
                        continue
                    
                    # 14b. Wait for pre-acquisition time
                    logger.info(f"Second Sweep: Waiting {pre_acq_ms}ms for current to stabilize...")
                    _nb_sleep(pre_acq_ms / 1000.0)
                    
                    # 14c. Start data acquisition
                    logger.info(f"Second Sweep: Starting data acquisition for {acq_ms}ms...")
                    can_feedback_values = []
                    collecting_can_data = True
                    
                    try:
                        # Start oscilloscope acquisition
                        self.oscilloscope_service.send_command("TRMD AUTO")
                        time.sleep(0.2)
                    except Exception as e:
                        logger.warning(f"Failed to start oscilloscope acquisition: {e}, continuing...")
                    
                    # 14d. Collect data during acquisition time
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
                        
                        time.sleep(SLEEP_INTERVAL_SHORT)
                    
                    # 14e. Stop data acquisition
                    collecting_can_data = False
                    logger.info("Second Sweep: Stopping data acquisition...")
                    try:
                        self.oscilloscope_service.send_command("STOP")
                        time.sleep(0.5)  # Wait for acquisition to stop
                    except Exception as e:
                        logger.warning(f"Failed to stop oscilloscope acquisition: {e}")
                    
                    # 14f. Analyze data and update plot
                    if not can_feedback_values:
                        logger.warning(f"Second Sweep: No CAN data collected at setpoint {setpoint}A, skipping...")
                        continue
                    
                    # Calculate CAN average
                    can_avg = sum(can_feedback_values) / len(can_feedback_values)
                    
                    # Query oscilloscope average
                    time.sleep(0.3)  # Additional delay before querying PAVA
                    osc_avg = self.oscilloscope_service.query_pava_mean(channel_num)
                    if osc_avg is None:
                        logger.warning(f"Second Sweep: Failed to obtain oscilloscope average at setpoint {setpoint}A, skipping...")
                        continue
                    
                    # Validate oscilloscope data quality (same as first sweep)
                    try:
                        osc_avg_float = float(osc_avg)
                        if not (0.0 <= abs(osc_avg_float) <= 60.0):
                            logger.warning(f"Output Current Calibration: Second sweep oscilloscope average {osc_avg_float}A at setpoint {setpoint}A is outside typical range (0-60A)")
                        osc_avg = osc_avg_float
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Output Current Calibration: Second sweep oscilloscope returned invalid average value at setpoint {setpoint}A: {osc_avg} (expected numeric value)")
                        continue
                    
                    # Validate CAN average is in reasonable range
                    if not (0.0 <= abs(can_avg) <= 60.0):
                        logger.warning(f"Output Current Calibration: Second sweep CAN average {can_avg}A at setpoint {setpoint}A is outside typical range (0-60A)")
                    
                    # Store data
                    second_can_averages.append(can_avg)
                    second_osc_averages.append(osc_avg)
                    second_setpoint_values.append(setpoint)
                    
                    logger.info(f"Second Sweep - Setpoint {setpoint}A: CAN avg={can_avg:.4f}A, Osc avg={osc_avg:.4f}A")
                    
                    # Update plot
                    if self.plot_update_callback is not None:
                        self.plot_update_callback(osc_avg, can_avg, test_name)
                    
                    if self.label_update_callback is not None:
                        self.label_update_callback(f"Output Current Calibration (Second Sweep): Setpoint {setpoint_idx + 1}/{len(current_setpoints)} ({setpoint}A) - CAN: {can_avg:.3f}A, Osc: {osc_avg:.3f}A")
                
                # Step 15: Disable test mode (end of second sweep)
                logger.info("Disabling test mode at DUT (end of second sweep)...")
                try:
                    _disable_test_mode()
                except Exception as e:
                    logger.warning(f"Failed to disable test mode at end of second sweep: {e}")
                
                # Step 16: Second Sweep Post-Test Analysis - Calculate gain error (point-by-point method, same as Phase Current Test)
                if len(second_can_averages) < 2:
                    return False, f"Insufficient data points collected in second sweep. Need at least 2 setpoints, got {len(second_can_averages)}. Check CAN connection and signal configuration."
                
                logger.info(f"Second Sweep: Calculating gain error using point-by-point method on {len(second_can_averages)} data points...")
                
                # Calculate gain error for each point (same as Phase Current Test)
                second_sweep_gain_errors = []
                
                for osc_avg, can_avg in zip(second_osc_averages, second_can_averages):
                    if osc_avg is not None and can_avg is not None and abs(osc_avg) > 1e-10:
                        # Calculate gain error: ((can - osc) / osc) * 100.0
                        gain_error = ((can_avg - osc_avg) / osc_avg) * 100.0
                        second_sweep_gain_errors.append(gain_error)
                    else:
                        second_sweep_gain_errors.append(float('nan'))
                
                # Filter out invalid values (NaN, Inf)
                valid_second_errors = [e for e in second_sweep_gain_errors if not (isinstance(e, float) and (e != e or abs(e) == float('inf')))]
                
                if len(valid_second_errors) < 1:
                    return False, "Insufficient valid data points for calculation in second sweep. Need at least 1 valid data point. Check data quality and ensure oscilloscope and CAN measurements are valid."
                
                # Calculate average gain error (same as Phase Current Test)
                second_sweep_gain_error = sum(valid_second_errors) / len(valid_second_errors) if valid_second_errors else None
                
                if second_sweep_gain_error is None:
                    return False, "Failed to calculate gain error: no valid errors. Check second sweep data quality."
                
                # For backward compatibility, calculate slope and intercept from linear regression (for display purposes only)
                valid_second_osc_values = []
                valid_second_can_values = []
                for osc_avg, can_avg in zip(second_osc_averages, second_can_averages):
                    if (osc_avg is not None and can_avg is not None and 
                        isinstance(osc_avg, (int, float)) and isinstance(can_avg, (int, float)) and
                        not (isinstance(osc_avg, float) and (osc_avg != osc_avg or abs(osc_avg) == float('inf'))) and
                        not (isinstance(can_avg, float) and (can_avg != can_avg or abs(can_avg) == float('inf')))):
                        valid_second_osc_values.append(float(osc_avg))
                        valid_second_can_values.append(float(can_avg))
                
                second_sweep_slope = None
                second_sweep_intercept = None
                if len(valid_second_osc_values) >= 2:
                    try:
                        n = len(valid_second_osc_values)
                        sum_x = sum(valid_second_osc_values)
                        sum_y = sum(valid_second_can_values)
                        sum_xy = sum(x * y for x, y in zip(valid_second_osc_values, valid_second_can_values))
                        sum_x2 = sum(x * x for x in valid_second_osc_values)
                        
                        denominator = n * sum_x2 - sum_x * sum_x
                        if abs(denominator) >= 1e-10:
                            second_sweep_slope = (n * sum_xy - sum_x * sum_y) / denominator
                            second_sweep_intercept = (sum_y - second_sweep_slope * sum_x) / n
                    except Exception:
                        pass  # Keep slope and intercept as None if calculation fails
                
                logger.info(f"Second Sweep Point-by-Point Results: Average Gain Error={second_sweep_gain_error:.4f}%")
                if second_sweep_slope is not None:
                    logger.info(f"Second Sweep Linear Regression (for reference): Slope={second_sweep_slope:.6f}, Intercept={second_sweep_intercept:.6f}A")
                
                # Store second sweep plot data with label
                second_sweep_plot_label = f"Second Sweep (Trim Value: {calculated_trim_value:.4f}%)"
                if self.gui is not None:
                    if not hasattr(self.gui, '_test_plot_data_temp'):
                        self.gui._test_plot_data_temp = {}
                    if test_name not in self.gui._test_plot_data_temp:
                        self.gui._test_plot_data_temp[test_name] = {}
                    self.gui._test_plot_data_temp[test_name]['second_sweep'] = {
                        'osc_averages': list(second_osc_averages),
                        'can_averages': list(second_can_averages),
                        'setpoint_values': list(second_setpoint_values),
                        'slope': second_sweep_slope,  # For reference only (linear regression)
                        'intercept': second_sweep_intercept,  # For reference only (linear regression)
                        'gain_error': second_sweep_gain_error,  # Average gain error (point-by-point method)
                        'avg_gain_error': second_sweep_gain_error,  # Same as gain_error for consistency
                        'trim_value': calculated_trim_value,
                        'plot_label': second_sweep_plot_label
                    }
                    # Also store calculated_trim_value and tolerance_percent at top level for easy access
                    self.gui._test_plot_data_temp[test_name]['calculated_trim_value'] = calculated_trim_value
                    self.gui._test_plot_data_temp[test_name]['tolerance_percent'] = tolerance_percent
                
                # Determine pass/fail based on second sweep average gain error (point-by-point method)
                passed = abs(second_sweep_gain_error) <= tolerance_percent
                
                # Build info string with both sweeps' results
                info = f"Output Current Calibration Results:\n\n"
                info += f"First Sweep (Trim Value: {initial_trim_value}%):\n"
                info += f"  Average Gain Error: {first_sweep_gain_error:.4f}%\n"
                info += f"  Average Adjustment Factor: {first_sweep_gain_adjustment_factor:.6f}\n"
                if first_sweep_slope is not None:
                    info += f"  Linear Regression (reference): Slope={first_sweep_slope:.6f}, Intercept={first_sweep_intercept:.6f}A\n"
                info += f"  Data Points: {len(can_averages)} (valid: {len(valid_errors)})\n"
                info += f"\nCalculated Trim Value: {calculated_trim_value:.4f}%\n\n"
                info += f"Second Sweep (Trim Value: {calculated_trim_value:.4f}%):\n"
                info += f"  Average Gain Error: {second_sweep_gain_error:.4f}%\n"
                if second_sweep_slope is not None:
                    info += f"  Linear Regression (reference): Slope={second_sweep_slope:.6f}, Intercept={second_sweep_intercept:.6f}A\n"
                info += f"  Data Points: {len(second_can_averages)} (valid: {len(valid_second_errors)})\n"
                info += f"\nTolerance: {tolerance_percent:.4f}%\n"
                info += f"\nFirst Sweep Setpoint Results:\n"
                for i, (sp, can_avg, osc_avg) in enumerate(zip(setpoint_values, can_averages, osc_averages)):
                    info += f"  {sp}A: CAN={can_avg:.4f}A, Osc={osc_avg:.4f}A\n"
                info += f"\nSecond Sweep Setpoint Results:\n"
                for i, (sp, can_avg, osc_avg) in enumerate(zip(second_setpoint_values, second_can_averages, second_osc_averages)):
                    info += f"  {sp}A: CAN={can_avg:.4f}A, Osc={osc_avg:.4f}A\n"
                
                if passed:
                    info += f"\nPASS: Second sweep average gain error {second_sweep_gain_error:.4f}% (point-by-point method) within tolerance {tolerance_percent:.4f}%"
                else:
                    info += f"\nFAIL: Second sweep average gain error {second_sweep_gain_error:.4f}% (point-by-point method) exceeds tolerance {tolerance_percent:.4f}%"
                
                # Store results for display (includes both sweeps)
                result_data = {
                    # First sweep results
                    'first_sweep_slope': first_sweep_slope,
                    'first_sweep_intercept': first_sweep_intercept,
                    'first_sweep_gain_error': first_sweep_gain_error,
                    'first_sweep_gain_adjustment_factor': first_sweep_gain_adjustment_factor,
                    'first_sweep_data_points': len(can_averages),
                    'first_sweep_valid_data_points': len(valid_errors),
                    'first_sweep_setpoint_values': setpoint_values,
                    'first_sweep_can_averages': can_averages,
                    'first_sweep_osc_averages': osc_averages,
                    'initial_trim_value': initial_trim_value,
                    # Calculated trim value
                    'calculated_trim_value': calculated_trim_value,
                    # Second sweep results
                    'second_sweep_slope': second_sweep_slope,
                    'second_sweep_intercept': second_sweep_intercept,
                    'second_sweep_gain_error': second_sweep_gain_error,
                    'second_sweep_data_points': len(second_can_averages),
                    'second_sweep_valid_data_points': len(valid_second_errors),
                    'second_sweep_setpoint_values': second_setpoint_values,
                    'second_sweep_can_averages': second_can_averages,
                    'second_sweep_osc_averages': second_osc_averages,
                    # Overall results
                    'tolerance_percent': tolerance_percent,
                    'oscilloscope_channel': osc_channel_name,
                    'channel_number': channel_num,
                    # Legacy fields for backward compatibility (use second sweep values)
                    'avg_gain_error': abs(second_sweep_gain_error),
                    'adjustment_factor': first_sweep_gain_adjustment_factor,
                    'data_points': len(second_can_averages),
                    'valid_data_points': len(valid_second_errors)
                }
                
                # Plot data is already stored above in _test_plot_data_temp with 'first_sweep' and 'second_sweep' keys
                
                if self.gui is not None:
                    if not hasattr(self.gui, '_test_result_data_temp'):
                        self.gui._test_result_data_temp = {}
                    self.gui._test_result_data_temp[test_name] = result_data
                    
                    # CRITICAL: Immediately process and store statistics in _test_execution_data
                    # This ensures the statistics are available for the next test (e.g., Charged HV Bus Test)
                    # before _on_test_finished processes the signal asynchronously
                    if not hasattr(self.gui, '_test_execution_data'):
                        self.gui._test_execution_data = {}
                    if test_name not in self.gui._test_execution_data:
                        self.gui._test_execution_data[test_name] = {}
                    
                    # Calculate pass/fail status
                    second_sweep_gain_error = result_data.get('second_sweep_gain_error')
                    tolerance_percent = result_data.get('tolerance_percent', 0)
                    passed_status = False
                    if second_sweep_gain_error is not None and tolerance_percent is not None:
                        passed_status = abs(second_sweep_gain_error) <= tolerance_percent
                    
                    # Store statistics immediately so next test can access them
                    self.gui._test_execution_data[test_name]['statistics'] = {
                        # Store both sweeps' data for completeness
                        'first_sweep_slope': result_data.get('first_sweep_slope'),
                        'first_sweep_intercept': result_data.get('first_sweep_intercept'),
                        'first_sweep_gain_error': result_data.get('first_sweep_gain_error'),
                        'first_sweep_gain_adjustment_factor': result_data.get('first_sweep_gain_adjustment_factor'),
                        'second_sweep_slope': result_data.get('second_sweep_slope'),
                        'second_sweep_intercept': result_data.get('second_sweep_intercept'),
                        'second_sweep_gain_error': second_sweep_gain_error,
                        # Legacy fields for backward compatibility
                        'slope': result_data.get('second_sweep_slope'),  # Use second sweep for legacy
                        'intercept': result_data.get('second_sweep_intercept'),  # Use second sweep for legacy
                        'gain_error': second_sweep_gain_error,  # Use second sweep gain error
                        'adjustment_factor': result_data.get('adjustment_factor'),  # First sweep adjustment factor
                        'tolerance_percent': tolerance_percent,
                        'data_points': result_data.get('data_points'),
                        'calculated_trim_value': result_data.get('calculated_trim_value'),
                        'passed': passed_status
                    }
                    # Also set status immediately
                    self.gui._test_execution_data[test_name]['status'] = 'PASS' if passed_status else 'FAIL'
                    logger.info(f"Output Current Calibration: Immediately stored statistics in _test_execution_data for '{test_name}' (adjustment_factor={result_data.get('adjustment_factor')}, passed={passed_status})")
                
                logger.info(f"Output Current Calibration Test completed: {'PASS' if passed else 'FAIL'}")
                
                # Final cleanup: Ensure test mode is disabled (safety net in case earlier disable failed)
                try:
                    _disable_test_mode()
                except Exception as e:
                    logger.debug(f"Output Current Calibration Test: Final cleanup attempt (may have already been disabled): {e}")
                
                return passed, info
            else:
                pass
        except Exception as e:
            return False, f'Failed to send actuation: {e}'

        waited = 0.0
        poll_interval = POLL_INTERVAL_MS / 1000.0  # Convert ms to seconds
        observed_info = 'no feedback'
        while waited < timeout:
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


