"""
Test Execution Service.

This service handles test execution logic without depending on the GUI.
It uses dependency injection for services and callbacks for UI updates.
"""
import time
import logging
from typing import Optional, Tuple, Dict, Any, Callable

logger = logging.getLogger(__name__)

# Import services and utilities
try:
    from host_gui.services import CanService, DbcService, SignalService
    from host_gui.services.phase_current_service import PhaseCurrentTestStateMachine
except ImportError:
    logger.error("Failed to import services for test execution")
    CanService = None
    DbcService = None
    SignalService = None
    PhaseCurrentTestStateMachine = None

# Import constants
try:
    from host_gui.constants import (
        CAN_ID_MIN, CAN_ID_MAX, DWELL_TIME_DEFAULT, DWELL_TIME_MIN,
        SLEEP_INTERVAL_SHORT, MSG_TYPE_SET_RELAY
    )
except ImportError:
    logger.error("Failed to import constants")
    CAN_ID_MIN = 0
    CAN_ID_MAX = 0x1FFFFFFF
    DWELL_TIME_DEFAULT = 100
    DWELL_TIME_MIN = 10
    SLEEP_INTERVAL_SHORT = 0.01
    MSG_TYPE_SET_RELAY = 1

# Import adapter interface
try:
    from backend.adapters.interface import Frame as AdapterFrame
except ImportError:
    AdapterFrame = None


class TestExecutionService:
    """Service for executing tests without GUI dependencies.
    
    This service encapsulates test execution logic and depends only on:
    - Services (CanService, DbcService, SignalService, OscilloscopeService)
    - Callbacks for UI updates (plot updates, label updates)
    - Configuration dictionaries (eol_hw_config, oscilloscope_config)
    
    Attributes:
        can_service: CanService instance for CAN communication
        dbc_service: DbcService instance for DBC operations
        signal_service: SignalService instance for signal decoding
        oscilloscope_service: Optional oscilloscope service
        eol_hw_config: Optional EOL hardware configuration dictionary
        plot_update_callback: Optional callback for plot updates (dac_voltage, feedback_value, test_name)
        plot_clear_callback: Optional callback to clear plots
        label_update_callback: Optional callback to update UI labels (text)
        oscilloscope_init_callback: Optional callback to initialize oscilloscope (test) -> bool
    """
    
    def __init__(
        self,
        can_service: Optional[CanService] = None,
        dbc_service: Optional[DbcService] = None,
        signal_service: Optional[SignalService] = None,
        oscilloscope_service: Optional[Any] = None,
        eol_hw_config: Optional[Dict[str, Any]] = None,
        plot_update_callback: Optional[Callable[[float, float, Optional[str]], None]] = None,
        plot_clear_callback: Optional[Callable[[], None]] = None,
        label_update_callback: Optional[Callable[[str], None]] = None,
        oscilloscope_init_callback: Optional[Callable[[Dict[str, Any]], bool]] = None
    ):
        """Initialize the TestExecutionService.
        
        Args:
            can_service: CanService instance
            dbc_service: DbcService instance
            signal_service: SignalService instance
            oscilloscope_service: Optional oscilloscope service
            eol_hw_config: Optional EOL hardware configuration
            plot_update_callback: Callback for plot updates (dac_voltage, feedback_value, test_name)
            plot_clear_callback: Callback to clear plots
            label_update_callback: Callback to update UI labels (text)
            oscilloscope_init_callback: Callback to initialize oscilloscope (test) -> bool
        """
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
        """Execute a single test.
        
        Args:
            test: Test configuration dictionary with 'name', 'actuation', etc.
            timeout: Timeout in seconds for feedback waiting
            
        Returns:
            Tuple of (success: bool, info: str)
        """
        # Ensure adapter running
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
            # For now, we'll need to pass a GUI-like object or refactor PhaseCurrentTestStateMachine
            try:
                # Create a minimal GUI-like object for PhaseCurrentTestStateMachine
                # This is a temporary solution until PhaseCurrentTestStateMachine is fully decoupled
                gui_proxy = self._create_gui_proxy()
                state_machine = PhaseCurrentTestStateMachine(gui_proxy, test)
                
                try:
                    success, info = state_machine.run()
                    return success, info
                finally:
                    # Clean up state machine reference if stored
                    pass
            except Exception as e:
                logger.error(f"Phase current test execution failed: {e}", exc_info=True)
                return False, f"Phase current test error: {e}"
        
        try:
            if act.get('type') == 'Digital Logic Test' and act.get('can_id') is not None:
                return self._run_digital_test(test, timeout)
            elif act.get('type') == 'Analog Sweep Test':
                return self._run_analog_test(test, timeout)
            elif act.get('type') == 'Analog Static Test':
                return self._run_analog_static_test(test, timeout)
            elif act.get('type') == 'Temperature Validation Test':
                # Temperature Validation Test uses the same execution logic as in test_runner
                # For now, delegate to test_runner or implement here
                # Since TestExecutionService is meant to be decoupled, we'll note this needs implementation
                logger.warning("Temperature Validation Test execution not fully implemented in TestExecutionService")
                return False, "Temperature Validation Test execution not yet implemented in TestExecutionService"
            else:
                logger.error(f"Unknown test type: {act.get('type')}")
                return False, f"Unknown test type: {act.get('type')}"
        except Exception as e:
            logger.error(f"Test execution failed: {e}", exc_info=True)
            return False, f"Test execution error: {e}"
    
    def _create_gui_proxy(self) -> Any:
        """Create a minimal GUI proxy object for PhaseCurrentTestStateMachine.
        
        This is a temporary solution until PhaseCurrentTestStateMachine is fully decoupled.
        The proxy provides the minimal interface needed by PhaseCurrentTestStateMachine.
        
        Returns:
            Proxy object with services and callbacks
        """
        class GUIProxy:
            def __init__(self, service: 'TestExecutionService'):
                self.service = service
                self.oscilloscope_service = service.oscilloscope_service
                self.can_service = service.can_service
                self.dbc_service = service.dbc_service
                self.signal_service = service.signal_service
                self._oscilloscope_config = getattr(service, '_oscilloscope_config', None)
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
                if self.service.signal_service:
                    return self.service.signal_service.get_latest_signal(can_id, signal_name)
                return None, None
        
        return GUIProxy(self)
    
    def _run_digital_test(self, test: Dict[str, Any], timeout: float) -> Tuple[bool, str]:
        """Execute a digital test.
        
        Args:
            test: Test configuration dictionary
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (success: bool, info: str)
        """
        act = test.get('actuation', {})
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
        
        # Helper functions
        def _encode_value_to_bytes(v: Any) -> bytes:
            """Encode value to bytes using DBC if available."""
            dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded())
            if dbc_available and sig:
                msg = self.dbc_service.find_message_by_id(can_id)
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
                    except Exception as e:
                        logger.debug(f"Failed to encode via DBC: {e}")
            # Fallback raw encoding
            try:
                if isinstance(v, str) and v.startswith('0x'):
                    return bytes.fromhex(v[2:])
                else:
                    ival = int(v)
                    return bytes([ival & 0xFF])
            except Exception:
                return b''
        
        def _send_bytes(data_bytes: bytes) -> None:
            """Send bytes via CAN service."""
            if AdapterFrame is not None:
                f = AdapterFrame(can_id=can_id, data=data_bytes, timestamp=time.time())
            else:
                class F:
                    pass
                f = F()
                f.can_id = can_id
                f.data = data_bytes
                f.timestamp = time.time()
            
            if self.can_service is not None and self.can_service.is_connected():
                self.can_service.send_frame(f)
                # Handle loopback if supported
                if hasattr(self.can_service.adapter, 'loopback'):
                    try:
                        self.can_service.adapter.loopback(f)
                    except Exception as e:
                        logger.debug(f"Loopback not supported or failed: {e}")
        
        def _wait_for_value(expected: Any, duration_ms: int) -> bool:
            """Wait for signal value to match expected."""
            fb = test.get('feedback_signal')
            fb_mid = test.get('feedback_message_id')
            if not fb or not fb_mid:
                time.sleep(duration_ms / 1000.0)
                return True
            
            end = time.time() + (duration_ms / 1000.0)
            while time.time() < end:
                try:
                    if self.signal_service is not None:
                        ts, val = self.signal_service.get_latest_signal(fb_mid, fb)
                    else:
                        ts, val = (None, None)
                    
                    now = time.time()
                    if val is not None:
                        try:
                            if isinstance(expected, (int, float)) and isinstance(val, (int, float)):
                                is_match = (abs(float(val) - float(expected)) < 0.01)
                            else:
                                is_match = (str(val) == str(expected))
                        except Exception:
                            is_match = (str(val) == str(expected))
                        
                        if is_match:
                            return True
                except Exception as e:
                    logger.debug(f"Error checking signal value: {e}")
                
                remaining = end - time.time()
                if remaining <= 0:
                    break
                time.sleep(min(SLEEP_INTERVAL_SHORT, remaining))
            
            return False
        
        # Execute test: set low, wait, set high, wait
        ok = False
        try:
            if low_val is not None:
                low_bytes = _encode_value_to_bytes(low_val)
                _send_bytes(low_bytes)
                low_ok = _wait_for_value(low_val, dwell_ms)
            else:
                low_ok = True
            
            if high_val is not None:
                high_bytes = _encode_value_to_bytes(high_val)
                _send_bytes(high_bytes)
                high_ok = _wait_for_value(high_val, dwell_ms)
            else:
                high_ok = True
            
            ok = bool(low_ok and high_ok)
        except Exception as e:
            logger.error(f"Digital test execution error: {e}", exc_info=True)
            return False, f"Digital test error: {e}"
        
        success = ok
        info = f"Digital test: low={low_val}, high={high_val}, dwell={dwell_ms}ms"
        return success, info
    
    def _run_analog_test(self, test: Dict[str, Any], timeout: float) -> Tuple[bool, str]:
        """Execute an analog test.
        
        Args:
            test: Test configuration dictionary
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (success: bool, info: str)
        """
        # This is a simplified version - full implementation would mirror TestRunner._run_analog_test
        # For now, return a placeholder
        logger.warning("Analog test execution not fully implemented in TestExecutionService")
        return False, "Analog test execution not yet implemented in TestExecutionService"
    
    def _run_analog_static_test(self, test: Dict[str, Any], timeout: float) -> Tuple[bool, str]:
        """Execute an analog static test.
        
        Args:
            test: Test configuration dictionary
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (success: bool, info: str)
        """
        # This is a simplified version - full implementation would mirror TestRunner._run_analog_static_test
        # For now, return a placeholder
        logger.warning("Analog static test execution not fully implemented in TestExecutionService")
        return False, "Analog static test execution not yet implemented in TestExecutionService"

