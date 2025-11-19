"""
EOL Host GUI - PySide6-based application for End of Line testing of IPC (Integrated Power Converter).

This module provides a GUI interface for:
- Connecting to CAN bus adapters (PCAN, SocketCAN, PythonCAN, Canalystii, SimAdapter)
- Loading and managing DBC (Database CAN) files for signal decoding
- Configuring and executing test sequences (9 test types)
- Real-time monitoring of CAN frames and decoded signals
- Visualizing test results with live plots
- Managing oscilloscope connections for advanced tests

Architecture:
The application uses a service-based architecture that separates business logic from the GUI layer:
- Services: CanService, DbcService, SignalService, OscilloscopeService, etc.
- ServiceContainer: Dependency injection container for service management
- TestExecutionThread: Async test execution in background thread

Key Components:
- BaseGUI: Main application window with tabs for CAN data, test configurator, and test status
- TestRunner: Test execution logic (supports both GUI and decoupled modes)
- Services: Business logic layer (host_gui/services/)
  - CanService: CAN adapter management and frame transmission
  - DbcService: DBC file loading, parsing, and message/signal operations
  - SignalService: Signal decoding, caching, and value retrieval
  - OscilloscopeService: Oscilloscope connection and configuration
  - TestExecutionService: Decoupled test execution (headless support)
  - TestExecutionThread: Async test execution in background thread

Test Types:
- Digital Logic Test: Apply High/Low voltage to inputs, verify IPC feedback
- Analog Sweep Test: Step DAC voltage from min to max, monitor feedback
- Phase Current Test: Phase current calibration with oscilloscope integration
- Analog Static Test: Static analog measurement comparison
- Analog PWM Sensor: PWM sensor frequency and duty cycle validation
- Temperature Validation Test: Temperature measurement validation
- Fan Control Test: Fan control system testing
- External 5V Test: External 5V power supply testing
- DC Bus Sensing: DC bus voltage sensing with oscilloscope
- Output Current Calibration: Output current sensor calibration with oscilloscope
- Charged HV Bus Test: Charged high voltage bus testing
- Charger Functional Test: Charger functional testing with current validation

Dependencies:
- PySide6: GUI framework
- cantools: DBC parsing and signal encoding/decoding
- matplotlib: Live plotting (optional)
- python-can: CAN bus abstraction layer (via backend adapters)
- pyvisa: Oscilloscope communication (optional, for oscilloscope tests)
"""
import sys
import json
import time
import os
import shutil
import copy
import base64
import re
import struct
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List, Union, Callable
from html import escape

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

# Ensure repo root on sys.path FIRST so imports work correctly
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Configure logging early - this is the single place for logging configuration
# Import config module to use centralized logging configuration
try:
    from host_gui.config import configure_logging
except ImportError:
    # Fallback: try relative import if running as module
    from .config import configure_logging

configure_logging()  # Uses LOG_LEVEL env var or defaults to 'INFO'

logger = logging.getLogger(__name__)

# Import constants - simplified import strategy
# Try relative import first (works when host_gui is a package), then absolute import
try:
    from .constants import (
        CAN_ID_MIN, CAN_ID_MAX, DAC_VOLTAGE_MIN, DAC_VOLTAGE_MAX,
        CAN_FRAME_MAX_LENGTH, DWELL_TIME_DEFAULT, DWELL_TIME_MIN,
        POLL_INTERVAL_MS, FRAME_POLL_INTERVAL_MS, DAC_SETTLING_TIME_MS, DATA_COLLECTION_PERIOD_MS,
        MAX_MESSAGES_DEFAULT, MAX_FRAMES_DEFAULT,
        MSG_TYPE_SET_RELAY, MSG_TYPE_SET_DAC, MSG_TYPE_SET_MUX,
        CAN_BITRATE_DEFAULT, CAN_CHANNEL_DEFAULT,
        WINDOW_WIDTH_DEFAULT, WINDOW_HEIGHT_DEFAULT,
        SLEEP_INTERVAL_SHORT, SLEEP_INTERVAL_MEDIUM,
        MUX_CHANNEL_MAX, DWELL_TIME_MAX_MS,
        LEFT_PANEL_MIN_WIDTH, LOGO_WIDTH, LOGO_HEIGHT,
        PLOT_GRID_ALPHA, ADC_A3_GAIN_FACTOR
    )
except ImportError:
    # Fallback to absolute import (works when run as script or module)
    try:
        from host_gui.constants import (
            CAN_ID_MIN, CAN_ID_MAX, DAC_VOLTAGE_MIN, DAC_VOLTAGE_MAX,
            CAN_FRAME_MAX_LENGTH, DWELL_TIME_DEFAULT, DWELL_TIME_MIN,
            POLL_INTERVAL_MS, FRAME_POLL_INTERVAL_MS, DAC_SETTLING_TIME_MS, DATA_COLLECTION_PERIOD_MS,
            MAX_MESSAGES_DEFAULT, MAX_FRAMES_DEFAULT,
            MSG_TYPE_SET_RELAY, MSG_TYPE_SET_DAC, MSG_TYPE_SET_MUX,
            CAN_BITRATE_DEFAULT, CAN_CHANNEL_DEFAULT,
            WINDOW_WIDTH_DEFAULT, WINDOW_HEIGHT_DEFAULT,
            SLEEP_INTERVAL_SHORT, SLEEP_INTERVAL_MEDIUM,
            MUX_CHANNEL_MAX, DWELL_TIME_MAX_MS,
            LEFT_PANEL_MIN_WIDTH, LOGO_WIDTH, LOGO_HEIGHT,
            PLOT_GRID_ALPHA, ADC_A3_GAIN_FACTOR
        )
    except ImportError:
        # Final fallback: define constants inline (should not happen in normal operation)
        logger.error("Failed to import constants module - using fallback values")
        CAN_ID_MIN = 0
        CAN_ID_MAX = 0x1FFFFFFF
        DAC_VOLTAGE_MIN = 0
        DAC_VOLTAGE_MAX = 5000
        CAN_FRAME_MAX_LENGTH = 8
        DWELL_TIME_DEFAULT = 100
        DWELL_TIME_MIN = 100
        POLL_INTERVAL_MS = 50
        FRAME_POLL_INTERVAL_MS = 150
        DAC_SETTLING_TIME_MS = 20
        DATA_COLLECTION_PERIOD_MS = 50
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
        ADC_A3_GAIN_FACTOR = 1.998

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

# Import exceptions for error handling
try:
    from host_gui.exceptions import SignalDecodeError, DbcError, CanAdapterError
except ImportError:
    # Fallback if exceptions not available
    SignalDecodeError = ValueError
    DbcError = ValueError
    CanAdapterError = RuntimeError

# Import utility functions
try:
    from host_gui.utils import (
        analyze_steady_state_can,
        apply_lowpass_filter,
        apply_moving_average_filter,
        WaveformDecoder
    )
except ImportError:
    # Fallback if utils not available (should not happen)
    logger.error("Failed to import utility modules")
    analyze_steady_state_can = None
    apply_lowpass_filter = None
    apply_moving_average_filter = None
    WaveformDecoder = None

# Import PhaseCurrentTestStateMachine from service
try:
    from host_gui.services.phase_current_service import PhaseCurrentTestStateMachine
except ImportError:
    logger.error("Failed to import PhaseCurrentTestStateMachine from service")
    PhaseCurrentTestStateMachine = None

# AdapterWorker class moved to host_gui/services/can_service.py
# Import from services if needed:
# from host_gui.services.can_service import AdapterWorker
# Pre-compile regex patterns for oscilloscope command parsing
REGEX_ATTN = re.compile(r'ATTN\s+([\d.]+)', re.IGNORECASE)
REGEX_TDIV = re.compile(r'TDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_VDIV = re.compile(r'VDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_OFST = re.compile(r'OFST\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_NUMBER = re.compile(r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)')
REGEX_NUMBER_SIMPLE = re.compile(r'([\d.]+)')
REGEX_TRA = re.compile(r'TRA\s+(\w+)', re.IGNORECASE)

# Import numpy for optimized array operations (optional)
try:
    import numpy as np
    numpy_available = True
except ImportError:
    numpy = None
    numpy_available = False

# Import scipy for signal filtering (optional)
try:
    from scipy import signal
    scipy_available = True
except ImportError:
    signal = None
    scipy_available = False


# Utility functions moved to host_gui/utils/ - imported at top of file


# WaveformDecoder class moved to host_gui/utils/waveform_decoder.py - imported at top of file
# PhaseCurrentTestStateMachine class moved to host_gui/services/phase_current_service.py - imported at top of file
# TestRunner class moved to host_gui/test_runner.py - imported at top of file

from host_gui.test_runner import TestRunner
from host_gui.base_gui import BaseGUI
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
