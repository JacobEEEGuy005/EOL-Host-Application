"""
EOL Host GUI - PySide6-based application for End of Line testing of IPC (Integrated Power Converter).

This module provides a GUI interface for:
- Connecting to CAN bus adapters (PCAN, SocketCAN, Canalystii, SimAdapter)
- Loading and managing DBC (Database CAN) files for signal decoding
- Configuring and executing test sequences (digital and analog tests)
- Real-time monitoring of CAN frames and decoded signals
- Visualizing test results with live plots (Feedback vs DAC Voltage for analog tests)

Key Components:
- BaseGUI: Main application window with tabs for CAN data, test configurator, and test status
- TestRunner: Encapsulates test execution logic (can be moved to background thread)
- AdapterWorker: Background thread for receiving CAN frames

Test Types:
- Digital: Apply High/Low voltage to inputs, verify IPC feedback (1/0)
- Analog: Step DAC voltage from min to max, monitor IPC feedback signal response

Dependencies:
- PySide6: GUI framework
- cantools: DBC parsing and signal encoding/decoding
- matplotlib: Live plotting (optional)
- python-can: CAN bus abstraction layer (via backend adapters)
"""
import sys
import threading
import json
import queue
import time
import os
import shutil
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

from PySide6 import QtCore, QtGui, QtWidgets
try:
    import matplotlib
    matplotlib.use('QtAgg')  # Use Qt backend for PySide6
    # Try newer backend first (matplotlib 3.5+), fall back to older if needed
    try:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    except ImportError:
        try:
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
        except ImportError:
            raise ImportError("Matplotlib Qt backend not available")
    from matplotlib.figure import Figure
    matplotlib_available = True
except Exception:
    matplotlib = None
    FigureCanvasQTAgg = None
    Figure = None
    matplotlib_available = False
try:
    import cantools
except Exception:
    cantools = None

import logging

# Configure logging for host GUI
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Import constants
try:
    from host_gui.constants import (
        CAN_ID_MIN, CAN_ID_MAX, DAC_VOLTAGE_MIN, DAC_VOLTAGE_MAX,
        CAN_FRAME_MAX_LENGTH, DWELL_TIME_DEFAULT, DWELL_TIME_MIN,
        POLL_INTERVAL_MS, FRAME_POLL_INTERVAL_MS,
        MAX_MESSAGES_DEFAULT, MAX_FRAMES_DEFAULT,
        MSG_TYPE_SET_RELAY, MSG_TYPE_SET_DAC, MSG_TYPE_SET_MUX,
        CAN_BITRATE_DEFAULT, CAN_CHANNEL_DEFAULT,
        WINDOW_WIDTH_DEFAULT, WINDOW_HEIGHT_DEFAULT,
        SLEEP_INTERVAL_SHORT, SLEEP_INTERVAL_MEDIUM,
        MUX_CHANNEL_MAX, DWELL_TIME_MAX_MS,
        LEFT_PANEL_MIN_WIDTH, LOGO_WIDTH, LOGO_HEIGHT,
        PLOT_GRID_ALPHA
    )
except ImportError:
    # Fallback constants if import fails
    CAN_ID_MIN = 0
    CAN_ID_MAX = 0x1FFFFFFF
    DAC_VOLTAGE_MIN = 0
    DAC_VOLTAGE_MAX = 5000
    CAN_FRAME_MAX_LENGTH = 8
    DWELL_TIME_DEFAULT = 100
    DWELL_TIME_MIN = 100
    POLL_INTERVAL_MS = 50
    FRAME_POLL_INTERVAL_MS = 150
    MAX_MESSAGES_DEFAULT = 50
    MAX_FRAMES_DEFAULT = 50
    MSG_TYPE_SET_RELAY = 16
    MSG_TYPE_SET_DAC = 18
    MSG_TYPE_SET_MUX = 17
    CAN_BITRATE_DEFAULT = 500
    CAN_CHANNEL_DEFAULT = '0'
    WINDOW_WIDTH_DEFAULT = 1100
    WINDOW_HEIGHT_DEFAULT = 700
    LEFT_PANEL_MIN_WIDTH = 300
    LOGO_WIDTH = 280
    LOGO_HEIGHT = 80
    SLEEP_INTERVAL_SHORT = 0.02
    SLEEP_INTERVAL_MEDIUM = 0.05
    MUX_CHANNEL_MAX = 65535
    DWELL_TIME_MAX_MS = 60000
    PLOT_GRID_ALPHA = 0.3
    logger.warning("Could not import constants, using fallback values")

# Ensure repo root on sys.path so `backend` imports resolve when running from host_gui/
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

try:
    from backend.adapters.sim import SimAdapter
    from backend.adapters.interface import Frame as AdapterFrame
except Exception as exc:
    SimAdapter = None
    AdapterFrame = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

# Import optional adapters independently so module-level names always exist
try:
    from backend.adapters.pcan import PcanAdapter
except Exception:
    PcanAdapter = None

try:
    from backend.adapters.python_can_adapter import PythonCanAdapter
except Exception:
    PythonCanAdapter = None

# Import services for Phase 1 refactoring
try:
    from host_gui.services import CanService, DbcService, SignalService
except ImportError:
    # Fallback if services not available (for backwards compatibility during transition)
    CanService = None
    DbcService = None
    SignalService = None
    logger.warning("Services not available, using legacy implementation")


class AdapterWorker(threading.Thread):
    """Background worker thread that receives CAN frames from adapter and enqueues them.
    
    This worker runs in a separate thread to prevent blocking the GUI main thread.
    Frames received from the adapter are placed into a queue for processing by the
    GUI's frame polling mechanism.
    
    Attributes:
        sim: CAN adapter instance (must implement iter_recv() method)
        out_q: Queue for outgoing frames to GUI
        _stop: Event to signal thread shutdown
    """
    
    def __init__(self, sim, out_q: queue.Queue):
        """Initialize the adapter worker thread.
        
        Args:
            sim: CAN adapter instance (SimAdapter, PcanAdapter, etc.)
            out_q: Queue.Queue for frames to be processed by GUI
        """
        super().__init__(daemon=True)
        self.sim = sim
        self.out_q = out_q
        self._stop = threading.Event()

    def run(self):
        """Main thread loop: continuously receive frames and enqueue them."""
        try:
            for frame in self.sim.iter_recv():
                if self._stop.is_set():
                    logger.debug("AdapterWorker: stop signal received")
                    break
                self.out_q.put(frame)
        except Exception as e:
            logger.error(f"AdapterWorker error in run loop: {e}", exc_info=True)

    def stop(self):
        """Signal the worker thread to stop. Thread will exit after current frame."""
        self._stop.set()
        logger.debug("AdapterWorker: stop() called")


class TestRunner:
    """Lightweight test runner that encapsulates single-test execution logic.
    
    This class handles the execution of individual test cases, including:
    - Digital tests: Setting relay states and verifying feedback
    - Analog tests: Stepping DAC voltages and monitoring feedback signals
    
    The TestRunner is designed to be called from the GUI's main thread,
    but can be moved to a background thread for non-blocking execution
    in future refactoring.
    
    Attributes:
        gui: Reference to the BaseGUI instance for UI updates and frame sending
    """
    
    def __init__(self, gui: 'BaseGUI'):
        """Initialize the TestRunner with a reference to the GUI.
        
        Args:
            gui: BaseGUI instance for sending frames and updating UI
        """
        self.gui = gui
        # Phase 1: Access services through GUI
        self.can_service = getattr(gui, 'can_service', None)
        self.dbc_service = getattr(gui, 'dbc_service', None)
        self.signal_service = getattr(gui, 'signal_service', None)

    def run_single_test(self, test: Dict[str, Any], timeout: float = 1.0) -> Tuple[bool, str]:
        """Execute a single test using the same behavior as the previous
        BaseGUI._run_single_test implementation. 
        
        Args:
            test: Test configuration dictionary with 'name', 'actuation', etc.
            timeout: Timeout in seconds for feedback waiting
            
        Returns:
            Tuple of (success: bool, info: str)
        """
        gui = self.gui
        # ensure adapter running - Phase 1: check CanService first
        adapter_available = (self.can_service is not None and self.can_service.is_connected()) or gui.sim is not None
        if not adapter_available:
            logger.error("Attempted to run test without adapter running")
            raise RuntimeError('Adapter not running')
        act = test.get('actuation', {})
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
                    dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded()) or getattr(gui, '_dbc_db', None) is not None
                    if dbc_available and sig:
                        if self.dbc_service is not None:
                            msg = self.dbc_service.find_message_by_id(can_id)
                        else:
                            msg = gui._find_message_by_id(can_id)
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
                        gui.sim.send(f)
                    except Exception:
                        pass
                    if hasattr(gui.sim, 'loopback'):
                        try:
                            gui.sim.loopback(f)
                        except Exception:
                            pass

                def _wait_for_feedback(timeout_sec: float):
                    # reuse existing feedback scanning logic to look for feedback signal
                    waited = 0.0
                    poll_interval = POLL_INTERVAL_MS / 1000.0  # Convert ms to seconds
                    fb = test.get('feedback_signal')
                    observed_info = 'no feedback'
                    while waited < timeout_sec:
                        QtCore.QCoreApplication.processEvents()
                        time.sleep(poll_interval)
                        waited += poll_interval
                        try:
                            rows = gui.frame_table.rowCount()
                            for r in range(max(0, rows-10), rows):
                                try:
                                    can_id_item = gui.frame_table.item(r,1)
                                    data_item = gui.frame_table.item(r,3)
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
                                    dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded()) or getattr(gui, '_dbc_db', None) is not None
                                    if dbc_available and fb:
                                        if self.dbc_service is not None:
                                            target_msg, target_sig = self.dbc_service.find_message_and_signal(row_can, fb)
                                        else:
                                            target_msg, target_sig = gui._find_message_and_signal(row_can, fb)
                                        if target_msg is not None:
                                            try:
                                                if self.dbc_service is not None:
                                                    decoded = self.dbc_service.decode_message(target_msg, raw)
                                                else:
                                                    decoded = target_msg.decode(raw)
                                                observed_info = f"{fb}={decoded.get(fb)} (msg 0x{row_can:X})"
                                                return True, observed_info
                                            except Exception:
                                                pass
                                    else:
                                        observed_info = f'observed frame id=0x{row_can:X} data={raw.hex()}'
                                        return True, observed_info
                                except Exception:
                                    continue
                        except Exception:
                            pass
                    return False, observed_info

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

                def _check_frame_for_feedback():
                    fb = test.get('feedback_signal')
                    fb_mid = test.get('feedback_message_id')
                    try:
                        if fb:
                            if fb_mid is not None:
                                key = f"{fb_mid}:{fb}"
                                entry = gui._signal_values.get(key)
                                if entry is not None:
                                    ts, v = entry
                                    return v, f"{fb}={v} (msg 0x{fb_mid:X})"
                            else:
                                candidates = []
                                for k, (ts, v) in gui._signal_values.items():
                                    try:
                                        _can, sname = k.split(':', 1)
                                    except Exception:
                                        continue
                                    if sname == fb:
                                        candidates.append((ts, k, v))
                                if candidates:
                                    candidates.sort(key=lambda x: x[0], reverse=True)
                                    ts, k, v = candidates[0]
                                    canid = k.split(':', 1)[0]
                                    try:
                                        cid = int(canid)
                                        return v, f"{fb}={v} (msg 0x{cid:X})"
                                    except Exception:
                                        return v, f"{fb}={v} (msg {canid})"
                    except Exception:
                        pass

                    try:
                        rows = gui.frame_table.rowCount()
                    except Exception:
                        rows = 0
                    for r in range(max(0, rows - 50), rows):
                        try:
                            can_id_item = gui.frame_table.item(r, 1)
                            data_item = gui.frame_table.item(r, 3)
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
                            if gui._dbc_db is not None and fb:
                                target_msg, target_sig = gui._find_message_and_signal(row_can, fb)
                                if target_msg is not None:
                                    try:
                                        try:
                                            decoded = target_msg.decode(raw, decode_choices=False)
                                        except TypeError:
                                            decoded = target_msg.decode(raw)
                                        val = decoded.get(fb)
                                        return val, f"{fb}={val} (msg 0x{row_can:X})"
                                    except Exception:
                                        pass
                            else:
                                return raw.hex(), f"raw={raw.hex()} (msg 0x{row_can:X})"
                        except Exception:
                            continue
                    return None, None

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
                                    else:
                                        ts, val = gui.get_latest_signal(fb_mid, fb)
                                else:
                                    candidates = []
                                    for k, (t, v) in gui._signal_values.items():
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

                def _encode_and_send(signals: dict):
                    # signals: mapping of signal name -> value
                    encode_data = {'DeviceID': 0}  # always include DeviceID
                    mux_value = None
                    data_bytes = b''
                    # Phase 1: Use DbcService if available
                    dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded()) or getattr(gui, '_dbc_db', None) is not None
                    if dbc_available:
                        if self.dbc_service is not None:
                            target_msg = self.dbc_service.find_message_by_id(can_id)
                        else:
                            target_msg = gui._find_message_by_id(can_id)
                    else:
                        target_msg = None
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
                    try:
                        if dac_cmd_sig and dac_cmd_sig in signals:
                            gui.current_signal_label.setText(str(signals[dac_cmd_sig]))
                        elif len(signals) == 1:
                            # if a single signal is being sent, show its value
                            gui.current_signal_label.setText(str(list(signals.values())[0]))
                    except Exception:
                        pass

                    # Phase 1: Use CanService if available
                    if self.can_service is not None and self.can_service.is_connected():
                        from backend.adapters.interface import Frame as AdapterFrame
                        f = AdapterFrame(can_id=can_id, data=data_bytes, timestamp=time.time())
                        logger.debug(f'Signals: {signals}')
                        logger.debug(f'Encode data: {encode_data}')
                        logger.debug(f"Sending frame via service: can_id=0x{can_id:X} data={data_bytes.hex()}")
                        try:
                            self.can_service.send_frame(f)
                        except Exception as e:
                            logger.warning(f"Failed to send frame via service: {e}")
                    else:
                        # Legacy: use direct adapter
                        if AdapterFrame is not None:
                            f = AdapterFrame(can_id=can_id, data=data_bytes)
                            logger.debug(f'Signals: {signals}')
                            logger.debug(f'Encode data: {encode_data}')
                            logger.debug(f"Sending frame: can_id=0x{can_id:X} data={data_bytes.hex()}")
                        else:
                            class F: pass
                            f = F(); f.can_id = can_id; f.data = data_bytes; f.timestamp = time.time()
                        try:
                            gui.sim.send(f)
                        except Exception:
                            pass
                    if hasattr(gui.sim, 'loopback'):
                        try:
                            gui.sim.loopback(f)
                        except Exception:
                            pass

                success = False
                info = ''
                # Get feedback signal info for plotting
                fb_signal = test.get('feedback_signal')
                fb_msg_id = test.get('feedback_message_id')
                test_name = test.get('name', 'Analog Test')
                
                # Clear plot before starting new analog test
                try:
                    gui._clear_plot()
                except Exception:
                    pass
                
                try:
                    # 1) Disable MUX
                    if mux_enable_sig:
                        _encode_and_send({mux_enable_sig: 0})
                        _nb_sleep(SLEEP_INTERVAL_SHORT)
                    # 2) Set MUX channel
                    if mux_channel_sig and mux_channel_value is not None:
                        _encode_and_send({mux_channel_sig: int(mux_channel_value)})
                        _nb_sleep(SLEEP_INTERVAL_SHORT)
                    # 3) Set DAC to min
                    if dac_cmd_sig:
                        _encode_and_send({dac_cmd_sig: int(dac_min)})
                        _nb_sleep(SLEEP_INTERVAL_SHORT)
                    # 4) Enable MUX (send channel + enable together if channel known)
                    if mux_enable_sig:
                        if mux_channel_sig and mux_channel_value is not None:
                            _encode_and_send({mux_enable_sig: 1, mux_channel_sig: int(mux_channel_value)})
                        else:
                            _encode_and_send({mux_enable_sig: 1})
                    # 5) Hold initial dwell and collect feedback data point
                    _nb_sleep(float(dwell_ms) / 1000.0)
                    # Collect feedback value for initial DAC voltage
                    if fb_signal and fb_msg_id:
                        try:
                            ts, fb_val = gui.get_latest_signal(fb_msg_id, fb_signal)
                            if fb_val is not None:
                                gui._update_plot(dac_min, fb_val, test_name)
                        except Exception:
                            pass
                    
                    # 6) Ramp DAC up by step, holding for dwell each step
                    cur = int(dac_min)
                    while cur < int(dac_max):
                        cur = min(cur + int(dac_step), int(dac_max))
                        if dac_cmd_sig:
                            _encode_and_send({dac_cmd_sig: int(cur)})
                        _nb_sleep(float(dwell_ms) / 1000.0)
                        # Collect feedback value at this DAC voltage step
                        if fb_signal and fb_msg_id:
                            try:
                                ts, fb_val = gui.get_latest_signal(fb_msg_id, fb_signal)
                                if fb_val is not None:
                                    gui._update_plot(cur, fb_val, test_name)
                            except Exception:
                                pass
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
                    except Exception:
                        pass
                    try:
                        if mux_enable_sig:
                            # send disable; include channel if available to be explicit
                            if mux_channel_sig and mux_channel_value is not None:
                                _encode_and_send({mux_enable_sig: 0, mux_channel_sig: int(mux_channel_value)})
                            else:
                                _encode_and_send({mux_enable_sig: 0})
                            _nb_sleep(SLEEP_INTERVAL_SHORT)
                    except Exception:
                        pass
                return success, info
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
                rows = gui.frame_table.rowCount()
                for r in range(max(0, rows-10), rows):
                    try:
                        can_id_item = gui.frame_table.item(r,1)
                        data_item = gui.frame_table.item(r,3)
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
                        dbc_available = (self.dbc_service is not None and self.dbc_service.is_loaded()) or getattr(gui, '_dbc_db', None) is not None
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
                            else:
                                # Legacy fallback
                                target_msg = None
                                for m in getattr(gui._dbc_db, 'messages', []):
                                    for s in getattr(m, 'signals', []):
                                        if s.name == fb and getattr(m, 'frame_id', None) == row_can:
                                            target_msg = m
                                            break
                                    if target_msg:
                                        break
                                if target_msg is not None:
                                    try:
                                        decoded = target_msg.decode(raw)
                                        observed_info = f"{fb}={decoded.get(fb)} (msg 0x{row_can:X})"
                                        return True, observed_info
                                    except Exception:
                                        pass
                        else:
                            observed_info = f'observed frame id=0x{row_can:X} data={raw.hex()}'
                            return True, observed_info
                    except Exception:
                        continue
            except Exception:
                pass

        return False, observed_info


class BaseGUI(QtWidgets.QMainWindow):
    """Main GUI application window for EOL Host testing.
    
    This class provides the main application interface including:
    - CAN adapter connection and configuration
    - DBC file management and loading
    - Test configuration and execution
    - Real-time CAN frame monitoring
    - Signal decoding and visualization
    - Test results display with live plots
    
    The GUI is organized into tabs:
    - Home: Welcome and overview
    - CAN Data View: Live frames, decoded signals, manual frame sending
    - Test Configurator: Create and manage test profiles
    - Test Status: Execute tests and view results with plots
    
    Attributes:
        sim: Current CAN adapter instance (None when disconnected, deprecated - use can_service)
        worker: AdapterWorker thread for frame reception (deprecated - use can_service)
        frame_q: Queue for frames from worker thread (deprecated - use can_service.frame_queue)
        _dbc_db: Loaded cantools database object (deprecated - use dbc_service)
        _tests: List of configured test profiles
        _signal_values: Cache of latest signal values (deprecated - use signal_service)
        
        # Phase 1: Service layer (new)
        can_service: CanService instance for adapter management
        dbc_service: DbcService instance for DBC operations
        signal_service: SignalService instance for signal decoding
    """
    
    def __init__(self):
        """Initialize the main GUI window and build all UI components."""
        super().__init__()
        self.setWindowTitle('EOL Host - Native GUI')
        self.resize(WINDOW_WIDTH_DEFAULT, WINDOW_HEIGHT_DEFAULT)

        self.sim = None  # Legacy - will be replaced by can_service
        self.worker = None  # Legacy - will be replaced by can_service
        self.frame_q = queue.Queue()  # Legacy - will use can_service.frame_queue
        
        # Initialize services (Phase 1)
        if CanService is not None:
            can_channel = os.environ.get('CAN_CHANNEL', os.environ.get('PCAN_CHANNEL', CAN_CHANNEL_DEFAULT))
            try:
                can_bitrate = int(os.environ.get('CAN_BITRATE', os.environ.get('PCAN_BITRATE', str(CAN_BITRATE_DEFAULT))))
            except Exception:
                can_bitrate = CAN_BITRATE_DEFAULT
            self.can_service = CanService(channel=can_channel, bitrate=can_bitrate)
            self.frame_q = self.can_service.frame_queue  # Use service's queue
        else:
            self.can_service = None
        
        if DbcService is not None:
            self.dbc_service = DbcService()
        else:
            self.dbc_service = None
        
        if SignalService is not None and self.dbc_service is not None:
            self.signal_service = SignalService(self.dbc_service)
        else:
            self.signal_service = None
        
        # limits
        self._max_messages = MAX_MESSAGES_DEFAULT
        self._max_frames = MAX_FRAMES_DEFAULT
        # generic CAN settings defaults (can be overridden by UI)
        # defaults may come from environment variables specific to adapters
        # Use conservative defaults: channel 0 and 500 kbps
        self._can_channel = os.environ.get('CAN_CHANNEL', os.environ.get('PCAN_CHANNEL', CAN_CHANNEL_DEFAULT))
        try:
            # prefer environment-provided bitrate in kbps, otherwise default to 500
            self._can_bitrate = int(os.environ.get('CAN_BITRATE', os.environ.get('PCAN_BITRATE', str(CAN_BITRATE_DEFAULT))))
        except Exception:
            self._can_bitrate = CAN_BITRATE_DEFAULT

        self._build_menu()
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

        self._load_dbcs()
        
        # Signal lookup cache: key = f"{can_id}:{signal_name}" -> (message, signal)
        self._signal_lookup_cache = {}
        self._message_cache = {}  # key = can_id -> message

        # Poll timer for frames
        self.poll_timer = QtCore.QTimer(self)
        self.poll_timer.setInterval(FRAME_POLL_INTERVAL_MS)
        self.poll_timer.timeout.connect(self._poll_frames)

    def _build_menu(self):
        """Build the application menu bar with File and Help menus."""
        menubar = self.menuBar()
        file_menu = menubar.addMenu('&File')
        exit_act = QtGui.QAction('E&xit', self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        help_menu = menubar.addMenu('&Help')
        about_act = QtGui.QAction('&About', self)
        about_act.triggered.connect(lambda: QtWidgets.QMessageBox.information(self, 'About', 'EOL Host Native GUI'))
        help_menu.addAction(about_act)

    def _build_test_configurator(self):
        """Builds the Test Configurator tab widget and returns it.
        
        The Test Configurator allows users to:
        - Create new test profiles (digital or analog)
        - Edit existing test configurations
        - Delete tests
        - Reorder tests in sequence
        - Save/load test profiles as JSON files
        
        Test profiles include:
        - Digital tests: Relay commands, feedback signal, dwell time
        - Analog tests: DAC voltage range, MUX settings, feedback signal
        
        Returns:
            QWidget containing the Test Configurator tab layout
        """
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # DBC file picker
        dbc_row = QtWidgets.QHBoxLayout()
        self.dbc_path_edit = QtWidgets.QLineEdit()
        self.dbc_load_btn = QtWidgets.QPushButton('Load DBC')
        dbc_row.addWidget(QtWidgets.QLabel('DBC File:'))
        dbc_row.addWidget(self.dbc_path_edit)
        dbc_row.addWidget(self.dbc_load_btn)
        layout.addLayout(dbc_row)

        # main split: left controls, right test list
        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # left controls
        left = QtWidgets.QWidget()
        left_v = QtWidgets.QVBoxLayout(left)
        self.create_test_btn = QtWidgets.QPushButton('Create Test')
        self.delete_test_btn = QtWidgets.QPushButton('Delete Selected Test')
        self.save_tests_btn = QtWidgets.QPushButton('Save Tests')
        self.load_tests_btn = QtWidgets.QPushButton('Load Tests')
        left_v.addWidget(self.create_test_btn)
        left_v.addWidget(self.delete_test_btn)
        left_v.addStretch()
        left_v.addWidget(self.save_tests_btn)
        left_v.addWidget(self.load_tests_btn)

        # right: reorderable test list and JSON preview
        right = QtWidgets.QWidget()
        right_v = QtWidgets.QVBoxLayout(right)
        self.test_list = QtWidgets.QListWidget()
        self.test_list.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.test_list.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.test_list.model().rowsMoved.connect(self._on_test_list_reordered)
        right_v.addWidget(QtWidgets.QLabel('Tests Sequence (drag to reorder):'))
        right_v.addWidget(self.test_list, 1)
        self.json_preview = QtWidgets.QPlainTextEdit()
        self.json_preview.setReadOnly(True)
        right_v.addWidget(QtWidgets.QLabel('Selected Test JSON Preview:'))
        right_v.addWidget(self.json_preview, 1)

        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)

        layout.addWidget(split)

        # internal tests storage
        self._tests = []
        # DBC database once loaded
        self._dbc_db = None

        # run controls will be created in the configurator UI
        self._run_log = []

        # wire buttons
        self.dbc_load_btn.clicked.connect(self._on_load_dbc)
        self.create_test_btn.clicked.connect(self._on_create_test)
        self.delete_test_btn.clicked.connect(self._on_delete_test)
        self.save_tests_btn.clicked.connect(self._on_save_tests)
        self.load_tests_btn.clicked.connect(self._on_load_tests)
        self.test_list.currentItemChanged.connect(self._on_select_test)
        self.test_list.itemDoubleClicked.connect(self._on_edit_test)

        # run buttons moved to Test Status tab

        return tab

    def _build_test_status(self):
        """Builds the Test Status tab widget and returns it.
        
        The Test Status tab provides:
        - Test execution controls (Run Selected, Run Sequence)
        - Real-time monitoring of current and feedback signals
        - Live plot showing Feedback vs DAC Voltage (for analog tests)
        - Test results table with pass/fail status
        - Execution log with timestamps
        
        Returns:
            QWidget containing the Test Status tab layout
        """
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # Run buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.run_test_btn = QtWidgets.QPushButton('Run Selected Test')
        self.run_seq_btn = QtWidgets.QPushButton('Run Sequence')
        btn_layout.addWidget(self.run_test_btn)
        btn_layout.addWidget(self.run_seq_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Control buttons
        ctrl_layout = QtWidgets.QHBoxLayout()
        self.clear_results_btn = QtWidgets.QPushButton('Clear Results')
        self.repeat_test_btn = QtWidgets.QPushButton('Repeat Last Test')
        ctrl_layout.addWidget(self.clear_results_btn)
        ctrl_layout.addWidget(self.repeat_test_btn)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # Status display
        status_group = QtWidgets.QGroupBox('Test Execution Status')
        status_layout = QtWidgets.QVBoxLayout(status_group)

        # Progress bar for sequence
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QtWidgets.QLabel('Ready')
        status_layout.addWidget(self.status_label)

        # Real-time monitoring
        monitor_group = QtWidgets.QGroupBox('Real-Time Monitoring')
        monitor_layout = QtWidgets.QFormLayout(monitor_group)
        self.current_signal_label = QtWidgets.QLabel('N/A')
        monitor_layout.addRow('Current Signal Value:', self.current_signal_label)
        self.feedback_signal_label = QtWidgets.QLabel('N/A')
        monitor_layout.addRow('Feedback Signal Value:', self.feedback_signal_label)
        status_layout.addWidget(monitor_group)

        # Plot widget for analog tests (Feedback vs DAC Voltage)
        plot_group = QtWidgets.QGroupBox('Feedback vs DAC Output Voltage')
        plot_layout = QtWidgets.QVBoxLayout(plot_group)
        if matplotlib_available:
            try:
                self._init_plot()
                if hasattr(self, 'plot_canvas') and self.plot_canvas is not None:
                    plot_layout.addWidget(self.plot_canvas)
                    plot_group.setVisible(True)
                else:
                    no_plot_label = QtWidgets.QLabel('Plot initialization failed.')
                    no_plot_label.setAlignment(QtCore.Qt.AlignCenter)
                    plot_layout.addWidget(no_plot_label)
                    plot_group.setVisible(False)
            except Exception:
                no_plot_label = QtWidgets.QLabel('Plot initialization failed.')
                no_plot_label.setAlignment(QtCore.Qt.AlignCenter)
                plot_layout.addWidget(no_plot_label)
                plot_group.setVisible(False)
        else:
            no_plot_label = QtWidgets.QLabel('Matplotlib not available. Plot disabled.')
            no_plot_label.setAlignment(QtCore.Qt.AlignCenter)
            plot_layout.addWidget(no_plot_label)
            plot_group.setVisible(False)
        status_layout.addWidget(plot_group)

        # Results table
        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels(['Test Name', 'Type', 'Status', 'Execution Time', 'Parameters', 'Notes'])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setAlternatingRowColors(True)

        # Log text area
        self.test_log = QtWidgets.QPlainTextEdit()
        self.test_log.setReadOnly(True)

        # Results display with splitter
        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        
        # Results table in a group
        table_group = QtWidgets.QGroupBox('Test Results Table')
        table_layout = QtWidgets.QVBoxLayout(table_group)
        table_layout.addWidget(self.results_table)
        splitter.addWidget(table_group)
        
        # Log in a group
        log_group = QtWidgets.QGroupBox('Execution Log')
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.addWidget(self.test_log)
        splitter.addWidget(log_group)
        
        status_layout.addWidget(splitter)

        layout.addWidget(status_group)

        # Connect buttons
        self.run_test_btn.clicked.connect(self._on_run_selected)
        self.run_seq_btn.clicked.connect(self._on_run_sequence)
        self.clear_results_btn.clicked.connect(self._on_clear_results)
        self.repeat_test_btn.clicked.connect(self._on_repeat_test)

        return tab

    def _add_result_to_table(self, test: Dict[str, Any], status: str, exec_time: str, notes: str) -> None:
        """Add a test result row to the results table in Test Status tab.
        
        Args:
            test: Test configuration dictionary
            status: Test status ('PASS', 'FAIL', or 'ERROR')
            exec_time: Execution time as string (e.g., "1.23s")
            notes: Additional information or error details
        """
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(test.get('name', '<unnamed>')))
        act = test.get('actuation', {})
        test_type = act.get('type', 'Unknown')
        self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(test_type.capitalize()))
        self.results_table.setItem(row, 2, QtWidgets.QTableWidgetItem(status))
        self.results_table.setItem(row, 3, QtWidgets.QTableWidgetItem(exec_time))
        
        # Parameters
        params = []
        if test_type == 'digital':
            if act.get('can_id'):
                params.append(f"CAN ID: {act['can_id']}")
            if act.get('signal'):
                params.append(f"Signal: {act['signal']}")
            if act.get('value'):
                params.append(f"Value: {act['value']}")
        elif test_type == 'analog':
            if act.get('dac_can_id'):
                params.append(f"DAC CAN ID: {act['dac_can_id']}")
            if act.get('dac_command'):
                params.append(f"Command: {act['dac_command']}")
            if act.get('mux_channel'):
                params.append(f"MUX Channel: {act['mux_channel']}")
            if act.get('mux_value'):
                params.append(f"MUX Value: {act['mux_value']}")
        param_str = ', '.join(params)
        self.results_table.setItem(row, 4, QtWidgets.QTableWidgetItem(param_str))
        self.results_table.setItem(row, 5, QtWidgets.QTableWidgetItem(notes))

    def _init_plot(self):
        """Initialize the matplotlib plot widget for Feedback vs DAC Voltage visualization.
        
        Creates a scatter plot with connected line showing the relationship between
        commanded DAC output voltage (X-axis) and IPC feedback signal value (Y-axis).
        The plot is displayed in the Test Status tab during analog test execution.
        """
        if not matplotlib_available:
            self.plot_canvas = None
            return
        try:
            # Create figure and canvas
            self.plot_figure = Figure(figsize=(8, 4))
            self.plot_canvas = FigureCanvasQTAgg(self.plot_figure)
            self.plot_axes = self.plot_figure.add_subplot(111)
            
            # Initialize data storage
            self.plot_dac_voltages = []
            self.plot_feedback_values = []
            
            # Configure axes
            self.plot_axes.set_xlabel('DAC Output Voltage (mV)')
            self.plot_axes.set_ylabel('Feedback Signal Value')
            self.plot_axes.set_title('Feedback vs DAC Output')
            self.plot_axes.grid(True, alpha=PLOT_GRID_ALPHA)
            
            # Create initial empty scatter plot with line connection
            self.plot_line, = self.plot_axes.plot([], [], 'bo-', markersize=6, linewidth=1, label='Feedback')
            self.plot_axes.legend()
            
            # Auto-adjust layout
            self.plot_figure.tight_layout()
        except Exception:
            # If plot initialization fails, mark as unavailable
            self.plot_canvas = None
            self.plot_axes = None
            self.plot_figure = None

    def _clear_plot(self):
        """Clear the plot data and reset axes."""
        if not matplotlib_available or not hasattr(self, 'plot_axes') or self.plot_axes is None:
            return
        try:
            self.plot_dac_voltages = []
            self.plot_feedback_values = []
            self.plot_line.set_data([], [])
            self.plot_axes.relim()
            self.plot_axes.autoscale()
            self.plot_canvas.draw_idle()
        except Exception:
            pass

    def _update_plot(self, dac_voltage: float, feedback_value: float, test_name: Optional[str] = None) -> None:
        """Update the plot with a new data point (DAC voltage, feedback value).
        
        Args:
            dac_voltage: DAC output voltage in millivolts
            feedback_value: IPC feedback signal value
            test_name: Optional test name for plot title
        """
        if not matplotlib_available or not hasattr(self, 'plot_axes') or self.plot_axes is None:
            return
        try:
            # Add new data point
            if dac_voltage is not None and feedback_value is not None:
                self.plot_dac_voltages.append(float(dac_voltage))
                self.plot_feedback_values.append(float(feedback_value))
                
                # Update plot line
                self.plot_line.set_data(self.plot_dac_voltages, self.plot_feedback_values)
                
                # Auto-scale axes to fit all data
                self.plot_axes.relim()
                self.plot_axes.autoscale()
                
                # Update title if test name provided
                if test_name and not self.plot_axes.get_title():
                    self.plot_axes.set_title(f'Feedback vs DAC Output: {test_name}')
                
                # Refresh canvas (use draw_idle for better performance)
                self.plot_canvas.draw_idle()
        except Exception:
            pass

    def _build_test_report(self):
        """Builds the Test Report tab widget and returns it."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        label = QtWidgets.QLabel('Test Report - Coming Soon')
        label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(label)
        return tab

    def _build_toolbar(self):
        # Toolbar kept minimal; adapter selection is on Welcome page
        tb = self.addToolBar('Main')
        self.status_label = QtWidgets.QLabel('Status: Idle')
        tb.addWidget(self.status_label)

    def _build_central(self):
        # Central layout: left persistent device controls, right main tabs
        central = QtWidgets.QWidget()
        main_h = QtWidgets.QHBoxLayout(central)

        # Left: persistent device controls (top-left corner, global)
        left_panel = QtWidgets.QWidget()
        left_panel.setMinimumWidth(LEFT_PANEL_MIN_WIDTH)
        left_layout = QtWidgets.QVBoxLayout(left_panel)

        # Logo and welcome buttons at top of left panel
        logo_label = QtWidgets.QLabel()
        logo_pix = self._generate_logo_pixmap(LOGO_WIDTH, LOGO_HEIGHT)
        logo_label.setPixmap(logo_pix)
        logo_label.setAlignment(QtCore.Qt.AlignCenter)
        left_layout.addWidget(logo_label)

        btn_row = QtWidgets.QHBoxLayout()
        test_menu_btn = QtWidgets.QPushButton('Test Menu')
        test_menu_btn.clicked.connect(self._open_test_menu)
        cfg_btn = QtWidgets.QPushButton('Test Configurator')
        cfg_btn.clicked.connect(self._open_test_configurator)
        help_btn = QtWidgets.QPushButton('Help')
        help_btn.clicked.connect(self._open_help)
        btn_row.addWidget(test_menu_btn)
        btn_row.addWidget(cfg_btn)
        btn_row.addWidget(help_btn)
        left_layout.addLayout(btn_row)

        left_layout.addSpacing(8)

        # Device controls (global)
        dev_group = QtWidgets.QGroupBox('CAN Interface')
        dg = QtWidgets.QVBoxLayout(dev_group)
        self.device_combo = QtWidgets.QComboBox()
        dg.addWidget(self.device_combo)
        hb = QtWidgets.QHBoxLayout()
        self.refresh_btn = QtWidgets.QPushButton('Refresh')
        self.refresh_btn.clicked.connect(self._refresh_can_devices)
        self.connect_btn = QtWidgets.QPushButton('Connect')
        self.connect_btn.clicked.connect(self._connect_selected_device)
        hb.addWidget(self.refresh_btn)
        hb.addWidget(self.connect_btn)
        dg.addLayout(hb)
        left_layout.addWidget(dev_group)

        # General CAN settings (generic)
        can_settings = QtWidgets.QGroupBox('CAN Settings')
        cs_layout = QtWidgets.QFormLayout(can_settings)
        # channel dropdown will be populated based on selected adapter
        self.can_channel_combo = QtWidgets.QComboBox()
        cs_layout.addRow('Channel:', self.can_channel_combo)
        # bitrate dropdown (kbps)
        self.can_bitrate_combo = QtWidgets.QComboBox()
        bitrate_choices = ['10 kbps','20 kbps','50 kbps','125 kbps','250 kbps','500 kbps','800 kbps','1000 kbps']
        self.can_bitrate_combo.addItems(bitrate_choices)
        # tooltip to clarify units; Canalystii backend expects bitrate in bits-per-second,
        # the GUI accepts kbps and will auto-convert when Canalystii is selected.
        self.can_bitrate_combo.setToolTip('Bitrate in kbps (e.g. 500). Canalystii backend will be converted to bps automatically.')
        # set default if present
        try:
            if self._can_bitrate:
                kb = str(int(self._can_bitrate))
                # prefer matching choice
                for i in range(self.can_bitrate_combo.count()):
                    if self.can_bitrate_combo.itemText(i).startswith(kb):
                        self.can_bitrate_combo.setCurrentIndex(i)
                        break
        except Exception:
            pass
        cs_layout.addRow('Bitrate (kbps):', self.can_bitrate_combo)
        apply_btn = QtWidgets.QPushButton('Apply')
        def _apply_settings():
            self._can_channel = self.can_channel_combo.currentText().strip() or self._can_channel
            # parse kbps value
            try:
                txt = self.can_bitrate_combo.currentText().strip()
                if txt:
                    self._can_bitrate = int(txt.split()[0])
            except Exception:
                pass
            QtWidgets.QMessageBox.information(self, 'Settings', 'CAN settings applied')
        apply_btn.clicked.connect(_apply_settings)
        cs_layout.addRow(apply_btn)
        left_layout.addWidget(can_settings)

        # when adapter selection changes, update available channels
        def _on_device_changed(text: str):
            text = (text or '').strip()
            channels = []
            if text.lower().startswith('pcan'):
                channels = ['PCAN_USBBUS1','PCAN_USBBUS2','PCAN_USBBUS3','PCAN_USBBUS4']
            elif text.lower().startswith('socketcan'):
                channels = ['can0','can1','can2']
            elif text.lower().startswith('canalystii') or text.lower() == 'canalystii':
                channels = ['0','1']
            elif text.lower().startswith('sim'):
                channels = ['sim']
            else:
                # default to previous or current
                channels = [self._can_channel]
            self.can_channel_combo.clear()
            self.can_channel_combo.addItems(channels)
            # select first
            try:
                self.can_channel_combo.setCurrentIndex(0)
            except Exception:
                pass

        self.device_combo.currentTextChanged.connect(_on_device_changed)

        left_layout.addStretch()

        # Right: main tab widget
        main_tabs = QtWidgets.QTabWidget()
        self.tabs_main = main_tabs

        # Welcome tab (simple overview)
        welcome_tab = QtWidgets.QWidget()
        w_layout = QtWidgets.QVBoxLayout(welcome_tab)
        w_layout.addWidget(QtWidgets.QLabel('<b>Welcome to EOL Host</b>'))
        w_layout.addStretch()
        main_tabs.addTab(welcome_tab, 'Home')

        # CAN Data View: contains inner sub-tabs
        can_tab = QtWidgets.QWidget()
        can_layout = QtWidgets.QVBoxLayout(can_tab)

        # Create sub-tabs for CAN Data View
        inner = QtWidgets.QTabWidget()
        self.inner_tabs = inner

        # DBC Manager
        self.dbc_widget = QtWidgets.QWidget()
        dbc_layout = QtWidgets.QVBoxLayout(self.dbc_widget)
        self.dbc_list = QtWidgets.QListWidget()
        dbc_layout.addWidget(self.dbc_list)
        btn_row2 = QtWidgets.QHBoxLayout()
        upload_btn = QtWidgets.QPushButton('Upload DBC')
        upload_btn.clicked.connect(self._upload_dbc)
        decode_btn = QtWidgets.QPushButton('Decode Sample Frame')
        decode_btn.clicked.connect(self._decode_sample)
        btn_row2.addWidget(upload_btn)
        btn_row2.addWidget(decode_btn)
        btn_row2.addStretch()
        dbc_layout.addLayout(btn_row2)

        # Live Data
        self.live_widget = QtWidgets.QWidget()
        live_layout = QtWidgets.QVBoxLayout(self.live_widget)
        self.frame_table = QtWidgets.QTableWidget(0, 4)
        self.frame_table.setHorizontalHeaderLabels(['ts', 'can_id', 'len', 'data'])
        self.frame_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.msg_log = QtWidgets.QListWidget()
        self.msg_log.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.msg_log.setMinimumWidth(360)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.frame_table)
        splitter.addWidget(self.msg_log)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        live_layout.addWidget(splitter)

        # Send Data
        self.send_widget = QtWidgets.QWidget()
        send_layout = QtWidgets.QFormLayout(self.send_widget)
        self.send_id = QtWidgets.QLineEdit()
        self.send_data = QtWidgets.QLineEdit()
        send_btn = QtWidgets.QPushButton('Send Frame')
        send_btn.clicked.connect(self._send_frame)
        send_layout.addRow('CAN ID (hex/dec):', self.send_id)
        send_layout.addRow('Data (hex):', self.send_data)
        send_layout.addRow(send_btn)

        # Settings
        self.settings_widget = QtWidgets.QWidget()
        s_layout = QtWidgets.QVBoxLayout(self.settings_widget)
        s_layout.addWidget(QtWidgets.QLabel('Settings / Configurations'))
        s_layout.addStretch()

        inner.addTab(self.dbc_widget, 'DBC Manager')
        inner.addTab(self.live_widget, 'Live Data')
        # Signal view: decoded signals from DBC (if loaded)
        self.signal_widget = QtWidgets.QWidget()
        sig_layout = QtWidgets.QVBoxLayout(self.signal_widget)
        self.signal_table = QtWidgets.QTableWidget(0, 5)
        self.signal_table.setHorizontalHeaderLabels(['ts', 'message', 'can_id', 'signal', 'value'])
        self.signal_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        sig_layout.addWidget(self.signal_table)
        inner.addTab(self.signal_widget, 'Signal View')
        # mapping of signal key -> row index in signal_table for fast updates
        self._signal_rows = {}
        # storage for latest signal values: key -> (timestamp, value)
        self._signal_values = {}
        # currently monitored feedback signal during test run: (msg_id, signal_name) or None
        self._current_feedback = None
        inner.addTab(self.send_widget, 'Send Data')
        inner.addTab(self.settings_widget, 'Settings')

        can_layout.addWidget(inner)
        main_tabs.addTab(can_tab, 'CAN Data View')

        # assemble central layout
        main_h.addWidget(left_panel)
        main_h.addWidget(main_tabs, 1)
        self.setCentralWidget(central)

        # keep references for switching and controls
        self.tabs_main = main_tabs
        self._refresh_can_devices()
        try:
            self.start_btn = self.connect_btn
        except Exception:
            self.start_btn = None

        # build Test Configurator tab and wire into main_tabs
        try:
            test_tab = self._build_test_configurator()
            # add as a top-level tab after CAN Data View
            self.tabs_main.addTab(test_tab, 'Test Configurator')
            # Add placeholder tabs for Test Status and Test Report
            status_tab = self._build_test_status()
            self.status_tab_index = self.tabs_main.addTab(status_tab, 'Test Status')
            report_tab = self._build_test_report()
            self.tabs_main.addTab(report_tab, 'Test Report')
        except Exception:
            pass

    # Welcome actions
    def _refresh_can_devices(self):
        """Refresh the list of available CAN adapter types in the device combo box.
        
        Probes for available adapters by attempting imports:
        - SimAdapter: Always available (software simulation)
        - PCAN: Peak CAN USB adapters
        - PythonCAN: Generic python-can backend
        - Canalystii: Canalystii hardware via python-can
        - SocketCAN: Linux SocketCAN interfaces
        """
        # Probe available adapters
        devices = []
        # SimAdapter always available as a software option
        devices.append('SimAdapter')
        try:
            import backend.adapters.pcan as _pc
            devices.append('PCAN')
        except Exception:
            pass
        try:
            import backend.adapters.python_can_adapter as _pycan
            devices.append('PythonCAN')
            # python-can backend can also be used with Canalystii hardware
            devices.append('Canalystii')
        except Exception:
            pass
        try:
            import backend.adapters.socketcan as _sc
            devices.append('SocketCAN')
        except Exception:
            pass
        # update combo
        self.device_combo.clear()
        self.device_combo.addItems(devices)

    def _connect_selected_device(self):
        """Connect or disconnect the selected CAN adapter device.
        
        If adapter is already running, this will disconnect it.
        Otherwise, it will attempt to connect using the selected device type.
        """
        # If adapter running, toggle to stop
        if self.sim is not None:
            self.toggle_adapter()
            return
        # otherwise start using selected device
        self.toggle_adapter()

    def _open_test_menu(self):
        # Switch to Live tab for quick access to running frames
        try:
            # switch to main CAN Data View and the Live Data inner tab
            if hasattr(self, 'tabs_main') and hasattr(self, 'inner_tabs'):
                # select CAN Data View
                for i in range(self.tabs_main.count()):
                    if self.tabs_main.tabText(i).lower() == 'can data view':
                        self.tabs_main.setCurrentIndex(i)
                        break
                # select Live Data inner tab
                for j in range(self.inner_tabs.count()):
                    if self.inner_tabs.tabText(j).lower() == 'live data':
                        self.inner_tabs.setCurrentIndex(j)
                        return
        except Exception:
            pass
        # If tab switching failed, show a message
        QtWidgets.QMessageBox.information(self, 'Test Menu', 'Switched to CAN Data View')

    def _open_test_configurator(self):
        """Switch to the Test Configurator tab."""
        try:
            if hasattr(self, 'tabs_main'):
                for i in range(self.tabs_main.count()):
                    if 'configurator' in self.tabs_main.tabText(i).lower():
                        self.tabs_main.setCurrentIndex(i)
                        return
        except Exception:
            pass
        QtWidgets.QMessageBox.information(self, 'Test Configurator', 'Test Configurator tab not found')

    def _open_help(self):
        """Display help information dialog."""
        help_text = (
            "EOL Host Application\n\n"
            "Usage:\n"
            "1. Connect to a CAN adapter from the Home tab\n"
            "2. Load a DBC file to decode CAN signals\n"
            "3. Configure tests in the Test Configurator tab\n"
            "4. Execute tests and view results in the Test Status tab\n"
            "5. Monitor live CAN data in the CAN Data View tab\n\n"
            "For detailed documentation, see README.md or the docs/ folder."
        )
        QtWidgets.QMessageBox.information(self, 'Help', help_text)

    def _build_statusbar(self):
        sb = self.statusBar()
        self.conn_indicator = QtWidgets.QLabel('Adapter: stopped')
        sb.addPermanentWidget(self.conn_indicator)

    def _find_message_by_id(self, can_id: int) -> Optional[Any]:
        """Find message by CAN ID in loaded DBC. Uses cache for performance.
        
        Args:
            can_id: CAN identifier (0-0x1FFFFFFF)
            
        Returns:
            Message object from cantools database or None if not found
        """
        # Phase 1: Use DbcService if available
        if self.dbc_service is not None:
            return self.dbc_service.find_message_by_id(can_id)
        
        # Legacy implementation (fallback)
        if not hasattr(self, '_dbc_db') or self._dbc_db is None:
            return None
        
        # Check cache first
        if can_id in self._message_cache:
            return self._message_cache[can_id]
        
        # Search and cache result
        for m in getattr(self._dbc_db, 'messages', []):
            msg_id = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
            if msg_id is not None and int(msg_id) == int(can_id):
                self._message_cache[can_id] = m
                return m
        
        # Cache None to avoid repeated searches
        self._message_cache[can_id] = None
        return None
    
    def _find_message_and_signal(self, can_id: int, signal_name: str) -> Tuple[Optional[Any], Optional[Any]]:
        """Find message and signal by CAN ID and signal name. Uses cache for performance.
        
        Args:
            can_id: CAN identifier (0-0x1FFFFFFF)
            signal_name: Name of the signal to find
            
        Returns:
            Tuple of (message, signal) from cantools database or (None, None) if not found
        """
        # Phase 1: Use DbcService if available
        if self.dbc_service is not None:
            return self.dbc_service.find_message_and_signal(can_id, signal_name)
        
        # Legacy implementation (fallback)
        if not signal_name:
            return None, None
        
        # Check signal lookup cache first
        cache_key = f"{int(can_id)}:{signal_name}"
        if cache_key in self._signal_lookup_cache:
            return self._signal_lookup_cache[cache_key]
        
        # Find message
        msg = self._find_message_by_id(can_id)
        if msg is None:
            self._signal_lookup_cache[cache_key] = (None, None)
            return None, None
        
        # Find signal in message
        for sig in getattr(msg, 'signals', []):
            if sig.name == signal_name:
                result = (msg, sig)
                self._signal_lookup_cache[cache_key] = result
                return result
        
        # Signal not found in message
        self._signal_lookup_cache[cache_key] = (None, None)
        return None, None
    
    def _clear_dbcs_cache(self):
        """Clear DBC-related caches. Call this when DBC is reloaded."""
        # Phase 1: Clear service caches
        if self.dbc_service is not None:
            self.dbc_service.clear_caches()
        if self.signal_service is not None:
            self.signal_service.clear_cache()
        
        # Legacy caches
        self._signal_lookup_cache.clear()
        self._message_cache.clear()
        logger.debug("Cleared DBC lookup caches")
    
    def _parse_can_id(self, text: str) -> Optional[int]:
        """Parse CAN ID from text string (supports hex with 0x prefix or decimal).
        
        Args:
            text: String representation of CAN ID
            
        Returns:
            CAN ID as integer or None if invalid
        """
        if not text or not text.strip():
            return None
        text = text.strip()
        try:
            if text.lower().startswith('0x'):
                return int(text, 16)
            else:
                return int(text, 0)
        except (ValueError, TypeError):
            return None
    
    def _parse_hex_data(self, text: str) -> bytes:
        """Parse hex string to bytes, handling spaces and dashes.
        
        Args:
            text: Hex string (may contain spaces or dashes)
            
        Returns:
            Bytes object or empty bytes if invalid/empty
        """
        if not text or not text.strip():
            return b''
        try:
            cleaned = text.strip().replace(' ', '').replace('-', '')
            return bytes.fromhex(cleaned)
        except (ValueError, TypeError) as e:
            logger.debug(f"Invalid hex data: {e}")
            return b''

    # DBC functions
    def _load_dbcs(self) -> None:
        """Load the list of available DBC files from the persistent store.
        
        Reads the DBC index.json file and populates the DBC list widget
        with available database files. Called during GUI initialization.
        """
        index_path = os.path.join(repo_root, 'backend', 'data', 'dbcs', 'index.json')
        self.dbc_list.clear()
        if os.path.exists(index_path):
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for entry in data.get('dbcs', []):
                    self.dbc_list.addItem(entry.get('original_name') or entry.get('filename'))
            except Exception:
                pass

    def _generate_logo_pixmap(self, w: int = 400, h: int = 120) -> QtGui.QPixmap:
        pix = QtGui.QPixmap(w, h)
        pix.fill(QtGui.QColor('#0b1220'))
        painter = QtGui.QPainter(pix)
        try:
            grad = QtGui.QLinearGradient(0, 0, w, h)
            grad.setColorAt(0.0, QtGui.QColor('#0f172a'))
            grad.setColorAt(1.0, QtGui.QColor('#0b1220'))
            brush = QtGui.QBrush(grad)
            painter.fillRect(0, 0, w, h, brush)
            # draw text
            font = QtGui.QFont('Segoe UI', 28, QtGui.QFont.Bold)
            painter.setFont(font)
            painter.setPen(QtGui.QColor('#7dd3fc'))
            fm = QtGui.QFontMetrics(font)
            text = 'Ergon Labs'
            tw = fm.horizontalAdvance(text)
            painter.drawText((w - tw) / 2, h // 2 + fm.ascent() // 2, text)
            # tagline
            font2 = QtGui.QFont('Segoe UI', 10)
            painter.setFont(font2)
            painter.setPen(QtGui.QColor('#c7f9ff'))
            painter.drawText(12, h - 14, 'EOL Host Application')
        finally:
            painter.end()
        return pix

    def _upload_dbc(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Select DBC file', '', 'DBC files (*.dbc);;All files (*)')
        if not fname:
            return
        dest_dir = os.path.join(repo_root, 'backend', 'data', 'dbcs')
        os.makedirs(dest_dir, exist_ok=True)
        base = os.path.basename(fname)
        # ensure unique filename
        i = 1
        dest = os.path.join(dest_dir, base)
        while os.path.exists(dest):
            name, ext = os.path.splitext(base)
            dest = os.path.join(dest_dir, f"{name}-{i}{ext}")
            i += 1
        try:
            shutil.copyfile(fname, dest)
            # update index.json
            index_path = os.path.join(dest_dir, 'index.json')
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    idx = json.load(f)
            else:
                idx = {'dbcs': []}
            idx['dbcs'].append({'filename': os.path.basename(dest), 'original_name': base, 'uploaded_at': datetime.utcnow().isoformat() + 'Z'})
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(idx, f, indent=2)
            QtWidgets.QMessageBox.information(self, 'Uploaded', f'Uploaded {base} -> {os.path.basename(dest)}')
            self._load_dbcs()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to upload: {e}')

    def _decode_sample(self):
        QtWidgets.QMessageBox.information(self, 'Decode', 'Decode sample frame: not yet implemented in prototype')

    # Test Configurator handlers
    def _on_load_dbc(self):
        # allow user to pick a DBC file, parse with cantools and display its path
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Select DBC file', '', 'DBC files (*.dbc);;All files (*)')
        if not fname:
            return
        self.dbc_path_edit.setText(fname)
        if cantools is None:
            QtWidgets.QMessageBox.warning(self, 'DBC Load', 'cantools not installed in this environment. Install cantools to enable DBC parsing.')
            self._dbc_db = None
            return
        try:
            # cantools provides database.load_file
            try:
                db = cantools.database.load_file(fname)
            except Exception:
                # fallback to older API name
                db = cantools.db.load_file(fname)
            self._dbc_db = db
            # populate nothing global; Create/Edit dialogs will query self._dbc_db when opened
            QtWidgets.QMessageBox.information(self, 'DBC Loaded', f'Loaded DBC: {os.path.basename(fname)} ({len(getattr(db, "messages", []))} messages)')
        except Exception as e:
            self._dbc_db = None
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to parse DBC: {e}')

    def _on_create_test(self):
        # Create a dialog to create a test entry (name, type, actuation mapping)
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Create Test')
        v = QtWidgets.QVBoxLayout(dlg)
        form = QtWidgets.QFormLayout()
        name_edit = QtWidgets.QLineEdit()
        type_combo = QtWidgets.QComboBox()
        type_combo.addItems(['digital', 'analog'])
        feedback_edit = QtWidgets.QLineEdit()
        # actuation fields container
        act_widget = QtWidgets.QWidget()
        act_layout = QtWidgets.QFormLayout(act_widget)
        # separate digital and analog sub-widgets so we can show/hide based on type
        digital_widget = QtWidgets.QWidget()
        digital_layout = QtWidgets.QFormLayout(digital_widget)
        analog_widget = QtWidgets.QWidget()
        analog_layout = QtWidgets.QFormLayout(analog_widget)
    # if a DBC is loaded, provide message+signal dropdowns
        if self._dbc_db is not None:
            # collect messages
            messages = list(getattr(self._dbc_db, 'messages', []))
            msg_display = []
            for m in messages:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                if fid is None:
                    continue
                msg_display.append((m, f"{m.name} (0x{fid:X})"))
            # message combo for digital actuation
            dig_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                dig_msg_combo.addItem(label, fid)
            # signal combo will be populated based on selected message
            dig_signal_combo = QtWidgets.QComboBox()
            def _update_dig_signals(idx=0):
                dig_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    dig_signal_combo.addItems(sigs)
                except Exception:
                    pass
            if msg_display:
                _update_dig_signals(0)
            dig_msg_combo.currentIndexChanged.connect(_update_dig_signals)

            # DAC/analog message combo
            dac_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                dac_msg_combo.addItem(label, fid)

            # value inputs (placed in sub-widgets)
            dig_value_low = QtWidgets.QLineEdit()
            dig_value_high = QtWidgets.QLineEdit()
            # Analog controls: Command Message + several signal dropdowns and numeric params
            mux_chan = QtWidgets.QLineEdit()
            dac_cmd = QtWidgets.QLineEdit()
            # When DBC present, provide signal dropdowns driven by selected DAC message
            dac_command_signal_combo = QtWidgets.QComboBox()
            mux_enable_signal_combo = QtWidgets.QComboBox()
            mux_channel_signal_combo = QtWidgets.QComboBox()
            mux_channel_value_spin = QtWidgets.QSpinBox()
            mux_channel_value_spin.setRange(0, MUX_CHANNEL_MAX)

            def _update_analog_signals(idx=0):
                # populate all signal combos based on selected message index
                for combo in (dac_command_signal_combo, mux_enable_signal_combo, mux_channel_signal_combo, mux_channel_value_spin):
                    try:
                        combo.clear()
                    except Exception:
                        # spinbox doesn't have clear(), ignore
                        pass
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    for combo in (dac_command_signal_combo, mux_enable_signal_combo, mux_channel_signal_combo):
                        combo.addItems(sigs)
                except Exception:
                    pass

            if msg_display:
                _update_analog_signals(0)
            dac_msg_combo.currentIndexChanged.connect(_update_analog_signals)

            # numeric validators for DAC voltages (mV)
            mv_validator = QtGui.QIntValidator(0, 5000, self)
            step_validator = QtGui.QIntValidator(0, 5000, self)
            dwell_validator = QtGui.QIntValidator(0, DWELL_TIME_MAX_MS, self)

            dac_min_mv = QtWidgets.QLineEdit()
            dac_min_mv.setValidator(mv_validator)
            dac_max_mv = QtWidgets.QLineEdit()
            dac_max_mv.setValidator(mv_validator)
            dac_step_mv = QtWidgets.QLineEdit()
            dac_step_mv.setValidator(step_validator)
            dac_dwell_ms = QtWidgets.QLineEdit()
            dac_dwell_ms.setValidator(dwell_validator)
            # digital dwell input
            dig_dwell_ms = QtWidgets.QLineEdit()
            dig_dwell_ms.setValidator(dwell_validator)

            # populate digital sub-widget
            digital_layout.addRow('Command Message:', dig_msg_combo)
            digital_layout.addRow('Actuation Signal:', dig_signal_combo)
            digital_layout.addRow('Value - Low:', dig_value_low)
            digital_layout.addRow('Value - High:', dig_value_high)
            digital_layout.addRow('Dwell Time (ms):', dig_dwell_ms)
            # populate analog sub-widget in requested order
            analog_layout.addRow('Command Message:', dac_msg_combo)
            analog_layout.addRow('DAC Command Signal:', dac_command_signal_combo)
            analog_layout.addRow('MUX Enable Signal:', mux_enable_signal_combo)
            analog_layout.addRow('MUX Channel Signal:', mux_channel_signal_combo)
            analog_layout.addRow('MUX Channel Value:', mux_channel_value_spin)
            analog_layout.addRow('DAC Min Output (mV):', dac_min_mv)
            analog_layout.addRow('DAC Max Output (mV):', dac_max_mv)
            analog_layout.addRow('Step Change (mV):', dac_step_mv)
            analog_layout.addRow('Dwell Time (ms):', dac_dwell_ms)
        else:
            # digital actuation - free text fallback
            dig_can = QtWidgets.QLineEdit()
            dig_signal = QtWidgets.QLineEdit()
            dig_value_low = QtWidgets.QLineEdit()
            dig_value_high = QtWidgets.QLineEdit()
            dig_dwell_ms = QtWidgets.QLineEdit()
            # analog actuation
            mux_chan = QtWidgets.QLineEdit()
            dac_can = QtWidgets.QLineEdit()
            dac_cmd = QtWidgets.QLineEdit()
            # populate sub-widgets
            digital_layout.addRow('Command Message:', dig_can)
            digital_layout.addRow('Actuation Signal:', dig_signal)
            digital_layout.addRow('Value - Low:', dig_value_low)
            digital_layout.addRow('Value - High:', dig_value_high)
            digital_layout.addRow('Dwell Time (ms):', dig_dwell_ms)
            # fallback analog fields when no DBC
            analog_layout.addRow('Command Message (free-text):', mux_chan)
            analog_layout.addRow('DAC CAN ID (analog):', dac_can)
            analog_layout.addRow('DAC Command (hex):', dac_cmd)
            analog_layout.addRow('DAC Min Output (mV):', QtWidgets.QLineEdit())
            analog_layout.addRow('DAC Max Output (mV):', QtWidgets.QLineEdit())
            analog_layout.addRow('Step Change (mV):', QtWidgets.QLineEdit())
            analog_layout.addRow('Dwell Time (ms):', QtWidgets.QLineEdit())

        form.addRow('Name:', name_edit)
        form.addRow('Type:', type_combo)
        # Feedback source and signal (DBC-driven when available)
        if self._dbc_db is not None:
            # build feedback message combo and signal combo
            fb_messages = list(getattr(self._dbc_db, 'messages', []))
            fb_msg_display = []
            for m in fb_messages:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                if fid is None:
                    continue
                fb_msg_display.append((m, f"{m.name} (0x{fid:X})"))
            fb_msg_combo = QtWidgets.QComboBox()
            for m, label in fb_msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                fb_msg_combo.addItem(label, fid)
            fb_signal_combo = QtWidgets.QComboBox()
            def _update_fb_signals(idx=0):
                fb_signal_combo.clear()
                try:
                    m = fb_messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    fb_signal_combo.addItems(sigs)
                except Exception:
                    pass
            if fb_msg_display:
                _update_fb_signals(0)
            fb_msg_combo.currentIndexChanged.connect(_update_fb_signals)
            form.addRow('Feedback Signal Source:', fb_msg_combo)
            form.addRow('Feedback Signal:', fb_signal_combo)
        else:
            form.addRow('Feedback Signal (free-text):', feedback_edit)
        v.addLayout(form)
        # add sub-widgets to container and show only the appropriate one
        act_layout.addRow('Digital:', digital_widget)
        act_layout.addRow('Analog:', analog_widget)
        v.addWidget(QtWidgets.QLabel('Actuation mapping (fill appropriate fields):'))
        v.addWidget(act_widget)

        def _on_type_change(txt: str):
            try:
                if txt == 'digital':
                    digital_widget.show(); analog_widget.hide()
                else:
                    digital_widget.hide(); analog_widget.show()
            except Exception:
                pass
        # initialize visibility
        _on_type_change(type_combo.currentText())
        type_combo.currentTextChanged.connect(_on_type_change)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        v.addWidget(btns)

        def on_accept():
            nm = name_edit.text().strip() or f"test-{len(self._tests)+1}"
            t = type_combo.currentText()
            feedback = feedback_edit.text().strip()
            # build actuation dict depending on type
            if self._dbc_db is not None:
                if t == 'digital':
                    # read selected message id and signal
                    try:
                        can_id = dig_msg_combo.currentData()
                    except Exception:
                        can_id = None
                    sig = dig_signal_combo.currentText().strip() if dig_signal_combo.count() else ''
                    low = dig_value_low.text().strip()
                    high = dig_value_high.text().strip()
                    # optional dwell time for digital in milliseconds
                    try:
                        dig_dwell = int(dig_dwell_ms.text().strip()) if hasattr(dig_dwell_ms, 'text') and dig_dwell_ms.text().strip() else None
                    except Exception:
                        dig_dwell = None
                    act = {
                        'type':'digital',
                        'can_id': can_id,
                        'signal': sig,
                        'value_low': low,
                        'value_high': high,
                        'dwell_ms': dig_dwell,
                    }
                else:
                    # analog: read selected DAC message and related signal selections and numeric params
                    try:
                        dac_id = dac_msg_combo.currentData()
                    except Exception:
                        dac_id = None
                    try:
                        dac_cmd_sig = dac_command_signal_combo.currentText().strip() if dac_command_signal_combo.count() else ''
                    except Exception:
                        dac_cmd_sig = ''
                    try:
                        mux_enable = mux_enable_signal_combo.currentText().strip() if mux_enable_signal_combo.count() else ''
                    except Exception:
                        mux_enable = ''
                    try:
                        mux_chan_sig = mux_channel_signal_combo.currentText().strip() if mux_channel_signal_combo.count() else ''
                    except Exception:
                        mux_chan_sig = ''
                    try:
                        mux_chan_val = int(mux_channel_value_spin.value())
                    except Exception:
                        mux_chan_val = None
                    def _to_int_or_none(txt):
                        try:
                            return int(txt.strip()) if txt and txt.strip() else None
                        except Exception:
                            return None
                    dac_min = _to_int_or_none(dac_min_mv.text() if hasattr(dac_min_mv, 'text') else '')
                    dac_max = _to_int_or_none(dac_max_mv.text() if hasattr(dac_max_mv, 'text') else '')
                    dac_step = _to_int_or_none(dac_step_mv.text() if hasattr(dac_step_mv, 'text') else '')
                    dac_dwell = _to_int_or_none(dac_dwell_ms.text() if hasattr(dac_dwell_ms, 'text') else '')
                    act = {
                        'type': 'analog',
                        'dac_can_id': dac_id,
                        'dac_command_signal': dac_cmd_sig,
                        'mux_enable_signal': mux_enable,
                        'mux_channel_signal': mux_chan_sig,
                        'mux_channel_value': mux_chan_val,
                        'dac_min_mv': dac_min,
                        'dac_max_mv': dac_max,
                        'dac_step_mv': dac_step,
                        'dac_dwell_ms': dac_dwell,
                    }
            else:
                if t == 'digital':
                    try:
                        can_id = int(dig_can.text().strip(), 0) if dig_can.text().strip() else None
                    except Exception:
                        can_id = None
                    # dwell for manual digital entry
                    try:
                        dig_dwell = int(dig_dwell_ms.text().strip()) if hasattr(dig_dwell_ms, 'text') and dig_dwell_ms.text().strip() else None
                    except Exception:
                        dig_dwell = None
                    act = {
                        'type': 'digital',
                        'can_id': can_id,
                        'signal': dig_signal.text().strip(),
                        'value_low': dig_value_low.text().strip(),
                        'value_high': dig_value_high.text().strip(),
                        'dwell_ms': dig_dwell,
                    }
                else:
                    try:
                        mux = int(mux_chan.text().strip(), 0) if mux_chan.text().strip() else None
                    except Exception:
                        mux = None
                    try:
                        dac_id = int(dac_can.text().strip(), 0) if dac_can.text().strip() else None
                    except Exception:
                        dac_id = None
                    act = {
                        'type': 'analog',
                        'mux_channel': mux,
                        'dac_can_id': dac_id,
                        'dac_command': dac_cmd.text().strip()
                    }
            # if using DBC-driven fields, read feedback from combo
            fb_msg_id = None
            if self._dbc_db is not None:
                try:
                    feedback = fb_signal_combo.currentText().strip()
                    fb_msg_id = fb_msg_combo.currentData()
                except Exception:
                    feedback = ''
            else:
                feedback = feedback_edit.text().strip()

            entry = {
                'name': nm,
                'type': t,
                'feedback_signal': feedback,
                'feedback_message_id': fb_msg_id,
                'actuation': act,
                'created_at': datetime.utcnow().isoformat() + 'Z'
            }
            self._tests.append(entry)
            self.test_list.addItem(entry['name'])
            # select the newly added test and update JSON preview
            try:
                self.test_list.setCurrentRow(self.test_list.count() - 1)
                self._on_select_test(None, None)
            except Exception:
                pass
            dlg.accept()

        btns.accepted.connect(on_accept)
        btns.rejected.connect(dlg.reject)
        dlg.exec()

    def _on_delete_test(self):
        it = self.test_list.currentRow()
        if it < 0:
            QtWidgets.QMessageBox.information(self, 'Delete Test', 'No test selected')
            return
        self.test_list.takeItem(it)
        try:
            del self._tests[it]
        except Exception:
            pass
        self.json_preview.clear()

    def _on_save_tests(self) -> None:
        """Save current test configuration to JSON file.
        
        Saves all configured tests to backend/data/tests/tests.json
        in the format defined by the test profile schema.
        """
        default_dir = os.path.join(repo_root, 'backend', 'data', 'tests')
        os.makedirs(default_dir, exist_ok=True)
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save Test Profile', os.path.join(default_dir, 'tests.json'), 'JSON Files (*.json);;All Files (*)'
        )
        if not file_path:
            return  # User cancelled
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({'tests': self._tests}, f, indent=2)
            QtWidgets.QMessageBox.information(self, 'Saved', f'Saved tests to {file_path}')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to save tests: {e}')

    def _on_load_tests(self) -> None:
        """Load test configuration from JSON file.
        
        Loads tests from backend/data/tests/tests.json and populates
        the test list. Validates test structure against schema.
        """
        default_dir = os.path.join(repo_root, 'backend', 'data', 'tests')
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Load Test Profile', default_dir, 'JSON Files (*.json);;All Files (*)'
        )
        if not file_path:
            return  # User cancelled
        if not os.path.exists(file_path):
            QtWidgets.QMessageBox.warning(self, 'Load Tests', 'Selected file does not exist')
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._tests = data.get('tests', [])
            self.test_list.clear()
            for t in self._tests:
                self.test_list.addItem(t.get('name', '<unnamed>'))
            QtWidgets.QMessageBox.information(self, 'Loaded', f'Loaded {len(self._tests)} tests from {file_path}')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to load tests: {e}')

    def _on_test_list_reordered(self, parent, start, end, destination, row):
        # Reorder self._tests to match the new order of the QListWidget
        tests_dict = {t['name']: t for t in self._tests}
        self._tests = [tests_dict[self.test_list.item(i).text()] for i in range(self.test_list.count())]

    def _on_select_test(self, current, previous=None):
        idx = self.test_list.currentRow()
        if idx < 0 or idx >= len(self._tests):
            self.json_preview.clear()
            return
        try:
            self.json_preview.setPlainText(json.dumps(self._tests[idx], indent=2))
        except Exception:
            self.json_preview.setPlainText(str(self._tests[idx]))

    def _on_edit_test(self, item):
        # Edit existing test (prefill create dialog)
        idx = self.test_list.currentRow()
        if idx < 0 or idx >= len(self._tests):
            return
        data = self._tests[idx]
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Edit Test')
        v = QtWidgets.QVBoxLayout(dlg)
        form = QtWidgets.QFormLayout()
        name_edit = QtWidgets.QLineEdit(data.get('name', ''))
        type_combo = QtWidgets.QComboBox()
        type_combo.addItems(['digital', 'analog'])
        try:
            type_combo.setCurrentText(data.get('type', 'digital'))
        except Exception:
            pass

        # prepare feedback source + signal similar to Create dialog
        feedback_edit = QtWidgets.QLineEdit()
        fb_msg_combo = None
        fb_signal_combo = None
        if self._dbc_db is not None:
            fb_messages = list(getattr(self._dbc_db, 'messages', []))
            fb_msg_display = []
            for m in fb_messages:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                if fid is None:
                    continue
                fb_msg_display.append((m, f"{m.name} (0x{fid:X})"))
            fb_msg_combo = QtWidgets.QComboBox()
            for m, label in fb_msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                fb_msg_combo.addItem(label, fid)
            fb_signal_combo = QtWidgets.QComboBox()
            def _update_fb_signals_edit(idx=0):
                fb_signal_combo.clear()
                try:
                    m = fb_messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    fb_signal_combo.addItems(sigs)
                except Exception:
                    pass
            if fb_msg_display:
                _update_fb_signals_edit(0)
            fb_msg_combo.currentIndexChanged.connect(_update_fb_signals_edit)

            # set current message/ signal from stored data
            try:
                stored_mid = data.get('feedback_message_id')
                if stored_mid is not None:
                    for i in range(fb_msg_combo.count()):
                        if fb_msg_combo.itemData(i) == stored_mid:
                            fb_msg_combo.setCurrentIndex(i)
                            _update_fb_signals_edit(i)
                            break
                if data.get('feedback_signal') and fb_signal_combo.count():
                    try:
                        fb_signal_combo.setCurrentText(data.get('feedback_signal'))
                    except Exception:
                        pass
            except Exception:
                pass

        # actuation sub-widgets (digital/analog)
        digital_widget = QtWidgets.QWidget(); digital_layout = QtWidgets.QFormLayout(digital_widget)
        analog_widget = QtWidgets.QWidget(); analog_layout = QtWidgets.QFormLayout(analog_widget)

        # populate actuation controls from stored data
        act = data.get('actuation', {}) or {}
        if self._dbc_db is not None:
            messages = list(getattr(self._dbc_db, 'messages', []))
            msg_display = []
            for m in messages:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                if fid is None:
                    continue
                msg_display.append((m, f"{m.name} (0x{fid:X})"))
            dig_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                dig_msg_combo.addItem(label, fid)
            dig_signal_combo = QtWidgets.QComboBox()
            def _update_dig_signals_edit(idx=0):
                dig_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    dig_signal_combo.addItems(sigs)
                except Exception:
                    pass
            if msg_display:
                _update_dig_signals_edit(0)
            dig_msg_combo.currentIndexChanged.connect(_update_dig_signals_edit)
            dac_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                dac_msg_combo.addItem(label, fid)

            dig_value_low = QtWidgets.QLineEdit(str(act.get('value_low','')))
            dig_value_high = QtWidgets.QLineEdit(str(act.get('value_high','')))
            # analog controls
            mux_chan = QtWidgets.QLineEdit(str(act.get('mux_channel','')))
            dac_cmd = QtWidgets.QLineEdit(str(act.get('dac_command','')))
            dac_command_signal_combo = QtWidgets.QComboBox()
            mux_enable_signal_combo = QtWidgets.QComboBox()
            mux_channel_signal_combo = QtWidgets.QComboBox()
            mux_channel_value_spin = QtWidgets.QSpinBox()
            mux_channel_value_spin.setRange(0, MUX_CHANNEL_MAX)
            # populate analog signal combos based on selected message
            def _update_analog_signals_edit(idx=0):
                for combo in (dac_command_signal_combo, mux_enable_signal_combo, mux_channel_signal_combo):
                    try:
                        combo.clear()
                    except Exception:
                        pass
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    for combo in (dac_command_signal_combo, mux_enable_signal_combo, mux_channel_signal_combo):
                        combo.addItems(sigs)
                except Exception:
                    pass
            if msg_display:
                _update_analog_signals_edit(0)
            dac_msg_combo.currentIndexChanged.connect(_update_analog_signals_edit)
            # set current dac message and signal selections from stored actuation
            try:
                stored_dac_id = act.get('dac_can_id') or act.get('dac_id')
                if stored_dac_id is not None:
                    for i in range(dac_msg_combo.count()):
                        if dac_msg_combo.itemData(i) == stored_dac_id:
                            dac_msg_combo.setCurrentIndex(i)
                            _update_analog_signals_edit(i)
                            break
                # set signal selections
                if act.get('dac_command_signal') and dac_command_signal_combo.count():
                    try:
                        dac_command_signal_combo.setCurrentText(str(act.get('dac_command_signal')))
                    except Exception:
                        pass
                if act.get('mux_enable_signal') and mux_enable_signal_combo.count():
                    try:
                        mux_enable_signal_combo.setCurrentText(str(act.get('mux_enable_signal')))
                    except Exception:
                        pass
                if act.get('mux_channel_signal') and mux_channel_signal_combo.count():
                    try:
                        mux_channel_signal_combo.setCurrentText(str(act.get('mux_channel_signal')))
                    except Exception:
                        pass
                if act.get('mux_channel_value') is not None:
                    try:
                        mux_channel_value_spin.setValue(int(act.get('mux_channel_value')))
                    except Exception:
                        pass
            except Exception:
                pass
            # numeric fields
            dac_min_mv = QtWidgets.QLineEdit(str(act.get('dac_min_mv','')))
            dac_max_mv = QtWidgets.QLineEdit(str(act.get('dac_max_mv','')))
            dac_step_mv = QtWidgets.QLineEdit(str(act.get('dac_step_mv','')))
            dac_dwell_ms = QtWidgets.QLineEdit(str(act.get('dac_dwell_ms','')))
            mv_validator = QtGui.QIntValidator(0, 5000, self)
            step_validator = QtGui.QIntValidator(0, 5000, self)
            dwell_validator = QtGui.QIntValidator(0, DWELL_TIME_MAX_MS, self)
            dac_min_mv.setValidator(mv_validator)
            dac_max_mv.setValidator(mv_validator)
            dac_step_mv.setValidator(step_validator)
            dac_dwell_ms.setValidator(dwell_validator)
            # digital dwell input (edit)
            dig_dwell_ms = QtWidgets.QLineEdit(str(act.get('dwell_ms','')))
            dig_dwell_ms.setValidator(dwell_validator)

            # set current dig message index from actuation can_id
            try:
                canid = act.get('can_id')
                if canid is not None:
                    for i in range(dig_msg_combo.count()):
                        if dig_msg_combo.itemData(i) == canid:
                            dig_msg_combo.setCurrentIndex(i)
                            _update_dig_signals_edit(i)
                            break
                if act.get('signal') and dig_signal_combo.count():
                    try:
                        dig_signal_combo.setCurrentText(act.get('signal'))
                    except Exception:
                        pass
            except Exception:
                pass
            digital_layout.addRow('Command Message:', dig_msg_combo)
            digital_layout.addRow('Actuation Signal:', dig_signal_combo)
            digital_layout.addRow('Value - Low:', dig_value_low)
            digital_layout.addRow('Value - High:', dig_value_high)
            digital_layout.addRow('Dwell Time (ms):', dig_dwell_ms)
            # populate analog sub-widget (DBC-driven)
            analog_layout.addRow('Command Message:', dac_msg_combo)
            analog_layout.addRow('DAC Command Signal:', dac_command_signal_combo)
            analog_layout.addRow('MUX Enable Signal:', mux_enable_signal_combo)
            analog_layout.addRow('MUX Channel Signal:', mux_channel_signal_combo)
            analog_layout.addRow('MUX Channel Value:', mux_channel_value_spin)
            analog_layout.addRow('DAC Min Output (mV):', dac_min_mv)
            analog_layout.addRow('DAC Max Output (mV):', dac_max_mv)
            analog_layout.addRow('Step Change (mV):', dac_step_mv)
            analog_layout.addRow('Dwell Time (ms):', dac_dwell_ms)
        else:
            dig_can = QtWidgets.QLineEdit(str(act.get('can_id','')))
            dig_signal = QtWidgets.QLineEdit(str(act.get('signal','')))
            dig_value_low = QtWidgets.QLineEdit(str(act.get('value_low','')))
            dig_value_high = QtWidgets.QLineEdit(str(act.get('value_high','')))
            # dwell input for fallback (non-DBC)
            dwell_validator = QtGui.QIntValidator(0, DWELL_TIME_MAX_MS, self)
            dig_dwell_ms = QtWidgets.QLineEdit(str(act.get('dwell_ms','')))
            dig_dwell_ms.setValidator(dwell_validator)
            mux_chan = QtWidgets.QLineEdit(str(act.get('mux_channel','')))
            dac_can = QtWidgets.QLineEdit(str(act.get('dac_can_id','')))
            dac_cmd = QtWidgets.QLineEdit(str(act.get('dac_command','')))
            digital_layout.addRow('Command Message:', dig_can)
            digital_layout.addRow('Actuation Signal:', dig_signal)
            digital_layout.addRow('Value - Low:', dig_value_low)
            digital_layout.addRow('Value - High:', dig_value_high)
            digital_layout.addRow('Dwell Time (ms):', dig_dwell_ms)
            # fallback analog layout
            analog_layout.addRow('Command Message (free-text):', mux_chan)
            analog_layout.addRow('DAC CAN ID (analog):', dac_can)
            analog_layout.addRow('DAC Command (hex):', dac_cmd)
            analog_layout.addRow('DAC Min Output (mV):', QtWidgets.QLineEdit(str(act.get('dac_min_mv',''))))
            analog_layout.addRow('DAC Max Output (mV):', QtWidgets.QLineEdit(str(act.get('dac_max_mv',''))))
            analog_layout.addRow('Step Change (mV):', QtWidgets.QLineEdit(str(act.get('dac_step_mv',''))))
            analog_layout.addRow('Dwell Time (ms):', QtWidgets.QLineEdit(str(act.get('dac_dwell_ms',''))))

        form.addRow('Name:', name_edit)
        form.addRow('Type:', type_combo)
        if self._dbc_db is not None:
            form.addRow('Feedback Signal Source:', fb_msg_combo)
            form.addRow('Feedback Signal:', fb_signal_combo)
        else:
            form.addRow('Feedback Signal (free-text):', feedback_edit)

        v.addLayout(form)
        act_layout_parent = QtWidgets.QFormLayout(act_widget := QtWidgets.QWidget())
        act_layout_parent.addRow('Digital:', digital_widget)
        act_layout_parent.addRow('Analog:', analog_widget)
        v.addWidget(QtWidgets.QLabel('Actuation mapping (fill appropriate fields):'))
        v.addWidget(act_widget)

        def _on_type_change_edit(txt: str):
            try:
                if txt == 'digital':
                    digital_widget.show(); analog_widget.hide()
                else:
                    digital_widget.hide(); analog_widget.show()
            except Exception:
                pass

        _on_type_change_edit(type_combo.currentText())
        type_combo.currentTextChanged.connect(_on_type_change_edit)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        v.addWidget(btns)

        def on_accept():
            data['name'] = name_edit.text().strip() or data.get('name')
            data['type'] = type_combo.currentText()
            # feedback
            if self._dbc_db is not None:
                try:
                    data['feedback_message_id'] = fb_msg_combo.currentData()
                    data['feedback_signal'] = fb_signal_combo.currentText().strip()
                except Exception:
                    data['feedback_message_id'] = None
                    data['feedback_signal'] = ''
            else:
                data['feedback_signal'] = feedback_edit.text().strip()

            # actuation
            if self._dbc_db is not None:
                if data['type'] == 'digital':
                    can_id = dig_msg_combo.currentData() if 'dig_msg_combo' in locals() else None
                    sig = dig_signal_combo.currentText().strip() if 'dig_signal_combo' in locals() else ''
                    low = dig_value_low.text().strip()
                    high = dig_value_high.text().strip()
                    # optional dwell time
                    try:
                        dig_dwell = int(dig_dwell_ms.text().strip()) if hasattr(dig_dwell_ms, 'text') and dig_dwell_ms.text().strip() else None
                    except Exception:
                        dig_dwell = None
                    data['actuation'] = {'type':'digital','can_id':can_id,'signal':sig,'value_low':low,'value_high':high,'dwell_ms':dig_dwell}
                else:
                    # analog: capture selected DAC message and signal selections
                    try:
                        dac_id = dac_msg_combo.currentData() if 'dac_msg_combo' in locals() else None
                    except Exception:
                        dac_id = None
                    try:
                        dac_cmd_sig = dac_command_signal_combo.currentText().strip() if 'dac_command_signal_combo' in locals() and dac_command_signal_combo.count() else ''
                    except Exception:
                        dac_cmd_sig = ''
                    try:
                        mux_enable = mux_enable_signal_combo.currentText().strip() if 'mux_enable_signal_combo' in locals() and mux_enable_signal_combo.count() else ''
                    except Exception:
                        mux_enable = ''
                    try:
                        mux_chan_sig = mux_channel_signal_combo.currentText().strip() if 'mux_channel_signal_combo' in locals() and mux_channel_signal_combo.count() else ''
                    except Exception:
                        mux_chan_sig = ''
                    try:
                        mux_chan_val = int(mux_channel_value_spin.value()) if 'mux_channel_value_spin' in locals() else None
                    except Exception:
                        mux_chan_val = None
                    def _to_int_or_none(txt):
                        try:
                            return int(txt.strip()) if txt and txt.strip() else None
                        except Exception:
                            return None
                    dac_min = _to_int_or_none(dac_min_mv.text() if 'dac_min_mv' in locals() else '')
                    dac_max = _to_int_or_none(dac_max_mv.text() if 'dac_max_mv' in locals() else '')
                    dac_step = _to_int_or_none(dac_step_mv.text() if 'dac_step_mv' in locals() else '')
                    dac_dwell = _to_int_or_none(dac_dwell_ms.text() if 'dac_dwell_ms' in locals() else '')
                    data['actuation'] = {
                        'type':'analog',
                        'dac_can_id': dac_id,
                        'dac_command_signal': dac_cmd_sig,
                        'mux_enable_signal': mux_enable,
                        'mux_channel_signal': mux_chan_sig,
                        'mux_channel_value': mux_chan_val,
                        'dac_min_mv': dac_min,
                        'dac_max_mv': dac_max,
                        'dac_step_mv': dac_step,
                        'dac_dwell_ms': dac_dwell,
                    }
            else:
                if data['type'] == 'digital':
                    try:
                        can_id = int(dig_can.text().strip(),0) if dig_can.text().strip() else None
                    except Exception:
                        can_id = None
                    try:
                        dig_dwell = int(dig_dwell_ms.text().strip()) if hasattr(dig_dwell_ms, 'text') and dig_dwell_ms.text().strip() else None
                    except Exception:
                        dig_dwell = None
                    data['actuation'] = {'type':'digital','can_id':can_id,'signal':dig_signal.text().strip(),'value_low':dig_value_low.text().strip(),'value_high':dig_value_high.text().strip(),'dwell_ms':dig_dwell}
                else:
                    try:
                        mux = int(mux_chan.text().strip(),0) if mux_chan.text().strip() else None
                    except Exception:
                        mux = None
                    try:
                        dac_id = int(dac_can.text().strip(),0) if dac_can.text().strip() else None
                    except Exception:
                        dac_id = None
                    data['actuation'] = {'type':'analog','mux_channel':mux,'dac_can_id':dac_id,'dac_command':dac_cmd.text().strip()}

            self._tests[idx] = data
            self.test_list.currentItem().setText(data['name'])
            # refresh JSON preview for current selection
            try:
                self._on_select_test(None, None)
            except Exception:
                pass
            dlg.accept()

        btns.accepted.connect(on_accept)
        btns.rejected.connect(dlg.reject)
        dlg.exec()

    def _on_run_selected(self) -> None:
        """Execute the currently selected test from the test list.
        
        Validates that a test is selected, switches to Test Status tab,
        and executes the test using the TestRunner. Results are displayed
        in the results table and execution log.
        """
        idx = self.test_list.currentRow()
        if idx < 0 or idx >= len(self._tests):
            self.status_label.setText('No test selected')
            self.tabs_main.setCurrentIndex(self.status_tab_index)
            return
        t = self._tests[idx]
        self.tabs_main.setCurrentIndex(self.status_tab_index)
        self.status_label.setText(f'Running test: {t.get("name", "<unnamed>")}')
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.test_log.appendPlainText(f'[{timestamp}] Starting test: {t.get("name", "<unnamed>")}')
        start_time = time.time()
        try:
            # set current feedback signal for UI monitoring
            try:
                self._current_feedback = (t.get('feedback_message_id'), t.get('feedback_signal'))
                if self._current_feedback and self._current_feedback[1]:
                    ts, v = self.get_latest_signal(self._current_feedback[0], self._current_feedback[1])
                    if v is not None:
                        try:
                            self.feedback_signal_label.setText(str(v))
                        except Exception:
                            pass
            except Exception:
                self._current_feedback = None

            ok, info = self._run_single_test(t)
            end_time = time.time()
            exec_time = f"{end_time - start_time:.2f}s"
            result = 'PASS' if ok else 'FAIL'
            self.status_label.setText(f'Test completed: {result}')
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.test_log.appendPlainText(f'[{timestamp}] Result: {result}\n{info}')
            # Add to table
            self._add_result_to_table(t, result, exec_time, info)
        except Exception as e:
            end_time = time.time()
            exec_time = f"{end_time - start_time:.2f}s"
            self.status_label.setText('Test error')
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.test_log.appendPlainText(f'[{timestamp}] Error: {e}')
            self._add_result_to_table(t, 'ERROR', exec_time, str(e))
        finally:
            # clear current feedback monitor
            try:
                self._current_feedback = None
            except Exception:
                pass

    def _on_clear_results(self) -> None:
        """Clear all test results, logs, and plots from the Test Status tab.
        
        Resets the results table, execution log, and clears the feedback
        vs DAC voltage plot. Useful for starting a fresh test session.
        """
        self.results_table.setRowCount(0)
        self.test_log.clear()
        self.status_label.setText('Results cleared')
        # Also clear the plot
        try:
            self._clear_plot()
        except Exception:
            pass

    def _on_repeat_test(self):
        # Repeat the currently selected test
        self._on_run_selected()

    def _on_run_sequence(self) -> None:
        """Execute all configured tests in sequence.
        
        Runs each test in the _tests list sequentially, displaying
        progress in the progress bar and logging results. Provides
        a summary with pass rate and performance metrics at completion.
        """
        if not self._tests:
            self.status_label.setText('No tests to run')
            self.tabs_main.setCurrentIndex(self.status_tab_index)
            return
        self.tabs_main.setCurrentIndex(self.status_tab_index)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(self._tests))
        self.progress_bar.setValue(0)
        self.status_label.setText('Running test sequence...')
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.test_log.appendPlainText(f'[{timestamp}] Starting test sequence')
        results = []
        exec_times = []
        for i, t in enumerate(list(self._tests)):
            self.status_label.setText(f'Running test {i+1}/{len(self._tests)}: {t.get("name","<unnamed>")}')
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.test_log.appendPlainText(f'[{timestamp}] Running test: {t.get("name","<unnamed>")}')
            start_time = time.time()
            try:
                # set current feedback signal for this test
                try:
                    self._current_feedback = (t.get('feedback_message_id'), t.get('feedback_signal'))
                    if self._current_feedback and self._current_feedback[1]:
                        ts, v = self.get_latest_signal(self._current_feedback[0], self._current_feedback[1])
                        if v is not None:
                            try:
                                self.feedback_signal_label.setText(str(v))
                            except Exception:
                                pass
                except Exception:
                    self._current_feedback = None

                ok, info = self._run_single_test(t)
                end_time = time.time()
                exec_time = end_time - start_time
                exec_times.append(exec_time)
                results.append((t.get('name','<unnamed>'), ok, info))
                result = 'PASS' if ok else 'FAIL'
                timestamp = datetime.now().strftime('%H:%M:%S')
                self.test_log.appendPlainText(f'[{timestamp}] Result: {result}\n{info}')
                self._add_result_to_table(t, result, f"{exec_time:.2f}s", info)
            except Exception as e:
                end_time = time.time()
                exec_time = end_time - start_time
                exec_times.append(exec_time)
                results.append((t.get('name','<unnamed>'), False, str(e)))
                timestamp = datetime.now().strftime('%H:%M:%S')
                self.test_log.appendPlainText(f'[{timestamp}] Error: {e}')
                self._add_result_to_table(t, 'ERROR', f"{exec_time:.2f}s", str(e))
            finally:
                # clear current feedback for this test iteration
                try:
                    self._current_feedback = None
                except Exception:
                    pass
            self.progress_bar.setValue(i+1)
        # summarize
        self.progress_bar.setVisible(False)
        summary = '\n'.join([f"{n}: {'PASS' if ok else 'FAIL'} - {info}" for n,ok,info in results])
        # Performance metrics
        pass_count = sum(1 for _, ok, _ in results if ok)
        pass_rate = pass_count / len(results) * 100 if results else 0
        avg_time = sum(exec_times) / len(exec_times) if exec_times else 0
        failure_reasons = [info for _, ok, info in results if not ok]
        failure_summary = '\n'.join(set(failure_reasons)) if failure_reasons else 'None'
        metrics = f"\nPerformance Metrics:\nPass Rate: {pass_rate:.1f}%\nAverage Execution Time: {avg_time:.2f}s\nFailure Reasons: {failure_summary}"
        self.status_label.setText('Sequence completed')
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.test_log.appendPlainText(f'[{timestamp}] Sequence summary:\n{summary}{metrics}')

    def _run_single_test(self, test: Dict[str, Any], timeout: float = 1.0) -> Tuple[bool, str]:
        """Run a single test with validation.
        
        Args:
            test: Test configuration dictionary
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (success: bool, info: str)
        """
        # Validate test structure
        if not isinstance(test, dict):
            logger.error(f"Invalid test format: {type(test)}")
            return False, "Invalid test format"
        if not test.get('name'):
            logger.warning("Test missing name field")
        if not test.get('actuation'):
            logger.error("Test missing actuation field")
            return False, "Test missing actuation configuration"
        
        # Delegate execution to TestRunner (keeps behavior identical but isolates logic)
        runner = TestRunner(self)
        try:
            return runner.run_single_test(test, timeout)
        except Exception as e:
            logger.error(f"Test execution failed: {e}", exc_info=True)
            return False, f"Test execution error: {e}"

    def _toggle_adapter_with_service(self):
        """Connect or disconnect adapter using CanService (Phase 1 implementation)."""
        try:
            selected = self.device_combo.currentText()
        except Exception:
            selected = getattr(self, 'adapter_combo', QtWidgets.QComboBox()).currentText()
        
        logger.info(f"toggle_adapter called (service); connected={self.can_service.is_connected()}; selected={selected}")
        
        if self.can_service.is_connected():
            # Disconnect
            self.can_service.disconnect()
            # Update legacy attributes for compatibility
            self.sim = None
            self.worker = None
            self.poll_timer.stop()
            if self.start_btn is not None:
                self.start_btn.setText('Connect')
            self.conn_indicator.setText('Adapter: stopped')
            logger.info('Adapter disconnected via service')
            return
        
        # Connect
        try:
            success = self.can_service.connect(selected)
            if not success:
                QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to connect to {selected}')
                return
        except (ValueError, RuntimeError) as e:
            logger.error(f"Adapter connection failed: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to connect: {e}')
            return
        
        # Update legacy attributes for compatibility during transition
        self.sim = self.can_service.adapter
        self.worker = self.can_service.worker
        
        # Prompt for DBC file and load
        try:
            fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Select DBC file', '', 'DBC files (*.dbc);;All files (*)')
        except Exception as e:
            logger.warning(f"File dialog error: {e}")
            fname = ''
        
        if fname and self.dbc_service is not None:
            # Update Test Configurator path editor if present
            try:
                self.dbc_path_edit.setText(fname)
            except Exception:
                pass
            
            try:
                self.dbc_service.load_dbc_file(fname)
                # Sync with legacy _dbc_db for compatibility
                self._dbc_db = self.dbc_service.database
                
                # Build filters from DBC messages and apply to adapter
                filters = []
                for m in self.dbc_service.get_all_messages():
                    msg_id = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                    if msg_id is not None:
                        filters.append({'can_id': int(msg_id), 'extended': False})
                
                if filters:
                    self.can_service.set_filters(filters)
                
                message_count = len(self.dbc_service.get_all_messages())
                QtWidgets.QMessageBox.information(self, 'DBC Loaded', f'Loaded DBC: {os.path.basename(fname)} ({message_count} messages)')
            except (FileNotFoundError, ValueError, RuntimeError) as e:
                logger.error(f"Failed to load DBC: {e}", exc_info=True)
                QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to load DBC: {e}')
        
        # Start frame polling
        self.poll_timer.start()
        
        # Update UI
        if self.start_btn is not None:
            self.start_btn.setText('Disconnect')
        self.conn_indicator.setText(f'Adapter: {self.can_service.adapter_name}')
        logger.info(f'Adapter connected via service: {self.can_service.adapter_name}')
        
        # Switch to Live Data tab
        try:
            if hasattr(self, 'stack') and hasattr(self, 'tabs'):
                self.stack.setCurrentWidget(self.tabs)
                try:
                    self.tabs.setCurrentWidget(self.live_widget)
                except Exception:
                    for i in range(self.tabs.count()):
                        if self.tabs.tabText(i).lower() == 'live':
                            self.tabs.setCurrentIndex(i)
                            break
        except Exception:
            pass
        
        # Optional test frame injection
        try:
            if os.environ.get('HOST_GUI_INJECT_TEST_FRAME', '').lower() in ('1', 'true'):
                from backend.adapters.interface import Frame
                test_frame = Frame(can_id=0x123, data=b'\x01\x02\x03', timestamp=time.time())
                logger.debug('[host_gui] injecting deterministic test frame into frame_q')
                self.frame_q.put(test_frame)
        except Exception:
            pass
    
    # Adapter control
    def toggle_adapter(self):
        """Connect or disconnect the CAN adapter.
        
        If no adapter is connected, this will:
        1. Instantiate the selected adapter type (PCAN, PythonCAN, Canalystii, or Sim)
        2. Prompt user to select a DBC file
        3. Load the DBC and apply filters to the adapter
        4. Start background frame reception thread
        
        If adapter is connected, this will:
        1. Stop the background worker thread
        2. Close the adapter connection
        3. Clean up resources
        
        The adapter selection is taken from the device_combo widget, which
        lists available adapter types based on installed hardware/drivers.
        """
        # Phase 1: Use CanService if available, fallback to legacy
        if self.can_service is not None:
            return self._toggle_adapter_with_service()
        
        # Legacy implementation (fallback)
        # If called from welcome connect button, use device_combo if present
        try:
            selected = self.device_combo.currentText()
        except Exception:
            selected = getattr(self, 'adapter_combo', QtWidgets.QComboBox()).currentText()
        logger.info(f"toggle_adapter called (legacy); sim is {'set' if self.sim is not None else 'None'}; selected={selected}")
        if self.sim is None:
            if selected != 'SimAdapter':
                handled = False
                # attempt to instantiate PCAN adapter if selected
                if selected == 'PCAN' and PcanAdapter is not None:
                    try:
                        # use generic CAN settings when creating adapter
                        br = None
                        if str(self._can_bitrate).strip():
                            try:
                                br = int(str(self._can_bitrate).strip())
                            except Exception:
                                br = None
                        self.sim = PcanAdapter(channel=self._can_channel, bitrate=br)
                        self.sim.open()
                        self._adapter_name = 'PCAN'
                        handled = True
                    except Exception as e:
                        logger.error(f"Failed to open PCAN adapter: {e}", exc_info=True)
                        QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to open PCAN adapter: {e}')
                        self.sim = None
                        return
                # Python-can backed adapter
                if selected == 'PythonCAN' and PythonCanAdapter is not None:
                    try:
                        br = None
                        if str(self._can_bitrate).strip():
                            try:
                                br = int(str(self._can_bitrate).strip())
                            except Exception:
                                br = None
                        # channel string from UI; interface can be None to let python-can choose
                        chan = self._can_channel
                        self.sim = PythonCanAdapter(channel=chan, bitrate=br, interface=None)
                        self.sim.open()
                        self._adapter_name = 'PythonCAN'
                        handled = True
                    except Exception as e:
                        logger.error(f"Failed to open PythonCAN adapter: {e}", exc_info=True)
                        QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to open PythonCAN adapter: {e}')
                        self.sim = None
                        return
                # Canalystii via python-can
                if selected == 'Canalystii' and PythonCanAdapter is not None:
                    try:
                        br = None
                        if str(self._can_bitrate).strip():
                            try:
                                br = int(str(self._can_bitrate).strip())
                            except Exception:
                                br = None
                        chan = self._can_channel or '0'
                        # python-can canalystii interface expects channel as string (e.g., '0')
                        # Canalystii python-can backend expects bitrate in bits-per-second; UI provides kbps.
                        if br is not None:
                            try:
                                br = int(br) * 1000
                            except Exception:
                                pass
                        self.sim = PythonCanAdapter(channel=chan, bitrate=br, interface='canalystii')
                        self.sim.open()
                        self._adapter_name = 'Canalystii'
                        handled = True
                    except Exception as e:
                        logger.error(f"Failed to open Canalystii adapter: {e}", exc_info=True)
                        QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to open Canalystii adapter: {e}')
                        self.sim = None
                        return

                if not handled:
                    QtWidgets.QMessageBox.information(self, 'Adapter', f'Adapter {selected} not implemented in prototype; using SimAdapter')
            if self.sim is None and SimAdapter is None:
                msg = 'SimAdapter import failed; ensure running from repository root or install dependencies.'
                if _IMPORT_ERROR is not None:
                    msg += f"\n\nImport error: {_IMPORT_ERROR!r}"
                QtWidgets.QMessageBox.critical(self, 'Import Error', msg)
                return
            # if no adapter created yet, fallback to SimAdapter
            if self.sim is None:
                try:
                    self.sim = SimAdapter()
                    self.sim.open()
                    self._adapter_name = 'Sim'
                except Exception as e:
                    logger.error(f"Failed to open SimAdapter: {e}", exc_info=True)
                    QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to open SimAdapter: {e}')
                    self.sim = None
                    return
            # Prompt user to optionally load a DBC when adapter starts
            try:
                fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Select DBC file', '', 'DBC files (*.dbc);;All files (*)')
            except Exception as e:
                logger.warning(f"File dialog error: {e}")
                fname = ''

            if fname:
                # update Test Configurator path editor if present
                try:
                    self.dbc_path_edit.setText(fname)
                except Exception:
                    pass

                if cantools is None:
                    QtWidgets.QMessageBox.warning(self, 'DBC Load', 'cantools not installed; cannot parse DBC. Adapter will run without filters.')
                    self._dbc_db = None
                else:
                    # attempt to load the DBC using cantools
                    try:
                        try:
                            db = cantools.database.load_file(fname)
                        except Exception:
                            db = cantools.db.load_file(fname)
                    except Exception as e:
                        logger.error(f"Failed to parse DBC file {fname}: {e}", exc_info=True)
                        self._dbc_db = None
                        QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to parse DBC: {e}')
                    else:
                        self._dbc_db = db
                        # Clear cache when DBC is reloaded
                        self._clear_dbcs_cache()
                        # build filters from DBC messages and apply to adapter
                        filters = []
                        for m in getattr(db, 'messages', []):
                            fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                            if fid is None:
                                continue
                            filters.append({'can_id': int(fid), 'extended': False})
                        try:
                            if hasattr(self.sim, 'set_filters'):
                                self.sim.set_filters(filters)
                            QtWidgets.QMessageBox.information(self, 'DBC Loaded', f'Loaded DBC: {os.path.basename(fname)}; applied {len(filters)} filters')
                        except Exception as e:
                            logger.warning(f"Failed to apply filters to adapter: {e}", exc_info=True)
                            QtWidgets.QMessageBox.warning(self, 'Filters', f'Failed to apply filters to adapter: {e}')
            # if no DBC was chosen or parse failed, close adapter and do not start reception
            if not fname or (cantools is not None and getattr(self, '_dbc_db', None) is None):
                try:
                    QtWidgets.QMessageBox.information(self, 'Adapter', 'DBC not loaded; adapter will be closed. Select a DBC to start reception.')
                except Exception:
                    pass
                try:
                    self.sim.close()
                except Exception as e:
                    logger.debug(f"Error closing adapter: {e}")
                self.sim = None
                return

            # Start background reception now that DBC is loaded and filters applied
            try:
                self.worker = AdapterWorker(self.sim, self.frame_q)
                self.worker.start()
                logger.info('Started AdapterWorker and poll timer')
                self.poll_timer.start()
            except Exception as e:
                logger.error(f"Failed to start AdapterWorker: {e}", exc_info=True)

            # update connect button and status
            if self.start_btn is not None:
                self.start_btn.setText('Disconnect')
            self.conn_indicator.setText(f'Adapter: running ({getattr(self, "_adapter_name", "Sim")})')
            # switch to Live view when adapter starts
            try:
                if hasattr(self, 'stack') and hasattr(self, 'tabs'):
                    self.stack.setCurrentWidget(self.tabs)
                    try:
                        self.tabs.setCurrentWidget(self.live_widget)
                    except Exception:
                        for i in range(self.tabs.count()):
                            if self.tabs.tabText(i).lower() == 'live':
                                self.tabs.setCurrentIndex(i)
                                break
            except Exception:
                pass
            # optional deterministic test-frame injection for manual tests
            try:
                if os.environ.get('HOST_GUI_INJECT_TEST_FRAME', '').lower() in ('1', 'true'):
                    class _F: pass
                    f = _F(); f.timestamp = time.time(); f.can_id = 0x123; f.data = b'\x01\x02\x03';
                    logger.debug('[host_gui] injecting deterministic test frame into frame_q')
                    self.frame_q.put(f)
            except Exception:
                pass
        else:
            try:
                if self.worker:
                    self.worker.stop()
                    logger.debug("Stopped AdapterWorker")
            except Exception as e:
                logger.warning(f"Error stopping AdapterWorker: {e}")
            try:
                self.sim.close()
                logger.info("Closed adapter")
            except Exception as e:
                logger.warning(f"Error closing adapter during disconnect: {e}", exc_info=True)
            self.sim = None
            self.worker = None
            self.poll_timer.stop()
            if self.start_btn is not None:
                self.start_btn.setText('Connect')
            self.conn_indicator.setText('Adapter: stopped')
            logger.info('Adapter stopped and cleaned up')


    def _append_msg_log(self, direction: str, frame):
        try:
            ts = getattr(frame, 'timestamp', time.time()) or time.time()
            can_id = getattr(frame, 'can_id', '')
            data = getattr(frame, 'data', b'')
            txt = f"{datetime.fromtimestamp(ts).isoformat()} {direction} ID=0x{can_id:X} LEN={len(data) if isinstance(data,(bytes,bytearray)) else ''} DATA={data.hex() if isinstance(data,(bytes,bytearray)) else str(data)}"
            # append to bottom and auto-scroll
            self.msg_log.addItem(txt)
            try:
                # limit stored messages
                while self.msg_log.count() > self._max_messages:
                    self.msg_log.takeItem(0)
                # auto-scroll to newest
                self.msg_log.scrollToBottom()
            except Exception:
                pass
        except Exception:
            pass

    def _poll_frames(self):
        """Poll the frame queue and add received frames to the frame table.
        
        This method is called periodically by a QTimer to process frames
        that have been received by the AdapterWorker thread and placed
        into frame_q. It processes all available frames in the queue
        during each poll interval.
        """
        try:
            while not self.frame_q.empty():
                f = self.frame_q.get_nowait()
                self._add_frame_row(f)
        except Exception as e:
            logger.debug(f"Error polling frames: {e}")

    def _add_frame_row(self, frame):
        """Add a received CAN frame to the frame table and process it.
        
        Args:
            frame: CAN frame object with attributes: can_id, data, timestamp
        """
        r = self.frame_table.rowCount()
        self.frame_table.insertRow(r)
        ts = getattr(frame, 'timestamp', '')
        can_id = getattr(frame, 'can_id', '')
        data = getattr(frame, 'data', b'')
        self.frame_table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(ts)))
        self.frame_table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(can_id)))
        self.frame_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(len(data) if isinstance(data, (bytes, bytearray)) else '')))
        self.frame_table.setItem(r, 3, QtWidgets.QTableWidgetItem(data.hex() if isinstance(data, (bytes, bytearray)) else str(data)))
        # also append to message log
        try:
            self._append_msg_log('RX', frame)
        except Exception as e:
            logger.debug(f"Error appending to message log: {e}")
        # limit number of rows to latest N
        try:
            while self.frame_table.rowCount() > self._max_frames:
                self.frame_table.removeRow(0)
            # scroll to bottom
            item = self.frame_table.item(self.frame_table.rowCount()-1, 0)
            if item is not None:
                self.frame_table.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtBottom)
        except Exception as e:
            logger.debug(f"Error managing frame table rows: {e}")
        # Also attempt to decode signals from DBC and show in Signal View
        try:
            self._decode_and_add_signals(frame)
        except Exception as e:
            logger.debug(f"Error decoding signals from frame: {e}")

    def _decode_and_add_signals(self, frame):
        """Decode a received CAN frame using loaded DBC and append each signal to Signal View.
        
        This method decodes the frame's data bytes using the DBC database to extract
        individual signal values. Each decoded signal is added to the signal table
        and cached in _signal_values for quick lookup during test execution.
        
        Args:
            frame: CAN frame object with can_id and data attributes
        """
        # Phase 1: Use SignalService if available
        if self.signal_service is not None:
            try:
                # Convert frame to SignalService format
                from backend.adapters.interface import Frame as AdapterFrame
                if not isinstance(frame, AdapterFrame):
                    # Convert from legacy format
                    adapter_frame = AdapterFrame(
                        can_id=getattr(frame, 'can_id', 0),
                        data=getattr(frame, 'data', b''),
                        timestamp=getattr(frame, 'timestamp', None)
                    )
                else:
                    adapter_frame = frame
                
                # Decode signals
                signal_values = self.signal_service.decode_frame(adapter_frame)
                
                # Update UI table (legacy table handling)
                for sig_val in signal_values:
                    key = sig_val.key
                    fid = sig_val.message_id
                    sig_name = sig_val.signal_name
                    val = sig_val.value
                    ts = sig_val.timestamp or time.time()
                    
                    if key in self._signal_rows:
                        row = self._signal_rows[key]
                        try:
                            self.signal_table.setItem(row, 0, QtWidgets.QTableWidgetItem(datetime.fromtimestamp(ts).isoformat()))
                        except Exception:
                            self.signal_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(ts)))
                        self.signal_table.setItem(row, 4, QtWidgets.QTableWidgetItem(str(val)))
                        # Sync legacy cache
                        self._signal_values[key] = (ts, val)
                    else:
                        r = self.signal_table.rowCount()
                        self.signal_table.insertRow(r)
                        try:
                            self.signal_table.setItem(r, 0, QtWidgets.QTableWidgetItem(datetime.fromtimestamp(ts).isoformat()))
                        except Exception:
                            self.signal_table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(ts)))
                        self.signal_table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(sig_val.message_name or '')))
                        self.signal_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(fid)))
                        self.signal_table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(sig_name)))
                        self.signal_table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(val)))
                        self._signal_rows[key] = r
                        # Sync legacy cache
                        self._signal_values[key] = (ts, val)
                    
                    # Update feedback label if this is the current monitored signal
                    try:
                        cur = getattr(self, '_current_feedback', None)
                        if cur and cur[1] and str(cur[1]) == str(sig_name):
                            try:
                                cur_id = int(cur[0]) if cur[0] is not None else None
                                this_id = int(fid)
                                if cur_id is not None and this_id is not None and cur_id == this_id:
                                    try:
                                        self.feedback_signal_label.setText(str(val))
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                    except Exception:
                        pass
                return
            except Exception as e:
                logger.debug(f"SignalService decode failed, falling back to legacy: {e}")
        
        # Legacy implementation (fallback)
        if cantools is None or getattr(self, '_dbc_db', None) is None:
            return
        try:
            fid = int(getattr(frame, 'can_id', 0))
        except Exception:
            return
        target_msg = None
        for m in getattr(self._dbc_db, 'messages', []):
            mid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
            try:
                if mid is not None and int(mid) == fid:
                    target_msg = m
                    break
            except Exception:
                continue
        if target_msg is None:
            return
        # get raw bytes
        raw = getattr(frame, 'data', b'')
        if isinstance(raw, str):
            try:
                raw = bytes.fromhex(raw)
            except Exception:
                raw = b''
        try:
            decoded = target_msg.decode(raw)
        except Exception:
            return
        ts = getattr(frame, 'timestamp', time.time()) or time.time()
        # update each signal into a single persistent row (create if missing)
        for sig_name, val in decoded.items():
            key = f"{fid}:{sig_name}"
            if key in self._signal_rows:
                row = self._signal_rows[key]
                try:
                    self.signal_table.setItem(row, 0, QtWidgets.QTableWidgetItem(datetime.fromtimestamp(ts).isoformat()))
                except Exception:
                    self.signal_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(ts)))
                self.signal_table.setItem(row, 4, QtWidgets.QTableWidgetItem(str(val)))
                # persist latest value (try to store numeric if possible)
                try:
                    num_val = val
                    # attempt to get numeric form by re-decoding without choice labels
                    try:
                        # some cantools versions accept decode_choices=False
                        nd = target_msg.decode(raw, decode_choices=False)
                        if sig_name in nd:
                            num_val = nd.get(sig_name)
                    except TypeError:
                        # decode doesn't accept decode_choices; fall back
                        pass
                    except Exception:
                        pass
                    # attempt numeric coercion if still a string
                    try:
                        if isinstance(num_val, str) and num_val.isdigit():
                            num_val = int(num_val)
                    except Exception:
                        pass
                    self._signal_values[key] = (ts, num_val)
                    # if this signal is currently being monitored for feedback, update the label
                    try:
                        cur = getattr(self, '_current_feedback', None)
                        if cur and cur[1] and str(cur[1]) == str(sig_name):
                            try:
                                cur_id = int(cur[0])
                            except Exception:
                                cur_id = None
                            try:
                                this_id = int(fid)
                            except Exception:
                                this_id = None
                            if cur_id is not None and this_id is not None and cur_id == this_id:
                                try:
                                    self.feedback_signal_label.setText(str(num_val))
                                except Exception:
                                    pass
                    except Exception:
                        pass
                except Exception:
                    pass
            else:
                r = self.signal_table.rowCount()
                self.signal_table.insertRow(r)
                try:
                    self.signal_table.setItem(r, 0, QtWidgets.QTableWidgetItem(datetime.fromtimestamp(ts).isoformat()))
                except Exception:
                    self.signal_table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(ts)))
                self.signal_table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(getattr(target_msg, 'name', ''))))
                self.signal_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(fid)))
                self.signal_table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(sig_name)))
                self.signal_table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(val)))
                self._signal_rows[key] = r
                # persist latest value (try to store numeric if possible)
                try:
                    num_val = val
                    try:
                        nd = target_msg.decode(raw, decode_choices=False)
                        if sig_name in nd:
                            num_val = nd.get(sig_name)
                    except TypeError:
                        pass
                    except Exception:
                        pass
                    try:
                        if isinstance(num_val, str) and num_val.isdigit():
                            num_val = int(num_val)
                    except Exception:
                        pass
                    self._signal_values[key] = (ts, num_val)
                    # if this signal is currently being monitored for feedback, update the label
                    try:
                        cur = getattr(self, '_current_feedback', None)
                        if cur and cur[1] and str(cur[1]) == str(sig_name):
                            try:
                                cur_id = int(cur[0])
                            except Exception:
                                cur_id = None
                            try:
                                this_id = int(fid)
                            except Exception:
                                this_id = None
                            if cur_id is not None and this_id is not None and cur_id == this_id:
                                try:
                                    self.feedback_signal_label.setText(str(num_val))
                                except Exception:
                                    pass
                    except Exception:
                        pass
                except Exception:
                    pass
        # trim if too many rows: remove oldest (row 0) and update mapping
        try:
            while self.signal_table.rowCount() > self._max_messages:
                # capture key for row 0
                try:
                    cid_item = self.signal_table.item(0, 2)
                    sig_item = self.signal_table.item(0, 3)
                    if cid_item is not None and sig_item is not None:
                        try:
                            kcid = cid_item.text()
                        except Exception:
                            kcid = ''
                        try:
                            ksig = sig_item.text()
                        except Exception:
                            ksig = ''
                        k = f"{kcid}:{ksig}"
                        if k in self._signal_rows:
                            try:
                                del self._signal_rows[k]
                            except Exception:
                                pass
                        # also remove persisted value if present
                        try:
                            if k in self._signal_values:
                                del self._signal_values[k]
                        except Exception:
                            pass
                except Exception:
                    pass
                self.signal_table.removeRow(0)
                # decrement indexes
                try:
                    for kk in list(self._signal_rows.keys()):
                        try:
                            if self._signal_rows[kk] > 0:
                                self._signal_rows[kk] = self._signal_rows[kk] - 1
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    def get_latest_signal(self, can_id: int, signal_name: str) -> Tuple[Optional[float], Optional[Any]]:
        """Return (timestamp, value) for the latest observed signal, or (None, None) if unknown.
        
        Args:
            can_id: CAN identifier for the message containing the signal
            signal_name: Name of the signal
            
        Returns:
            Tuple of (timestamp: float or None, value: signal value or None)
        """
        try:
            key = f"{int(can_id)}:{signal_name}"
        except Exception:
            key = f"{can_id}:{signal_name}"
        try:
            return self._signal_values.get(key, (None, None))
        except Exception:
            return (None, None)

    def _send_frame(self):
        """Send a CAN frame manually via the adapter.
        
        Reads CAN ID and data from the send frame UI widgets, validates
        the input, encodes it as a CAN frame, and sends it through the
        connected adapter. The frame is also logged in the message log.
        
        The CAN ID can be specified in hex (0x prefix) or decimal format.
        Data must be a hex string (may contain spaces or dashes).
        """
        # Phase 1: Check CanService first
        if self.can_service is not None:
            if not self.can_service.is_connected():
                QtWidgets.QMessageBox.warning(self, 'Not running', 'Start adapter before sending frames')
                return
            
            try:
                can_id_text = self.send_id.text()
                can_id = self._parse_can_id(can_id_text)
                if can_id is None:
                    raise ValueError("CAN ID is required and must be a valid number")
                
                # Validate CAN ID range
                if not (CAN_ID_MIN <= can_id <= CAN_ID_MAX):
                    raise ValueError(f"CAN ID out of range: 0x{can_id:X} (valid: 0x{CAN_ID_MIN:X}-0x{CAN_ID_MAX:X})")
                
                data_hex = self.send_data.text()
                data_bytes = self._parse_hex_data(data_hex)
                
                # Validate data length
                if len(data_bytes) > CAN_FRAME_MAX_LENGTH:
                    raise ValueError(f"Data too long: {len(data_bytes)} bytes (max: {CAN_FRAME_MAX_LENGTH})")
                
                # Create frame
                from backend.adapters.interface import Frame as AdapterFrame
                frame = AdapterFrame(can_id=can_id, data=data_bytes, timestamp=time.time())
                
                # Send via service
                success = self.can_service.send_frame(frame)
                if success:
                    # Log message
                    self._append_msg_log('TX', frame)
                    logger.debug(f"Sent frame via service: can_id=0x{can_id:X} data={data_bytes.hex()}")
                else:
                    QtWidgets.QMessageBox.warning(self, 'Send Failed', 'Failed to send frame')
                return
            except ValueError as e:
                QtWidgets.QMessageBox.warning(self, 'Invalid Input', str(e))
                return
            except Exception as e:
                logger.error(f"Failed to send frame via service: {e}", exc_info=True)
                QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to send: {e}')
                return
        
        # Legacy implementation (fallback)
        if self.sim is None:
            QtWidgets.QMessageBox.warning(self, 'Not running', 'Start adapter before sending frames')
            return
        try:
            can_id_text = self.send_id.text()
            can_id = self._parse_can_id(can_id_text)
            if can_id is None:
                raise ValueError("CAN ID is required and must be a valid number")
            
            # Validate CAN ID range
            if not (CAN_ID_MIN <= can_id <= CAN_ID_MAX):
                raise ValueError(f"CAN ID {can_id} out of range ({CAN_ID_MIN}-{CAN_ID_MAX:#X})")
            
            data_text = self.send_data.text()
            data = self._parse_hex_data(data_text)
            
            # Validate data length
            if len(data) > CAN_FRAME_MAX_LENGTH:
                raise ValueError(f"Data length {len(data)} exceeds CAN frame max ({CAN_FRAME_MAX_LENGTH} bytes)")
            if AdapterFrame is not None:
                f = AdapterFrame(can_id=can_id, data=data)
            else:
                class F: pass
                f = F(); f.can_id = can_id; f.data = data; f.timestamp = time.time()
            self.sim.send(f)
            logger.debug(f"Sent frame: can_id=0x{can_id:X}, data={data.hex()}")
            if hasattr(self.sim, 'loopback'):
                try:
                    self.sim.loopback(f)
                except Exception as e:
                    logger.debug(f"Loopback failed (non-fatal): {e}")
            try:
                self._append_msg_log('TX', f)
            except Exception as e:
                logger.debug(f"Error appending TX to message log: {e}")
            QtWidgets.QMessageBox.information(self, 'Sent', 'Frame sent')
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid frame data: {e}")
            QtWidgets.QMessageBox.critical(self, 'Error', f'Invalid input: {e}')
        except Exception as e:
            logger.error(f"Failed to send frame: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to send: {e}')


def main():
    """Main entry point for the EOL Host GUI application.
    
    Initializes the Qt application, creates and shows the main window,
    then enters the Qt event loop. The application will run until
    the user closes the window or calls QApplication.quit().
    """
    logger.info(f"Starting host GUI (cwd={os.getcwd()}, python={sys.executable})")
    # create QApplication and show main window
    app = QtWidgets.QApplication(sys.argv)
    win = BaseGUI()
    win.show()
    logger.info('GUI shown; entering Qt event loop')
    sys.exit(app.exec())


if __name__ == '__main__':
    # Simple wrapper to surface startup in terminals and optionally run a headless smoke test
    if '--headless-test' in sys.argv:
        logger.info('[host_gui] Running headless startup test')
        try:
            # create a temporary QApplication so QWidget construction succeeds without entering event loop
            app = QtWidgets.QApplication([])
            _ = BaseGUI()
            logger.info('[host_gui] Headless startup OK')
            # clean up
            try:
                app.quit()
            except Exception:
                pass
            sys.exit(0)
        except Exception:
            import traceback
            traceback.print_exc()
            sys.exit(2)
    else:
        try:
            main()
        except Exception:
            import traceback
            traceback.print_exc()
            raise
