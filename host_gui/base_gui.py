"""
Base GUI module for EOL Host Application.

This module contains the BaseGUI class, the main application window.
Extracted from main.py for better modularity.

Architecture:
The GUI uses a service-based architecture:
- Services are initialized in __init__() and accessed as attributes
- ServiceContainer provides dependency injection (optional)
- TestExecutionThread handles async test execution
- Services handle all hardware communication (CAN, oscilloscope)

Key Services:
- can_service: CanService instance for CAN adapter management
- dbc_service: DbcService instance for DBC file operations
- signal_service: SignalService instance for signal decoding
- oscilloscope_service: OscilloscopeService instance for oscilloscope management
- service_container: ServiceContainer instance for dependency injection (optional)
- test_execution_thread: TestExecutionThread instance for async test execution

Deprecated Attributes (for backwards compatibility):
- sim: Use can_service instead
- worker: Managed by CanService
- frame_q: Use can_service.frame_queue instead
- _dbc_db: Use dbc_service instead
- _signal_values: Use signal_service instead
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

# Logging is configured centrally in host_gui.config.configure_logging()
# which is called early in main.py. No need to configure here.
logger = logging.getLogger(__name__)

# Ensure repo root on sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Import constants - use same strategy as main.py
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
    # Fallback to absolute import
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
        logger.error("Failed to import constants - using fallback values")
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

# Import services
try:
    from host_gui.services import CanService, DbcService, SignalService
except ImportError:
    logger.error("Failed to import services")
    CanService = None
    DbcService = None
    SignalService = None

# Import exceptions
try:
    from host_gui.exceptions import SignalDecodeError, DbcError, CanAdapterError
except ImportError:
    logger.error("Failed to import exceptions")
    SignalDecodeError = Exception
    DbcError = Exception
    CanAdapterError = Exception

# Import adapters
try:
    from backend.adapters.sim import SimAdapter
    from backend.adapters.interface import Frame as AdapterFrame
except Exception as exc:
    SimAdapter = None
    AdapterFrame = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

try:
    from backend.adapters.pcan import PcanAdapter
except Exception:
    PcanAdapter = None

try:
    from backend.adapters.python_can_adapter import PythonCanAdapter
except Exception:
    PythonCanAdapter = None

# Import utilities
try:
    from host_gui.utils import (
        analyze_steady_state_can,
        apply_lowpass_filter,
        apply_moving_average_filter,
    )
    from host_gui.utils.waveform_decoder import WaveformDecoder
except ImportError:
    logger.error("Failed to import utilities")
    analyze_steady_state_can = None
    apply_lowpass_filter = None
    apply_moving_average_filter = None
    WaveformDecoder = None

# Import numpy and scipy (optional)
try:
    import numpy as np
    numpy_available = True
except ImportError:
    numpy = None
    numpy_available = False

try:
    from scipy import signal
    scipy_available = True
except ImportError:
    signal = None
    scipy_available = False

# Pre-compile regex patterns for oscilloscope command parsing
REGEX_ATTN = re.compile(r'ATTN\s+([\d.]+)', re.IGNORECASE)
REGEX_TDIV = re.compile(r'TDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_VDIV = re.compile(r'VDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_OFST = re.compile(r'OFST\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_NUMBER = re.compile(r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)')
REGEX_NUMBER_SIMPLE = re.compile(r'([\d.]+)')
REGEX_TRA = re.compile(r'TRA\s+(\w+)', re.IGNORECASE)

# Import TestRunner
from host_gui.test_runner import TestRunner

# Import PhaseCurrentTestStateMachine
try:
    from host_gui.services.phase_current_service import PhaseCurrentTestStateMachine
except ImportError:
    logger.error("Failed to import PhaseCurrentTestStateMachine")
    PhaseCurrentTestStateMachine = None


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
        
        # DUT UID management
        current_dut_uid (Optional[int]): The DUT (Device Under Test) UID for the 
            current test sequence. Set when Run Sequence is executed and cleared 
            when results are cleared. This UID is stored as metadata in all test 
            execution data and displayed in test reports.
        dut_uid_input (QLineEdit): Input field for entering DUT UID. Located in 
            Test Status tab next to Run buttons. Validates for positive integers 
            only. Required before running test sequences.
        _cached_dut_uid (Optional[int]): Cached DUT UID value for performance 
            optimization when generating multiple reports.
        _dut_uid_cache_valid (bool): Flag indicating whether the DUT UID cache 
            is valid and can be used.
        
        # Phase 2: Async test execution
        test_execution_thread: TestExecutionThread instance (None when not running)
        
        # Phase 3: Service Container
        service_container: ServiceContainer instance for dependency injection (None if unavailable)
    """
    
    def __init__(self):
        """Initialize the main GUI window and build all UI components."""
        super().__init__()
        
        # Phase 3: Track if services need cleanup on shutdown
        self._services_initialized = False
        self.setWindowTitle('EOL Host - Native GUI')
        
        # Phase 4: Initialize ConfigManager first (must be early, before window sizing and services)
        try:
            from host_gui.config import ConfigManager, configure_logging
            self.config_manager = ConfigManager()
            # Update log level if ConfigManager loaded it from config file (overrides env var)
            if self.config_manager.app_settings.log_level:
                configure_logging(self.config_manager.app_settings.log_level)
                logger.info(f"Log level updated to {self.config_manager.app_settings.log_level} from ConfigManager")
        except Exception as e:
            logger.warning(f"Failed to initialize ConfigManager, using defaults: {e}", exc_info=True)
            self.config_manager = None
        
        # Phase 4: Use window size from ConfigManager if available
        if self.config_manager:
            window_width = self.config_manager.ui_settings.window_width
            window_height = self.config_manager.ui_settings.window_height
            # Try to restore window geometry from QSettings
            saved_geometry = self.config_manager.restore_window_geometry()
            if saved_geometry:
                self.restoreGeometry(saved_geometry)
            else:
                self.resize(window_width, window_height)
        else:
            self.resize(WINDOW_WIDTH_DEFAULT, WINDOW_HEIGHT_DEFAULT)

        # Legacy attributes removed - use services instead:
        # self.sim -> self.can_service.adapter
        # self.worker -> self.can_service.worker
        # self.frame_q -> self.can_service.frame_queue
        
        # Initialize services (Phase 1) - use ConfigManager if available
        if CanService is not None:
            if self.config_manager:
                can_channel = self.config_manager.can_settings.channel
                can_bitrate = self.config_manager.can_settings.bitrate
            else:
                # Fallback to environment variables (backwards compatibility)
                can_channel = os.environ.get('CAN_CHANNEL', os.environ.get('PCAN_CHANNEL', CAN_CHANNEL_DEFAULT))
                try:
                    can_bitrate = int(os.environ.get('CAN_BITRATE', os.environ.get('PCAN_BITRATE', str(CAN_BITRATE_DEFAULT))))
                except Exception:
                    can_bitrate = CAN_BITRATE_DEFAULT
            self.can_service = CanService(channel=can_channel, bitrate=can_bitrate)
            # frame_queue accessed via self.can_service.frame_queue
        else:
            self.can_service = None
        
        # Initialize oscilloscope service
        try:
            from host_gui.services.oscilloscope_service import OscilloscopeService
            self.oscilloscope_service = OscilloscopeService()
        except ImportError:
            logger.warning("OscilloscopeService not available - PyVISA may not be installed")
            self.oscilloscope_service = None
        except Exception as e:
            logger.warning(f"Failed to initialize OscilloscopeService: {e}", exc_info=True)
            self.oscilloscope_service = None
        
        if DbcService is not None:
            self.dbc_service = DbcService()
        else:
            self.dbc_service = None
        
        if SignalService is not None and self.dbc_service is not None:
            self.signal_service = SignalService(self.dbc_service)
        else:
            self.signal_service = None
        
        self._services_initialized = True
        
        # Phase 2: Async test execution thread (initialized when needed)
        try:
            from host_gui.services.test_execution_thread import TestExecutionThread
            self.TestExecutionThread = TestExecutionThread
        except ImportError:
            self.TestExecutionThread = None
        self.test_execution_thread = None
        
        # limits - use ConfigManager if available
        if self.config_manager:
            self._max_messages = self.config_manager.ui_settings.max_messages
            self._max_frames = self.config_manager.ui_settings.max_frames
            self._can_channel = self.config_manager.can_settings.channel
            self._can_bitrate = self.config_manager.can_settings.bitrate
        else:
            # Fallback to defaults
            self._max_messages = MAX_MESSAGES_DEFAULT
            self._max_frames = MAX_FRAMES_DEFAULT
            self._can_channel = os.environ.get('CAN_CHANNEL', os.environ.get('PCAN_CHANNEL', CAN_CHANNEL_DEFAULT))
            try:
                self._can_bitrate = int(os.environ.get('CAN_BITRATE', os.environ.get('PCAN_BITRATE', str(CAN_BITRATE_DEFAULT))))
            except Exception:
                self._can_bitrate = CAN_BITRATE_DEFAULT

        # Shared connection widgets for dialog/backwards compatibility
        self.device_combo = QtWidgets.QComboBox()
        self.refresh_btn = QtWidgets.QPushButton('Refresh')
        self.connect_btn = QtWidgets.QPushButton('Connect')
        self.can_channel_combo = QtWidgets.QComboBox()
        self.can_bitrate_combo = QtWidgets.QComboBox()
        self.oscilloscope_combo = QtWidgets.QComboBox()
        self.osc_refresh_btn = QtWidgets.QPushButton('Refresh')
        self.osc_connect_btn = QtWidgets.QPushButton('Connect')
        self.osc_status_label = QtWidgets.QLabel('Status: Disconnected')
        self.osc_status_label.setStyleSheet('color: gray;')

        self._build_menu()
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

        # Perform initial oscilloscope scan if service is available
        if self.oscilloscope_service is not None:
            try:
                self._refresh_oscilloscopes()
            except Exception as e:
                logger.warning(f"Failed to perform initial oscilloscope scan: {e}")

        # Auto-load last used oscilloscope configuration - DISABLED per user request
        # self._load_last_osc_config()

        self._load_dbcs()
        
        # Signal lookup cache: key = f"{can_id}:{signal_name}" -> (message, signal)
        self._signal_lookup_cache = {}
        self._message_cache = {}  # key = can_id -> message

        # Poll timer for frames
        self.poll_timer = QtCore.QTimer(self)
        self.poll_timer.setInterval(FRAME_POLL_INTERVAL_MS)
        self.poll_timer.timeout.connect(self._poll_frames)

        # Initialize dialog reference
        self._connect_eol_dialog = None

    def _build_menu(self):
        """Build the application menu bar with File, EOL, and Help menus."""
        menubar = self.menuBar()
        
        # Add logo to menu bar (left side)
        logo_label = QtWidgets.QLabel()
        logo_pix = self._generate_logo_pixmap(LOGO_WIDTH, LOGO_HEIGHT)
        logo_label.setPixmap(logo_pix)
        logo_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        logo_label.setContentsMargins(5, 0, 10, 0)
        menubar.setCornerWidget(logo_label, QtCore.Qt.TopLeftCorner)
        
        # File menu
        file_menu = menubar.addMenu('&File')
        exit_act = QtGui.QAction('E&xit', self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # EOL menu (new)
        eol_menu = menubar.addMenu('&EOL')
        connect_eol_act = QtGui.QAction('&Connect EOL', self)
        connect_eol_act.triggered.connect(self._show_connect_eol_dialog)
        eol_menu.addAction(connect_eol_act)

        # Help menu
        help_menu = menubar.addMenu('&Help')
        help_act = QtGui.QAction('&Help', self)
        help_act.triggered.connect(self._open_help)
        help_menu.addAction(help_act)
        about_act = QtGui.QAction('&About', self)
        about_act.triggered.connect(lambda: QtWidgets.QMessageBox.information(self, 'About', 'EOL Host Native GUI'))
        help_menu.addAction(about_act)

    def _show_connect_eol_dialog(self):
        """Show the Connect EOL dialog with CAN and Oscilloscope connection options."""
        if not hasattr(self, '_connect_eol_dialog') or self._connect_eol_dialog is None:
            self._connect_eol_dialog = self._create_connect_eol_dialog()
        self._connect_eol_dialog.show()
        self._connect_eol_dialog.raise_()
        self._connect_eol_dialog.activateWindow()

    def _create_connect_eol_dialog(self) -> QtWidgets.QDialog:
        """Create the Connect EOL dialog window."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle('Connect EOL')
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(500)
        
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # CAN Interface section
        dev_group = QtWidgets.QGroupBox('CAN Interface')
        dg = QtWidgets.QVBoxLayout(dev_group)
        dg.addWidget(self.device_combo)
        hb = QtWidgets.QHBoxLayout()
        try:
            self.refresh_btn.clicked.disconnect()
        except TypeError:
            pass
        self.refresh_btn.clicked.connect(self._refresh_can_devices)
        try:
            self.connect_btn.clicked.disconnect()
        except TypeError:
            pass
        self.connect_btn.clicked.connect(self._connect_selected_device)
        hb.addWidget(self.refresh_btn)
        hb.addWidget(self.connect_btn)
        dg.addLayout(hb)
        layout.addWidget(dev_group)
        
        # CAN Settings section
        can_settings = QtWidgets.QGroupBox('CAN Settings')
        cs_layout = QtWidgets.QFormLayout(can_settings)
        cs_layout.addRow('Channel:', self.can_channel_combo)
        self.can_bitrate_combo.clear()
        bitrate_choices = ['10 kbps','20 kbps','50 kbps','125 kbps','250 kbps','500 kbps','800 kbps','1000 kbps']
        self.can_bitrate_combo.addItems(bitrate_choices)
        self.can_bitrate_combo.setToolTip('Bitrate in kbps (e.g. 500). Canalystii backend will be converted to bps automatically.')
        # Set default if present
        try:
            if self._can_bitrate:
                kb = str(int(self._can_bitrate))
                for i in range(self.can_bitrate_combo.count()):
                    if self.can_bitrate_combo.itemText(i).startswith(kb):
                        self.can_bitrate_combo.setCurrentIndex(i)
                        break
        except Exception as e:
            logger.debug(f"Failed to load CAN settings: {e}")
        cs_layout.addRow('Bitrate (kbps):', self.can_bitrate_combo)
        apply_btn = QtWidgets.QPushButton('Apply')
        def _apply_settings():
            self._can_channel = self.can_channel_combo.currentText().strip() or self._can_channel
            try:
                txt = self.can_bitrate_combo.currentText().strip()
                if txt:
                    self._can_bitrate = int(txt.split()[0])
            except Exception as e:
                logger.warning(f"Failed to save CAN settings: {e}", exc_info=True)
            if self.can_service is not None:
                if self._can_channel:
                    self.can_service.channel = self._can_channel
                if self._can_bitrate:
                    self.can_service.bitrate = self._can_bitrate
                logger.info(f"Updated CanService settings: channel={self.can_service.channel}, bitrate={self.can_service.bitrate}kbps")
            QtWidgets.QMessageBox.information(dialog, 'Settings', 'CAN settings applied')
        apply_btn.clicked.connect(_apply_settings)
        cs_layout.addRow(apply_btn)
        layout.addWidget(can_settings)
        
        # Oscilloscope Connection section
        osc_group = QtWidgets.QGroupBox('Oscilloscope Connection')
        osc_layout = QtWidgets.QVBoxLayout(osc_group)
        self.oscilloscope_combo.clear()
        self.oscilloscope_combo.setToolTip('Select an available oscilloscope (USB or LAN)')
        if self.oscilloscope_service is None:
            self.oscilloscope_combo.addItem('PyVISA not available')
            self.oscilloscope_combo.setEnabled(False)
        osc_layout.addWidget(self.oscilloscope_combo)
        osc_btn_layout = QtWidgets.QHBoxLayout()
        try:
            self.osc_refresh_btn.clicked.disconnect()
        except TypeError:
            pass
        self.osc_refresh_btn.clicked.connect(self._refresh_oscilloscopes)
        if self.oscilloscope_service is None:
            self.osc_refresh_btn.setEnabled(False)
        osc_btn_layout.addWidget(self.osc_refresh_btn)
        try:
            self.osc_connect_btn.clicked.disconnect()
        except TypeError:
            pass
        self.osc_connect_btn.clicked.connect(self._toggle_oscilloscope_connection)
        if self.oscilloscope_service is None:
            self.osc_connect_btn.setEnabled(False)
        osc_btn_layout.addWidget(self.osc_connect_btn)
        osc_layout.addLayout(osc_btn_layout)
        osc_layout.addWidget(self.osc_status_label)
        layout.addWidget(osc_group)
        
        # Device changed handler
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
                channels = [self._can_channel]
            self.can_channel_combo.clear()
            self.can_channel_combo.addItems(channels)
            try:
                self.can_channel_combo.setCurrentIndex(0)
            except Exception:
                pass
        
        self.device_combo.currentTextChanged.connect(_on_device_changed)
        
        # Close button
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        button_box.rejected.connect(dialog.close)
        layout.addWidget(button_box)
        
        # Initialize device list
        self._refresh_can_devices()
        self._refresh_oscilloscopes()
        
        # Set start_btn reference for compatibility
        self.start_btn = self.connect_btn
        
        return dialog

    def _build_eol_hw_configurator(self) -> QtWidgets.QWidget:
        """Builds the EOL H/W Configuration tab widget.
        
        This tab allows users to:
        - Create new EOL hardware configurations
        - Edit existing configurations
        - Load saved configurations
        - Link DBC messages/signals to EOL hardware
        
        Configuration includes:
        - EOL Feedback Message: DBC message that contains feedback data
        - Measured DAC Output Voltage Signal: Signal within that message for DAC measurement
        - EOL Command Message ID: DBC message ID for sending commands to DUT
        - Set DUT Test Mode Signal: Signal within EOL Command Message for setting test mode
        - DUT Feedback Message ID: DBC message ID for receiving feedback from DUT
        - DUT Test Status Signal: Signal within DUT Feedback Message for test status
        
        Returns:
            QWidget containing the EOL H/W Configuration layout
        """
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Top: Action buttons (Create, Edit, Load)
        button_layout = QtWidgets.QHBoxLayout()
        self.eol_create_btn = QtWidgets.QPushButton('Create EOL Configuration')
        self.eol_edit_btn = QtWidgets.QPushButton('Edit EOL Configuration')
        self.eol_load_btn = QtWidgets.QPushButton('Load EOL Configuration')
        self.eol_save_btn = QtWidgets.QPushButton('Save EOL Configuration')
        button_layout.addWidget(self.eol_create_btn)
        button_layout.addWidget(self.eol_edit_btn)
        button_layout.addWidget(self.eol_load_btn)
        button_layout.addWidget(self.eol_save_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Middle: Current Configuration display area
        config_group = QtWidgets.QGroupBox('Current EOL Hardware Configuration')
        config_layout = QtWidgets.QFormLayout()
        
        self.eol_config_name_label = QtWidgets.QLabel('No configuration loaded')
        self.eol_config_name_label.setStyleSheet('color: gray; font-style: italic;')
        self.eol_feedback_msg_label = QtWidgets.QLabel('Not configured')
        self.eol_feedback_msg_label.setStyleSheet('color: gray; font-style: italic;')
        self.eol_dac_signal_label = QtWidgets.QLabel('Not configured')
        self.eol_dac_signal_label.setStyleSheet('color: gray; font-style: italic;')
        
        # New fields
        self.eol_command_msg_label = QtWidgets.QLabel('Not configured')
        self.eol_command_msg_label.setStyleSheet('color: gray; font-style: italic;')
        self.eol_dut_test_mode_signal_label = QtWidgets.QLabel('Not configured')
        self.eol_dut_test_mode_signal_label.setStyleSheet('color: gray; font-style: italic;')
        self.eol_dut_feedback_msg_label = QtWidgets.QLabel('Not configured')
        self.eol_dut_feedback_msg_label.setStyleSheet('color: gray; font-style: italic;')
        self.eol_dut_test_status_signal_label = QtWidgets.QLabel('Not configured')
        self.eol_dut_test_status_signal_label.setStyleSheet('color: gray; font-style: italic;')
        
        config_layout.addRow('Configuration Name:', self.eol_config_name_label)
        config_layout.addRow('EOL Feedback Message:', self.eol_feedback_msg_label)
        config_layout.addRow('Measured DAC Output Voltage Signal:', self.eol_dac_signal_label)
        config_layout.addRow('EOL Command Message ID:', self.eol_command_msg_label)
        config_layout.addRow('Set DUT Test Mode Signal:', self.eol_dut_test_mode_signal_label)
        config_layout.addRow('DUT Feedback Message ID:', self.eol_dut_feedback_msg_label)
        config_layout.addRow('DUT Test Status Signal:', self.eol_dut_test_status_signal_label)
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # Bottom: Saved configurations list
        saved_group = QtWidgets.QGroupBox('Saved Configurations')
        saved_layout = QtWidgets.QVBoxLayout()
        saved_info = QtWidgets.QLabel('Double-click to load a saved configuration')
        saved_info.setStyleSheet('color: gray; font-size: 10px;')
        saved_layout.addWidget(saved_info)
        self.eol_config_list = QtWidgets.QListWidget()
        self.eol_config_list.itemDoubleClicked.connect(self._on_eol_config_list_double_clicked)
        saved_layout.addWidget(self.eol_config_list)
        saved_group.setLayout(saved_layout)
        layout.addWidget(saved_group, 1)
        
        # Store current configuration
        self._eol_hw_config = {
            'name': None,
            'feedback_message_id': None,
            'feedback_message_name': None,
            'measured_dac_signal': None,
            'eol_command_message_id': None,
            'eol_command_message_name': None,
            'set_dut_test_mode_signal': None,
            'dut_feedback_message_id': None,
            'dut_feedback_message_name': None,
            'dut_test_status_signal': None,
            'created_at': None,
            'updated_at': None
        }
        
        # Wire buttons
        self.eol_create_btn.clicked.connect(self._on_create_eol_config)
        self.eol_edit_btn.clicked.connect(self._on_edit_eol_config)
        self.eol_load_btn.clicked.connect(self._on_load_eol_config)
        self.eol_save_btn.clicked.connect(self._on_save_eol_config)
        
        # Refresh saved configurations list
        self._refresh_eol_config_list()
        
        return tab
    
    def _build_oscilloscope_configurator(self) -> QtWidgets.QWidget:
        """Builds the Oscilloscope Configuration tab widget.
        
        This tab allows users to:
        - Create new oscilloscope configurations
        - Edit existing configurations
        - Load saved configurations
        - Save configurations to JSON
        - Apply configurations to connected oscilloscope
        
        Configuration includes:
        - Channel settings (CH1-CH4): Enable, Name, Probe Attenuation, Unit
        - Acquisition settings: Timebase
        
        Returns:
            QWidget containing the Oscilloscope Configuration layout
        """
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Top: Action buttons (Create, Edit, Load, Save, Apply)
        button_layout = QtWidgets.QHBoxLayout()
        self.osc_config_create_btn = QtWidgets.QPushButton('Create Oscilloscope Configuration')
        self.osc_config_edit_btn = QtWidgets.QPushButton('Edit Configuration')
        self.osc_config_load_btn = QtWidgets.QPushButton('Load Configuration')
        self.osc_config_save_btn = QtWidgets.QPushButton('Save Configuration')
        self.osc_config_apply_btn = QtWidgets.QPushButton('Validate Oscilloscope settings')
        self.osc_config_apply_btn.setStyleSheet('font-weight: bold;')
        button_layout.addWidget(self.osc_config_create_btn)
        button_layout.addWidget(self.osc_config_edit_btn)
        button_layout.addWidget(self.osc_config_load_btn)
        button_layout.addWidget(self.osc_config_save_btn)
        button_layout.addWidget(self.osc_config_apply_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Middle: Configuration Parameters
        config_group = QtWidgets.QGroupBox('Configuration Parameters')
        config_layout = QtWidgets.QVBoxLayout()
        
        # Channel Configuration Section
        channel_group = QtWidgets.QGroupBox('Channel Configuration')
        channel_group_layout = QtWidgets.QVBoxLayout()
        
        # Create scroll area for channel configuration
        channel_scroll = QtWidgets.QScrollArea()
        channel_scroll.setWidgetResizable(True)
        channel_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        channel_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        
        # Create container widget for channels
        channel_container = QtWidgets.QWidget()
        channel_layout = QtWidgets.QVBoxLayout(channel_container)
        channel_layout.setContentsMargins(5, 5, 5, 5)
        
        # Channel widgets storage
        self.osc_channel_widgets = {}
        
        for ch_num in [1, 2, 3, 4]:
            ch_key = f'CH{ch_num}'
            ch_widget = QtWidgets.QWidget()
            ch_form = QtWidgets.QFormLayout(ch_widget)
            
            # Enable checkbox
            enable_cb = QtWidgets.QCheckBox()
            enable_cb.setObjectName(f'osc_ch{ch_num}_enable')
            self.osc_channel_widgets[f'{ch_key}_enable'] = enable_cb
            # Use a lambda with proper closure capture
            def make_enable_handler(ch):
                return lambda state: self._on_osc_channel_enable_changed(ch, state == 2)
            enable_cb.stateChanged.connect(make_enable_handler(ch_num))
            ch_form.addRow('Enable:', enable_cb)
            
            # Channel Name
            name_edit = QtWidgets.QLineEdit()
            name_edit.setObjectName(f'osc_ch{ch_num}_name')
            name_edit.setPlaceholderText(f'Enter channel name (e.g., Phase W Current)')
            self.osc_channel_widgets[f'{ch_key}_name'] = name_edit
            ch_form.addRow('Channel Name:', name_edit)
            
            # Probe Attenuation
            probe_spin = QtWidgets.QDoubleSpinBox()
            probe_spin.setObjectName(f'osc_ch{ch_num}_probe')
            probe_spin.setRange(0.1, 1000.0)
            probe_spin.setDecimals(6)
            probe_spin.setSingleStep(0.1)
            probe_spin.setValue(1.0)
            self.osc_channel_widgets[f'{ch_key}_probe'] = probe_spin
            ch_form.addRow('Probe Attenuation:', probe_spin)
            
            # Unit
            unit_combo = QtWidgets.QComboBox()
            unit_combo.setObjectName(f'osc_ch{ch_num}_unit')
            unit_combo.addItems(['V', 'A'])
            unit_combo.setCurrentText('V')
            self.osc_channel_widgets[f'{ch_key}_unit'] = unit_combo
            ch_form.addRow('Unit:', unit_combo)
            
            # Initially disable non-enable fields (CH2-CH4 default to disabled)
            if ch_num == 1:
                enable_cb.setChecked(True)
            else:
                enable_cb.setChecked(False)
                name_edit.setEnabled(False)
                probe_spin.setEnabled(False)
                unit_combo.setEnabled(False)
            
            channel_layout.addWidget(ch_widget)
        
        # Add stretch to push widgets to top
        channel_layout.addStretch()
        
        # Set the container widget as the scroll area's widget
        channel_scroll.setWidget(channel_container)
        
        # Add scroll area to channel group layout
        channel_group_layout.addWidget(channel_scroll)
        channel_group.setLayout(channel_group_layout)
        config_layout.addWidget(channel_group)
        
        # Acquisition Setting Section
        acquisition_group = QtWidgets.QGroupBox('Acquisition Setting')
        acquisition_layout = QtWidgets.QFormLayout()
        
        # Timebase (in milliseconds)
        self.osc_timebase = QtWidgets.QDoubleSpinBox()
        self.osc_timebase.setMinimum(0.001)  # Minimum 0.001 ms
        self.osc_timebase.setMaximum(10000.0)  # Maximum 10000 ms
        self.osc_timebase.setSingleStep(0.1)  # Step size 0.1 ms
        self.osc_timebase.setDecimals(3)  # 3 decimal places
        self.osc_timebase.setValue(1.0)  # Default 1.0 ms
        self.osc_timebase.setSuffix(' ms')
        acquisition_layout.addRow('Timebase:', self.osc_timebase)
        
        acquisition_group.setLayout(acquisition_layout)
        config_layout.addWidget(acquisition_group)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # Status label
        status_layout = QtWidgets.QHBoxLayout()
        self.osc_config_status_label = QtWidgets.QLabel('Status: Not Applied')
        self.osc_config_status_label.setStyleSheet('color: gray; font-weight: bold;')
        status_layout.addWidget(self.osc_config_status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)
        
        # Bottom: Saved configurations list
        saved_group = QtWidgets.QGroupBox('Saved Configurations')
        saved_layout = QtWidgets.QVBoxLayout()
        saved_info = QtWidgets.QLabel('Double-click to load a saved configuration')
        saved_info.setStyleSheet('color: gray; font-size: 10px;')
        saved_layout.addWidget(saved_info)
        self.osc_config_list = QtWidgets.QListWidget()
        self.osc_config_list.itemDoubleClicked.connect(self._on_osc_config_list_double_clicked)
        saved_layout.addWidget(self.osc_config_list)
        saved_group.setLayout(saved_layout)
        layout.addWidget(saved_group, 1)
        
        # Wire buttons
        self.osc_config_create_btn.clicked.connect(self._on_create_osc_config)
        self.osc_config_edit_btn.clicked.connect(self._on_edit_osc_config)
        self.osc_config_load_btn.clicked.connect(self._on_load_osc_config)
        self.osc_config_save_btn.clicked.connect(self._on_save_osc_config)
        self.osc_config_apply_btn.clicked.connect(self._on_apply_osc_config)
        
        # Refresh saved configurations list
        self._refresh_osc_config_list()
        
        return tab
    
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
        self.duplicate_test_btn = QtWidgets.QPushButton('Duplicate Selected Test')
        self.delete_test_btn = QtWidgets.QPushButton('Delete Selected Test')
        self.save_tests_btn = QtWidgets.QPushButton('Save Tests')
        self.load_tests_btn = QtWidgets.QPushButton('Load Tests')
        left_v.addWidget(self.create_test_btn)
        left_v.addWidget(self.duplicate_test_btn)
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
        # DBC database access via dbc_service (legacy _dbc_db removed)
        
        # EOL Hardware Configuration (initialized in _build_eol_hw_configurator if that tab exists)
        # Pre-initialize here in case tab isn't built yet
        self._eol_hw_config = {
            'name': None,
            'feedback_message_id': None,
            'feedback_message_name': None,
            'measured_dac_signal': None,
            'eol_command_message_id': None,
            'eol_command_message_name': None,
            'set_dut_test_mode_signal': None,
            'dut_feedback_message_id': None,
            'dut_feedback_message_name': None,
            'dut_test_status_signal': None,
            'created_at': None,
            'updated_at': None
        }
        
        # Oscilloscope Configuration (initialized in _build_oscilloscope_configurator)
        # Pre-initialize here in case tab isn't built yet
        self._oscilloscope_config = {
            'name': None,
            'version': '1.0',
            'created_at': None,
            'updated_at': None,
            'channels': {
                'CH1': {
                    'enabled': True,
                    'channel_name': 'CH1',
                    'probe_attenuation': 1.0,
                    'unit': 'V'
                },
                'CH2': {
                    'enabled': False,
                    'channel_name': 'CH2',
                    'probe_attenuation': 1.0,
                    'unit': 'V'
                },
                'CH3': {
                    'enabled': False,
                    'channel_name': 'CH3',
                    'probe_attenuation': 1.0,
                    'unit': 'V'
                },
                'CH4': {
                    'enabled': False,
                    'channel_name': 'CH4',
                    'probe_attenuation': 1.0,
                    'unit': 'V'
                }
            },
            'acquisition': {
                'timebase_ms': 1.0
            }
        }
        self._osc_config_file_path = None  # Path to currently loaded config file
        self._osc_config_applied = False  # Track if config was successfully applied
        
        # Test execution data storage: test_name -> {exec_time, notes, parameters}
        # Used to display details in popup when clicking Test Plan rows
        self._test_execution_data = {}
        
        # DUT UID for current test sequence (set when sequence starts)
        # Type: Optional[int] - ensures type safety
        self.current_dut_uid: Optional[int] = None
        
        # DUT UID cache for performance optimization
        self._cached_dut_uid: Optional[int] = None
        self._dut_uid_cache_valid: bool = False
        
        # Temporary storage for plot data captured at the end of run_single_test
        # Key: test_name -> plot_data dictionary
        # This prevents plot data from being lost when the next test clears the plot arrays
        # Data is removed after being retrieved by _on_test_finished/_on_test_failed
        self._test_plot_data_temp = {}

        # run controls will be created in the configurator UI
        self._run_log = []

        # wire buttons
        self.dbc_load_btn.clicked.connect(self._on_load_dbc)
        self.create_test_btn.clicked.connect(self._on_create_test)
        self.duplicate_test_btn.clicked.connect(self._on_duplicate_test)
        self.delete_test_btn.clicked.connect(self._on_delete_test)
        self.save_tests_btn.clicked.connect(self._on_save_tests)
        self.load_tests_btn.clicked.connect(self._on_load_tests)
        self.test_list.currentItemChanged.connect(self._on_select_test)
        self.test_list.itemDoubleClicked.connect(self._on_edit_test)

        # run buttons moved to Test Status tab

        return tab

    def _get_dut_uid_from_execution_data(self, use_cache: bool = True) -> Optional[int]:
        """Extract DUT UID from test execution data.
        
        The DUT UID is stored in each test's execution data when a sequence runs.
        This method retrieves it from the first test that has it, since all tests
        in a sequence share the same DUT UID.
        
        Args:
            use_cache: If True, use cached value if available (performance optimization)
        
        Returns:
            DUT UID as integer if found in any execution data, None otherwise.
            
        Note:
            Returns None if no tests have been executed or if DUT UID was not
            set during sequence execution (e.g., for manually run single tests).
        """
        if use_cache and self._dut_uid_cache_valid and self._cached_dut_uid is not None:
            return self._cached_dut_uid
        
        for exec_data in self._test_execution_data.values():
            dut_uid = exec_data.get('dut_uid')
            if dut_uid is not None:
                # Ensure it's an integer (type safety)
                try:
                    result = int(dut_uid)
                    # Cache the result
                    self._cached_dut_uid = result
                    self._dut_uid_cache_valid = True
                    return result
                except (ValueError, TypeError):
                    logger.warning(f"Invalid DUT UID type found in execution data: {type(dut_uid)}")
                    continue
        
        # Not found - cache the "not found" result too
        self._cached_dut_uid = None
        self._dut_uid_cache_valid = True
        return None
    
    def _get_validated_dut_uid(self) -> Tuple[Optional[int], Optional[str]]:
        """Get and validate DUT UID from input field.
        
        Returns:
            Tuple of (validated_dut_uid: Optional[int], error_message: Optional[str])
            - If valid: (int, None)
            - If empty: (None, "Please enter a DUT UID...")
            - If invalid: (None, "Invalid DUT UID format...")
        """
        if not hasattr(self, 'dut_uid_input'):
            return None, "DUT UID input field not available"
        
        dut_uid_text = self.dut_uid_input.text().strip()
        
        # Check if empty
        if not dut_uid_text:
            return None, "Please enter a DUT UID before running the test sequence."
        
        # Use validator to check format
        validator = self.dut_uid_input.validator()
        if validator is None:
            # Fallback validation if validator not set
            try:
                dut_uid = int(dut_uid_text)
                if dut_uid <= 0:
                    return None, f'DUT UID must be a positive integer. Received: {dut_uid_text}'
                return dut_uid, None
            except ValueError:
                return None, f'DUT UID must be a valid integer. Received: "{dut_uid_text}"'
        
        # Check validator state
        state, value, pos = validator.validate(dut_uid_text, 0)
        
        if state == QtGui.QValidator.Acceptable:
            try:
                dut_uid = int(value)
                if dut_uid <= 0:
                    return None, f'DUT UID must be a positive integer. Received: {dut_uid}'
                return dut_uid, None
            except (ValueError, TypeError):
                return None, f'Could not convert DUT UID to integer: "{value}"'
        elif state == QtGui.QValidator.Intermediate:
            return None, f'DUT UID is incomplete or invalid: "{dut_uid_text}"'
        else:  # Invalid
            return None, f'Invalid DUT UID format: "{dut_uid_text}". Must be a positive integer.'
    
    def _show_dut_uid_error(self, error_type: str, details: str = "") -> None:
        """Show user-friendly DUT UID error message.
        
        Args:
            error_type: Type of error ('empty', 'invalid_format', 'invalid_range', 'type_error')
            details: Additional error details
        """
        messages = {
            'empty': (
                'DUT UID Required',
                'Please enter a DUT UID before running the test sequence.\n\n'
                'The DUT UID is the IPC UID number that identifies the device under test.'
            ),
            'invalid_format': (
                'Invalid DUT UID Format',
                f'DUT UID must be a valid positive integer.\n\n'
                f'Received: "{details}"\n\n'
                f'Please enter a number between 1 and 2,147,483,647.'
            ),
            'invalid_range': (
                'DUT UID Out of Range',
                f'DUT UID must be a positive integer.\n\n'
                f'Received: {details}\n\n'
                f'Please enter a number between 1 and 2,147,483,647.'
            ),
            'type_error': (
                'DUT UID Type Error',
                f'An unexpected error occurred while validating DUT UID.\n\n'
                f'Details: {details}\n\n'
                f'Please try entering the UID again or restart the application.'
            )
        }
        
        title, message = messages.get(error_type, (
            'DUT UID Error',
            f'An error occurred with the DUT UID input.\n\n{details}'
        ))
        
        self.status_label.setText('DUT UID error')
        self.tabs_main.setCurrentIndex(self.status_tab_index)
        QtWidgets.QMessageBox.warning(self, title, message)
        
        # Focus input field for better UX
        if hasattr(self, 'dut_uid_input'):
            self.dut_uid_input.setFocus()
            self.dut_uid_input.selectAll()
    
    def _invalidate_dut_uid_cache(self) -> None:
        """Invalidate DUT UID cache when execution data changes."""
        self._dut_uid_cache_valid = False
        self._cached_dut_uid = None
    
    def _on_dut_uid_changed(self, text: str) -> None:
        """Provide visual feedback on DUT UID input validity.
        
        Args:
            text: Current text in DUT UID input field
        """
        if not hasattr(self, 'dut_uid_input'):
            return
        
        validator = self.dut_uid_input.validator()
        if validator is None:
            return
        
        state, _, _ = validator.validate(text, 0)
        
        # Visual feedback with stylesheet
        if not text.strip():
            # Empty - neutral
            self.dut_uid_input.setStyleSheet("")
        elif state == QtGui.QValidator.Acceptable:
            # Valid - green border
            self.dut_uid_input.setStyleSheet("border: 2px solid green;")
        elif state == QtGui.QValidator.Intermediate:
            # Partial - yellow border
            self.dut_uid_input.setStyleSheet("border: 2px solid orange;")
        else:
            # Invalid - red border
            self.dut_uid_input.setStyleSheet("border: 2px solid red;")

    def _build_test_status(self):
        """Builds the Test Status tab widget and returns it.
        
        The Test Status tab provides:
        - Test execution controls (Run Sequence, Pause Test, Resume Test)
        - Real-time monitoring of current and feedback signals
        - Live plot showing Feedback vs DAC Voltage (for analog tests)
        - Test results table with pass/fail status
        - Execution log with timestamps
        
        Returns:
            QWidget containing the Test Status tab layout
        """
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # Run buttons and DUT UID input
        btn_layout = QtWidgets.QHBoxLayout()
        self.run_seq_btn = QtWidgets.QPushButton('Run Sequence')
        
        # Pause and Resume buttons for test sequences
        self.pause_test_btn = QtWidgets.QPushButton('Pause Test')
        self.resume_test_btn = QtWidgets.QPushButton('Resume Test')
        self.pause_test_btn.setEnabled(False)  # Disabled by default
        self.resume_test_btn.setEnabled(False)  # Disabled by default
        
        # DUT UID input field - required for test sequence execution
        # Located next to Run buttons for easy access
        dut_uid_label = QtWidgets.QLabel('DUT UID:')
        self.dut_uid_input = QtWidgets.QLineEdit()
        self.dut_uid_input.setPlaceholderText('Enter IPC UID number')
        self.dut_uid_input.setMaximumWidth(200)
        self.dut_uid_input.setToolTip('Enter IPC UID number for the test sequence')
        
        # Restrict input to positive integers only (1 to max 32-bit signed int)
        # This prevents invalid data entry and ensures type consistency
        validator = QtGui.QIntValidator(1, 2147483647, self.dut_uid_input)
        self.dut_uid_input.setValidator(validator)
        
        # Connect text changed signal for visual feedback
        self.dut_uid_input.textChanged.connect(self._on_dut_uid_changed)
        
        btn_layout.addWidget(self.run_seq_btn)
        btn_layout.addWidget(self.pause_test_btn)
        btn_layout.addWidget(self.resume_test_btn)
        btn_layout.addWidget(dut_uid_label)
        btn_layout.addWidget(self.dut_uid_input)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Control buttons
        ctrl_layout = QtWidgets.QHBoxLayout()
        self.clear_results_btn = QtWidgets.QPushButton('Clear Results')
        ctrl_layout.addWidget(self.clear_results_btn)
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

        # Create horizontal splitter for two-column layout
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        # Left column: Real-time monitoring, plot, and execution log
        left_column = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Real-time monitoring with compact table view
        monitor_group = QtWidgets.QGroupBox('Real-Time Monitoring')
        monitor_main_layout = QtWidgets.QVBoxLayout(monitor_group)
        monitor_main_layout.setContentsMargins(5, 5, 5, 5)
        
        # Initialize monitoring data structures
        self._monitor_data = {}  # Store signal data: {signal_name: {'value': val, 'timestamp': ts, 'history': []}}
        self._monitor_last_update_times = {}  # Track update times for refresh rate
        self._monitor_sparklines = {}  # Store sparkline widgets
        self._monitor_labels = {}  # Store all label widgets (QTableWidgetItem)
        self._monitor_timestamps = {}  # Store timestamp items (QTableWidgetItem)
        self._monitor_table_rows = {}  # Map signal names to table row indices
        
        # Create compact table
        monitor_table = QtWidgets.QTableWidget(6, 4)  # 6 signals, 4 columns
        monitor_table.setHorizontalHeaderLabels(['Signal', 'Value', 'Trend', 'Updated'])
        monitor_table.horizontalHeader().setStretchLastSection(True)
        monitor_table.verticalHeader().setVisible(False)
        monitor_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        monitor_table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        monitor_table.setAlternatingRowColors(True)
        monitor_table.setMaximumHeight(280)  # Fixed compact height, no scroll needed
        monitor_table.setMinimumHeight(280)
        monitor_table.setShowGrid(True)
        monitor_table.setGridStyle(QtCore.Qt.SolidLine)
        
        # Set column widths
        monitor_table.setColumnWidth(0, 150)  # Signal name
        monitor_table.setColumnWidth(1, 120)  # Value
        monitor_table.setColumnWidth(2, 80)   # Trend (sparkline)
        # Column 3 (Updated) will stretch
        
        # Define signals with their display names and keys
        signals = [
            ('Current Signal', 'current_signal'),
            ('Feedback Signal', 'feedback_signal'),
            ('Enable Relay', 'enable_relay'),
            ('Enable PFC', 'enable_pfc'),
            ('PFC Power Good', 'pfc_power_good'),
            ('Output Current', 'output_current'),
        ]
        
        # Populate table rows
        for row, (display_name, signal_key) in enumerate(signals):
            # Signal name (column 0)
            name_item = QtWidgets.QTableWidgetItem(display_name)
            name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemIsEditable)
            name_item.setTextAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            font = name_item.font()
            font.setBold(True)
            name_item.setFont(font)
            monitor_table.setItem(row, 0, name_item)
            
            # Value (column 1) - will be updated dynamically
            value_item = QtWidgets.QTableWidgetItem('N/A')
            value_item.setFlags(value_item.flags() & ~QtCore.Qt.ItemIsEditable)
            value_item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            value_font = value_item.font()
            value_font.setBold(True)
            value_font.setPointSize(11)
            value_item.setFont(value_font)
            monitor_table.setItem(row, 1, value_item)
            self._monitor_labels[signal_key] = value_item
            self._monitor_table_rows[signal_key] = row
            
            # Sparkline/Trend (column 2)
            if matplotlib_available:
                sparkline = self._create_sparkline_widget()
                if sparkline:
                    monitor_table.setCellWidget(row, 2, sparkline['widget'])
                    monitor_table.setRowHeight(row, 40)  # Make row taller for sparkline
                    self._monitor_sparklines[signal_key] = sparkline
                else:
                    no_trend_item = QtWidgets.QTableWidgetItem('N/A')
                    no_trend_item.setFlags(no_trend_item.flags() & ~QtCore.Qt.ItemIsEditable)
                    no_trend_item.setTextAlignment(QtCore.Qt.AlignCenter)
                    monitor_table.setItem(row, 2, no_trend_item)
            else:
                no_trend_item = QtWidgets.QTableWidgetItem('N/A')
                no_trend_item.setFlags(no_trend_item.flags() & ~QtCore.Qt.ItemIsEditable)
                no_trend_item.setTextAlignment(QtCore.Qt.AlignCenter)
                monitor_table.setItem(row, 2, no_trend_item)
            
            # Timestamp (column 3)
            timestamp_item = QtWidgets.QTableWidgetItem('')
            timestamp_item.setFlags(timestamp_item.flags() & ~QtCore.Qt.ItemIsEditable)
            timestamp_item.setTextAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            timestamp_font = timestamp_item.font()
            timestamp_font.setPointSize(9)
            timestamp_item.setFont(timestamp_font)
            timestamp_item.setForeground(QtGui.QColor('gray'))
            monitor_table.setItem(row, 3, timestamp_item)
            self._monitor_timestamps[signal_key] = timestamp_item
        
        # Store reference to table for backward compatibility
        self.current_signal_label = self._monitor_labels['current_signal']
        self.feedback_signal_label = self._monitor_labels['feedback_signal']
        self.enable_relay_monitor_label = self._monitor_labels['enable_relay']
        self.enable_pfc_monitor_label = self._monitor_labels['enable_pfc']
        self.pfc_power_good_monitor_label = self._monitor_labels['pfc_power_good']
        self.output_current_monitor_label = self._monitor_labels['output_current']
        
        # Store timestamp references for backward compatibility
        self.current_signal_timestamp = self._monitor_timestamps['current_signal']
        self.feedback_signal_timestamp = self._monitor_timestamps['feedback_signal']
        self.enable_relay_timestamp = self._monitor_timestamps['enable_relay']
        self.enable_pfc_timestamp = self._monitor_timestamps['enable_pfc']
        self.pfc_power_good_timestamp = self._monitor_timestamps['pfc_power_good']
        self.output_current_timestamp = self._monitor_timestamps['output_current']
        
        monitor_main_layout.addWidget(monitor_table)
        
        # Refresh rate indicator
        refresh_rate_layout = QtWidgets.QHBoxLayout()
        self.update_rate_label = QtWidgets.QLabel('Update Rate: -- Hz')
        self.update_rate_label.setStyleSheet('font-size: 9pt; color: gray; font-style: italic;')
        refresh_rate_layout.addStretch()
        refresh_rate_layout.addWidget(self.update_rate_label)
        monitor_main_layout.addLayout(refresh_rate_layout)
        
        # Initialize monitor data structures
        for signal_name in ['current_signal', 'feedback_signal', 'enable_relay', 'enable_pfc', 'pfc_power_good', 'output_current']:
            self._monitor_data[signal_name] = {
                'value': None,
                'timestamp': None,
                'history': [],
                'history_max_size': 50  # Keep last 50 values for sparkline
            }
        
        left_layout.addWidget(monitor_group)

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
        left_layout.addWidget(plot_group)

        # Log text area
        self.test_log = QtWidgets.QPlainTextEdit()
        self.test_log.setReadOnly(True)
        
        # Log in a group
        log_group = QtWidgets.QGroupBox('Execution Log')
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.addWidget(self.test_log)
        left_layout.addWidget(log_group)
        
        main_splitter.addWidget(left_column)
        
        # Right column: Test Plan
        # Test Plan table (renamed from Results table)
        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(['Test Name', 'Type', 'Status'])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setAlternatingRowColors(True)
        # Enable single-click to show details
        self.results_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.results_table.itemClicked.connect(self._on_test_plan_item_clicked)
        
        # Test Plan in a group
        table_group = QtWidgets.QGroupBox('Test Plan')
        table_layout = QtWidgets.QVBoxLayout(table_group)
        table_layout.addWidget(self.results_table)
        main_splitter.addWidget(table_group)
        
        # Set splitter proportions (left column gets more space initially)
        main_splitter.setStretchFactor(0, 2)  # Left column
        main_splitter.setStretchFactor(1, 1)  # Right column (Test Plan)
        
        status_layout.addWidget(main_splitter)

        layout.addWidget(status_group)

        # Connect buttons
        self.run_seq_btn.clicked.connect(self._on_run_sequence)
        self.pause_test_btn.clicked.connect(self._on_pause_test)
        self.resume_test_btn.clicked.connect(self._on_resume_test)
        self.clear_results_btn.clicked.connect(self._on_clear_results)

        return tab

    def _populate_test_plan(self) -> None:
        """Populate the Test Plan table with all tests from self._tests.
        
        This method ensures all loaded tests are displayed in the Test Plan,
        with status "Not Run" for tests that haven't been executed yet.
        Tests that have been executed will show their current status.
        """
        # Clear existing rows
        self.results_table.setRowCount(0)
        
        # Add all tests from self._tests
        for test in self._tests:
            test_name = test.get('name', '<unnamed>')
            act = test.get('actuation', {})
            test_type = act.get('type', 'Unknown')
            
            # Check if test has execution data (has been run before)
            exec_data = self._test_execution_data.get(test_name, {})
            status = exec_data.get('status', 'Not Run')
            
            # Add row
            row = self.results_table.rowCount()
            self.results_table.insertRow(row)
            self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(test_name))
            self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(test_type))
            self.results_table.setItem(row, 2, QtWidgets.QTableWidgetItem(status))
    
    def _get_test_parameters_string(self, test: Dict[str, Any]) -> str:
        """Extract parameters string from test configuration.
        
        Args:
            test: Test configuration dictionary
            
        Returns:
            Formatted string with test parameters
        """
        act = test.get('actuation', {})
        test_type = act.get('type', 'Unknown')
        params = []
        
        if test_type == 'Digital Logic Test':
            if act.get('can_id'):
                params.append(f"CAN ID: {act['can_id']}")
            if act.get('signal'):
                params.append(f"Signal: {act['signal']}")
            if act.get('value'):
                params.append(f"Value: {act['value']}")
        elif test_type == 'Analog Sweep Test':
            if act.get('dac_can_id'):
                params.append(f"DAC CAN ID: {act['dac_can_id']}")
            if act.get('dac_command'):
                params.append(f"Command: {act['dac_command']}")
            if act.get('mux_channel') is not None:
                params.append(f"MUX Channel: {act['mux_channel']}")
            if act.get('mux_value') is not None:
                params.append(f"MUX Value: {act['mux_value']}")
            if act.get('mux_enable_signal'):
                params.append(f"MUX Enable Signal: {act['mux_enable_signal']}")
        elif test_type == 'Analog Static Test':
            if act.get('feedback_signal_source'):
                params.append(f"Feedback Source: 0x{act['feedback_signal_source']:X}")
            if act.get('feedback_signal'):
                params.append(f"Feedback Signal: {act['feedback_signal']}")
            if act.get('eol_signal_source'):
                params.append(f"EOL Source: 0x{act['eol_signal_source']:X}")
            if act.get('eol_signal'):
                params.append(f"EOL Signal: {act['eol_signal']}")
            if act.get('tolerance_mv') is not None:
                params.append(f"Tolerance: {act['tolerance_mv']:.2f} mV")
            if act.get('pre_dwell_time_ms') is not None:
                params.append(f"Pre-dwell: {act['pre_dwell_time_ms']} ms")
            if act.get('dwell_time_ms') is not None:
                params.append(f"Dwell: {act['dwell_time_ms']} ms")
        elif test_type == 'Analog PWM Sensor':
            if act.get('feedback_signal_source'):
                params.append(f"Feedback Source: 0x{act['feedback_signal_source']:X}")
            if act.get('feedback_pwm_frequency_signal'):
                params.append(f"PWM Frequency Signal: {act['feedback_pwm_frequency_signal']}")
            if act.get('feedback_duty_signal'):
                params.append(f"Duty Signal: {act['feedback_duty_signal']}")
            if act.get('reference_pwm_frequency') is not None:
                params.append(f"Reference Frequency: {act['reference_pwm_frequency']:.2f} Hz")
            if act.get('reference_duty') is not None:
                params.append(f"Reference Duty: {act['reference_duty']:.2f} %")
            if act.get('pwm_frequency_tolerance') is not None:
                params.append(f"Frequency Tolerance: {act['pwm_frequency_tolerance']:.2f} Hz")
            if act.get('duty_tolerance') is not None:
                params.append(f"Duty Tolerance: {act['duty_tolerance']:.2f} %")
            if act.get('acquisition_time_ms') is not None:
                params.append(f"Acquisition: {act['acquisition_time_ms']} ms")
        elif test_type == 'Temperature Validation Test':
            if act.get('feedback_signal_source'):
                params.append(f"Feedback Source: 0x{act['feedback_signal_source']:X}")
            if act.get('feedback_signal'):
                params.append(f"Feedback Signal: {act['feedback_signal']}")
            if act.get('reference_temperature_c') is not None:
                params.append(f"Reference: {act['reference_temperature_c']:.2f} °C")
            if act.get('tolerance_c') is not None:
                params.append(f"Tolerance: {act['tolerance_c']:.2f} °C")
            if act.get('dwell_time_ms') is not None:
                params.append(f"Dwell: {act['dwell_time_ms']} ms")
        elif test_type == 'DC Bus Sensing':
            if act.get('oscilloscope_channel'):
                params.append(f"Oscilloscope Channel: {act['oscilloscope_channel']}")
            if act.get('feedback_signal_source'):
                params.append(f"Feedback Source: 0x{act['feedback_signal_source']:X}")
            if act.get('feedback_signal'):
                params.append(f"Feedback Signal: {act['feedback_signal']}")
            if act.get('dwell_time_ms') is not None:
                params.append(f"Dwell: {act['dwell_time_ms']} ms")
            if act.get('tolerance_v') is not None:
                params.append(f"Tolerance: {act['tolerance_v']:.4f} V")
        elif test_type == 'Output Current Calibration':
            if act.get('test_trigger_source'):
                params.append(f"Trigger Source: 0x{act['test_trigger_source']:X}")
            if act.get('test_trigger_signal'):
                params.append(f"Trigger Signal: {act['test_trigger_signal']}")
            if act.get('test_trigger_signal_value') is not None:
                params.append(f"Trigger Value: {act['test_trigger_signal_value']}")
            if act.get('current_setpoint_signal'):
                params.append(f"Setpoint Signal: {act['current_setpoint_signal']}")
            if act.get('feedback_signal_source'):
                params.append(f"Feedback Source: 0x{act['feedback_signal_source']:X}")
            if act.get('feedback_signal'):
                params.append(f"Feedback Signal: {act['feedback_signal']}")
            if act.get('oscilloscope_channel'):
                params.append(f"Oscilloscope Channel: {act['oscilloscope_channel']}")
            if act.get('oscilloscope_timebase'):
                params.append(f"Timebase: {act['oscilloscope_timebase']}")
            if act.get('minimum_test_current') is not None:
                params.append(f"Min Current: {act['minimum_test_current']:.2f} A")
            if act.get('maximum_test_current') is not None:
                params.append(f"Max Current: {act['maximum_test_current']:.2f} A")
            if act.get('step_current') is not None:
                params.append(f"Step Current: {act['step_current']:.2f} A")
            if act.get('pre_acquisition_time_ms') is not None:
                params.append(f"Pre-Acq Time: {act['pre_acquisition_time_ms']} ms")
            if act.get('acquisition_time_ms') is not None:
                params.append(f"Acquisition Time: {act['acquisition_time_ms']} ms")
            if act.get('tolerance_percent') is not None:
                params.append(f"Tolerance: {act['tolerance_percent']:.4f}%")
        elif test_type == 'Fan Control Test':
            if act.get('fan_test_trigger_source'):
                params.append(f"Trigger Source: 0x{act['fan_test_trigger_source']:X}")
            if act.get('fan_test_trigger_signal'):
                params.append(f"Trigger Signal: {act['fan_test_trigger_signal']}")
            if act.get('fan_control_feedback_source'):
                params.append(f"Feedback Source: 0x{act['fan_control_feedback_source']:X}")
            if act.get('fan_enabled_signal'):
                params.append(f"Enabled Signal: {act['fan_enabled_signal']}")
            if act.get('fan_tach_feedback_signal'):
                params.append(f"Tach Signal: {act['fan_tach_feedback_signal']}")
        elif test_type == 'Charged HV Bus Test':
            if act.get('command_signal_source'):
                params.append(f"Command Source: 0x{act['command_signal_source']:X}")
            if act.get('test_trigger_signal'):
                params.append(f"Trigger Signal: {act['test_trigger_signal']}")
            if act.get('test_trigger_signal_value') is not None:
                params.append(f"Trigger Value: {act['test_trigger_signal_value']}")
            if act.get('set_output_current_trim_signal'):
                params.append(f"Trim Signal: {act['set_output_current_trim_signal']}")
            if act.get('fallback_output_current_trim_value') is not None:
                params.append(f"Fallback Trim: {act['fallback_output_current_trim_value']:.2f}%")
            if act.get('set_output_current_setpoint_signal'):
                params.append(f"Setpoint Signal: {act['set_output_current_setpoint_signal']}")
            if act.get('output_test_current') is not None:
                params.append(f"Output Current: {act['output_test_current']:.2f} A")
            if act.get('feedback_signal_source'):
                params.append(f"Feedback Source: 0x{act['feedback_signal_source']:X}")
            if act.get('dut_test_state_signal'):
                params.append(f"DUT State Signal: {act['dut_test_state_signal']}")
            if act.get('enable_pfc_signal'):
                params.append(f"Enable PFC Signal: {act['enable_pfc_signal']}")
            if act.get('pfc_power_good_signal'):
                params.append(f"PFC Power Good Signal: {act['pfc_power_good_signal']}")
            if act.get('pcmc_signal'):
                params.append(f"PCMC Signal: {act['pcmc_signal']}")
            if act.get('test_time_ms'):
                params.append(f"Test Time: {act['test_time_ms']} ms")
        elif test_type == 'Charger Functional Test':
            if act.get('command_signal_source'):
                params.append(f"Command Source: 0x{act['command_signal_source']:X}")
            if act.get('test_trigger_signal'):
                params.append(f"Trigger Signal: {act['test_trigger_signal']}")
            if act.get('test_trigger_signal_value') is not None:
                params.append(f"Trigger Value: {act['test_trigger_signal_value']}")
            if act.get('set_output_current_trim_signal'):
                params.append(f"Trim Signal: {act['set_output_current_trim_signal']}")
            if act.get('fallback_output_current_trim_value') is not None:
                params.append(f"Fallback Trim: {act['fallback_output_current_trim_value']:.2f}%")
            if act.get('set_output_current_setpoint_signal'):
                params.append(f"Setpoint Signal: {act['set_output_current_setpoint_signal']}")
            if act.get('output_test_current') is not None:
                params.append(f"Output Current: {act['output_test_current']:.2f} A")
            if act.get('feedback_signal_source'):
                params.append(f"Feedback Source: 0x{act['feedback_signal_source']:X}")
            if act.get('dut_test_state_signal'):
                params.append(f"DUT State Signal: {act['dut_test_state_signal']}")
            if act.get('enable_pfc_signal'):
                params.append(f"Enable PFC Signal: {act['enable_pfc_signal']}")
            if act.get('pfc_power_good_signal'):
                params.append(f"PFC Power Good Signal: {act['pfc_power_good_signal']}")
            if act.get('pcmc_signal'):
                params.append(f"PCMC Signal: {act['pcmc_signal']}")
            if act.get('output_current_signal'):
                params.append(f"Output Current Signal: {act['output_current_signal']}")
            if act.get('output_current_tolerance') is not None:
                params.append(f"Current Tolerance: {act['output_current_tolerance']:.2f} A")
            if act.get('test_time_ms'):
                params.append(f"Test Time: {act['test_time_ms']} ms")
        
        return ', '.join(params) if params else 'None'
    
    def _calculate_calibration_parameters(self, dac_voltages: list, feedback_values: list) -> Optional[Dict[str, float]]:
        """Calculate calibration parameters from DAC voltage and feedback signal data.
        
        Performs linear regression to calculate:
        - Gain/Slope: mV feedback per mV DAC input
        - Offset: Feedback value at DAC = 0mV
        - R²: Correlation coefficient (linearity measure, 0-1)
        - MSE: Mean Squared Error
        - Max Error: Maximum deviation from linear fit
        
        Args:
            dac_voltages: List of DAC output voltages in mV
            feedback_values: List of corresponding feedback signal values
            
        Returns:
            Dictionary with calibration parameters, or None if calculation fails
        """
        if not dac_voltages or not feedback_values:
            return None
        
        if len(dac_voltages) != len(feedback_values):
            logger.warning("DAC voltages and feedback values have different lengths")
            return None
        
        if len(dac_voltages) < 2:
            logger.warning("Need at least 2 data points for linear regression")
            return None
        
        try:
            import numpy as np
            
            x = np.array(dac_voltages, dtype=float)
            y = np.array(feedback_values, dtype=float)
            
            # Linear regression: y = mx + b
            # m = gain/slope, b = offset
            n = len(x)
            sum_x = np.sum(x)
            sum_y = np.sum(y)
            sum_xy = np.sum(x * y)
            sum_x2 = np.sum(x * x)
            sum_y2 = np.sum(y * y)
            
            # Calculate slope (gain)
            denominator = n * sum_x2 - sum_x * sum_x
            if abs(denominator) < 1e-10:
                logger.warning("Cannot calculate gain: denominator too small (data may be constant)")
                return None
            
            gain = (n * sum_xy - sum_x * sum_y) / denominator
            
            # Calculate offset (y-intercept)
            offset = (sum_y - gain * sum_x) / n
            
            # Calculate R² (coefficient of determination)
            y_predicted = gain * x + offset
            ss_res = np.sum((y - y_predicted) ** 2)  # Sum of squared residuals
            ss_tot = np.sum((y - np.mean(y)) ** 2)   # Total sum of squares
            
            if abs(ss_tot) < 1e-10:
                r_squared = 1.0  # Perfect fit or constant data
            else:
                r_squared = 1 - (ss_res / ss_tot)
            
            # Calculate Mean Squared Error
            mse = ss_res / n
            
            # Calculate maximum error
            errors = np.abs(y - y_predicted)
            max_error = np.max(errors)
            mean_error = np.mean(errors)
            
            return {
                'gain': float(gain),
                'offset': float(offset),
                'r_squared': float(r_squared),
                'mse': float(mse),
                'max_error': float(max_error),
                'mean_error': float(mean_error),
                'data_points': n
            }
        except ImportError:
            # Fallback calculation without numpy
            try:
                n = len(dac_voltages)
                sum_x = sum(dac_voltages)
                sum_y = sum(feedback_values)
                sum_xy = sum(x * y for x, y in zip(dac_voltages, feedback_values))
                sum_x2 = sum(x * x for x in dac_voltages)
                sum_y2 = sum(y * y for y in feedback_values)
                
                denominator = n * sum_x2 - sum_x * sum_x
                if abs(denominator) < 1e-10:
                    return None
                
                gain = (n * sum_xy - sum_x * sum_y) / denominator
                offset = (sum_y - gain * sum_x) / n
                
                # Calculate R²
                y_mean = sum_y / n
                ss_res = sum((y - (gain * x + offset)) ** 2 for x, y in zip(dac_voltages, feedback_values))
                ss_tot = sum((y - y_mean) ** 2 for y in feedback_values)
                
                if abs(ss_tot) < 1e-10:
                    r_squared = 1.0
                else:
                    r_squared = 1 - (ss_res / ss_tot)
                
                # Calculate errors
                errors = [abs(y - (gain * x + offset)) for x, y in zip(dac_voltages, feedback_values)]
                mse = ss_res / n
                max_error = max(errors)
                mean_error = sum(errors) / n
                
                return {
                    'gain': gain,
                    'offset': offset,
                    'r_squared': r_squared,
                    'mse': mse,
                    'max_error': max_error,
                    'mean_error': mean_error,
                    'data_points': n
                }
            except Exception as e:
                logger.error(f"Error calculating calibration parameters: {e}", exc_info=True)
                return None
        except Exception as e:
            logger.error(f"Error calculating calibration parameters: {e}", exc_info=True)
            return None
    
    def _update_test_plan_row(self, test: Dict[str, Any], status: str, exec_time: str, notes: str, 
                             plot_data: Optional[Dict[str, list]] = None) -> None:
        """Update or insert a test result row in the Test Plan table.
        
        Uses test name as the unique key. If a row with the same test name exists,
        it updates the status. Otherwise, it inserts a new row. Execution data
        (exec_time, notes, parameters) are stored separately for popup display.
        
        Args:
            test: Test configuration dictionary
            status: Test status ('PASS', 'FAIL', 'ERROR', 'Running...')
            exec_time: Execution time as string (e.g., "1.23s")
            notes: Additional information or error details
            plot_data: Optional dictionary with 'dac_voltages' and 'feedback_values' lists for analog tests
        """
        test_name = test.get('name', '<unnamed>')
        act = test.get('actuation', {})
        test_type_raw = act.get('type', 'Unknown')
        # Use display name directly (types are now stored with display names)
        test_type = test_type_raw
        
        # Store execution data for popup display
        params_str = self._get_test_parameters_string(test)
        
        # CRITICAL: Preserve existing execution data (especially statistics) if it exists
        # This prevents overwriting statistics that were set immediately in test_runner.py
        existing_exec_data = self._test_execution_data.get(test_name, {})
        existing_statistics = existing_exec_data.get('statistics')
        
        exec_data = {
            'status': status,
            'exec_time': exec_time,
            'notes': notes,
            'parameters': params_str,
            'test_type': test_type
        }
        
        # Preserve existing statistics if they exist (they may have been set immediately in test_runner.py)
        if existing_statistics is not None:
            exec_data['statistics'] = existing_statistics
            logger.debug(f"_update_test_plan_row: Preserved existing statistics for '{test_name}'")
        
        # Add DUT UID metadata if available (from current test sequence)
        # Ensure type safety - always store as integer
        if self.current_dut_uid is not None:
            try:
                exec_data['dut_uid'] = int(self.current_dut_uid)
            except (ValueError, TypeError) as e:
                logger.error(
                    f"Invalid DUT UID type in current_dut_uid: {type(self.current_dut_uid)}. "
                    f"Value: {self.current_dut_uid}. Error: {e}"
                )
                # Don't store invalid UID - invalidate cache
                self._invalidate_dut_uid_cache()
        
        # Store plot data for analog tests and phase current calibration tests (make a copy to preserve data)
        if plot_data is not None:
            test_type = test.get('type', '')
            
            if test_type == 'Analog Sweep Test':
                dac_voltages = list(plot_data.get('dac_voltages', []))
                feedback_values = list(plot_data.get('feedback_values', []))
                
                exec_data['plot_data'] = {
                    'dac_voltages': dac_voltages,
                    'feedback_values': feedback_values
                }
                
                # Calculate calibration parameters for analog tests
                if dac_voltages and feedback_values and len(dac_voltages) == len(feedback_values):
                    calibration_params = self._calculate_calibration_parameters(dac_voltages, feedback_values)
                    if calibration_params:
                        # Calculate gain error percentage if expected gain is available
                        actuation = test.get('actuation', {})
                        expected_gain = actuation.get('expected_gain')
                        if expected_gain is not None:
                            try:
                                expected_gain = float(expected_gain)
                                actual_gain = calibration_params.get('gain', 0)
                                if abs(expected_gain) > 1e-10 and abs(actual_gain) > 1e-10:
                                    # Gain error percentage = ((Actual - Expected) / Expected) * 100
                                    gain_error_percent = ((actual_gain - expected_gain) / expected_gain) * 100.0
                                    calibration_params['gain_error_percent'] = gain_error_percent
                                    calibration_params['expected_gain'] = expected_gain
                                    
                                    # Check gain tolerance for pass/fail determination
                                    gain_tolerance = actuation.get('gain_tolerance_percent')
                                    if gain_tolerance is not None:
                                        try:
                                            gain_tolerance = float(gain_tolerance)
                                            if abs(gain_error_percent) > gain_tolerance:
                                                # Gain error exceeds tolerance - test should fail
                                                if status == 'PASS':
                                                    status = 'FAIL'
                                                    notes = (notes + '\n' if notes else '') + \
                                                        f"Gain error {gain_error_percent:+.4f}% exceeds tolerance of ±{gain_tolerance:.2f}%"
                                                    logger.warning(
                                                        f"Test '{test_name}': Gain error {gain_error_percent:+.4f}% "
                                                        f"exceeds tolerance ±{gain_tolerance:.2f}% - marking as FAIL"
                                                    )
                                                calibration_params['tolerance_check'] = 'FAIL'
                                            else:
                                                calibration_params['tolerance_check'] = 'PASS'
                                                logger.debug(
                                                    f"Test '{test_name}': Gain error {gain_error_percent:+.4f}% "
                                                    f"within tolerance ±{gain_tolerance:.2f}%"
                                                )
                                        except (ValueError, TypeError) as e:
                                            logger.debug(f"Error checking gain tolerance: {e}")
                            except (ValueError, TypeError):
                                pass
                        exec_data['calibration'] = calibration_params
            elif test_type == 'Phase Current Test':
                # Store plot data for phase current calibration tests
                exec_data['plot_data'] = {
                    'iq_refs': list(plot_data.get('iq_refs', [])),
                    'osc_ch1': list(plot_data.get('osc_ch1', [])),
                    'osc_ch2': list(plot_data.get('osc_ch2', [])),
                    'can_v': list(plot_data.get('can_v', [])),
                    'can_w': list(plot_data.get('can_w', [])),
                    'gain_errors_v': list(plot_data.get('gain_errors_v', [])),
                    'gain_corrections_v': list(plot_data.get('gain_corrections_v', [])),
                    'gain_errors_w': list(plot_data.get('gain_errors_w', [])),
                    'gain_corrections_w': list(plot_data.get('gain_corrections_w', [])),
                    'avg_gain_error_v': plot_data.get('avg_gain_error_v'),
                    'avg_gain_correction_v': plot_data.get('avg_gain_correction_v'),
                    'avg_gain_error_w': plot_data.get('avg_gain_error_w'),
                    'avg_gain_correction_w': plot_data.get('avg_gain_correction_w')
                }
            elif test_type == 'Output Current Calibration':
                # Store plot data for Output Current Calibration tests
                # Check if we have dual sweep data (new format) or single plot data (old format)
                if 'first_sweep' in plot_data and 'second_sweep' in plot_data:
                    # New format: Dual sweep data
                    exec_data['plot_data'] = {
                        'first_sweep': plot_data.get('first_sweep', {}),
                        'second_sweep': plot_data.get('second_sweep', {}),
                        'calculated_trim_value': plot_data.get('calculated_trim_value'),
                        'tolerance_percent': plot_data.get('tolerance_percent')
                    }
                else:
                    # Old format: Single plot (backward compatibility)
                    exec_data['plot_data'] = {
                        'osc_averages': list(plot_data.get('osc_averages', [])),
                        'can_averages': list(plot_data.get('can_averages', [])),
                        'setpoint_values': list(plot_data.get('setpoint_values', [])),
                        'slope': plot_data.get('slope'),
                        'intercept': plot_data.get('intercept'),
                        'gain_error': plot_data.get('gain_error'),
                        'adjustment_factor': plot_data.get('adjustment_factor'),
                        'tolerance_percent': plot_data.get('tolerance_percent')
                    }
            elif test_type == 'Analog Static Test':
                # Store plot data and statistics for analog_static tests
                if plot_data:
                    exec_data['plot_data'] = {
                        'feedback_values': list(plot_data.get('feedback_values', [])),
                        'eol_values': list(plot_data.get('eol_values', []))
                    }
                # Statistics should already be stored in _test_execution_data by _on_test_finished
                # But ensure they're in exec_data for display
                if test_name in self._test_execution_data:
                    stats = self._test_execution_data[test_name].get('statistics')
                    if stats:
                        exec_data['statistics'] = stats
        
        # Update exec_data with final status and notes (may have been modified by gain tolerance check)
        exec_data['status'] = status
        exec_data['notes'] = notes
        
        self._test_execution_data[test_name] = exec_data
        
        # Invalidate DUT UID cache since execution data changed
        self._invalidate_dut_uid_cache()
        
        # Find existing row by test name
        existing_row = None
        for row in range(self.results_table.rowCount()):
            name_item = self.results_table.item(row, 0)
            if name_item and name_item.text() == test_name:
                existing_row = row
                break
        
        if existing_row is not None:
            # Update existing row
            self.results_table.setItem(existing_row, 2, QtWidgets.QTableWidgetItem(status))
        else:
            # Insert new row if test exists in self._tests but not in table
            # (shouldn't happen if _populate_test_plan was called, but handle gracefully)
            row = self.results_table.rowCount()
            self.results_table.insertRow(row)
            self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(test_name))
            self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(test_type))
            self.results_table.setItem(row, 2, QtWidgets.QTableWidgetItem(status))
    
    def _on_test_plan_item_clicked(self, item: QtWidgets.QTableWidgetItem) -> None:
        """Handle click on Test Plan table item to show test details popup.
        
        Args:
            item: The clicked table item
        """
        # Get row of clicked item
        row = item.row()
        
        # Get test name from first column
        name_item = self.results_table.item(row, 0)
        if not name_item:
            return
        
        test_name = name_item.text()
        
        # Find test in self._tests for full configuration
        test_config = None
        for test in self._tests:
            if test.get('name', '') == test_name:
                test_config = test
                break
        
        # Get execution data
        exec_data = self._test_execution_data.get(test_name, {})
        
        # Show popup dialog
        self._show_test_details_popup(test_name, test_config, exec_data)
    
    def _show_test_details_popup(self, test_name: str, test_config: Optional[Dict[str, Any]], exec_data: Dict[str, Any]) -> None:
        """Show a popup dialog with test execution details.
        
        Args:
            test_name: Name of the test
            test_config: Test configuration dictionary (may be None if test not found)
            exec_data: Execution data dictionary with status, exec_time, notes, parameters
        """
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f'Test Details: {test_name}')
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(300)
        
        layout = QtWidgets.QVBoxLayout(dialog)
        
        # Test Name section
        name_label = QtWidgets.QLabel(f'<b>Test Name:</b> {test_name}')
        layout.addWidget(name_label)
        
        # Status section
        status = exec_data.get('status', 'Not Run')
        status_label = QtWidgets.QLabel(f'<b>Status:</b> {status}')
        # Color code status
        if status == 'PASS':
            status_label.setStyleSheet('color: green;')
        elif status in ('FAIL', 'ERROR'):
            status_label.setStyleSheet('color: red;')
        elif status == 'Running...':
            status_label.setStyleSheet('color: blue;')
        layout.addWidget(status_label)
        
        # Execution Time section
        exec_time = exec_data.get('exec_time', 'N/A')
        exec_time_label = QtWidgets.QLabel(f'<b>Execution Time:</b> {exec_time}')
        layout.addWidget(exec_time_label)
        
        # Parameters section
        parameters = exec_data.get('parameters', 'None')
        if not parameters and test_config:
            # If no stored parameters, extract them from test_config
            parameters = self._get_test_parameters_string(test_config)
        params_label = QtWidgets.QLabel(f'<b>Parameters:</b>')
        layout.addWidget(params_label)
        params_text = QtWidgets.QTextEdit()
        params_text.setPlainText(parameters)
        params_text.setReadOnly(True)
        params_text.setMaximumHeight(100)
        layout.addWidget(params_text)
        
        # Notes/Details section
        notes = exec_data.get('notes', '')
        if not notes:
            notes = 'No additional notes available.'
        notes_label = QtWidgets.QLabel(f'<b>Notes/Details:</b>')
        layout.addWidget(notes_label)
        notes_text = QtWidgets.QTextEdit()
        notes_text.setPlainText(notes)
        notes_text.setReadOnly(True)
        layout.addWidget(notes_text)
        
        # Statistical Analysis section for analog_static tests
        is_analog_static = test_config and test_config.get('type') == 'Analog Static Test'
        statistics = exec_data.get('statistics')
        
        if is_analog_static and statistics:
            stats_label = QtWidgets.QLabel('<b>Statistical Analysis:</b>')
            layout.addWidget(stats_label)
            
            stats_text = QtWidgets.QTextEdit()
            stats_text.setReadOnly(True)
            stats_text.setMaximumHeight(150)
            
            feedback_avg = statistics.get('feedback_avg', 0)
            eol_avg = statistics.get('eol_avg', 0)
            difference = statistics.get('difference', 0)
            tolerance = statistics.get('tolerance', 0)
            passed = statistics.get('passed', False)
            fb_samples = statistics.get('feedback_samples', 0)
            eol_samples = statistics.get('eol_samples', 0)
            
            stats_info = f"""Feedback Signal Average: {feedback_avg:.2f} mV
EOL Signal Average: {eol_avg:.2f} mV
Difference: {difference:.2f} mV
Tolerance: {tolerance:.2f} mV
Result: {'PASS' if passed else 'FAIL'}
Feedback Samples Collected: {fb_samples}
EOL Samples Collected: {eol_samples}"""
            
            stats_text.setPlainText(stats_info)
            layout.addWidget(stats_text)
        
        # Calibration Parameters section for analog tests
        is_analog = test_config and test_config.get('type') == 'Analog Sweep Test'
        calibration_params = exec_data.get('calibration')
        
        if is_analog and calibration_params:
            calib_label = QtWidgets.QLabel(f'<b>Calibration Parameters (for IPC Hardware Gain Adjustment):</b>')
            layout.addWidget(calib_label)
            
            # Create a formatted text display for calibration parameters
            calib_text = QtWidgets.QTextEdit()
            calib_text.setReadOnly(True)
            calib_text.setMaximumHeight(150)
            
            gain = calibration_params.get('gain', 0)
            offset = calibration_params.get('offset', 0)
            r_squared = calibration_params.get('r_squared', 0)
            mse = calibration_params.get('mse', 0)
            max_error = calibration_params.get('max_error', 0)
            mean_error = calibration_params.get('mean_error', 0)
            data_points = calibration_params.get('data_points', 0)
            
            calib_info = f"""Gain (Slope): {gain:.6f} (mV feedback per mV DAC)
Offset: {offset:.4f} (feedback value at DAC = 0mV)
R² (Linearity): {r_squared:.6f} (1.0 = perfectly linear)
Mean Error: {mean_error:.4f}
Max Error: {max_error:.4f}
Mean Squared Error (MSE): {mse:.4f}
Data Points Used: {data_points}"""
            
            # Add gain error percentage and adjustment factor if expected gain is specified
            gain_error_percent = calibration_params.get('gain_error_percent')
            expected_gain_stored = calibration_params.get('expected_gain')
            
            # Also check test_config as fallback
            if gain_error_percent is None and test_config:
                actuation = test_config.get('actuation', {})
                expected_gain = actuation.get('expected_gain')
                if expected_gain is not None:
                    try:
                        expected_gain = float(expected_gain)
                        if abs(expected_gain) > 1e-10 and abs(gain) > 1e-10:
                            gain_error_percent = ((gain - expected_gain) / expected_gain) * 100.0
                            expected_gain_stored = expected_gain
                    except (ValueError, TypeError):
                        pass
            
            if gain_error_percent is not None and expected_gain_stored is not None:
                calib_info += f"\n\nExpected Gain: {expected_gain_stored:.6f}"
                calib_info += f"\nGain Error: {gain_error_percent:+.4f}%"
                # Color code: negative = under-gain, positive = over-gain
                if abs(gain_error_percent) < 1.0:
                    calib_info += " (Excellent)"
                elif abs(gain_error_percent) < 5.0:
                    calib_info += " (Good)"
                elif abs(gain_error_percent) < 10.0:
                    calib_info += " (Acceptable)"
                else:
                    calib_info += " (Needs Adjustment)"
                
                # Calculate and display adjustment factor
                if abs(gain) > 1e-10:
                    adjustment_factor = expected_gain_stored / gain
                    calib_info += f"\nGain Adjustment Factor: {adjustment_factor:.6f}"
                    calib_info += f"\n(IPC Hardware Gain should be multiplied by {adjustment_factor:.6f})"
            
            calib_text.setPlainText(calib_info)
            layout.addWidget(calib_text)
        
        # Plot section for analog tests and phase current calibration
        plot_data = exec_data.get('plot_data')
        is_phase_current = test_config and test_config.get('type') == 'Phase Current Test'
        
        if is_analog and plot_data and matplotlib_available:
            plot_dac_voltages = plot_data.get('dac_voltages', [])
            plot_feedback_values = plot_data.get('feedback_values', [])
            
            if plot_dac_voltages and plot_feedback_values and len(plot_dac_voltages) == len(plot_feedback_values):
                plot_label = QtWidgets.QLabel(f'<b>Feedback vs DAC Output Voltage Plot:</b>')
                layout.addWidget(plot_label)
                
                try:
                    # Create a new figure and canvas for the dialog
                    plot_figure = Figure(figsize=(6, 4))
                    plot_canvas = FigureCanvasQTAgg(plot_figure)
                    plot_axes = plot_figure.add_subplot(111)
                    
                    # Plot the data
                    plot_axes.plot(plot_dac_voltages, plot_feedback_values, 'bo-', markersize=6, linewidth=1, label='Feedback')
                    plot_axes.set_xlabel('DAC Output Voltage (mV)')
                    plot_axes.set_ylabel('Feedback Signal Value')
                    plot_axes.set_title(f'Feedback vs DAC Output: {test_name}')
                    plot_axes.grid(True, alpha=0.3)
                    plot_axes.legend()
                    
                    # Auto-scale axes to fit all data
                    plot_axes.relim()
                    plot_axes.autoscale()
                    
                    # Tight layout
                    plot_figure.tight_layout()
                    
                    # Add canvas to layout
                    layout.addWidget(plot_canvas)
                except Exception as e:
                    logger.error(f"Error creating plot in test details dialog: {e}", exc_info=True)
                    error_label = QtWidgets.QLabel(f'<i>Plot visualization failed: {e}</i>')
                    error_label.setStyleSheet('color: red;')
                    layout.addWidget(error_label)
        
        # Plot section for phase current calibration tests
        if is_phase_current and plot_data and matplotlib_available:
            plot_can_v = plot_data.get('can_v', [])
            plot_osc_v = plot_data.get('osc_ch1', [])
            plot_can_w = plot_data.get('can_w', [])
            plot_osc_w = plot_data.get('osc_ch2', [])
            
            if (plot_can_v or plot_osc_v or plot_can_w or plot_osc_w):
                plot_label = QtWidgets.QLabel(f'<b>Average Phase Current: CAN vs Oscilloscope Comparison:</b>')
                layout.addWidget(plot_label)
                
                try:
                    # Create a new figure with two subplots
                    plot_figure = Figure(figsize=(12, 5))
                    plot_canvas = FigureCanvasQTAgg(plot_figure)
                    
                    # Phase V plot
                    plot_axes_v = plot_figure.add_subplot(121)
                    
                    # Filter out NaN values and ensure matching lengths
                    can_v_clean = []
                    osc_v_clean = []
                    if plot_can_v and plot_osc_v:
                        min_len = min(len(plot_can_v), len(plot_osc_v))
                        for i in range(min_len):
                            can_val = plot_can_v[i]
                            osc_val = plot_osc_v[i]
                            # Check if both are valid (not NaN)
                            if (isinstance(can_val, (int, float)) and isinstance(osc_val, (int, float)) and
                                not (isinstance(can_val, float) and can_val != can_val) and
                                not (isinstance(osc_val, float) and osc_val != osc_val)):
                                can_v_clean.append(can_val)
                                osc_v_clean.append(osc_val)
                    
                    if can_v_clean and osc_v_clean:
                        plot_axes_v.plot(osc_v_clean, can_v_clean, 'bo', markersize=6, label='Phase V')
                        # Add diagonal reference line (y=x)
                        plot_axes_v.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
                    
                    plot_axes_v.set_xlabel('Average Phase V Current from Oscilloscope (A)')
                    plot_axes_v.set_ylabel('Average Phase V Current from CAN (A)')
                    plot_axes_v.set_title('Phase V: CAN vs Oscilloscope')
                    plot_axes_v.grid(True, alpha=0.3)
                    plot_axes_v.legend()
                    
                    # Phase W plot
                    plot_axes_w = plot_figure.add_subplot(122)
                    
                    # Filter out NaN values and ensure matching lengths
                    can_w_clean = []
                    osc_w_clean = []
                    if plot_can_w and plot_osc_w:
                        min_len = min(len(plot_can_w), len(plot_osc_w))
                        for i in range(min_len):
                            can_val = plot_can_w[i]
                            osc_val = plot_osc_w[i]
                            # Check if both are valid (not NaN)
                            if (isinstance(can_val, (int, float)) and isinstance(osc_val, (int, float)) and
                                not (isinstance(can_val, float) and can_val != can_val) and
                                not (isinstance(osc_val, float) and osc_val != osc_val)):
                                can_w_clean.append(can_val)
                                osc_w_clean.append(osc_val)
                    
                    if can_w_clean and osc_w_clean:
                        plot_axes_w.plot(osc_w_clean, can_w_clean, 'ro', markersize=6, label='Phase W')
                        # Add diagonal reference line (y=x)
                        plot_axes_w.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
                    
                    plot_axes_w.set_xlabel('Average Phase W Current from Oscilloscope (A)')
                    plot_axes_w.set_ylabel('Average Phase W Current from CAN (A)')
                    plot_axes_w.set_title('Phase W: CAN vs Oscilloscope')
                    plot_axes_w.grid(True, alpha=0.3)
                    plot_axes_w.legend()
                    
                    # Tight layout
                    plot_figure.tight_layout()
                    
                    # Add canvas to layout
                    layout.addWidget(plot_canvas)
                    
                    # Display gain error and correction factor
                    avg_gain_error_v = plot_data.get('avg_gain_error_v')
                    avg_gain_correction_v = plot_data.get('avg_gain_correction_v')
                    avg_gain_error_w = plot_data.get('avg_gain_error_w')
                    avg_gain_correction_w = plot_data.get('avg_gain_correction_w')
                    
                    if avg_gain_error_v is not None or avg_gain_error_w is not None:
                        gain_info_label = QtWidgets.QLabel(f'<b>Gain Error and Correction Factor:</b>')
                        layout.addWidget(gain_info_label)
                        
                        gain_info_text = QtWidgets.QTextEdit()
                        gain_info_text.setReadOnly(True)
                        gain_info_text.setMaximumHeight(120)
                        
                        gain_info = ""
                        if avg_gain_error_v is not None:
                            gain_info += f"Phase V:\n"
                            gain_info += f"  Average Gain Error: {avg_gain_error_v:+.4f}%\n"
                            if avg_gain_correction_v is not None:
                                gain_info += f"  Average Gain Correction Factor: {avg_gain_correction_v:.6f}\n"
                            gain_info += "\n"
                        
                        if avg_gain_error_w is not None:
                            gain_info += f"Phase W:\n"
                            gain_info += f"  Average Gain Error: {avg_gain_error_w:+.4f}%\n"
                            if avg_gain_correction_w is not None:
                                gain_info += f"  Average Gain Correction Factor: {avg_gain_correction_w:.6f}\n"
                        
                        gain_info_text.setPlainText(gain_info)
                        layout.addWidget(gain_info_text)
                        
                except Exception as e:
                    logger.error(f"Error creating phase current plots in test details dialog: {e}", exc_info=True)
                    error_label = QtWidgets.QLabel(f'<i>Plot visualization failed: {e}</i>')
                    error_label.setStyleSheet('color: red;')
                    layout.addWidget(error_label)
        
        # Plot section for Output Current Calibration tests
        is_output_current_calibration = test_config and test_config.get('type') == 'Output Current Calibration'
        if is_output_current_calibration and plot_data and matplotlib_available:
            # Check if we have dual sweep data (new format) or single plot data (old format)
            first_sweep_data = plot_data.get('first_sweep')
            second_sweep_data = plot_data.get('second_sweep')
            
            if first_sweep_data and second_sweep_data:
                # New format: Dual sweep plots
                plot_label = QtWidgets.QLabel(f'<b>Output Current Calibration: Dual Sweep Results</b>')
                layout.addWidget(plot_label)
                
                try:
                    # Helper function to create a plot
                    def create_plot(plot_data_dict, plot_title):
                        plot_figure = Figure(figsize=(8, 6))
                        plot_canvas = FigureCanvasQTAgg(plot_figure)
                        plot_axes = plot_figure.add_subplot(111)
                        
                        plot_osc_averages = plot_data_dict.get('osc_averages', [])
                        plot_can_averages = plot_data_dict.get('can_averages', [])
                        slope = plot_data_dict.get('slope')
                        intercept = plot_data_dict.get('intercept')
                        
                        if plot_osc_averages and plot_can_averages:
                            # Filter out NaN values and ensure matching lengths
                            osc_clean = []
                            can_clean = []
                            min_len = min(len(plot_osc_averages), len(plot_can_averages))
                            for i in range(min_len):
                                osc_val = plot_osc_averages[i]
                                can_val = plot_can_averages[i]
                                # Check if both are valid (not NaN)
                                if (isinstance(osc_val, (int, float)) and isinstance(can_val, (int, float)) and
                                    not (isinstance(osc_val, float) and osc_val != osc_val) and
                                    not (isinstance(can_val, float) and can_val != can_val)):
                                    osc_clean.append(osc_val)
                                    can_clean.append(can_val)
                            
                            if osc_clean and can_clean:
                                # Plot data points
                                plot_axes.plot(osc_clean, can_clean, 'bo', markersize=8, label='Data Points')
                                
                                # Add diagonal reference line (y=x) for ideal line
                                plot_axes.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
                                
                                # Add regression line if slope and intercept are available
                                if slope is not None and intercept is not None and isinstance(slope, (int, float)) and isinstance(intercept, (int, float)):
                                    x_min = min(osc_clean)
                                    x_max = max(osc_clean)
                                    x_reg = [x_min, x_max]
                                    y_reg = [slope * x + intercept for x in x_reg]
                                    plot_axes.plot(x_reg, y_reg, 'r-', linewidth=2, alpha=0.7, label=f'Regression (slope={slope:.4f})')
                                
                                plot_axes.set_xlabel('Oscilloscope Measurement (A)')
                                plot_axes.set_ylabel('DUT Measurement (A)')
                                plot_axes.set_title(plot_title)
                                plot_axes.grid(True, alpha=0.3)
                                plot_axes.legend()
                                
                                # Auto-scale axes to fit all data
                                plot_axes.relim()
                                plot_axes.autoscale()
                                
                                # Tight layout
                                plot_figure.tight_layout()
                        
                        return plot_canvas
                    
                    # Create first sweep plot
                    first_plot_label = QtWidgets.QLabel(f'<b>{first_sweep_data.get("plot_label", "First Sweep")}</b>')
                    layout.addWidget(first_plot_label)
                    first_plot_canvas = create_plot(first_sweep_data, first_sweep_data.get("plot_label", "First Sweep"))
                    layout.addWidget(first_plot_canvas)
                    
                    # Create second sweep plot
                    second_plot_label = QtWidgets.QLabel(f'<b>{second_sweep_data.get("plot_label", "Second Sweep")}</b>')
                    layout.addWidget(second_plot_label)
                    second_plot_canvas = create_plot(second_sweep_data, second_sweep_data.get("plot_label", "Second Sweep"))
                    layout.addWidget(second_plot_canvas)
                    
                    # Display calibration results
                    gain_info_label = QtWidgets.QLabel(f'<b>Calibration Results:</b>')
                    layout.addWidget(gain_info_label)
                    
                    gain_info_text = QtWidgets.QTextEdit()
                    gain_info_text.setReadOnly(True)
                    gain_info_text.setMaximumHeight(200)
                    
                    gain_info = ""
                    # First sweep results
                    first_slope = first_sweep_data.get('slope')
                    first_intercept = first_sweep_data.get('intercept')
                    first_gain_error = first_sweep_data.get('gain_error')
                    first_adjustment = first_sweep_data.get('adjustment_factor')
                    first_trim = first_sweep_data.get('trim_value')
                    if first_slope is not None:
                        gain_info += f"First Sweep (Trim: {first_trim}%):\n"
                        gain_info += f"  Linear Regression: Slope={first_slope:.6f}, Intercept={first_intercept:.6f}A\n"
                    if first_gain_error is not None:
                        gain_info += f"  Gain Error: {first_gain_error:.4f}%\n"
                    if first_adjustment is not None:
                        gain_info += f"  Adjustment Factor: {first_adjustment:.6f}\n"
                    
                    # Calculated trim value
                    calculated_trim = plot_data.get('calculated_trim_value')
                    if calculated_trim is not None:
                        gain_info += f"\nCalculated Trim Value: {calculated_trim:.4f}%\n"
                    
                    # Second sweep results
                    second_slope = second_sweep_data.get('slope')
                    second_intercept = second_sweep_data.get('intercept')
                    second_gain_error = second_sweep_data.get('gain_error')
                    second_trim = second_sweep_data.get('trim_value')
                    tolerance_percent = plot_data.get('tolerance_percent')
                    if second_slope is not None:
                        gain_info += f"\nSecond Sweep (Trim: {second_trim:.4f}%):\n"
                        gain_info += f"  Linear Regression: Slope={second_slope:.6f}, Intercept={second_intercept:.6f}A\n"
                    if second_gain_error is not None:
                        gain_info += f"  Gain Error: {second_gain_error:.4f}%\n"
                    if tolerance_percent is not None:
                        gain_info += f"  Tolerance: {tolerance_percent:.4f}%\n"
                        passed = second_gain_error is not None and abs(second_gain_error) <= tolerance_percent
                        gain_info += f"  Result: {'PASS' if passed else 'FAIL'}\n"
                    
                    gain_info_text.setPlainText(gain_info)
                    layout.addWidget(gain_info_text)
                    
                except Exception as e:
                    logger.error(f"Error creating Output Current Calibration dual plots in test details dialog: {e}", exc_info=True)
                    error_label = QtWidgets.QLabel(f'<i>Plot visualization failed: {e}</i>')
                    error_label.setStyleSheet('color: red;')
                    layout.addWidget(error_label)
            else:
                # Old format: Single plot (backward compatibility)
                plot_osc_averages = plot_data.get('osc_averages', [])
                plot_can_averages = plot_data.get('can_averages', [])
                
                if plot_osc_averages and plot_can_averages:
                    plot_label = QtWidgets.QLabel(f'<b>Output Current Calibration: DUT vs Oscilloscope Comparison:</b>')
                    layout.addWidget(plot_label)
                    
                    try:
                        # Create a new figure for the dialog
                        plot_figure = Figure(figsize=(8, 6))
                        plot_canvas = FigureCanvasQTAgg(plot_figure)
                        plot_axes = plot_figure.add_subplot(111)
                        
                        # Filter out NaN values and ensure matching lengths
                        osc_clean = []
                        can_clean = []
                        min_len = min(len(plot_osc_averages), len(plot_can_averages))
                        for i in range(min_len):
                            osc_val = plot_osc_averages[i]
                            can_val = plot_can_averages[i]
                            # Check if both are valid (not NaN)
                            if (isinstance(osc_val, (int, float)) and isinstance(can_val, (int, float)) and
                                not (isinstance(osc_val, float) and osc_val != osc_val) and
                                not (isinstance(can_val, float) and can_val != can_val)):
                                osc_clean.append(osc_val)
                                can_clean.append(can_val)
                        
                        if osc_clean and can_clean:
                            # Plot data points
                            plot_axes.plot(osc_clean, can_clean, 'bo', markersize=8, label='Data Points')
                            
                            # Add diagonal reference line (y=x) for ideal line
                            plot_axes.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
                            
                            # Add regression line if available
                            slope = plot_data.get('slope')
                            intercept = plot_data.get('intercept')
                            if slope is not None and intercept is not None:
                                # Calculate regression line points
                                x_min = min(osc_clean)
                                x_max = max(osc_clean)
                                x_reg = [x_min, x_max]
                                y_reg = [slope * x + intercept for x in x_reg]
                                plot_axes.plot(x_reg, y_reg, 'r-', linewidth=2, alpha=0.7, label=f'Regression (slope={slope:.4f})')
                            
                            plot_axes.set_xlabel('Oscilloscope Measurement (A)')
                            plot_axes.set_ylabel('DUT Measurement (A)')
                            plot_axes.set_title(f'Output Current Calibration: DUT vs Oscilloscope{(": " + test_name) if test_name else ""}')
                            plot_axes.grid(True, alpha=0.3)
                            plot_axes.legend()
                            
                            # Auto-scale axes to fit all data
                            plot_axes.relim()
                            plot_axes.autoscale()
                            
                            # Tight layout
                            plot_figure.tight_layout()
                            
                            # Add canvas to layout
                            layout.addWidget(plot_canvas)
                            
                            # Display gain error and adjustment factor
                            # Support both old format (gain_error) and new format (avg_gain_error)
                            gain_error = plot_data.get('gain_error') or plot_data.get('avg_gain_error')
                            adjustment_factor = plot_data.get('adjustment_factor')
                            tolerance_percent = plot_data.get('tolerance_percent')
                            slope = plot_data.get('slope')
                            intercept = plot_data.get('intercept')
                            
                            if gain_error is not None:
                                gain_info_label = QtWidgets.QLabel(f'<b>Calibration Results:</b>')
                                layout.addWidget(gain_info_label)
                                
                                gain_info_text = QtWidgets.QTextEdit()
                                gain_info_text.setReadOnly(True)
                                gain_info_text.setMaximumHeight(120)
                                
                                gain_info = ""
                                # Only show slope/intercept if available (old format)
                                if slope is not None:
                                    gain_info += f"Slope: {slope:.6f} (ideal: 1.0)\n"
                                if intercept is not None:
                                    gain_info += f"Intercept: {intercept:.6f} A\n"
                                # Show average gain error (new format) or gain error (old format)
                                if plot_data.get('avg_gain_error') is not None:
                                    gain_info += f"Average Gain Error: {gain_error:.4f}%\n"
                                else:
                                    gain_info += f"Gain Error: {gain_error:+.4f}%\n"
                                if adjustment_factor is not None:
                                    gain_info += f"Adjustment Factor: {adjustment_factor:.6f}\n"
                                if tolerance_percent is not None:
                                    gain_info += f"Tolerance: {tolerance_percent:.4f}%\n"
                                    passed = abs(gain_error) <= tolerance_percent
                                    gain_info += f"Result: {'PASS' if passed else 'FAIL'}\n"
                                
                                gain_info_text.setPlainText(gain_info)
                                layout.addWidget(gain_info_text)
                        
                    except Exception as e:
                        logger.error(f"Error creating Output Current Calibration plot in test details dialog: {e}", exc_info=True)
                        error_label = QtWidgets.QLabel(f'<i>Plot visualization failed: {e}</i>')
                        error_label.setStyleSheet('color: red;')
                        layout.addWidget(error_label)
        
        # Close button
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        close_btn = QtWidgets.QPushButton('Close')
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        # Adjust dialog size for plot and calibration parameters if present
        if (is_analog and (plot_data and matplotlib_available or calibration_params)) or \
           (is_phase_current and plot_data and matplotlib_available) or \
           (is_output_current_calibration and plot_data and matplotlib_available):
            dialog.setMinimumWidth(700)
            dialog.setMinimumHeight(650)
        else:
            dialog.setMinimumWidth(500)
            dialog.setMinimumHeight(300)
        
        dialog.exec()

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
            # Clear Output Current Calibration plot data if it exists
            if hasattr(self, 'plot_osc_values'):
                self.plot_osc_values = []
            if hasattr(self, 'plot_can_values'):
                self.plot_can_values = []
            if hasattr(self, '_output_current_plot_initialized'):
                self._output_current_plot_initialized = False
            self.plot_line.set_data([], [])
            self.plot_axes.relim()
            self.plot_axes.autoscale()
            self.plot_canvas.draw_idle()
        except Exception as e:
            logger.debug(f"Failed to update plot during initialization: {e}", exc_info=True)
    
    def _initialize_output_current_plot(self, test_name: Optional[str] = None) -> None:
        """Initialize the plot for Output Current Calibration test with proper labels and title.
        
        Args:
            test_name: Optional test name to include in the plot title
        """
        if not matplotlib_available:
            logger.debug("Matplotlib not available, skipping plot initialization")
            return
        if not hasattr(self, 'plot_axes') or self.plot_axes is None:
            logger.debug("Plot axes not initialized, skipping plot initialization")
            return
        if not hasattr(self, 'plot_canvas') or self.plot_canvas is None:
            logger.debug("Plot canvas not initialized, skipping plot initialization")
            return
        try:
            self.plot_axes.clear()
            self.plot_axes.set_xlabel('Oscilloscope Measurement (A)')
            self.plot_axes.set_ylabel('DUT Measurement (A)')
            self.plot_axes.set_title(f'Output Current Calibration: DUT vs Oscilloscope{(": " + test_name) if test_name else ""}')
            self.plot_axes.grid(True, alpha=PLOT_GRID_ALPHA)
            # Add diagonal reference line (y=x) for ideal line
            self.plot_axes.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
            # Create scatter plot for Output Current Calibration
            self.plot_line, = self.plot_axes.plot([], [], 'bo', markersize=6, label='Data Points')
            self.plot_axes.legend()
            self.plot_figure.tight_layout()
            self.plot_canvas.draw_idle()
            self._output_current_plot_initialized = True
            logger.debug(f"Initialized plot for Output Current Calibration: {test_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Output Current Calibration plot: {e}", exc_info=True)

    def _create_sparkline_widget(self):
        """Create a small sparkline widget for value history visualization."""
        if not matplotlib_available:
            return None
        
        fig = Figure(figsize=(2, 0.5), dpi=100)
        ax = fig.add_subplot(111)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.set_facecolor('white')
        fig.patch.set_facecolor('white')
        canvas = FigureCanvasQTAgg(fig)
        canvas.setMinimumWidth(80)
        canvas.setMaximumWidth(80)
        canvas.setMinimumHeight(30)
        canvas.setMaximumHeight(30)
        
        return {'widget': canvas, 'figure': fig, 'axes': ax, 'data': []}
    
    def _format_signal_value(self, value: Any, signal_type: str) -> str:
        """Format signal value with appropriate units and precision.
        
        Args:
            value: The signal value to format
            signal_type: Type of signal ('voltage', 'current', 'temperature', 'frequency', 'duty', 'digital', 'generic')
        
        Returns:
            Formatted string with value and unit
        """
        if value is None:
            return 'N/A'
        
        try:
            float_val = float(value)
        except (ValueError, TypeError):
            return str(value)
        
        formatters = {
            'voltage': lambda v: f"{v:.2f} V",
            'current': lambda v: f"{v:.2f} A",
            'temperature': lambda v: f"{v:.2f} °C",
            'frequency': lambda v: f"{v:.2f} Hz",
            'duty': lambda v: f"{v:.2f} %",
            'digital': lambda v: f"{int(round(v))}",
            'generic': lambda v: f"{v:.2f}",
        }
        
        formatter = formatters.get(signal_type, lambda v: f"{v:.2f}")
        return formatter(float_val)
    
    def _get_signal_type(self, signal_name: str) -> str:
        """Determine signal type from signal name."""
        name_lower = signal_name.lower()
        if 'voltage' in name_lower or 'dac' in name_lower:
            return 'voltage'
        elif 'current' in name_lower:
            return 'current'
        elif 'temp' in name_lower:
            return 'temperature'
        elif 'freq' in name_lower or 'frequency' in name_lower:
            return 'frequency'
        elif 'duty' in name_lower:
            return 'duty'
        elif 'relay' in name_lower or 'pfc' in name_lower or 'enable' in name_lower or 'power' in name_lower:
            return 'digital'
        else:
            return 'generic'
    
    def _update_signal_with_status(self, signal_name: str, value: Any, 
                                   threshold_good: Optional[Tuple[float, float]] = None,
                                   threshold_warn: Optional[Tuple[float, float]] = None) -> None:
        """Update signal label with value, formatting, color coding, timestamp, and sparkline.
        
        Args:
            signal_name: Name of the signal ('current_signal', 'feedback_signal', etc.)
            value: The signal value to display
            threshold_good: Optional tuple (min, max) for good range (green)
            threshold_warn: Optional tuple (min, max) for warning range (orange)
        """
        import time
        from datetime import datetime
        
        # Get signal type and format value
        signal_type = self._get_signal_type(signal_name)
        formatted_value = self._format_signal_value(value, signal_type)
        
        # Get label and timestamp items (can be QTableWidgetItem or QLabel for backward compatibility)
        label = self._monitor_labels.get(signal_name)
        timestamp_item = self._monitor_timestamps.get(signal_name)
        
        if label is None:
            return
        
        # Update label text
        if isinstance(label, QtWidgets.QTableWidgetItem):
            label.setText(formatted_value)
        elif hasattr(label, 'setText'):
            label.setText(formatted_value)
        
        # Update timestamp
        if timestamp_item is not None:
            timestamp_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            if isinstance(timestamp_item, QtWidgets.QTableWidgetItem):
                timestamp_item.setText(timestamp_str)
            elif hasattr(timestamp_item, 'setText'):
                timestamp_item.setText(f"Updated: {timestamp_str}")
        
        # Color coding based on thresholds
        if value is None:
            # Gray for N/A
            if isinstance(label, QtWidgets.QTableWidgetItem):
                label.setForeground(QtGui.QColor('gray'))
                label.setBackground(QtGui.QColor('#f5f5f5'))
            elif hasattr(label, 'setStyleSheet'):
                label.setStyleSheet('color: gray; font-weight: bold; font-size: 11pt; padding: 5px; background-color: #f5f5f5;')
        else:
            try:
                float_val = float(value)
                
                # Determine colors based on thresholds
                if threshold_good is not None and threshold_warn is not None:
                    if threshold_good[0] <= float_val <= threshold_good[1]:
                        text_color = QtGui.QColor('green')
                        bg_color = QtGui.QColor('#e8f5e9')
                    elif threshold_warn[0] <= float_val <= threshold_warn[1]:
                        text_color = QtGui.QColor('orange')
                        bg_color = QtGui.QColor('#fff3e0')
                    else:
                        text_color = QtGui.QColor('red')
                        bg_color = QtGui.QColor('#ffebee')
                elif signal_type == 'digital':
                    # Digital signals: 1 = green, 0 = red
                    if float_val >= 0.5:
                        text_color = QtGui.QColor('green')
                        bg_color = QtGui.QColor('#e8f5e9')
                    else:
                        text_color = QtGui.QColor('red')
                        bg_color = QtGui.QColor('#ffebee')
                else:
                    # Default: blue for analog values
                    text_color = QtGui.QColor('blue')
                    bg_color = QtGui.QColor('#e3f2fd')
                
                # Apply colors
                if isinstance(label, QtWidgets.QTableWidgetItem):
                    label.setForeground(text_color)
                    label.setBackground(bg_color)
                elif hasattr(label, 'setStyleSheet'):
                    style = f'color: {text_color.name()}; font-weight: bold; font-size: 11pt; padding: 5px; background-color: {bg_color.name()};'
                    label.setStyleSheet(style)
            except (ValueError, TypeError):
                # Default blue for non-numeric values
                if isinstance(label, QtWidgets.QTableWidgetItem):
                    label.setForeground(QtGui.QColor('blue'))
                    label.setBackground(QtGui.QColor('#e3f2fd'))
                elif hasattr(label, 'setStyleSheet'):
                    label.setStyleSheet('color: blue; font-weight: bold; font-size: 11pt; padding: 5px; background-color: #e3f2fd;')
        
        # Update value history and sparkline
        if signal_name in self._monitor_data:
            data_entry = self._monitor_data[signal_name]
            data_entry['value'] = value
            data_entry['timestamp'] = time.time()
            
            # Add to history
            if value is not None:
                try:
                    float_val = float(value)
                    data_entry['history'].append(float_val)
                    # Keep only last N values
                    max_size = data_entry.get('history_max_size', 50)
                    if len(data_entry['history']) > max_size:
                        data_entry['history'] = data_entry['history'][-max_size:]
                except (ValueError, TypeError):
                    pass
            
            # Update sparkline
            if signal_name in self._monitor_sparklines and matplotlib_available:
                sparkline = self._monitor_sparklines[signal_name]
                if sparkline and len(data_entry['history']) > 1:
                    try:
                        ax = sparkline['axes']
                        ax.clear()
                        history = data_entry['history']
                        if len(history) > 0:
                            ax.plot(history, 'b-', linewidth=1.5, alpha=0.7)
                            ax.set_ylim(min(history) * 0.95 if min(history) > 0 else min(history) * 1.05,
                                       max(history) * 1.05 if max(history) > 0 else max(history) * 0.95)
                        ax.set_xticks([])
                        ax.set_yticks([])
                        ax.spines['top'].set_visible(False)
                        ax.spines['right'].set_visible(False)
                        ax.spines['bottom'].set_visible(False)
                        ax.spines['left'].set_visible(False)
                        sparkline['figure'].tight_layout(pad=0.1)
                        sparkline['widget'].draw()
                    except Exception as e:
                        logger.debug(f"Failed to update sparkline for {signal_name}: {e}")
        
        # Update refresh rate
        now = time.time()
        if signal_name in self._monitor_last_update_times:
            dt = now - self._monitor_last_update_times[signal_name]
            if dt > 0:
                rate = 1.0 / dt
                if hasattr(self, 'update_rate_label'):
                    self.update_rate_label.setText(f"Update Rate: {rate:.1f} Hz")
        self._monitor_last_update_times[signal_name] = now
    
    def update_monitor_signal(self, key: str, value: Optional[float]) -> None:
        """Update real-time monitoring labels for charger-related signals.
        
        This method now uses the enhanced display system with formatting, colors, timestamps, and sparklines.
        """
        # Map old keys to new signal names
        key_map = {
            'enable_relay': 'enable_relay',
            'enable_pfc': 'enable_pfc',
            'pfc_power_good': 'pfc_power_good',
            'output_current': 'output_current',
        }
        
        signal_name = key_map.get(key)
        if signal_name is None:
            return
        
        # Determine thresholds based on signal type
        threshold_good = None
        threshold_warn = None
        
        if key == 'output_current':
            # Current: good if > 0, warn if very low
            threshold_good = (0.1, float('inf'))
            threshold_warn = (0.01, 0.1)
        elif key in ['enable_relay', 'enable_pfc', 'pfc_power_good']:
            # Digital signals: 1 = good, 0 = bad
            threshold_good = (0.5, 1.5)
            threshold_warn = (0.0, 0.5)
        
        self._update_signal_with_status(signal_name, value, threshold_good, threshold_warn)

    def reset_monitor_signals(self) -> None:
        """Reset real-time monitoring labels to their default state."""
        for signal_name in self._monitor_labels.keys():
            self._update_signal_with_status(signal_name, None)
        
        # Clear history
        for signal_name in self._monitor_data.keys():
            self._monitor_data[signal_name]['history'] = []
            self._monitor_data[signal_name]['value'] = None
            self._monitor_data[signal_name]['timestamp'] = None
        
        # Clear sparklines
        for signal_name, sparkline in self._monitor_sparklines.items():
            if sparkline and matplotlib_available:
                try:
                    ax = sparkline['axes']
                    ax.clear()
                    ax.set_xticks([])
                    ax.set_yticks([])
                    sparkline['widget'].draw()
                except Exception:
                    pass
        
        # Reset refresh rate
        if hasattr(self, 'update_rate_label'):
            self.update_rate_label.setText('Update Rate: -- Hz')

    def _update_plot(self, dac_voltage: float, feedback_value: float, test_name: Optional[str] = None) -> None:
        """Update the plot with a new data point (DAC voltage, feedback value).
        
        Args:
            dac_voltage: DAC output voltage in millivolts (or oscilloscope value for Output Current Calibration)
            feedback_value: IPC feedback signal value (or CAN value for Output Current Calibration)
            test_name: Optional test name for plot title
        """
        if not matplotlib_available:
            logger.debug("Matplotlib not available, skipping plot update")
            return
        if not hasattr(self, 'plot_axes') or self.plot_axes is None:
            logger.debug("Plot axes not initialized, skipping plot update")
            return
        if not hasattr(self, 'plot_canvas') or self.plot_canvas is None:
            logger.debug("Plot canvas not initialized, skipping plot update")
            return
        try:
            # Detect Output Current Calibration test by checking current test type
            is_output_current_calibration = False
            if hasattr(self, '_current_test_index') and self._current_test_index is not None:
                if self._current_test_index < len(self._tests):
                    current_test = self._tests[self._current_test_index]
                    is_output_current_calibration = current_test.get('type') == 'Output Current Calibration'
            
            # Add new data point
            if dac_voltage is not None and feedback_value is not None:
                if is_output_current_calibration:
                    # For Output Current Calibration: X = oscilloscope (dac_voltage param), Y = CAN (feedback_value param)
                    # Initialize plot for Output Current Calibration if not already done
                    if not hasattr(self, '_output_current_plot_initialized') or not self._output_current_plot_initialized:
                        self.plot_axes.clear()
                        self.plot_axes.set_xlabel('Oscilloscope Measurement (A)')
                        self.plot_axes.set_ylabel('DUT Measurement (A)')
                        self.plot_axes.set_title(f'Output Current Calibration: DUT vs Oscilloscope{(": " + test_name) if test_name else ""}')
                        self.plot_axes.grid(True, alpha=PLOT_GRID_ALPHA)
                        # Add diagonal reference line (y=x) for ideal line
                        self.plot_axes.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
                        # Create scatter plot for Output Current Calibration
                        self.plot_line, = self.plot_axes.plot([], [], 'bo', markersize=6, label='Data Points')
                        self.plot_axes.legend()
                        self.plot_figure.tight_layout()
                        self._output_current_plot_initialized = True
                        logger.debug("Initialized plot for Output Current Calibration")
                    
                    # Store data points (oscilloscope as X, CAN as Y)
                    if not hasattr(self, 'plot_osc_values'):
                        self.plot_osc_values = []
                    if not hasattr(self, 'plot_can_values'):
                        self.plot_can_values = []
                    
                    self.plot_osc_values.append(float(dac_voltage))
                    self.plot_can_values.append(float(feedback_value))
                    
                    logger.debug(
                        f"Plot update (Output Current): Added point (Osc={dac_voltage}A, CAN={feedback_value}A), "
                        f"total points: {len(self.plot_osc_values)}"
                    )
                    
                    # Update plot line
                    self.plot_line.set_data(self.plot_osc_values, self.plot_can_values)
                else:
                    # For other tests: X = DAC voltage, Y = feedback value
                    self.plot_dac_voltages.append(float(dac_voltage))
                    self.plot_feedback_values.append(float(feedback_value))
                    
                    logger.debug(
                        f"Plot update: Added point (DAC={dac_voltage}mV, Feedback={feedback_value}), "
                        f"total points: {len(self.plot_dac_voltages)}"
                    )
                    
                    # Update plot line
                    self.plot_line.set_data(self.plot_dac_voltages, self.plot_feedback_values)
                    
                    # Update title if test name provided (for non-Output Current tests)
                    if test_name and not self.plot_axes.get_title():
                        self.plot_axes.set_title(f'Feedback vs DAC Output: {test_name}')
                
                # Auto-scale axes to fit all data
                self.plot_axes.relim()
                self.plot_axes.autoscale()
                
                # Force immediate redraw (draw_idle may not refresh fast enough)
                self.plot_canvas.draw()
                
                # Also trigger draw_idle for Qt event processing
                self.plot_canvas.draw_idle()
        except Exception as e:
            logger.error(f"Error updating plot: {e}", exc_info=True)

    def _build_test_report(self):
        """Builds the Test Report tab widget with interactive UI and export capabilities."""
        tab = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(tab)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Summary Section
        summary_group = QtWidgets.QGroupBox('Summary')
        summary_layout = QtWidgets.QFormLayout()
        
        self.report_total_tests_label = QtWidgets.QLabel('0')
        self.report_pass_count_label = QtWidgets.QLabel('0')
        self.report_fail_count_label = QtWidgets.QLabel('0')
        self.report_error_count_label = QtWidgets.QLabel('0')
        self.report_pass_rate_label = QtWidgets.QLabel('0%')
        self.report_total_time_label = QtWidgets.QLabel('0.00s')
        self.report_last_updated_label = QtWidgets.QLabel('Never')
        
        self.report_pass_count_label.setStyleSheet('color: green; font-weight: bold;')
        self.report_fail_count_label.setStyleSheet('color: red; font-weight: bold;')
        self.report_error_count_label.setStyleSheet('color: red; font-weight: bold;')
        
        summary_layout.addRow('Total Tests Executed:', self.report_total_tests_label)
        summary_layout.addRow('Passed:', self.report_pass_count_label)
        summary_layout.addRow('Failed:', self.report_fail_count_label)
        summary_layout.addRow('Errors:', self.report_error_count_label)
        summary_layout.addRow('Pass Rate:', self.report_pass_rate_label)
        summary_layout.addRow('Total Execution Time:', self.report_total_time_label)
        summary_layout.addRow('Last Updated:', self.report_last_updated_label)
        
        summary_group.setLayout(summary_layout)
        main_layout.addWidget(summary_group)
        
        # Action Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.report_refresh_btn = QtWidgets.QPushButton('Refresh Report')
        self.report_export_html_btn = QtWidgets.QPushButton('Export as HTML')
        self.report_export_pdf_btn = QtWidgets.QPushButton('Export as PDF')
        self.report_export_json_btn = QtWidgets.QPushButton('Export as JSON')
        
        button_layout.addWidget(self.report_refresh_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.report_export_html_btn)
        button_layout.addWidget(self.report_export_pdf_btn)
        button_layout.addWidget(self.report_export_json_btn)
        
        main_layout.addLayout(button_layout)
        
        # Filter Section
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel('Filter:'))
        
        self.report_status_filter = QtWidgets.QComboBox()
        self.report_status_filter.addItems(['All', 'Pass', 'Fail', 'Error', 'Not Run'])
        filter_layout.addWidget(self.report_status_filter)
        
        self.report_type_filter = QtWidgets.QComboBox()
        self.report_type_filter.addItems(['All', 'Digital Logic Test', 'Analog Sweep Test', 'Analog Static Test', 'Analog PWM Sensor', 'Phase Current Test', 'Temperature Validation Test', 'Fan Control Test', 'External 5V Test', 'DC Bus Sensing', 'Output Current Calibration', 'Charged HV Bus Test', 'Charger Functional Test'])
        filter_layout.addWidget(self.report_type_filter)
        
        filter_layout.addStretch()
        main_layout.addLayout(filter_layout)
        
        # Test Results Section
        results_group = QtWidgets.QGroupBox('Test Results')
        results_layout = QtWidgets.QVBoxLayout()
        
        # Use QTreeWidget for expandable rows
        self.report_tree = QtWidgets.QTreeWidget()
        self.report_tree.setHeaderLabels(['Test Name', 'Type', 'Status', 'Execution Time'])
        self.report_tree.setColumnWidth(0, 200)
        self.report_tree.setColumnWidth(1, 80)
        self.report_tree.setColumnWidth(2, 80)
        self.report_tree.setColumnWidth(3, 120)
        self.report_tree.setAlternatingRowColors(True)
        self.report_tree.setExpandsOnDoubleClick(False)
        self.report_tree.setItemsExpandable(True)
        
        results_layout.addWidget(self.report_tree)
        results_group.setLayout(results_layout)
        main_layout.addWidget(results_group, 1)
        
        # Wire buttons
        self.report_refresh_btn.clicked.connect(self._refresh_test_report)
        self.report_export_html_btn.clicked.connect(self._export_report_html)
        self.report_export_pdf_btn.clicked.connect(self._export_report_pdf)
        self.report_export_json_btn.clicked.connect(self._export_report_json)
        
        # Wire filters
        self.report_status_filter.currentTextChanged.connect(self._refresh_test_report)
        self.report_type_filter.currentTextChanged.connect(self._refresh_test_report)
        
        # Initial refresh
        self._refresh_test_report()
        
        return tab
    
    def _refresh_test_report(self):
        """Refresh the test report with current execution data, applying filters."""
        if not hasattr(self, 'report_tree'):
            return
        
        # Clear existing items
        self.report_tree.clear()
        
        # Get filter values
        status_filter = self.report_status_filter.currentText() if hasattr(self, 'report_status_filter') else 'All'
        type_filter = self.report_type_filter.currentText() if hasattr(self, 'report_type_filter') else 'All'
        
        # Check if there's any test data
        if not self._test_execution_data and not self._tests:
            # Show "No test results" message
            if hasattr(self, 'report_total_tests_label'):
                self.report_total_tests_label.setText('0')
                self.report_pass_count_label.setText('0')
                self.report_fail_count_label.setText('0')
                self.report_error_count_label.setText('0')
                self.report_pass_rate_label.setText('0%')
                self.report_total_time_label.setText('0.00s')
                self.report_last_updated_label.setText('Never')
            
            no_results_item = QtWidgets.QTreeWidgetItem(['No test results available', '', '', ''])
            self.report_tree.addTopLevelItem(no_results_item)
            return
        
        # Collect test data from execution data and test configurations
        test_items = []
        for test_name, exec_data in self._test_execution_data.items():
            # Find matching test config
            test_config = None
            for test in self._tests:
                if test.get('name', '') == test_name:
                    test_config = test
                    break
            
            status = exec_data.get('status', 'Not Run')
            test_type = exec_data.get('test_type', 'Unknown')
            # Handle legacy analog_static -> Analog Static Test (for backward compatibility)
            if test_type == 'Analog_static' or test_type == 'analog_static':
                test_type = 'Analog Static Test'
            
            # Apply filters
            if status_filter != 'All':
                if status_filter == 'Pass' and status != 'PASS':
                    continue
                elif status_filter == 'Fail' and status != 'FAIL':
                    continue
                elif status_filter == 'Error' and status != 'ERROR':
                    continue
                elif status_filter == 'Not Run' and status != 'Not Run':
                    continue
            
            if type_filter != 'All':
                if type_filter == 'Digital Logic Test' and test_type != 'Digital Logic Test':
                    continue
                elif type_filter == 'Analog Sweep Test' and test_type != 'Analog Sweep Test':
                    continue
                elif type_filter == 'Analog Static Test' and test_type != 'Analog Static Test':
                    continue
                elif type_filter == 'Phase Current Test' and test_type != 'Phase Current Test':
                    continue
                elif type_filter == 'Analog PWM Sensor' and test_type != 'Analog PWM Sensor':
                    continue
                elif type_filter == 'Temperature Validation Test' and test_type != 'Temperature Validation Test':
                    continue
                elif type_filter == 'Fan Control Test' and test_type != 'Fan Control Test':
                    continue
                elif type_filter == 'Charged HV Bus Test' and test_type != 'Charged HV Bus Test':
                    continue
                elif type_filter == 'Charger Functional Test' and test_type != 'Charger Functional Test':
                    continue
            
            test_items.append((test_name, test_config, exec_data))
        
        # Also include tests from _tests that haven't been executed yet (if filter allows)
        if status_filter == 'All' or status_filter == 'Not Run':
            for test in self._tests:
                test_name = test.get('name', '')
                if test_name not in self._test_execution_data:
                    act = test.get('actuation', {})
                    test_type = act.get('type', 'Unknown')
                    # Handle legacy analog_static -> Analog Static Test (for backward compatibility)
                    if test_type == 'Analog_static' or test_type == 'analog_static':
                        test_type = 'Analog Static Test'
                    
                    if type_filter != 'All':
                        if type_filter == 'Digital Logic Test' and test_type != 'Digital Logic Test':
                            continue
                        elif type_filter == 'Analog Sweep Test' and test_type != 'Analog Sweep Test':
                            continue
                        elif type_filter == 'Analog Static Test' and test_type != 'Analog Static Test':
                            continue
                        elif type_filter == 'Phase Current Test' and test_type != 'Phase Current Test':
                            continue
                        elif type_filter == 'Analog PWM Sensor' and test_type != 'Analog PWM Sensor':
                            continue
                        elif type_filter == 'Temperature Validation Test' and test_type != 'Temperature Validation Test':
                            continue
                        elif type_filter == 'Fan Control Test' and test_type != 'Fan Control Test':
                            continue
                    
                    test_items.append((test_name, test, {'status': 'Not Run', 'test_type': test_type}))
        
        # Calculate summary statistics
        total_executed = 0
        pass_count = 0
        fail_count = 0
        error_count = 0
        total_time = 0.0
        
        for _, _, exec_data in test_items:
            status = exec_data.get('status', 'Not Run')
            if status != 'Not Run':
                total_executed += 1
                if status == 'PASS':
                    pass_count += 1
                elif status == 'FAIL':
                    fail_count += 1
                elif status == 'ERROR':
                    error_count += 1
                
                # Parse execution time
                exec_time_str = exec_data.get('exec_time', '0s')
                try:
                    if exec_time_str.endswith('s'):
                        total_time += float(exec_time_str[:-1])
                except Exception:
                    pass
        
        pass_rate = (pass_count / total_executed * 100) if total_executed > 0 else 0
        
        # Update summary labels
        if hasattr(self, 'report_total_tests_label'):
            self.report_total_tests_label.setText(str(total_executed))
            self.report_pass_count_label.setText(str(pass_count))
            self.report_fail_count_label.setText(str(fail_count))
            self.report_error_count_label.setText(str(error_count))
            self.report_pass_rate_label.setText(f"{pass_rate:.1f}%")
            self.report_total_time_label.setText(f"{total_time:.2f}s")
            self.report_last_updated_label.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # Add test items to tree
        for test_name, test_config, exec_data in test_items:
            status = exec_data.get('status', 'Not Run')
            test_type = exec_data.get('test_type', 'Unknown')
            exec_time = exec_data.get('exec_time', 'N/A')
            
            # Create main test item
            test_item = QtWidgets.QTreeWidgetItem([test_name, test_type, status, exec_time])
            
            # Color code status
            if status == 'PASS':
                test_item.setForeground(2, QtGui.QColor('green'))
            elif status in ('FAIL', 'ERROR'):
                test_item.setForeground(2, QtGui.QColor('red'))
            
            # Add details as child items
            # Execution details
            details_item = QtWidgets.QTreeWidgetItem(['Details', '', '', ''])
            details_item.setExpanded(False)
            
            params = exec_data.get('parameters', 'N/A')
            notes = exec_data.get('notes', 'N/A')
            
            params_item = QtWidgets.QTreeWidgetItem(['Parameters', params, '', ''])
            details_item.addChild(params_item)
            
            notes_item = QtWidgets.QTreeWidgetItem(['Notes', notes, '', ''])
            details_item.addChild(notes_item)
            
            test_item.addChild(details_item)
            
            # For analog tests, add calibration and plot sections
            if test_type == 'Analog Sweep Test' and test_config:
                exec_data_full = self._test_execution_data.get(test_name, exec_data)
                calibration = exec_data_full.get('calibration')
                plot_data = exec_data_full.get('plot_data')
                
                if calibration:
                    calib_item = QtWidgets.QTreeWidgetItem(['Calibration Parameters', '', '', ''])
                    calib_item.setExpanded(False)
                    
                    gain = calibration.get('gain', 0)
                    offset = calibration.get('offset', 0)
                    r_squared = calibration.get('r_squared', 0)
                    mse = calibration.get('mse', 0)
                    max_error = calibration.get('max_error', 0)
                    mean_error = calibration.get('mean_error', 0)
                    data_points = calibration.get('data_points', 0)
                    
                    calib_item.addChild(QtWidgets.QTreeWidgetItem(['Gain (Slope)', f"{gain:.6f} mV/mV", '', '']))
                    calib_item.addChild(QtWidgets.QTreeWidgetItem(['Offset', f"{offset:.4f}", '', '']))
                    calib_item.addChild(QtWidgets.QTreeWidgetItem(['R² (Linearity)', f"{r_squared:.6f}", '', '']))
                    calib_item.addChild(QtWidgets.QTreeWidgetItem(['Mean Error', f"{mean_error:.4f}", '', '']))
                    calib_item.addChild(QtWidgets.QTreeWidgetItem(['Max Error', f"{max_error:.4f}", '', '']))
                    calib_item.addChild(QtWidgets.QTreeWidgetItem(['MSE', f"{mse:.4f}", '', '']))
                    calib_item.addChild(QtWidgets.QTreeWidgetItem(['Data Points', str(data_points), '', '']))
                    
                    # Add gain error if available
                    gain_error_percent = calibration.get('gain_error_percent')
                    expected_gain = calibration.get('expected_gain')
                    if gain_error_percent is not None and expected_gain is not None:
                        calib_item.addChild(QtWidgets.QTreeWidgetItem(['Expected Gain', f"{expected_gain:.6f}", '', '']))
                        calib_item.addChild(QtWidgets.QTreeWidgetItem(['Gain Error', f"{gain_error_percent:+.4f}%", '', '']))
                        
                        tolerance_check = calibration.get('tolerance_check')
                        if tolerance_check:
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['Tolerance Check', tolerance_check, '', '']))
                        
                        # Gain adjustment factor
                        if abs(gain) > 1e-10:
                            adjustment_factor = expected_gain / gain
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['Gain Adjustment Factor', f"{adjustment_factor:.6f}", '', '']))
                    
                    test_item.addChild(calib_item)
                
                # Add plot widget if plot data is available
                if plot_data and matplotlib_available:
                    plot_item = QtWidgets.QTreeWidgetItem(['Plot', '', '', ''])
                    plot_item.setExpanded(False)
                    
                    dac_voltages = plot_data.get('dac_voltages', [])
                    feedback_values = plot_data.get('feedback_values', [])
                    
                    if dac_voltages and feedback_values and len(dac_voltages) == len(feedback_values):
                        try:
                            # Create plot widget
                            plot_widget = QtWidgets.QWidget()
                            plot_layout = QtWidgets.QVBoxLayout(plot_widget)
                            plot_layout.setContentsMargins(0, 0, 0, 0)
                            
                            plot_figure = Figure(figsize=(5, 3))
                            plot_canvas = FigureCanvasQTAgg(plot_figure)
                            plot_axes = plot_figure.add_subplot(111)
                            
                            plot_axes.plot(dac_voltages, feedback_values, 'bo-', markersize=4, linewidth=1)
                            plot_axes.set_xlabel('DAC Output Voltage (mV)')
                            plot_axes.set_ylabel('Feedback Signal Value')
                            plot_axes.set_title(f'Feedback vs DAC Output: {test_name}')
                            plot_axes.grid(True, alpha=0.3)
                            
                            plot_figure.tight_layout()
                            plot_layout.addWidget(plot_canvas)
                            
                            # Set widget as item widget
                            self.report_tree.setItemWidget(plot_item, 1, plot_widget)
                        except Exception as e:
                            logger.error(f"Error creating plot in report: {e}", exc_info=True)
                            plot_item.setText(1, f"Plot error: {e}")
                    
                    test_item.addChild(plot_item)
            
            # For phase current calibration tests, add gain error/correction and plot sections
            is_phase_current = (test_type == 'Phase Current Test' or 
                              (test_config and test_config.get('type') == 'Phase Current Test'))
            if is_phase_current and test_config:
                exec_data_full = self._test_execution_data.get(test_name, exec_data)
                plot_data = exec_data_full.get('plot_data')
                
                if plot_data:
                    # Gain error and correction data
                    avg_gain_error_v = plot_data.get('avg_gain_error_v')
                    avg_gain_correction_v = plot_data.get('avg_gain_correction_v')
                    avg_gain_error_w = plot_data.get('avg_gain_error_w')
                    avg_gain_correction_w = plot_data.get('avg_gain_correction_w')
                    
                    if (avg_gain_error_v is not None or avg_gain_error_w is not None or
                        avg_gain_correction_v is not None or avg_gain_correction_w is not None):
                        gain_item = QtWidgets.QTreeWidgetItem(['Gain Error and Correction', '', '', ''])
                        gain_item.setExpanded(False)
                        
                        if avg_gain_error_v is not None:
                            gain_item.addChild(QtWidgets.QTreeWidgetItem(['Avg Gain Error V (%)', f"{avg_gain_error_v:+.4f}%", '', '']))
                            gain_item.addChild(QtWidgets.QTreeWidgetItem(['Avg Gain Error W (%)', f"{avg_gain_error_w:+.4f}%", '', '']))
                        if avg_gain_correction_v is not None:
                            gain_item.addChild(QtWidgets.QTreeWidgetItem(['Avg Gain Correction V', f"{avg_gain_correction_v:.6f}", '', '']))
                            gain_item.addChild(QtWidgets.QTreeWidgetItem(['Avg Gain Correction W', f"{avg_gain_correction_w:.6f}", '', '']))
                        
                        test_item.addChild(gain_item)
                    
                    # Add plot widget if plot data is available
                    if matplotlib_available:
                        plot_item = QtWidgets.QTreeWidgetItem(['Plot: CAN vs Oscilloscope', '', '', ''])
                        plot_item.setExpanded(False)
                        
                        osc_ch1 = plot_data.get('osc_ch1', [])
                        osc_ch2 = plot_data.get('osc_ch2', [])
                        can_v = plot_data.get('can_v', [])
                        can_w = plot_data.get('can_w', [])
                        
                        if (osc_ch1 or osc_ch2 or can_v or can_w):
                            try:
                                # Create plot widget
                                plot_widget = QtWidgets.QWidget()
                                plot_layout = QtWidgets.QVBoxLayout(plot_widget)
                                plot_layout.setContentsMargins(0, 0, 0, 0)
                                
                                plot_figure = Figure(figsize=(10, 4))
                                plot_canvas = FigureCanvasQTAgg(plot_figure)
                                
                                # Phase V plot
                                plot_axes_v = plot_figure.add_subplot(121)
                                
                                # Filter out NaN values
                                osc_v_clean = []
                                can_v_clean = []
                                if osc_ch1 and can_v:
                                    min_len = min(len(osc_ch1), len(can_v))
                                    for i in range(min_len):
                                        osc_val = osc_ch1[i]
                                        can_val = can_v[i]
                                        if (isinstance(osc_val, (int, float)) and isinstance(can_val, (int, float)) and
                                            not (isinstance(osc_val, float) and osc_val != osc_val) and
                                            not (isinstance(can_val, float) and can_val != can_val)):
                                            osc_v_clean.append(osc_val)
                                            can_v_clean.append(can_val)
                                
                                if osc_v_clean and can_v_clean:
                                    plot_axes_v.plot(osc_v_clean, can_v_clean, 'bo', markersize=4, label='Phase V')
                                    plot_axes_v.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
                                
                                plot_axes_v.set_xlabel('Avg Phase V Current from Oscilloscope (A)')
                                plot_axes_v.set_ylabel('Avg Phase V Current from CAN (A)')
                                plot_axes_v.set_title('Phase V: CAN vs Oscilloscope')
                                plot_axes_v.grid(True, alpha=0.3)
                                plot_axes_v.legend()
                                
                                # Phase W plot
                                plot_axes_w = plot_figure.add_subplot(122)
                                
                                # Filter out NaN values
                                osc_w_clean = []
                                can_w_clean = []
                                if osc_ch2 and can_w:
                                    min_len = min(len(osc_ch2), len(can_w))
                                    for i in range(min_len):
                                        osc_val = osc_ch2[i]
                                        can_val = can_w[i]
                                        if (isinstance(osc_val, (int, float)) and isinstance(can_val, (int, float)) and
                                            not (isinstance(osc_val, float) and osc_val != osc_val) and
                                            not (isinstance(can_val, float) and can_val != can_val)):
                                            osc_w_clean.append(osc_val)
                                            can_w_clean.append(can_val)
                                
                                if osc_w_clean and can_w_clean:
                                    plot_axes_w.plot(osc_w_clean, can_w_clean, 'ro', markersize=4, label='Phase W')
                                    plot_axes_w.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
                                
                                plot_axes_w.set_xlabel('Avg Phase W Current from Oscilloscope (A)')
                                plot_axes_w.set_ylabel('Avg Phase W Current from CAN (A)')
                                plot_axes_w.set_title('Phase W: CAN vs Oscilloscope')
                                plot_axes_w.grid(True, alpha=0.3)
                                plot_axes_w.legend()
                                
                                plot_figure.tight_layout()
                                plot_layout.addWidget(plot_canvas)
                                
                                # Set widget as item widget
                                self.report_tree.setItemWidget(plot_item, 1, plot_widget)
                            except Exception as e:
                                logger.error(f"Error creating phase current plot in report: {e}", exc_info=True)
                                plot_item.setText(1, f"Plot error: {e}")
                        
                        test_item.addChild(plot_item)
            
            # For Output Current Calibration tests, add calibration results and plot sections
            is_output_current_calibration = (test_type == 'Output Current Calibration' or 
                                           (test_config and test_config.get('type') == 'Output Current Calibration'))
            if is_output_current_calibration and test_config:
                exec_data_full = self._test_execution_data.get(test_name, exec_data)
                plot_data = exec_data_full.get('plot_data')
                
                if plot_data:
                    # Check if we have dual sweep data (new format) or single plot data (old format)
                    first_sweep_data = plot_data.get('first_sweep')
                    second_sweep_data = plot_data.get('second_sweep')
                    
                    if first_sweep_data and second_sweep_data:
                        # New format: Dual sweep results
                        calib_item = QtWidgets.QTreeWidgetItem(['Calibration Results', '', '', ''])
                        calib_item.setExpanded(False)
                        
                        # First sweep results
                        first_slope = first_sweep_data.get('slope')
                        first_intercept = first_sweep_data.get('intercept')
                        first_gain_error = first_sweep_data.get('gain_error')
                        first_adjustment = first_sweep_data.get('adjustment_factor')
                        first_trim = first_sweep_data.get('trim_value')
                        if first_slope is not None:
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['First Sweep (Trim Value)', f"{first_trim}%", '', '']))
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['First Sweep Slope', f"{first_slope:.6f} (ideal: 1.0)", '', '']))
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['First Sweep Intercept', f"{first_intercept:.6f} A", '', '']))
                        if first_gain_error is not None:
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['First Sweep Gain Error (%)', f"{first_gain_error:.4f}%", '', '']))
                        if first_adjustment is not None:
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['First Sweep Adjustment Factor', f"{first_adjustment:.6f}", '', '']))
                        
                        # Calculated trim value
                        calculated_trim = plot_data.get('calculated_trim_value')
                        if calculated_trim is not None:
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['Calculated Trim Value (%)', f"{calculated_trim:.4f}%", '', '']))
                        
                        # Second sweep results
                        second_slope = second_sweep_data.get('slope')
                        second_intercept = second_sweep_data.get('intercept')
                        second_gain_error = second_sweep_data.get('gain_error')
                        second_trim = second_sweep_data.get('trim_value')
                        tolerance_percent = plot_data.get('tolerance_percent')
                        if second_slope is not None:
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['Second Sweep (Trim Value)', f"{second_trim:.4f}%", '', '']))
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['Second Sweep Slope', f"{second_slope:.6f} (ideal: 1.0)", '', '']))
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['Second Sweep Intercept', f"{second_intercept:.6f} A", '', '']))
                        if second_gain_error is not None:
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['Second Sweep Gain Error (%)', f"{second_gain_error:.4f}%", '', '']))
                        if tolerance_percent is not None:
                            calib_item.addChild(QtWidgets.QTreeWidgetItem(['Tolerance (%)', f"{tolerance_percent:.4f}%", '', '']))
                            if second_gain_error is not None:
                                passed = abs(second_gain_error) <= tolerance_percent
                                calib_item.addChild(QtWidgets.QTreeWidgetItem(['Result', 'PASS' if passed else 'FAIL', '', '']))
                        
                        test_item.addChild(calib_item)
                        
                        # Add dual plot widgets
                        if matplotlib_available:
                            # Helper function to create a plot
                            def create_plot_for_report(plot_data_dict, plot_title):
                                plot_figure = Figure(figsize=(8, 6))
                                plot_axes = plot_figure.add_subplot(111)
                                
                                plot_osc_averages = plot_data_dict.get('osc_averages', [])
                                plot_can_averages = plot_data_dict.get('can_averages', [])
                                slope = plot_data_dict.get('slope')
                                intercept = plot_data_dict.get('intercept')
                                
                                if plot_osc_averages and plot_can_averages:
                                    # Filter out NaN values
                                    osc_clean = []
                                    can_clean = []
                                    min_len = min(len(plot_osc_averages), len(plot_can_averages))
                                    for i in range(min_len):
                                        osc_val = plot_osc_averages[i]
                                        can_val = plot_can_averages[i]
                                        if (isinstance(osc_val, (int, float)) and isinstance(can_val, (int, float)) and
                                            not (isinstance(osc_val, float) and osc_val != osc_val) and
                                            not (isinstance(can_val, float) and can_val != can_val)):
                                            osc_clean.append(osc_val)
                                            can_clean.append(can_val)
                                    
                                    if osc_clean and can_clean:
                                        plot_axes.plot(osc_clean, can_clean, 'bo', markersize=6, label='Data Points')
                                        plot_axes.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
                                        
                                        # Add regression line if slope and intercept are available
                                        if slope is not None and intercept is not None and isinstance(slope, (int, float)) and isinstance(intercept, (int, float)):
                                            x_min = min(osc_clean)
                                            x_max = max(osc_clean)
                                            x_reg = [x_min, x_max]
                                            y_reg = [slope * x + intercept for x in x_reg]
                                            plot_axes.plot(x_reg, y_reg, 'r-', linewidth=2, alpha=0.7, label=f'Regression (slope={slope:.4f})')
                                        
                                        plot_axes.set_xlabel('Oscilloscope Measurement (A)')
                                        plot_axes.set_ylabel('DUT Measurement (A)')
                                        plot_axes.set_title(plot_title)
                                        plot_axes.grid(True, alpha=0.3)
                                        plot_axes.legend()
                                        plot_axes.relim()
                                        plot_axes.autoscale()
                                
                                plot_figure.tight_layout()
                                return plot_figure
                            
                            # First sweep plot
                            first_plot_item = QtWidgets.QTreeWidgetItem([f'Plot: {first_sweep_data.get("plot_label", "First Sweep")}', '', '', ''])
                            first_plot_item.setExpanded(False)
                            try:
                                plot_figure = create_plot_for_report(first_sweep_data, first_sweep_data.get("plot_label", "First Sweep"))
                                plot_canvas = FigureCanvasQTAgg(plot_figure)
                                plot_widget = QtWidgets.QWidget()
                                plot_layout = QtWidgets.QVBoxLayout(plot_widget)
                                plot_layout.setContentsMargins(0, 0, 0, 0)
                                plot_layout.addWidget(plot_canvas)
                                self.report_tree.setItemWidget(first_plot_item, 1, plot_widget)
                            except Exception as e:
                                logger.error(f"Error creating first sweep plot in report: {e}", exc_info=True)
                                first_plot_item.setText(1, f"Plot error: {e}")
                            test_item.addChild(first_plot_item)
                            
                            # Second sweep plot
                            second_plot_item = QtWidgets.QTreeWidgetItem([f'Plot: {second_sweep_data.get("plot_label", "Second Sweep")}', '', '', ''])
                            second_plot_item.setExpanded(False)
                            try:
                                plot_figure = create_plot_for_report(second_sweep_data, second_sweep_data.get("plot_label", "Second Sweep"))
                                plot_canvas = FigureCanvasQTAgg(plot_figure)
                                plot_widget = QtWidgets.QWidget()
                                plot_layout = QtWidgets.QVBoxLayout(plot_widget)
                                plot_layout.setContentsMargins(0, 0, 0, 0)
                                plot_layout.addWidget(plot_canvas)
                                self.report_tree.setItemWidget(second_plot_item, 1, plot_widget)
                            except Exception as e:
                                logger.error(f"Error creating second sweep plot in report: {e}", exc_info=True)
                                second_plot_item.setText(1, f"Plot error: {e}")
                            test_item.addChild(second_plot_item)
                    else:
                        # Old format: Single plot (backward compatibility)
                        slope = plot_data.get('slope')
                        intercept = plot_data.get('intercept')
                        gain_error = plot_data.get('gain_error') or plot_data.get('avg_gain_error')
                        adjustment_factor = plot_data.get('adjustment_factor')
                        tolerance_percent = plot_data.get('tolerance_percent')
                        
                        if (slope is not None or intercept is not None or gain_error is not None or 
                            adjustment_factor is not None or tolerance_percent is not None):
                            calib_item = QtWidgets.QTreeWidgetItem(['Calibration Results', '', '', ''])
                            calib_item.setExpanded(False)
                            
                            if slope is not None:
                                calib_item.addChild(QtWidgets.QTreeWidgetItem(['Slope', f"{slope:.6f} (ideal: 1.0)", '', '']))
                            if intercept is not None:
                                calib_item.addChild(QtWidgets.QTreeWidgetItem(['Intercept (A)', f"{intercept:.6f}", '', '']))
                            if gain_error is not None:
                                if plot_data.get('avg_gain_error') is not None:
                                    calib_item.addChild(QtWidgets.QTreeWidgetItem(['Average Gain Error (%)', f"{gain_error:.4f}%", '', '']))
                                else:
                                    calib_item.addChild(QtWidgets.QTreeWidgetItem(['Gain Error (%)', f"{gain_error:+.4f}%", '', '']))
                            if adjustment_factor is not None:
                                calib_item.addChild(QtWidgets.QTreeWidgetItem(['Adjustment Factor', f"{adjustment_factor:.6f}", '', '']))
                            if tolerance_percent is not None:
                                calib_item.addChild(QtWidgets.QTreeWidgetItem(['Tolerance (%)', f"{tolerance_percent:.4f}%", '', '']))
                                if gain_error is not None:
                                    passed = abs(gain_error) <= tolerance_percent
                                    calib_item.addChild(QtWidgets.QTreeWidgetItem(['Result', 'PASS' if passed else 'FAIL', '', '']))
                            
                            test_item.addChild(calib_item)
                        
                        # Add plot widget if plot data is available
                        if matplotlib_available:
                            plot_item = QtWidgets.QTreeWidgetItem(['Plot: DUT vs Oscilloscope', '', '', ''])
                            plot_item.setExpanded(False)
                            
                            osc_averages = plot_data.get('osc_averages', [])
                            can_averages = plot_data.get('can_averages', [])
                            
                            if osc_averages and can_averages:
                                try:
                                    plot_widget = QtWidgets.QWidget()
                                    plot_layout = QtWidgets.QVBoxLayout(plot_widget)
                                    plot_layout.setContentsMargins(0, 0, 0, 0)
                                    
                                    plot_figure = Figure(figsize=(8, 6))
                                    plot_canvas = FigureCanvasQTAgg(plot_figure)
                                    plot_axes = plot_figure.add_subplot(111)
                                    
                                    osc_clean = []
                                    can_clean = []
                                    min_len = min(len(osc_averages), len(can_averages))
                                    for i in range(min_len):
                                        osc_val = osc_averages[i]
                                        can_val = can_averages[i]
                                        if (isinstance(osc_val, (int, float)) and isinstance(can_val, (int, float)) and
                                            not (isinstance(osc_val, float) and osc_val != osc_val) and
                                            not (isinstance(can_val, float) and can_val != can_val)):
                                            osc_clean.append(osc_val)
                                            can_clean.append(can_val)
                                    
                                    if osc_clean and can_clean:
                                        plot_axes.plot(osc_clean, can_clean, 'bo', markersize=6, label='Data Points')
                                        plot_axes.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
                                        
                                        if slope is not None and intercept is not None:
                                            x_min = min(osc_clean)
                                            x_max = max(osc_clean)
                                            x_reg = [x_min, x_max]
                                            y_reg = [slope * x + intercept for x in x_reg]
                                            plot_axes.plot(x_reg, y_reg, 'r-', linewidth=2, alpha=0.7, label=f'Regression (slope={slope:.4f})')
                                        
                                        plot_axes.set_xlabel('Oscilloscope Measurement (A)')
                                        plot_axes.set_ylabel('DUT Measurement (A)')
                                        plot_axes.set_title(f'Output Current Calibration: DUT vs Oscilloscope{(": " + test_name) if test_name else ""}')
                                        plot_axes.grid(True, alpha=0.3)
                                        plot_axes.legend()
                                        plot_axes.relim()
                                        plot_axes.autoscale()
                                    
                                    plot_figure.tight_layout()
                                    plot_layout.addWidget(plot_canvas)
                                    self.report_tree.setItemWidget(plot_item, 1, plot_widget)
                                except Exception as e:
                                    logger.error(f"Error creating Output Current Calibration plot in report: {e}", exc_info=True)
                                    plot_item.setText(1, f"Plot error: {e}")
                            
                            test_item.addChild(plot_item)
            
            self.report_tree.addTopLevelItem(test_item)
        
        # Expand all items by default (user can collapse)
        self.report_tree.expandAll()
    
    def _generate_test_plot_image(self, test_name: str, dac_voltages: list, feedback_values: list, 
                                  output_format: str = 'png') -> Optional[bytes]:
        """Generate a plot image for export (PNG or other formats).
        
        Args:
            test_name: Name of the test
            dac_voltages: List of DAC voltage values
            feedback_values: List of feedback signal values
            output_format: Image format ('png', 'svg', etc.)
            
        Returns:
            Image bytes if successful, None otherwise
        """
        if not matplotlib_available or not dac_voltages or not feedback_values:
            return None
        
        if len(dac_voltages) != len(feedback_values):
            return None
        
        try:
            import io
            from matplotlib.figure import Figure
            
            fig = Figure(figsize=(6, 4))
            ax = fig.add_subplot(111)
            
            ax.plot(dac_voltages, feedback_values, 'bo-', markersize=6, linewidth=1)
            ax.set_xlabel('DAC Output Voltage (mV)')
            ax.set_ylabel('Feedback Signal Value')
            ax.set_title(f'Feedback vs DAC Output: {test_name}')
            ax.grid(True, alpha=0.3)
            
            fig.tight_layout()
            
            # Save to bytes buffer
            buf = io.BytesIO()
            fig.savefig(buf, format=output_format, dpi=100, bbox_inches='tight')
            buf.seek(0)
            image_bytes = buf.read()
            buf.close()
            
            return image_bytes
        except Exception as e:
            logger.error(f"Error generating plot image: {e}", exc_info=True)
            return None
    
    def _generate_test_plot_base64(self, test_name: str, dac_voltages: list, feedback_values: list) -> Optional[str]:
        """Generate a base64-encoded plot image for HTML embedding.
        
        Args:
            test_name: Name of the test
            dac_voltages: List of DAC voltage values
            feedback_values: List of feedback signal values
            
        Returns:
            Base64-encoded image string if successful, None otherwise
        """
        image_bytes = self._generate_test_plot_image(test_name, dac_voltages, feedback_values, 'png')
        if image_bytes:
            return base64.b64encode(image_bytes).decode('utf-8')
        return None
    
    def _generate_phase_current_plot_image(self, test_name: str, osc_v: list, can_v: list, 
                                           osc_w: list, can_w: list, output_format: str = 'png') -> Optional[bytes]:
        """Generate a phase current plot image for export (CAN vs Oscilloscope).
        
        Args:
            test_name: Name of the test
            osc_v: List of oscilloscope Phase V current values
            can_v: List of CAN Phase V current values
            osc_w: List of oscilloscope Phase W current values
            can_w: List of CAN Phase W current values
            output_format: Image format ('png', 'svg', etc.)
            
        Returns:
            Image bytes if successful, None otherwise
        """
        if not matplotlib_available:
            return None
        
        # Filter out NaN values
        osc_v_clean = []
        can_v_clean = []
        osc_w_clean = []
        can_w_clean = []
        
        if osc_v and can_v:
            min_len = min(len(osc_v), len(can_v))
            for i in range(min_len):
                osc_val = osc_v[i]
                can_val = can_v[i]
                if (isinstance(osc_val, (int, float)) and isinstance(can_val, (int, float)) and
                    not (isinstance(osc_val, float) and osc_val != osc_val) and
                    not (isinstance(can_val, float) and can_val != can_val)):
                    osc_v_clean.append(osc_val)
                    can_v_clean.append(can_val)
        
        if osc_w and can_w:
            min_len = min(len(osc_w), len(can_w))
            for i in range(min_len):
                osc_val = osc_w[i]
                can_val = can_w[i]
                if (isinstance(osc_val, (int, float)) and isinstance(can_val, (int, float)) and
                    not (isinstance(osc_val, float) and osc_val != osc_val) and
                    not (isinstance(can_val, float) and can_val != can_val)):
                    osc_w_clean.append(osc_val)
                    can_w_clean.append(can_val)
        
        if not (osc_v_clean and can_v_clean) and not (osc_w_clean and can_w_clean):
            return None
        
        try:
            import io
            from matplotlib.figure import Figure
            
            fig = Figure(figsize=(12, 5))
            
            # Phase V plot
            ax_v = fig.add_subplot(121)
            if osc_v_clean and can_v_clean:
                ax_v.plot(osc_v_clean, can_v_clean, 'bo', markersize=6, label='Phase V')
                # Add diagonal reference line (y=x)
                ax_v.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
            ax_v.set_xlabel('Average Phase V Current from Oscilloscope (A)')
            ax_v.set_ylabel('Average Phase V Current from CAN (A)')
            ax_v.set_title('Phase V: CAN vs Oscilloscope')
            ax_v.grid(True, alpha=0.3)
            ax_v.legend()
            
            # Phase W plot
            ax_w = fig.add_subplot(122)
            if osc_w_clean and can_w_clean:
                ax_w.plot(osc_w_clean, can_w_clean, 'ro', markersize=6, label='Phase W')
                # Add diagonal reference line (y=x)
                ax_w.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
            ax_w.set_xlabel('Average Phase W Current from Oscilloscope (A)')
            ax_w.set_ylabel('Average Phase W Current from CAN (A)')
            ax_w.set_title('Phase W: CAN vs Oscilloscope')
            ax_w.grid(True, alpha=0.3)
            ax_w.legend()
            
            fig.tight_layout()
            
            # Save to bytes buffer
            buf = io.BytesIO()
            fig.savefig(buf, format=output_format, dpi=100, bbox_inches='tight')
            buf.seek(0)
            image_bytes = buf.read()
            buf.close()
            
            return image_bytes
        except Exception as e:
            logger.error(f"Error generating phase current plot image: {e}", exc_info=True)
            return None
    
    def _generate_phase_current_plot_base64(self, test_name: str, osc_v: list, can_v: list,
                                            osc_w: list, can_w: list) -> Optional[str]:
        """Generate a base64-encoded phase current plot image for HTML embedding.
        
        Args:
            test_name: Name of the test
            osc_v: List of oscilloscope Phase V current values
            can_v: List of CAN Phase V current values
            osc_w: List of oscilloscope Phase W current values
            can_w: List of CAN Phase W current values
            
        Returns:
            Base64-encoded image string if successful, None otherwise
        """
        image_bytes = self._generate_phase_current_plot_image(test_name, osc_v, can_v, osc_w, can_w, 'png')
        if image_bytes:
            return base64.b64encode(image_bytes).decode('utf-8')
        return None
    
    def _generate_output_current_calibration_plot_image(self, test_name: str, osc_averages: list, 
                                                        can_averages: list, slope: Optional[float] = None,
                                                        intercept: Optional[float] = None,
                                                        output_format: str = 'png') -> Optional[bytes]:
        """Generate an Output Current Calibration plot image for export (DUT vs Oscilloscope).
        
        Args:
            test_name: Name of the test
            osc_averages: List of oscilloscope average current values
            can_averages: List of CAN average current values
            slope: Optional regression slope
            intercept: Optional regression intercept
            output_format: Image format ('png', 'svg', etc.)
            
        Returns:
            Image bytes if successful, None otherwise
        """
        if not matplotlib_available:
            return None
        
        # Filter out NaN values
        osc_clean = []
        can_clean = []
        if osc_averages and can_averages:
            min_len = min(len(osc_averages), len(can_averages))
            for i in range(min_len):
                osc_val = osc_averages[i]
                can_val = can_averages[i]
                if (isinstance(osc_val, (int, float)) and isinstance(can_val, (int, float)) and
                    not (isinstance(osc_val, float) and osc_val != osc_val) and
                    not (isinstance(can_val, float) and can_val != can_val)):
                    osc_clean.append(osc_val)
                    can_clean.append(can_val)
        
        if not (osc_clean and can_clean):
            return None
        
        try:
            import io
            from matplotlib.figure import Figure
            
            fig = Figure(figsize=(8, 6))
            ax = fig.add_subplot(111)
            
            # Plot data points
            ax.plot(osc_clean, can_clean, 'bo', markersize=6, label='Data Points')
            
            # Add diagonal reference line (y=x) for ideal line
            ax.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
            
            # Add regression line if available
            if slope is not None and intercept is not None:
                x_min = min(osc_clean)
                x_max = max(osc_clean)
                x_reg = [x_min, x_max]
                y_reg = [slope * x + intercept for x in x_reg]
                ax.plot(x_reg, y_reg, 'r-', linewidth=2, alpha=0.7, label=f'Regression (slope={slope:.4f})')
            
            ax.set_xlabel('Oscilloscope Measurement (A)')
            ax.set_ylabel('DUT Measurement (A)')
            ax.set_title(f'Output Current Calibration: DUT vs Oscilloscope{(": " + test_name) if test_name else ""}')
            ax.grid(True, alpha=0.3)
            ax.legend()
            
            # Auto-scale axes to fit all data
            ax.relim()
            ax.autoscale()
            
            fig.tight_layout()
            
            # Save to bytes buffer
            buf = io.BytesIO()
            fig.savefig(buf, format=output_format, dpi=100, bbox_inches='tight')
            buf.seek(0)
            image_bytes = buf.read()
            buf.close()
            
            return image_bytes
        except Exception as e:
            logger.error(f"Error generating Output Current Calibration plot image: {e}", exc_info=True)
            return None
    
    def _generate_output_current_calibration_plot_base64(self, test_name: str, osc_averages: list,
                                                          can_averages: list, slope: Optional[float] = None,
                                                          intercept: Optional[float] = None) -> Optional[str]:
        """Generate a base64-encoded Output Current Calibration plot image for HTML embedding.
        
        Args:
            test_name: Name of the test
            osc_averages: List of oscilloscope average current values
            can_averages: List of CAN average current values
            slope: Optional regression slope
            intercept: Optional regression intercept
            
        Returns:
            Base64-encoded image string if successful, None otherwise
        """
        image_bytes = self._generate_output_current_calibration_plot_image(test_name, osc_averages, can_averages, slope, intercept, 'png')
        if image_bytes:
            return base64.b64encode(image_bytes).decode('utf-8')
        return None
    
    def _export_report_json(self):
        """Export test report as JSON file."""
        try:
            default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', 'data', 'reports')
            os.makedirs(default_dir, exist_ok=True)
        except Exception:
            default_dir = os.path.expanduser('~')
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_filename = f'test_report_{timestamp}.json'
        
        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Export Test Report as JSON',
            os.path.join(default_dir, default_filename),
            'JSON Files (*.json);;All Files (*)'
        )
        
        if not fname:
            return
        
        try:
            # Extract DUT UID from execution data using helper method
            dut_uid = self._get_dut_uid_from_execution_data()
            
            # Collect all test data
            metadata = {
                'report_type': 'Test Report',
                'generated_at': datetime.now().isoformat() + 'Z',
                'application': 'EOL Host Application'
            }
            if dut_uid is not None:
                metadata['dut_uid'] = dut_uid
            
            report_data = {
                'metadata': metadata,
                'summary': {},
                'tests': []
            }
            
            # Calculate summary
            total_executed = 0
            pass_count = 0
            fail_count = 0
            error_count = 0
            total_time = 0.0
            
            test_results = []
            for test_name, exec_data in self._test_execution_data.items():
                status = exec_data.get('status', 'Not Run')
                if status != 'Not Run':
                    total_executed += 1
                    if status == 'PASS':
                        pass_count += 1
                    elif status == 'FAIL':
                        fail_count += 1
                    elif status == 'ERROR':
                        error_count += 1
                    
                    exec_time_str = exec_data.get('exec_time', '0s')
                    try:
                        if exec_time_str.endswith('s'):
                            total_time += float(exec_time_str[:-1])
                    except Exception:
                        pass
                
                # Find test config
                test_config = None
                for test in self._tests:
                    if test.get('name', '') == test_name:
                        test_config = test
                        break
                
                # Build test result entry
                test_result = {
                    'test_configuration': test_config if test_config else {'name': test_name},
                    'execution_data': exec_data.copy()
                }
                
                # Include plot data if analog test
                if exec_data.get('test_type') == 'Analog':
                    plot_data = exec_data.get('plot_data')
                    if plot_data:
                        test_result['plot_data'] = {
                            'dac_voltages': list(plot_data.get('dac_voltages', [])),
                            'feedback_values': list(plot_data.get('feedback_values', []))
                        }
                    
                    calibration = exec_data.get('calibration')
                    if calibration:
                        test_result['calibration'] = calibration.copy()
                
                # Include plot data and gain error/correction for phase current tests
                elif test_config and test_config.get('type') == 'Phase Current Test':
                    plot_data = exec_data.get('plot_data')
                    if plot_data:
                        test_result['plot_data'] = {
                            'iq_refs': list(plot_data.get('iq_refs', [])),
                            'osc_ch1': list(plot_data.get('osc_ch1', [])),
                            'osc_ch2': list(plot_data.get('osc_ch2', [])),
                            'can_v': list(plot_data.get('can_v', [])),
                            'can_w': list(plot_data.get('can_w', [])),
                            'gain_errors_v': list(plot_data.get('gain_errors_v', [])),
                            'gain_corrections_v': list(plot_data.get('gain_corrections_v', [])),
                            'gain_errors_w': list(plot_data.get('gain_errors_w', [])),
                            'gain_corrections_w': list(plot_data.get('gain_corrections_w', [])),
                            'avg_gain_error_v': plot_data.get('avg_gain_error_v'),
                            'avg_gain_correction_v': plot_data.get('avg_gain_correction_v'),
                            'avg_gain_error_w': plot_data.get('avg_gain_error_w'),
                            'avg_gain_correction_w': plot_data.get('avg_gain_correction_w')
                        }
                
                test_results.append(test_result)
            
            pass_rate = (pass_count / total_executed * 100) if total_executed > 0 else 0
            
            report_data['summary'] = {
                'total_tests_executed': total_executed,
                'pass_count': pass_count,
                'fail_count': fail_count,
                'error_count': error_count,
                'pass_rate_percent': round(pass_rate, 2),
                'total_execution_time_seconds': round(total_time, 2)
            }
            
            report_data['tests'] = test_results
            
            # Write JSON file
            with open(fname, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported test report to JSON: {os.path.basename(fname)}")
            QtWidgets.QMessageBox.information(self, 'Export Successful', 
                f'Test report exported to:\n{os.path.basename(fname)}')
        except Exception as e:
            logger.error(f"Failed to export JSON report: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Export Error', 
                f'Failed to export JSON report:\n{e}')
    
    def _export_report_html(self):
        """Export test report as HTML file with embedded plots and styled tables."""
        try:
            default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', 'data', 'reports')
            os.makedirs(default_dir, exist_ok=True)
        except Exception:
            default_dir = os.path.expanduser('~')
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_filename = f'test_report_{timestamp}.html'
        
        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Export Test Report as HTML',
            os.path.join(default_dir, default_filename),
            'HTML Files (*.html);;All Files (*)'
        )
        
        if not fname:
            return
        
        try:
            # Calculate summary
            total_executed = 0
            pass_count = 0
            fail_count = 0
            error_count = 0
            total_time = 0.0
            
            for exec_data in self._test_execution_data.values():
                status = exec_data.get('status', 'Not Run')
                if status != 'Not Run':
                    total_executed += 1
                    if status == 'PASS':
                        pass_count += 1
                    elif status == 'FAIL':
                        fail_count += 1
                    elif status == 'ERROR':
                        error_count += 1
                    
                    exec_time_str = exec_data.get('exec_time', '0s')
                    try:
                        if exec_time_str.endswith('s'):
                            total_time += float(exec_time_str[:-1])
                    except Exception:
                        pass
            
            pass_rate = (pass_count / total_executed * 100) if total_executed > 0 else 0
            
            # Generate HTML
            html_parts = []
            html_parts.append('<!DOCTYPE html>')
            html_parts.append('<html>')
            html_parts.append('<head>')
            html_parts.append('<meta charset="UTF-8">')
            html_parts.append('<title>Test Report</title>')
            html_parts.append('<style>')
            html_parts.append('body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }')
            html_parts.append('.header { background-color: #2c3e50; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }')
            html_parts.append('.header h1 { margin: 0; }')
            html_parts.append('.summary { background-color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }')
            html_parts.append('.summary table { width: 100%; border-collapse: collapse; }')
            html_parts.append('.summary td { padding: 8px; border-bottom: 1px solid #ddd; }')
            html_parts.append('.summary td:first-child { font-weight: bold; width: 200px; }')
            html_parts.append('.test-section { background-color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }')
            html_parts.append('.test-section h2 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }')
            html_parts.append('.status-pass { color: green; font-weight: bold; }')
            html_parts.append('.status-fail { color: red; font-weight: bold; }')
            html_parts.append('.status-error { color: red; font-weight: bold; }')
            html_parts.append('.calibration-table { width: 100%; border-collapse: collapse; margin-top: 10px; }')
            html_parts.append('.calibration-table th, .calibration-table td { padding: 8px; text-align: left; border: 1px solid #ddd; }')
            html_parts.append('.calibration-table th { background-color: #3498db; color: white; }')
            html_parts.append('.calibration-table tr:nth-child(even) { background-color: #f2f2f2; }')
            html_parts.append('.plot-image { max-width: 100%; height: auto; margin-top: 10px; }')
            html_parts.append('.details { margin-top: 10px; }')
            html_parts.append('.details p { margin: 5px 0; }')
            html_parts.append('</style>')
            html_parts.append('</head>')
            html_parts.append('<body>')
            
            # Extract DUT UID from execution data using helper method
            dut_uid = self._get_dut_uid_from_execution_data()
            
            # Header
            html_parts.append('<div class="header">')
            html_parts.append(f'<h1>Test Report</h1>')
            html_parts.append(f'<p>Generated: {escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</p>')
            if dut_uid is not None:
                # Escape DUT UID to prevent XSS (defense in depth)
                escaped_uid = escape(str(dut_uid))
                html_parts.append(f'<p><strong>DUT UID:</strong> {escaped_uid}</p>')
            html_parts.append('</div>')
            
            # Summary
            html_parts.append('<div class="summary">')
            html_parts.append('<h2>Summary</h2>')
            html_parts.append('<table>')
            if dut_uid is not None:
                # Escape DUT UID for safety
                escaped_uid = escape(str(dut_uid))
                html_parts.append(f'<tr><td>DUT UID:</td><td>{escaped_uid}</td></tr>')
            html_parts.append(f'<tr><td>Total Tests Executed:</td><td>{escape(str(total_executed))}</td></tr>')
            html_parts.append(f'<tr><td>Passed:</td><td class="status-pass">{escape(str(pass_count))}</td></tr>')
            html_parts.append(f'<tr><td>Failed:</td><td class="status-fail">{escape(str(fail_count))}</td></tr>')
            html_parts.append(f'<tr><td>Errors:</td><td class="status-error">{escape(str(error_count))}</td></tr>')
            html_parts.append(f'<tr><td>Pass Rate:</td><td>{escape(f"{pass_rate:.1f}%")}</td></tr>')
            html_parts.append(f'<tr><td>Total Execution Time:</td><td>{escape(f"{total_time:.2f}s")}</td></tr>')
            html_parts.append('</table>')
            html_parts.append('</div>')
            
            # Test results
            for test_name, exec_data in self._test_execution_data.items():
                status = exec_data.get('status', 'Not Run')
                test_type = exec_data.get('test_type', 'Unknown')
                exec_time = exec_data.get('exec_time', 'N/A')
                params = exec_data.get('parameters', 'N/A')
                notes = exec_data.get('notes', 'N/A')
                
                # Find test config
                test_config = None
                for test in self._tests:
                    if test.get('name', '') == test_name:
                        test_config = test
                        break
                
                status_class = 'status-pass' if status == 'PASS' else ('status-fail' if status == 'FAIL' else 'status-error')
                
                html_parts.append('<div class="test-section">')
                html_parts.append(f'<h2>{escape(test_name)}</h2>')
                html_parts.append('<div class="details">')
                html_parts.append(f'<p><strong>Type:</strong> {escape(str(test_type))}</p>')
                html_parts.append(f'<p><strong>Status:</strong> <span class="{status_class}">{escape(status)}</span></p>')
                html_parts.append(f'<p><strong>Execution Time:</strong> {escape(str(exec_time))}</p>')
                html_parts.append(f'<p><strong>Parameters:</strong> {escape(str(params))}</p>')
                # Notes may contain newlines, escape but preserve line breaks
                escaped_notes = escape(str(notes)).replace(chr(10), "<br>")
                html_parts.append(f'<p><strong>Notes:</strong> {escaped_notes}</p>')
                html_parts.append('</div>')
                
                # Calibration parameters for analog tests
                if test_type == 'Analog':
                    calibration = exec_data.get('calibration')
                    if calibration:
                        html_parts.append('<h3>Calibration Parameters</h3>')
                        html_parts.append('<table class="calibration-table">')
                        html_parts.append('<tr><th>Parameter</th><th>Value</th></tr>')
                        
                        gain = calibration.get('gain', 0)
                        offset = calibration.get('offset', 0)
                        r_squared = calibration.get('r_squared', 0)
                        mse = calibration.get('mse', 0)
                        max_error = calibration.get('max_error', 0)
                        mean_error = calibration.get('mean_error', 0)
                        data_points = calibration.get('data_points', 0)
                        
                        html_parts.append(f'<tr><td>Gain (Slope)</td><td>{gain:.6f} mV/mV</td></tr>')
                        html_parts.append(f'<tr><td>Offset</td><td>{offset:.4f}</td></tr>')
                        html_parts.append(f'<tr><td>R² (Linearity)</td><td>{r_squared:.6f}</td></tr>')
                        html_parts.append(f'<tr><td>Mean Error</td><td>{mean_error:.4f}</td></tr>')
                        html_parts.append(f'<tr><td>Max Error</td><td>{max_error:.4f}</td></tr>')
                        html_parts.append(f'<tr><td>MSE</td><td>{mse:.4f}</td></tr>')
                        html_parts.append(f'<tr><td>Data Points</td><td>{data_points}</td></tr>')
                        
                        gain_error_percent = calibration.get('gain_error_percent')
                        expected_gain = calibration.get('expected_gain')
                        if gain_error_percent is not None and expected_gain is not None:
                            html_parts.append(f'<tr><td>Expected Gain</td><td>{expected_gain:.6f}</td></tr>')
                            html_parts.append(f'<tr><td>Gain Error</td><td>{gain_error_percent:+.4f}%</td></tr>')
                            
                            tolerance_check = calibration.get('tolerance_check')
                            if tolerance_check:
                                check_class = 'status-pass' if tolerance_check == 'PASS' else 'status-fail'
                                html_parts.append(f'<tr><td>Tolerance Check</td><td class="{check_class}">{tolerance_check}</td></tr>')
                            
                            if abs(gain) > 1e-10:
                                adjustment_factor = expected_gain / gain
                                html_parts.append(f'<tr><td>Gain Adjustment Factor</td><td>{adjustment_factor:.6f}</td></tr>')
                        
                        html_parts.append('</table>')
                    
                    # Plot image
                    plot_data = exec_data.get('plot_data')
                    if plot_data:
                        dac_voltages = plot_data.get('dac_voltages', [])
                        feedback_values = plot_data.get('feedback_values', [])
                        
                        if dac_voltages and feedback_values:
                            plot_base64 = self._generate_test_plot_base64(test_name, dac_voltages, feedback_values)
                            if plot_base64:
                                html_parts.append('<h3>Plot</h3>')
                                html_parts.append(f'<img src="data:image/png;base64,{plot_base64}" alt="Plot for {test_name}" class="plot-image">')
                
                # Phase current calibration test results
                elif test_type == 'Phase Current Test' or (test_config and test_config.get('type') == 'Phase Current Test'):
                    plot_data = exec_data.get('plot_data')
                    if plot_data:
                        # Gain error and correction data
                        avg_gain_error_v = plot_data.get('avg_gain_error_v')
                        avg_gain_correction_v = plot_data.get('avg_gain_correction_v')
                        avg_gain_error_w = plot_data.get('avg_gain_error_w')
                        avg_gain_correction_w = plot_data.get('avg_gain_correction_w')
                        
                        if (avg_gain_error_v is not None or avg_gain_error_w is not None or
                            avg_gain_correction_v is not None or avg_gain_correction_w is not None):
                            html_parts.append('<h3>Gain Error and Correction Factor</h3>')
                            html_parts.append('<table class="calibration-table">')
                            html_parts.append('<tr><th>Parameter</th><th>Phase V</th><th>Phase W</th></tr>')
                            
                            if avg_gain_error_v is not None:
                                html_parts.append(f'<tr><td>Average Gain Error (%)</td><td>{avg_gain_error_v:+.4f}%</td><td>{avg_gain_error_w:+.4f}%</td></tr>')
                            if avg_gain_correction_v is not None:
                                html_parts.append(f'<tr><td>Average Gain Correction Factor</td><td>{avg_gain_correction_v:.6f}</td><td>{avg_gain_correction_w:.6f}</td></tr>')
                            
                            html_parts.append('</table>')
                        
                        # Plot image (CAN vs Oscilloscope)
                        osc_ch1 = plot_data.get('osc_ch1', [])
                        osc_ch2 = plot_data.get('osc_ch2', [])
                        can_v = plot_data.get('can_v', [])
                        can_w = plot_data.get('can_w', [])
                        
                        if (osc_ch1 or osc_ch2 or can_v or can_w):
                            plot_base64 = self._generate_phase_current_plot_base64(test_name, osc_ch1, can_v, osc_ch2, can_w)
                            if plot_base64:
                                html_parts.append('<h3>Plot: Average Phase Current (CAN vs Oscilloscope)</h3>')
                                html_parts.append(f'<img src="data:image/png;base64,{plot_base64}" alt="Phase Current Plot for {test_name}" class="plot-image">')
                
                # Output Current Calibration test results
                elif test_type == 'Output Current Calibration' or (test_config and test_config.get('type') == 'Output Current Calibration'):
                    plot_data = exec_data.get('plot_data')
                    if plot_data:
                        # Check for dual sweep data (new format) or single plot data (old format)
                        first_sweep_data = plot_data.get('first_sweep')
                        second_sweep_data = plot_data.get('second_sweep')
                        
                        if first_sweep_data and second_sweep_data:
                            # New format: Dual sweep results
                            html_parts.append('<h3>Calibration Results</h3>')
                            html_parts.append('<table class="calibration-table">')
                            html_parts.append('<tr><th>Parameter</th><th>Value</th></tr>')
                            
                            # First sweep results
                            first_slope = first_sweep_data.get('slope')
                            first_intercept = first_sweep_data.get('intercept')
                            first_gain_error = first_sweep_data.get('gain_error')
                            first_adjustment = first_sweep_data.get('adjustment_factor')
                            first_trim = first_sweep_data.get('trim_value')
                            
                            if first_trim is not None:
                                html_parts.append(f'<tr><td>First Sweep (Trim Value)</td><td>{first_trim}%</td></tr>')
                            if first_slope is not None:
                                html_parts.append(f'<tr><td>First Sweep Slope</td><td>{first_slope:.6f} (ideal: 1.0)</td></tr>')
                            if first_intercept is not None:
                                html_parts.append(f'<tr><td>First Sweep Intercept</td><td>{first_intercept:.6f} A</td></tr>')
                            if first_gain_error is not None:
                                html_parts.append(f'<tr><td>First Sweep Gain Error (%)</td><td>{first_gain_error:.4f}%</td></tr>')
                            if first_adjustment is not None:
                                html_parts.append(f'<tr><td>First Sweep Adjustment Factor</td><td>{first_adjustment:.6f}</td></tr>')
                            
                            # Calculated trim value
                            calculated_trim = plot_data.get('calculated_trim_value')
                            if calculated_trim is not None:
                                html_parts.append(f'<tr><td>Calculated Trim Value (%)</td><td>{calculated_trim:.4f}%</td></tr>')
                            
                            # Second sweep results
                            second_slope = second_sweep_data.get('slope')
                            second_intercept = second_sweep_data.get('intercept')
                            second_gain_error = second_sweep_data.get('gain_error')
                            second_trim = second_sweep_data.get('trim_value')
                            tolerance_percent = plot_data.get('tolerance_percent')
                            
                            if second_trim is not None:
                                html_parts.append(f'<tr><td>Second Sweep (Trim Value)</td><td>{second_trim:.4f}%</td></tr>')
                            if second_slope is not None:
                                html_parts.append(f'<tr><td>Second Sweep Slope</td><td>{second_slope:.6f} (ideal: 1.0)</td></tr>')
                            if second_intercept is not None:
                                html_parts.append(f'<tr><td>Second Sweep Intercept</td><td>{second_intercept:.6f} A</td></tr>')
                            if second_gain_error is not None:
                                html_parts.append(f'<tr><td>Second Sweep Gain Error (%)</td><td>{second_gain_error:.4f}%</td></tr>')
                            if tolerance_percent is not None:
                                html_parts.append(f'<tr><td>Tolerance (%)</td><td>{tolerance_percent:.4f}%</td></tr>')
                                if second_gain_error is not None:
                                    passed = abs(second_gain_error) <= tolerance_percent
                                    result_class = 'status-pass' if passed else 'status-fail'
                                    html_parts.append(f'<tr><td>Result</td><td class="{result_class}">{"PASS" if passed else "FAIL"}</td></tr>')
                            
                            html_parts.append('</table>')
                            
                            # First sweep plot
                            first_osc_averages = first_sweep_data.get('osc_averages', [])
                            first_can_averages = first_sweep_data.get('can_averages', [])
                            if first_osc_averages and first_can_averages:
                                first_plot_base64 = self._generate_output_current_calibration_plot_base64(
                                    test_name, first_osc_averages, first_can_averages, first_slope, first_intercept)
                                if first_plot_base64:
                                    first_plot_label = first_sweep_data.get('plot_label', 'First Sweep')
                                    html_parts.append(f'<h3>Plot: {first_plot_label}</h3>')
                                    html_parts.append(f'<img src="data:image/png;base64,{first_plot_base64}" alt="{first_plot_label} for {test_name}" class="plot-image">')
                            
                            # Second sweep plot
                            second_osc_averages = second_sweep_data.get('osc_averages', [])
                            second_can_averages = second_sweep_data.get('can_averages', [])
                            if second_osc_averages and second_can_averages:
                                second_plot_base64 = self._generate_output_current_calibration_plot_base64(
                                    test_name, second_osc_averages, second_can_averages, second_slope, second_intercept)
                                if second_plot_base64:
                                    second_plot_label = second_sweep_data.get('plot_label', 'Second Sweep')
                                    html_parts.append(f'<h3>Plot: {second_plot_label}</h3>')
                                    html_parts.append(f'<img src="data:image/png;base64,{second_plot_base64}" alt="{second_plot_label} for {test_name}" class="plot-image">')
                        else:
                            # Old format: Single plot (backward compatibility)
                            # Calibration results data
                            # Support both old format (gain_error) and new format (avg_gain_error)
                            slope = plot_data.get('slope')
                            intercept = plot_data.get('intercept')
                            gain_error = plot_data.get('gain_error') or plot_data.get('avg_gain_error')
                            adjustment_factor = plot_data.get('adjustment_factor')
                            tolerance_percent = plot_data.get('tolerance_percent')
                            
                            if (slope is not None or intercept is not None or gain_error is not None or 
                                adjustment_factor is not None or tolerance_percent is not None):
                                html_parts.append('<h3>Calibration Results</h3>')
                                html_parts.append('<table class="calibration-table">')
                                html_parts.append('<tr><th>Parameter</th><th>Value</th></tr>')
                                
                                if slope is not None:
                                    html_parts.append(f'<tr><td>Slope</td><td>{slope:.6f} (ideal: 1.0)</td></tr>')
                                if intercept is not None:
                                    html_parts.append(f'<tr><td>Intercept (A)</td><td>{intercept:.6f}</td></tr>')
                                if gain_error is not None:
                                    # Use appropriate label based on format
                                    if plot_data.get('avg_gain_error') is not None:
                                        html_parts.append(f'<tr><td>Average Gain Error (%)</td><td>{gain_error:.4f}%</td></tr>')
                                    else:
                                        html_parts.append(f'<tr><td>Gain Error (%)</td><td>{gain_error:+.4f}%</td></tr>')
                                if adjustment_factor is not None:
                                    html_parts.append(f'<tr><td>Adjustment Factor</td><td>{adjustment_factor:.6f}</td></tr>')
                                if tolerance_percent is not None:
                                    html_parts.append(f'<tr><td>Tolerance (%)</td><td>{tolerance_percent:.4f}%</td></tr>')
                                    if gain_error is not None:
                                        passed = abs(gain_error) <= tolerance_percent
                                        result_class = 'status-pass' if passed else 'status-fail'
                                        html_parts.append(f'<tr><td>Result</td><td class="{result_class}">{"PASS" if passed else "FAIL"}</td></tr>')
                                
                                html_parts.append('</table>')
                            
                            # Plot image (DUT vs Oscilloscope)
                            osc_averages = plot_data.get('osc_averages', [])
                            can_averages = plot_data.get('can_averages', [])
                            
                            if osc_averages and can_averages:
                                plot_base64 = self._generate_output_current_calibration_plot_base64(
                                    test_name, osc_averages, can_averages, slope, intercept)
                                if plot_base64:
                                    html_parts.append('<h3>Plot: Output Current Calibration (DUT vs Oscilloscope)</h3>')
                                    html_parts.append(f'<img src="data:image/png;base64,{plot_base64}" alt="Output Current Calibration Plot for {test_name}" class="plot-image">')
                
                html_parts.append('</div>')
            
            html_parts.append('</body>')
            html_parts.append('</html>')
            
            # Write HTML file
            with open(fname, 'w', encoding='utf-8') as f:
                f.write('\n'.join(html_parts))
            
            logger.info(f"Exported test report to HTML: {os.path.basename(fname)}")
            QtWidgets.QMessageBox.information(self, 'Export Successful', 
                f'Test report exported to:\n{os.path.basename(fname)}')
        except Exception as e:
            logger.error(f"Failed to export HTML report: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Export Error', 
                f'Failed to export HTML report:\n{e}')
    
    def _export_report_pdf(self):
        """Export test report as PDF file."""
        # Check for reportlab
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
            from reportlab.lib.units import inch
            reportlab_available = True
        except ImportError:
            reportlab_available = False
            logger.warning("reportlab not available, using matplotlib backend for PDF")
        
        try:
            default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', 'data', 'reports')
            os.makedirs(default_dir, exist_ok=True)
        except Exception:
            default_dir = os.path.expanduser('~')
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_filename = f'test_report_{timestamp}.pdf'
        
        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Export Test Report as PDF',
            os.path.join(default_dir, default_filename),
            'PDF Files (*.pdf);;All Files (*)'
        )
        
        if not fname:
            return
        
        try:
            if reportlab_available:
                # Use reportlab for professional PDF generation
                doc = SimpleDocTemplate(fname, pagesize=letter)
                story = []
                styles = getSampleStyleSheet()
                
                # Extract DUT UID from execution data using helper method
                dut_uid = self._get_dut_uid_from_execution_data()
                
                # Title
                title_style = ParagraphStyle(
                    'CustomTitle',
                    parent=styles['Heading1'],
                    fontSize=18,
                    textColor=colors.HexColor('#2c3e50'),
                    spaceAfter=30
                )
                story.append(Paragraph('Test Report', title_style))
                story.append(Paragraph(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))
                if dut_uid is not None:
                    story.append(Paragraph(f'<b>DUT UID:</b> {dut_uid}', styles['Normal']))
                story.append(Spacer(1, 0.2*inch))
                
                # Summary
                total_executed = 0
                pass_count = 0
                fail_count = 0
                error_count = 0
                total_time = 0.0
                
                for exec_data in self._test_execution_data.values():
                    status = exec_data.get('status', 'Not Run')
                    if status != 'Not Run':
                        total_executed += 1
                        if status == 'PASS':
                            pass_count += 1
                        elif status == 'FAIL':
                            fail_count += 1
                        elif status == 'ERROR':
                            error_count += 1
                        
                        exec_time_str = exec_data.get('exec_time', '0s')
                        try:
                            if exec_time_str.endswith('s'):
                                total_time += float(exec_time_str[:-1])
                        except Exception:
                            pass
                
                pass_rate = (pass_count / total_executed * 100) if total_executed > 0 else 0
                
                summary_data = [
                    ['Metric', 'Value']
                ]
                if dut_uid is not None:
                    summary_data.append(['DUT UID', str(dut_uid)])
                summary_data.extend([
                    ['Total Tests Executed', str(total_executed)],
                    ['Passed', str(pass_count)],
                    ['Failed', str(fail_count)],
                    ['Errors', str(error_count)],
                    ['Pass Rate', f'{pass_rate:.1f}%'],
                    ['Total Execution Time', f'{total_time:.2f}s']
                ])
                
                summary_table = Table(summary_data)
                summary_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                
                story.append(Paragraph('<b>Summary</b>', styles['Heading2']))
                story.append(summary_table)
                story.append(Spacer(1, 0.3*inch))
                
                # Test results
                for test_name, exec_data in self._test_execution_data.items():
                    status = exec_data.get('status', 'Not Run')
                    test_type = exec_data.get('test_type', 'Unknown')
                    exec_time = exec_data.get('exec_time', 'N/A')
                    params = exec_data.get('parameters', 'N/A')
                    notes = exec_data.get('notes', 'N/A')
                    
                    # Find test config
                    test_config = None
                    for test in self._tests:
                        if test.get('name', '') == test_name:
                            test_config = test
                            break
                    
                    story.append(Paragraph(f'<b>{test_name}</b>', styles['Heading2']))
                    story.append(Spacer(1, 0.1*inch))
                    
                    test_details = [
                        ['Field', 'Value'],
                        ['Type', test_type],
                        ['Status', status],
                        ['Execution Time', exec_time],
                        ['Parameters', params],
                        ['Notes', notes.replace('\n', ' ')]
                    ]
                    
                    test_table = Table(test_details)
                    test_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ]))
                    
                    story.append(test_table)
                    
                    # Calibration for analog tests
                    if test_type == 'Analog':
                        calibration = exec_data.get('calibration')
                        if calibration:
                            story.append(Spacer(1, 0.1*inch))
                            story.append(Paragraph('<b>Calibration Parameters</b>', styles['Heading3']))
                            
                            calib_data = [['Parameter', 'Value']]
                            
                            gain = calibration.get('gain', 0)
                            offset = calibration.get('offset', 0)
                            r_squared = calibration.get('r_squared', 0)
                            mse = calibration.get('mse', 0)
                            max_error = calibration.get('max_error', 0)
                            mean_error = calibration.get('mean_error', 0)
                            data_points = calibration.get('data_points', 0)
                            
                            calib_data.append(['Gain (Slope)', f'{gain:.6f} mV/mV'])
                            calib_data.append(['Offset', f'{offset:.4f}'])
                            calib_data.append(['R² (Linearity)', f'{r_squared:.6f}'])
                            calib_data.append(['Mean Error', f'{mean_error:.4f}'])
                            calib_data.append(['Max Error', f'{max_error:.4f}'])
                            calib_data.append(['MSE', f'{mse:.4f}'])
                            calib_data.append(['Data Points', str(data_points)])
                            
                            gain_error_percent = calibration.get('gain_error_percent')
                            expected_gain = calibration.get('expected_gain')
                            if gain_error_percent is not None and expected_gain is not None:
                                calib_data.append(['Expected Gain', f'{expected_gain:.6f}'])
                                calib_data.append(['Gain Error', f'{gain_error_percent:+.4f}%'])
                                
                                tolerance_check = calibration.get('tolerance_check')
                                if tolerance_check:
                                    calib_data.append(['Tolerance Check', tolerance_check])
                                
                                if abs(gain) > 1e-10:
                                    adjustment_factor = expected_gain / gain
                                    calib_data.append(['Gain Adjustment Factor', f'{adjustment_factor:.6f}'])
                            
                            calib_table = Table(calib_data)
                            calib_table.setStyle(TableStyle([
                                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('FONTSIZE', (0, 0), (-1, 0), 10),
                                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                            ]))
                            
                            story.append(calib_table)
                        
                        # Plot image
                        plot_data = exec_data.get('plot_data')
                        if plot_data:
                            dac_voltages = plot_data.get('dac_voltages', [])
                            feedback_values = plot_data.get('feedback_values', [])
                            
                            if dac_voltages and feedback_values:
                                # Save plot to temporary file
                                import tempfile
                                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                                    tmp_path = tmp_file.name
                                
                                plot_bytes = self._generate_test_plot_image(test_name, dac_voltages, feedback_values, 'png')
                                if plot_bytes:
                                    with open(tmp_path, 'wb') as f:
                                        f.write(plot_bytes)
                                    
                                    story.append(Spacer(1, 0.1*inch))
                                    story.append(Paragraph('<b>Plot</b>', styles['Heading3']))
                                    img = Image(tmp_path, width=5*inch, height=3*inch)
                                    story.append(img)
                                    
                                    # Clean up temp file
                                    try:
                                        os.unlink(tmp_path)
                                    except Exception:
                                        pass
                    
                    # Phase current calibration test results
                    elif test_type == 'Phase Current Test' or (test_config and test_config.get('type') == 'Phase Current Test'):
                        plot_data = exec_data.get('plot_data')
                        if plot_data:
                            # Gain error and correction data
                            avg_gain_error_v = plot_data.get('avg_gain_error_v')
                            avg_gain_correction_v = plot_data.get('avg_gain_correction_v')
                            avg_gain_error_w = plot_data.get('avg_gain_error_w')
                            avg_gain_correction_w = plot_data.get('avg_gain_correction_w')
                            
                            if (avg_gain_error_v is not None or avg_gain_error_w is not None or
                                avg_gain_correction_v is not None or avg_gain_correction_w is not None):
                                story.append(Spacer(1, 0.1*inch))
                                story.append(Paragraph('<b>Gain Error and Correction Factor</b>', styles['Heading3']))
                                
                                gain_data = [['Parameter', 'Phase V', 'Phase W']]
                                if avg_gain_error_v is not None:
                                    gain_data.append(['Average Gain Error (%)', f'{avg_gain_error_v:+.4f}%', f'{avg_gain_error_w:+.4f}%'])
                                if avg_gain_correction_v is not None:
                                    gain_data.append(['Average Gain Correction Factor', f'{avg_gain_correction_v:.6f}', f'{avg_gain_correction_w:.6f}'])
                                
                                gain_table = Table(gain_data)
                                gain_table.setStyle(TableStyle([
                                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
                                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                                ]))
                                
                                story.append(gain_table)
                            
                            # Plot image (CAN vs Oscilloscope)
                            osc_ch1 = plot_data.get('osc_ch1', [])
                            osc_ch2 = plot_data.get('osc_ch2', [])
                            can_v = plot_data.get('can_v', [])
                            can_w = plot_data.get('can_w', [])
                            
                            if (osc_ch1 or osc_ch2 or can_v or can_w):
                                import tempfile
                                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                                    tmp_path = tmp_file.name
                                
                                plot_bytes = self._generate_phase_current_plot_image(test_name, osc_ch1, can_v, osc_ch2, can_w, 'png')
                                if plot_bytes:
                                    with open(tmp_path, 'wb') as f:
                                        f.write(plot_bytes)
                                    
                                    story.append(Spacer(1, 0.1*inch))
                                    story.append(Paragraph('<b>Plot: Average Phase Current (CAN vs Oscilloscope)</b>', styles['Heading3']))
                                    img = Image(tmp_path, width=6*inch, height=2.5*inch)
                                    story.append(img)
                                    
                                    # Clean up temp file
                                    try:
                                        os.unlink(tmp_path)
                                    except Exception:
                                        pass
                    
                    story.append(PageBreak())
                
                # Build PDF
                doc.build(story)
                
            else:
                # Fallback: Use matplotlib backend for simple PDF
                if matplotlib_available:
                    from matplotlib.backends.backend_pdf import PdfPages
                    
                    with PdfPages(fname) as pdf:
                        # Title page
                        fig = Figure(figsize=(8.5, 11))
                        ax = fig.add_subplot(111)
                        ax.axis('off')
                        ax.text(0.5, 0.7, 'Test Report', ha='center', va='center', fontsize=24, fontweight='bold')
                        ax.text(0.5, 0.6, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 
                                ha='center', va='center', fontsize=12)
                        pdf.savefig(fig, bbox_inches='tight')
                        
                        # Summary page
                        total_executed = 0
                        pass_count = 0
                        fail_count = 0
                        error_count = 0
                        
                        for exec_data in self._test_execution_data.values():
                            status = exec_data.get('status', 'Not Run')
                            if status != 'Not Run':
                                total_executed += 1
                                if status == 'PASS':
                                    pass_count += 1
                                elif status == 'FAIL':
                                    fail_count += 1
                                elif status == 'ERROR':
                                    error_count += 1
                        
                        fig = Figure(figsize=(8.5, 11))
                        ax = fig.add_subplot(111)
                        ax.axis('off')
                        y_pos = 0.9
                        ax.text(0.1, y_pos, 'Summary', fontsize=18, fontweight='bold')
                        y_pos -= 0.1
                        ax.text(0.1, y_pos, f'Total Tests Executed: {total_executed}', fontsize=12)
                        y_pos -= 0.08
                        ax.text(0.1, y_pos, f'Passed: {pass_count}', fontsize=12, color='green')
                        y_pos -= 0.08
                        ax.text(0.1, y_pos, f'Failed: {fail_count}', fontsize=12, color='red')
                        y_pos -= 0.08
                        ax.text(0.1, y_pos, f'Errors: {error_count}', fontsize=12, color='red')
                        pdf.savefig(fig, bbox_inches='tight')
                        
                        # Test results with plots
                        for test_name, exec_data in self._test_execution_data.items():
                            test_type = exec_data.get('test_type', 'Unknown')
                            plot_data = exec_data.get('plot_data')
                            
                            if plot_data and test_type == 'Analog':
                                dac_voltages = plot_data.get('dac_voltages', [])
                                feedback_values = plot_data.get('feedback_values', [])
                                
                                if dac_voltages and feedback_values:
                                    fig = Figure(figsize=(8.5, 11))
                                    ax = fig.add_subplot(111)
                                    ax.plot(dac_voltages, feedback_values, 'bo-', markersize=4, linewidth=1)
                                    ax.set_xlabel('DAC Output Voltage (mV)')
                                    ax.set_ylabel('Feedback Signal Value')
                                    ax.set_title(f'{test_name}')
                                    ax.grid(True, alpha=0.3)
                                    pdf.savefig(fig, bbox_inches='tight')
                else:
                    raise RuntimeError("Neither reportlab nor matplotlib available for PDF export")
            
            logger.info(f"Exported test report to PDF: {os.path.basename(fname)}")
            QtWidgets.QMessageBox.information(self, 'Export Successful', 
                f'Test report exported to:\n{os.path.basename(fname)}')
        except Exception as e:
            logger.error(f"Failed to export PDF report: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Export Error', 
                f'Failed to export PDF report:\n{e}')
    
    def _build_toolbar(self):
        # Toolbar kept minimal; adapter selection is on Welcome page
        tb = self.addToolBar('Main')
        self.status_label = QtWidgets.QLabel('Status: Idle')
        tb.addWidget(self.status_label)

    def _build_central(self):
        # Central layout: just main tabs (no left panel - moved to dialog)
        central = QtWidgets.QWidget()
        main_h = QtWidgets.QHBoxLayout(central)
        main_h.setContentsMargins(0, 0, 0, 0)

        # Main tab widget (full width now)
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
        # Signal values accessed via signal_service (legacy _signal_values removed)
        # currently monitored feedback signal during test run: (msg_id, signal_name) or None
        self._current_feedback = None
        inner.addTab(self.send_widget, 'Send Data')
        inner.addTab(self.settings_widget, 'Settings')

        can_layout.addWidget(inner)
        main_tabs.addTab(can_tab, 'CAN Data View')

        # assemble central layout (no left panel)
        main_h.addWidget(main_tabs, 1)
        self.setCentralWidget(central)

        # keep references for switching and controls
        self.tabs_main = main_tabs
        # Note: _refresh_can_devices() will be called when dialog opens
        # Store reference to connect_btn for start_btn (will be set when dialog is created)
        self.start_btn = None

        # build EOL H/W Configuration tab and wire into main_tabs
        try:
            eol_tab = self._build_eol_hw_configurator()
            # add as a top-level tab before Test Configurator
            self.tabs_main.addTab(eol_tab, 'EOL H/W Configuration')
        except Exception as e:
            logger.error(f"Failed to build EOL H/W Configuration tab: {e}", exc_info=True)
        
        # build Oscilloscope Configuration tab and wire into main_tabs
        try:
            osc_config_tab = self._build_oscilloscope_configurator()
            # add as a top-level tab after EOL H/W Configuration
            self.tabs_main.addTab(osc_config_tab, 'Oscilloscope Configuration')
        except Exception as e:
            logger.error(f"Failed to build Oscilloscope Configuration tab: {e}", exc_info=True)
        
        # build Test Configurator tab and wire into main_tabs
        try:
            test_tab = self._build_test_configurator()
            # add as a top-level tab after EOL H/W Configuration
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
        # Check if widget exists (dialog may not be created yet)
        if not hasattr(self, 'device_combo') or self.device_combo is None:
            return
        
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
        if self.can_service is not None and self.can_service.is_connected():
            self.toggle_adapter()
            return
        # otherwise start using selected device
        self.toggle_adapter()

    def _refresh_oscilloscopes(self) -> None:
        """Refresh the list of available oscilloscopes."""
        if self.oscilloscope_service is None:
            # Only show warning if dialog is open (widget exists)
            if hasattr(self, 'oscilloscope_combo') and self.oscilloscope_combo is not None:
                QtWidgets.QMessageBox.warning(self, 'Oscilloscope', 
                    'Oscilloscope service not available. Please install PyVISA.')
            return
        
        # Check if widget exists (dialog may not be created yet)
        if not hasattr(self, 'oscilloscope_combo') or self.oscilloscope_combo is None:
            return
        
        try:
            # Clear and repopulate dropdown
            self.oscilloscope_combo.clear()
            
            # Scan for devices
            devices = self.oscilloscope_service.scan_for_devices()
            
            if not devices:
                self.oscilloscope_combo.addItem('No devices found')
                self.oscilloscope_combo.setEnabled(False)
                logger.info("No oscilloscopes found (USB or LAN)")
            else:
                for device in devices:
                    # Try to get device info for display
                    try:
                        temp_resource = self.oscilloscope_service.resource_manager.open_resource(device)
                        try:
                            idn = temp_resource.query('*IDN?')
                            # Format: "Manufacturer,Model,Serial,Version"
                            parts = idn.split(',')
                            if len(parts) >= 2:
                                display_name = f"{parts[0].strip()} {parts[1].strip()}"
                            else:
                                display_name = idn.strip()
                            self.oscilloscope_combo.addItem(f"{display_name} ({device})", device)
                        except Exception:
                            self.oscilloscope_combo.addItem(device, device)
                        finally:
                            temp_resource.close()
                    except Exception:
                        self.oscilloscope_combo.addItem(device, device)
                
                self.oscilloscope_combo.setEnabled(True)
                logger.info(f"Found {len(devices)} oscilloscope(s)")
        except Exception as e:
            logger.error(f"Error refreshing oscilloscopes: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', 
                f'Failed to scan for oscilloscopes:\n{e}')
    
    def _toggle_oscilloscope_connection(self) -> None:
        """Toggle oscilloscope connection/disconnection."""
        if self.oscilloscope_service is None:
            QtWidgets.QMessageBox.warning(self, 'Oscilloscope', 
                'Oscilloscope service not available.')
            return
        
        if self.oscilloscope_service.is_connected():
            # Disconnect
            self.oscilloscope_service.disconnect()
            self.osc_connect_btn.setText('Connect')
            self.osc_status_label.setText('Status: Disconnected')
            self.osc_status_label.setStyleSheet('color: gray;')
            self.oscilloscope_combo.setEnabled(True)
            self.osc_refresh_btn.setEnabled(True)
            logger.info("Oscilloscope disconnected")
        else:
            # Connect
            current_index = self.oscilloscope_combo.currentIndex()
            if current_index < 0:
                QtWidgets.QMessageBox.warning(self, 'Oscilloscope', 
                    'Please select an oscilloscope first.')
                return
            
            # Get resource string from combo box
            resource = self.oscilloscope_combo.itemData(current_index)
            if resource is None:
                # Fallback to display text if no data
                resource = self.oscilloscope_combo.currentText()
                # Extract resource string if it's in parentheses
                if '(' in resource and ')' in resource:
                    resource = resource.split('(')[1].rstrip(')')
            
            if not resource or resource == 'No devices found':
                QtWidgets.QMessageBox.warning(self, 'Oscilloscope', 
                    'No oscilloscope selected or available.')
                return
            
            # Connect
            if self.oscilloscope_service.connect(resource):
                self.osc_connect_btn.setText('Disconnect')
                device_info = self.oscilloscope_service.get_device_info()
                if device_info:
                    # Extract manufacturer and model for display
                    parts = device_info.split(',')
                    if len(parts) >= 2:
                        short_info = f"{parts[0].strip()} {parts[1].strip()}"
                    else:
                        short_info = device_info.strip()
                    self.osc_status_label.setText(f'Status: Connected\n{short_info}')
                else:
                    self.osc_status_label.setText('Status: Connected')
                self.osc_status_label.setStyleSheet('color: green;')
                self.oscilloscope_combo.setEnabled(False)
                self.osc_refresh_btn.setEnabled(False)
                logger.info(f"Oscilloscope connected: {resource}")
            else:
                QtWidgets.QMessageBox.critical(self, 'Connection Error', 
                    f'Failed to connect to oscilloscope:\n{resource}')

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
        
        # Legacy implementation removed - DbcService should always be available
        # If we reach here, DbcService was not available - this should not happen
        logger.warning("_find_message_by_id: DbcService not available")
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

    # EOL H/W Configuration handlers
    def _on_create_eol_config(self):
        """Open dialog to create new EOL hardware configuration."""
        if not self._check_dbc_loaded():
            return
        
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle('Create EOL Hardware Configuration')
        dialog.setMinimumWidth(600)
        layout = QtWidgets.QVBoxLayout(dialog)
        
        # Configuration name
        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(QtWidgets.QLabel('Configuration Name:'))
        name_edit = QtWidgets.QLineEdit()
        name_edit.setPlaceholderText('e.g., EOL_HW_v1.0')
        name_layout.addWidget(name_edit)
        layout.addLayout(name_layout)
        
        # Message selection
        msg_label = QtWidgets.QLabel('<b>EOL Feedback Message:</b>')
        layout.addWidget(msg_label)
        msg_combo = QtWidgets.QComboBox()
        
        # Populate with messages from loaded DBC
        messages = []
        if self.dbc_service and self.dbc_service.is_loaded():
            messages = self.dbc_service.get_all_messages()
        else:
            # Try to get from database if service has it
            if self.dbc_service and hasattr(self.dbc_service, 'database') and self.dbc_service.database:
                try:
                    messages = getattr(self.dbc_service.database, 'messages', [])
                except Exception:
                    pass
        
        if not messages:
            QtWidgets.QMessageBox.warning(self, 'No DBC Loaded', 
                'Please load a DBC file first in the CAN Data View tab.')
            dialog.reject()
            return
        
        msg_combo.addItem('-- Select Message --', None)
        for msg in messages:
            msg_name = getattr(msg, 'name', 'Unknown')
            msg_id = getattr(msg, 'frame_id', 0)
            msg_length = getattr(msg, 'length', 0)
            msg_combo.addItem(f"{msg_name} (ID: 0x{msg_id:X}, Length: {msg_length})", msg)
        
        layout.addWidget(msg_combo)
        
        # Signal selection (updates when message changes)
        sig_label = QtWidgets.QLabel('<b>Measured DAC Output Voltage Signal:</b>')
        layout.addWidget(sig_label)
        sig_combo = QtWidgets.QComboBox()
        sig_combo.setEnabled(False)
        layout.addWidget(sig_combo)
        
        # Signal details display
        sig_details = QtWidgets.QLabel('')
        sig_details.setWordWrap(True)
        sig_details.setStyleSheet('color: gray; font-size: 10px;')
        layout.addWidget(sig_details)
        
        # Separator
        separator1 = QtWidgets.QFrame()
        separator1.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator1.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        layout.addWidget(separator1)
        
        # EOL Command Message ID
        eol_cmd_msg_label = QtWidgets.QLabel('<b>EOL Command Message ID:</b>')
        layout.addWidget(eol_cmd_msg_label)
        eol_cmd_msg_combo = QtWidgets.QComboBox()
        eol_cmd_msg_combo.addItem('-- Select Message --', None)
        for msg in messages:
            msg_name = getattr(msg, 'name', 'Unknown')
            msg_id = getattr(msg, 'frame_id', 0)
            msg_length = getattr(msg, 'length', 0)
            eol_cmd_msg_combo.addItem(f"{msg_name} (ID: 0x{msg_id:X}, Length: {msg_length})", msg)
        layout.addWidget(eol_cmd_msg_combo)
        
        # Set DUT Test Mode Signal (updates when EOL Command Message changes)
        dut_test_mode_sig_label = QtWidgets.QLabel('<b>Set DUT Test Mode Signal:</b>')
        layout.addWidget(dut_test_mode_sig_label)
        dut_test_mode_sig_combo = QtWidgets.QComboBox()
        dut_test_mode_sig_combo.setEnabled(False)
        layout.addWidget(dut_test_mode_sig_combo)
        
        # DUT Feedback Message ID
        dut_fb_msg_label = QtWidgets.QLabel('<b>DUT Feedback Message ID:</b>')
        layout.addWidget(dut_fb_msg_label)
        dut_fb_msg_combo = QtWidgets.QComboBox()
        dut_fb_msg_combo.addItem('-- Select Message --', None)
        for msg in messages:
            msg_name = getattr(msg, 'name', 'Unknown')
            msg_id = getattr(msg, 'frame_id', 0)
            msg_length = getattr(msg, 'length', 0)
            dut_fb_msg_combo.addItem(f"{msg_name} (ID: 0x{msg_id:X}, Length: {msg_length})", msg)
        layout.addWidget(dut_fb_msg_combo)
        
        # DUT Test Status Signal (updates when DUT Feedback Message changes)
        dut_test_status_sig_label = QtWidgets.QLabel('<b>DUT Test Status Signal:</b>')
        layout.addWidget(dut_test_status_sig_label)
        dut_test_status_sig_combo = QtWidgets.QComboBox()
        dut_test_status_sig_combo.setEnabled(False)
        layout.addWidget(dut_test_status_sig_combo)
        
        def on_message_changed(index):
            """Update signal combo when message selection changes."""
            sig_combo.clear()
            sig_details.setText('')
            msg = msg_combo.currentData()
            if msg is None or index == 0:
                sig_combo.setEnabled(False)
                return
            
            sig_combo.setEnabled(True)
            signals = []
            if self.dbc_service and self.dbc_service.is_loaded():
                signals = self.dbc_service.get_message_signals(msg)
            else:
                signals = getattr(msg, 'signals', [])
            
            sig_combo.addItem('-- Select Signal --', None)
            for sig in signals:
                sig_name = getattr(sig, 'name', '')
                sig_units = getattr(sig, 'unit', '')
                sig_scale = getattr(sig, 'scale', 1.0)
                sig_offset = getattr(sig, 'offset', 0.0)
                display_text = sig_name
                if sig_units:
                    display_text += f" ({sig_units})"
                sig_combo.addItem(display_text, sig)
        
        def on_eol_cmd_message_changed(index):
            """Update DUT Test Mode Signal combo when EOL Command Message changes."""
            dut_test_mode_sig_combo.clear()
            msg = eol_cmd_msg_combo.currentData()
            if msg is None or index == 0:
                dut_test_mode_sig_combo.setEnabled(False)
                return
            
            dut_test_mode_sig_combo.setEnabled(True)
            signals = []
            if self.dbc_service and self.dbc_service.is_loaded():
                signals = self.dbc_service.get_message_signals(msg)
            else:
                signals = getattr(msg, 'signals', [])
            
            dut_test_mode_sig_combo.addItem('-- Select Signal --', None)
            for sig in signals:
                sig_name = getattr(sig, 'name', '')
                sig_units = getattr(sig, 'unit', '')
                display_text = sig_name
                if sig_units:
                    display_text += f" ({sig_units})"
                dut_test_mode_sig_combo.addItem(display_text, sig)
        
        def on_dut_fb_message_changed(index):
            """Update DUT Test Status Signal combo when DUT Feedback Message changes."""
            dut_test_status_sig_combo.clear()
            msg = dut_fb_msg_combo.currentData()
            if msg is None or index == 0:
                dut_test_status_sig_combo.setEnabled(False)
                return
            
            dut_test_status_sig_combo.setEnabled(True)
            signals = []
            if self.dbc_service and self.dbc_service.is_loaded():
                signals = self.dbc_service.get_message_signals(msg)
            else:
                signals = getattr(msg, 'signals', [])
            
            dut_test_status_sig_combo.addItem('-- Select Signal --', None)
            for sig in signals:
                sig_name = getattr(sig, 'name', '')
                sig_units = getattr(sig, 'unit', '')
                display_text = sig_name
                if sig_units:
                    display_text += f" ({sig_units})"
                dut_test_status_sig_combo.addItem(display_text, sig)
        
        msg_combo.currentIndexChanged.connect(on_message_changed)
        eol_cmd_msg_combo.currentIndexChanged.connect(on_eol_cmd_message_changed)
        dut_fb_msg_combo.currentIndexChanged.connect(on_dut_fb_message_changed)
        
        def on_signal_changed(index):
            """Update signal details when signal selection changes."""
            sig = sig_combo.currentData()
            if sig is None or index == 0:
                sig_details.setText('')
                return
            
            sig_name = getattr(sig, 'name', '')
            sig_units = getattr(sig, 'unit', '')
            sig_scale = getattr(sig, 'scale', 1.0)
            sig_offset = getattr(sig, 'offset', 0.0)
            sig_min = getattr(sig, 'minimum', None)
            sig_max = getattr(sig, 'maximum', None)
            
            details = f"Signal: {sig_name}"
            if sig_units:
                details += f", Units: {sig_units}"
            details += f", Scale: {sig_scale}, Offset: {sig_offset}"
            if sig_min is not None or sig_max is not None:
                details += f", Range: [{sig_min}, {sig_max}]"
            sig_details.setText(details)
        
        sig_combo.currentIndexChanged.connect(on_signal_changed)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton('Save')
        cancel_btn = QtWidgets.QPushButton('Cancel')
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        def on_save():
            config_name = name_edit.text().strip()
            if not config_name:
                QtWidgets.QMessageBox.warning(dialog, 'Invalid Name', 
                    'Please enter a configuration name.')
                return
            
            msg = msg_combo.currentData()
            sig = sig_combo.currentData()
            if not msg or not sig:
                QtWidgets.QMessageBox.warning(dialog, 'Invalid Configuration', 
                    'Please select both EOL Feedback Message and Measured DAC Output Voltage Signal.')
                return
            
            # Get new field values (optional)
            eol_cmd_msg = eol_cmd_msg_combo.currentData()
            dut_test_mode_sig = dut_test_mode_sig_combo.currentData()
            dut_fb_msg = dut_fb_msg_combo.currentData()
            dut_test_status_sig = dut_test_status_sig_combo.currentData()
            
            # Save configuration
            self._eol_hw_config = {
                'name': config_name,
                'feedback_message_id': getattr(msg, 'frame_id', 0),
                'feedback_message_name': getattr(msg, 'name', ''),
                'measured_dac_signal': getattr(sig, 'name', ''),
                'eol_command_message_id': getattr(eol_cmd_msg, 'frame_id', None) if eol_cmd_msg else None,
                'eol_command_message_name': getattr(eol_cmd_msg, 'name', None) if eol_cmd_msg else None,
                'set_dut_test_mode_signal': getattr(dut_test_mode_sig, 'name', None) if dut_test_mode_sig else None,
                'dut_feedback_message_id': getattr(dut_fb_msg, 'frame_id', None) if dut_fb_msg else None,
                'dut_feedback_message_name': getattr(dut_fb_msg, 'name', None) if dut_fb_msg else None,
                'dut_test_status_signal': getattr(dut_test_status_sig, 'name', None) if dut_test_status_sig else None,
                'created_at': datetime.utcnow().isoformat() + 'Z',
                'updated_at': datetime.utcnow().isoformat() + 'Z'
            }
            
            # Update display labels
            self._update_eol_config_display()
            
            logger.info(f"Created EOL HW configuration: {config_name}")
            QtWidgets.QMessageBox.information(dialog, 'Success', 
                f'EOL Hardware Configuration "{config_name}" created successfully.')
            dialog.accept()
        
        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec()
    
    def _on_edit_eol_config(self):
        """Open dialog to edit current EOL hardware configuration."""
        if not self._check_dbc_loaded():
            return
        
        if not self._eol_hw_config.get('feedback_message_id'):
            QtWidgets.QMessageBox.information(self, 'No Configuration', 
                'No EOL configuration loaded. Please create or load a configuration first.')
            return
        
        # Open same dialog as create, but pre-filled
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle('Edit EOL Hardware Configuration')
        dialog.setMinimumWidth(600)
        layout = QtWidgets.QVBoxLayout(dialog)
        
        # Configuration name
        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(QtWidgets.QLabel('Configuration Name:'))
        name_edit = QtWidgets.QLineEdit()
        name_edit.setText(self._eol_hw_config.get('name', ''))
        name_edit.setPlaceholderText('e.g., EOL_HW_v1.0')
        name_layout.addWidget(name_edit)
        layout.addLayout(name_layout)
        
        # Message selection
        msg_label = QtWidgets.QLabel('<b>EOL Feedback Message:</b>')
        layout.addWidget(msg_label)
        msg_combo = QtWidgets.QComboBox()
        
        messages = []
        if self.dbc_service and self.dbc_service.is_loaded():
            messages = self.dbc_service.get_all_messages()
        else:
            # Try to get from database if service has it
            if self.dbc_service and hasattr(self.dbc_service, 'database') and self.dbc_service.database:
                try:
                    messages = getattr(self.dbc_service.database, 'messages', [])
                except Exception:
                    pass
        
        if not messages:
            QtWidgets.QMessageBox.warning(self, 'No DBC Loaded', 
                'Please load a DBC file first in the CAN Data View tab.')
            dialog.reject()
            return
        
        msg_combo.addItem('-- Select Message --', None)
        current_msg_id = self._eol_hw_config.get('feedback_message_id')
        current_msg_index = 0
        for idx, msg in enumerate(messages, start=1):
            msg_name = getattr(msg, 'name', 'Unknown')
            msg_id = getattr(msg, 'frame_id', 0)
            msg_length = getattr(msg, 'length', 0)
            msg_combo.addItem(f"{msg_name} (ID: 0x{msg_id:X}, Length: {msg_length})", msg)
            if msg_id == current_msg_id:
                current_msg_index = idx
        
        layout.addWidget(msg_combo)
        
        # Signal selection
        sig_label = QtWidgets.QLabel('<b>Measured DAC Output Voltage Signal:</b>')
        layout.addWidget(sig_label)
        sig_combo = QtWidgets.QComboBox()
        sig_combo.setEnabled(False)
        layout.addWidget(sig_combo)
        
        sig_details = QtWidgets.QLabel('')
        sig_details.setWordWrap(True)
        sig_details.setStyleSheet('color: gray; font-size: 10px;')
        layout.addWidget(sig_details)
        
        # Separator
        separator1 = QtWidgets.QFrame()
        separator1.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator1.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        layout.addWidget(separator1)
        
        # EOL Command Message ID
        eol_cmd_msg_label = QtWidgets.QLabel('<b>EOL Command Message ID:</b>')
        layout.addWidget(eol_cmd_msg_label)
        eol_cmd_msg_combo = QtWidgets.QComboBox()
        eol_cmd_msg_combo.addItem('-- Select Message --', None)
        current_eol_cmd_msg_id = self._eol_hw_config.get('eol_command_message_id')
        current_eol_cmd_msg_index = 0
        for idx, msg in enumerate(messages, start=1):
            msg_name = getattr(msg, 'name', 'Unknown')
            msg_id = getattr(msg, 'frame_id', 0)
            msg_length = getattr(msg, 'length', 0)
            eol_cmd_msg_combo.addItem(f"{msg_name} (ID: 0x{msg_id:X}, Length: {msg_length})", msg)
            if current_eol_cmd_msg_id and msg_id == current_eol_cmd_msg_id:
                current_eol_cmd_msg_index = idx
        layout.addWidget(eol_cmd_msg_combo)
        
        # Set DUT Test Mode Signal (updates when EOL Command Message changes)
        dut_test_mode_sig_label = QtWidgets.QLabel('<b>Set DUT Test Mode Signal:</b>')
        layout.addWidget(dut_test_mode_sig_label)
        dut_test_mode_sig_combo = QtWidgets.QComboBox()
        dut_test_mode_sig_combo.setEnabled(False)
        layout.addWidget(dut_test_mode_sig_combo)
        
        # DUT Feedback Message ID
        dut_fb_msg_label = QtWidgets.QLabel('<b>DUT Feedback Message ID:</b>')
        layout.addWidget(dut_fb_msg_label)
        dut_fb_msg_combo = QtWidgets.QComboBox()
        dut_fb_msg_combo.addItem('-- Select Message --', None)
        current_dut_fb_msg_id = self._eol_hw_config.get('dut_feedback_message_id')
        current_dut_fb_msg_index = 0
        for idx, msg in enumerate(messages, start=1):
            msg_name = getattr(msg, 'name', 'Unknown')
            msg_id = getattr(msg, 'frame_id', 0)
            msg_length = getattr(msg, 'length', 0)
            dut_fb_msg_combo.addItem(f"{msg_name} (ID: 0x{msg_id:X}, Length: {msg_length})", msg)
            if current_dut_fb_msg_id and msg_id == current_dut_fb_msg_id:
                current_dut_fb_msg_index = idx
        layout.addWidget(dut_fb_msg_combo)
        
        # DUT Test Status Signal (updates when DUT Feedback Message changes)
        dut_test_status_sig_label = QtWidgets.QLabel('<b>DUT Test Status Signal:</b>')
        layout.addWidget(dut_test_status_sig_label)
        dut_test_status_sig_combo = QtWidgets.QComboBox()
        dut_test_status_sig_combo.setEnabled(False)
        layout.addWidget(dut_test_status_sig_combo)
        
        def on_message_changed(index):
            sig_combo.clear()
            sig_details.setText('')
            msg = msg_combo.currentData()
            if msg is None or index == 0:
                sig_combo.setEnabled(False)
                return
            
            sig_combo.setEnabled(True)
            signals = []
            if self.dbc_service and self.dbc_service.is_loaded():
                signals = self.dbc_service.get_message_signals(msg)
            else:
                signals = getattr(msg, 'signals', [])
            
            sig_combo.addItem('-- Select Signal --', None)
            current_sig_name = self._eol_hw_config.get('measured_dac_signal')
            current_sig_index = 0
            for idx, sig in enumerate(signals, start=1):
                sig_name = getattr(sig, 'name', '')
                sig_units = getattr(sig, 'unit', '')
                display_text = sig_name
                if sig_units:
                    display_text += f" ({sig_units})"
                sig_combo.addItem(display_text, sig)
                if sig_name == current_sig_name:
                    current_sig_index = idx
            
            if current_sig_index > 0:
                sig_combo.setCurrentIndex(current_sig_index)
                on_signal_changed(current_sig_index)
        
        def on_eol_cmd_message_changed(index):
            """Update DUT Test Mode Signal combo when EOL Command Message changes."""
            dut_test_mode_sig_combo.clear()
            msg = eol_cmd_msg_combo.currentData()
            if msg is None or index == 0:
                dut_test_mode_sig_combo.setEnabled(False)
                return
            
            dut_test_mode_sig_combo.setEnabled(True)
            signals = []
            if self.dbc_service and self.dbc_service.is_loaded():
                signals = self.dbc_service.get_message_signals(msg)
            else:
                signals = getattr(msg, 'signals', [])
            
            dut_test_mode_sig_combo.addItem('-- Select Signal --', None)
            current_dut_test_mode_sig_name = self._eol_hw_config.get('set_dut_test_mode_signal')
            current_dut_test_mode_sig_index = 0
            for idx, sig in enumerate(signals, start=1):
                sig_name = getattr(sig, 'name', '')
                sig_units = getattr(sig, 'unit', '')
                display_text = sig_name
                if sig_units:
                    display_text += f" ({sig_units})"
                dut_test_mode_sig_combo.addItem(display_text, sig)
                if sig_name == current_dut_test_mode_sig_name:
                    current_dut_test_mode_sig_index = idx
            
            if current_dut_test_mode_sig_index > 0:
                dut_test_mode_sig_combo.setCurrentIndex(current_dut_test_mode_sig_index)
        
        def on_dut_fb_message_changed(index):
            """Update DUT Test Status Signal combo when DUT Feedback Message changes."""
            dut_test_status_sig_combo.clear()
            msg = dut_fb_msg_combo.currentData()
            if msg is None or index == 0:
                dut_test_status_sig_combo.setEnabled(False)
                return
            
            dut_test_status_sig_combo.setEnabled(True)
            signals = []
            if self.dbc_service and self.dbc_service.is_loaded():
                signals = self.dbc_service.get_message_signals(msg)
            else:
                signals = getattr(msg, 'signals', [])
            
            dut_test_status_sig_combo.addItem('-- Select Signal --', None)
            current_dut_test_status_sig_name = self._eol_hw_config.get('dut_test_status_signal')
            current_dut_test_status_sig_index = 0
            for idx, sig in enumerate(signals, start=1):
                sig_name = getattr(sig, 'name', '')
                sig_units = getattr(sig, 'unit', '')
                display_text = sig_name
                if sig_units:
                    display_text += f" ({sig_units})"
                dut_test_status_sig_combo.addItem(display_text, sig)
                if sig_name == current_dut_test_status_sig_name:
                    current_dut_test_status_sig_index = idx
            
            if current_dut_test_status_sig_index > 0:
                dut_test_status_sig_combo.setCurrentIndex(current_dut_test_status_sig_index)
        
        def on_signal_changed(index):
            sig = sig_combo.currentData()
            if sig is None or index == 0:
                sig_details.setText('')
                return
            
            sig_name = getattr(sig, 'name', '')
            sig_units = getattr(sig, 'unit', '')
            sig_scale = getattr(sig, 'scale', 1.0)
            sig_offset = getattr(sig, 'offset', 0.0)
            sig_min = getattr(sig, 'minimum', None)
            sig_max = getattr(sig, 'maximum', None)
            
            details = f"Signal: {sig_name}"
            if sig_units:
                details += f", Units: {sig_units}"
            details += f", Scale: {sig_scale}, Offset: {sig_offset}"
            if sig_min is not None or sig_max is not None:
                details += f", Range: [{sig_min}, {sig_max}]"
            sig_details.setText(details)
        
        msg_combo.currentIndexChanged.connect(on_message_changed)
        sig_combo.currentIndexChanged.connect(on_signal_changed)
        eol_cmd_msg_combo.currentIndexChanged.connect(on_eol_cmd_message_changed)
        dut_fb_msg_combo.currentIndexChanged.connect(on_dut_fb_message_changed)
        
        # Set current selections
        if current_msg_index > 0:
            msg_combo.setCurrentIndex(current_msg_index)
            on_message_changed(current_msg_index)
        
        if current_eol_cmd_msg_index > 0:
            eol_cmd_msg_combo.setCurrentIndex(current_eol_cmd_msg_index)
            on_eol_cmd_message_changed(current_eol_cmd_msg_index)
        
        if current_dut_fb_msg_index > 0:
            dut_fb_msg_combo.setCurrentIndex(current_dut_fb_msg_index)
            on_dut_fb_message_changed(current_dut_fb_msg_index)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton('Save')
        cancel_btn = QtWidgets.QPushButton('Cancel')
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        def on_save():
            config_name = name_edit.text().strip()
            if not config_name:
                QtWidgets.QMessageBox.warning(dialog, 'Invalid Name', 
                    'Please enter a configuration name.')
                return
            
            msg = msg_combo.currentData()
            sig = sig_combo.currentData()
            if not msg or not sig:
                QtWidgets.QMessageBox.warning(dialog, 'Invalid Configuration', 
                    'Please select both EOL Feedback Message and Measured DAC Output Voltage Signal.')
                return
            
            # Get new field values (optional)
            eol_cmd_msg = eol_cmd_msg_combo.currentData()
            dut_test_mode_sig = dut_test_mode_sig_combo.currentData()
            dut_fb_msg = dut_fb_msg_combo.currentData()
            dut_test_status_sig = dut_test_status_sig_combo.currentData()
            
            self._eol_hw_config.update({
                'name': config_name,
                'feedback_message_id': getattr(msg, 'frame_id', 0),
                'feedback_message_name': getattr(msg, 'name', ''),
                'measured_dac_signal': getattr(sig, 'name', ''),
                'eol_command_message_id': getattr(eol_cmd_msg, 'frame_id', None) if eol_cmd_msg else None,
                'eol_command_message_name': getattr(eol_cmd_msg, 'name', None) if eol_cmd_msg else None,
                'set_dut_test_mode_signal': getattr(dut_test_mode_sig, 'name', None) if dut_test_mode_sig else None,
                'dut_feedback_message_id': getattr(dut_fb_msg, 'frame_id', None) if dut_fb_msg else None,
                'dut_feedback_message_name': getattr(dut_fb_msg, 'name', None) if dut_fb_msg else None,
                'dut_test_status_signal': getattr(dut_test_status_sig, 'name', None) if dut_test_status_sig else None,
                'updated_at': datetime.utcnow().isoformat() + 'Z'
            })
            
            self._update_eol_config_display()
            logger.info(f"Edited EOL HW configuration: {config_name}")
            QtWidgets.QMessageBox.information(dialog, 'Success', 
                f'EOL Hardware Configuration "{config_name}" updated successfully.')
            dialog.accept()
        
        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec()
    
    def _on_load_eol_config(self):
        """Load EOL hardware configuration from file."""
        try:
            default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', 'data', 'eol_configs')
            os.makedirs(default_dir, exist_ok=True)
        except Exception:
            default_dir = os.path.expanduser('~')
        
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Load EOL Hardware Configuration',
            default_dir,
            'JSON Files (*.json);;All Files (*)'
        )
        
        if not fname:
            return
        
        try:
            with open(fname, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Validate structure
            required_keys = ['feedback_message_id', 'feedback_message_name', 'measured_dac_signal']
            if not all(key in config_data for key in required_keys):
                QtWidgets.QMessageBox.warning(self, 'Invalid File', 
                    'Configuration file is missing required fields.')
                return
            
            # Validate with current DBC
            if self.dbc_service and self.dbc_service.is_loaded():
                msg = self.dbc_service.find_message_by_id(config_data['feedback_message_id'])
                if msg is None:
                    QtWidgets.QMessageBox.warning(self, 'Validation Error', 
                        f"Message ID 0x{config_data['feedback_message_id']:X} not found in loaded DBC.")
                    return
                
                # Check if signal exists in message
                msg_name = getattr(msg, 'name', '')
                signals = self.dbc_service.get_message_signals(msg)
                sig_names = [getattr(s, 'name', '') for s in signals]
                if config_data['measured_dac_signal'] not in sig_names:
                    QtWidgets.QMessageBox.warning(self, 'Validation Error', 
                        f"Signal '{config_data['measured_dac_signal']}' not found in message '{msg_name}'.")
                    return
            
            self._eol_hw_config = config_data
            self._update_eol_config_display()
            logger.info(f"Loaded EOL HW configuration from {os.path.basename(fname)}")
            QtWidgets.QMessageBox.information(self, 'Success', 
                f'EOL Hardware Configuration loaded from:\n{os.path.basename(fname)}')
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse EOL config JSON: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to parse JSON file: {e}')
        except Exception as e:
            logger.error(f"Failed to load EOL config: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to load configuration: {e}')
    
    def _on_save_eol_config(self):
        """Save current EOL hardware configuration to file."""
        if not self._eol_hw_config.get('feedback_message_id'):
            QtWidgets.QMessageBox.information(self, 'No Configuration', 
                'No EOL configuration to save. Please create or edit a configuration first.')
            return
        
        try:
            default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', 'data', 'eol_configs')
            os.makedirs(default_dir, exist_ok=True)
        except Exception:
            default_dir = os.path.expanduser('~')
        
        config_name = self._eol_hw_config.get('name', 'eol_hw_config')
        default_filename = f"{config_name.replace(' ', '_')}.json"
        
        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save EOL Hardware Configuration',
            os.path.join(default_dir, default_filename),
            'JSON Files (*.json);;All Files (*)'
        )
        
        if not fname:
            return
        
        try:
            # Update timestamp
            self._eol_hw_config['updated_at'] = datetime.utcnow().isoformat() + 'Z'
            if not self._eol_hw_config.get('created_at'):
                self._eol_hw_config['created_at'] = self._eol_hw_config['updated_at']
            
            with open(fname, 'w', encoding='utf-8') as f:
                json.dump(self._eol_hw_config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved EOL HW configuration to {os.path.basename(fname)}")
            QtWidgets.QMessageBox.information(self, 'Success', 
                f'EOL Hardware Configuration saved to:\n{os.path.basename(fname)}')
            
            # Refresh saved configurations list
            self._refresh_eol_config_list()
        except Exception as e:
            logger.error(f"Failed to save EOL config: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to save configuration: {e}')
    
    def _on_eol_config_list_double_clicked(self, item: QtWidgets.QListWidgetItem):
        """Load configuration when double-clicked in list."""
        if not item:
            return
        
        filepath = item.data(QtCore.Qt.UserRole)
        if not filepath or not os.path.exists(filepath):
            QtWidgets.QMessageBox.warning(self, 'File Not Found', 
                'Configuration file no longer exists.')
            self._refresh_eol_config_list()
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            required_keys = ['feedback_message_id', 'feedback_message_name', 'measured_dac_signal']
            if not all(key in config_data for key in required_keys):
                QtWidgets.QMessageBox.warning(self, 'Invalid File', 
                    'Configuration file is missing required fields.')
                return
            
            self._eol_hw_config = config_data
            self._update_eol_config_display()
            logger.info(f"Loaded EOL HW configuration from list: {os.path.basename(filepath)}")
        except Exception as e:
            logger.error(f"Failed to load EOL config from list: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to load configuration: {e}')
    
    def _update_eol_config_display(self):
        """Update the display labels for current EOL configuration."""
        if not hasattr(self, 'eol_feedback_msg_label'):
            return
        
        config = self._eol_hw_config
        if config.get('feedback_message_id'):
            name = config.get('name', 'Unnamed')
            msg_name = config.get('feedback_message_name', 'Unknown')
            msg_id = config.get('feedback_message_id', 0)
            signal_name = config.get('measured_dac_signal', 'Unknown')
            
            self.eol_config_name_label.setText(name)
            self.eol_config_name_label.setStyleSheet('')
            self.eol_feedback_msg_label.setText(f"{msg_name} (0x{msg_id:X})")
            self.eol_feedback_msg_label.setStyleSheet('')
            self.eol_dac_signal_label.setText(signal_name)
            self.eol_dac_signal_label.setStyleSheet('')
            
            # Display new fields
            eol_cmd_msg_id = config.get('eol_command_message_id')
            eol_cmd_msg_name = config.get('eol_command_message_name', '')
            if eol_cmd_msg_id:
                self.eol_command_msg_label.setText(f"{eol_cmd_msg_name} (0x{eol_cmd_msg_id:X})" if eol_cmd_msg_name else f"0x{eol_cmd_msg_id:X}")
                self.eol_command_msg_label.setStyleSheet('')
            else:
                self.eol_command_msg_label.setText('Not configured')
                self.eol_command_msg_label.setStyleSheet('color: gray; font-style: italic;')
            
            dut_test_mode_sig = config.get('set_dut_test_mode_signal')
            if dut_test_mode_sig:
                self.eol_dut_test_mode_signal_label.setText(dut_test_mode_sig)
                self.eol_dut_test_mode_signal_label.setStyleSheet('')
            else:
                self.eol_dut_test_mode_signal_label.setText('Not configured')
                self.eol_dut_test_mode_signal_label.setStyleSheet('color: gray; font-style: italic;')
            
            dut_fb_msg_id = config.get('dut_feedback_message_id')
            dut_fb_msg_name = config.get('dut_feedback_message_name', '')
            if dut_fb_msg_id:
                self.eol_dut_feedback_msg_label.setText(f"{dut_fb_msg_name} (0x{dut_fb_msg_id:X})" if dut_fb_msg_name else f"0x{dut_fb_msg_id:X}")
                self.eol_dut_feedback_msg_label.setStyleSheet('')
            else:
                self.eol_dut_feedback_msg_label.setText('Not configured')
                self.eol_dut_feedback_msg_label.setStyleSheet('color: gray; font-style: italic;')
            
            dut_test_status_sig = config.get('dut_test_status_signal')
            if dut_test_status_sig:
                self.eol_dut_test_status_signal_label.setText(dut_test_status_sig)
                self.eol_dut_test_status_signal_label.setStyleSheet('')
            else:
                self.eol_dut_test_status_signal_label.setText('Not configured')
                self.eol_dut_test_status_signal_label.setStyleSheet('color: gray; font-style: italic;')
        else:
            self.eol_config_name_label.setText('No configuration loaded')
            self.eol_config_name_label.setStyleSheet('color: gray; font-style: italic;')
            self.eol_feedback_msg_label.setText('Not configured')
            self.eol_feedback_msg_label.setStyleSheet('color: gray; font-style: italic;')
            self.eol_dac_signal_label.setText('Not configured')
            self.eol_dac_signal_label.setStyleSheet('color: gray; font-style: italic;')
            self.eol_command_msg_label.setText('Not configured')
            self.eol_command_msg_label.setStyleSheet('color: gray; font-style: italic;')
            self.eol_dut_test_mode_signal_label.setText('Not configured')
            self.eol_dut_test_mode_signal_label.setStyleSheet('color: gray; font-style: italic;')
            self.eol_dut_feedback_msg_label.setText('Not configured')
            self.eol_dut_feedback_msg_label.setStyleSheet('color: gray; font-style: italic;')
            self.eol_dut_test_status_signal_label.setText('Not configured')
            self.eol_dut_test_status_signal_label.setStyleSheet('color: gray; font-style: italic;')
    
    def _refresh_eol_config_list(self):
        """Refresh the list of saved EOL configurations."""
        if not hasattr(self, 'eol_config_list'):
            return
        
        self.eol_config_list.clear()
        
        try:
            config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', 'data', 'eol_configs')
            if not os.path.exists(config_dir):
                return
            
            config_files = []
            for filename in os.listdir(config_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(config_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                            config_name = config_data.get('name', filename.replace('.json', ''))
                            updated_at = config_data.get('updated_at', '')
                            item_text = config_name
                            if updated_at:
                                try:
                                    dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                                    item_text += f" (Updated: {dt.strftime('%Y-%m-%d %H:%M')})"
                                except Exception:
                                    pass
                            config_files.append((item_text, filepath, os.path.getmtime(filepath)))
                    except Exception:
                        continue
            
            # Sort by modification time (newest first)
            config_files.sort(key=lambda x: x[2], reverse=True)
            
            for item_text, filepath, _ in config_files:
                item = QtWidgets.QListWidgetItem(item_text)
                item.setData(QtCore.Qt.UserRole, filepath)
                self.eol_config_list.addItem(item)
        except Exception as e:
            logger.debug(f"Error refreshing EOL config list: {e}", exc_info=True)
    
    # Oscilloscope Configuration handlers
    def _on_create_osc_config(self):
        """Reset to default oscilloscope configuration."""
        self._oscilloscope_config = {
            'name': None,
            'version': '1.0',
            'created_at': None,
            'updated_at': None,
            'channels': {
                'CH1': {
                    'enabled': True,
                    'channel_name': 'CH1',
                    'probe_attenuation': 1.0,
                    'unit': 'V'
                },
                'CH2': {
                    'enabled': False,
                    'channel_name': 'CH2',
                    'probe_attenuation': 1.0,
                    'unit': 'V'
                },
                'CH3': {
                    'enabled': False,
                    'channel_name': 'CH3',
                    'probe_attenuation': 1.0,
                    'unit': 'V'
                },
                'CH4': {
                    'enabled': False,
                    'channel_name': 'CH4',
                    'probe_attenuation': 1.0,
                    'unit': 'V'
                }
            },
            'acquisition': {
                'timebase_ms': 1.0
            }
        }
        self._osc_config_file_path = None
        self._osc_config_applied = False
        self._update_osc_config_ui()
        self.osc_config_status_label.setText('Status: Not Applied')
        self.osc_config_status_label.setStyleSheet('color: gray; font-weight: bold;')
        logger.info("Created new oscilloscope configuration")
    
    def _on_edit_osc_config(self):
        """Edit current oscilloscope configuration (same as create, just updates UI)."""
        # Editing is done directly in the UI, this just ensures UI is up to date
        self._update_osc_config_ui()
        logger.info("Editing oscilloscope configuration")
    
    def _on_load_osc_config(self):
        """Load oscilloscope configuration from file."""
        try:
            default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', 'data', 'oscilloscope_configs')
            os.makedirs(default_dir, exist_ok=True)
        except Exception:
            default_dir = os.path.expanduser('~')
        
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Load Oscilloscope Configuration',
            default_dir,
            'JSON Files (*.json);;All Files (*)'
        )
        
        if not fname:
            return
        
        self._load_osc_config_from_file(fname)
    
    def _load_osc_config_from_file(self, fname: str):
        """Load oscilloscope configuration from file path."""
        try:
            with open(fname, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Validate structure
            if 'channels' not in config_data:
                QtWidgets.QMessageBox.warning(self, 'Invalid File', 
                    'Configuration file is missing required fields (channels).')
                return
            
            # Validate and fix channel structure
            for ch_key in ['CH1', 'CH2', 'CH3', 'CH4']:
                if ch_key not in config_data['channels']:
                    # Add default channel if missing
                    config_data['channels'][ch_key] = {
                        'enabled': False,
                        'channel_name': ch_key,
                        'probe_attenuation': 1.0,
                        'unit': 'V'
                    }
                else:
                    # Ensure all required fields exist
                    ch = config_data['channels'][ch_key]
                    ch.setdefault('enabled', False)
                    ch.setdefault('channel_name', ch_key)
                    ch.setdefault('probe_attenuation', 1.0)
                    ch.setdefault('unit', 'V')
            
            # Validate acquisition structure
            acquisition = config_data.get('acquisition', {})
            acquisition.setdefault('timebase_ms', 1.0)
            config_data['acquisition'] = acquisition
            
            # Set defaults for missing top-level fields
            config_data.setdefault('version', '1.0')
            config_data.setdefault('name', os.path.basename(fname).replace('.json', ''))
            
            self._oscilloscope_config = config_data
            self._osc_config_file_path = fname
            self._osc_config_applied = False
            self._update_osc_config_ui()
            self.osc_config_status_label.setText('Status: Not Applied')
            self.osc_config_status_label.setStyleSheet('color: gray; font-weight: bold;')
            
            # Save path to QSettings for auto-load
            if self.config_manager and self.config_manager._qsettings:
                self.config_manager._qsettings.setValue('oscilloscope/last_config_path', fname)
            
            logger.info(f"Loaded oscilloscope configuration from {os.path.basename(fname)}")
            QtWidgets.QMessageBox.information(self, 'Success', 
                f'Oscilloscope Configuration loaded from:\n{os.path.basename(fname)}')
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse oscilloscope config JSON: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to parse JSON file: {e}')
        except Exception as e:
            logger.error(f"Failed to load oscilloscope config: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to load configuration: {e}')
    
    def _on_save_osc_config(self):
        """Save current oscilloscope configuration to file."""
        # Collect values from UI
        self._collect_osc_config_from_ui()
        
        # Validate configuration
        is_valid, errors = self._validate_osc_config()
        if not is_valid:
            error_msg = 'Configuration validation failed:\n' + '\n'.join(errors)
            QtWidgets.QMessageBox.warning(self, 'Validation Error', error_msg)
            return
        
        try:
            default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', 'data', 'oscilloscope_configs')
            os.makedirs(default_dir, exist_ok=True)
        except Exception:
            default_dir = os.path.expanduser('~')
        
        # Get config name - use existing name or prompt user
        config_name = self._oscilloscope_config.get('name')
        if not config_name or config_name.strip() == '':
            # Prompt for configuration name
            name, ok = QtWidgets.QInputDialog.getText(
                self, 
                'Configuration Name', 
                'Enter a name for this configuration:',
                text='oscilloscope_config'
            )
            if not ok or not name.strip():
                # User cancelled or entered empty name
                return
            config_name = name.strip()
        
        # Ensure filename has .json extension
        default_filename = f"{config_name.replace(' ', '_')}.json"
        if not default_filename.endswith('.json'):
            default_filename += '.json'
        
        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save Oscilloscope Configuration',
            os.path.join(default_dir, default_filename),
            'JSON Files (*.json);;All Files (*)'
        )
        
        if not fname:
            return
        
        # Ensure saved filename has .json extension
        if not fname.endswith('.json'):
            fname += '.json'
        
        # Extract config name from filename if it was changed
        file_basename = os.path.basename(fname)
        if file_basename.endswith('.json'):
            config_name_from_file = file_basename[:-5].replace('_', ' ')
            if config_name_from_file:
                config_name = config_name_from_file
        
        try:
            # Update configuration with name and timestamp
            self._oscilloscope_config['name'] = config_name
            self._oscilloscope_config['updated_at'] = datetime.utcnow().isoformat() + 'Z'
            if not self._oscilloscope_config.get('created_at'):
                self._oscilloscope_config['created_at'] = self._oscilloscope_config['updated_at']
            
            # Write to file
            with open(fname, 'w', encoding='utf-8') as f:
                json.dump(self._oscilloscope_config, f, indent=2, ensure_ascii=False)
            
            self._osc_config_file_path = fname
            
            # Save path to QSettings for auto-load
            if self.config_manager and self.config_manager._qsettings:
                self.config_manager._qsettings.setValue('oscilloscope/last_config_path', fname)
            
            logger.info(f"Saved oscilloscope configuration to {os.path.basename(fname)}")
            QtWidgets.QMessageBox.information(self, 'Success', 
                f'Oscilloscope Configuration saved to:\n{os.path.basename(fname)}')
            
            # Refresh saved configurations list
            self._refresh_osc_config_list()
        except PermissionError as e:
            logger.error(f"Permission denied saving oscilloscope config: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Permission Error', 
                f'Permission denied saving to:\n{os.path.basename(fname)}\n\nPlease check file permissions.')
        except OSError as e:
            logger.error(f"OS error saving oscilloscope config: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', 
                f'Failed to save configuration:\n{str(e)}\n\nPlease check if the directory exists and is writable.')
        except Exception as e:
            logger.error(f"Failed to save oscilloscope config: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to save configuration: {e}')
    
    def _on_apply_osc_config(self):
        """Validate oscilloscope settings by comparing with current configuration.
        
        This method queries the oscilloscope for channel trace status and probe attenuation,
        then compares them with the configuration in the UI.
        """
        if self.oscilloscope_service is None:
            QtWidgets.QMessageBox.warning(self, 'Oscilloscope Service', 
                'Oscilloscope service not available.')
            return
        
        if not self.oscilloscope_service.is_connected():
            QtWidgets.QMessageBox.warning(self, 'Not Connected', 
                'Oscilloscope is not connected. Please connect first.')
            return
        
        # Collect values from UI
        self._collect_osc_config_from_ui()
        
        # Show progress dialog
        progress = QtWidgets.QProgressDialog('Validating oscilloscope settings...', 'Cancel', 0, 0, self)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setCancelButton(None)  # Don't allow cancel
        progress.show()
        QtWidgets.QApplication.processEvents()
        
        try:
            comparison_results = []
            errors = []
            
            # Query each channel's trace status and probe attenuation
            for ch_num in [1, 2, 3, 4]:
                ch_key = f'CH{ch_num}'
                channel_config = self._oscilloscope_config.get('channels', {}).get(ch_key, {})
                expected_enabled = channel_config.get('enabled', False)
                expected_attenuation = channel_config.get('probe_attenuation', 1.0)
                
                # Query trace status (C1:TRA?, C2:TRA?, etc.)
                time.sleep(0.2)  # Delay between queries
                tra_response = self.oscilloscope_service.send_command(f"C{ch_num}:TRA?")
                
                if tra_response is None:
                    errors.append(f"Channel {ch_num}: Failed to query trace status")
                    actual_enabled = None
                else:
                    # Parse response - expect ON/OFF or 1/0
                    # Response format: "C1:TRA ON\n" or "C1:TRA OFF\n"
                    tra_str = tra_response.strip()
                    tra_str_upper = tra_str.upper()
                    # Check if response contains ON, OFF, 1, or 0
                    if 'ON' in tra_str_upper or tra_str_upper == '1' or 'TRUE' in tra_str_upper:
                        actual_enabled = True
                    elif 'OFF' in tra_str_upper or tra_str_upper == '0' or 'FALSE' in tra_str_upper:
                        actual_enabled = False
                    else:
                        # Try to extract from formats like "C1:TRA ON" or "C1:TRA 1"
                        tra_match = re.search(r'TRA\s+(\w+)', tra_str, re.IGNORECASE)
                        if tra_match:
                            tra_val = tra_match.group(1).upper()
                            actual_enabled = tra_val in ['ON', '1', 'TRUE']
                        else:
                            # Default: try to parse as boolean from the string
                            actual_enabled = tra_str_upper in ['ON', '1', 'TRUE']
                
                # Query probe attenuation (C1:ATTN?, C2:ATTN?, etc.)
                time.sleep(0.2)  # Delay between queries
                attn_response = self.oscilloscope_service.send_command(f"C{ch_num}:ATTN?")
                
                if attn_response is None:
                    errors.append(f"Channel {ch_num}: Failed to query probe attenuation")
                    actual_attenuation = None
                else:
                    # Parse response - extract numeric value
                    # Response format: "C1:ATTN 811.97\n"
                    try:
                        attn_str = attn_response.strip()
                        # Extract number after "ATTN " to avoid matching channel number
                        attn_match = re.search(r'ATTN\s+([\d.]+)', attn_str, re.IGNORECASE)
                        if attn_match:
                            actual_attenuation = float(attn_match.group(1))
                        else:
                            # Fallback: find all numbers and take the last one (avoiding channel number)
                            all_numbers = re.findall(r'([\d.]+)', attn_str)
                            if all_numbers:
                                # Take the last number (should be the attenuation value)
                                actual_attenuation = float(all_numbers[-1])
                            else:
                                actual_attenuation = float(attn_str)
                    except (ValueError, AttributeError):
                        errors.append(f"Channel {ch_num}: Invalid probe attenuation response: {attn_response}")
                        actual_attenuation = None
                
                # Compare values
                trace_match = (actual_enabled == expected_enabled) if actual_enabled is not None else False
                attn_match = (abs(actual_attenuation - expected_attenuation) < 0.01) if actual_attenuation is not None else False
                
                comparison_results.append({
                    'channel': ch_key,
                    'trace_match': trace_match,
                    'expected_trace': expected_enabled,
                    'actual_trace': actual_enabled,
                    'attenuation_match': attn_match,
                    'expected_attenuation': expected_attenuation,
                    'actual_attenuation': actual_attenuation
                })
            
            progress.close()
            
            # Build comparison message
            message_lines = ["Oscilloscope Settings Validation Results:\n"]
            all_match = True
            
            for result in comparison_results:
                ch = result['channel']
                trace_match = result['trace_match']
                attn_match = result['attenuation_match']
                
                if trace_match and attn_match:
                    message_lines.append(f"{ch}: ✓ Match")
                else:
                    all_match = False
                    message_lines.append(f"{ch}: ✗ Mismatch")
                    
                    if not trace_match:
                        expected_trace_str = "ON" if result['expected_trace'] else "OFF"
                        actual_trace_str = "ON" if result['actual_trace'] else "OFF" if result['actual_trace'] is not None else "Query Failed"
                        message_lines.append(f"  - Trace: Expected {expected_trace_str}, Got {actual_trace_str}")
                    
                    if not attn_match:
                        expected_attn = result['expected_attenuation']
                        actual_attn = result['actual_attenuation'] if result['actual_attenuation'] is not None else "Query Failed"
                        message_lines.append(f"  - Attenuation: Expected {expected_attn}, Got {actual_attn}")
            
            if errors:
                message_lines.append("\nErrors:")
                message_lines.extend(f"  - {err}" for err in errors)
            
            message = '\n'.join(message_lines)
            
            if all_match and not errors:
                logger.info("Oscilloscope settings validation: All settings match")
                QtWidgets.QMessageBox.information(self, 'Validation Success', message)
            else:
                logger.warning(f"Oscilloscope settings validation: Mismatches found")
                QtWidgets.QMessageBox.warning(self, 'Validation Results', message)
                
        except Exception as e:
            progress.close()
            logger.error(f"Error validating oscilloscope settings: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to validate settings: {e}')
    
    def _on_osc_config_list_double_clicked(self, item: QtWidgets.QListWidgetItem):
        """Load configuration when double-clicked in list."""
        if not item:
            return
        
        filepath = item.data(QtCore.Qt.UserRole)
        if not filepath or not os.path.exists(filepath):
            QtWidgets.QMessageBox.warning(self, 'File Not Found', 
                'Configuration file no longer exists.')
            self._refresh_osc_config_list()
            return
        
        self._load_osc_config_from_file(filepath)
    
    def _on_osc_channel_enable_changed(self, channel_num: int, enabled: bool):
        """Handle channel enable/disable checkbox change."""
        ch_key = f'CH{channel_num}'
        
        # Get widgets for this channel
        name_widget = self.osc_channel_widgets.get(f'{ch_key}_name')
        probe_widget = self.osc_channel_widgets.get(f'{ch_key}_probe')
        unit_widget = self.osc_channel_widgets.get(f'{ch_key}_unit')
        
        if name_widget and probe_widget and unit_widget:
            # Enable/disable fields based on checkbox
            name_widget.setEnabled(enabled)
            probe_widget.setEnabled(enabled)
            unit_widget.setEnabled(enabled)
            
            # Update styling when disabled
            if not enabled:
                name_widget.setStyleSheet('color: gray;')
                probe_widget.setStyleSheet('color: gray;')
                unit_widget.setStyleSheet('color: gray;')
            else:
                name_widget.setStyleSheet('')
                probe_widget.setStyleSheet('')
                unit_widget.setStyleSheet('')
        
    
    def _collect_osc_config_from_ui(self):
        """Collect configuration values from UI widgets into _oscilloscope_config."""
        if not hasattr(self, 'osc_channel_widgets'):
            return
        
        # Collect channel settings
        for ch_num in [1, 2, 3, 4]:
            ch_key = f'CH{ch_num}'
            enable_widget = self.osc_channel_widgets.get(f'{ch_key}_enable')
            name_widget = self.osc_channel_widgets.get(f'{ch_key}_name')
            probe_widget = self.osc_channel_widgets.get(f'{ch_key}_probe')
            unit_widget = self.osc_channel_widgets.get(f'{ch_key}_unit')
            
            if enable_widget and name_widget and probe_widget and unit_widget:
                self._oscilloscope_config['channels'][ch_key] = {
                    'enabled': enable_widget.isChecked(),
                    'channel_name': name_widget.text().strip() or ch_key,
                    'probe_attenuation': probe_widget.value(),
                    'unit': unit_widget.currentText()
                }
        
        # Collect acquisition settings
        if hasattr(self, 'osc_timebase'):
            self._oscilloscope_config['acquisition'] = {
                'timebase_ms': self.osc_timebase.value()
            }
    
    def _update_osc_config_ui(self):
        """Update UI widgets from _oscilloscope_config dictionary."""
        if not hasattr(self, 'osc_channel_widgets'):
            return
        
        # Update channel widgets
        for ch_num in [1, 2, 3, 4]:
            ch_key = f'CH{ch_num}'
            ch_config = self._oscilloscope_config.get('channels', {}).get(ch_key, {})
            
            enable_widget = self.osc_channel_widgets.get(f'{ch_key}_enable')
            name_widget = self.osc_channel_widgets.get(f'{ch_key}_name')
            probe_widget = self.osc_channel_widgets.get(f'{ch_key}_probe')
            unit_widget = self.osc_channel_widgets.get(f'{ch_key}_unit')
            
            if enable_widget:
                enabled = ch_config.get('enabled', ch_num == 1)
                enable_widget.setChecked(enabled)
                # Trigger enable/disable handler
                self._on_osc_channel_enable_changed(ch_num, enabled)
            
            if name_widget:
                name_widget.setText(ch_config.get('channel_name', ch_key))
            
            if probe_widget:
                probe_widget.setValue(ch_config.get('probe_attenuation', 1.0))
            
            if unit_widget:
                unit = ch_config.get('unit', 'V')
                index = unit_widget.findText(unit)
                if index >= 0:
                    unit_widget.setCurrentIndex(index)
        
        # Update acquisition settings widgets
        acquisition_config = self._oscilloscope_config.get('acquisition', {})
        if hasattr(self, 'osc_timebase'):
            timebase_ms = acquisition_config.get('timebase_ms', 1.0)
            self.osc_timebase.setValue(timebase_ms)
    
    def _validate_osc_config(self) -> Tuple[bool, List[str]]:
        """Validate oscilloscope configuration.
        
        Returns:
            Tuple of (is_valid: bool, errors: List[str])
        """
        errors = []
        
        # 1. Check channel name uniqueness
        channel_names = []
        for ch_key in ['CH1', 'CH2', 'CH3', 'CH4']:
            ch_config = self._oscilloscope_config.get('channels', {}).get(ch_key, {})
            if ch_config.get('enabled', False):
                name = ch_config.get('channel_name', '').strip()
                if not name:
                    errors.append(f"{ch_key}: Channel name cannot be empty when enabled")
                elif name in channel_names:
                    errors.append(f"{ch_key}: Channel name '{name}' must be unique")
                else:
                    channel_names.append(name)
        
        # 2. Validate timebase (must be > 0)
        acquisition_config = self._oscilloscope_config.get('acquisition', {})
        timebase_ms = acquisition_config.get('timebase_ms', 1.0)
        if timebase_ms <= 0:
            errors.append("Timebase must be greater than 0")
        
        # 3. Validate probe attenuation (must be > 0)
        for ch_key in ['CH1', 'CH2', 'CH3', 'CH4']:
            ch_config = self._oscilloscope_config.get('channels', {}).get(ch_key, {})
            if ch_config.get('enabled', False):
                att = ch_config.get('probe_attenuation', 1.0)
                if att <= 0:
                    errors.append(f"{ch_key}: Probe attenuation must be greater than 0")
        
        # 4. Validate unit (must be V or A)
        for ch_key in ['CH1', 'CH2', 'CH3', 'CH4']:
            ch_config = self._oscilloscope_config.get('channels', {}).get(ch_key, {})
            if ch_config.get('enabled', False):
                unit = ch_config.get('unit', 'V')
                if unit not in ['V', 'A']:
                    errors.append(f"{ch_key}: Unit must be 'V' or 'A'")
        
        return len(errors) == 0, errors
    
    def _refresh_osc_config_list(self):
        """Refresh the list of saved oscilloscope configurations."""
        if not hasattr(self, 'osc_config_list'):
            return
        
        self.osc_config_list.clear()
        
        try:
            config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', 'data', 'oscilloscope_configs')
            if not os.path.exists(config_dir):
                return
            
            config_files = []
            for filename in os.listdir(config_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(config_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                            config_name = config_data.get('name', filename.replace('.json', ''))
                            updated_at = config_data.get('updated_at', '')
                            item_text = config_name
                            if updated_at:
                                try:
                                    dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                                    item_text += f" (Updated: {dt.strftime('%Y-%m-%d %H:%M')})"
                                except Exception:
                                    pass
                            config_files.append((item_text, filepath, os.path.getmtime(filepath)))
                    except Exception:
                        continue
            
            # Sort by modification time (newest first)
            config_files.sort(key=lambda x: x[2], reverse=True)
            
            for item_text, filepath, _ in config_files:
                item = QtWidgets.QListWidgetItem(item_text)
                item.setData(QtCore.Qt.UserRole, filepath)
                self.osc_config_list.addItem(item)
        except Exception as e:
            logger.debug(f"Error refreshing oscilloscope config list: {e}", exc_info=True)
    
    def _load_last_osc_config(self):
        """Load the last used oscilloscope configuration from QSettings."""
        try:
            if self.config_manager and self.config_manager._qsettings:
                last_config = self.config_manager._qsettings.value('oscilloscope/last_config_path', None)
                if last_config and os.path.exists(last_config):
                    self._load_osc_config_from_file(last_config)
                    logger.info(f"Auto-loaded last oscilloscope configuration: {last_config}")
        except Exception as e:
            logger.warning(f"Failed to auto-load last oscilloscope config: {e}")
    
    def _initialize_oscilloscope_for_test(self, test: Dict[str, Any]) -> bool:
        """Initialize oscilloscope before phase current test execution.
        
        This method applies the current oscilloscope configuration to the connected
        oscilloscope as part of test initialization. It is called automatically
        before phase current calibration tests.
        
        Args:
            test: Test configuration dictionary
        
        Returns:
            True if oscilloscope initialized successfully, False otherwise
            Note: Returns False if oscilloscope not connected or test is not phase_current
        """
        # Check if test type is phase_current_calibration
        act = test.get('actuation', {})
        if act.get('type') != 'Phase Current Test':
            return True  # Not a phase current test, no initialization needed
        
        # Check if oscilloscope service is available and connected
        if self.oscilloscope_service is None:
            logger.warning("Oscilloscope service not available for phase current test")
            return False
        
        if not self.oscilloscope_service.is_connected():
            logger.warning("Oscilloscope not connected, cannot initialize for phase current test")
            return False
        
        # Collect current configuration from UI if tab exists
        if hasattr(self, 'osc_channel_widgets'):
            self._collect_osc_config_from_ui()
        
        # Validate configuration
        is_valid, errors = self._validate_osc_config()
        if not is_valid:
            logger.warning(f"Oscilloscope configuration validation failed: {errors}")
            # Continue anyway, but log warning
        
        # Apply configuration
        try:
            logger.info("Initializing oscilloscope for phase current test...")
            success, errors = self.oscilloscope_service.apply_configuration(self._oscilloscope_config)
            
            if success:
                self._osc_config_applied = True
                logger.info("Oscilloscope initialized successfully for phase current test")
                return True
            else:
                logger.warning(f"Oscilloscope initialization completed with errors: {errors}")
                # Continue test execution even if some settings failed
                return len(errors) == 0  # Return True only if no errors
        except Exception as e:
            logger.error(f"Error initializing oscilloscope for phase current test: {e}", exc_info=True)
            # Continue test execution even if initialization fails
            return False
    
    def _check_dbc_loaded(self) -> bool:
        """Check if DBC is loaded, show message if not."""
        dbc_loaded = False
        if self.dbc_service and self.dbc_service.is_loaded():
            dbc_loaded = True
        elif self.dbc_service and hasattr(self.dbc_service, 'database') and self.dbc_service.database:
            dbc_loaded = True
        
        if not dbc_loaded:
            QtWidgets.QMessageBox.warning(self, 'No DBC Loaded', 
                'Please load a DBC file first in the CAN Data View tab before configuring EOL hardware.')
        return dbc_loaded
    
    # Test Configurator handlers
    def _on_load_dbc(self):
        """Load a DBC file using DbcService (Phase 1) or legacy method."""
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Select DBC file', '', 'DBC files (*.dbc);;All files (*)')
        if not fname:
            return
        self.dbc_path_edit.setText(fname)
        
        # Phase 1: Use DbcService if available
        if self.dbc_service is not None:
            try:
                if self.dbc_service.load_dbc_file(fname):
                    # DBC loaded via service
                    # Clear signal cache when DBC reloaded
                    if self.signal_service is not None:
                        self.signal_service.clear_cache()
                    self._clear_dbcs_cache()
                    message_count = len(self.dbc_service.get_all_messages())
                    QtWidgets.QMessageBox.information(self, 'DBC Loaded', f'Loaded DBC: {os.path.basename(fname)} ({message_count} messages)')
                    logger.info(f"DBC loaded successfully via service: {os.path.basename(fname)} ({message_count} messages)")
                    return
                else:
                    logger.warning(f"DbcService.load_dbc_file returned False for: {fname}")
                    QtWidgets.QMessageBox.warning(self, 'Error', f'Failed to load DBC file: {fname}')
                    return
            except (FileNotFoundError, ValueError, RuntimeError) as e:
                logger.error(f"Failed to load DBC via service: {e}", exc_info=True)
                QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to load DBC: {e}')
                return
        
        # Legacy implementation (fallback) - should not be reached if services are available
        if cantools is None:
            QtWidgets.QMessageBox.warning(self, 'DBC Load', 'cantools not installed in this environment. Install cantools to enable DBC parsing.')
            return
        try:
            # cantools provides database.load_file
            try:
                db = cantools.database.load_file(fname)
            except Exception:
                # fallback to older API name
                db = cantools.db.load_file(fname)
            # Load via service if available, otherwise this is a fallback that shouldn't happen
            if self.dbc_service is not None:
                # Try to load via service with the database object
                logger.warning("Legacy DBC loading path used - services should handle this")
            
            # If DbcService is available, try to sync the DBC into it
            if self.dbc_service is not None:
                try:
                    # Manually set the database in DbcService to keep them in sync
                    self.dbc_service.database = db
                    self.dbc_service.dbc_path = fname
                    logger.info(f"Synced legacy DBC load into DbcService: {os.path.basename(fname)}")
                except Exception as e:
                    logger.warning(f"Failed to sync DBC into DbcService: {e}", exc_info=True)
            
            # Clear signal cache when DBC reloaded
            if self.signal_service is not None:
                self.signal_service.clear_cache()
            self._clear_dbcs_cache()
            
            # Create/Edit dialogs will query dbc_service.database when opened
            QtWidgets.QMessageBox.information(self, 'DBC Loaded', f'Loaded DBC: {os.path.basename(fname)} ({len(getattr(db, "messages", []))} messages)')
        except Exception as e:
            if self.dbc_service is not None:
                try:
                    self.dbc_service.database = None
                    self.dbc_service.dbc_path = None
                except Exception:
                    pass
            logger.error(f"Failed to load DBC: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to load DBC: {e}')

    def _on_create_test(self):
        # Create a dialog to create a test entry (name, type, actuation mapping)
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Create Test')
        v = QtWidgets.QVBoxLayout(dlg)
        form = QtWidgets.QFormLayout()
        name_edit = QtWidgets.QLineEdit()
        type_combo = QtWidgets.QComboBox()
        type_combo.addItems(['Digital Logic Test', 'Analog Sweep Test', 'Phase Current Test', 'Analog Static Test', 'Analog PWM Sensor', 'Temperature Validation Test', 'Fan Control Test', 'External 5V Test', 'DC Bus Sensing', 'Output Current Calibration', 'Charged HV Bus Test', 'Charger Functional Test'])
        feedback_edit = QtWidgets.QLineEdit()
        # actuation fields container - use QStackedWidget to show only relevant fields
        act_stacked = QtWidgets.QStackedWidget()
        # separate digital, analog, phase_current_calibration, and analog_static sub-widgets so we can show/hide based on type
        digital_widget = QtWidgets.QWidget()
        digital_layout = QtWidgets.QFormLayout(digital_widget)
        analog_widget = QtWidgets.QWidget()
        analog_layout = QtWidgets.QFormLayout(analog_widget)
        phase_current_widget = QtWidgets.QWidget()
        phase_current_layout = QtWidgets.QFormLayout(phase_current_widget)
        analog_static_widget = QtWidgets.QWidget()
        analog_static_layout = QtWidgets.QFormLayout(analog_static_widget)
        temperature_validation_widget = QtWidgets.QWidget()
        temperature_validation_layout = QtWidgets.QFormLayout(temperature_validation_widget)
        analog_pwm_sensor_widget = QtWidgets.QWidget()
        analog_pwm_sensor_layout = QtWidgets.QFormLayout(analog_pwm_sensor_widget)
        fan_control_widget = QtWidgets.QWidget()
        fan_control_layout = QtWidgets.QFormLayout(fan_control_widget)
        ext_5v_test_widget = QtWidgets.QWidget()
        ext_5v_test_layout = QtWidgets.QFormLayout(ext_5v_test_widget)
        
        # Initialize analog_static variables to None (will be set in if/else blocks)
        # Initialize temperature_validation variables to None (will be set in if/else blocks)
        # Initialize analog_pwm_sensor variables to None (will be set in if/else blocks)
        # Initialize fan_control variables to None (will be set in if/else blocks)
        temp_val_fb_msg_combo = None
        temp_val_fb_signal_combo = None
        temp_val_reference_edit = None
        temp_val_tolerance_edit = None
        temp_val_dwell_time_edit = None
        temp_val_fb_msg_edit = None
        temp_val_fb_signal_edit = None
        temp_val_reference_edit_fallback = None
        temp_val_tolerance_edit_fallback = None
        temp_val_dwell_time_edit_fallback = None
        analog_pwm_fb_msg_combo = None
        analog_pwm_frequency_signal_combo = None
        analog_pwm_duty_signal_combo = None
        analog_pwm_reference_frequency_edit = None
        analog_pwm_reference_duty_edit = None
        analog_pwm_frequency_tolerance_edit = None
        analog_pwm_duty_tolerance_edit = None
        analog_pwm_acquisition_time_edit = None
        analog_pwm_fb_msg_edit = None
        analog_pwm_frequency_signal_edit = None
        analog_pwm_duty_signal_edit = None
        analog_pwm_reference_frequency_edit_fallback = None
        analog_pwm_reference_duty_edit_fallback = None
        analog_pwm_frequency_tolerance_edit_fallback = None
        analog_pwm_duty_tolerance_edit_fallback = None
        analog_pwm_acquisition_time_edit_fallback = None
        fan_control_trigger_msg_combo = None
        fan_control_trigger_signal_combo = None
        fan_control_feedback_msg_combo = None
        fan_control_enabled_signal_combo = None
        fan_control_tach_signal_combo = None
        fan_control_fault_signal_combo = None
        fan_control_dwell_time_edit = None
        fan_control_timeout_edit = None
        fan_control_trigger_msg_edit = None
        fan_control_trigger_signal_edit = None
        fan_control_feedback_msg_edit = None
        fan_control_enabled_signal_edit = None
        fan_control_tach_signal_edit = None
        fan_control_fault_signal_edit = None
        fan_control_dwell_time_edit_fallback = None
        fan_control_timeout_edit_fallback = None
        ext_5v_test_trigger_msg_combo = None
        ext_5v_test_trigger_signal_combo = None
        ext_5v_test_eol_msg_combo = None
        ext_5v_test_eol_signal_combo = None
        ext_5v_test_feedback_msg_combo = None
        ext_5v_test_feedback_signal_combo = None
        ext_5v_test_tolerance_edit = None
        ext_5v_test_pre_dwell_time_edit = None
        ext_5v_test_dwell_time_edit = None
        ext_5v_test_trigger_msg_edit = None
        ext_5v_test_trigger_signal_edit = None
        ext_5v_test_eol_msg_edit = None
        ext_5v_test_eol_signal_edit = None
        ext_5v_test_feedback_msg_edit = None
        ext_5v_test_feedback_signal_edit = None
        ext_5v_test_tolerance_edit_fallback = None
        ext_5v_test_pre_dwell_time_edit_fallback = None
        ext_5v_test_dwell_time_edit_fallback = None
        analog_static_fb_msg_combo = None
        analog_static_fb_signal_combo = None
        analog_static_eol_msg_combo = None
        analog_static_eol_signal_combo = None
        tolerance_edit = None
        pre_dwell_time_edit = None
        dwell_time_edit = None
        analog_static_fb_msg_edit = None
        analog_static_fb_signal_edit = None
        analog_static_eol_msg_edit = None
        analog_static_eol_signal_edit = None
        tolerance_edit_fallback = None
        pre_dwell_time_edit_fallback = None
        dwell_time_edit_fallback = None
        
    # if a DBC is loaded, provide message+signal dropdowns
        if self.dbc_service is not None and self.dbc_service.is_loaded():
            # collect messages
            messages = list(getattr(self.dbc_service.database, 'messages', []))
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
            # Expected Gain input (optional, for calibration)
            expected_gain_validator = QtGui.QDoubleValidator(0.000001, 1000000.0, 6, self)
            expected_gain_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            expected_gain_edit = QtWidgets.QLineEdit()
            expected_gain_edit.setValidator(expected_gain_validator)
            expected_gain_edit.setPlaceholderText('Optional: for gain adjustment calculation')
            # Gain Tolerance input (optional, for pass/fail determination)
            gain_tolerance_validator = QtGui.QDoubleValidator(0.0, 1000.0, 2, self)
            gain_tolerance_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            gain_tolerance_edit = QtWidgets.QLineEdit()
            gain_tolerance_edit.setValidator(gain_tolerance_validator)
            gain_tolerance_edit.setPlaceholderText('Optional: % tolerance for gain error (e.g., 5.0)')
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
            analog_layout.addRow('Expected Gain (optional):', expected_gain_edit)
            
            # Phase Current Calibration fields (DBC-driven)
            # Command Message: dropdown of CAN Messages
            phase_current_cmd_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                phase_current_cmd_msg_combo.addItem(label, fid)
            
            # Trigger Test Signal: dropdown based on selected Command Message
            phase_current_trigger_signal_combo = QtWidgets.QComboBox()
            # Iq_ref Signal: dropdown based on selected Command Message
            phase_current_iq_ref_signal_combo = QtWidgets.QComboBox()
            # Id_ref Signal: dropdown based on selected Command Message
            phase_current_id_ref_signal_combo = QtWidgets.QComboBox()
            
            def _update_phase_current_cmd_signals(idx=0):
                """Update Trigger Test, Iq_ref, and Id_ref signal dropdowns based on selected Command Message."""
                phase_current_trigger_signal_combo.clear()
                phase_current_iq_ref_signal_combo.clear()
                phase_current_id_ref_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    phase_current_trigger_signal_combo.addItems(sigs)
                    phase_current_iq_ref_signal_combo.addItems(sigs)
                    phase_current_id_ref_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_phase_current_cmd_signals(0)
            phase_current_cmd_msg_combo.currentIndexChanged.connect(_update_phase_current_cmd_signals)
            
            # Phase Current Signal Source: dropdown of CAN Messages (for V and W signals)
            phase_current_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                phase_current_msg_combo.addItem(label, fid)
            
            # Phase Current V Signal: dropdown based on selected message
            phase_current_v_signal_combo = QtWidgets.QComboBox()
            # Phase Current W Signal: dropdown based on selected message
            phase_current_w_signal_combo = QtWidgets.QComboBox()
            
            def _update_phase_current_signals(idx=0):
                """Update both V and W signal dropdowns based on selected message."""
                phase_current_v_signal_combo.clear()
                phase_current_w_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    phase_current_v_signal_combo.addItems(sigs)
                    phase_current_w_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_phase_current_signals(0)
            phase_current_msg_combo.currentIndexChanged.connect(_update_phase_current_signals)
            
            # Numerical input fields for Iq values (in Amperes)
            iq_validator = QtGui.QDoubleValidator(-1000.0, 1000.0, 6, self)
            iq_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            
            min_iq_edit = QtWidgets.QLineEdit()
            min_iq_edit.setValidator(iq_validator)
            min_iq_edit.setPlaceholderText('e.g., -10.0')
            
            max_iq_edit = QtWidgets.QLineEdit()
            max_iq_edit.setValidator(iq_validator)
            max_iq_edit.setPlaceholderText('e.g., 10.0')
            
            step_iq_edit = QtWidgets.QLineEdit()
            step_iq_edit.setValidator(iq_validator)
            step_iq_edit.setPlaceholderText('e.g., 1.0')
            
            # IPC Test duration input field (in milliseconds)
            duration_validator = QtGui.QIntValidator(0, 60000, self)  # 0 to 60 seconds
            ipc_test_duration_edit = QtWidgets.QLineEdit()
            ipc_test_duration_edit.setValidator(duration_validator)
            ipc_test_duration_edit.setPlaceholderText('e.g., 1000')
            
            # Oscilloscope Channel dropdowns - populated from enabled channels in oscilloscope config
            osc_phase_v_ch_combo = QtWidgets.QComboBox()
            osc_phase_w_ch_combo = QtWidgets.QComboBox()
            
            def _update_osc_channel_dropdowns():
                """Update oscilloscope channel dropdowns with enabled channel names."""
                osc_phase_v_ch_combo.clear()
                osc_phase_w_ch_combo.clear()
                
                # Get enabled channel names from oscilloscope configuration
                enabled_channel_names = []
                if hasattr(self, '_oscilloscope_config') and self._oscilloscope_config:
                    channels = self._oscilloscope_config.get('channels', {})
                    for ch_key in ['CH1', 'CH2', 'CH3', 'CH4']:
                        if ch_key in channels:
                            ch_config = channels[ch_key]
                            if ch_config.get('enabled', False):
                                channel_name = ch_config.get('channel_name', '').strip()
                                if channel_name:
                                    enabled_channel_names.append(channel_name)
                
                # Populate both dropdowns with enabled channel names
                osc_phase_v_ch_combo.addItems(enabled_channel_names)
                osc_phase_w_ch_combo.addItems(enabled_channel_names)
            
            # Initialize dropdowns
            _update_osc_channel_dropdowns()
            
            # Populate phase current sub-widget
            phase_current_layout.addRow('Command Message:', phase_current_cmd_msg_combo)
            phase_current_layout.addRow('Trigger Test Signal:', phase_current_trigger_signal_combo)
            phase_current_layout.addRow('Iq_ref Signal:', phase_current_iq_ref_signal_combo)
            phase_current_layout.addRow('Id_ref Signal:', phase_current_id_ref_signal_combo)
            phase_current_layout.addRow('Phase Current Signal Source:', phase_current_msg_combo)
            phase_current_layout.addRow('Phase Current V Signal:', phase_current_v_signal_combo)
            phase_current_layout.addRow('Phase Current W Signal:', phase_current_w_signal_combo)
            phase_current_layout.addRow('Min Iq (A):', min_iq_edit)
            phase_current_layout.addRow('Max Iq (A):', max_iq_edit)
            phase_current_layout.addRow('Step Iq (A):', step_iq_edit)
            phase_current_layout.addRow('IPC Test Duration (ms):', ipc_test_duration_edit)
            phase_current_layout.addRow('Oscilloscope Phase V CH:', osc_phase_v_ch_combo)
            phase_current_layout.addRow('Oscilloscope Phase W CH:', osc_phase_w_ch_combo)
            
            # Analog Static Test fields (DBC mode)
            # Feedback Signal Source: dropdown of CAN Messages
            analog_static_fb_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                analog_static_fb_msg_combo.addItem(label, fid)
            
            # Feedback Signal: dropdown based on selected message
            analog_static_fb_signal_combo = QtWidgets.QComboBox()
            
            # EOL Signal Source: dropdown of CAN Messages
            analog_static_eol_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                analog_static_eol_msg_combo.addItem(label, fid)
            
            # EOL Signal: dropdown based on selected message
            analog_static_eol_signal_combo = QtWidgets.QComboBox()
            
            def _update_analog_static_fb_signals(idx=0):
                """Update feedback signal dropdown based on selected message."""
                analog_static_fb_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    analog_static_fb_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            def _update_analog_static_eol_signals(idx=0):
                """Update EOL signal dropdown based on selected message."""
                analog_static_eol_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    analog_static_eol_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_analog_static_fb_signals(0)
                _update_analog_static_eol_signals(0)
            analog_static_fb_msg_combo.currentIndexChanged.connect(_update_analog_static_fb_signals)
            analog_static_eol_msg_combo.currentIndexChanged.connect(_update_analog_static_eol_signals)
            
            # Tolerance input (float, in mV)
            tolerance_validator = QtGui.QDoubleValidator(0.0, 10000.0, 2, self)
            tolerance_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            tolerance_edit = QtWidgets.QLineEdit()
            tolerance_edit.setValidator(tolerance_validator)
            tolerance_edit.setPlaceholderText('e.g., 10.0')
            
            # Pre-dwell time input (int, in ms)
            pre_dwell_validator = QtGui.QIntValidator(0, 60000, self)
            pre_dwell_time_edit = QtWidgets.QLineEdit()
            pre_dwell_time_edit.setValidator(pre_dwell_validator)
            pre_dwell_time_edit.setPlaceholderText('e.g., 100')
            
            # Dwell time input (int, in ms)
            dwell_time_validator = QtGui.QIntValidator(1, 60000, self)
            dwell_time_edit = QtWidgets.QLineEdit()
            dwell_time_edit.setValidator(dwell_time_validator)
            dwell_time_edit.setPlaceholderText('e.g., 500')
            
            # Populate analog static sub-widget
            analog_static_layout.addRow('Feedback Signal Source:', analog_static_fb_msg_combo)
            analog_static_layout.addRow('Feedback Signal:', analog_static_fb_signal_combo)
            analog_static_layout.addRow('EOL Signal Source:', analog_static_eol_msg_combo)
            analog_static_layout.addRow('EOL Signal:', analog_static_eol_signal_combo)
            analog_static_layout.addRow('Tolerance (mV):', tolerance_edit)
            analog_static_layout.addRow('Pre-dwell Time (ms):', pre_dwell_time_edit)
            analog_static_layout.addRow('Dwell Time (ms):', dwell_time_edit)
            
            # Temperature Validation Test fields (DBC mode)
            # Feedback Signal Source: dropdown of CAN Messages
            temp_val_fb_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                temp_val_fb_msg_combo.addItem(label, fid)
            
            # Feedback Signal: dropdown based on selected message
            temp_val_fb_signal_combo = QtWidgets.QComboBox()
            
            def _update_temp_val_fb_signals(idx=0):
                """Update feedback signal dropdown based on selected message."""
                temp_val_fb_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    temp_val_fb_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_temp_val_fb_signals(0)
            temp_val_fb_msg_combo.currentIndexChanged.connect(_update_temp_val_fb_signals)
            
            # Reference temperature input (float, in °C)
            reference_validator = QtGui.QDoubleValidator(-273.15, 1000.0, 2, self)
            reference_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            temp_val_reference_edit = QtWidgets.QLineEdit()
            temp_val_reference_edit.setValidator(reference_validator)
            temp_val_reference_edit.setPlaceholderText('e.g., 25.0')
            
            # Tolerance input (float, in °C)
            temp_tolerance_validator = QtGui.QDoubleValidator(0.0, 1000.0, 2, self)
            temp_tolerance_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            temp_val_tolerance_edit = QtWidgets.QLineEdit()
            temp_val_tolerance_edit.setValidator(temp_tolerance_validator)
            temp_val_tolerance_edit.setPlaceholderText('e.g., 2.0')
            
            # Dwell time input (int, in ms)
            temp_dwell_time_validator = QtGui.QIntValidator(1, 60000, self)
            temp_val_dwell_time_edit = QtWidgets.QLineEdit()
            temp_val_dwell_time_edit.setValidator(temp_dwell_time_validator)
            temp_val_dwell_time_edit.setPlaceholderText('e.g., 1000')
            
            # Populate temperature validation sub-widget
            temperature_validation_layout.addRow('Feedback Signal Source:', temp_val_fb_msg_combo)
            temperature_validation_layout.addRow('Feedback Signal:', temp_val_fb_signal_combo)
            temperature_validation_layout.addRow('Reference Temperature (°C):', temp_val_reference_edit)
            temperature_validation_layout.addRow('Tolerance (°C):', temp_val_tolerance_edit)
            temperature_validation_layout.addRow('Dwell Time (ms):', temp_val_dwell_time_edit)
            
            # Analog PWM Sensor Test fields (DBC mode)
            # Feedback Signal Source: dropdown of CAN Messages
            analog_pwm_fb_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                analog_pwm_fb_msg_combo.addItem(label, fid)
            
            # PWM Frequency Signal: dropdown based on selected message
            analog_pwm_frequency_signal_combo = QtWidgets.QComboBox()
            # Duty Signal: dropdown based on selected message
            analog_pwm_duty_signal_combo = QtWidgets.QComboBox()
            
            def _update_analog_pwm_signals(idx=0):
                """Update both signal dropdowns based on selected message."""
                analog_pwm_frequency_signal_combo.clear()
                analog_pwm_duty_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    analog_pwm_frequency_signal_combo.addItems(sigs)
                    analog_pwm_duty_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_analog_pwm_signals(0)
            analog_pwm_fb_msg_combo.currentIndexChanged.connect(_update_analog_pwm_signals)
            
            # Reference PWM frequency input (float, in Hz)
            pwm_freq_reference_validator = QtGui.QDoubleValidator(0.0, 1000000.0, 2, self)
            pwm_freq_reference_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_reference_frequency_edit = QtWidgets.QLineEdit()
            analog_pwm_reference_frequency_edit.setValidator(pwm_freq_reference_validator)
            analog_pwm_reference_frequency_edit.setPlaceholderText('e.g., 1000.0')
            
            # Reference duty input (float, in %)
            duty_reference_validator = QtGui.QDoubleValidator(0.0, 100.0, 2, self)
            duty_reference_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_reference_duty_edit = QtWidgets.QLineEdit()
            analog_pwm_reference_duty_edit.setValidator(duty_reference_validator)
            analog_pwm_reference_duty_edit.setPlaceholderText('e.g., 50.0')
            
            # PWM frequency tolerance input (float, in Hz)
            pwm_freq_tolerance_validator = QtGui.QDoubleValidator(0.0, 1000000.0, 2, self)
            pwm_freq_tolerance_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_frequency_tolerance_edit = QtWidgets.QLineEdit()
            analog_pwm_frequency_tolerance_edit.setValidator(pwm_freq_tolerance_validator)
            analog_pwm_frequency_tolerance_edit.setPlaceholderText('e.g., 10.0')
            
            # Duty tolerance input (float, in %)
            duty_tolerance_validator = QtGui.QDoubleValidator(0.0, 100.0, 2, self)
            duty_tolerance_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_duty_tolerance_edit = QtWidgets.QLineEdit()
            analog_pwm_duty_tolerance_edit.setValidator(duty_tolerance_validator)
            analog_pwm_duty_tolerance_edit.setPlaceholderText('e.g., 1.0')
            
            # Acquisition time input (int, in ms)
            pwm_acquisition_time_validator = QtGui.QIntValidator(1, 60000, self)
            analog_pwm_acquisition_time_edit = QtWidgets.QLineEdit()
            analog_pwm_acquisition_time_edit.setValidator(pwm_acquisition_time_validator)
            analog_pwm_acquisition_time_edit.setPlaceholderText('e.g., 3000')
            
            # Populate Analog PWM Sensor sub-widget
            analog_pwm_sensor_layout.addRow('Feedback Signal Source:', analog_pwm_fb_msg_combo)
            analog_pwm_sensor_layout.addRow('PWM Frequency Signal:', analog_pwm_frequency_signal_combo)
            analog_pwm_sensor_layout.addRow('Duty Signal:', analog_pwm_duty_signal_combo)
            analog_pwm_sensor_layout.addRow('Reference PWM Frequency (Hz):', analog_pwm_reference_frequency_edit)
            analog_pwm_sensor_layout.addRow('Reference Duty (%):', analog_pwm_reference_duty_edit)
            analog_pwm_sensor_layout.addRow('PWM Frequency Tolerance (Hz):', analog_pwm_frequency_tolerance_edit)
            analog_pwm_sensor_layout.addRow('Duty Tolerance (%):', analog_pwm_duty_tolerance_edit)
            analog_pwm_sensor_layout.addRow('Acquisition Time (ms):', analog_pwm_acquisition_time_edit)
            
            # Fan Control Test fields (DBC mode)
            # Fan Test Trigger Source: dropdown of CAN Messages
            fan_control_trigger_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                fan_control_trigger_msg_combo.addItem(label, fid)
            
            # Fan Test Trigger Signal: dropdown based on selected message
            fan_control_trigger_signal_combo = QtWidgets.QComboBox()
            
            def _update_fan_control_trigger_signals(idx=0):
                """Update trigger signal dropdown based on selected message."""
                fan_control_trigger_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    fan_control_trigger_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_fan_control_trigger_signals(0)
            fan_control_trigger_msg_combo.currentIndexChanged.connect(_update_fan_control_trigger_signals)
            
            # Fan Control Feedback Source: dropdown of CAN Messages
            fan_control_feedback_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                fan_control_feedback_msg_combo.addItem(label, fid)
            
            # Fan Enabled Signal: dropdown based on selected message
            fan_control_enabled_signal_combo = QtWidgets.QComboBox()
            # Fan Tach Feedback Signal: dropdown based on selected message
            fan_control_tach_signal_combo = QtWidgets.QComboBox()
            # Fan Fault Feedback Signal: dropdown based on selected message
            fan_control_fault_signal_combo = QtWidgets.QComboBox()
            
            def _update_fan_control_feedback_signals(idx=0):
                """Update all feedback signal dropdowns based on selected message."""
                fan_control_enabled_signal_combo.clear()
                fan_control_tach_signal_combo.clear()
                fan_control_fault_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    fan_control_enabled_signal_combo.addItems(sigs)
                    fan_control_tach_signal_combo.addItems(sigs)
                    fan_control_fault_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_fan_control_feedback_signals(0)
            fan_control_feedback_msg_combo.currentIndexChanged.connect(_update_fan_control_feedback_signals)
            
            # Dwell time input (int, in ms)
            fan_dwell_time_validator = QtGui.QIntValidator(1, 60000, self)
            fan_control_dwell_time_edit = QtWidgets.QLineEdit()
            fan_control_dwell_time_edit.setValidator(fan_dwell_time_validator)
            fan_control_dwell_time_edit.setPlaceholderText('e.g., 1000')
            
            # Test timeout input (int, in ms)
            fan_timeout_validator = QtGui.QIntValidator(1, 60000, self)
            fan_control_timeout_edit = QtWidgets.QLineEdit()
            fan_control_timeout_edit.setValidator(fan_timeout_validator)
            fan_control_timeout_edit.setPlaceholderText('e.g., 5000')
            
            # Populate fan control sub-widget
            fan_control_layout.addRow('Fan Test Trigger Source:', fan_control_trigger_msg_combo)
            fan_control_layout.addRow('Fan Test Trigger Signal:', fan_control_trigger_signal_combo)
            fan_control_layout.addRow('Fan Control Feedback Source:', fan_control_feedback_msg_combo)
            fan_control_layout.addRow('Fan Enabled Signal:', fan_control_enabled_signal_combo)
            fan_control_layout.addRow('Fan Tach Feedback Signal:', fan_control_tach_signal_combo)
            fan_control_layout.addRow('Fan Fault Feedback Signal:', fan_control_fault_signal_combo)
            fan_control_layout.addRow('Dwell Time (ms):', fan_control_dwell_time_edit)
            fan_control_layout.addRow('Test Timeout (ms):', fan_control_timeout_edit)
            
            # External 5V Test fields (DBC mode)
            # Ext 5V Test Trigger Source: dropdown of CAN Messages
            ext_5v_test_trigger_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                ext_5v_test_trigger_msg_combo.addItem(label, fid)
            
            # Ext 5V Test Trigger Signal: dropdown based on selected message
            ext_5v_test_trigger_signal_combo = QtWidgets.QComboBox()
            
            def _update_ext_5v_test_trigger_signals(idx=0):
                """Update trigger signal dropdown based on selected message."""
                ext_5v_test_trigger_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    ext_5v_test_trigger_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_ext_5v_test_trigger_signals(0)
            ext_5v_test_trigger_msg_combo.currentIndexChanged.connect(_update_ext_5v_test_trigger_signals)
            
            # EOL Ext 5V Measurement Source: dropdown of CAN Messages
            ext_5v_test_eol_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                ext_5v_test_eol_msg_combo.addItem(label, fid)
            
            # EOL Ext 5V Measurement Signal: dropdown based on selected message
            ext_5v_test_eol_signal_combo = QtWidgets.QComboBox()
            
            def _update_ext_5v_test_eol_signals(idx=0):
                """Update EOL signal dropdown based on selected message."""
                ext_5v_test_eol_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    ext_5v_test_eol_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_ext_5v_test_eol_signals(0)
            ext_5v_test_eol_msg_combo.currentIndexChanged.connect(_update_ext_5v_test_eol_signals)
            
            # Feedback Signal Source: dropdown of CAN Messages
            ext_5v_test_feedback_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                ext_5v_test_feedback_msg_combo.addItem(label, fid)
            
            # Feedback Signal: dropdown based on selected message
            ext_5v_test_feedback_signal_combo = QtWidgets.QComboBox()
            
            def _update_ext_5v_test_feedback_signals(idx=0):
                """Update feedback signal dropdown based on selected message."""
                ext_5v_test_feedback_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    ext_5v_test_feedback_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_ext_5v_test_feedback_signals(0)
            ext_5v_test_feedback_msg_combo.currentIndexChanged.connect(_update_ext_5v_test_feedback_signals)
            
            # Tolerance input (float, in mV)
            ext_5v_tolerance_validator = QtGui.QDoubleValidator(0.0, 10000.0, 2, self)
            ext_5v_tolerance_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            ext_5v_test_tolerance_edit = QtWidgets.QLineEdit()
            ext_5v_test_tolerance_edit.setValidator(ext_5v_tolerance_validator)
            ext_5v_test_tolerance_edit.setPlaceholderText('e.g., 50.0')
            
            # Pre-dwell time input (int, in ms)
            ext_5v_pre_dwell_validator = QtGui.QIntValidator(0, 60000, self)
            ext_5v_test_pre_dwell_time_edit = QtWidgets.QLineEdit()
            ext_5v_test_pre_dwell_time_edit.setValidator(ext_5v_pre_dwell_validator)
            ext_5v_test_pre_dwell_time_edit.setPlaceholderText('e.g., 100')
            
            # Dwell time input (int, in ms)
            ext_5v_dwell_time_validator = QtGui.QIntValidator(1, 60000, self)
            ext_5v_test_dwell_time_edit = QtWidgets.QLineEdit()
            ext_5v_test_dwell_time_edit.setValidator(ext_5v_dwell_time_validator)
            ext_5v_test_dwell_time_edit.setPlaceholderText('e.g., 500')
            
            # Populate External 5V Test sub-widget
            ext_5v_test_layout.addRow('Ext 5V Test Trigger Source:', ext_5v_test_trigger_msg_combo)
            ext_5v_test_layout.addRow('Ext 5V Test Trigger Signal:', ext_5v_test_trigger_signal_combo)
            ext_5v_test_layout.addRow('EOL Ext 5V Measurement Source:', ext_5v_test_eol_msg_combo)
            ext_5v_test_layout.addRow('EOL Ext 5V Measurement Signal:', ext_5v_test_eol_signal_combo)
            ext_5v_test_layout.addRow('Feedback Signal Source:', ext_5v_test_feedback_msg_combo)
            ext_5v_test_layout.addRow('Feedback Signal:', ext_5v_test_feedback_signal_combo)
            ext_5v_test_layout.addRow('Tolerance (mV):', ext_5v_test_tolerance_edit)
            ext_5v_test_layout.addRow('Pre-dwell Time (ms):', ext_5v_test_pre_dwell_time_edit)
            ext_5v_test_layout.addRow('Dwell Time (ms):', ext_5v_test_dwell_time_edit)
            
            # DC Bus Sensing Test fields (DBC mode)
            dc_bus_sensing_widget = QtWidgets.QWidget()
            dc_bus_sensing_layout = QtWidgets.QFormLayout(dc_bus_sensing_widget)
            
            # Oscilloscope Channel: dropdown of enabled channel names from oscilloscope configuration
            dc_bus_osc_channel_combo = QtWidgets.QComboBox()
            # Populate from oscilloscope configuration
            if hasattr(self, '_oscilloscope_config') and self._oscilloscope_config:
                channel_names = self.oscilloscope_service.get_channel_names(self._oscilloscope_config) if self.oscilloscope_service else []
                dc_bus_osc_channel_combo.addItems(channel_names)
            else:
                dc_bus_osc_channel_combo.addItem('No oscilloscope config loaded', None)
            
            # Feedback Signal Source: dropdown of CAN Messages
            dc_bus_feedback_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                dc_bus_feedback_msg_combo.addItem(label, fid)
            
            # Feedback Signal: dropdown based on selected message
            dc_bus_feedback_signal_combo = QtWidgets.QComboBox()
            
            def _update_dc_bus_feedback_signals(idx=0):
                """Update feedback signal dropdown based on selected message."""
                dc_bus_feedback_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    dc_bus_feedback_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_dc_bus_feedback_signals(0)
            dc_bus_feedback_msg_combo.currentIndexChanged.connect(_update_dc_bus_feedback_signals)
            
            # Dwell time input (int, in ms)
            dc_bus_dwell_time_validator = QtGui.QIntValidator(1, 60000, self)
            dc_bus_dwell_time_edit = QtWidgets.QLineEdit()
            dc_bus_dwell_time_edit.setValidator(dc_bus_dwell_time_validator)
            dc_bus_dwell_time_edit.setPlaceholderText('e.g., 500')
            
            # Tolerance input (float, in V)
            dc_bus_tolerance_validator = QtGui.QDoubleValidator(0.0, 1000.0, 4, self)
            dc_bus_tolerance_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            dc_bus_tolerance_edit = QtWidgets.QLineEdit()
            dc_bus_tolerance_edit.setValidator(dc_bus_tolerance_validator)
            dc_bus_tolerance_edit.setPlaceholderText('e.g., 0.1')
            
            # Populate DC Bus Sensing Test sub-widget
            dc_bus_sensing_layout.addRow('Oscilloscope Channel:', dc_bus_osc_channel_combo)
            dc_bus_sensing_layout.addRow('Feedback Signal Source:', dc_bus_feedback_msg_combo)
            dc_bus_sensing_layout.addRow('Feedback Signal:', dc_bus_feedback_signal_combo)
            dc_bus_sensing_layout.addRow('Dwell Time (ms):', dc_bus_dwell_time_edit)
            dc_bus_sensing_layout.addRow('Tolerance (V):', dc_bus_tolerance_edit)
            
            # Output Current Calibration Test fields (DBC mode)
            output_current_calibration_widget = QtWidgets.QWidget()
            output_current_calibration_layout = QtWidgets.QFormLayout(output_current_calibration_widget)
            
            # Test Trigger Source: dropdown of CAN Messages
            output_current_trigger_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                output_current_trigger_msg_combo.addItem(label, fid)
            
            # Test Trigger Signal: dropdown based on selected message
            output_current_trigger_signal_combo = QtWidgets.QComboBox()
            
            def _update_output_current_trigger_signals(idx=0):
                """Update trigger signal dropdown based on selected message."""
                output_current_trigger_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    output_current_trigger_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_output_current_trigger_signals(0)
            output_current_trigger_msg_combo.currentIndexChanged.connect(_update_output_current_trigger_signals)
            
            # Test Trigger Signal Value: integer input (0-255)
            output_current_trigger_value_validator = QtGui.QIntValidator(0, 255, self)
            output_current_trigger_value_edit = QtWidgets.QLineEdit()
            output_current_trigger_value_edit.setValidator(output_current_trigger_value_validator)
            output_current_trigger_value_edit.setPlaceholderText('e.g., 1 (to enable)')
            
            # Current Setpoint Signal: dropdown based on same message as trigger
            output_current_setpoint_signal_combo = QtWidgets.QComboBox()
            
            def _update_output_current_setpoint_signals():
                """Update setpoint signal dropdown based on trigger message selection."""
                output_current_setpoint_signal_combo.clear()
                try:
                    idx = output_current_trigger_msg_combo.currentIndex()
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    output_current_setpoint_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_output_current_setpoint_signals()
            output_current_trigger_msg_combo.currentIndexChanged.connect(_update_output_current_setpoint_signals)
            
            # Output Current Trim Signal: dropdown based on same message as trigger
            output_current_trim_signal_combo = QtWidgets.QComboBox()
            
            def _update_output_current_trim_signals():
                """Update trim signal dropdown based on trigger message selection."""
                output_current_trim_signal_combo.clear()
                try:
                    idx = output_current_trigger_msg_combo.currentIndex()
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    output_current_trim_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_output_current_trim_signals()
            output_current_trigger_msg_combo.currentIndexChanged.connect(_update_output_current_trim_signals)
            
            # Initial Trim Value: double input (0.0000-200.0000, default 100.0000)
            output_current_initial_trim_validator = QtGui.QDoubleValidator(0.0, 200.0, 4, self)
            output_current_initial_trim_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            output_current_initial_trim_edit = QtWidgets.QLineEdit()
            output_current_initial_trim_edit.setValidator(output_current_initial_trim_validator)
            output_current_initial_trim_edit.setPlaceholderText('e.g., 100.0000')
            output_current_initial_trim_edit.setText('100.0000')
            
            # Feedback Signal Source: dropdown of CAN Messages
            output_current_feedback_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                output_current_feedback_msg_combo.addItem(label, fid)
            
            # Feedback Signal: dropdown based on selected message
            output_current_feedback_signal_combo = QtWidgets.QComboBox()
            
            def _update_output_current_feedback_signals(idx=0):
                """Update feedback signal dropdown based on selected message."""
                output_current_feedback_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    output_current_feedback_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_output_current_feedback_signals(0)
            output_current_feedback_msg_combo.currentIndexChanged.connect(_update_output_current_feedback_signals)
            
            # Oscilloscope Channel: dropdown of enabled channel names
            output_current_osc_channel_combo = QtWidgets.QComboBox()
            if hasattr(self, '_oscilloscope_config') and self._oscilloscope_config:
                channel_names = self.oscilloscope_service.get_channel_names(self._oscilloscope_config) if self.oscilloscope_service else []
                output_current_osc_channel_combo.addItems(channel_names)
            else:
                output_current_osc_channel_combo.addItem('No oscilloscope config loaded', None)
            
            # Oscilloscope Timebase: dropdown
            output_current_timebase_combo = QtWidgets.QComboBox()
            output_current_timebase_combo.addItems(['10MS', '20MS', '100MS', '500MS'])
            
            # Minimum Test Current: double input (>= 0, default 5.0)
            output_current_min_current_validator = QtGui.QDoubleValidator(0.0, 1000.0, 3, self)
            output_current_min_current_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            output_current_min_current_edit = QtWidgets.QLineEdit()
            output_current_min_current_edit.setValidator(output_current_min_current_validator)
            output_current_min_current_edit.setPlaceholderText('e.g., 5.0')
            output_current_min_current_edit.setText('5.0')
            
            # Maximum Test Current: double input (>= minimum, default 20.0)
            output_current_max_current_validator = QtGui.QDoubleValidator(0.0, 1000.0, 3, self)
            output_current_max_current_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            output_current_max_current_edit = QtWidgets.QLineEdit()
            output_current_max_current_edit.setValidator(output_current_max_current_validator)
            output_current_max_current_edit.setPlaceholderText('e.g., 20.0')
            output_current_max_current_edit.setText('20.0')
            
            # Step Current: double input (>= 0.1, default 5.0)
            output_current_step_current_validator = QtGui.QDoubleValidator(0.1, 1000.0, 3, self)
            output_current_step_current_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            output_current_step_current_edit = QtWidgets.QLineEdit()
            output_current_step_current_edit.setValidator(output_current_step_current_validator)
            output_current_step_current_edit.setPlaceholderText('e.g., 5.0')
            output_current_step_current_edit.setText('5.0')
            
            # Pre-Acquisition Time: integer input (>= 0, default 1000)
            output_current_pre_acq_validator = QtGui.QIntValidator(0, 60000, self)
            output_current_pre_acq_edit = QtWidgets.QLineEdit()
            output_current_pre_acq_edit.setValidator(output_current_pre_acq_validator)
            output_current_pre_acq_edit.setPlaceholderText('e.g., 1000')
            output_current_pre_acq_edit.setText('1000')
            
            # Acquisition Time: integer input (>= 1, default 3000)
            output_current_acq_validator = QtGui.QIntValidator(1, 60000, self)
            output_current_acq_edit = QtWidgets.QLineEdit()
            output_current_acq_edit.setValidator(output_current_acq_validator)
            output_current_acq_edit.setPlaceholderText('e.g., 3000')
            output_current_acq_edit.setText('3000')
            
            # Tolerance: double input (>= 0, default 1.0)
            output_current_tolerance_validator = QtGui.QDoubleValidator(0.0, 100.0, 3, self)
            output_current_tolerance_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            output_current_tolerance_edit = QtWidgets.QLineEdit()
            output_current_tolerance_edit.setValidator(output_current_tolerance_validator)
            output_current_tolerance_edit.setPlaceholderText('e.g., 1.0')
            output_current_tolerance_edit.setText('1.0')
            
            # Populate Output Current Calibration Test sub-widget
            output_current_calibration_layout.addRow('Test Trigger Source:', output_current_trigger_msg_combo)
            output_current_calibration_layout.addRow('Test Trigger Signal:', output_current_trigger_signal_combo)
            output_current_calibration_layout.addRow('Test Trigger Signal Value:', output_current_trigger_value_edit)
            output_current_calibration_layout.addRow('Current Setpoint Signal:', output_current_setpoint_signal_combo)
            output_current_calibration_layout.addRow('Output Current Trim Signal:', output_current_trim_signal_combo)
            output_current_calibration_layout.addRow('Initial Trim Value (%):', output_current_initial_trim_edit)
            output_current_calibration_layout.addRow('Feedback Signal Source:', output_current_feedback_msg_combo)
            output_current_calibration_layout.addRow('Feedback Signal:', output_current_feedback_signal_combo)
            output_current_calibration_layout.addRow('Oscilloscope Channel:', output_current_osc_channel_combo)
            output_current_calibration_layout.addRow('Oscilloscope Timebase:', output_current_timebase_combo)
            output_current_calibration_layout.addRow('Minimum Test Current (A):', output_current_min_current_edit)
            output_current_calibration_layout.addRow('Maximum Test Current (A):', output_current_max_current_edit)
            output_current_calibration_layout.addRow('Step Current (A):', output_current_step_current_edit)
            output_current_calibration_layout.addRow('Pre-Acquisition Time (ms):', output_current_pre_acq_edit)
            output_current_calibration_layout.addRow('Acquisition Time (ms):', output_current_acq_edit)
            output_current_calibration_layout.addRow('Tolerance (%):', output_current_tolerance_edit)
            
            # Charged HV Bus Test fields (DBC mode)
            charged_hv_bus_widget = QtWidgets.QWidget()
            charged_hv_bus_layout = QtWidgets.QFormLayout(charged_hv_bus_widget)
            
            # Command Signal Source: dropdown of CAN Messages
            charged_hv_bus_cmd_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                charged_hv_bus_cmd_msg_combo.addItem(label, fid)
            
            # Test Trigger Signal: dropdown based on selected message
            charged_hv_bus_trigger_signal_combo = QtWidgets.QComboBox()
            
            def _update_charged_hv_bus_trigger_signals(idx=0):
                """Update trigger signal dropdown based on selected message."""
                charged_hv_bus_trigger_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    charged_hv_bus_trigger_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_charged_hv_bus_trigger_signals(0)
            charged_hv_bus_cmd_msg_combo.currentIndexChanged.connect(_update_charged_hv_bus_trigger_signals)
            
            # Test Trigger Signal Value: integer input (0-255)
            charged_hv_bus_trigger_value_validator = QtGui.QIntValidator(0, 255, self)
            charged_hv_bus_trigger_value_edit = QtWidgets.QLineEdit()
            charged_hv_bus_trigger_value_edit.setValidator(charged_hv_bus_trigger_value_validator)
            charged_hv_bus_trigger_value_edit.setPlaceholderText('e.g., 1')
            
            # Set Output Current Trim Value Signal: dropdown based on command message
            charged_hv_bus_trim_signal_combo = QtWidgets.QComboBox()
            
            def _update_charged_hv_bus_trim_signals():
                """Update trim signal dropdown based on command message selection."""
                charged_hv_bus_trim_signal_combo.clear()
                try:
                    idx = charged_hv_bus_cmd_msg_combo.currentIndex()
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    charged_hv_bus_trim_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_charged_hv_bus_trim_signals()
            charged_hv_bus_cmd_msg_combo.currentIndexChanged.connect(_update_charged_hv_bus_trim_signals)
            
            # Fallback Output Current Trim Value: double input (0-200)
            charged_hv_bus_fallback_trim_validator = QtGui.QDoubleValidator(0.0, 200.0, 2, self)
            charged_hv_bus_fallback_trim_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            charged_hv_bus_fallback_trim_edit = QtWidgets.QLineEdit()
            charged_hv_bus_fallback_trim_edit.setValidator(charged_hv_bus_fallback_trim_validator)
            charged_hv_bus_fallback_trim_edit.setPlaceholderText('e.g., 100.0')
            charged_hv_bus_fallback_trim_edit.setText('100.0')
            
            # Set Output Current Setpoint Signal: dropdown based on command message
            charged_hv_bus_setpoint_signal_combo = QtWidgets.QComboBox()
            
            def _update_charged_hv_bus_setpoint_signals():
                """Update setpoint signal dropdown based on command message selection."""
                charged_hv_bus_setpoint_signal_combo.clear()
                try:
                    idx = charged_hv_bus_cmd_msg_combo.currentIndex()
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    charged_hv_bus_setpoint_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_charged_hv_bus_setpoint_signals()
            charged_hv_bus_cmd_msg_combo.currentIndexChanged.connect(_update_charged_hv_bus_setpoint_signals)
            
            # Output Test Current: double input (0-40)
            charged_hv_bus_output_current_validator = QtGui.QDoubleValidator(0.0, 40.0, 3, self)
            charged_hv_bus_output_current_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            charged_hv_bus_output_current_edit = QtWidgets.QLineEdit()
            charged_hv_bus_output_current_edit.setValidator(charged_hv_bus_output_current_validator)
            charged_hv_bus_output_current_edit.setPlaceholderText('e.g., 10.0')
            charged_hv_bus_output_current_edit.setText('10.0')
            
            # Feedback Signal Source: dropdown of CAN Messages
            charged_hv_bus_feedback_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                charged_hv_bus_feedback_msg_combo.addItem(label, fid)
            
            # DUT Test State Signal: dropdown based on selected message
            charged_hv_bus_dut_state_signal_combo = QtWidgets.QComboBox()
            # Enable Relay Signal: dropdown based on selected message
            charged_hv_bus_enable_relay_signal_combo = QtWidgets.QComboBox()
            # Enable PFC Signal: dropdown based on selected message
            charged_hv_bus_enable_pfc_signal_combo = QtWidgets.QComboBox()
            # PFC Power Good Signal: dropdown based on selected message
            charged_hv_bus_pfc_power_good_signal_combo = QtWidgets.QComboBox()
            # PCMC Signal: dropdown based on selected message
            charged_hv_bus_pcmc_signal_combo = QtWidgets.QComboBox()
            # PSFB Fault Signal: dropdown based on selected message
            charged_hv_bus_psfb_fault_signal_combo = QtWidgets.QComboBox()
            
            def _update_charged_hv_bus_feedback_signals(idx=0):
                """Update all feedback signal dropdowns based on selected message."""
                charged_hv_bus_dut_state_signal_combo.clear()
                charged_hv_bus_enable_relay_signal_combo.clear()
                charged_hv_bus_enable_pfc_signal_combo.clear()
                charged_hv_bus_pfc_power_good_signal_combo.clear()
                charged_hv_bus_pcmc_signal_combo.clear()
                charged_hv_bus_psfb_fault_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    charged_hv_bus_dut_state_signal_combo.addItems(sigs)
                    charged_hv_bus_enable_relay_signal_combo.addItems(sigs)
                    charged_hv_bus_enable_pfc_signal_combo.addItems(sigs)
                    charged_hv_bus_pfc_power_good_signal_combo.addItems(sigs)
                    charged_hv_bus_pcmc_signal_combo.addItems(sigs)
                    charged_hv_bus_psfb_fault_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_charged_hv_bus_feedback_signals(0)
            charged_hv_bus_feedback_msg_combo.currentIndexChanged.connect(_update_charged_hv_bus_feedback_signals)
            
            # Test Time: integer input (>= 1000)
            charged_hv_bus_test_time_validator = QtGui.QIntValidator(1000, 600000, self)
            charged_hv_bus_test_time_edit = QtWidgets.QLineEdit()
            charged_hv_bus_test_time_edit.setValidator(charged_hv_bus_test_time_validator)
            charged_hv_bus_test_time_edit.setPlaceholderText('e.g., 30000')
            charged_hv_bus_test_time_edit.setText('30000')
            
            # Populate Charged HV Bus Test sub-widget
            charged_hv_bus_layout.addRow('Command Signal Source:', charged_hv_bus_cmd_msg_combo)
            charged_hv_bus_layout.addRow('Test Trigger Signal:', charged_hv_bus_trigger_signal_combo)
            charged_hv_bus_layout.addRow('Test Trigger Signal Value:', charged_hv_bus_trigger_value_edit)
            charged_hv_bus_layout.addRow('Set Output Current Trim Value Signal:', charged_hv_bus_trim_signal_combo)
            charged_hv_bus_layout.addRow('Fallback Output Current Trim Value (%):', charged_hv_bus_fallback_trim_edit)
            charged_hv_bus_layout.addRow('Set Output Current Setpoint Signal:', charged_hv_bus_setpoint_signal_combo)
            charged_hv_bus_layout.addRow('Output Test Current (A):', charged_hv_bus_output_current_edit)
            charged_hv_bus_layout.addRow('Feedback Signal Source:', charged_hv_bus_feedback_msg_combo)
            charged_hv_bus_layout.addRow('DUT Test State Signal:', charged_hv_bus_dut_state_signal_combo)
            charged_hv_bus_layout.addRow('Enable Relay Signal:', charged_hv_bus_enable_relay_signal_combo)
            charged_hv_bus_layout.addRow('Enable PFC Signal:', charged_hv_bus_enable_pfc_signal_combo)
            charged_hv_bus_layout.addRow('PFC Power Good Signal:', charged_hv_bus_pfc_power_good_signal_combo)
            charged_hv_bus_layout.addRow('PCMC Signal:', charged_hv_bus_pcmc_signal_combo)
            charged_hv_bus_layout.addRow('PSFB Fault Signal:', charged_hv_bus_psfb_fault_signal_combo)
            charged_hv_bus_layout.addRow('Test Time (ms):', charged_hv_bus_test_time_edit)
            
            # Charger Functional Test fields (DBC mode)
            charger_functional_widget = QtWidgets.QWidget()
            charger_functional_layout = QtWidgets.QFormLayout(charger_functional_widget)
            
            # Command Signal Source: dropdown of CAN Messages
            charger_functional_cmd_msg_combo = QtWidgets.QComboBox()
            charger_functional_cmd_msg_combo.setEditable(False)
            if self.dbc_service is not None and self.dbc_service.is_loaded():
                db = self.dbc_service.database
                if db:
                    for msg in db.messages:
                        charger_functional_cmd_msg_combo.addItem(f"{msg.name} (0x{msg.frame_id:X})", msg.frame_id)
            
            # Test Trigger Signal: dropdown based on Command Signal Source
            charger_functional_trigger_signal_combo = QtWidgets.QComboBox()
            charger_functional_trigger_signal_combo.setEditable(False)
            
            def _update_charger_functional_trigger_signals():
                charger_functional_trigger_signal_combo.clear()
                try:
                    msg_id = charger_functional_cmd_msg_combo.currentData()
                    if msg_id is not None and self.dbc_service is not None:
                        msg = self.dbc_service.find_message_by_id(msg_id)
                        if msg:
                            for sig in msg.signals:
                                charger_functional_trigger_signal_combo.addItem(sig.name)
                except Exception:
                    pass
            
            charger_functional_cmd_msg_combo.currentIndexChanged.connect(_update_charger_functional_trigger_signals)
            _update_charger_functional_trigger_signals()
            
            # Test Trigger Signal Value (int, 0-255)
            charger_functional_trigger_value_validator = QtGui.QIntValidator(0, 255, self)
            charger_functional_trigger_value_edit = QtWidgets.QLineEdit()
            charger_functional_trigger_value_edit.setValidator(charger_functional_trigger_value_validator)
            charger_functional_trigger_value_edit.setPlaceholderText('e.g., 1')
            charger_functional_trigger_value_edit.setText('1')
            
            # Set Output Current Trim Value Signal: dropdown based on Command Signal Source
            charger_functional_trim_signal_combo = QtWidgets.QComboBox()
            charger_functional_trim_signal_combo.setEditable(False)
            
            def _update_charger_functional_trim_signals():
                charger_functional_trim_signal_combo.clear()
                try:
                    msg_id = charger_functional_cmd_msg_combo.currentData()
                    if msg_id is not None and self.dbc_service is not None:
                        msg = self.dbc_service.find_message_by_id(msg_id)
                        if msg:
                            for sig in msg.signals:
                                charger_functional_trim_signal_combo.addItem(sig.name)
                except Exception:
                    pass
            
            charger_functional_cmd_msg_combo.currentIndexChanged.connect(_update_charger_functional_trim_signals)
            _update_charger_functional_trim_signals()
            
            # Fallback Output Current Trim Value (float, 0-200)
            charger_functional_fallback_trim_validator = QtGui.QDoubleValidator(0.0, 200.0, 2, self)
            charger_functional_fallback_trim_edit = QtWidgets.QLineEdit()
            charger_functional_fallback_trim_edit.setValidator(charger_functional_fallback_trim_validator)
            charger_functional_fallback_trim_edit.setPlaceholderText('e.g., 100.0')
            charger_functional_fallback_trim_edit.setText('100.0')
            
            # Set Output Current Setpoint Signal: dropdown based on Command Signal Source
            charger_functional_setpoint_signal_combo = QtWidgets.QComboBox()
            charger_functional_setpoint_signal_combo.setEditable(False)
            
            def _update_charger_functional_setpoint_signals():
                charger_functional_setpoint_signal_combo.clear()
                try:
                    msg_id = charger_functional_cmd_msg_combo.currentData()
                    if msg_id is not None and self.dbc_service is not None:
                        msg = self.dbc_service.find_message_by_id(msg_id)
                        if msg:
                            for sig in msg.signals:
                                charger_functional_setpoint_signal_combo.addItem(sig.name)
                except Exception:
                    pass
            
            charger_functional_cmd_msg_combo.currentIndexChanged.connect(_update_charger_functional_setpoint_signals)
            _update_charger_functional_setpoint_signals()
            
            # Output Test Current (float, 0-40)
            charger_functional_output_current_validator = QtGui.QDoubleValidator(0.0, 40.0, 2, self)
            charger_functional_output_current_edit = QtWidgets.QLineEdit()
            charger_functional_output_current_edit.setValidator(charger_functional_output_current_validator)
            charger_functional_output_current_edit.setPlaceholderText('e.g., 10.0')
            charger_functional_output_current_edit.setText('10.0')
            
            # Feedback Signal Source: dropdown of CAN Messages
            charger_functional_feedback_msg_combo = QtWidgets.QComboBox()
            charger_functional_feedback_msg_combo.setEditable(False)
            if self.dbc_service is not None and self.dbc_service.is_loaded():
                db = self.dbc_service.database
                if db:
                    for msg in db.messages:
                        charger_functional_feedback_msg_combo.addItem(f"{msg.name} (0x{msg.frame_id:X})", msg.frame_id)
            
            # DUT Test State Signal: dropdown based on Feedback Signal Source
            charger_functional_dut_state_signal_combo = QtWidgets.QComboBox()
            charger_functional_dut_state_signal_combo.setEditable(False)
            
            def _update_charger_functional_dut_state_signals():
                charger_functional_dut_state_signal_combo.clear()
                try:
                    msg_id = charger_functional_feedback_msg_combo.currentData()
                    if msg_id is not None and self.dbc_service is not None:
                        msg = self.dbc_service.find_message_by_id(msg_id)
                        if msg:
                            for sig in msg.signals:
                                charger_functional_dut_state_signal_combo.addItem(sig.name)
                except Exception:
                    pass
            
            charger_functional_feedback_msg_combo.currentIndexChanged.connect(_update_charger_functional_dut_state_signals)
            _update_charger_functional_dut_state_signals()
            
            # Enable Relay Signal: dropdown based on Feedback Signal Source
            charger_functional_enable_relay_signal_combo = QtWidgets.QComboBox()
            charger_functional_enable_relay_signal_combo.setEditable(False)
            
            def _update_charger_functional_enable_relay_signals():
                charger_functional_enable_relay_signal_combo.clear()
                try:
                    msg_id = charger_functional_feedback_msg_combo.currentData()
                    if msg_id is not None and self.dbc_service is not None:
                        msg = self.dbc_service.find_message_by_id(msg_id)
                        if msg:
                            for sig in msg.signals:
                                charger_functional_enable_relay_signal_combo.addItem(sig.name)
                except Exception:
                    pass
            
            charger_functional_feedback_msg_combo.currentIndexChanged.connect(_update_charger_functional_enable_relay_signals)
            _update_charger_functional_enable_relay_signals()
            
            # Enable PFC Signal: dropdown based on Feedback Signal Source
            charger_functional_enable_pfc_signal_combo = QtWidgets.QComboBox()
            charger_functional_enable_pfc_signal_combo.setEditable(False)
            
            def _update_charger_functional_enable_pfc_signals():
                charger_functional_enable_pfc_signal_combo.clear()
                try:
                    msg_id = charger_functional_feedback_msg_combo.currentData()
                    if msg_id is not None and self.dbc_service is not None:
                        msg = self.dbc_service.find_message_by_id(msg_id)
                        if msg:
                            for sig in msg.signals:
                                charger_functional_enable_pfc_signal_combo.addItem(sig.name)
                except Exception:
                    pass
            
            charger_functional_feedback_msg_combo.currentIndexChanged.connect(_update_charger_functional_enable_pfc_signals)
            _update_charger_functional_enable_pfc_signals()
            
            # PFC Power Good Signal: dropdown based on Feedback Signal Source
            charger_functional_pfc_power_good_signal_combo = QtWidgets.QComboBox()
            charger_functional_pfc_power_good_signal_combo.setEditable(False)
            
            def _update_charger_functional_pfc_power_good_signals():
                charger_functional_pfc_power_good_signal_combo.clear()
                try:
                    msg_id = charger_functional_feedback_msg_combo.currentData()
                    if msg_id is not None and self.dbc_service is not None:
                        msg = self.dbc_service.find_message_by_id(msg_id)
                        if msg:
                            for sig in msg.signals:
                                charger_functional_pfc_power_good_signal_combo.addItem(sig.name)
                except Exception:
                    pass
            
            charger_functional_feedback_msg_combo.currentIndexChanged.connect(_update_charger_functional_pfc_power_good_signals)
            _update_charger_functional_pfc_power_good_signals()
            
            # PCMC Signal: dropdown based on Feedback Signal Source
            charger_functional_pcmc_signal_combo = QtWidgets.QComboBox()
            charger_functional_pcmc_signal_combo.setEditable(False)
            
            def _update_charger_functional_pcmc_signals():
                charger_functional_pcmc_signal_combo.clear()
                try:
                    msg_id = charger_functional_feedback_msg_combo.currentData()
                    if msg_id is not None and self.dbc_service is not None:
                        msg = self.dbc_service.find_message_by_id(msg_id)
                        if msg:
                            for sig in msg.signals:
                                charger_functional_pcmc_signal_combo.addItem(sig.name)
                except Exception:
                    pass
            
            charger_functional_feedback_msg_combo.currentIndexChanged.connect(_update_charger_functional_pcmc_signals)
            _update_charger_functional_pcmc_signals()
            
            # Output Current Signal: dropdown based on Feedback Signal Source
            charger_functional_output_current_signal_combo = QtWidgets.QComboBox()
            charger_functional_output_current_signal_combo.setEditable(False)
            
            def _update_charger_functional_output_current_signals():
                charger_functional_output_current_signal_combo.clear()
                try:
                    msg_id = charger_functional_feedback_msg_combo.currentData()
                    if msg_id is not None and self.dbc_service is not None:
                        msg = self.dbc_service.find_message_by_id(msg_id)
                        if msg:
                            for sig in msg.signals:
                                charger_functional_output_current_signal_combo.addItem(sig.name)
                except Exception:
                    pass
            
            charger_functional_feedback_msg_combo.currentIndexChanged.connect(_update_charger_functional_output_current_signals)
            _update_charger_functional_output_current_signals()
            
            # PSFB Fault Signal: dropdown based on Feedback Signal Source
            charger_functional_psfb_fault_signal_combo = QtWidgets.QComboBox()
            charger_functional_psfb_fault_signal_combo.setEditable(False)
            
            def _update_charger_functional_psfb_fault_signals():
                charger_functional_psfb_fault_signal_combo.clear()
                try:
                    msg_id = charger_functional_feedback_msg_combo.currentData()
                    if msg_id is not None and self.dbc_service is not None:
                        msg = self.dbc_service.find_message_by_id(msg_id)
                        if msg:
                            for sig in msg.signals:
                                charger_functional_psfb_fault_signal_combo.addItem(sig.name)
                except Exception:
                    pass
            
            charger_functional_feedback_msg_combo.currentIndexChanged.connect(_update_charger_functional_psfb_fault_signals)
            _update_charger_functional_psfb_fault_signals()
            
            # Output Current Tolerance (float, >= 0)
            charger_functional_output_current_tolerance_validator = QtGui.QDoubleValidator(0.0, 999.0, 2, self)
            charger_functional_output_current_tolerance_edit = QtWidgets.QLineEdit()
            charger_functional_output_current_tolerance_edit.setValidator(charger_functional_output_current_tolerance_validator)
            charger_functional_output_current_tolerance_edit.setPlaceholderText('e.g., 0.5')
            charger_functional_output_current_tolerance_edit.setText('0.5')
            
            # Test Time (int, >= 1000)
            charger_functional_test_time_validator = QtGui.QIntValidator(1000, 600000, self)
            charger_functional_test_time_edit = QtWidgets.QLineEdit()
            charger_functional_test_time_edit.setValidator(charger_functional_test_time_validator)
            charger_functional_test_time_edit.setPlaceholderText('e.g., 30000')
            charger_functional_test_time_edit.setText('30000')
            
            # Populate Charger Functional Test sub-widget
            charger_functional_layout.addRow('Command Signal Source:', charger_functional_cmd_msg_combo)
            charger_functional_layout.addRow('Test Trigger Signal:', charger_functional_trigger_signal_combo)
            charger_functional_layout.addRow('Test Trigger Signal Value:', charger_functional_trigger_value_edit)
            charger_functional_layout.addRow('Set Output Current Trim Value Signal:', charger_functional_trim_signal_combo)
            charger_functional_layout.addRow('Fallback Output Current Trim Value (%):', charger_functional_fallback_trim_edit)
            charger_functional_layout.addRow('Set Output Current Setpoint Signal:', charger_functional_setpoint_signal_combo)
            charger_functional_layout.addRow('Output Test Current (A):', charger_functional_output_current_edit)
            charger_functional_layout.addRow('Feedback Signal Source:', charger_functional_feedback_msg_combo)
            charger_functional_layout.addRow('DUT Test State Signal:', charger_functional_dut_state_signal_combo)
            charger_functional_layout.addRow('Enable Relay Signal:', charger_functional_enable_relay_signal_combo)
            charger_functional_layout.addRow('Enable PFC Signal:', charger_functional_enable_pfc_signal_combo)
            charger_functional_layout.addRow('PFC Power Good Signal:', charger_functional_pfc_power_good_signal_combo)
            charger_functional_layout.addRow('PCMC Signal:', charger_functional_pcmc_signal_combo)
            charger_functional_layout.addRow('Output Current Signal:', charger_functional_output_current_signal_combo)
            charger_functional_layout.addRow('PSFB Fault Signal:', charger_functional_psfb_fault_signal_combo)
            charger_functional_layout.addRow('Output Current Tolerance (A):', charger_functional_output_current_tolerance_edit)
            charger_functional_layout.addRow('Test Time (ms):', charger_functional_test_time_edit)
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
            # Create widgets for analog test parameters (with validators)
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
            # populate sub-widgets
            digital_layout.addRow('Command Message:', dig_can)
            digital_layout.addRow('Actuation Signal:', dig_signal)
            digital_layout.addRow('Value - Low:', dig_value_low)
            digital_layout.addRow('Value - High:', dig_value_high)
            digital_layout.addRow('Dwell Time (ms):', dig_dwell_ms)
            # fallback analog fields when no DBC
            analog_layout.addRow('MUX Channel:', mux_chan)
            analog_layout.addRow('DAC CAN ID:', dac_can)
            analog_layout.addRow('DAC Command Signal:', dac_cmd)
            analog_layout.addRow('DAC Min Output (mV):', dac_min_mv)
            analog_layout.addRow('DAC Max Output (mV):', dac_max_mv)
            analog_layout.addRow('Step Change (mV):', dac_step_mv)
            analog_layout.addRow('Dwell Time (ms):', dac_dwell_ms)
            
            # Phase Current Calibration fields (fallback when no DBC)
            phase_current_cmd_msg_edit = QtWidgets.QLineEdit()
            phase_current_trigger_signal_edit = QtWidgets.QLineEdit()
            phase_current_iq_ref_signal_edit = QtWidgets.QLineEdit()
            phase_current_id_ref_signal_edit = QtWidgets.QLineEdit()
            phase_current_msg_edit = QtWidgets.QLineEdit()
            phase_current_v_signal_edit = QtWidgets.QLineEdit()
            phase_current_w_signal_edit = QtWidgets.QLineEdit()
            
            # Numerical input fields for Iq values (in Amperes)
            iq_validator = QtGui.QDoubleValidator(-1000.0, 1000.0, 6, self)
            iq_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            
            min_iq_edit = QtWidgets.QLineEdit()
            min_iq_edit.setValidator(iq_validator)
            min_iq_edit.setPlaceholderText('e.g., -10.0')
            
            max_iq_edit = QtWidgets.QLineEdit()
            max_iq_edit.setValidator(iq_validator)
            max_iq_edit.setPlaceholderText('e.g., 10.0')
            
            step_iq_edit = QtWidgets.QLineEdit()
            step_iq_edit.setValidator(iq_validator)
            step_iq_edit.setPlaceholderText('e.g., 1.0')
            
            # IPC Test duration input field (in milliseconds)
            duration_validator = QtGui.QIntValidator(0, 60000, self)  # 0 to 60 seconds
            ipc_test_duration_edit = QtWidgets.QLineEdit()
            ipc_test_duration_edit.setValidator(duration_validator)
            ipc_test_duration_edit.setPlaceholderText('e.g., 1000')
            
            # Oscilloscope Channel dropdowns - populated from enabled channels in oscilloscope config
            osc_phase_v_ch_combo = QtWidgets.QComboBox()
            osc_phase_w_ch_combo = QtWidgets.QComboBox()
            
            def _update_osc_channel_dropdowns():
                """Update oscilloscope channel dropdowns with enabled channel names."""
                osc_phase_v_ch_combo.clear()
                osc_phase_w_ch_combo.clear()
                
                # Get enabled channel names from oscilloscope configuration
                enabled_channel_names = []
                if hasattr(self, '_oscilloscope_config') and self._oscilloscope_config:
                    channels = self._oscilloscope_config.get('channels', {})
                    for ch_key in ['CH1', 'CH2', 'CH3', 'CH4']:
                        if ch_key in channels:
                            ch_config = channels[ch_key]
                            if ch_config.get('enabled', False):
                                channel_name = ch_config.get('channel_name', '').strip()
                                if channel_name:
                                    enabled_channel_names.append(channel_name)
                
                # Populate both dropdowns with enabled channel names
                osc_phase_v_ch_combo.addItems(enabled_channel_names)
                osc_phase_w_ch_combo.addItems(enabled_channel_names)
            
            # Initialize dropdowns
            _update_osc_channel_dropdowns()
            
            # Analog Static Test fields (fallback when no DBC)
            analog_static_fb_msg_edit = QtWidgets.QLineEdit()
            analog_static_fb_signal_edit = QtWidgets.QLineEdit()
            analog_static_eol_msg_edit = QtWidgets.QLineEdit()
            analog_static_eol_signal_edit = QtWidgets.QLineEdit()
            
            # Tolerance input (float, in mV)
            tolerance_validator_fallback = QtGui.QDoubleValidator(0.0, 10000.0, 2, self)
            tolerance_validator_fallback.setNotation(QtGui.QDoubleValidator.StandardNotation)
            tolerance_edit_fallback = QtWidgets.QLineEdit()
            tolerance_edit_fallback.setValidator(tolerance_validator_fallback)
            tolerance_edit_fallback.setPlaceholderText('e.g., 10.0')
            
            # Pre-dwell time input (int, in ms)
            pre_dwell_validator_fallback = QtGui.QIntValidator(0, 60000, self)
            pre_dwell_time_edit_fallback = QtWidgets.QLineEdit()
            pre_dwell_time_edit_fallback.setValidator(pre_dwell_validator_fallback)
            pre_dwell_time_edit_fallback.setPlaceholderText('e.g., 100')
            
            # Dwell time input (int, in ms)
            dwell_time_validator_fallback = QtGui.QIntValidator(1, 60000, self)
            dwell_time_edit_fallback = QtWidgets.QLineEdit()
            dwell_time_edit_fallback.setValidator(dwell_time_validator_fallback)
            dwell_time_edit_fallback.setPlaceholderText('e.g., 500')
            
            # Populate analog static sub-widget (fallback)
            analog_static_layout.addRow('Feedback Signal Source (CAN ID):', analog_static_fb_msg_edit)
            analog_static_layout.addRow('Feedback Signal:', analog_static_fb_signal_edit)
            analog_static_layout.addRow('EOL Signal Source (CAN ID):', analog_static_eol_msg_edit)
            analog_static_layout.addRow('EOL Signal:', analog_static_eol_signal_edit)
            analog_static_layout.addRow('Tolerance (mV):', tolerance_edit_fallback)
            analog_static_layout.addRow('Pre-dwell Time (ms):', pre_dwell_time_edit_fallback)
            analog_static_layout.addRow('Dwell Time (ms):', dwell_time_edit_fallback)
            
            # Temperature Validation Test fields (fallback when no DBC)
            temp_val_fb_msg_edit = QtWidgets.QLineEdit()
            temp_val_fb_signal_edit = QtWidgets.QLineEdit()
            
            # Reference temperature input (float, in °C)
            reference_validator_fallback = QtGui.QDoubleValidator(-273.15, 1000.0, 2, self)
            reference_validator_fallback.setNotation(QtGui.QDoubleValidator.StandardNotation)
            temp_val_reference_edit_fallback = QtWidgets.QLineEdit()
            temp_val_reference_edit_fallback.setValidator(reference_validator_fallback)
            temp_val_reference_edit_fallback.setPlaceholderText('e.g., 25.0')
            
            # Tolerance input (float, in °C)
            temp_tolerance_validator_fallback = QtGui.QDoubleValidator(0.0, 1000.0, 2, self)
            temp_tolerance_validator_fallback.setNotation(QtGui.QDoubleValidator.StandardNotation)
            temp_val_tolerance_edit_fallback = QtWidgets.QLineEdit()
            temp_val_tolerance_edit_fallback.setValidator(temp_tolerance_validator_fallback)
            temp_val_tolerance_edit_fallback.setPlaceholderText('e.g., 2.0')
            
            # Dwell time input (int, in ms)
            temp_dwell_time_validator_fallback = QtGui.QIntValidator(1, 60000, self)
            temp_val_dwell_time_edit_fallback = QtWidgets.QLineEdit()
            temp_val_dwell_time_edit_fallback.setValidator(temp_dwell_time_validator_fallback)
            temp_val_dwell_time_edit_fallback.setPlaceholderText('e.g., 1000')
            
            # Populate temperature validation sub-widget (fallback)
            temperature_validation_layout.addRow('Feedback Signal Source (CAN ID):', temp_val_fb_msg_edit)
            temperature_validation_layout.addRow('Feedback Signal:', temp_val_fb_signal_edit)
            temperature_validation_layout.addRow('Reference Temperature (°C):', temp_val_reference_edit_fallback)
            temperature_validation_layout.addRow('Tolerance (°C):', temp_val_tolerance_edit_fallback)
            temperature_validation_layout.addRow('Dwell Time (ms):', temp_val_dwell_time_edit_fallback)
            
            # Analog PWM Sensor Test fields (fallback when no DBC)
            analog_pwm_fb_msg_edit = QtWidgets.QLineEdit()
            analog_pwm_frequency_signal_edit = QtWidgets.QLineEdit()
            analog_pwm_duty_signal_edit = QtWidgets.QLineEdit()
            
            # Reference PWM frequency input (float, in Hz)
            pwm_freq_reference_validator_fallback = QtGui.QDoubleValidator(0.0, 1000000.0, 2, self)
            pwm_freq_reference_validator_fallback.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_reference_frequency_edit_fallback = QtWidgets.QLineEdit()
            analog_pwm_reference_frequency_edit_fallback.setValidator(pwm_freq_reference_validator_fallback)
            analog_pwm_reference_frequency_edit_fallback.setPlaceholderText('e.g., 1000.0')
            
            # Reference duty input (float, in %)
            duty_reference_validator_fallback = QtGui.QDoubleValidator(0.0, 100.0, 2, self)
            duty_reference_validator_fallback.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_reference_duty_edit_fallback = QtWidgets.QLineEdit()
            analog_pwm_reference_duty_edit_fallback.setValidator(duty_reference_validator_fallback)
            analog_pwm_reference_duty_edit_fallback.setPlaceholderText('e.g., 50.0')
            
            # PWM frequency tolerance input (float, in Hz)
            pwm_freq_tolerance_validator_fallback = QtGui.QDoubleValidator(0.0, 1000000.0, 2, self)
            pwm_freq_tolerance_validator_fallback.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_frequency_tolerance_edit_fallback = QtWidgets.QLineEdit()
            analog_pwm_frequency_tolerance_edit_fallback.setValidator(pwm_freq_tolerance_validator_fallback)
            analog_pwm_frequency_tolerance_edit_fallback.setPlaceholderText('e.g., 10.0')
            
            # Duty tolerance input (float, in %)
            duty_tolerance_validator_fallback = QtGui.QDoubleValidator(0.0, 100.0, 2, self)
            duty_tolerance_validator_fallback.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_duty_tolerance_edit_fallback = QtWidgets.QLineEdit()
            analog_pwm_duty_tolerance_edit_fallback.setValidator(duty_tolerance_validator_fallback)
            analog_pwm_duty_tolerance_edit_fallback.setPlaceholderText('e.g., 1.0')
            
            # Acquisition time input (int, in ms)
            pwm_acquisition_time_validator_fallback = QtGui.QIntValidator(1, 60000, self)
            analog_pwm_acquisition_time_edit_fallback = QtWidgets.QLineEdit()
            analog_pwm_acquisition_time_edit_fallback.setValidator(pwm_acquisition_time_validator_fallback)
            analog_pwm_acquisition_time_edit_fallback.setPlaceholderText('e.g., 3000')
            
            # Populate Analog PWM Sensor sub-widget (fallback)
            analog_pwm_sensor_layout.addRow('Feedback Signal Source (CAN ID):', analog_pwm_fb_msg_edit)
            analog_pwm_sensor_layout.addRow('PWM Frequency Signal:', analog_pwm_frequency_signal_edit)
            analog_pwm_sensor_layout.addRow('Duty Signal:', analog_pwm_duty_signal_edit)
            analog_pwm_sensor_layout.addRow('Reference PWM Frequency (Hz):', analog_pwm_reference_frequency_edit_fallback)
            analog_pwm_sensor_layout.addRow('Reference Duty (%):', analog_pwm_reference_duty_edit_fallback)
            analog_pwm_sensor_layout.addRow('PWM Frequency Tolerance (Hz):', analog_pwm_frequency_tolerance_edit_fallback)
            analog_pwm_sensor_layout.addRow('Duty Tolerance (%):', analog_pwm_duty_tolerance_edit_fallback)
            analog_pwm_sensor_layout.addRow('Acquisition Time (ms):', analog_pwm_acquisition_time_edit_fallback)
            
            # Fan Control Test fields (fallback when no DBC)
            fan_control_trigger_msg_edit = QtWidgets.QLineEdit()
            fan_control_trigger_signal_edit = QtWidgets.QLineEdit()
            fan_control_feedback_msg_edit = QtWidgets.QLineEdit()
            fan_control_enabled_signal_edit = QtWidgets.QLineEdit()
            fan_control_tach_signal_edit = QtWidgets.QLineEdit()
            fan_control_fault_signal_edit = QtWidgets.QLineEdit()
            
            # Dwell time input (int, in ms)
            fan_dwell_time_validator_fallback = QtGui.QIntValidator(1, 60000, self)
            fan_control_dwell_time_edit_fallback = QtWidgets.QLineEdit()
            fan_control_dwell_time_edit_fallback.setValidator(fan_dwell_time_validator_fallback)
            fan_control_dwell_time_edit_fallback.setPlaceholderText('e.g., 1000')
            
            # Test timeout input (int, in ms)
            fan_timeout_validator_fallback = QtGui.QIntValidator(1, 60000, self)
            fan_control_timeout_edit_fallback = QtWidgets.QLineEdit()
            fan_control_timeout_edit_fallback.setValidator(fan_timeout_validator_fallback)
            fan_control_timeout_edit_fallback.setPlaceholderText('e.g., 5000')
            
            # Populate fan control sub-widget (fallback)
            fan_control_layout.addRow('Fan Test Trigger Source (CAN ID):', fan_control_trigger_msg_edit)
            fan_control_layout.addRow('Fan Test Trigger Signal:', fan_control_trigger_signal_edit)
            fan_control_layout.addRow('Fan Control Feedback Source (CAN ID):', fan_control_feedback_msg_edit)
            fan_control_layout.addRow('Fan Enabled Signal:', fan_control_enabled_signal_edit)
            fan_control_layout.addRow('Fan Tach Feedback Signal:', fan_control_tach_signal_edit)
            fan_control_layout.addRow('Fan Fault Feedback Signal:', fan_control_fault_signal_edit)
            fan_control_layout.addRow('Dwell Time (ms):', fan_control_dwell_time_edit_fallback)
            fan_control_layout.addRow('Test Timeout (ms):', fan_control_timeout_edit_fallback)
            
            # External 5V Test fields (fallback when no DBC)
            ext_5v_test_trigger_msg_edit = QtWidgets.QLineEdit()
            ext_5v_test_trigger_signal_edit = QtWidgets.QLineEdit()
            ext_5v_test_eol_msg_edit = QtWidgets.QLineEdit()
            ext_5v_test_eol_signal_edit = QtWidgets.QLineEdit()
            ext_5v_test_feedback_msg_edit = QtWidgets.QLineEdit()
            ext_5v_test_feedback_signal_edit = QtWidgets.QLineEdit()
            
            # Tolerance input (float, in mV)
            ext_5v_tolerance_validator_fallback = QtGui.QDoubleValidator(0.0, 10000.0, 2, self)
            ext_5v_tolerance_validator_fallback.setNotation(QtGui.QDoubleValidator.StandardNotation)
            ext_5v_test_tolerance_edit_fallback = QtWidgets.QLineEdit()
            ext_5v_test_tolerance_edit_fallback.setValidator(ext_5v_tolerance_validator_fallback)
            ext_5v_test_tolerance_edit_fallback.setPlaceholderText('e.g., 50.0')
            
            # Pre-dwell time input (int, in ms)
            ext_5v_pre_dwell_validator_fallback = QtGui.QIntValidator(0, 60000, self)
            ext_5v_test_pre_dwell_time_edit_fallback = QtWidgets.QLineEdit()
            ext_5v_test_pre_dwell_time_edit_fallback.setValidator(ext_5v_pre_dwell_validator_fallback)
            ext_5v_test_pre_dwell_time_edit_fallback.setPlaceholderText('e.g., 100')
            
            # Dwell time input (int, in ms)
            ext_5v_dwell_time_validator_fallback = QtGui.QIntValidator(1, 60000, self)
            ext_5v_test_dwell_time_edit_fallback = QtWidgets.QLineEdit()
            ext_5v_test_dwell_time_edit_fallback.setValidator(ext_5v_dwell_time_validator_fallback)
            ext_5v_test_dwell_time_edit_fallback.setPlaceholderText('e.g., 500')
            
            # Populate External 5V Test sub-widget (fallback)
            ext_5v_test_layout.addRow('Ext 5V Test Trigger Source (CAN ID):', ext_5v_test_trigger_msg_edit)
            ext_5v_test_layout.addRow('Ext 5V Test Trigger Signal:', ext_5v_test_trigger_signal_edit)
            ext_5v_test_layout.addRow('EOL Ext 5V Measurement Source (CAN ID):', ext_5v_test_eol_msg_edit)
            ext_5v_test_layout.addRow('EOL Ext 5V Measurement Signal:', ext_5v_test_eol_signal_edit)
            ext_5v_test_layout.addRow('Feedback Signal Source (CAN ID):', ext_5v_test_feedback_msg_edit)
            ext_5v_test_layout.addRow('Feedback Signal:', ext_5v_test_feedback_signal_edit)
            ext_5v_test_layout.addRow('Tolerance (mV):', ext_5v_test_tolerance_edit_fallback)
            ext_5v_test_layout.addRow('Pre-dwell Time (ms):', ext_5v_test_pre_dwell_time_edit_fallback)
            ext_5v_test_layout.addRow('Dwell Time (ms):', ext_5v_test_dwell_time_edit_fallback)
            
            phase_current_layout.addRow('Command Message (CAN ID):', phase_current_cmd_msg_edit)
            phase_current_layout.addRow('Trigger Test Signal:', phase_current_trigger_signal_edit)
            phase_current_layout.addRow('Iq_ref Signal:', phase_current_iq_ref_signal_edit)
            phase_current_layout.addRow('Id_ref Signal:', phase_current_id_ref_signal_edit)
            phase_current_layout.addRow('Phase Current Signal Source (CAN ID):', phase_current_msg_edit)
            phase_current_layout.addRow('Phase Current V Signal:', phase_current_v_signal_edit)
            phase_current_layout.addRow('Phase Current W Signal:', phase_current_w_signal_edit)
            phase_current_layout.addRow('Min Iq (A):', min_iq_edit)
            phase_current_layout.addRow('Max Iq (A):', max_iq_edit)
            phase_current_layout.addRow('Step Iq (A):', step_iq_edit)
            phase_current_layout.addRow('IPC Test Duration (ms):', ipc_test_duration_edit)
            phase_current_layout.addRow('Oscilloscope Phase V CH:', osc_phase_v_ch_combo)
            phase_current_layout.addRow('Oscilloscope Phase W CH:', osc_phase_w_ch_combo)

        form.addRow('Name:', name_edit)
        form.addRow('Type:', type_combo)
        # Test Mode field (0-3, default 0)
        test_mode_spin = QtWidgets.QSpinBox()
        test_mode_spin.setRange(0, 3)
        test_mode_spin.setValue(0)
        test_mode_spin.setToolTip('DUT must be in this test mode before test execution (0-3)')
        form.addRow('Test Mode:', test_mode_spin)
        # Feedback source and signal (DBC-driven when available)
        if self.dbc_service is not None and self.dbc_service.is_loaded():
            # build feedback message combo and signal combo
            fb_messages = list(getattr(self.dbc_service.database, 'messages', []))
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
            # Create labels and store references for showing/hiding
            fb_msg_label = QtWidgets.QLabel('Feedback Signal Source:')
            fb_signal_label = QtWidgets.QLabel('Feedback Signal:')
            form.addRow(fb_msg_label, fb_msg_combo)
            form.addRow(fb_signal_label, fb_signal_combo)
        else:
            feedback_edit_label = QtWidgets.QLabel('Feedback Signal (free-text):')
            form.addRow(feedback_edit_label, feedback_edit)
            # For non-DBC case, store reference to feedback_edit
            fb_msg_label = None
            fb_msg_field = None
            fb_signal_label = None
            fb_signal_field = None
        v.addLayout(form)
        # add sub-widgets to stacked widget - each test type gets its own page
        # Create mapping of test type to index
        test_type_to_index = {}
        test_type_to_index['Digital Logic Test'] = act_stacked.addWidget(digital_widget)
        test_type_to_index['Analog Sweep Test'] = act_stacked.addWidget(analog_widget)
        test_type_to_index['Phase Current Test'] = act_stacked.addWidget(phase_current_widget)
        test_type_to_index['Analog Static Test'] = act_stacked.addWidget(analog_static_widget)
        test_type_to_index['Analog PWM Sensor'] = act_stacked.addWidget(analog_pwm_sensor_widget)
        test_type_to_index['Temperature Validation Test'] = act_stacked.addWidget(temperature_validation_widget)
        test_type_to_index['Fan Control Test'] = act_stacked.addWidget(fan_control_widget)
        test_type_to_index['External 5V Test'] = act_stacked.addWidget(ext_5v_test_widget)
        test_type_to_index['DC Bus Sensing'] = act_stacked.addWidget(dc_bus_sensing_widget)
        if self.dbc_service is not None and self.dbc_service.is_loaded():
            test_type_to_index['Output Current Calibration'] = act_stacked.addWidget(output_current_calibration_widget)
            test_type_to_index['Charged HV Bus Test'] = act_stacked.addWidget(charged_hv_bus_widget)
            test_type_to_index['Charger Functional Test'] = act_stacked.addWidget(charger_functional_widget)
        
        v.addWidget(QtWidgets.QLabel('Test Configuration:'))
        v.addWidget(act_stacked)

        def _on_type_change(txt: str):
            try:
                # Switch to the appropriate page in the stacked widget
                if txt in test_type_to_index:
                    act_stacked.setCurrentIndex(test_type_to_index[txt])
                
                # Handle feedback fields visibility based on test type
                if txt in ('Digital Logic Test', 'Analog Sweep Test'):
                    # Show feedback fields for digital and analog
                    if fb_msg_label is not None:
                        fb_msg_label.show()
                        fb_msg_combo.show()
                        fb_signal_label.show()
                        fb_signal_combo.show()
                    elif feedback_edit_label is not None:
                        feedback_edit_label.show()
                        feedback_edit.show()
                elif txt in ('Phase Current Test', 'Analog Static Test', 'Analog PWM Sensor', 'Temperature Validation Test', 'Fan Control Test', 'External 5V Test', 'DC Bus Sensing', 'Output Current Calibration', 'Charged HV Bus Test', 'Charger Functional Test'):
                    # Hide feedback fields (these test types use their own fields)
                    if fb_msg_label is not None:
                        fb_msg_label.hide()
                        fb_msg_combo.hide()
                        fb_signal_label.hide()
                        fb_signal_combo.hide()
                    elif feedback_edit_label is not None:
                        feedback_edit_label.hide()
                        feedback_edit.hide()
            except Exception:
                pass
        # initialize visibility
        _on_type_change(type_combo.currentText())
        type_combo.currentTextChanged.connect(_on_type_change)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        v.addWidget(btns)

        def on_accept():
            nm = name_edit.text().strip() or f"test-{len(self._tests)+1}"
            # Validate name is not empty and unique
            if not nm or not nm.strip():
                QtWidgets.QMessageBox.warning(dlg, 'Invalid Name', 'Test name cannot be empty')
                return
            if not self._is_test_name_unique(nm):
                QtWidgets.QMessageBox.warning(dlg, 'Duplicate Name', f'A test with name "{nm}" already exists. Please choose a different name.')
                return
            
            t = type_combo.currentText()
            feedback = feedback_edit.text().strip()
            # build actuation dict depending on type
            if self.dbc_service is not None and self.dbc_service.is_loaded():
                if t == 'Digital Logic Test':
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
                        'type':'Digital Logic Test',
                        'can_id': can_id,
                        'signal': sig,
                        'value_low': low,
                        'value_high': high,
                        'dwell_ms': dig_dwell,
                    }
                elif t == 'Analog Sweep Test':
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
                    # Read expected gain (optional float)
                    expected_gain_val = None
                    try:
                        expected_gain_text = expected_gain_edit.text().strip() if hasattr(expected_gain_edit, 'text') else ''
                        if expected_gain_text:
                            expected_gain_val = float(expected_gain_text)
                    except (ValueError, TypeError):
                        pass
                    # Read gain tolerance (optional float)
                    gain_tolerance_val = None
                    try:
                        gain_tolerance_text = gain_tolerance_edit.text().strip() if hasattr(gain_tolerance_edit, 'text') else ''
                        if gain_tolerance_text:
                            gain_tolerance_val = float(gain_tolerance_text)
                            if gain_tolerance_val < 0:
                                raise ValueError("Gain tolerance cannot be negative")
                    except (ValueError, TypeError):
                        pass
                    act = {
                        'type': 'Analog Sweep Test',
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
                    if expected_gain_val is not None:
                        act['expected_gain'] = expected_gain_val
                    if gain_tolerance_val is not None:
                        act['gain_tolerance_percent'] = gain_tolerance_val
                elif t == 'Phase Current Test':
                    # Phase Current Calibration: read all fields
                    # Command Message and related signals
                    try:
                        cmd_msg_id = phase_current_cmd_msg_combo.currentData()
                    except Exception:
                        cmd_msg_id = None
                    trigger_test_sig = phase_current_trigger_signal_combo.currentText().strip() if phase_current_trigger_signal_combo.count() else ''
                    iq_ref_sig = phase_current_iq_ref_signal_combo.currentText().strip() if phase_current_iq_ref_signal_combo.count() else ''
                    id_ref_sig = phase_current_id_ref_signal_combo.currentText().strip() if phase_current_id_ref_signal_combo.count() else ''
                    
                    # Phase Current Signal Source and V/W signals
                    try:
                        phase_current_can_id = phase_current_msg_combo.currentData()
                    except Exception:
                        phase_current_can_id = None
                    phase_current_v_sig = phase_current_v_signal_combo.currentText().strip() if phase_current_v_signal_combo.count() else ''
                    phase_current_w_sig = phase_current_w_signal_combo.currentText().strip() if phase_current_w_signal_combo.count() else ''
                    
                    # Iq values (convert to float)
                    def _to_float_or_none(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    min_iq = _to_float_or_none(min_iq_edit)
                    max_iq = _to_float_or_none(max_iq_edit)
                    step_iq = _to_float_or_none(step_iq_edit)
                    
                    # IPC Test duration (convert to int)
                    def _to_int_or_none_duration(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    ipc_test_duration = _to_int_or_none_duration(ipc_test_duration_edit)
                    
                    # Oscilloscope channel selections
                    osc_phase_v_ch = osc_phase_v_ch_combo.currentText().strip() if osc_phase_v_ch_combo.count() else ''
                    osc_phase_w_ch = osc_phase_w_ch_combo.currentText().strip() if osc_phase_w_ch_combo.count() else ''
                    
                    act = {
                        'type': 'Phase Current Test',
                        'command_message': cmd_msg_id,
                        'trigger_test_signal': trigger_test_sig,
                        'iq_ref_signal': iq_ref_sig,
                        'id_ref_signal': id_ref_sig,
                        'phase_current_signal_source': phase_current_can_id,
                        'phase_current_v_signal': phase_current_v_sig,
                        'phase_current_w_signal': phase_current_w_sig,
                        'min_iq': min_iq,
                        'max_iq': max_iq,
                        'step_iq': step_iq,
                        'ipc_test_duration_ms': ipc_test_duration,
                        'oscilloscope_phase_v_ch': osc_phase_v_ch,
                        'oscilloscope_phase_w_ch': osc_phase_w_ch,
                    }
                elif t == 'Analog Static Test':
                    # Analog Static Test: read all fields (DBC mode)
                    try:
                        fb_msg_id = analog_static_fb_msg_combo.currentData()
                    except Exception:
                        fb_msg_id = None
                    fb_signal = analog_static_fb_signal_combo.currentText().strip() if analog_static_fb_signal_combo.count() else ''
                    
                    try:
                        eol_msg_id = analog_static_eol_msg_combo.currentData()
                    except Exception:
                        eol_msg_id = None
                    eol_signal = analog_static_eol_signal_combo.currentText().strip() if analog_static_eol_signal_combo.count() else ''
                    
                    # Tolerance (float)
                    def _to_float_or_none_tolerance(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_val = _to_float_or_none_tolerance(tolerance_edit)
                    
                    # Pre-dwell and dwell times (int)
                    def _to_int_or_none_time(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    pre_dwell_val = _to_int_or_none_time(pre_dwell_time_edit)
                    dwell_time_val = _to_int_or_none_time(dwell_time_edit)
                    
                    act = {
                        'type': 'Analog Static Test',
                        'feedback_signal_source': fb_msg_id,
                        'feedback_signal': fb_signal,
                        'eol_signal_source': eol_msg_id,
                        'eol_signal': eol_signal,
                        'tolerance_mv': tolerance_val,
                        'pre_dwell_time_ms': pre_dwell_val,
                        'dwell_time_ms': dwell_time_val,
                    }
                elif t == 'Temperature Validation Test':
                    # Temperature Validation Test: read all fields (DBC mode)
                    try:
                        fb_msg_id = temp_val_fb_msg_combo.currentData()
                    except Exception:
                        fb_msg_id = None
                    fb_signal = temp_val_fb_signal_combo.currentText().strip() if temp_val_fb_signal_combo.count() else ''
                    
                    # Reference temperature (float)
                    def _to_float_or_none_reference(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    reference_temp_val = _to_float_or_none_reference(temp_val_reference_edit)
                    
                    # Tolerance (float)
                    def _to_float_or_none_temp_tolerance(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_c_val = _to_float_or_none_temp_tolerance(temp_val_tolerance_edit)
                    
                    # Dwell time (int)
                    def _to_int_or_none_dwell(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dwell_time_val = _to_int_or_none_dwell(temp_val_dwell_time_edit)
                    
                    act = {
                        'type': 'Temperature Validation Test',
                        'feedback_signal_source': fb_msg_id,
                        'feedback_signal': fb_signal,
                        'reference_temperature_c': reference_temp_val,
                        'tolerance_c': tolerance_c_val,
                        'dwell_time_ms': dwell_time_val,
                    }
                elif t == 'Analog PWM Sensor':
                    # Analog PWM Sensor Test: read all fields (DBC mode)
                    try:
                        fb_msg_id = analog_pwm_fb_msg_combo.currentData()
                    except Exception:
                        fb_msg_id = None
                    pwm_frequency_signal = analog_pwm_frequency_signal_combo.currentText().strip() if analog_pwm_frequency_signal_combo.count() else ''
                    duty_signal = analog_pwm_duty_signal_combo.currentText().strip() if analog_pwm_duty_signal_combo.count() else ''
                    
                    # Reference PWM frequency (float)
                    def _to_float_or_none_pwm_freq_reference(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    reference_pwm_freq_val = _to_float_or_none_pwm_freq_reference(analog_pwm_reference_frequency_edit)
                    
                    # Reference duty (float)
                    def _to_float_or_none_duty_reference(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    reference_duty_val = _to_float_or_none_duty_reference(analog_pwm_reference_duty_edit)
                    
                    # PWM frequency tolerance (float)
                    def _to_float_or_none_pwm_freq_tolerance(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    pwm_freq_tolerance_val = _to_float_or_none_pwm_freq_tolerance(analog_pwm_frequency_tolerance_edit)
                    
                    # Duty tolerance (float)
                    def _to_float_or_none_duty_tolerance(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    duty_tolerance_val = _to_float_or_none_duty_tolerance(analog_pwm_duty_tolerance_edit)
                    
                    # Acquisition time (int)
                    def _to_int_or_none_acquisition(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    acquisition_time_val = _to_int_or_none_acquisition(analog_pwm_acquisition_time_edit)
                    
                    act = {
                        'type': 'Analog PWM Sensor',
                        'feedback_signal_source': fb_msg_id,
                        'feedback_pwm_frequency_signal': pwm_frequency_signal,
                        'feedback_duty_signal': duty_signal,
                        'reference_pwm_frequency': reference_pwm_freq_val,
                        'reference_duty': reference_duty_val,
                        'pwm_frequency_tolerance': pwm_freq_tolerance_val,
                        'duty_tolerance': duty_tolerance_val,
                        'acquisition_time_ms': acquisition_time_val,
                    }
                elif t == 'Fan Control Test':
                    # Fan Control Test: read all fields (DBC mode)
                    try:
                        trigger_msg_id = fan_control_trigger_msg_combo.currentData()
                    except Exception:
                        trigger_msg_id = None
                    trigger_signal = fan_control_trigger_signal_combo.currentText().strip() if fan_control_trigger_signal_combo.count() else ''
                    
                    try:
                        feedback_msg_id = fan_control_feedback_msg_combo.currentData()
                    except Exception:
                        feedback_msg_id = None
                    fan_enabled_signal = fan_control_enabled_signal_combo.currentText().strip() if fan_control_enabled_signal_combo.count() else ''
                    fan_tach_signal = fan_control_tach_signal_combo.currentText().strip() if fan_control_tach_signal_combo.count() else ''
                    fan_fault_signal = fan_control_fault_signal_combo.currentText().strip() if fan_control_fault_signal_combo.count() else ''
                    
                    # Dwell time (int)
                    def _to_int_or_none_fan_dwell(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dwell_time_val = _to_int_or_none_fan_dwell(fan_control_dwell_time_edit)
                    
                    # Test timeout (int)
                    def _to_int_or_none_fan_timeout(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    timeout_val = _to_int_or_none_fan_timeout(fan_control_timeout_edit)
                    
                    act = {
                        'type': 'Fan Control Test',
                        'fan_test_trigger_source': trigger_msg_id,
                        'fan_test_trigger_signal': trigger_signal,
                        'fan_control_feedback_source': feedback_msg_id,
                        'fan_enabled_signal': fan_enabled_signal,
                        'fan_tach_feedback_signal': fan_tach_signal,
                        'fan_fault_feedback_signal': fan_fault_signal,
                        'dwell_time_ms': dwell_time_val,
                        'test_timeout_ms': timeout_val,
                    }
                elif t == 'External 5V Test':
                    # External 5V Test: read all fields (DBC mode)
                    try:
                        trigger_msg_id = ext_5v_test_trigger_msg_combo.currentData()
                    except Exception:
                        trigger_msg_id = None
                    trigger_signal = ext_5v_test_trigger_signal_combo.currentText().strip() if ext_5v_test_trigger_signal_combo.count() else ''
                    
                    try:
                        eol_msg_id = ext_5v_test_eol_msg_combo.currentData()
                    except Exception:
                        eol_msg_id = None
                    eol_signal = ext_5v_test_eol_signal_combo.currentText().strip() if ext_5v_test_eol_signal_combo.count() else ''
                    
                    try:
                        feedback_msg_id = ext_5v_test_feedback_msg_combo.currentData()
                    except Exception:
                        feedback_msg_id = None
                    feedback_signal = ext_5v_test_feedback_signal_combo.currentText().strip() if ext_5v_test_feedback_signal_combo.count() else ''
                    
                    # Tolerance (float)
                    def _to_float_or_none_ext5v_tolerance(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_val = _to_float_or_none_ext5v_tolerance(ext_5v_test_tolerance_edit)
                    
                    # Pre-dwell and dwell times (int)
                    def _to_int_or_none_ext5v_time(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    pre_dwell_val = _to_int_or_none_ext5v_time(ext_5v_test_pre_dwell_time_edit)
                    dwell_time_val = _to_int_or_none_ext5v_time(ext_5v_test_dwell_time_edit)
                    
                    act = {
                        'type': 'External 5V Test',
                        'ext_5v_test_trigger_source': trigger_msg_id,
                        'ext_5v_test_trigger_signal': trigger_signal,
                        'eol_ext_5v_measurement_source': eol_msg_id,
                        'eol_ext_5v_measurement_signal': eol_signal,
                        'feedback_signal_source': feedback_msg_id,
                        'feedback_signal': feedback_signal,
                        'tolerance_mv': tolerance_val,
                        'pre_dwell_time_ms': pre_dwell_val,
                        'dwell_time_ms': dwell_time_val,
                    }
                elif t == 'DC Bus Sensing':
                    # DC Bus Sensing: read all fields (DBC mode)
                    osc_channel = dc_bus_osc_channel_combo.currentText().strip() if dc_bus_osc_channel_combo.count() else ''
                    
                    try:
                        feedback_msg_id = dc_bus_feedback_msg_combo.currentData()
                    except Exception:
                        feedback_msg_id = None
                    feedback_signal = dc_bus_feedback_signal_combo.currentText().strip() if dc_bus_feedback_signal_combo.count() else ''
                    
                    # Dwell time (int)
                    def _to_int_or_none_dc_bus_dwell(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dwell_time_val = _to_int_or_none_dc_bus_dwell(dc_bus_dwell_time_edit)
                    
                    # Tolerance (float, in V)
                    def _to_float_or_none_dc_bus_tolerance(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_val = _to_float_or_none_dc_bus_tolerance(dc_bus_tolerance_edit)
                    
                    act = {
                        'type': 'DC Bus Sensing',
                        'oscilloscope_channel': osc_channel,
                        'feedback_signal_source': feedback_msg_id,
                        'feedback_signal': feedback_signal,
                        'dwell_time_ms': dwell_time_val,
                        'tolerance_v': tolerance_val,
                    }
                elif t == 'Output Current Calibration':
                    # Output Current Calibration: read all fields (DBC mode)
                    try:
                        trigger_msg_id = output_current_trigger_msg_combo.currentData()
                    except Exception:
                        trigger_msg_id = None
                    trigger_signal = output_current_trigger_signal_combo.currentText().strip() if output_current_trigger_signal_combo.count() else ''
                    
                    # Test Trigger Signal Value (int, 0-255)
                    def _to_int_or_none_output_current_trigger_value(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    trigger_value = _to_int_or_none_output_current_trigger_value(output_current_trigger_value_edit)
                    
                    setpoint_signal = output_current_setpoint_signal_combo.currentText().strip() if output_current_setpoint_signal_combo.count() else ''
                    
                    trim_signal = output_current_trim_signal_combo.currentText().strip() if output_current_trim_signal_combo.count() else ''
                    
                    # Initial Trim Value (float, 0.0000-200.0000)
                    def _to_float_or_none_output_current_initial_trim(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    initial_trim_value = _to_float_or_none_output_current_initial_trim(output_current_initial_trim_edit)
                    
                    try:
                        feedback_msg_id = output_current_feedback_msg_combo.currentData()
                    except Exception:
                        feedback_msg_id = None
                    feedback_signal = output_current_feedback_signal_combo.currentText().strip() if output_current_feedback_signal_combo.count() else ''
                    
                    osc_channel = output_current_osc_channel_combo.currentText().strip() if output_current_osc_channel_combo.count() else ''
                    timebase = output_current_timebase_combo.currentText().strip() if output_current_timebase_combo.count() else ''
                    
                    # Minimum Test Current (float)
                    def _to_float_or_none_output_current_min(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    min_current = _to_float_or_none_output_current_min(output_current_min_current_edit)
                    
                    # Maximum Test Current (float)
                    def _to_float_or_none_output_current_max(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    max_current = _to_float_or_none_output_current_max(output_current_max_current_edit)
                    
                    # Step Current (float)
                    def _to_float_or_none_output_current_step(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    step_current = _to_float_or_none_output_current_step(output_current_step_current_edit)
                    
                    # Pre-Acquisition Time (int)
                    def _to_int_or_none_output_current_pre_acq(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    pre_acq_time = _to_int_or_none_output_current_pre_acq(output_current_pre_acq_edit)
                    
                    # Acquisition Time (int)
                    def _to_int_or_none_output_current_acq(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    acq_time = _to_int_or_none_output_current_acq(output_current_acq_edit)
                    
                    # Tolerance (float, in %)
                    def _to_float_or_none_output_current_tolerance(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_percent = _to_float_or_none_output_current_tolerance(output_current_tolerance_edit)
                    
                    act = {
                        'type': 'Output Current Calibration',
                        'test_trigger_source': trigger_msg_id,
                        'test_trigger_signal': trigger_signal,
                        'test_trigger_signal_value': trigger_value,
                        'current_setpoint_signal': setpoint_signal,
                        'output_current_trim_signal': trim_signal,
                        'initial_trim_value': initial_trim_value,
                        'feedback_signal_source': feedback_msg_id,
                        'feedback_signal': feedback_signal,
                        'oscilloscope_channel': osc_channel,
                        'oscilloscope_timebase': timebase,
                        'minimum_test_current': min_current,
                        'maximum_test_current': max_current,
                        'step_current': step_current,
                        'pre_acquisition_time_ms': pre_acq_time,
                        'acquisition_time_ms': acq_time,
                        'tolerance_percent': tolerance_percent,
                    }
                elif t == 'Charged HV Bus Test':
                    # Charged HV Bus Test: read all fields (DBC mode)
                    try:
                        cmd_msg_id = charged_hv_bus_cmd_msg_combo.currentData()
                    except Exception:
                        cmd_msg_id = None
                    trigger_signal = charged_hv_bus_trigger_signal_combo.currentText().strip() if charged_hv_bus_trigger_signal_combo.count() else ''
                    
                    # Test Trigger Signal Value (int, 0-255)
                    def _to_int_or_none_charged_hv_bus_trigger_value(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    trigger_value = _to_int_or_none_charged_hv_bus_trigger_value(charged_hv_bus_trigger_value_edit)
                    
                    trim_signal = charged_hv_bus_trim_signal_combo.currentText().strip() if charged_hv_bus_trim_signal_combo.count() else ''
                    
                    # Fallback Output Current Trim Value (float, 0-200)
                    def _to_float_or_none_charged_hv_bus_fallback_trim(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    fallback_trim = _to_float_or_none_charged_hv_bus_fallback_trim(charged_hv_bus_fallback_trim_edit)
                    
                    setpoint_signal = charged_hv_bus_setpoint_signal_combo.currentText().strip() if charged_hv_bus_setpoint_signal_combo.count() else ''
                    
                    # Output Test Current (float, 0-40)
                    def _to_float_or_none_charged_hv_bus_output_current(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    output_current = _to_float_or_none_charged_hv_bus_output_current(charged_hv_bus_output_current_edit)
                    
                    try:
                        feedback_msg_id = charged_hv_bus_feedback_msg_combo.currentData()
                    except Exception:
                        feedback_msg_id = None
                    dut_state_signal = charged_hv_bus_dut_state_signal_combo.currentText().strip() if charged_hv_bus_dut_state_signal_combo.count() else ''
                    enable_relay_signal = charged_hv_bus_enable_relay_signal_combo.currentText().strip() if charged_hv_bus_enable_relay_signal_combo.count() else ''
                    enable_pfc_signal = charged_hv_bus_enable_pfc_signal_combo.currentText().strip() if charged_hv_bus_enable_pfc_signal_combo.count() else ''
                    pfc_power_good_signal = charged_hv_bus_pfc_power_good_signal_combo.currentText().strip() if charged_hv_bus_pfc_power_good_signal_combo.count() else ''
                    pcmc_signal = charged_hv_bus_pcmc_signal_combo.currentText().strip() if charged_hv_bus_pcmc_signal_combo.count() else ''
                    psfb_fault_signal = charged_hv_bus_psfb_fault_signal_combo.currentText().strip() if charged_hv_bus_psfb_fault_signal_combo.count() else ''
                    
                    # Test Time (int, >= 1000)
                    def _to_int_or_none_charged_hv_bus_test_time(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    test_time = _to_int_or_none_charged_hv_bus_test_time(charged_hv_bus_test_time_edit)
                    
                    act = {
                        'type': 'Charged HV Bus Test',
                        'command_signal_source': cmd_msg_id,
                        'test_trigger_signal': trigger_signal,
                        'test_trigger_signal_value': trigger_value,
                        'set_output_current_trim_signal': trim_signal,
                        'fallback_output_current_trim_value': fallback_trim,
                        'set_output_current_setpoint_signal': setpoint_signal,
                        'output_test_current': output_current,
                        'feedback_signal_source': feedback_msg_id,
                        'dut_test_state_signal': dut_state_signal,
                        'enable_relay_signal': enable_relay_signal,
                        'enable_pfc_signal': enable_pfc_signal,
                        'pfc_power_good_signal': pfc_power_good_signal,
                        'pcmc_signal': pcmc_signal,
                        'psfb_fault_signal': psfb_fault_signal,
                        'test_time_ms': test_time,
                    }
                elif t == 'Charger Functional Test':
                    # Charger Functional Test: read all fields (DBC mode)
                    try:
                        cmd_msg_id = charger_functional_cmd_msg_combo.currentData()
                    except Exception:
                        cmd_msg_id = None
                    trigger_signal = charger_functional_trigger_signal_combo.currentText().strip() if charger_functional_trigger_signal_combo.count() else ''
                    
                    # Test Trigger Signal Value (int, 0-255)
                    def _to_int_or_none_charger_functional_trigger_value(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    trigger_value = _to_int_or_none_charger_functional_trigger_value(charger_functional_trigger_value_edit)
                    
                    trim_signal = charger_functional_trim_signal_combo.currentText().strip() if charger_functional_trim_signal_combo.count() else ''
                    
                    # Fallback Output Current Trim Value (float, 0-200)
                    def _to_float_or_none_charger_functional_fallback_trim(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    fallback_trim = _to_float_or_none_charger_functional_fallback_trim(charger_functional_fallback_trim_edit)
                    
                    setpoint_signal = charger_functional_setpoint_signal_combo.currentText().strip() if charger_functional_setpoint_signal_combo.count() else ''
                    
                    # Output Test Current (float, 0-40)
                    def _to_float_or_none_charger_functional_output_current(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    output_current = _to_float_or_none_charger_functional_output_current(charger_functional_output_current_edit)
                    
                    try:
                        feedback_msg_id = charger_functional_feedback_msg_combo.currentData()
                    except Exception:
                        feedback_msg_id = None
                    dut_state_signal = charger_functional_dut_state_signal_combo.currentText().strip() if charger_functional_dut_state_signal_combo.count() else ''
                    enable_relay_signal = charger_functional_enable_relay_signal_combo.currentText().strip() if charger_functional_enable_relay_signal_combo.count() else ''
                    enable_pfc_signal = charger_functional_enable_pfc_signal_combo.currentText().strip() if charger_functional_enable_pfc_signal_combo.count() else ''
                    pfc_power_good_signal = charger_functional_pfc_power_good_signal_combo.currentText().strip() if charger_functional_pfc_power_good_signal_combo.count() else ''
                    pcmc_signal = charger_functional_pcmc_signal_combo.currentText().strip() if charger_functional_pcmc_signal_combo.count() else ''
                    output_current_signal = charger_functional_output_current_signal_combo.currentText().strip() if charger_functional_output_current_signal_combo.count() else ''
                    psfb_fault_signal = charger_functional_psfb_fault_signal_combo.currentText().strip() if charger_functional_psfb_fault_signal_combo.count() else ''
                    
                    # Output Current Tolerance (float, >= 0)
                    def _to_float_or_none_charger_functional_tolerance(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    output_current_tolerance = _to_float_or_none_charger_functional_tolerance(charger_functional_output_current_tolerance_edit)
                    
                    # Test Time (int, >= 1000)
                    def _to_int_or_none_charger_functional_test_time(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    test_time = _to_int_or_none_charger_functional_test_time(charger_functional_test_time_edit)
                    
                    act = {
                        'type': 'Charger Functional Test',
                        'command_signal_source': cmd_msg_id,
                        'test_trigger_signal': trigger_signal,
                        'test_trigger_signal_value': trigger_value,
                        'set_output_current_trim_signal': trim_signal,
                        'fallback_output_current_trim_value': fallback_trim,
                        'set_output_current_setpoint_signal': setpoint_signal,
                        'output_test_current': output_current,
                        'feedback_signal_source': feedback_msg_id,
                        'dut_test_state_signal': dut_state_signal,
                        'enable_relay_signal': enable_relay_signal,
                        'enable_pfc_signal': enable_pfc_signal,
                        'pfc_power_good_signal': pfc_power_good_signal,
                        'pcmc_signal': pcmc_signal,
                        'output_current_signal': output_current_signal,
                        'psfb_fault_signal': psfb_fault_signal,
                        'output_current_tolerance': output_current_tolerance,
                        'test_time_ms': test_time,
                    }
            else:  # No DBC loaded
                if t == 'Digital Logic Test':
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
                        'type': 'Digital Logic Test',
                        'can_id': can_id,
                        'signal': dig_signal.text().strip(),
                        'value_low': dig_value_low.text().strip(),
                        'value_high': dig_value_high.text().strip(),
                        'dwell_ms': dig_dwell,
                    }
                elif t == 'Analog Sweep Test':
                    # Non-DBC analog test: read all fields
                    try:
                        mux_channel_val = int(mux_chan.text().strip(), 0) if mux_chan.text().strip() else None
                    except Exception:
                        mux_channel_val = None
                    try:
                        dac_id = int(dac_can.text().strip(), 0) if dac_can.text().strip() else None
                    except Exception:
                        dac_id = None
                    dac_cmd_sig = dac_cmd.text().strip()
                    
                    # Read numeric DAC parameters
                    def _to_int_or_none(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dac_min = _to_int_or_none(dac_min_mv)
                    dac_max = _to_int_or_none(dac_max_mv)
                    dac_step = _to_int_or_none(dac_step_mv)
                    dac_dwell = _to_int_or_none(dac_dwell_ms)
                    # Read expected gain (optional float)
                    expected_gain_val = None
                    try:
                        expected_gain_text = expected_gain_edit.text().strip() if hasattr(expected_gain_edit, 'text') else ''
                        if expected_gain_text:
                            expected_gain_val = float(expected_gain_text)
                    except (ValueError, TypeError):
                        pass
                    # Read gain tolerance (optional float)
                    gain_tolerance_val = None
                    try:
                        gain_tolerance_text = gain_tolerance_edit.text().strip() if hasattr(gain_tolerance_edit, 'text') else ''
                        if gain_tolerance_text:
                            gain_tolerance_val = float(gain_tolerance_text)
                            if gain_tolerance_val < 0:
                                raise ValueError("Gain tolerance cannot be negative")
                    except (ValueError, TypeError):
                        pass
                    
                    act = {
                        'type': 'Analog Sweep Test',
                        'dac_can_id': dac_id,
                        'dac_command_signal': dac_cmd_sig,
                        'mux_channel_value': mux_channel_val,
                        'dac_min_mv': dac_min,
                        'dac_max_mv': dac_max,
                        'dac_step_mv': dac_step,
                        'dac_dwell_ms': dac_dwell,
                    }
                    if expected_gain_val is not None:
                        act['expected_gain'] = expected_gain_val
                    if gain_tolerance_val is not None:
                        act['gain_tolerance_percent'] = gain_tolerance_val
                elif t == 'Phase Current Test':
                    # Phase Current Calibration (no DBC): read from text fields
                    # Command Message and related signals
                    try:
                        cmd_msg_id = int(phase_current_cmd_msg_edit.text().strip(), 0) if phase_current_cmd_msg_edit.text().strip() else None
                    except Exception:
                        cmd_msg_id = None
                    trigger_test_sig = phase_current_trigger_signal_edit.text().strip()
                    iq_ref_sig = phase_current_iq_ref_signal_edit.text().strip()
                    id_ref_sig = phase_current_id_ref_signal_edit.text().strip()
                    
                    # Phase Current Signal Source and V/W signals
                    try:
                        phase_current_can_id = int(phase_current_msg_edit.text().strip(), 0) if phase_current_msg_edit.text().strip() else None
                    except Exception:
                        phase_current_can_id = None
                    phase_current_v_sig = phase_current_v_signal_edit.text().strip()
                    phase_current_w_sig = phase_current_w_signal_edit.text().strip()
                    
                    # Iq values (convert to float)
                    def _to_float_or_none(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    min_iq = _to_float_or_none(min_iq_edit)
                    max_iq = _to_float_or_none(max_iq_edit)
                    step_iq = _to_float_or_none(step_iq_edit)
                    
                    # IPC Test duration (convert to int)
                    def _to_int_or_none_duration(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    ipc_test_duration = _to_int_or_none_duration(ipc_test_duration_edit)
                    
                    # Oscilloscope channel selections
                    osc_phase_v_ch = osc_phase_v_ch_combo.currentText().strip() if osc_phase_v_ch_combo.count() else ''
                    osc_phase_w_ch = osc_phase_w_ch_combo.currentText().strip() if osc_phase_w_ch_combo.count() else ''
                    
                    act = {
                        'type': 'Phase Current Test',
                        'command_message': cmd_msg_id,
                        'trigger_test_signal': trigger_test_sig,
                        'iq_ref_signal': iq_ref_sig,
                        'id_ref_signal': id_ref_sig,
                        'phase_current_signal_source': phase_current_can_id,
                        'phase_current_v_signal': phase_current_v_sig,
                        'phase_current_w_signal': phase_current_w_sig,
                        'min_iq': min_iq,
                        'max_iq': max_iq,
                        'step_iq': step_iq,
                        'ipc_test_duration_ms': ipc_test_duration,
                        'oscilloscope_phase_v_ch': osc_phase_v_ch,
                        'oscilloscope_phase_w_ch': osc_phase_w_ch,
                    }
                elif t == 'Analog Static Test':
                    # Analog Static Test (no DBC): read from text fields
                    try:
                        fb_msg_id = int(analog_static_fb_msg_edit.text().strip(), 0) if analog_static_fb_msg_edit.text().strip() else None
                    except Exception:
                        fb_msg_id = None
                    fb_signal = analog_static_fb_signal_edit.text().strip()
                    
                    try:
                        eol_msg_id = int(analog_static_eol_msg_edit.text().strip(), 0) if analog_static_eol_msg_edit.text().strip() else None
                    except Exception:
                        eol_msg_id = None
                    eol_signal = analog_static_eol_signal_edit.text().strip()
                    
                    # Tolerance (float)
                    def _to_float_or_none_tolerance_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_val = _to_float_or_none_tolerance_fallback(tolerance_edit_fallback)
                    
                    # Pre-dwell and dwell times (int)
                    def _to_int_or_none_time_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    pre_dwell_val = _to_int_or_none_time_fallback(pre_dwell_time_edit_fallback)
                    dwell_time_val = _to_int_or_none_time_fallback(dwell_time_edit_fallback)
                    
                    act = {
                        'type': 'Analog Static Test',
                        'feedback_signal_source': fb_msg_id,
                        'feedback_signal': fb_signal,
                        'eol_signal_source': eol_msg_id,
                        'eol_signal': eol_signal,
                        'tolerance_mv': tolerance_val,
                        'pre_dwell_time_ms': pre_dwell_val,
                        'dwell_time_ms': dwell_time_val,
                    }
                elif t == 'Temperature Validation Test':
                    # Temperature Validation Test (no DBC): read from text fields
                    try:
                        fb_msg_id = int(temp_val_fb_msg_edit.text().strip(), 0) if temp_val_fb_msg_edit.text().strip() else None
                    except Exception:
                        fb_msg_id = None
                    fb_signal = temp_val_fb_signal_edit.text().strip()
                    
                    # Reference temperature (float)
                    def _to_float_or_none_reference_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    reference_temp_val = _to_float_or_none_reference_fallback(temp_val_reference_edit_fallback)
                    
                    # Tolerance (float)
                    def _to_float_or_none_temp_tolerance_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_c_val = _to_float_or_none_temp_tolerance_fallback(temp_val_tolerance_edit_fallback)
                    
                    # Dwell time (int)
                    def _to_int_or_none_dwell_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dwell_time_val = _to_int_or_none_dwell_fallback(temp_val_dwell_time_edit_fallback)
                    
                    act = {
                        'type': 'Temperature Validation Test',
                        'feedback_signal_source': fb_msg_id,
                        'feedback_signal': fb_signal,
                        'reference_temperature_c': reference_temp_val,
                        'tolerance_c': tolerance_c_val,
                        'dwell_time_ms': dwell_time_val,
                    }
                elif t == 'Analog PWM Sensor':
                    # Analog PWM Sensor Test (no DBC): read from text fields
                    try:
                        fb_msg_id = int(analog_pwm_fb_msg_edit.text().strip(), 0) if analog_pwm_fb_msg_edit.text().strip() else None
                    except Exception:
                        fb_msg_id = None
                    pwm_frequency_signal = analog_pwm_frequency_signal_edit.text().strip()
                    duty_signal = analog_pwm_duty_signal_edit.text().strip()
                    
                    # Reference PWM frequency (float)
                    def _to_float_or_none_pwm_freq_reference_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    reference_pwm_freq_val = _to_float_or_none_pwm_freq_reference_fallback(analog_pwm_reference_frequency_edit_fallback)
                    
                    # Reference duty (float)
                    def _to_float_or_none_duty_reference_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    reference_duty_val = _to_float_or_none_duty_reference_fallback(analog_pwm_reference_duty_edit_fallback)
                    
                    # PWM frequency tolerance (float)
                    def _to_float_or_none_pwm_freq_tolerance_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    pwm_freq_tolerance_val = _to_float_or_none_pwm_freq_tolerance_fallback(analog_pwm_frequency_tolerance_edit_fallback)
                    
                    # Duty tolerance (float)
                    def _to_float_or_none_duty_tolerance_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    duty_tolerance_val = _to_float_or_none_duty_tolerance_fallback(analog_pwm_duty_tolerance_edit_fallback)
                    
                    # Acquisition time (int)
                    def _to_int_or_none_acquisition_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    acquisition_time_val = _to_int_or_none_acquisition_fallback(analog_pwm_acquisition_time_edit_fallback)
                    
                    act = {
                        'type': 'Analog PWM Sensor',
                        'feedback_signal_source': fb_msg_id,
                        'feedback_pwm_frequency_signal': pwm_frequency_signal,
                        'feedback_duty_signal': duty_signal,
                        'reference_pwm_frequency': reference_pwm_freq_val,
                        'reference_duty': reference_duty_val,
                        'pwm_frequency_tolerance': pwm_freq_tolerance_val,
                        'duty_tolerance': duty_tolerance_val,
                        'acquisition_time_ms': acquisition_time_val,
                    }
                elif t == 'Fan Control Test':
                    # Fan Control Test (no DBC): read from text fields
                    try:
                        trigger_msg_id = int(fan_control_trigger_msg_edit.text().strip(), 0) if fan_control_trigger_msg_edit.text().strip() else None
                    except Exception:
                        trigger_msg_id = None
                    trigger_signal = fan_control_trigger_signal_edit.text().strip()
                    
                    try:
                        feedback_msg_id = int(fan_control_feedback_msg_edit.text().strip(), 0) if fan_control_feedback_msg_edit.text().strip() else None
                    except Exception:
                        feedback_msg_id = None
                    fan_enabled_signal = fan_control_enabled_signal_edit.text().strip()
                    fan_tach_signal = fan_control_tach_signal_edit.text().strip()
                    fan_fault_signal = fan_control_fault_signal_edit.text().strip()
                    
                    # Dwell time (int)
                    def _to_int_or_none_fan_dwell_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dwell_time_val = _to_int_or_none_fan_dwell_fallback(fan_control_dwell_time_edit_fallback)
                    
                    # Test timeout (int)
                    def _to_int_or_none_fan_timeout_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    timeout_val = _to_int_or_none_fan_timeout_fallback(fan_control_timeout_edit_fallback)
                    
                    act = {
                        'type': 'Fan Control Test',
                        'fan_test_trigger_source': trigger_msg_id,
                        'fan_test_trigger_signal': trigger_signal,
                        'fan_control_feedback_source': feedback_msg_id,
                        'fan_enabled_signal': fan_enabled_signal,
                        'fan_tach_feedback_signal': fan_tach_signal,
                        'fan_fault_feedback_signal': fan_fault_signal,
                        'dwell_time_ms': dwell_time_val,
                        'test_timeout_ms': timeout_val,
                    }
                elif t == 'External 5V Test':
                    # External 5V Test (no DBC): read from text fields
                    try:
                        trigger_msg_id = int(ext_5v_test_trigger_msg_edit.text().strip(), 0) if ext_5v_test_trigger_msg_edit.text().strip() else None
                    except Exception:
                        trigger_msg_id = None
                    trigger_signal = ext_5v_test_trigger_signal_edit.text().strip()
                    
                    try:
                        eol_msg_id = int(ext_5v_test_eol_msg_edit.text().strip(), 0) if ext_5v_test_eol_msg_edit.text().strip() else None
                    except Exception:
                        eol_msg_id = None
                    eol_signal = ext_5v_test_eol_signal_edit.text().strip()
                    
                    try:
                        feedback_msg_id = int(ext_5v_test_feedback_msg_edit.text().strip(), 0) if ext_5v_test_feedback_msg_edit.text().strip() else None
                    except Exception:
                        feedback_msg_id = None
                    feedback_signal = ext_5v_test_feedback_signal_edit.text().strip()
                    
                    # Tolerance (float)
                    def _to_float_or_none_ext5v_tolerance_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_val = _to_float_or_none_ext5v_tolerance_fallback(ext_5v_test_tolerance_edit_fallback)
                    
                    # Pre-dwell and dwell times (int)
                    def _to_int_or_none_ext5v_time_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    pre_dwell_val = _to_int_or_none_ext5v_time_fallback(ext_5v_test_pre_dwell_time_edit_fallback)
                    dwell_time_val = _to_int_or_none_ext5v_time_fallback(ext_5v_test_dwell_time_edit_fallback)
                    
                    act = {
                        'type': 'External 5V Test',
                        'ext_5v_test_trigger_source': trigger_msg_id,
                        'ext_5v_test_trigger_signal': trigger_signal,
                        'eol_ext_5v_measurement_source': eol_msg_id,
                        'eol_ext_5v_measurement_signal': eol_signal,
                        'feedback_signal_source': feedback_msg_id,
                        'feedback_signal': feedback_signal,
                        'tolerance_mv': tolerance_val,
                        'pre_dwell_time_ms': pre_dwell_val,
                        'dwell_time_ms': dwell_time_val,
                    }
                elif t == 'DC Bus Sensing':
                    # DC Bus Sensing (no DBC): read from text fields
                    # Note: DC Bus Sensing requires oscilloscope config, so fallback mode may not be fully supported
                    # For now, we'll use text fields similar to other tests
                    osc_channel = dc_bus_osc_channel_combo.currentText().strip() if dc_bus_osc_channel_combo.count() else ''
                    
                    try:
                        feedback_msg_id = int(dc_bus_feedback_msg_edit.text().strip(), 0) if dc_bus_feedback_msg_edit.text().strip() else None
                    except Exception:
                        feedback_msg_id = None
                    feedback_signal = dc_bus_feedback_signal_edit.text().strip()
                    
                    # Dwell time (int)
                    def _to_int_or_none_dc_bus_dwell_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dwell_time_val = _to_int_or_none_dc_bus_dwell_fallback(dc_bus_dwell_time_edit_fallback)
                    
                    # Tolerance (float, in V)
                    def _to_float_or_none_dc_bus_tolerance_fallback(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_val = _to_float_or_none_dc_bus_tolerance_fallback(dc_bus_tolerance_edit_fallback)
                    
                    act = {
                        'type': 'DC Bus Sensing',
                        'oscilloscope_channel': osc_channel,
                        'feedback_signal_source': feedback_msg_id,
                        'feedback_signal': feedback_signal,
                        'dwell_time_ms': dwell_time_val,
                        'tolerance_v': tolerance_val,
                    }
            # if using DBC-driven fields, read feedback from combo
            # Only save feedback fields for test types that use them
            # Test types that have their own feedback fields inside actuation don't need these
            test_types_with_own_feedback = ('Phase Current Test', 'Analog Static Test', 'Analog PWM Sensor', 'Temperature Validation Test', 
                                          'Fan Control Test', 'External 5V Test', 'DC Bus Sensing', 'Output Current Calibration', 'Charged HV Bus Test', 'Charger Functional Test')
            
            fb_msg_id = None
            feedback = None
            if t not in test_types_with_own_feedback:
                # Only read feedback fields for test types that use them
                if self.dbc_service is not None and self.dbc_service.is_loaded():
                    try:
                        feedback = fb_signal_combo.currentText().strip()
                        fb_msg_id = fb_msg_combo.currentData()
                    except Exception:
                        feedback = ''
                else:
                    feedback = feedback_edit.text().strip()

            # Get test_mode value
            test_mode_val = test_mode_spin.value()
            
            entry = {
                'name': nm,
                'type': t,
                'actuation': act,
                'test_mode': test_mode_val,
                'created_at': datetime.utcnow().isoformat() + 'Z'
            }
            
            # Only add feedback fields if they were read (for test types that use them)
            if feedback is not None:
                entry['feedback_signal'] = feedback
            if fb_msg_id is not None:
                entry['feedback_message_id'] = fb_msg_id
            
            # Validate test before adding
            is_valid, error_msg = self._validate_test(entry)
            if not is_valid:
                QtWidgets.QMessageBox.warning(dlg, 'Invalid Test Configuration', f'Cannot create test: {error_msg}')
                return
            
            self._tests.append(entry)
            self.test_list.addItem(entry['name'])
            # select the newly added test and update JSON preview
            try:
                self.test_list.setCurrentRow(self.test_list.count() - 1)
                self._on_select_test(None, None)
            except Exception:
                pass
            # Sync Test Plan
            try:
                self._populate_test_plan()
            except Exception:
                pass
            dlg.accept()

        btns.accepted.connect(on_accept)
        btns.rejected.connect(dlg.reject)
        dlg.exec()

    def _is_test_name_unique(self, name: str, exclude_index: int = None) -> bool:
        """Check if test name is unique, optionally excluding a specific index (for edit).
        
        Args:
            name: Test name to check
            exclude_index: Index to exclude from check (current test being edited)
            
        Returns:
            True if name is unique, False otherwise
        """
        if not name or not name.strip():
            return False
        name = name.strip()
        for i, test in enumerate(self._tests):
            if i == exclude_index:
                continue
            if test.get('name', '').strip() == name:
                return False
        return True
    
    def _is_test_name_unique(self, name: str, exclude_index: int = None) -> bool:
        """Check if test name is unique, optionally excluding a specific index (for edit).
        
        Args:
            name: Test name to check
            exclude_index: Index to exclude from check (current test being edited)
            
        Returns:
            True if name is unique, False otherwise
        """
        if not name or not name.strip():
            return False
        name = name.strip()
        for i, test in enumerate(self._tests):
            if i == exclude_index:
                continue
            if test.get('name', '').strip() == name:
                return False
        return True
    
    def _validate_test(self, test_data: dict) -> tuple[bool, str]:
        """Validate test data.
        
        Args:
            test_data: Dictionary containing test configuration
            
        Returns:
            Tuple of (is_valid, error_message). If valid, error_message is empty.
        """
        # Check name
        name = test_data.get('name', '').strip()
        if not name:
            return False, "Test name is required and cannot be empty"
        
        # Check type
        test_type = test_data.get('type')
        if test_type not in ('Digital Logic Test', 'Analog Sweep Test', 'Phase Current Test', 'Analog Static Test', 'Analog PWM Sensor', 'Temperature Validation Test', 'Fan Control Test', 'External 5V Test', 'DC Bus Sensing', 'Output Current Calibration', 'Charged HV Bus Test', 'Charger Functional Test'):
            return False, f"Invalid test type: {test_type}. Must be 'Digital Logic Test', 'Analog Sweep Test', 'Phase Current Test', 'Analog Static Test', 'Analog PWM Sensor', 'Temperature Validation Test', 'Fan Control Test', 'External 5V Test', 'DC Bus Sensing', 'Output Current Calibration', or 'Charged HV Bus Test'"
        
        # Check actuation
        actuation = test_data.get('actuation', {})
        if not actuation:
            return False, "Test actuation configuration is required"
        
        act_type = actuation.get('type')
        if act_type != test_type:
            return False, f"Actuation type '{act_type}' does not match test type '{test_type}'"
        
        # Type-specific validation
        if test_type == 'Analog Sweep Test':
            if actuation.get('dac_can_id') is None:
                return False, "Analog test requires DAC CAN ID"
            if not actuation.get('dac_command_signal'):
                return False, "Analog test requires DAC command signal"
            # Validate DAC voltage ranges
            dac_min = actuation.get('dac_min_mv')
            dac_max = actuation.get('dac_max_mv')
            if dac_min is not None and not (DAC_VOLTAGE_MIN <= dac_min <= DAC_VOLTAGE_MAX):
                return False, f"DAC min voltage {dac_min} out of range ({DAC_VOLTAGE_MIN}-{DAC_VOLTAGE_MAX} mV)"
            if dac_max is not None and not (DAC_VOLTAGE_MIN <= dac_max <= DAC_VOLTAGE_MAX):
                return False, f"DAC max voltage {dac_max} out of range ({DAC_VOLTAGE_MIN}-{DAC_VOLTAGE_MAX} mV)"
            if dac_min is not None and dac_max is not None and dac_max < dac_min:
                return False, f"DAC max voltage {dac_max} cannot be less than min voltage {dac_min}"
        
        elif test_type == 'Digital Logic Test':
            if actuation.get('can_id') is None:
                return False, "Digital test requires CAN ID"
        elif test_type == 'Phase Current Test':
            # Phase current calibration validation - fields are optional but should be validated if present
            # No strict requirements for now, but could add validation for required fields later
            pass
        elif test_type == 'Analog Static Test':
            # Validate required fields
            if actuation.get('feedback_signal_source') is None:
                return False, "Analog Static test requires feedback signal source (CAN ID)"
            if not actuation.get('feedback_signal'):
                return False, "Analog Static test requires feedback signal name"
            if actuation.get('eol_signal_source') is None:
                return False, "Analog Static test requires EOL signal source (CAN ID)"
            if not actuation.get('eol_signal'):
                return False, "Analog Static test requires EOL signal name"
            if actuation.get('tolerance_mv') is None:
                return False, "Analog Static test requires tolerance (mV)"
            if actuation.get('tolerance_mv', 0) < 0:
                return False, "Tolerance must be non-negative"
            if actuation.get('pre_dwell_time_ms') is None:
                return False, "Analog Static test requires pre-dwell time (ms)"
            if actuation.get('pre_dwell_time_ms', 0) < 0:
                return False, "Pre-dwell time must be non-negative"
            if actuation.get('dwell_time_ms') is None:
                return False, "Analog Static test requires dwell time (ms)"
            if actuation.get('dwell_time_ms', 0) <= 0:
                return False, "Dwell time must be positive"
        elif test_type == 'Analog PWM Sensor':
            # Validate required fields
            if actuation.get('feedback_signal_source') is None:
                return False, "Analog PWM Sensor test requires feedback signal source (CAN ID)"
            if not actuation.get('feedback_pwm_frequency_signal'):
                return False, "Analog PWM Sensor test requires feedback PWM frequency signal name"
            if not actuation.get('feedback_duty_signal'):
                return False, "Analog PWM Sensor test requires feedback duty signal name"
            if actuation.get('reference_pwm_frequency') is None:
                return False, "Analog PWM Sensor test requires reference PWM frequency (Hz)"
            if actuation.get('reference_duty') is None:
                return False, "Analog PWM Sensor test requires reference duty (%)"
            if actuation.get('pwm_frequency_tolerance') is None:
                return False, "Analog PWM Sensor test requires PWM frequency tolerance (Hz)"
            if actuation.get('pwm_frequency_tolerance', 0) < 0:
                return False, "PWM frequency tolerance must be non-negative"
            if actuation.get('duty_tolerance') is None:
                return False, "Analog PWM Sensor test requires duty tolerance (%)"
            if actuation.get('duty_tolerance', 0) < 0:
                return False, "Duty tolerance must be non-negative"
            if actuation.get('acquisition_time_ms') is None:
                return False, "Analog PWM Sensor test requires acquisition time (ms)"
            if actuation.get('acquisition_time_ms', 0) <= 0:
                return False, "Acquisition time must be positive"
        elif test_type == 'Temperature Validation Test':
            # Validate required fields
            if actuation.get('feedback_signal_source') is None:
                return False, "Temperature Validation test requires feedback signal source (CAN ID)"
            if not actuation.get('feedback_signal'):
                return False, "Temperature Validation test requires feedback signal name"
            if actuation.get('reference_temperature_c') is None:
                return False, "Temperature Validation test requires reference temperature (°C)"
            if actuation.get('tolerance_c') is None:
                return False, "Temperature Validation test requires tolerance (°C)"
            if actuation.get('tolerance_c', 0) < 0:
                return False, "Tolerance must be non-negative"
            if actuation.get('dwell_time_ms') is None:
                return False, "Temperature Validation test requires dwell time (ms)"
            if actuation.get('dwell_time_ms', 0) <= 0:
                return False, "Dwell time must be positive"
        elif test_type == 'Fan Control Test':
            # Validate required fields
            if actuation.get('fan_test_trigger_source') is None:
                return False, "Fan Control test requires fan test trigger source (CAN ID)"
            if not actuation.get('fan_test_trigger_signal'):
                return False, "Fan Control test requires fan test trigger signal name"
            if actuation.get('fan_control_feedback_source') is None:
                return False, "Fan Control test requires fan control feedback source (CAN ID)"
            if not actuation.get('fan_enabled_signal'):
                return False, "Fan Control test requires fan enabled signal name"
            if not actuation.get('fan_tach_feedback_signal'):
                return False, "Fan Control test requires fan tach feedback signal name"
            if not actuation.get('fan_fault_feedback_signal'):
                return False, "Fan Control test requires fan fault feedback signal name"
            if actuation.get('dwell_time_ms') is None:
                return False, "Fan Control test requires dwell time (ms)"
            if actuation.get('dwell_time_ms', 0) <= 0:
                return False, "Dwell time must be positive"
            if actuation.get('test_timeout_ms') is None:
                return False, "Fan Control test requires test timeout (ms)"
            if actuation.get('test_timeout_ms', 0) <= 0:
                return False, "Test timeout must be positive"
        elif test_type == 'External 5V Test':
            # Validate required fields
            if actuation.get('ext_5v_test_trigger_source') is None:
                return False, "External 5V Test requires trigger source (CAN ID)"
            if not actuation.get('ext_5v_test_trigger_signal'):
                return False, "External 5V Test requires trigger signal name"
            if actuation.get('eol_ext_5v_measurement_source') is None:
                return False, "External 5V Test requires EOL measurement source (CAN ID)"
            if not actuation.get('eol_ext_5v_measurement_signal'):
                return False, "External 5V Test requires EOL measurement signal name"
            if actuation.get('feedback_signal_source') is None:
                return False, "External 5V Test requires feedback signal source (CAN ID)"
            if not actuation.get('feedback_signal'):
                return False, "External 5V Test requires feedback signal name"
            if actuation.get('tolerance_mv') is None:
                return False, "External 5V Test requires tolerance (mV)"
            if actuation.get('tolerance_mv', 0) < 0:
                return False, "Tolerance must be non-negative"
            if actuation.get('pre_dwell_time_ms') is None:
                return False, "External 5V Test requires pre-dwell time (ms)"
            if actuation.get('pre_dwell_time_ms', 0) < 0:
                return False, "Pre-dwell time must be non-negative"
            if actuation.get('dwell_time_ms') is None:
                return False, "External 5V Test requires dwell time (ms)"
            if actuation.get('dwell_time_ms', 0) <= 0:
                return False, "Dwell time must be positive"
        elif test_type == 'DC Bus Sensing':
            # Validate required fields
            if not actuation.get('oscilloscope_channel'):
                return False, "DC Bus Sensing test requires oscilloscope channel"
            if actuation.get('feedback_signal_source') is None:
                return False, "DC Bus Sensing test requires feedback signal source (CAN ID)"
            if not actuation.get('feedback_signal'):
                return False, "DC Bus Sensing test requires feedback signal name"
            if actuation.get('dwell_time_ms') is None:
                return False, "DC Bus Sensing test requires dwell time (ms)"
            if actuation.get('dwell_time_ms', 0) <= 0:
                return False, "Dwell time must be positive"
            if actuation.get('tolerance_v') is None:
                return False, "DC Bus Sensing test requires tolerance (V)"
            if actuation.get('tolerance_v', 0) < 0:
                return False, "Tolerance must be non-negative"
        elif test_type == 'Output Current Calibration':
            # Validate required fields
            if actuation.get('test_trigger_source') is None:
                return False, "Output Current Calibration test requires test trigger source (CAN ID)"
            if not (0 <= actuation.get('test_trigger_source', -1) <= 0x1FFFFFFF):
                return False, "Test trigger source must be in range 0-0x1FFFFFFF"
            if not actuation.get('test_trigger_signal'):
                return False, "Output Current Calibration test requires test trigger signal name"
            if actuation.get('test_trigger_signal_value') is None:
                return False, "Output Current Calibration test requires test trigger signal value"
            if not (0 <= actuation.get('test_trigger_signal_value', -1) <= 255):
                return False, "Test trigger signal value must be in range 0-255"
            if not actuation.get('current_setpoint_signal'):
                return False, "Output Current Calibration test requires current setpoint signal name"
            if not actuation.get('output_current_trim_signal'):
                return False, "Output Current Calibration test requires output current trim signal name"
            if actuation.get('initial_trim_value') is None:
                return False, "Output Current Calibration test requires initial trim value (%)"
            initial_trim = actuation.get('initial_trim_value')
            if initial_trim is not None:
                try:
                    initial_trim_float = float(initial_trim)
                    if not (0.0 <= initial_trim_float <= 200.0):
                        return False, f"Initial trim value must be in range 0.0000-200.0000%, got {initial_trim_float}"
                except (ValueError, TypeError):
                    return False, f"Initial trim value must be a number, got {initial_trim}"
            if actuation.get('feedback_signal_source') is None:
                return False, "Output Current Calibration test requires feedback signal source (CAN ID)"
            if not (0 <= actuation.get('feedback_signal_source', -1) <= 0x1FFFFFFF):
                return False, "Feedback signal source must be in range 0-0x1FFFFFFF"
            if not actuation.get('feedback_signal'):
                return False, "Output Current Calibration test requires feedback signal name"
            if not actuation.get('oscilloscope_channel'):
                return False, "Output Current Calibration test requires oscilloscope channel"
            if actuation.get('oscilloscope_timebase') not in ('10MS', '20MS', '100MS', '500MS'):
                return False, "Oscilloscope timebase must be one of: '10MS', '20MS', '100MS', '500MS'"
            if actuation.get('minimum_test_current') is None:
                return False, "Output Current Calibration test requires minimum test current (A)"
            if actuation.get('minimum_test_current', -1) < 0:
                return False, "Minimum test current must be non-negative"
            if actuation.get('maximum_test_current') is None:
                return False, "Output Current Calibration test requires maximum test current (A)"
            if actuation.get('maximum_test_current', -1) < 0:
                return False, "Maximum test current must be non-negative"
            if actuation.get('minimum_test_current') is not None and actuation.get('maximum_test_current') is not None:
                if actuation.get('maximum_test_current') < actuation.get('minimum_test_current'):
                    return False, "Maximum test current must be >= minimum test current"
            if actuation.get('step_current') is None:
                return False, "Output Current Calibration test requires step current (A)"
            if actuation.get('step_current', 0) < 0.1:
                return False, "Step current must be >= 0.1 A"
            if actuation.get('pre_acquisition_time_ms') is None:
                return False, "Output Current Calibration test requires pre-acquisition time (ms)"
            if actuation.get('pre_acquisition_time_ms', -1) < 0:
                return False, "Pre-acquisition time must be non-negative"
            if actuation.get('acquisition_time_ms') is None:
                return False, "Output Current Calibration test requires acquisition time (ms)"
            if actuation.get('acquisition_time_ms', 0) <= 0:
                return False, "Acquisition time must be positive"
            if actuation.get('tolerance_percent') is None:
                return False, "Output Current Calibration test requires tolerance (%)"
            if actuation.get('tolerance_percent', -1) < 0:
                return False, "Tolerance must be non-negative"
            # Check oscilloscope service availability
            if self.oscilloscope_service is None or not self.oscilloscope_service.is_connected():
                return False, "Output Current Calibration test requires oscilloscope to be connected"
            # Check oscilloscope channel exists in profile
            if hasattr(self, '_oscilloscope_config') and self._oscilloscope_config:
                osc_channel = actuation.get('oscilloscope_channel', '')
                if osc_channel:
                    channel_names = self.oscilloscope_service.get_channel_names(self._oscilloscope_config) if self.oscilloscope_service else []
                    if osc_channel not in channel_names:
                        return False, f"Oscilloscope channel '{osc_channel}' not found in oscilloscope configuration"
            # Check DBC service is available (test requires DBC)
            if self.dbc_service is None or not self.dbc_service.is_loaded():
                return False, "Output Current Calibration test requires DBC file to be loaded"
        elif test_type == 'Charged HV Bus Test':
            # Validate required fields
            if actuation.get('command_signal_source') is None:
                return False, "Charged HV Bus Test requires command signal source (CAN ID)"
            if not (0 <= actuation.get('command_signal_source', -1) <= 0x1FFFFFFF):
                return False, "Command signal source must be in range 0-0x1FFFFFFF"
            if not actuation.get('test_trigger_signal'):
                return False, "Charged HV Bus Test requires test trigger signal name"
            if actuation.get('test_trigger_signal_value') is None:
                return False, "Charged HV Bus Test requires test trigger signal value"
            if not (0 <= actuation.get('test_trigger_signal_value', -1) <= 255):
                return False, "Test trigger signal value must be in range 0-255"
            if not actuation.get('set_output_current_trim_signal'):
                return False, "Charged HV Bus Test requires set output current trim signal name"
            if actuation.get('fallback_output_current_trim_value') is None:
                return False, "Charged HV Bus Test requires fallback output current trim value"
            if not (0 <= actuation.get('fallback_output_current_trim_value', -1) <= 200):
                return False, "Fallback output current trim value must be in range 0-200"
            if not actuation.get('set_output_current_setpoint_signal'):
                return False, "Charged HV Bus Test requires set output current setpoint signal name"
            if actuation.get('output_test_current') is None:
                return False, "Charged HV Bus Test requires output test current (A)"
            if not (0 <= actuation.get('output_test_current', -1) <= 40):
                return False, "Output test current must be in range 0-40 A"
            if actuation.get('feedback_signal_source') is None:
                return False, "Charged HV Bus Test requires feedback signal source (CAN ID)"
            if not (0 <= actuation.get('feedback_signal_source', -1) <= 0x1FFFFFFF):
                return False, "Feedback signal source must be in range 0-0x1FFFFFFF"
            if not actuation.get('dut_test_state_signal'):
                return False, "Charged HV Bus Test requires DUT test state signal name"
            if not actuation.get('enable_relay_signal'):
                return False, "Charged HV Bus Test requires enable relay signal name"
            if not actuation.get('enable_pfc_signal'):
                return False, "Charged HV Bus Test requires enable PFC signal name"
            if not actuation.get('pfc_power_good_signal'):
                return False, "Charged HV Bus Test requires PFC power good signal name"
            if not actuation.get('pcmc_signal'):
                return False, "Charged HV Bus Test requires PCMC signal name"
            if not actuation.get('psfb_fault_signal'):
                return False, "Charged HV Bus Test requires PSFB fault signal name"
            if actuation.get('test_time_ms') is None:
                return False, "Charged HV Bus Test requires test time (ms)"
            if actuation.get('test_time_ms', 0) < 1000:
                return False, "Test time must be >= 1000 ms"
            # Check DBC service is available (test requires DBC)
            if self.dbc_service is None or not self.dbc_service.is_loaded():
                return False, "Charged HV Bus Test requires DBC file to be loaded"
        elif test_type == 'Charger Functional Test':
            # Validate required fields
            if actuation.get('command_signal_source') is None:
                return False, "Charger Functional Test requires command signal source (CAN ID)"
            if not (0 <= actuation.get('command_signal_source', -1) <= 0x1FFFFFFF):
                return False, "Command signal source must be in range 0-0x1FFFFFFF"
            if not actuation.get('test_trigger_signal'):
                return False, "Charger Functional Test requires test trigger signal name"
            if actuation.get('test_trigger_signal_value') is None:
                return False, "Charger Functional Test requires test trigger signal value"
            if not (0 <= actuation.get('test_trigger_signal_value', -1) <= 255):
                return False, "Test trigger signal value must be in range 0-255"
            if not actuation.get('set_output_current_trim_signal'):
                return False, "Charger Functional Test requires set output current trim signal name"
            if actuation.get('fallback_output_current_trim_value') is None:
                return False, "Charger Functional Test requires fallback output current trim value"
            if not (0 <= actuation.get('fallback_output_current_trim_value', -1) <= 200):
                return False, "Fallback output current trim value must be in range 0-200"
            if not actuation.get('set_output_current_setpoint_signal'):
                return False, "Charger Functional Test requires set output current setpoint signal name"
            if actuation.get('output_test_current') is None:
                return False, "Charger Functional Test requires output test current (A)"
            if not (0 <= actuation.get('output_test_current', -1) <= 40):
                return False, "Output test current must be in range 0-40 A"
            if actuation.get('feedback_signal_source') is None:
                return False, "Charger Functional Test requires feedback signal source (CAN ID)"
            if not (0 <= actuation.get('feedback_signal_source', -1) <= 0x1FFFFFFF):
                return False, "Feedback signal source must be in range 0-0x1FFFFFFF"
            if not actuation.get('dut_test_state_signal'):
                return False, "Charger Functional Test requires DUT test state signal name"
            if not actuation.get('enable_relay_signal'):
                return False, "Charger Functional Test requires enable relay signal name"
            if not actuation.get('enable_pfc_signal'):
                return False, "Charger Functional Test requires enable PFC signal name"
            if not actuation.get('pfc_power_good_signal'):
                return False, "Charger Functional Test requires PFC power good signal name"
            if not actuation.get('pcmc_signal'):
                return False, "Charger Functional Test requires PCMC signal name"
            if not actuation.get('output_current_signal'):
                return False, "Charger Functional Test requires output current signal name"
            if not actuation.get('psfb_fault_signal'):
                return False, "Charger Functional Test requires PSFB fault signal name"
            if actuation.get('output_current_tolerance') is None:
                return False, "Charger Functional Test requires output current tolerance (A)"
            if actuation.get('output_current_tolerance', -1) < 0:
                return False, "Output current tolerance must be >= 0"
            if actuation.get('test_time_ms') is None:
                return False, "Charger Functional Test requires test time (ms)"
            if actuation.get('test_time_ms', 0) < 1000:
                return False, "Test time must be >= 1000 ms"
            # Check DBC service is available (test requires DBC)
            if self.dbc_service is None or not self.dbc_service.is_loaded():
                return False, "Charger Functional Test requires DBC file to be loaded"
        
        return True, ""
    
    def _on_duplicate_test(self):
        """Duplicate the currently selected test with a unique name."""
        it = self.test_list.currentRow()
        if it < 0 or it >= len(self._tests):
            QtWidgets.QMessageBox.information(self, 'Duplicate Test', 'No test selected')
            return
        
        try:
            # Get the test to duplicate
            original_test = self._tests[it]
            
            # Create a deep copy of the test
            duplicated_test = copy.deepcopy(original_test)
            
            # Generate a unique name
            original_name = duplicated_test.get('name', 'Test').strip()
            base_name = original_name
            # Try different suffixes until we find a unique name
            new_name = f"{base_name}_Copy"
            counter = 1
            while not self._is_test_name_unique(new_name):
                new_name = f"{base_name}_Copy_{counter}"
                counter += 1
                # Safety limit to prevent infinite loop
                if counter > 1000:
                    new_name = f"{base_name}_Copy_{time.time():.0f}"
                    break
            
            # Update the duplicated test with new name and timestamp
            duplicated_test['name'] = new_name
            duplicated_test['created_at'] = datetime.utcnow().isoformat() + 'Z'
            
            # Validate the duplicated test
            is_valid, error_msg = self._validate_test(duplicated_test)
            if not is_valid:
                QtWidgets.QMessageBox.warning(
                    self, 'Invalid Test Configuration',
                    f'Cannot duplicate test: {error_msg}'
                )
                return
            
            # Add the duplicated test to the list
            self._tests.append(duplicated_test)
            self.test_list.addItem(new_name)
            
            # Select the newly duplicated test
            try:
                new_index = self.test_list.count() - 1
                self.test_list.setCurrentRow(new_index)
                self._on_select_test(None, None)
            except Exception:
                pass
            
            # Sync Test Plan
            try:
                self._populate_test_plan()
            except Exception:
                pass
            
            QtWidgets.QMessageBox.information(
                self, 'Test Duplicated',
                f'Test "{original_name}" duplicated as "{new_name}"'
            )
            logger.info(f"Duplicated test '{original_name}' as '{new_name}'")
        except Exception as e:
            logger.error(f"Error duplicating test: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to duplicate test: {e}')
    
    def _on_delete_test(self):
        it = self.test_list.currentRow()
        if it < 0:
            QtWidgets.QMessageBox.information(self, 'Delete Test', 'No test selected')
            return
        self.test_list.takeItem(it)
        try:
            deleted_test = self._tests[it]
            del self._tests[it]
            # Remove execution data for deleted test
            test_name = deleted_test.get('name', '')
            if test_name in self._test_execution_data:
                del self._test_execution_data[test_name]
        except Exception:
            pass
        self.json_preview.clear()
        # Sync Test Plan
        try:
            self._populate_test_plan()
        except Exception:
            pass

    def _on_save_tests(self) -> None:
        """Save current test configuration to JSON file.
        
        Saves all configured tests to backend/data/tests/tests.json
        in the format defined by the test profile schema.
        
        Validates all tests before saving and creates backup of existing file.
        """
        # Check if there are tests to save
        if not self._tests:
            QtWidgets.QMessageBox.warning(self, 'No Tests', 'No tests to save. Create tests first.')
            return
        
        # Validate all tests before saving
        validation_errors = []
        for i, test in enumerate(self._tests):
            is_valid, error_msg = self._validate_test(test)
            if not is_valid:
                validation_errors.append(f"Test {i+1} '{test.get('name', '<unnamed>')}': {error_msg}")
        
        if validation_errors:
            error_text = "Cannot save tests with validation errors:\n\n" + "\n".join(validation_errors)
            QtWidgets.QMessageBox.warning(self, 'Validation Errors', error_text)
            return
        
        # Check for duplicate names
        duplicate_names = []
        seen_names = set()
        for test in self._tests:
            name = test.get('name', '').strip()
            if name in seen_names:
                duplicate_names.append(name)
            seen_names.add(name)
        
        if duplicate_names:
            reply = QtWidgets.QMessageBox.warning(
                self, 'Duplicate Names',
                f"The following test names appear multiple times: {', '.join(set(duplicate_names))}\n\n"
                "This may cause issues with test reordering. Continue anyway?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.No:
                return
        
        default_dir = os.path.join(repo_root, 'backend', 'data', 'tests')
        os.makedirs(default_dir, exist_ok=True)
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save Test Profile', os.path.join(default_dir, 'tests.json'), 'JSON Files (*.json);;All Files (*)'
        )
        if not file_path:
            return  # User cancelled
        
        # Check if file exists and create backup
        if os.path.exists(file_path):
            backup_path = file_path + '.bak'
            try:
                import shutil
                shutil.copy2(file_path, backup_path)
                logger.info(f"Created backup: {backup_path}")
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({'tests': self._tests}, f, indent=2)
            QtWidgets.QMessageBox.information(self, 'Saved', f'Saved {len(self._tests)} test(s) to {file_path}')
            logger.info(f"Saved {len(self._tests)} tests to {file_path}")
        except json.JSONEncodeError as e:
            QtWidgets.QMessageBox.critical(self, 'JSON Error', f'Failed to encode tests as JSON: {e}')
            logger.error(f"JSON encoding error: {e}", exc_info=True)
        except IOError as e:
            QtWidgets.QMessageBox.critical(self, 'File Error', f'Failed to write file: {e}')
            logger.error(f"File write error: {e}", exc_info=True)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to save tests: {e}')
            logger.error(f"Unexpected error saving tests: {e}", exc_info=True)

    def _on_load_tests(self) -> None:
        """Load test configuration from JSON file.
        
        Loads tests from backend/data/tests/tests.json and populates
        the test list. Validates test structure and checks for duplicates.
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
        except json.JSONDecodeError as e:
            QtWidgets.QMessageBox.critical(
                self, 'JSON Parse Error',
                f'Failed to parse JSON file:\n{str(e)}\n\nFile may be corrupted or invalid.'
            )
            logger.error(f"JSON parse error loading {file_path}: {e}", exc_info=True)
            return
        except IOError as e:
            QtWidgets.QMessageBox.critical(self, 'File Error', f'Failed to read file: {e}')
            logger.error(f"File read error: {e}", exc_info=True)
            return
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to load tests: {e}')
            logger.error(f"Unexpected error loading tests: {e}", exc_info=True)
            return
        
        # Validate structure
        if not isinstance(data, dict):
            QtWidgets.QMessageBox.warning(self, 'Invalid Format', 'JSON file must contain an object with a "tests" array')
            return
        
        loaded_tests = data.get('tests', [])
        if not isinstance(loaded_tests, list):
            QtWidgets.QMessageBox.warning(self, 'Invalid Format', 'JSON file "tests" field must be an array')
            return
        
        if not loaded_tests:
            QtWidgets.QMessageBox.warning(self, 'Load Tests', 'JSON file contains no tests. Expected a "tests" array.')
            return
        
        # Validate each test and check for duplicates
        validation_errors = []
        duplicate_names = []
        seen_names = set()
        
        for i, test in enumerate(loaded_tests):
            if not isinstance(test, dict):
                validation_errors.append(f"Test {i+1}: Not a valid object")
                continue
            
            # Check name
            name = test.get('name', '').strip()
            if not name:
                validation_errors.append(f"Test {i+1}: Missing or empty name")
            
            # Check for duplicates
            if name in seen_names:
                duplicate_names.append(name)
            seen_names.add(name)
            
            # Validate test structure
            is_valid, error_msg = self._validate_test(test)
            if not is_valid:
                validation_errors.append(f"Test {i+1} '{name}': {error_msg}")
        
        # Ask user about errors
        if validation_errors:
            error_text = "The loaded file contains validation errors:\n\n" + "\n".join(validation_errors[:10])
            if len(validation_errors) > 10:
                error_text += f"\n... and {len(validation_errors) - 10} more errors"
            error_text += "\n\nContinue loading anyway?"
            reply = QtWidgets.QMessageBox.warning(
                self, 'Validation Errors', error_text,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.No:
                return
        
        if duplicate_names:
            reply = QtWidgets.QMessageBox.warning(
                self, 'Duplicate Names',
                f"The file contains duplicate test names: {', '.join(set(duplicate_names))}\n\n"
                "This may cause issues with test reordering. Continue loading anyway?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.No:
                return
        
        # Ask user if they want to merge or replace
        if self._tests:
            reply = QtWidgets.QMessageBox.question(
                self, 'Merge or Replace?',
                f'You currently have {len(self._tests)} test(s). How would you like to load the file?\n\n'
                'Yes = Replace all current tests\n'
                'No = Merge with current tests\n'
                'Cancel = Do not load',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel
            )
            if reply == QtWidgets.QMessageBox.Cancel:
                return
            elif reply == QtWidgets.QMessageBox.Yes:
                # Replace
                self._tests = loaded_tests
            else:
                # Merge - add with renamed duplicates
                existing_names = {t.get('name', '').strip() for t in self._tests}
                merged_count = 0
                for test in loaded_tests:
                    original_name = test.get('name', '').strip()
                    name = original_name
                    counter = 1
                    while name in existing_names:
                        name = f"{original_name}_loaded_{counter}"
                        counter += 1
                    test['name'] = name
                    self._tests.append(test)
                    existing_names.add(name)
                    merged_count += 1
                QtWidgets.QMessageBox.information(
                    self, 'Merged',
                    f'Merged {merged_count} test(s) from file.\n'
                    f'{merged_count - len(loaded_tests) + len(set(duplicate_names))} name(s) were renamed to avoid conflicts.'
                )
        else:
            # No existing tests, just load
            self._tests = loaded_tests
        
        # Update UI
        self.test_list.clear()
        for t in self._tests:
            self.test_list.addItem(t.get('name', '<unnamed>'))
        
        # Sync Test Plan
        try:
            self._populate_test_plan()
        except Exception:
            pass
        
        logger.info(f"Loaded {len(loaded_tests)} tests from {file_path}")
        QtWidgets.QMessageBox.information(
            self, 'Loaded',
            f'Loaded {len(loaded_tests)} test(s) from {os.path.basename(file_path)}\n'
            f'Total tests now: {len(self._tests)}'
        )

    def _on_test_list_reordered(self, parent, start, end, destination, row):
        """Handle test list reordering via drag-and-drop.
        
        Uses index-based reordering to handle cases where duplicate names might exist.
        """
        try:
            # Build new order based on current list widget order
            new_order = []
            for i in range(self.test_list.count()):
                item = self.test_list.item(i)
                if item is None:
                    continue
                item_text = item.text()
                
                # Find the test that matches this position
                # Try to match by index first (handles duplicates correctly)
                if i < len(self._tests):
                    # Check if item text matches current test at this position
                    current_test = self._tests[i]
                    if current_test.get('name') == item_text:
                        new_order.append(current_test)
                        continue
                
                # Fallback: search by name (only if no duplicates)
                found = False
                for test in self._tests:
                    if test.get('name') == item_text and test not in new_order:
                        new_order.append(test)
                        found = True
                        break
                
                if not found:
                    logger.warning(f"Could not find test matching list item '{item_text}' at position {i}")
            
            # Update _tests if we successfully matched all items
            if len(new_order) == self.test_list.count() == len(self._tests):
                self._tests = new_order
                logger.debug(f"Reordered {len(new_order)} tests")
                # Sync Test Plan (order matters, but we preserve existing statuses)
                try:
                    self._populate_test_plan()
                except Exception:
                    pass
            else:
                logger.error(f"Reorder failed: expected {self.test_list.count()} items, matched {len(new_order)}, have {len(self._tests)} tests")
        except Exception as e:
            logger.error(f"Error during test reorder: {e}", exc_info=True)
            QtWidgets.QMessageBox.warning(self, 'Reorder Error', f'Failed to reorder tests: {e}')

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
        type_combo.addItems(['Digital Logic Test', 'Analog Sweep Test', 'Phase Current Test', 'Analog Static Test', 'Analog PWM Sensor', 'Temperature Validation Test', 'Fan Control Test', 'External 5V Test', 'DC Bus Sensing', 'Output Current Calibration', 'Charged HV Bus Test', 'Charger Functional Test'])
        try:
            type_combo.setCurrentText(data.get('type', 'digital'))
        except Exception:
            pass

        # prepare feedback source + signal similar to Create dialog
        feedback_edit = QtWidgets.QLineEdit(data.get('feedback_signal', ''))
        fb_msg_combo = None
        fb_signal_combo = None
        if self.dbc_service is not None and self.dbc_service.is_loaded():
            fb_messages = list(getattr(self.dbc_service.database, 'messages', []))
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

        # actuation sub-widgets (digital/analog/phase_current_calibration/analog_static/temperature_validation)
        digital_widget = QtWidgets.QWidget(); digital_layout = QtWidgets.QFormLayout(digital_widget)
        analog_widget = QtWidgets.QWidget(); analog_layout = QtWidgets.QFormLayout(analog_widget)
        phase_current_widget = QtWidgets.QWidget(); phase_current_layout = QtWidgets.QFormLayout(phase_current_widget)
        analog_static_widget = QtWidgets.QWidget(); analog_static_layout = QtWidgets.QFormLayout(analog_static_widget)
        temperature_validation_widget = QtWidgets.QWidget(); temperature_validation_layout = QtWidgets.QFormLayout(temperature_validation_widget)
        analog_pwm_sensor_widget_edit = QtWidgets.QWidget(); analog_pwm_sensor_layout_edit = QtWidgets.QFormLayout(analog_pwm_sensor_widget_edit)

        # populate actuation controls from stored data
        act = data.get('actuation', {}) or {}
        if self.dbc_service is not None and self.dbc_service.is_loaded():
            messages = list(getattr(self.dbc_service.database, 'messages', []))
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
            # Expected Gain input (optional, for calibration)
            expected_gain_validator = QtGui.QDoubleValidator(0.000001, 1000000.0, 6, self)
            expected_gain_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            expected_gain_edit = QtWidgets.QLineEdit(str(act.get('expected_gain', '')))
            expected_gain_edit.setValidator(expected_gain_validator)
            expected_gain_edit.setPlaceholderText('Optional: for gain adjustment calculation')
            analog_layout.addRow('Expected Gain (optional):', expected_gain_edit)
            # Gain Tolerance input (optional, for pass/fail determination)
            gain_tolerance_validator = QtGui.QDoubleValidator(0.0, 1000.0, 2, self)
            gain_tolerance_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            gain_tolerance_edit = QtWidgets.QLineEdit(str(act.get('gain_tolerance_percent', '')))
            gain_tolerance_edit.setValidator(gain_tolerance_validator)
            gain_tolerance_edit.setPlaceholderText('Optional: % tolerance for gain error (e.g., 5.0)')
            analog_layout.addRow('Gain Tolerance % (optional):', gain_tolerance_edit)
            
            # Phase Current Calibration fields (DBC-driven) - for edit dialog
            phase_current_cmd_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                phase_current_cmd_msg_combo.addItem(label, fid)
            
            phase_current_trigger_signal_combo = QtWidgets.QComboBox()
            phase_current_iq_ref_signal_combo = QtWidgets.QComboBox()
            phase_current_id_ref_signal_combo = QtWidgets.QComboBox()
            
            def _update_phase_current_cmd_signals_edit(idx=0):
                phase_current_trigger_signal_combo.clear()
                phase_current_iq_ref_signal_combo.clear()
                phase_current_id_ref_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    phase_current_trigger_signal_combo.addItems(sigs)
                    phase_current_iq_ref_signal_combo.addItems(sigs)
                    phase_current_id_ref_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_phase_current_cmd_signals_edit(0)
            phase_current_cmd_msg_combo.currentIndexChanged.connect(_update_phase_current_cmd_signals_edit)
            
            phase_current_msg_combo = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                phase_current_msg_combo.addItem(label, fid)
            
            phase_current_v_signal_combo = QtWidgets.QComboBox()
            phase_current_w_signal_combo = QtWidgets.QComboBox()
            
            def _update_phase_current_signals_edit(idx=0):
                phase_current_v_signal_combo.clear()
                phase_current_w_signal_combo.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    phase_current_v_signal_combo.addItems(sigs)
                    phase_current_w_signal_combo.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_phase_current_signals_edit(0)
            phase_current_msg_combo.currentIndexChanged.connect(_update_phase_current_signals_edit)
            
            # Iq values
            iq_validator = QtGui.QDoubleValidator(-1000.0, 1000.0, 6, self)
            iq_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            min_iq_edit = QtWidgets.QLineEdit(str(act.get('min_iq', '')))
            min_iq_edit.setValidator(iq_validator)
            max_iq_edit = QtWidgets.QLineEdit(str(act.get('max_iq', '')))
            max_iq_edit.setValidator(iq_validator)
            step_iq_edit = QtWidgets.QLineEdit(str(act.get('step_iq', '')))
            step_iq_edit.setValidator(iq_validator)
            
            # IPC Test duration
            duration_validator = QtGui.QIntValidator(0, 60000, self)
            ipc_test_duration_edit = QtWidgets.QLineEdit(str(act.get('ipc_test_duration_ms', '')))
            ipc_test_duration_edit.setValidator(duration_validator)
            
            # Oscilloscope channel dropdowns
            osc_phase_v_ch_combo = QtWidgets.QComboBox()
            osc_phase_w_ch_combo = QtWidgets.QComboBox()
            
            def _update_osc_channel_dropdowns_edit():
                osc_phase_v_ch_combo.clear()
                osc_phase_w_ch_combo.clear()
                enabled_channel_names = []
                if hasattr(self, '_oscilloscope_config') and self._oscilloscope_config:
                    channels = self._oscilloscope_config.get('channels', {})
                    for ch_key in ['CH1', 'CH2', 'CH3', 'CH4']:
                        if ch_key in channels:
                            ch_config = channels[ch_key]
                            if ch_config.get('enabled', False):
                                channel_name = ch_config.get('channel_name', '').strip()
                                if channel_name:
                                    enabled_channel_names.append(channel_name)
                osc_phase_v_ch_combo.addItems(enabled_channel_names)
                osc_phase_w_ch_combo.addItems(enabled_channel_names)
            
            _update_osc_channel_dropdowns_edit()
            
            # Populate phase current fields from stored data
            try:
                cmd_msg_id = act.get('command_message')
                if cmd_msg_id is not None:
                    for i in range(phase_current_cmd_msg_combo.count()):
                        if phase_current_cmd_msg_combo.itemData(i) == cmd_msg_id:
                            phase_current_cmd_msg_combo.setCurrentIndex(i)
                            _update_phase_current_cmd_signals_edit(i)
                            break
                if act.get('trigger_test_signal') and phase_current_trigger_signal_combo.count():
                    phase_current_trigger_signal_combo.setCurrentText(str(act.get('trigger_test_signal')))
                if act.get('iq_ref_signal') and phase_current_iq_ref_signal_combo.count():
                    phase_current_iq_ref_signal_combo.setCurrentText(str(act.get('iq_ref_signal')))
                if act.get('id_ref_signal') and phase_current_id_ref_signal_combo.count():
                    phase_current_id_ref_signal_combo.setCurrentText(str(act.get('id_ref_signal')))
                
                phase_current_can_id = act.get('phase_current_signal_source')
                if phase_current_can_id is not None:
                    for i in range(phase_current_msg_combo.count()):
                        if phase_current_msg_combo.itemData(i) == phase_current_can_id:
                            phase_current_msg_combo.setCurrentIndex(i)
                            _update_phase_current_signals_edit(i)
                            break
                if act.get('phase_current_v_signal') and phase_current_v_signal_combo.count():
                    phase_current_v_signal_combo.setCurrentText(str(act.get('phase_current_v_signal')))
                if act.get('phase_current_w_signal') and phase_current_w_signal_combo.count():
                    phase_current_w_signal_combo.setCurrentText(str(act.get('phase_current_w_signal')))
                
                if act.get('oscilloscope_phase_v_ch') and osc_phase_v_ch_combo.count():
                    osc_phase_v_ch_combo.setCurrentText(str(act.get('oscilloscope_phase_v_ch')))
                if act.get('oscilloscope_phase_w_ch') and osc_phase_w_ch_combo.count():
                    osc_phase_w_ch_combo.setCurrentText(str(act.get('oscilloscope_phase_w_ch')))
            except Exception:
                pass
            
            phase_current_layout.addRow('Command Message:', phase_current_cmd_msg_combo)
            phase_current_layout.addRow('Trigger Test Signal:', phase_current_trigger_signal_combo)
            phase_current_layout.addRow('Iq_ref Signal:', phase_current_iq_ref_signal_combo)
            phase_current_layout.addRow('Id_ref Signal:', phase_current_id_ref_signal_combo)
            phase_current_layout.addRow('Phase Current Signal Source:', phase_current_msg_combo)
            phase_current_layout.addRow('Phase Current V Signal:', phase_current_v_signal_combo)
            phase_current_layout.addRow('Phase Current W Signal:', phase_current_w_signal_combo)
            phase_current_layout.addRow('Min Iq (A):', min_iq_edit)
            phase_current_layout.addRow('Max Iq (A):', max_iq_edit)
            phase_current_layout.addRow('Step Iq (A):', step_iq_edit)
            phase_current_layout.addRow('IPC Test Duration (ms):', ipc_test_duration_edit)
            phase_current_layout.addRow('Oscilloscope Phase V CH:', osc_phase_v_ch_combo)
            phase_current_layout.addRow('Oscilloscope Phase W CH:', osc_phase_w_ch_combo)
            
            # Analog Static Test fields (DBC mode) - for edit dialog
            # Feedback Signal Source: dropdown of CAN Messages
            analog_static_fb_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                analog_static_fb_msg_combo_edit.addItem(label, fid)
            
            # Feedback Signal: dropdown based on selected message
            analog_static_fb_signal_combo_edit = QtWidgets.QComboBox()
            
            # EOL Signal Source: dropdown of CAN Messages
            analog_static_eol_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                analog_static_eol_msg_combo_edit.addItem(label, fid)
            
            # EOL Signal: dropdown based on selected message
            analog_static_eol_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_analog_static_fb_signals_edit(idx=0):
                """Update feedback signal dropdown based on selected message."""
                analog_static_fb_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    analog_static_fb_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            def _update_analog_static_eol_signals_edit(idx=0):
                """Update EOL signal dropdown based on selected message."""
                analog_static_eol_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    analog_static_eol_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_analog_static_fb_signals_edit(0)
                _update_analog_static_eol_signals_edit(0)
            analog_static_fb_msg_combo_edit.currentIndexChanged.connect(_update_analog_static_fb_signals_edit)
            analog_static_eol_msg_combo_edit.currentIndexChanged.connect(_update_analog_static_eol_signals_edit)
            
            # Tolerance input (float, in mV)
            tolerance_validator_edit = QtGui.QDoubleValidator(0.0, 10000.0, 2, self)
            tolerance_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            tolerance_edit_edit = QtWidgets.QLineEdit(str(act.get('tolerance_mv', '')))
            tolerance_edit_edit.setValidator(tolerance_validator_edit)
            tolerance_edit_edit.setPlaceholderText('e.g., 10.0')
            
            # Pre-dwell time input (int, in ms)
            pre_dwell_validator_edit = QtGui.QIntValidator(0, 60000, self)
            pre_dwell_time_edit_edit = QtWidgets.QLineEdit(str(act.get('pre_dwell_time_ms', '')))
            pre_dwell_time_edit_edit.setValidator(pre_dwell_validator_edit)
            pre_dwell_time_edit_edit.setPlaceholderText('e.g., 100')
            
            # Dwell time input (int, in ms)
            dwell_time_validator_edit = QtGui.QIntValidator(1, 60000, self)
            dwell_time_edit_edit = QtWidgets.QLineEdit(str(act.get('dwell_time_ms', '')))
            dwell_time_edit_edit.setValidator(dwell_time_validator_edit)
            dwell_time_edit_edit.setPlaceholderText('e.g., 500')
            
            # Populate analog static fields from stored data
            try:
                fb_msg_id = act.get('feedback_signal_source')
                if fb_msg_id is not None:
                    for i in range(analog_static_fb_msg_combo_edit.count()):
                        if analog_static_fb_msg_combo_edit.itemData(i) == fb_msg_id:
                            analog_static_fb_msg_combo_edit.setCurrentIndex(i)
                            _update_analog_static_fb_signals_edit(i)
                            break
                if act.get('feedback_signal') and analog_static_fb_signal_combo_edit.count():
                    try:
                        analog_static_fb_signal_combo_edit.setCurrentText(str(act.get('feedback_signal')))
                    except Exception:
                        pass
                
                eol_msg_id = act.get('eol_signal_source')
                if eol_msg_id is not None:
                    for i in range(analog_static_eol_msg_combo_edit.count()):
                        if analog_static_eol_msg_combo_edit.itemData(i) == eol_msg_id:
                            analog_static_eol_msg_combo_edit.setCurrentIndex(i)
                            _update_analog_static_eol_signals_edit(i)
                            break
                if act.get('eol_signal') and analog_static_eol_signal_combo_edit.count():
                    try:
                        analog_static_eol_signal_combo_edit.setCurrentText(str(act.get('eol_signal')))
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Populate analog static sub-widget
            analog_static_layout.addRow('Feedback Signal Source:', analog_static_fb_msg_combo_edit)
            analog_static_layout.addRow('Feedback Signal:', analog_static_fb_signal_combo_edit)
            analog_static_layout.addRow('EOL Signal Source:', analog_static_eol_msg_combo_edit)
            analog_static_layout.addRow('EOL Signal:', analog_static_eol_signal_combo_edit)
            analog_static_layout.addRow('Tolerance (mV):', tolerance_edit_edit)
            analog_static_layout.addRow('Pre-dwell Time (ms):', pre_dwell_time_edit_edit)
            analog_static_layout.addRow('Dwell Time (ms):', dwell_time_edit_edit)
            
            # Temperature Validation Test fields (DBC mode) - for edit dialog
            temp_val_fb_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                temp_val_fb_msg_combo_edit.addItem(label, fid)
            
            temp_val_fb_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_temp_val_fb_signals_edit(idx=0):
                """Update feedback signal dropdown based on selected message."""
                temp_val_fb_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    temp_val_fb_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_temp_val_fb_signals_edit(0)
            temp_val_fb_msg_combo_edit.currentIndexChanged.connect(_update_temp_val_fb_signals_edit)
            
            # Reference temperature input (float, in °C)
            reference_validator_edit = QtGui.QDoubleValidator(-273.15, 1000.0, 2, self)
            reference_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            temp_val_reference_edit_edit = QtWidgets.QLineEdit(str(act.get('reference_temperature_c', '')))
            temp_val_reference_edit_edit.setValidator(reference_validator_edit)
            temp_val_reference_edit_edit.setPlaceholderText('e.g., 25.0')
            
            # Tolerance input (float, in °C)
            temp_tolerance_validator_edit = QtGui.QDoubleValidator(0.0, 1000.0, 2, self)
            temp_tolerance_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            temp_val_tolerance_edit_edit = QtWidgets.QLineEdit(str(act.get('tolerance_c', '')))
            temp_val_tolerance_edit_edit.setValidator(temp_tolerance_validator_edit)
            temp_val_tolerance_edit_edit.setPlaceholderText('e.g., 2.0')
            
            # Dwell time input (int, in ms)
            temp_dwell_time_validator_edit = QtGui.QIntValidator(1, 60000, self)
            temp_val_dwell_time_edit_edit = QtWidgets.QLineEdit(str(act.get('dwell_time_ms', '')))
            temp_val_dwell_time_edit_edit.setValidator(temp_dwell_time_validator_edit)
            temp_val_dwell_time_edit_edit.setPlaceholderText('e.g., 1000')
            
            # Populate temperature validation fields from stored data
            try:
                fb_msg_id = act.get('feedback_signal_source')
                if fb_msg_id is not None:
                    for i in range(temp_val_fb_msg_combo_edit.count()):
                        if temp_val_fb_msg_combo_edit.itemData(i) == fb_msg_id:
                            temp_val_fb_msg_combo_edit.setCurrentIndex(i)
                            _update_temp_val_fb_signals_edit(i)
                            break
                if act.get('feedback_signal') and temp_val_fb_signal_combo_edit.count():
                    try:
                        temp_val_fb_signal_combo_edit.setCurrentText(str(act.get('feedback_signal')))
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Populate temperature validation sub-widget
            temperature_validation_layout.addRow('Feedback Signal Source:', temp_val_fb_msg_combo_edit)
            temperature_validation_layout.addRow('Feedback Signal:', temp_val_fb_signal_combo_edit)
            temperature_validation_layout.addRow('Reference Temperature (°C):', temp_val_reference_edit_edit)
            temperature_validation_layout.addRow('Tolerance (°C):', temp_val_tolerance_edit_edit)
            temperature_validation_layout.addRow('Dwell Time (ms):', temp_val_dwell_time_edit_edit)
            
            # Analog PWM Sensor Test fields (DBC mode) - for edit dialog
            analog_pwm_fb_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                analog_pwm_fb_msg_combo_edit.addItem(label, fid)
            
            analog_pwm_frequency_signal_combo_edit = QtWidgets.QComboBox()
            analog_pwm_duty_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_analog_pwm_signals_edit(idx=0):
                """Update both signal dropdowns based on selected message."""
                analog_pwm_frequency_signal_combo_edit.clear()
                analog_pwm_duty_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    analog_pwm_frequency_signal_combo_edit.addItems(sigs)
                    analog_pwm_duty_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_analog_pwm_signals_edit(0)
            analog_pwm_fb_msg_combo_edit.currentIndexChanged.connect(_update_analog_pwm_signals_edit)
            
            # Reference PWM frequency input (float, in Hz)
            pwm_freq_reference_validator_edit = QtGui.QDoubleValidator(0.0, 1000000.0, 2, self)
            pwm_freq_reference_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_reference_frequency_edit_edit = QtWidgets.QLineEdit(str(act.get('reference_pwm_frequency', '')))
            analog_pwm_reference_frequency_edit_edit.setValidator(pwm_freq_reference_validator_edit)
            analog_pwm_reference_frequency_edit_edit.setPlaceholderText('e.g., 1000.0')
            
            # Reference duty input (float, in %)
            duty_reference_validator_edit = QtGui.QDoubleValidator(0.0, 100.0, 2, self)
            duty_reference_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_reference_duty_edit_edit = QtWidgets.QLineEdit(str(act.get('reference_duty', '')))
            analog_pwm_reference_duty_edit_edit.setValidator(duty_reference_validator_edit)
            analog_pwm_reference_duty_edit_edit.setPlaceholderText('e.g., 50.0')
            
            # PWM frequency tolerance input (float, in Hz)
            pwm_freq_tolerance_validator_edit = QtGui.QDoubleValidator(0.0, 1000000.0, 2, self)
            pwm_freq_tolerance_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_frequency_tolerance_edit_edit = QtWidgets.QLineEdit(str(act.get('pwm_frequency_tolerance', '')))
            analog_pwm_frequency_tolerance_edit_edit.setValidator(pwm_freq_tolerance_validator_edit)
            analog_pwm_frequency_tolerance_edit_edit.setPlaceholderText('e.g., 10.0')
            
            # Duty tolerance input (float, in %)
            duty_tolerance_validator_edit = QtGui.QDoubleValidator(0.0, 100.0, 2, self)
            duty_tolerance_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_duty_tolerance_edit_edit = QtWidgets.QLineEdit(str(act.get('duty_tolerance', '')))
            analog_pwm_duty_tolerance_edit_edit.setValidator(duty_tolerance_validator_edit)
            analog_pwm_duty_tolerance_edit_edit.setPlaceholderText('e.g., 1.0')
            
            # Acquisition time input (int, in ms)
            pwm_acquisition_time_validator_edit = QtGui.QIntValidator(1, 60000, self)
            analog_pwm_acquisition_time_edit_edit = QtWidgets.QLineEdit(str(act.get('acquisition_time_ms', '')))
            analog_pwm_acquisition_time_edit_edit.setValidator(pwm_acquisition_time_validator_edit)
            analog_pwm_acquisition_time_edit_edit.setPlaceholderText('e.g., 3000')
            
            # Populate Analog PWM Sensor fields from stored data
            try:
                fb_msg_id = act.get('feedback_signal_source')
                if fb_msg_id is not None:
                    for i in range(analog_pwm_fb_msg_combo_edit.count()):
                        if analog_pwm_fb_msg_combo_edit.itemData(i) == fb_msg_id:
                            analog_pwm_fb_msg_combo_edit.setCurrentIndex(i)
                            _update_analog_pwm_signals_edit(i)
                            break
                if act.get('feedback_pwm_frequency_signal') and analog_pwm_frequency_signal_combo_edit.count():
                    try:
                        analog_pwm_frequency_signal_combo_edit.setCurrentText(str(act.get('feedback_pwm_frequency_signal')))
                    except Exception:
                        pass
                if act.get('feedback_duty_signal') and analog_pwm_duty_signal_combo_edit.count():
                    try:
                        analog_pwm_duty_signal_combo_edit.setCurrentText(str(act.get('feedback_duty_signal')))
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Populate Analog PWM Sensor sub-widget
            analog_pwm_sensor_layout_edit.addRow('Feedback Signal Source:', analog_pwm_fb_msg_combo_edit)
            analog_pwm_sensor_layout_edit.addRow('PWM Frequency Signal:', analog_pwm_frequency_signal_combo_edit)
            analog_pwm_sensor_layout_edit.addRow('Duty Signal:', analog_pwm_duty_signal_combo_edit)
            analog_pwm_sensor_layout_edit.addRow('Reference PWM Frequency (Hz):', analog_pwm_reference_frequency_edit_edit)
            analog_pwm_sensor_layout_edit.addRow('Reference Duty (%):', analog_pwm_reference_duty_edit_edit)
            analog_pwm_sensor_layout_edit.addRow('PWM Frequency Tolerance (Hz):', analog_pwm_frequency_tolerance_edit_edit)
            analog_pwm_sensor_layout_edit.addRow('Duty Tolerance (%):', analog_pwm_duty_tolerance_edit_edit)
            analog_pwm_sensor_layout_edit.addRow('Acquisition Time (ms):', analog_pwm_acquisition_time_edit_edit)
            
            # Fan Control Test fields (DBC mode) - for edit dialog
            # Create container for Fan Control Test (edit)
            fan_control_widget_edit = QtWidgets.QWidget()
            fan_control_layout_edit = QtWidgets.QFormLayout(fan_control_widget_edit)
            
            fan_control_trigger_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                fan_control_trigger_msg_combo_edit.addItem(label, fid)
            
            fan_control_trigger_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_fan_control_trigger_signals_edit(idx=0):
                """Update trigger signal dropdown based on selected message."""
                fan_control_trigger_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    fan_control_trigger_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_fan_control_trigger_signals_edit(0)
            fan_control_trigger_msg_combo_edit.currentIndexChanged.connect(_update_fan_control_trigger_signals_edit)
            
            fan_control_feedback_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                fan_control_feedback_msg_combo_edit.addItem(label, fid)
            
            fan_control_enabled_signal_combo_edit = QtWidgets.QComboBox()
            fan_control_tach_signal_combo_edit = QtWidgets.QComboBox()
            fan_control_fault_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_fan_control_feedback_signals_edit(idx=0):
                """Update all feedback signal dropdowns based on selected message."""
                fan_control_enabled_signal_combo_edit.clear()
                fan_control_tach_signal_combo_edit.clear()
                fan_control_fault_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    fan_control_enabled_signal_combo_edit.addItems(sigs)
                    fan_control_tach_signal_combo_edit.addItems(sigs)
                    fan_control_fault_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_fan_control_feedback_signals_edit(0)
            fan_control_feedback_msg_combo_edit.currentIndexChanged.connect(_update_fan_control_feedback_signals_edit)
            
            # Dwell time input (int, in ms)
            fan_dwell_time_validator_edit = QtGui.QIntValidator(1, 60000, self)
            fan_control_dwell_time_edit_edit = QtWidgets.QLineEdit(str(act.get('dwell_time_ms', '')))
            fan_control_dwell_time_edit_edit.setValidator(fan_dwell_time_validator_edit)
            fan_control_dwell_time_edit_edit.setPlaceholderText('e.g., 1000')
            
            # Test timeout input (int, in ms)
            fan_timeout_validator_edit = QtGui.QIntValidator(1, 60000, self)
            fan_control_timeout_edit_edit = QtWidgets.QLineEdit(str(act.get('test_timeout_ms', '')))
            fan_control_timeout_edit_edit.setValidator(fan_timeout_validator_edit)
            fan_control_timeout_edit_edit.setPlaceholderText('e.g., 5000')
            
            # Populate fan control fields from stored data
            try:
                trigger_msg_id = act.get('fan_test_trigger_source')
                if trigger_msg_id is not None:
                    for i in range(fan_control_trigger_msg_combo_edit.count()):
                        if fan_control_trigger_msg_combo_edit.itemData(i) == trigger_msg_id:
                            fan_control_trigger_msg_combo_edit.setCurrentIndex(i)
                            _update_fan_control_trigger_signals_edit(i)
                            break
                if act.get('fan_test_trigger_signal') and fan_control_trigger_signal_combo_edit.count():
                    try:
                        fan_control_trigger_signal_combo_edit.setCurrentText(str(act.get('fan_test_trigger_signal')))
                    except Exception:
                        pass
                
                feedback_msg_id = act.get('fan_control_feedback_source')
                if feedback_msg_id is not None:
                    for i in range(fan_control_feedback_msg_combo_edit.count()):
                        if fan_control_feedback_msg_combo_edit.itemData(i) == feedback_msg_id:
                            fan_control_feedback_msg_combo_edit.setCurrentIndex(i)
                            _update_fan_control_feedback_signals_edit(i)
                            break
                if act.get('fan_enabled_signal') and fan_control_enabled_signal_combo_edit.count():
                    try:
                        fan_control_enabled_signal_combo_edit.setCurrentText(str(act.get('fan_enabled_signal')))
                    except Exception:
                        pass
                if act.get('fan_tach_feedback_signal') and fan_control_tach_signal_combo_edit.count():
                    try:
                        fan_control_tach_signal_combo_edit.setCurrentText(str(act.get('fan_tach_feedback_signal')))
                    except Exception:
                        pass
                if act.get('fan_fault_feedback_signal') and fan_control_fault_signal_combo_edit.count():
                    try:
                        fan_control_fault_signal_combo_edit.setCurrentText(str(act.get('fan_fault_feedback_signal')))
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Populate fan control sub-widget (edit)
            fan_control_layout_edit.addRow('Fan Test Trigger Source:', fan_control_trigger_msg_combo_edit)
            fan_control_layout_edit.addRow('Fan Test Trigger Signal:', fan_control_trigger_signal_combo_edit)
            fan_control_layout_edit.addRow('Fan Control Feedback Source:', fan_control_feedback_msg_combo_edit)
            fan_control_layout_edit.addRow('Fan Enabled Signal:', fan_control_enabled_signal_combo_edit)
            fan_control_layout_edit.addRow('Fan Tach Feedback Signal:', fan_control_tach_signal_combo_edit)
            fan_control_layout_edit.addRow('Fan Fault Feedback Signal:', fan_control_fault_signal_combo_edit)
            fan_control_layout_edit.addRow('Dwell Time (ms):', fan_control_dwell_time_edit_edit)
            fan_control_layout_edit.addRow('Test Timeout (ms):', fan_control_timeout_edit_edit)
            
            # External 5V Test fields (DBC mode) - for edit dialog
            ext_5v_test_widget_edit = QtWidgets.QWidget()
            ext_5v_test_layout_edit = QtWidgets.QFormLayout(ext_5v_test_widget_edit)
            
            # Ext 5V Test Trigger Source: dropdown of CAN Messages
            ext_5v_test_trigger_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                ext_5v_test_trigger_msg_combo_edit.addItem(label, fid)
            
            # Ext 5V Test Trigger Signal: dropdown based on selected message
            ext_5v_test_trigger_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_ext_5v_test_trigger_signals_edit(idx=0):
                """Update trigger signal dropdown based on selected message."""
                ext_5v_test_trigger_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    ext_5v_test_trigger_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_ext_5v_test_trigger_signals_edit(0)
            ext_5v_test_trigger_msg_combo_edit.currentIndexChanged.connect(_update_ext_5v_test_trigger_signals_edit)
            
            # EOL Ext 5V Measurement Source: dropdown of CAN Messages
            ext_5v_test_eol_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                ext_5v_test_eol_msg_combo_edit.addItem(label, fid)
            
            # EOL Ext 5V Measurement Signal: dropdown based on selected message
            ext_5v_test_eol_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_ext_5v_test_eol_signals_edit(idx=0):
                """Update EOL signal dropdown based on selected message."""
                ext_5v_test_eol_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    ext_5v_test_eol_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_ext_5v_test_eol_signals_edit(0)
            ext_5v_test_eol_msg_combo_edit.currentIndexChanged.connect(_update_ext_5v_test_eol_signals_edit)
            
            # Feedback Signal Source: dropdown of CAN Messages
            ext_5v_test_feedback_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                ext_5v_test_feedback_msg_combo_edit.addItem(label, fid)
            
            # Feedback Signal: dropdown based on selected message
            ext_5v_test_feedback_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_ext_5v_test_feedback_signals_edit(idx=0):
                """Update feedback signal dropdown based on selected message."""
                ext_5v_test_feedback_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    ext_5v_test_feedback_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_ext_5v_test_feedback_signals_edit(0)
            ext_5v_test_feedback_msg_combo_edit.currentIndexChanged.connect(_update_ext_5v_test_feedback_signals_edit)
            
            # Tolerance input (float, in mV)
            ext_5v_tolerance_validator_edit = QtGui.QDoubleValidator(0.0, 10000.0, 2, self)
            ext_5v_tolerance_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            ext_5v_test_tolerance_edit_edit = QtWidgets.QLineEdit(str(act.get('tolerance_mv', '')))
            ext_5v_test_tolerance_edit_edit.setValidator(ext_5v_tolerance_validator_edit)
            ext_5v_test_tolerance_edit_edit.setPlaceholderText('e.g., 50.0')
            
            # Pre-dwell time input (int, in ms)
            ext_5v_pre_dwell_validator_edit = QtGui.QIntValidator(0, 60000, self)
            ext_5v_test_pre_dwell_time_edit_edit = QtWidgets.QLineEdit(str(act.get('pre_dwell_time_ms', '')))
            ext_5v_test_pre_dwell_time_edit_edit.setValidator(ext_5v_pre_dwell_validator_edit)
            ext_5v_test_pre_dwell_time_edit_edit.setPlaceholderText('e.g., 100')
            
            # Dwell time input (int, in ms)
            ext_5v_dwell_time_validator_edit = QtGui.QIntValidator(1, 60000, self)
            ext_5v_test_dwell_time_edit_edit = QtWidgets.QLineEdit(str(act.get('dwell_time_ms', '')))
            ext_5v_test_dwell_time_edit_edit.setValidator(ext_5v_dwell_time_validator_edit)
            ext_5v_test_dwell_time_edit_edit.setPlaceholderText('e.g., 500')
            
            # Populate External 5V Test fields from stored data
            try:
                trigger_msg_id = act.get('ext_5v_test_trigger_source')
                if trigger_msg_id is not None:
                    for i in range(ext_5v_test_trigger_msg_combo_edit.count()):
                        if ext_5v_test_trigger_msg_combo_edit.itemData(i) == trigger_msg_id:
                            ext_5v_test_trigger_msg_combo_edit.setCurrentIndex(i)
                            _update_ext_5v_test_trigger_signals_edit(i)
                            break
                if act.get('ext_5v_test_trigger_signal') and ext_5v_test_trigger_signal_combo_edit.count():
                    try:
                        ext_5v_test_trigger_signal_combo_edit.setCurrentText(str(act.get('ext_5v_test_trigger_signal')))
                    except Exception:
                        pass
                
                eol_msg_id = act.get('eol_ext_5v_measurement_source')
                if eol_msg_id is not None:
                    for i in range(ext_5v_test_eol_msg_combo_edit.count()):
                        if ext_5v_test_eol_msg_combo_edit.itemData(i) == eol_msg_id:
                            ext_5v_test_eol_msg_combo_edit.setCurrentIndex(i)
                            _update_ext_5v_test_eol_signals_edit(i)
                            break
                if act.get('eol_ext_5v_measurement_signal') and ext_5v_test_eol_signal_combo_edit.count():
                    try:
                        ext_5v_test_eol_signal_combo_edit.setCurrentText(str(act.get('eol_ext_5v_measurement_signal')))
                    except Exception:
                        pass
                
                fb_msg_id = act.get('feedback_signal_source')
                if fb_msg_id is not None:
                    for i in range(ext_5v_test_feedback_msg_combo_edit.count()):
                        if ext_5v_test_feedback_msg_combo_edit.itemData(i) == fb_msg_id:
                            ext_5v_test_feedback_msg_combo_edit.setCurrentIndex(i)
                            _update_ext_5v_test_feedback_signals_edit(i)
                            break
                if act.get('feedback_signal') and ext_5v_test_feedback_signal_combo_edit.count():
                    try:
                        ext_5v_test_feedback_signal_combo_edit.setCurrentText(str(act.get('feedback_signal')))
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Populate External 5V Test sub-widget
            ext_5v_test_layout_edit.addRow('Ext 5V Test Trigger Source:', ext_5v_test_trigger_msg_combo_edit)
            ext_5v_test_layout_edit.addRow('Ext 5V Test Trigger Signal:', ext_5v_test_trigger_signal_combo_edit)
            ext_5v_test_layout_edit.addRow('EOL Ext 5V Measurement Source:', ext_5v_test_eol_msg_combo_edit)
            ext_5v_test_layout_edit.addRow('EOL Ext 5V Measurement Signal:', ext_5v_test_eol_signal_combo_edit)
            ext_5v_test_layout_edit.addRow('Feedback Signal Source:', ext_5v_test_feedback_msg_combo_edit)
            ext_5v_test_layout_edit.addRow('Feedback Signal:', ext_5v_test_feedback_signal_combo_edit)
            ext_5v_test_layout_edit.addRow('Tolerance (mV):', ext_5v_test_tolerance_edit_edit)
            ext_5v_test_layout_edit.addRow('Pre-dwell Time (ms):', ext_5v_test_pre_dwell_time_edit_edit)
            ext_5v_test_layout_edit.addRow('Dwell Time (ms):', ext_5v_test_dwell_time_edit_edit)
            
            # DC Bus Sensing Test fields (DBC mode) - for edit dialog
            dc_bus_sensing_widget_edit = QtWidgets.QWidget()
            dc_bus_sensing_layout_edit = QtWidgets.QFormLayout(dc_bus_sensing_widget_edit)
            
            # Oscilloscope Channel: dropdown of enabled channel names from oscilloscope configuration
            dc_bus_osc_channel_combo_edit = QtWidgets.QComboBox()
            # Populate from oscilloscope configuration
            if hasattr(self, '_oscilloscope_config') and self._oscilloscope_config:
                channel_names = self.oscilloscope_service.get_channel_names(self._oscilloscope_config) if self.oscilloscope_service else []
                dc_bus_osc_channel_combo_edit.addItems(channel_names)
            else:
                dc_bus_osc_channel_combo_edit.addItem('No oscilloscope config loaded', None)
            
            # Feedback Signal Source: dropdown of CAN Messages
            dc_bus_feedback_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                dc_bus_feedback_msg_combo_edit.addItem(label, fid)
            
            # Feedback Signal: dropdown based on selected message
            dc_bus_feedback_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_dc_bus_feedback_signals_edit(idx=0):
                """Update feedback signal dropdown based on selected message."""
                dc_bus_feedback_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    dc_bus_feedback_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_dc_bus_feedback_signals_edit(0)
            dc_bus_feedback_msg_combo_edit.currentIndexChanged.connect(_update_dc_bus_feedback_signals_edit)
            
            # Dwell time input (int, in ms)
            dc_bus_dwell_time_validator_edit = QtGui.QIntValidator(1, 60000, self)
            dc_bus_dwell_time_edit_edit = QtWidgets.QLineEdit(str(act.get('dwell_time_ms', '')))
            dc_bus_dwell_time_edit_edit.setValidator(dc_bus_dwell_time_validator_edit)
            dc_bus_dwell_time_edit_edit.setPlaceholderText('e.g., 500')
            
            # Tolerance input (float, in V)
            dc_bus_tolerance_validator_edit = QtGui.QDoubleValidator(0.0, 1000.0, 4, self)
            dc_bus_tolerance_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            dc_bus_tolerance_edit_edit = QtWidgets.QLineEdit(str(act.get('tolerance_v', '')))
            dc_bus_tolerance_edit_edit.setValidator(dc_bus_tolerance_validator_edit)
            dc_bus_tolerance_edit_edit.setPlaceholderText('e.g., 0.1')
            
            # Populate DC Bus Sensing fields from stored data
            try:
                osc_channel = act.get('oscilloscope_channel', '')
                if osc_channel and dc_bus_osc_channel_combo_edit.count():
                    try:
                        dc_bus_osc_channel_combo_edit.setCurrentText(osc_channel)
                    except Exception:
                        pass
                
                fb_msg_id = act.get('feedback_signal_source')
                if fb_msg_id is not None:
                    for i in range(dc_bus_feedback_msg_combo_edit.count()):
                        if dc_bus_feedback_msg_combo_edit.itemData(i) == fb_msg_id:
                            dc_bus_feedback_msg_combo_edit.setCurrentIndex(i)
                            _update_dc_bus_feedback_signals_edit(i)
                            break
                if act.get('feedback_signal') and dc_bus_feedback_signal_combo_edit.count():
                    try:
                        dc_bus_feedback_signal_combo_edit.setCurrentText(str(act.get('feedback_signal')))
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Populate DC Bus Sensing Test sub-widget
            dc_bus_sensing_layout_edit.addRow('Oscilloscope Channel:', dc_bus_osc_channel_combo_edit)
            dc_bus_sensing_layout_edit.addRow('Feedback Signal Source:', dc_bus_feedback_msg_combo_edit)
            dc_bus_sensing_layout_edit.addRow('Feedback Signal:', dc_bus_feedback_signal_combo_edit)
            dc_bus_sensing_layout_edit.addRow('Dwell Time (ms):', dc_bus_dwell_time_edit_edit)
            dc_bus_sensing_layout_edit.addRow('Tolerance (V):', dc_bus_tolerance_edit_edit)
            
            # Output Current Calibration Test fields (DBC mode) - for edit dialog
            output_current_calibration_widget_edit = QtWidgets.QWidget()
            output_current_calibration_layout_edit = QtWidgets.QFormLayout(output_current_calibration_widget_edit)
            
            # Test Trigger Source: dropdown of CAN Messages
            output_current_trigger_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                output_current_trigger_msg_combo_edit.addItem(label, fid)
            
            # Test Trigger Signal: dropdown based on selected message
            output_current_trigger_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_output_current_trigger_signals_edit(idx=0):
                """Update trigger signal dropdown based on selected message."""
                output_current_trigger_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    output_current_trigger_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_output_current_trigger_signals_edit(0)
            output_current_trigger_msg_combo_edit.currentIndexChanged.connect(_update_output_current_trigger_signals_edit)
            
            # Test Trigger Signal Value: integer input (0-255)
            output_current_trigger_value_validator_edit = QtGui.QIntValidator(0, 255, self)
            output_current_trigger_value_edit_edit = QtWidgets.QLineEdit(str(act.get('test_trigger_signal_value', '')))
            output_current_trigger_value_edit_edit.setValidator(output_current_trigger_value_validator_edit)
            output_current_trigger_value_edit_edit.setPlaceholderText('e.g., 1 (to enable)')
            
            # Current Setpoint Signal: dropdown based on same message as trigger
            output_current_setpoint_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_output_current_setpoint_signals_edit():
                """Update setpoint signal dropdown based on trigger message selection."""
                output_current_setpoint_signal_combo_edit.clear()
                try:
                    idx = output_current_trigger_msg_combo_edit.currentIndex()
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    output_current_setpoint_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_output_current_setpoint_signals_edit()
            output_current_trigger_msg_combo_edit.currentIndexChanged.connect(_update_output_current_setpoint_signals_edit)
            
            # Output Current Trim Signal: dropdown based on same message as trigger
            output_current_trim_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_output_current_trim_signals_edit():
                """Update trim signal dropdown based on trigger message selection."""
                output_current_trim_signal_combo_edit.clear()
                try:
                    idx = output_current_trigger_msg_combo_edit.currentIndex()
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    output_current_trim_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_output_current_trim_signals_edit()
            output_current_trigger_msg_combo_edit.currentIndexChanged.connect(_update_output_current_trim_signals_edit)
            
            # Initial Trim Value: double input (0.0000-200.0000, default 100.0000)
            output_current_initial_trim_validator_edit = QtGui.QDoubleValidator(0.0, 200.0, 4, self)
            output_current_initial_trim_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            output_current_initial_trim_edit_edit = QtWidgets.QLineEdit(str(act.get('initial_trim_value', '100.0000')))
            output_current_initial_trim_edit_edit.setValidator(output_current_initial_trim_validator_edit)
            output_current_initial_trim_edit_edit.setPlaceholderText('e.g., 100.0000')
            
            # Feedback Signal Source: dropdown of CAN Messages
            output_current_feedback_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                output_current_feedback_msg_combo_edit.addItem(label, fid)
            
            # Feedback Signal: dropdown based on selected message
            output_current_feedback_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_output_current_feedback_signals_edit(idx=0):
                """Update feedback signal dropdown based on selected message."""
                output_current_feedback_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    output_current_feedback_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_output_current_feedback_signals_edit(0)
            output_current_feedback_msg_combo_edit.currentIndexChanged.connect(_update_output_current_feedback_signals_edit)
            
            # Oscilloscope Channel: dropdown of enabled channel names
            output_current_osc_channel_combo_edit = QtWidgets.QComboBox()
            if hasattr(self, '_oscilloscope_config') and self._oscilloscope_config:
                channel_names = self.oscilloscope_service.get_channel_names(self._oscilloscope_config) if self.oscilloscope_service else []
                output_current_osc_channel_combo_edit.addItems(channel_names)
            else:
                output_current_osc_channel_combo_edit.addItem('No oscilloscope config loaded', None)
            
            # Oscilloscope Timebase: dropdown
            output_current_timebase_combo_edit = QtWidgets.QComboBox()
            output_current_timebase_combo_edit.addItems(['10MS', '20MS', '100MS', '500MS'])
            
            # Minimum Test Current: double input (>= 0, default 5.0)
            output_current_min_current_validator_edit = QtGui.QDoubleValidator(0.0, 1000.0, 3, self)
            output_current_min_current_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            output_current_min_current_edit_edit = QtWidgets.QLineEdit(str(act.get('minimum_test_current', '5.0')))
            output_current_min_current_edit_edit.setValidator(output_current_min_current_validator_edit)
            output_current_min_current_edit_edit.setPlaceholderText('e.g., 5.0')
            
            # Maximum Test Current: double input (>= minimum, default 20.0)
            output_current_max_current_validator_edit = QtGui.QDoubleValidator(0.0, 1000.0, 3, self)
            output_current_max_current_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            output_current_max_current_edit_edit = QtWidgets.QLineEdit(str(act.get('maximum_test_current', '20.0')))
            output_current_max_current_edit_edit.setValidator(output_current_max_current_validator_edit)
            output_current_max_current_edit_edit.setPlaceholderText('e.g., 20.0')
            
            # Step Current: double input (>= 0.1, default 5.0)
            output_current_step_current_validator_edit = QtGui.QDoubleValidator(0.1, 1000.0, 3, self)
            output_current_step_current_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            output_current_step_current_edit_edit = QtWidgets.QLineEdit(str(act.get('step_current', '5.0')))
            output_current_step_current_edit_edit.setValidator(output_current_step_current_validator_edit)
            output_current_step_current_edit_edit.setPlaceholderText('e.g., 5.0')
            
            # Pre-Acquisition Time: integer input (>= 0, default 1000)
            output_current_pre_acq_validator_edit = QtGui.QIntValidator(0, 60000, self)
            output_current_pre_acq_edit_edit = QtWidgets.QLineEdit(str(act.get('pre_acquisition_time_ms', '1000')))
            output_current_pre_acq_edit_edit.setValidator(output_current_pre_acq_validator_edit)
            output_current_pre_acq_edit_edit.setPlaceholderText('e.g., 1000')
            
            # Acquisition Time: integer input (>= 1, default 3000)
            output_current_acq_validator_edit = QtGui.QIntValidator(1, 60000, self)
            output_current_acq_edit_edit = QtWidgets.QLineEdit(str(act.get('acquisition_time_ms', '3000')))
            output_current_acq_edit_edit.setValidator(output_current_acq_validator_edit)
            output_current_acq_edit_edit.setPlaceholderText('e.g., 3000')
            
            # Tolerance: double input (>= 0, default 1.0)
            output_current_tolerance_validator_edit = QtGui.QDoubleValidator(0.0, 100.0, 3, self)
            output_current_tolerance_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            output_current_tolerance_edit_edit = QtWidgets.QLineEdit(str(act.get('tolerance_percent', '1.0')))
            output_current_tolerance_edit_edit.setValidator(output_current_tolerance_validator_edit)
            output_current_tolerance_edit_edit.setPlaceholderText('e.g., 1.0')
            
            # Populate Output Current Calibration fields from stored data
            try:
                trigger_msg_id = act.get('test_trigger_source')
                if trigger_msg_id is not None:
                    for i in range(output_current_trigger_msg_combo_edit.count()):
                        if output_current_trigger_msg_combo_edit.itemData(i) == trigger_msg_id:
                            output_current_trigger_msg_combo_edit.setCurrentIndex(i)
                            _update_output_current_trigger_signals_edit(i)
                            break
                if act.get('test_trigger_signal') and output_current_trigger_signal_combo_edit.count():
                    try:
                        output_current_trigger_signal_combo_edit.setCurrentText(str(act.get('test_trigger_signal')))
                    except Exception:
                        pass
                
                if act.get('current_setpoint_signal') and output_current_setpoint_signal_combo_edit.count():
                    try:
                        output_current_setpoint_signal_combo_edit.setCurrentText(str(act.get('current_setpoint_signal')))
                    except Exception:
                        pass
                
                if act.get('output_current_trim_signal') and output_current_trim_signal_combo_edit.count():
                    try:
                        output_current_trim_signal_combo_edit.setCurrentText(str(act.get('output_current_trim_signal')))
                    except Exception:
                        pass
                
                fb_msg_id = act.get('feedback_signal_source')
                if fb_msg_id is not None:
                    for i in range(output_current_feedback_msg_combo_edit.count()):
                        if output_current_feedback_msg_combo_edit.itemData(i) == fb_msg_id:
                            output_current_feedback_msg_combo_edit.setCurrentIndex(i)
                            _update_output_current_feedback_signals_edit(i)
                            break
                if act.get('feedback_signal') and output_current_feedback_signal_combo_edit.count():
                    try:
                        output_current_feedback_signal_combo_edit.setCurrentText(str(act.get('feedback_signal')))
                    except Exception:
                        pass
                
                osc_channel = act.get('oscilloscope_channel', '')
                if osc_channel and output_current_osc_channel_combo_edit.count():
                    try:
                        output_current_osc_channel_combo_edit.setCurrentText(osc_channel)
                    except Exception:
                        pass
                
                timebase = act.get('oscilloscope_timebase', '')
                if timebase and output_current_timebase_combo_edit.count():
                    try:
                        output_current_timebase_combo_edit.setCurrentText(timebase)
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Populate Output Current Calibration Test sub-widget
            output_current_calibration_layout_edit.addRow('Test Trigger Source:', output_current_trigger_msg_combo_edit)
            output_current_calibration_layout_edit.addRow('Test Trigger Signal:', output_current_trigger_signal_combo_edit)
            output_current_calibration_layout_edit.addRow('Test Trigger Signal Value:', output_current_trigger_value_edit_edit)
            output_current_calibration_layout_edit.addRow('Current Setpoint Signal:', output_current_setpoint_signal_combo_edit)
            output_current_calibration_layout_edit.addRow('Output Current Trim Signal:', output_current_trim_signal_combo_edit)
            output_current_calibration_layout_edit.addRow('Initial Trim Value (%):', output_current_initial_trim_edit_edit)
            output_current_calibration_layout_edit.addRow('Feedback Signal Source:', output_current_feedback_msg_combo_edit)
            output_current_calibration_layout_edit.addRow('Feedback Signal:', output_current_feedback_signal_combo_edit)
            output_current_calibration_layout_edit.addRow('Oscilloscope Channel:', output_current_osc_channel_combo_edit)
            output_current_calibration_layout_edit.addRow('Oscilloscope Timebase:', output_current_timebase_combo_edit)
            output_current_calibration_layout_edit.addRow('Minimum Test Current (A):', output_current_min_current_edit_edit)
            output_current_calibration_layout_edit.addRow('Maximum Test Current (A):', output_current_max_current_edit_edit)
            output_current_calibration_layout_edit.addRow('Step Current (A):', output_current_step_current_edit_edit)
            output_current_calibration_layout_edit.addRow('Pre-Acquisition Time (ms):', output_current_pre_acq_edit_edit)
            output_current_calibration_layout_edit.addRow('Acquisition Time (ms):', output_current_acq_edit_edit)
            output_current_calibration_layout_edit.addRow('Tolerance (%):', output_current_tolerance_edit_edit)
            
            # Charged HV Bus Test fields (DBC mode) - for edit dialog
            charged_hv_bus_widget_edit = QtWidgets.QWidget()
            charged_hv_bus_layout_edit = QtWidgets.QFormLayout(charged_hv_bus_widget_edit)
            
            # Command Signal Source: dropdown of CAN Messages
            charged_hv_bus_cmd_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                charged_hv_bus_cmd_msg_combo_edit.addItem(label, fid)
            
            # Test Trigger Signal: dropdown based on selected message
            charged_hv_bus_trigger_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_charged_hv_bus_trigger_signals_edit(idx=0):
                """Update trigger signal dropdown based on selected message."""
                charged_hv_bus_trigger_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    charged_hv_bus_trigger_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_charged_hv_bus_trigger_signals_edit(0)
            charged_hv_bus_cmd_msg_combo_edit.currentIndexChanged.connect(_update_charged_hv_bus_trigger_signals_edit)
            
            # Test Trigger Signal Value: integer input (0-255)
            charged_hv_bus_trigger_value_validator_edit = QtGui.QIntValidator(0, 255, self)
            charged_hv_bus_trigger_value_edit_edit = QtWidgets.QLineEdit(str(act.get('test_trigger_signal_value', '1')))
            charged_hv_bus_trigger_value_edit_edit.setValidator(charged_hv_bus_trigger_value_validator_edit)
            charged_hv_bus_trigger_value_edit_edit.setPlaceholderText('e.g., 1')
            
            # Set Output Current Trim Value Signal: dropdown based on command message
            charged_hv_bus_trim_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_charged_hv_bus_trim_signals_edit():
                """Update trim signal dropdown based on command message selection."""
                charged_hv_bus_trim_signal_combo_edit.clear()
                try:
                    idx = charged_hv_bus_cmd_msg_combo_edit.currentIndex()
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    charged_hv_bus_trim_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_charged_hv_bus_trim_signals_edit()
            charged_hv_bus_cmd_msg_combo_edit.currentIndexChanged.connect(_update_charged_hv_bus_trim_signals_edit)
            
            # Fallback Output Current Trim Value: double input (0-200)
            charged_hv_bus_fallback_trim_validator_edit = QtGui.QDoubleValidator(0.0, 200.0, 2, self)
            charged_hv_bus_fallback_trim_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            charged_hv_bus_fallback_trim_edit_edit = QtWidgets.QLineEdit(str(act.get('fallback_output_current_trim_value', '100.0')))
            charged_hv_bus_fallback_trim_edit_edit.setValidator(charged_hv_bus_fallback_trim_validator_edit)
            charged_hv_bus_fallback_trim_edit_edit.setPlaceholderText('e.g., 100.0')
            
            # Set Output Current Setpoint Signal: dropdown based on command message
            charged_hv_bus_setpoint_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_charged_hv_bus_setpoint_signals_edit():
                """Update setpoint signal dropdown based on command message selection."""
                charged_hv_bus_setpoint_signal_combo_edit.clear()
                try:
                    idx = charged_hv_bus_cmd_msg_combo_edit.currentIndex()
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    charged_hv_bus_setpoint_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_charged_hv_bus_setpoint_signals_edit()
            charged_hv_bus_cmd_msg_combo_edit.currentIndexChanged.connect(_update_charged_hv_bus_setpoint_signals_edit)
            
            # Output Test Current: double input (0-40)
            charged_hv_bus_output_current_validator_edit = QtGui.QDoubleValidator(0.0, 40.0, 3, self)
            charged_hv_bus_output_current_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            charged_hv_bus_output_current_edit_edit = QtWidgets.QLineEdit(str(act.get('output_test_current', '10.0')))
            charged_hv_bus_output_current_edit_edit.setValidator(charged_hv_bus_output_current_validator_edit)
            charged_hv_bus_output_current_edit_edit.setPlaceholderText('e.g., 10.0')
            
            # Feedback Signal Source: dropdown of CAN Messages
            charged_hv_bus_feedback_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                charged_hv_bus_feedback_msg_combo_edit.addItem(label, fid)
            
            # DUT Test State Signal: dropdown based on selected message
            charged_hv_bus_dut_state_signal_combo_edit = QtWidgets.QComboBox()
            # Enable Relay Signal: dropdown based on selected message
            charged_hv_bus_enable_relay_signal_combo_edit = QtWidgets.QComboBox()
            # Enable PFC Signal: dropdown based on selected message
            charged_hv_bus_enable_pfc_signal_combo_edit = QtWidgets.QComboBox()
            # PFC Power Good Signal: dropdown based on selected message
            charged_hv_bus_pfc_power_good_signal_combo_edit = QtWidgets.QComboBox()
            # PCMC Signal: dropdown based on selected message
            charged_hv_bus_pcmc_signal_combo_edit = QtWidgets.QComboBox()
            # PSFB Fault Signal: dropdown based on selected message
            charged_hv_bus_psfb_fault_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_charged_hv_bus_feedback_signals_edit(idx=0):
                """Update all feedback signal dropdowns based on selected message."""
                charged_hv_bus_dut_state_signal_combo_edit.clear()
                charged_hv_bus_enable_relay_signal_combo_edit.clear()
                charged_hv_bus_enable_pfc_signal_combo_edit.clear()
                charged_hv_bus_pfc_power_good_signal_combo_edit.clear()
                charged_hv_bus_pcmc_signal_combo_edit.clear()
                charged_hv_bus_psfb_fault_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    charged_hv_bus_dut_state_signal_combo_edit.addItems(sigs)
                    charged_hv_bus_enable_relay_signal_combo_edit.addItems(sigs)
                    charged_hv_bus_enable_pfc_signal_combo_edit.addItems(sigs)
                    charged_hv_bus_pfc_power_good_signal_combo_edit.addItems(sigs)
                    charged_hv_bus_pcmc_signal_combo_edit.addItems(sigs)
                    charged_hv_bus_psfb_fault_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_charged_hv_bus_feedback_signals_edit(0)
            charged_hv_bus_feedback_msg_combo_edit.currentIndexChanged.connect(_update_charged_hv_bus_feedback_signals_edit)
            
            # Test Time: integer input (>= 1000)
            charged_hv_bus_test_time_validator_edit = QtGui.QIntValidator(1000, 600000, self)
            charged_hv_bus_test_time_edit_edit = QtWidgets.QLineEdit(str(act.get('test_time_ms', '30000')))
            charged_hv_bus_test_time_edit_edit.setValidator(charged_hv_bus_test_time_validator_edit)
            charged_hv_bus_test_time_edit_edit.setPlaceholderText('e.g., 30000')
            
            # Populate Charged HV Bus Test fields from stored data
            try:
                cmd_msg_id = act.get('command_signal_source')
                if cmd_msg_id is not None:
                    for i in range(charged_hv_bus_cmd_msg_combo_edit.count()):
                        if charged_hv_bus_cmd_msg_combo_edit.itemData(i) == cmd_msg_id:
                            charged_hv_bus_cmd_msg_combo_edit.setCurrentIndex(i)
                            _update_charged_hv_bus_trigger_signals_edit(i)
                            _update_charged_hv_bus_trim_signals_edit()
                            _update_charged_hv_bus_setpoint_signals_edit()
                            break
                if act.get('test_trigger_signal') and charged_hv_bus_trigger_signal_combo_edit.count():
                    try:
                        charged_hv_bus_trigger_signal_combo_edit.setCurrentText(str(act.get('test_trigger_signal')))
                    except Exception:
                        pass
                if act.get('set_output_current_trim_signal') and charged_hv_bus_trim_signal_combo_edit.count():
                    try:
                        charged_hv_bus_trim_signal_combo_edit.setCurrentText(str(act.get('set_output_current_trim_signal')))
                    except Exception:
                        pass
                if act.get('set_output_current_setpoint_signal') and charged_hv_bus_setpoint_signal_combo_edit.count():
                    try:
                        charged_hv_bus_setpoint_signal_combo_edit.setCurrentText(str(act.get('set_output_current_setpoint_signal')))
                    except Exception:
                        pass
                fb_msg_id = act.get('feedback_signal_source')
                if fb_msg_id is not None:
                    for i in range(charged_hv_bus_feedback_msg_combo_edit.count()):
                        if charged_hv_bus_feedback_msg_combo_edit.itemData(i) == fb_msg_id:
                            charged_hv_bus_feedback_msg_combo_edit.setCurrentIndex(i)
                            _update_charged_hv_bus_feedback_signals_edit(i)
                            break
                if act.get('dut_test_state_signal') and charged_hv_bus_dut_state_signal_combo_edit.count():
                    try:
                        charged_hv_bus_dut_state_signal_combo_edit.setCurrentText(str(act.get('dut_test_state_signal')))
                    except Exception:
                        pass
                if act.get('enable_relay_signal') and charged_hv_bus_enable_relay_signal_combo_edit.count():
                    try:
                        charged_hv_bus_enable_relay_signal_combo_edit.setCurrentText(str(act.get('enable_relay_signal')))
                    except Exception:
                        pass
                if act.get('enable_pfc_signal') and charged_hv_bus_enable_pfc_signal_combo_edit.count():
                    try:
                        charged_hv_bus_enable_pfc_signal_combo_edit.setCurrentText(str(act.get('enable_pfc_signal')))
                    except Exception:
                        pass
                if act.get('pfc_power_good_signal') and charged_hv_bus_pfc_power_good_signal_combo_edit.count():
                    try:
                        charged_hv_bus_pfc_power_good_signal_combo_edit.setCurrentText(str(act.get('pfc_power_good_signal')))
                    except Exception:
                        pass
                if act.get('pcmc_signal') and charged_hv_bus_pcmc_signal_combo_edit.count():
                    try:
                        charged_hv_bus_pcmc_signal_combo_edit.setCurrentText(str(act.get('pcmc_signal')))
                    except Exception:
                        pass
                if act.get('psfb_fault_signal') and charged_hv_bus_psfb_fault_signal_combo_edit.count():
                    try:
                        charged_hv_bus_psfb_fault_signal_combo_edit.setCurrentText(str(act.get('psfb_fault_signal')))
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Populate Charged HV Bus Test sub-widget
            charged_hv_bus_layout_edit.addRow('Command Signal Source:', charged_hv_bus_cmd_msg_combo_edit)
            charged_hv_bus_layout_edit.addRow('Test Trigger Signal:', charged_hv_bus_trigger_signal_combo_edit)
            charged_hv_bus_layout_edit.addRow('Test Trigger Signal Value:', charged_hv_bus_trigger_value_edit_edit)
            charged_hv_bus_layout_edit.addRow('Set Output Current Trim Value Signal:', charged_hv_bus_trim_signal_combo_edit)
            charged_hv_bus_layout_edit.addRow('Fallback Output Current Trim Value (%):', charged_hv_bus_fallback_trim_edit_edit)
            charged_hv_bus_layout_edit.addRow('Set Output Current Setpoint Signal:', charged_hv_bus_setpoint_signal_combo_edit)
            charged_hv_bus_layout_edit.addRow('Output Test Current (A):', charged_hv_bus_output_current_edit_edit)
            charged_hv_bus_layout_edit.addRow('Feedback Signal Source:', charged_hv_bus_feedback_msg_combo_edit)
            charged_hv_bus_layout_edit.addRow('DUT Test State Signal:', charged_hv_bus_dut_state_signal_combo_edit)
            charged_hv_bus_layout_edit.addRow('Enable Relay Signal:', charged_hv_bus_enable_relay_signal_combo_edit)
            charged_hv_bus_layout_edit.addRow('Enable PFC Signal:', charged_hv_bus_enable_pfc_signal_combo_edit)
            charged_hv_bus_layout_edit.addRow('PFC Power Good Signal:', charged_hv_bus_pfc_power_good_signal_combo_edit)
            charged_hv_bus_layout_edit.addRow('PCMC Signal:', charged_hv_bus_pcmc_signal_combo_edit)
            charged_hv_bus_layout_edit.addRow('PSFB Fault Signal:', charged_hv_bus_psfb_fault_signal_combo_edit)
            charged_hv_bus_layout_edit.addRow('Test Time (ms):', charged_hv_bus_test_time_edit_edit)
            
            # Charger Functional Test fields (DBC mode) - for edit dialog
            charger_functional_widget_edit = QtWidgets.QWidget()
            charger_functional_layout_edit = QtWidgets.QFormLayout(charger_functional_widget_edit)
            
            # Command Signal Source: dropdown of CAN Messages
            charger_functional_cmd_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                charger_functional_cmd_msg_combo_edit.addItem(label, fid)
            
            # Test Trigger Signal: dropdown based on selected message
            charger_functional_trigger_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_charger_functional_trigger_signals_edit(idx=0):
                charger_functional_trigger_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    charger_functional_trigger_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_charger_functional_trigger_signals_edit(0)
            charger_functional_cmd_msg_combo_edit.currentIndexChanged.connect(_update_charger_functional_trigger_signals_edit)
            
            # Test Trigger Signal Value: integer input (0-255)
            charger_functional_trigger_value_validator_edit = QtGui.QIntValidator(0, 255, self)
            charger_functional_trigger_value_edit_edit = QtWidgets.QLineEdit(str(act.get('test_trigger_signal_value', '1')))
            charger_functional_trigger_value_edit_edit.setValidator(charger_functional_trigger_value_validator_edit)
            charger_functional_trigger_value_edit_edit.setPlaceholderText('e.g., 1')
            
            # Set Output Current Trim Value Signal: dropdown based on command message
            charger_functional_trim_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_charger_functional_trim_signals_edit():
                charger_functional_trim_signal_combo_edit.clear()
                try:
                    idx = charger_functional_cmd_msg_combo_edit.currentIndex()
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    charger_functional_trim_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_charger_functional_trim_signals_edit()
            charger_functional_cmd_msg_combo_edit.currentIndexChanged.connect(_update_charger_functional_trim_signals_edit)
            
            # Fallback Output Current Trim Value: double input (0-200)
            charger_functional_fallback_trim_validator_edit = QtGui.QDoubleValidator(0.0, 200.0, 2, self)
            charger_functional_fallback_trim_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            charger_functional_fallback_trim_edit_edit = QtWidgets.QLineEdit(str(act.get('fallback_output_current_trim_value', '100.0')))
            charger_functional_fallback_trim_edit_edit.setValidator(charger_functional_fallback_trim_validator_edit)
            charger_functional_fallback_trim_edit_edit.setPlaceholderText('e.g., 100.0')
            
            # Set Output Current Setpoint Signal: dropdown based on command message
            charger_functional_setpoint_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_charger_functional_setpoint_signals_edit():
                charger_functional_setpoint_signal_combo_edit.clear()
                try:
                    idx = charger_functional_cmd_msg_combo_edit.currentIndex()
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    charger_functional_setpoint_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_charger_functional_setpoint_signals_edit()
            charger_functional_cmd_msg_combo_edit.currentIndexChanged.connect(_update_charger_functional_setpoint_signals_edit)
            
            # Output Test Current: double input (0-40)
            charger_functional_output_current_validator_edit = QtGui.QDoubleValidator(0.0, 40.0, 3, self)
            charger_functional_output_current_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            charger_functional_output_current_edit_edit = QtWidgets.QLineEdit(str(act.get('output_test_current', '10.0')))
            charger_functional_output_current_edit_edit.setValidator(charger_functional_output_current_validator_edit)
            charger_functional_output_current_edit_edit.setPlaceholderText('e.g., 10.0')
            
            # Feedback Signal Source: dropdown of CAN Messages
            charger_functional_feedback_msg_combo_edit = QtWidgets.QComboBox()
            for m, label in msg_display:
                fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
                charger_functional_feedback_msg_combo_edit.addItem(label, fid)
            
            # DUT Test State Signal: dropdown based on selected message
            charger_functional_dut_state_signal_combo_edit = QtWidgets.QComboBox()
            # Enable Relay Signal: dropdown based on selected message
            charger_functional_enable_relay_signal_combo_edit = QtWidgets.QComboBox()
            # Enable PFC Signal: dropdown based on selected message
            charger_functional_enable_pfc_signal_combo_edit = QtWidgets.QComboBox()
            # PFC Power Good Signal: dropdown based on selected message
            charger_functional_pfc_power_good_signal_combo_edit = QtWidgets.QComboBox()
            # PCMC Signal: dropdown based on selected message
            charger_functional_pcmc_signal_combo_edit = QtWidgets.QComboBox()
            # Output Current Signal: dropdown based on selected message
            charger_functional_output_current_signal_combo_edit = QtWidgets.QComboBox()
            # PSFB Fault Signal: dropdown based on selected message
            charger_functional_psfb_fault_signal_combo_edit = QtWidgets.QComboBox()
            
            def _update_charger_functional_feedback_signals_edit(idx=0):
                charger_functional_dut_state_signal_combo_edit.clear()
                charger_functional_enable_relay_signal_combo_edit.clear()
                charger_functional_enable_pfc_signal_combo_edit.clear()
                charger_functional_pfc_power_good_signal_combo_edit.clear()
                charger_functional_pcmc_signal_combo_edit.clear()
                charger_functional_output_current_signal_combo_edit.clear()
                charger_functional_psfb_fault_signal_combo_edit.clear()
                try:
                    m = messages[idx]
                    sigs = [s.name for s in getattr(m, 'signals', [])]
                    charger_functional_dut_state_signal_combo_edit.addItems(sigs)
                    charger_functional_enable_relay_signal_combo_edit.addItems(sigs)
                    charger_functional_enable_pfc_signal_combo_edit.addItems(sigs)
                    charger_functional_pfc_power_good_signal_combo_edit.addItems(sigs)
                    charger_functional_pcmc_signal_combo_edit.addItems(sigs)
                    charger_functional_output_current_signal_combo_edit.addItems(sigs)
                    charger_functional_psfb_fault_signal_combo_edit.addItems(sigs)
                except Exception:
                    pass
            
            if msg_display:
                _update_charger_functional_feedback_signals_edit(0)
            charger_functional_feedback_msg_combo_edit.currentIndexChanged.connect(_update_charger_functional_feedback_signals_edit)
            
            # Output Current Tolerance: double input (>= 0)
            charger_functional_output_current_tolerance_validator_edit = QtGui.QDoubleValidator(0.0, 999.0, 2, self)
            charger_functional_output_current_tolerance_validator_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            charger_functional_output_current_tolerance_edit_edit = QtWidgets.QLineEdit(str(act.get('output_current_tolerance', '0.5')))
            charger_functional_output_current_tolerance_edit_edit.setValidator(charger_functional_output_current_tolerance_validator_edit)
            charger_functional_output_current_tolerance_edit_edit.setPlaceholderText('e.g., 0.5')
            
            # Test Time: integer input (>= 1000)
            charger_functional_test_time_validator_edit = QtGui.QIntValidator(1000, 600000, self)
            charger_functional_test_time_edit_edit = QtWidgets.QLineEdit(str(act.get('test_time_ms', '30000')))
            charger_functional_test_time_edit_edit.setValidator(charger_functional_test_time_validator_edit)
            charger_functional_test_time_edit_edit.setPlaceholderText('e.g., 30000')
            
            # Populate Charger Functional Test fields from stored data
            try:
                cmd_msg_id = act.get('command_signal_source')
                if cmd_msg_id is not None:
                    for i in range(charger_functional_cmd_msg_combo_edit.count()):
                        if charger_functional_cmd_msg_combo_edit.itemData(i) == cmd_msg_id:
                            charger_functional_cmd_msg_combo_edit.setCurrentIndex(i)
                            _update_charger_functional_trigger_signals_edit(i)
                            _update_charger_functional_trim_signals_edit()
                            _update_charger_functional_setpoint_signals_edit()
                            break
                if act.get('test_trigger_signal') and charger_functional_trigger_signal_combo_edit.count():
                    try:
                        charger_functional_trigger_signal_combo_edit.setCurrentText(str(act.get('test_trigger_signal')))
                    except Exception:
                        pass
                if act.get('set_output_current_trim_signal') and charger_functional_trim_signal_combo_edit.count():
                    try:
                        charger_functional_trim_signal_combo_edit.setCurrentText(str(act.get('set_output_current_trim_signal')))
                    except Exception:
                        pass
                if act.get('set_output_current_setpoint_signal') and charger_functional_setpoint_signal_combo_edit.count():
                    try:
                        charger_functional_setpoint_signal_combo_edit.setCurrentText(str(act.get('set_output_current_setpoint_signal')))
                    except Exception:
                        pass
                feedback_msg_id = act.get('feedback_signal_source')
                if feedback_msg_id is not None:
                    for i in range(charger_functional_feedback_msg_combo_edit.count()):
                        if charger_functional_feedback_msg_combo_edit.itemData(i) == feedback_msg_id:
                            charger_functional_feedback_msg_combo_edit.setCurrentIndex(i)
                            _update_charger_functional_feedback_signals_edit(i)
                            break
                if act.get('dut_test_state_signal') and charger_functional_dut_state_signal_combo_edit.count():
                    try:
                        charger_functional_dut_state_signal_combo_edit.setCurrentText(str(act.get('dut_test_state_signal')))
                    except Exception:
                        pass
                if act.get('enable_relay_signal') and charger_functional_enable_relay_signal_combo_edit.count():
                    try:
                        charger_functional_enable_relay_signal_combo_edit.setCurrentText(str(act.get('enable_relay_signal')))
                    except Exception:
                        pass
                if act.get('enable_pfc_signal') and charger_functional_enable_pfc_signal_combo_edit.count():
                    try:
                        charger_functional_enable_pfc_signal_combo_edit.setCurrentText(str(act.get('enable_pfc_signal')))
                    except Exception:
                        pass
                if act.get('pfc_power_good_signal') and charger_functional_pfc_power_good_signal_combo_edit.count():
                    try:
                        charger_functional_pfc_power_good_signal_combo_edit.setCurrentText(str(act.get('pfc_power_good_signal')))
                    except Exception:
                        pass
                if act.get('pcmc_signal') and charger_functional_pcmc_signal_combo_edit.count():
                    try:
                        charger_functional_pcmc_signal_combo_edit.setCurrentText(str(act.get('pcmc_signal')))
                    except Exception:
                        pass
                if act.get('output_current_signal') and charger_functional_output_current_signal_combo_edit.count():
                    try:
                        charger_functional_output_current_signal_combo_edit.setCurrentText(str(act.get('output_current_signal')))
                    except Exception:
                        pass
                if act.get('psfb_fault_signal') and charger_functional_psfb_fault_signal_combo_edit.count():
                    try:
                        charger_functional_psfb_fault_signal_combo_edit.setCurrentText(str(act.get('psfb_fault_signal')))
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Populate Charger Functional Test sub-widget
            charger_functional_layout_edit.addRow('Command Signal Source:', charger_functional_cmd_msg_combo_edit)
            charger_functional_layout_edit.addRow('Test Trigger Signal:', charger_functional_trigger_signal_combo_edit)
            charger_functional_layout_edit.addRow('Test Trigger Signal Value:', charger_functional_trigger_value_edit_edit)
            charger_functional_layout_edit.addRow('Set Output Current Trim Value Signal:', charger_functional_trim_signal_combo_edit)
            charger_functional_layout_edit.addRow('Fallback Output Current Trim Value (%):', charger_functional_fallback_trim_edit_edit)
            charger_functional_layout_edit.addRow('Set Output Current Setpoint Signal:', charger_functional_setpoint_signal_combo_edit)
            charger_functional_layout_edit.addRow('Output Test Current (A):', charger_functional_output_current_edit_edit)
            charger_functional_layout_edit.addRow('Feedback Signal Source:', charger_functional_feedback_msg_combo_edit)
            charger_functional_layout_edit.addRow('DUT Test State Signal:', charger_functional_dut_state_signal_combo_edit)
            charger_functional_layout_edit.addRow('Enable Relay Signal:', charger_functional_enable_relay_signal_combo_edit)
            charger_functional_layout_edit.addRow('Enable PFC Signal:', charger_functional_enable_pfc_signal_combo_edit)
            charger_functional_layout_edit.addRow('PFC Power Good Signal:', charger_functional_pfc_power_good_signal_combo_edit)
            charger_functional_layout_edit.addRow('PCMC Signal:', charger_functional_pcmc_signal_combo_edit)
            charger_functional_layout_edit.addRow('Output Current Signal:', charger_functional_output_current_signal_combo_edit)
            charger_functional_layout_edit.addRow('PSFB Fault Signal:', charger_functional_psfb_fault_signal_combo_edit)
            charger_functional_layout_edit.addRow('Output Current Tolerance (A):', charger_functional_output_current_tolerance_edit_edit)
            charger_functional_layout_edit.addRow('Test Time (ms):', charger_functional_test_time_edit_edit)
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
            # fallback analog layout - create widgets with validators and assign to variables
            mv_validator = QtGui.QIntValidator(0, 5000, self)
            step_validator = QtGui.QIntValidator(0, 5000, self)
            dwell_validator = QtGui.QIntValidator(0, DWELL_TIME_MAX_MS, self)
            dac_min_mv = QtWidgets.QLineEdit(str(act.get('dac_min_mv','')))
            dac_min_mv.setValidator(mv_validator)
            dac_max_mv = QtWidgets.QLineEdit(str(act.get('dac_max_mv','')))
            dac_max_mv.setValidator(mv_validator)
            dac_step_mv = QtWidgets.QLineEdit(str(act.get('dac_step_mv','')))
            dac_step_mv.setValidator(step_validator)
            dac_dwell_ms = QtWidgets.QLineEdit(str(act.get('dac_dwell_ms','')))
            dac_dwell_ms.setValidator(dwell_validator)
            # Expected Gain input (optional, for calibration)
            expected_gain_validator = QtGui.QDoubleValidator(0.000001, 1000000.0, 6, self)
            expected_gain_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            expected_gain_edit = QtWidgets.QLineEdit(str(act.get('expected_gain', '')))
            expected_gain_edit.setValidator(expected_gain_validator)
            expected_gain_edit.setPlaceholderText('Optional: for gain adjustment calculation')
            analog_layout.addRow('Command Message (free-text):', mux_chan)
            analog_layout.addRow('DAC CAN ID (analog):', dac_can)
            analog_layout.addRow('DAC Command (hex):', dac_cmd)
            analog_layout.addRow('DAC Min Output (mV):', dac_min_mv)
            analog_layout.addRow('DAC Max Output (mV):', dac_max_mv)
            analog_layout.addRow('Step Change (mV):', dac_step_mv)
            analog_layout.addRow('Dwell Time (ms):', dac_dwell_ms)
            analog_layout.addRow('Expected Gain (optional):', expected_gain_edit)
            
            # Phase Current Calibration fields (fallback when no DBC) - for edit dialog
            phase_current_cmd_msg_edit = QtWidgets.QLineEdit(str(act.get('command_message', '')))
            phase_current_trigger_signal_edit = QtWidgets.QLineEdit(str(act.get('trigger_test_signal', '')))
            phase_current_iq_ref_signal_edit = QtWidgets.QLineEdit(str(act.get('iq_ref_signal', '')))
            phase_current_id_ref_signal_edit = QtWidgets.QLineEdit(str(act.get('id_ref_signal', '')))
            phase_current_msg_edit = QtWidgets.QLineEdit(str(act.get('phase_current_signal_source', '')))
            phase_current_v_signal_edit = QtWidgets.QLineEdit(str(act.get('phase_current_v_signal', '')))
            phase_current_w_signal_edit = QtWidgets.QLineEdit(str(act.get('phase_current_w_signal', '')))
            
            iq_validator = QtGui.QDoubleValidator(-1000.0, 1000.0, 6, self)
            iq_validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            min_iq_edit = QtWidgets.QLineEdit(str(act.get('min_iq', '')))
            min_iq_edit.setValidator(iq_validator)
            max_iq_edit = QtWidgets.QLineEdit(str(act.get('max_iq', '')))
            max_iq_edit.setValidator(iq_validator)
            step_iq_edit = QtWidgets.QLineEdit(str(act.get('step_iq', '')))
            step_iq_edit.setValidator(iq_validator)
            
            duration_validator = QtGui.QIntValidator(0, 60000, self)
            ipc_test_duration_edit = QtWidgets.QLineEdit(str(act.get('ipc_test_duration_ms', '')))
            ipc_test_duration_edit.setValidator(duration_validator)
            
            osc_phase_v_ch_combo = QtWidgets.QComboBox()
            osc_phase_w_ch_combo = QtWidgets.QComboBox()
            
            def _update_osc_channel_dropdowns_edit():
                osc_phase_v_ch_combo.clear()
                osc_phase_w_ch_combo.clear()
                enabled_channel_names = []
                if hasattr(self, '_oscilloscope_config') and self._oscilloscope_config:
                    channels = self._oscilloscope_config.get('channels', {})
                    for ch_key in ['CH1', 'CH2', 'CH3', 'CH4']:
                        if ch_key in channels:
                            ch_config = channels[ch_key]
                            if ch_config.get('enabled', False):
                                channel_name = ch_config.get('channel_name', '').strip()
                                if channel_name:
                                    enabled_channel_names.append(channel_name)
                osc_phase_v_ch_combo.addItems(enabled_channel_names)
                osc_phase_w_ch_combo.addItems(enabled_channel_names)
            
            _update_osc_channel_dropdowns_edit()
            
            try:
                if act.get('oscilloscope_phase_v_ch') and osc_phase_v_ch_combo.count():
                    osc_phase_v_ch_combo.setCurrentText(str(act.get('oscilloscope_phase_v_ch')))
                if act.get('oscilloscope_phase_w_ch') and osc_phase_w_ch_combo.count():
                    osc_phase_w_ch_combo.setCurrentText(str(act.get('oscilloscope_phase_w_ch')))
            except Exception:
                pass
            
            phase_current_layout.addRow('Command Message (CAN ID):', phase_current_cmd_msg_edit)
            phase_current_layout.addRow('Trigger Test Signal:', phase_current_trigger_signal_edit)
            phase_current_layout.addRow('Iq_ref Signal:', phase_current_iq_ref_signal_edit)
            phase_current_layout.addRow('Id_ref Signal:', phase_current_id_ref_signal_edit)
            phase_current_layout.addRow('Phase Current Signal Source (CAN ID):', phase_current_msg_edit)
            phase_current_layout.addRow('Phase Current V Signal:', phase_current_v_signal_edit)
            phase_current_layout.addRow('Phase Current W Signal:', phase_current_w_signal_edit)
            phase_current_layout.addRow('Min Iq (A):', min_iq_edit)
            phase_current_layout.addRow('Max Iq (A):', max_iq_edit)
            phase_current_layout.addRow('Step Iq (A):', step_iq_edit)
            phase_current_layout.addRow('IPC Test Duration (ms):', ipc_test_duration_edit)
            phase_current_layout.addRow('Oscilloscope Phase V CH:', osc_phase_v_ch_combo)
            phase_current_layout.addRow('Oscilloscope Phase W CH:', osc_phase_w_ch_combo)
            
            # Analog Static Test fields (fallback when no DBC) - for edit dialog
            analog_static_fb_msg_edit_edit = QtWidgets.QLineEdit(str(act.get('feedback_signal_source', '')))
            analog_static_fb_signal_edit_edit = QtWidgets.QLineEdit(str(act.get('feedback_signal', '')))
            analog_static_eol_msg_edit_edit = QtWidgets.QLineEdit(str(act.get('eol_signal_source', '')))
            analog_static_eol_signal_edit_edit = QtWidgets.QLineEdit(str(act.get('eol_signal', '')))
            
            # Tolerance input (float, in mV)
            tolerance_validator_fallback_edit = QtGui.QDoubleValidator(0.0, 10000.0, 2, self)
            tolerance_validator_fallback_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            tolerance_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('tolerance_mv', '')))
            tolerance_edit_fallback_edit.setValidator(tolerance_validator_fallback_edit)
            tolerance_edit_fallback_edit.setPlaceholderText('e.g., 10.0')
            
            # Pre-dwell time input (int, in ms)
            pre_dwell_validator_fallback_edit = QtGui.QIntValidator(0, 60000, self)
            pre_dwell_time_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('pre_dwell_time_ms', '')))
            pre_dwell_time_edit_fallback_edit.setValidator(pre_dwell_validator_fallback_edit)
            pre_dwell_time_edit_fallback_edit.setPlaceholderText('e.g., 100')
            
            # Dwell time input (int, in ms)
            dwell_time_validator_fallback_edit = QtGui.QIntValidator(1, 60000, self)
            dwell_time_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('dwell_time_ms', '')))
            dwell_time_edit_fallback_edit.setValidator(dwell_time_validator_fallback_edit)
            dwell_time_edit_fallback_edit.setPlaceholderText('e.g., 500')
            
            # Populate analog static sub-widget (fallback)
            analog_static_layout.addRow('Feedback Signal Source (CAN ID):', analog_static_fb_msg_edit_edit)
            analog_static_layout.addRow('Feedback Signal:', analog_static_fb_signal_edit_edit)
            analog_static_layout.addRow('EOL Signal Source (CAN ID):', analog_static_eol_msg_edit_edit)
            analog_static_layout.addRow('EOL Signal:', analog_static_eol_signal_edit_edit)
            analog_static_layout.addRow('Tolerance (mV):', tolerance_edit_fallback_edit)
            analog_static_layout.addRow('Pre-dwell Time (ms):', pre_dwell_time_edit_fallback_edit)
            analog_static_layout.addRow('Dwell Time (ms):', dwell_time_edit_fallback_edit)
            
            # Temperature Validation Test fields (fallback when no DBC) - for edit dialog
            temp_val_fb_msg_edit_edit = QtWidgets.QLineEdit(str(act.get('feedback_signal_source', '')))
            temp_val_fb_signal_edit_edit = QtWidgets.QLineEdit(str(act.get('feedback_signal', '')))
            
            # Reference temperature input (float, in °C)
            reference_validator_fallback_edit = QtGui.QDoubleValidator(-273.15, 1000.0, 2, self)
            reference_validator_fallback_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            temp_val_reference_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('reference_temperature_c', '')))
            temp_val_reference_edit_fallback_edit.setValidator(reference_validator_fallback_edit)
            temp_val_reference_edit_fallback_edit.setPlaceholderText('e.g., 25.0')
            
            # Tolerance input (float, in °C)
            temp_tolerance_validator_fallback_edit = QtGui.QDoubleValidator(0.0, 1000.0, 2, self)
            temp_tolerance_validator_fallback_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            temp_val_tolerance_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('tolerance_c', '')))
            temp_val_tolerance_edit_fallback_edit.setValidator(temp_tolerance_validator_fallback_edit)
            temp_val_tolerance_edit_fallback_edit.setPlaceholderText('e.g., 2.0')
            
            # Dwell time input (int, in ms)
            temp_dwell_time_validator_fallback_edit = QtGui.QIntValidator(1, 60000, self)
            temp_val_dwell_time_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('dwell_time_ms', '')))
            temp_val_dwell_time_edit_fallback_edit.setValidator(temp_dwell_time_validator_fallback_edit)
            temp_val_dwell_time_edit_fallback_edit.setPlaceholderText('e.g., 1000')
            
            # Populate temperature validation sub-widget (fallback)
            temperature_validation_layout.addRow('Feedback Signal Source (CAN ID):', temp_val_fb_msg_edit_edit)
            temperature_validation_layout.addRow('Feedback Signal:', temp_val_fb_signal_edit_edit)
            temperature_validation_layout.addRow('Reference Temperature (°C):', temp_val_reference_edit_fallback_edit)
            temperature_validation_layout.addRow('Tolerance (°C):', temp_val_tolerance_edit_fallback_edit)
            temperature_validation_layout.addRow('Dwell Time (ms):', temp_val_dwell_time_edit_fallback_edit)
            
            # Analog PWM Sensor Test fields (fallback when no DBC) - for edit dialog
            analog_pwm_fb_msg_edit_edit = QtWidgets.QLineEdit(str(act.get('feedback_signal_source', '')))
            analog_pwm_frequency_signal_edit_edit = QtWidgets.QLineEdit(str(act.get('feedback_pwm_frequency_signal', '')))
            analog_pwm_duty_signal_edit_edit = QtWidgets.QLineEdit(str(act.get('feedback_duty_signal', '')))
            
            # Reference PWM frequency input (float, in Hz)
            pwm_freq_reference_validator_fallback_edit = QtGui.QDoubleValidator(0.0, 1000000.0, 2, self)
            pwm_freq_reference_validator_fallback_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_reference_frequency_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('reference_pwm_frequency', '')))
            analog_pwm_reference_frequency_edit_fallback_edit.setValidator(pwm_freq_reference_validator_fallback_edit)
            analog_pwm_reference_frequency_edit_fallback_edit.setPlaceholderText('e.g., 1000.0')
            
            # Reference duty input (float, in %)
            duty_reference_validator_fallback_edit = QtGui.QDoubleValidator(0.0, 100.0, 2, self)
            duty_reference_validator_fallback_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_reference_duty_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('reference_duty', '')))
            analog_pwm_reference_duty_edit_fallback_edit.setValidator(duty_reference_validator_fallback_edit)
            analog_pwm_reference_duty_edit_fallback_edit.setPlaceholderText('e.g., 50.0')
            
            # PWM frequency tolerance input (float, in Hz)
            pwm_freq_tolerance_validator_fallback_edit = QtGui.QDoubleValidator(0.0, 1000000.0, 2, self)
            pwm_freq_tolerance_validator_fallback_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_frequency_tolerance_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('pwm_frequency_tolerance', '')))
            analog_pwm_frequency_tolerance_edit_fallback_edit.setValidator(pwm_freq_tolerance_validator_fallback_edit)
            analog_pwm_frequency_tolerance_edit_fallback_edit.setPlaceholderText('e.g., 10.0')
            
            # Duty tolerance input (float, in %)
            duty_tolerance_validator_fallback_edit = QtGui.QDoubleValidator(0.0, 100.0, 2, self)
            duty_tolerance_validator_fallback_edit.setNotation(QtGui.QDoubleValidator.StandardNotation)
            analog_pwm_duty_tolerance_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('duty_tolerance', '')))
            analog_pwm_duty_tolerance_edit_fallback_edit.setValidator(duty_tolerance_validator_fallback_edit)
            analog_pwm_duty_tolerance_edit_fallback_edit.setPlaceholderText('e.g., 1.0')
            
            # Acquisition time input (int, in ms)
            pwm_acquisition_time_validator_fallback_edit = QtGui.QIntValidator(1, 60000, self)
            analog_pwm_acquisition_time_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('acquisition_time_ms', '')))
            analog_pwm_acquisition_time_edit_fallback_edit.setValidator(pwm_acquisition_time_validator_fallback_edit)
            analog_pwm_acquisition_time_edit_fallback_edit.setPlaceholderText('e.g., 3000')
            
            # Populate Analog PWM Sensor sub-widget (fallback)
            analog_pwm_sensor_layout_edit.addRow('Feedback Signal Source (CAN ID):', analog_pwm_fb_msg_edit_edit)
            analog_pwm_sensor_layout_edit.addRow('PWM Frequency Signal:', analog_pwm_frequency_signal_edit_edit)
            analog_pwm_sensor_layout_edit.addRow('Duty Signal:', analog_pwm_duty_signal_edit_edit)
            analog_pwm_sensor_layout_edit.addRow('Reference PWM Frequency (Hz):', analog_pwm_reference_frequency_edit_fallback_edit)
            analog_pwm_sensor_layout_edit.addRow('Reference Duty (%):', analog_pwm_reference_duty_edit_fallback_edit)
            analog_pwm_sensor_layout_edit.addRow('PWM Frequency Tolerance (Hz):', analog_pwm_frequency_tolerance_edit_fallback_edit)
            analog_pwm_sensor_layout_edit.addRow('Duty Tolerance (%):', analog_pwm_duty_tolerance_edit_fallback_edit)
            analog_pwm_sensor_layout_edit.addRow('Acquisition Time (ms):', analog_pwm_acquisition_time_edit_fallback_edit)
            
            # Fan Control Test fields (fallback when no DBC) - for edit dialog
            fan_control_trigger_msg_edit_edit = QtWidgets.QLineEdit(str(act.get('fan_test_trigger_source', '')))
            fan_control_trigger_signal_edit_edit = QtWidgets.QLineEdit(str(act.get('fan_test_trigger_signal', '')))
            fan_control_feedback_msg_edit_edit = QtWidgets.QLineEdit(str(act.get('fan_control_feedback_source', '')))
            fan_control_enabled_signal_edit_edit = QtWidgets.QLineEdit(str(act.get('fan_enabled_signal', '')))
            fan_control_tach_signal_edit_edit = QtWidgets.QLineEdit(str(act.get('fan_tach_feedback_signal', '')))
            fan_control_fault_signal_edit_edit = QtWidgets.QLineEdit(str(act.get('fan_fault_feedback_signal', '')))
            
            # Dwell time input (int, in ms)
            fan_dwell_time_validator_fallback_edit = QtGui.QIntValidator(1, 60000, self)
            fan_control_dwell_time_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('dwell_time_ms', '')))
            fan_control_dwell_time_edit_fallback_edit.setValidator(fan_dwell_time_validator_fallback_edit)
            fan_control_dwell_time_edit_fallback_edit.setPlaceholderText('e.g., 1000')
            
            # Test timeout input (int, in ms)
            fan_timeout_validator_fallback_edit = QtGui.QIntValidator(1, 60000, self)
            fan_control_timeout_edit_fallback_edit = QtWidgets.QLineEdit(str(act.get('test_timeout_ms', '')))
            fan_control_timeout_edit_fallback_edit.setValidator(fan_timeout_validator_fallback_edit)
            fan_control_timeout_edit_fallback_edit.setPlaceholderText('e.g., 5000')
            
            # Populate fan control sub-widget (fallback)
            fan_control_layout.addRow('Fan Test Trigger Source (CAN ID):', fan_control_trigger_msg_edit_edit)
            fan_control_layout.addRow('Fan Test Trigger Signal:', fan_control_trigger_signal_edit_edit)
            fan_control_layout.addRow('Fan Control Feedback Source (CAN ID):', fan_control_feedback_msg_edit_edit)
            fan_control_layout.addRow('Fan Enabled Signal:', fan_control_enabled_signal_edit_edit)
            fan_control_layout.addRow('Fan Tach Feedback Signal:', fan_control_tach_signal_edit_edit)
            fan_control_layout.addRow('Fan Fault Feedback Signal:', fan_control_fault_signal_edit_edit)
            fan_control_layout.addRow('Dwell Time (ms):', fan_control_dwell_time_edit_fallback_edit)
            fan_control_layout.addRow('Test Timeout (ms):', fan_control_timeout_edit_fallback_edit)

        form.addRow('Name:', name_edit)
        form.addRow('Type:', type_combo)
        # Test Mode field (0-3, default 0)
        test_mode_spin_edit = QtWidgets.QSpinBox()
        test_mode_spin_edit.setRange(0, 3)
        test_mode_spin_edit.setValue(data.get('test_mode', 0))
        test_mode_spin_edit.setToolTip('DUT must be in this test mode before test execution (0-3)')
        form.addRow('Test Mode:', test_mode_spin_edit)
        # Feedback fields - store references for showing/hiding
        fb_msg_label = None
        fb_signal_label = None
        feedback_edit_label = None
        if self.dbc_service is not None and self.dbc_service.is_loaded():
            fb_msg_label = QtWidgets.QLabel('Feedback Signal Source:')
            fb_signal_label = QtWidgets.QLabel('Feedback Signal:')
            form.addRow(fb_msg_label, fb_msg_combo)
            form.addRow(fb_signal_label, fb_signal_combo)
        else:
            feedback_edit_label = QtWidgets.QLabel('Feedback Signal (free-text):')
            form.addRow(feedback_edit_label, feedback_edit)

        v.addLayout(form)
        # Use QStackedWidget to show only relevant fields for selected test type
        act_stacked_edit = QtWidgets.QStackedWidget()
        # Create mapping of test type to index
        test_type_to_index_edit = {}
        test_type_to_index_edit['Digital Logic Test'] = act_stacked_edit.addWidget(digital_widget)
        test_type_to_index_edit['Analog Sweep Test'] = act_stacked_edit.addWidget(analog_widget)
        test_type_to_index_edit['Phase Current Test'] = act_stacked_edit.addWidget(phase_current_widget)
        test_type_to_index_edit['Analog Static Test'] = act_stacked_edit.addWidget(analog_static_widget)
        test_type_to_index_edit['Analog PWM Sensor'] = act_stacked_edit.addWidget(analog_pwm_sensor_widget_edit)
        test_type_to_index_edit['Temperature Validation Test'] = act_stacked_edit.addWidget(temperature_validation_widget)
        test_type_to_index_edit['Fan Control Test'] = act_stacked_edit.addWidget(fan_control_widget_edit)
        test_type_to_index_edit['External 5V Test'] = act_stacked_edit.addWidget(ext_5v_test_widget_edit)
        test_type_to_index_edit['DC Bus Sensing'] = act_stacked_edit.addWidget(dc_bus_sensing_widget_edit)
        if self.dbc_service is not None and self.dbc_service.is_loaded():
            test_type_to_index_edit['Output Current Calibration'] = act_stacked_edit.addWidget(output_current_calibration_widget_edit)
            test_type_to_index_edit['Charged HV Bus Test'] = act_stacked_edit.addWidget(charged_hv_bus_widget_edit)
            test_type_to_index_edit['Charger Functional Test'] = act_stacked_edit.addWidget(charger_functional_widget_edit)
        
        v.addWidget(QtWidgets.QLabel('Test Configuration:'))
        v.addWidget(act_stacked_edit)

        def _on_type_change_edit(txt: str):
            try:
                # Switch to the appropriate page in the stacked widget
                if txt in test_type_to_index_edit:
                    act_stacked_edit.setCurrentIndex(test_type_to_index_edit[txt])
                
                # Handle feedback fields visibility based on test type
                if txt in ('Digital Logic Test', 'Analog Sweep Test'):
                    # Show feedback fields for digital and analog
                    if fb_msg_label is not None:
                        fb_msg_label.show()
                        fb_msg_combo.show()
                        fb_signal_label.show()
                        fb_signal_combo.show()
                    elif feedback_edit_label is not None:
                        feedback_edit_label.show()
                        feedback_edit.show()
                elif txt in ('Phase Current Test', 'Analog Static Test', 'Analog PWM Sensor', 'Temperature Validation Test', 'Fan Control Test', 'External 5V Test', 'DC Bus Sensing', 'Output Current Calibration', 'Charged HV Bus Test', 'Charger Functional Test'):
                    # Hide feedback fields (these test types use their own fields)
                    if fb_msg_label is not None:
                        fb_msg_label.hide()
                        fb_msg_combo.hide()
                        fb_signal_label.hide()
                        fb_signal_combo.hide()
                    elif feedback_edit_label is not None:
                        feedback_edit_label.hide()
                        feedback_edit.hide()
            except Exception:
                pass

        _on_type_change_edit(type_combo.currentText())
        type_combo.currentTextChanged.connect(_on_type_change_edit)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        v.addWidget(btns)

        def on_accept():
            new_name = name_edit.text().strip()
            if not new_name:
                QtWidgets.QMessageBox.warning(dlg, 'Invalid Name', 'Test name cannot be empty')
                return
            # Check for duplicate name (excluding current test index)
            if not self._is_test_name_unique(new_name, exclude_index=idx):
                QtWidgets.QMessageBox.warning(dlg, 'Duplicate Name', f'A test with name "{new_name}" already exists. Please choose a different name.')
                return
            
            data['name'] = new_name
            data['type'] = type_combo.currentText()
            # Update test_mode
            data['test_mode'] = test_mode_spin_edit.value()
            # feedback
            # Only save feedback fields for test types that use them
            # Test types that have their own feedback fields inside actuation don't need these
            test_types_with_own_feedback = ('Phase Current Test', 'Analog Static Test', 'Analog PWM Sensor', 'Temperature Validation Test', 
                                          'Fan Control Test', 'External 5V Test', 'DC Bus Sensing', 'Output Current Calibration', 'Charged HV Bus Test', 'Charger Functional Test')
            
            if data['type'] not in test_types_with_own_feedback:
                # Only read and save feedback fields for test types that use them
                if self.dbc_service is not None and self.dbc_service.is_loaded():
                    try:
                        data['feedback_message_id'] = fb_msg_combo.currentData()
                        data['feedback_signal'] = fb_signal_combo.currentText().strip()
                    except Exception:
                        data['feedback_message_id'] = None
                        data['feedback_signal'] = ''
                else:
                    data['feedback_signal'] = feedback_edit.text().strip()
            else:
                # Remove feedback fields if they exist (for test types that don't use them)
                if 'feedback_signal' in data:
                    del data['feedback_signal']
                if 'feedback_message_id' in data:
                    del data['feedback_message_id']

            # actuation
            if self.dbc_service is not None and self.dbc_service.is_loaded():
                if data['type'] == 'Digital Logic Test':
                    can_id = dig_msg_combo.currentData() if 'dig_msg_combo' in locals() else None
                    sig = dig_signal_combo.currentText().strip() if 'dig_signal_combo' in locals() else ''
                    low = dig_value_low.text().strip()
                    high = dig_value_high.text().strip()
                    # optional dwell time
                    try:
                        dig_dwell = int(dig_dwell_ms.text().strip()) if hasattr(dig_dwell_ms, 'text') and dig_dwell_ms.text().strip() else None
                    except Exception:
                        dig_dwell = None
                    data['actuation'] = {'type':'Digital Logic Test','can_id':can_id,'signal':sig,'value_low':low,'value_high':high,'dwell_ms':dig_dwell}
                elif data['type'] == 'Analog Sweep Test':
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
                    # Read expected gain (optional float)
                    expected_gain_val = None
                    try:
                        if 'expected_gain_edit' in locals():
                            expected_gain_text = expected_gain_edit.text().strip() if hasattr(expected_gain_edit, 'text') else ''
                            if expected_gain_text:
                                expected_gain_val = float(expected_gain_text)
                    except (ValueError, TypeError):
                        pass
                    # Read gain tolerance (optional float)
                    gain_tolerance_val = None
                    try:
                        if 'gain_tolerance_edit' in locals():
                            gain_tolerance_text = gain_tolerance_edit.text().strip() if hasattr(gain_tolerance_edit, 'text') else ''
                            if gain_tolerance_text:
                                gain_tolerance_val = float(gain_tolerance_text)
                                if gain_tolerance_val < 0:
                                    raise ValueError("Gain tolerance cannot be negative")
                    except (ValueError, TypeError):
                        pass
                    data['actuation'] = {
                        'type':'Analog Sweep Test',
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
                    if expected_gain_val is not None:
                        data['actuation']['expected_gain'] = expected_gain_val
                    if gain_tolerance_val is not None:
                        data['actuation']['gain_tolerance_percent'] = gain_tolerance_val
                elif data['type'] == 'Phase Current Test':
                    # Phase Current Calibration: read all fields
                    try:
                        cmd_msg_id = phase_current_cmd_msg_combo.currentData() if 'phase_current_cmd_msg_combo' in locals() else None
                    except Exception:
                        cmd_msg_id = None
                    trigger_test_sig = phase_current_trigger_signal_combo.currentText().strip() if 'phase_current_trigger_signal_combo' in locals() and phase_current_trigger_signal_combo.count() else ''
                    iq_ref_sig = phase_current_iq_ref_signal_combo.currentText().strip() if 'phase_current_iq_ref_signal_combo' in locals() and phase_current_iq_ref_signal_combo.count() else ''
                    id_ref_sig = phase_current_id_ref_signal_combo.currentText().strip() if 'phase_current_id_ref_signal_combo' in locals() and phase_current_id_ref_signal_combo.count() else ''
                    
                    try:
                        phase_current_can_id = phase_current_msg_combo.currentData() if 'phase_current_msg_combo' in locals() else None
                    except Exception:
                        phase_current_can_id = None
                    phase_current_v_sig = phase_current_v_signal_combo.currentText().strip() if 'phase_current_v_signal_combo' in locals() and phase_current_v_signal_combo.count() else ''
                    phase_current_w_sig = phase_current_w_signal_combo.currentText().strip() if 'phase_current_w_signal_combo' in locals() and phase_current_w_signal_combo.count() else ''
                    
                    def _to_float_or_none(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    min_iq = _to_float_or_none(min_iq_edit) if 'min_iq_edit' in locals() else None
                    max_iq = _to_float_or_none(max_iq_edit) if 'max_iq_edit' in locals() else None
                    step_iq = _to_float_or_none(step_iq_edit) if 'step_iq_edit' in locals() else None
                    
                    def _to_int_or_none_duration(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    ipc_test_duration = _to_int_or_none_duration(ipc_test_duration_edit) if 'ipc_test_duration_edit' in locals() else None
                    
                    osc_phase_v_ch = osc_phase_v_ch_combo.currentText().strip() if 'osc_phase_v_ch_combo' in locals() and osc_phase_v_ch_combo.count() else ''
                    osc_phase_w_ch = osc_phase_w_ch_combo.currentText().strip() if 'osc_phase_w_ch_combo' in locals() and osc_phase_w_ch_combo.count() else ''
                    
                    data['actuation'] = {
                        'type': 'Phase Current Test',
                        'command_message': cmd_msg_id,
                        'trigger_test_signal': trigger_test_sig,
                        'iq_ref_signal': iq_ref_sig,
                        'id_ref_signal': id_ref_sig,
                        'phase_current_signal_source': phase_current_can_id,
                        'phase_current_v_signal': phase_current_v_sig,
                        'phase_current_w_signal': phase_current_w_sig,
                        'min_iq': min_iq,
                        'max_iq': max_iq,
                        'step_iq': step_iq,
                        'ipc_test_duration_ms': ipc_test_duration,
                        'oscilloscope_phase_v_ch': osc_phase_v_ch,
                        'oscilloscope_phase_w_ch': osc_phase_w_ch,
                    }
                elif data['type'] == 'Analog Static Test':
                    # Analog Static Test: read all fields (DBC mode)
                    try:
                        fb_msg_id = analog_static_fb_msg_combo_edit.currentData() if 'analog_static_fb_msg_combo_edit' in locals() else None
                    except Exception:
                        fb_msg_id = None
                    fb_signal = analog_static_fb_signal_combo_edit.currentText().strip() if 'analog_static_fb_signal_combo_edit' in locals() and analog_static_fb_signal_combo_edit.count() else ''
                    
                    try:
                        eol_msg_id = analog_static_eol_msg_combo_edit.currentData() if 'analog_static_eol_msg_combo_edit' in locals() else None
                    except Exception:
                        eol_msg_id = None
                    eol_signal = analog_static_eol_signal_combo_edit.currentText().strip() if 'analog_static_eol_signal_combo_edit' in locals() and analog_static_eol_signal_combo_edit.count() else ''
                    
                    # Tolerance (float)
                    def _to_float_or_none_tolerance_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_val = _to_float_or_none_tolerance_edit(tolerance_edit_edit) if 'tolerance_edit_edit' in locals() else None
                    
                    # Pre-dwell and dwell times (int)
                    def _to_int_or_none_time_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    pre_dwell_val = _to_int_or_none_time_edit(pre_dwell_time_edit_edit) if 'pre_dwell_time_edit_edit' in locals() else None
                    dwell_time_val = _to_int_or_none_time_edit(dwell_time_edit_edit) if 'dwell_time_edit_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'Analog Static Test',
                        'feedback_signal_source': fb_msg_id,
                        'feedback_signal': fb_signal,
                        'eol_signal_source': eol_msg_id,
                        'eol_signal': eol_signal,
                        'tolerance_mv': tolerance_val,
                        'pre_dwell_time_ms': pre_dwell_val,
                        'dwell_time_ms': dwell_time_val,
                    }
                elif data['type'] == 'Temperature Validation Test':
                    # Temperature Validation Test: read all fields (DBC mode)
                    try:
                        fb_msg_id = temp_val_fb_msg_combo_edit.currentData() if 'temp_val_fb_msg_combo_edit' in locals() else None
                    except Exception:
                        fb_msg_id = None
                    fb_signal = temp_val_fb_signal_combo_edit.currentText().strip() if 'temp_val_fb_signal_combo_edit' in locals() and temp_val_fb_signal_combo_edit.count() else ''
                    
                    # Reference temperature (float)
                    def _to_float_or_none_reference_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    reference_temp_val = _to_float_or_none_reference_edit(temp_val_reference_edit_edit) if 'temp_val_reference_edit_edit' in locals() else None
                    
                    # Tolerance (float)
                    def _to_float_or_none_temp_tolerance_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_c_val = _to_float_or_none_temp_tolerance_edit(temp_val_tolerance_edit_edit) if 'temp_val_tolerance_edit_edit' in locals() else None
                    
                    # Dwell time (int)
                    def _to_int_or_none_dwell_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dwell_time_val = _to_int_or_none_dwell_edit(temp_val_dwell_time_edit_edit) if 'temp_val_dwell_time_edit_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'Temperature Validation Test',
                        'feedback_signal_source': fb_msg_id,
                        'feedback_signal': fb_signal,
                        'reference_temperature_c': reference_temp_val,
                        'tolerance_c': tolerance_c_val,
                        'dwell_time_ms': dwell_time_val,
                    }
                elif data['type'] == 'Analog PWM Sensor':
                    # Analog PWM Sensor Test: read all fields (DBC mode)
                    try:
                        fb_msg_id = analog_pwm_fb_msg_combo_edit.currentData() if 'analog_pwm_fb_msg_combo_edit' in locals() else None
                    except Exception:
                        fb_msg_id = None
                    pwm_frequency_signal = analog_pwm_frequency_signal_combo_edit.currentText().strip() if 'analog_pwm_frequency_signal_combo_edit' in locals() and analog_pwm_frequency_signal_combo_edit.count() else ''
                    duty_signal = analog_pwm_duty_signal_combo_edit.currentText().strip() if 'analog_pwm_duty_signal_combo_edit' in locals() and analog_pwm_duty_signal_combo_edit.count() else ''
                    
                    # Reference PWM frequency (float)
                    def _to_float_or_none_pwm_freq_reference_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    reference_pwm_freq_val = _to_float_or_none_pwm_freq_reference_edit(analog_pwm_reference_frequency_edit_edit) if 'analog_pwm_reference_frequency_edit_edit' in locals() else None
                    
                    # Reference duty (float)
                    def _to_float_or_none_duty_reference_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    reference_duty_val = _to_float_or_none_duty_reference_edit(analog_pwm_reference_duty_edit_edit) if 'analog_pwm_reference_duty_edit_edit' in locals() else None
                    
                    # PWM frequency tolerance (float)
                    def _to_float_or_none_pwm_freq_tolerance_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    pwm_freq_tolerance_val = _to_float_or_none_pwm_freq_tolerance_edit(analog_pwm_frequency_tolerance_edit_edit) if 'analog_pwm_frequency_tolerance_edit_edit' in locals() else None
                    
                    # Duty tolerance (float)
                    def _to_float_or_none_duty_tolerance_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    duty_tolerance_val = _to_float_or_none_duty_tolerance_edit(analog_pwm_duty_tolerance_edit_edit) if 'analog_pwm_duty_tolerance_edit_edit' in locals() else None
                    
                    # Acquisition time (int)
                    def _to_int_or_none_acquisition_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    acquisition_time_val = _to_int_or_none_acquisition_edit(analog_pwm_acquisition_time_edit_edit) if 'analog_pwm_acquisition_time_edit_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'Analog PWM Sensor',
                        'feedback_signal_source': fb_msg_id,
                        'feedback_pwm_frequency_signal': pwm_frequency_signal,
                        'feedback_duty_signal': duty_signal,
                        'reference_pwm_frequency': reference_pwm_freq_val,
                        'reference_duty': reference_duty_val,
                        'pwm_frequency_tolerance': pwm_freq_tolerance_val,
                        'duty_tolerance': duty_tolerance_val,
                        'acquisition_time_ms': acquisition_time_val,
                    }
                elif data['type'] == 'Fan Control Test':
                    # Fan Control Test: read all fields (DBC mode)
                    try:
                        trigger_msg_id = fan_control_trigger_msg_combo_edit.currentData() if 'fan_control_trigger_msg_combo_edit' in locals() else None
                    except Exception:
                        trigger_msg_id = None
                    trigger_signal = fan_control_trigger_signal_combo_edit.currentText().strip() if 'fan_control_trigger_signal_combo_edit' in locals() and fan_control_trigger_signal_combo_edit.count() else ''
                    
                    try:
                        feedback_msg_id = fan_control_feedback_msg_combo_edit.currentData() if 'fan_control_feedback_msg_combo_edit' in locals() else None
                    except Exception:
                        feedback_msg_id = None
                    fan_enabled_signal = fan_control_enabled_signal_combo_edit.currentText().strip() if 'fan_control_enabled_signal_combo_edit' in locals() and fan_control_enabled_signal_combo_edit.count() else ''
                    fan_tach_signal = fan_control_tach_signal_combo_edit.currentText().strip() if 'fan_control_tach_signal_combo_edit' in locals() and fan_control_tach_signal_combo_edit.count() else ''
                    fan_fault_signal = fan_control_fault_signal_combo_edit.currentText().strip() if 'fan_control_fault_signal_combo_edit' in locals() and fan_control_fault_signal_combo_edit.count() else ''
                    
                    # Dwell time (int)
                    def _to_int_or_none_fan_dwell_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dwell_time_val = _to_int_or_none_fan_dwell_edit(fan_control_dwell_time_edit_edit) if 'fan_control_dwell_time_edit_edit' in locals() else None
                    
                    # Test timeout (int)
                    def _to_int_or_none_fan_timeout_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    timeout_val = _to_int_or_none_fan_timeout_edit(fan_control_timeout_edit_edit) if 'fan_control_timeout_edit_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'Fan Control Test',
                        'fan_test_trigger_source': trigger_msg_id,
                        'fan_test_trigger_signal': trigger_signal,
                        'fan_control_feedback_source': feedback_msg_id,
                        'fan_enabled_signal': fan_enabled_signal,
                        'fan_tach_feedback_signal': fan_tach_signal,
                        'fan_fault_feedback_signal': fan_fault_signal,
                        'dwell_time_ms': dwell_time_val,
                        'test_timeout_ms': timeout_val,
                    }
                elif data['type'] == 'External 5V Test':
                    # External 5V Test: read all fields (DBC mode)
                    try:
                        trigger_msg_id = ext_5v_test_trigger_msg_combo_edit.currentData() if 'ext_5v_test_trigger_msg_combo_edit' in locals() else None
                    except Exception:
                        trigger_msg_id = None
                    trigger_signal = ext_5v_test_trigger_signal_combo_edit.currentText().strip() if 'ext_5v_test_trigger_signal_combo_edit' in locals() and ext_5v_test_trigger_signal_combo_edit.count() else ''
                    
                    try:
                        eol_msg_id = ext_5v_test_eol_msg_combo_edit.currentData() if 'ext_5v_test_eol_msg_combo_edit' in locals() else None
                    except Exception:
                        eol_msg_id = None
                    eol_signal = ext_5v_test_eol_signal_combo_edit.currentText().strip() if 'ext_5v_test_eol_signal_combo_edit' in locals() and ext_5v_test_eol_signal_combo_edit.count() else ''
                    
                    try:
                        feedback_msg_id = ext_5v_test_feedback_msg_combo_edit.currentData() if 'ext_5v_test_feedback_msg_combo_edit' in locals() else None
                    except Exception:
                        feedback_msg_id = None
                    feedback_signal = ext_5v_test_feedback_signal_combo_edit.currentText().strip() if 'ext_5v_test_feedback_signal_combo_edit' in locals() and ext_5v_test_feedback_signal_combo_edit.count() else ''
                    
                    # Tolerance (float)
                    def _to_float_or_none_ext5v_tolerance_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_val = _to_float_or_none_ext5v_tolerance_edit(ext_5v_test_tolerance_edit_edit) if 'ext_5v_test_tolerance_edit_edit' in locals() else None
                    
                    # Pre-dwell and dwell times (int)
                    def _to_int_or_none_ext5v_time_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    pre_dwell_val = _to_int_or_none_ext5v_time_edit(ext_5v_test_pre_dwell_time_edit_edit) if 'ext_5v_test_pre_dwell_time_edit_edit' in locals() else None
                    dwell_time_val = _to_int_or_none_ext5v_time_edit(ext_5v_test_dwell_time_edit_edit) if 'ext_5v_test_dwell_time_edit_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'External 5V Test',
                        'ext_5v_test_trigger_source': trigger_msg_id,
                        'ext_5v_test_trigger_signal': trigger_signal,
                        'eol_ext_5v_measurement_source': eol_msg_id,
                        'eol_ext_5v_measurement_signal': eol_signal,
                        'feedback_signal_source': feedback_msg_id,
                        'feedback_signal': feedback_signal,
                        'tolerance_mv': tolerance_val,
                        'pre_dwell_time_ms': pre_dwell_val,
                        'dwell_time_ms': dwell_time_val,
                    }
                elif data['type'] == 'DC Bus Sensing':
                    # DC Bus Sensing: read all fields (DBC mode)
                    osc_channel = dc_bus_osc_channel_combo_edit.currentText().strip() if 'dc_bus_osc_channel_combo_edit' in locals() and dc_bus_osc_channel_combo_edit.count() else ''
                    
                    try:
                        feedback_msg_id = dc_bus_feedback_msg_combo_edit.currentData() if 'dc_bus_feedback_msg_combo_edit' in locals() else None
                    except Exception:
                        feedback_msg_id = None
                    feedback_signal = dc_bus_feedback_signal_combo_edit.currentText().strip() if 'dc_bus_feedback_signal_combo_edit' in locals() and dc_bus_feedback_signal_combo_edit.count() else ''
                    
                    # Dwell time (int)
                    def _to_int_or_none_dc_bus_dwell_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dwell_time_val = _to_int_or_none_dc_bus_dwell_edit(dc_bus_dwell_time_edit_edit) if 'dc_bus_dwell_time_edit_edit' in locals() else None
                    
                    # Tolerance (float, in V)
                    def _to_float_or_none_dc_bus_tolerance_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_val = _to_float_or_none_dc_bus_tolerance_edit(dc_bus_tolerance_edit_edit) if 'dc_bus_tolerance_edit_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'DC Bus Sensing',
                        'oscilloscope_channel': osc_channel,
                        'feedback_signal_source': feedback_msg_id,
                        'feedback_signal': feedback_signal,
                        'dwell_time_ms': dwell_time_val,
                        'tolerance_v': tolerance_val,
                    }
                elif data['type'] == 'Output Current Calibration':
                    # Output Current Calibration: read all fields (DBC mode)
                    try:
                        trigger_msg_id = output_current_trigger_msg_combo_edit.currentData() if 'output_current_trigger_msg_combo_edit' in locals() else None
                    except Exception:
                        trigger_msg_id = None
                    trigger_signal = output_current_trigger_signal_combo_edit.currentText().strip() if 'output_current_trigger_signal_combo_edit' in locals() and output_current_trigger_signal_combo_edit.count() else ''
                    
                    # Test Trigger Signal Value (int, 0-255)
                    def _to_int_or_none_output_current_trigger_value_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    trigger_value = _to_int_or_none_output_current_trigger_value_edit(output_current_trigger_value_edit_edit) if 'output_current_trigger_value_edit_edit' in locals() else None
                    
                    setpoint_signal = output_current_setpoint_signal_combo_edit.currentText().strip() if 'output_current_setpoint_signal_combo_edit' in locals() and output_current_setpoint_signal_combo_edit.count() else ''
                    
                    trim_signal = output_current_trim_signal_combo_edit.currentText().strip() if 'output_current_trim_signal_combo_edit' in locals() and output_current_trim_signal_combo_edit.count() else ''
                    
                    # Initial Trim Value (float, 0.0000-200.0000)
                    def _to_float_or_none_output_current_initial_trim_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    initial_trim_value = _to_float_or_none_output_current_initial_trim_edit(output_current_initial_trim_edit_edit) if 'output_current_initial_trim_edit_edit' in locals() else None
                    
                    try:
                        feedback_msg_id = output_current_feedback_msg_combo_edit.currentData() if 'output_current_feedback_msg_combo_edit' in locals() else None
                    except Exception:
                        feedback_msg_id = None
                    feedback_signal = output_current_feedback_signal_combo_edit.currentText().strip() if 'output_current_feedback_signal_combo_edit' in locals() and output_current_feedback_signal_combo_edit.count() else ''
                    
                    osc_channel = output_current_osc_channel_combo_edit.currentText().strip() if 'output_current_osc_channel_combo_edit' in locals() and output_current_osc_channel_combo_edit.count() else ''
                    timebase = output_current_timebase_combo_edit.currentText().strip() if 'output_current_timebase_combo_edit' in locals() and output_current_timebase_combo_edit.count() else ''
                    
                    # Minimum Test Current (float)
                    def _to_float_or_none_output_current_min_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    min_current = _to_float_or_none_output_current_min_edit(output_current_min_current_edit_edit) if 'output_current_min_current_edit_edit' in locals() else None
                    
                    # Maximum Test Current (float)
                    def _to_float_or_none_output_current_max_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    max_current = _to_float_or_none_output_current_max_edit(output_current_max_current_edit_edit) if 'output_current_max_current_edit_edit' in locals() else None
                    
                    # Step Current (float)
                    def _to_float_or_none_output_current_step_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    step_current = _to_float_or_none_output_current_step_edit(output_current_step_current_edit_edit) if 'output_current_step_current_edit_edit' in locals() else None
                    
                    # Pre-Acquisition Time (int)
                    def _to_int_or_none_output_current_pre_acq_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    pre_acq_time = _to_int_or_none_output_current_pre_acq_edit(output_current_pre_acq_edit_edit) if 'output_current_pre_acq_edit_edit' in locals() else None
                    
                    # Acquisition Time (int)
                    def _to_int_or_none_output_current_acq_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    acq_time = _to_int_or_none_output_current_acq_edit(output_current_acq_edit_edit) if 'output_current_acq_edit_edit' in locals() else None
                    
                    # Tolerance (float, in %)
                    def _to_float_or_none_output_current_tolerance_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_percent = _to_float_or_none_output_current_tolerance_edit(output_current_tolerance_edit_edit) if 'output_current_tolerance_edit_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'Output Current Calibration',
                        'test_trigger_source': trigger_msg_id,
                        'test_trigger_signal': trigger_signal,
                        'test_trigger_signal_value': trigger_value,
                        'current_setpoint_signal': setpoint_signal,
                        'output_current_trim_signal': trim_signal,
                        'initial_trim_value': initial_trim_value,
                        'feedback_signal_source': feedback_msg_id,
                        'feedback_signal': feedback_signal,
                        'oscilloscope_channel': osc_channel,
                        'oscilloscope_timebase': timebase,
                        'minimum_test_current': min_current,
                        'maximum_test_current': max_current,
                        'step_current': step_current,
                        'pre_acquisition_time_ms': pre_acq_time,
                        'acquisition_time_ms': acq_time,
                        'tolerance_percent': tolerance_percent,
                    }
                elif data['type'] == 'Charged HV Bus Test':
                    # Charged HV Bus Test: read all fields (DBC mode)
                    try:
                        cmd_msg_id = charged_hv_bus_cmd_msg_combo_edit.currentData() if 'charged_hv_bus_cmd_msg_combo_edit' in locals() else None
                    except Exception:
                        cmd_msg_id = None
                    trigger_signal = charged_hv_bus_trigger_signal_combo_edit.currentText().strip() if 'charged_hv_bus_trigger_signal_combo_edit' in locals() and charged_hv_bus_trigger_signal_combo_edit.count() else ''
                    
                    # Test Trigger Signal Value (int, 0-255)
                    def _to_int_or_none_charged_hv_bus_trigger_value_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    trigger_value = _to_int_or_none_charged_hv_bus_trigger_value_edit(charged_hv_bus_trigger_value_edit_edit) if 'charged_hv_bus_trigger_value_edit_edit' in locals() else None
                    
                    trim_signal = charged_hv_bus_trim_signal_combo_edit.currentText().strip() if 'charged_hv_bus_trim_signal_combo_edit' in locals() and charged_hv_bus_trim_signal_combo_edit.count() else ''
                    
                    # Fallback Output Current Trim Value (float, 0-200)
                    def _to_float_or_none_charged_hv_bus_fallback_trim_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    fallback_trim = _to_float_or_none_charged_hv_bus_fallback_trim_edit(charged_hv_bus_fallback_trim_edit_edit) if 'charged_hv_bus_fallback_trim_edit_edit' in locals() else None
                    
                    setpoint_signal = charged_hv_bus_setpoint_signal_combo_edit.currentText().strip() if 'charged_hv_bus_setpoint_signal_combo_edit' in locals() and charged_hv_bus_setpoint_signal_combo_edit.count() else ''
                    
                    # Output Test Current (float, 0-40)
                    def _to_float_or_none_charged_hv_bus_output_current_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    output_current = _to_float_or_none_charged_hv_bus_output_current_edit(charged_hv_bus_output_current_edit_edit) if 'charged_hv_bus_output_current_edit_edit' in locals() else None
                    
                    try:
                        feedback_msg_id = charged_hv_bus_feedback_msg_combo_edit.currentData() if 'charged_hv_bus_feedback_msg_combo_edit' in locals() else None
                    except Exception:
                        feedback_msg_id = None
                    dut_state_signal = charged_hv_bus_dut_state_signal_combo_edit.currentText().strip() if 'charged_hv_bus_dut_state_signal_combo_edit' in locals() and charged_hv_bus_dut_state_signal_combo_edit.count() else ''
                    enable_relay_signal = charged_hv_bus_enable_relay_signal_combo_edit.currentText().strip() if 'charged_hv_bus_enable_relay_signal_combo_edit' in locals() and charged_hv_bus_enable_relay_signal_combo_edit.count() else ''
                    enable_pfc_signal = charged_hv_bus_enable_pfc_signal_combo_edit.currentText().strip() if 'charged_hv_bus_enable_pfc_signal_combo_edit' in locals() and charged_hv_bus_enable_pfc_signal_combo_edit.count() else ''
                    pfc_power_good_signal = charged_hv_bus_pfc_power_good_signal_combo_edit.currentText().strip() if 'charged_hv_bus_pfc_power_good_signal_combo_edit' in locals() and charged_hv_bus_pfc_power_good_signal_combo_edit.count() else ''
                    pcmc_signal = charged_hv_bus_pcmc_signal_combo_edit.currentText().strip() if 'charged_hv_bus_pcmc_signal_combo_edit' in locals() and charged_hv_bus_pcmc_signal_combo_edit.count() else ''
                    psfb_fault_signal = charged_hv_bus_psfb_fault_signal_combo_edit.currentText().strip() if 'charged_hv_bus_psfb_fault_signal_combo_edit' in locals() and charged_hv_bus_psfb_fault_signal_combo_edit.count() else ''
                    
                    # Test Time (int, >= 1000)
                    def _to_int_or_none_charged_hv_bus_test_time_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    test_time = _to_int_or_none_charged_hv_bus_test_time_edit(charged_hv_bus_test_time_edit_edit) if 'charged_hv_bus_test_time_edit_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'Charged HV Bus Test',
                        'command_signal_source': cmd_msg_id,
                        'test_trigger_signal': trigger_signal,
                        'test_trigger_signal_value': trigger_value,
                        'set_output_current_trim_signal': trim_signal,
                        'fallback_output_current_trim_value': fallback_trim,
                        'set_output_current_setpoint_signal': setpoint_signal,
                        'output_test_current': output_current,
                        'feedback_signal_source': feedback_msg_id,
                        'dut_test_state_signal': dut_state_signal,
                        'enable_relay_signal': enable_relay_signal,
                        'enable_pfc_signal': enable_pfc_signal,
                        'pfc_power_good_signal': pfc_power_good_signal,
                        'pcmc_signal': pcmc_signal,
                        'psfb_fault_signal': psfb_fault_signal,
                        'test_time_ms': test_time,
                    }
                elif data['type'] == 'Charger Functional Test':
                    # Charger Functional Test: read all fields (DBC mode)
                    try:
                        cmd_msg_id = charger_functional_cmd_msg_combo_edit.currentData() if 'charger_functional_cmd_msg_combo_edit' in locals() else None
                    except Exception:
                        cmd_msg_id = None
                    trigger_signal = charger_functional_trigger_signal_combo_edit.currentText().strip() if 'charger_functional_trigger_signal_combo_edit' in locals() and charger_functional_trigger_signal_combo_edit.count() else ''
                    
                    # Test Trigger Signal Value (int, 0-255)
                    def _to_int_or_none_charger_functional_trigger_value_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    trigger_value = _to_int_or_none_charger_functional_trigger_value_edit(charger_functional_trigger_value_edit_edit) if 'charger_functional_trigger_value_edit_edit' in locals() else None
                    
                    trim_signal = charger_functional_trim_signal_combo_edit.currentText().strip() if 'charger_functional_trim_signal_combo_edit' in locals() and charger_functional_trim_signal_combo_edit.count() else ''
                    
                    # Fallback Output Current Trim Value (float, 0-200)
                    def _to_float_or_none_charger_functional_fallback_trim_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    fallback_trim = _to_float_or_none_charger_functional_fallback_trim_edit(charger_functional_fallback_trim_edit_edit) if 'charger_functional_fallback_trim_edit_edit' in locals() else None
                    
                    setpoint_signal = charger_functional_setpoint_signal_combo_edit.currentText().strip() if 'charger_functional_setpoint_signal_combo_edit' in locals() and charger_functional_setpoint_signal_combo_edit.count() else ''
                    
                    # Output Test Current (float, 0-40)
                    def _to_float_or_none_charger_functional_output_current_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    output_current = _to_float_or_none_charger_functional_output_current_edit(charger_functional_output_current_edit_edit) if 'charger_functional_output_current_edit_edit' in locals() else None
                    
                    try:
                        feedback_msg_id = charger_functional_feedback_msg_combo_edit.currentData() if 'charger_functional_feedback_msg_combo_edit' in locals() else None
                    except Exception:
                        feedback_msg_id = None
                    dut_state_signal = charger_functional_dut_state_signal_combo_edit.currentText().strip() if 'charger_functional_dut_state_signal_combo_edit' in locals() and charger_functional_dut_state_signal_combo_edit.count() else ''
                    enable_relay_signal = charger_functional_enable_relay_signal_combo_edit.currentText().strip() if 'charger_functional_enable_relay_signal_combo_edit' in locals() and charger_functional_enable_relay_signal_combo_edit.count() else ''
                    enable_pfc_signal = charger_functional_enable_pfc_signal_combo_edit.currentText().strip() if 'charger_functional_enable_pfc_signal_combo_edit' in locals() and charger_functional_enable_pfc_signal_combo_edit.count() else ''
                    pfc_power_good_signal = charger_functional_pfc_power_good_signal_combo_edit.currentText().strip() if 'charger_functional_pfc_power_good_signal_combo_edit' in locals() and charger_functional_pfc_power_good_signal_combo_edit.count() else ''
                    pcmc_signal = charger_functional_pcmc_signal_combo_edit.currentText().strip() if 'charger_functional_pcmc_signal_combo_edit' in locals() and charger_functional_pcmc_signal_combo_edit.count() else ''
                    output_current_signal = charger_functional_output_current_signal_combo_edit.currentText().strip() if 'charger_functional_output_current_signal_combo_edit' in locals() and charger_functional_output_current_signal_combo_edit.count() else ''
                    psfb_fault_signal = charger_functional_psfb_fault_signal_combo_edit.currentText().strip() if 'charger_functional_psfb_fault_signal_combo_edit' in locals() and charger_functional_psfb_fault_signal_combo_edit.count() else ''
                    
                    # Output Current Tolerance (float, >= 0)
                    def _to_float_or_none_charger_functional_tolerance_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    output_current_tolerance = _to_float_or_none_charger_functional_tolerance_edit(charger_functional_output_current_tolerance_edit_edit) if 'charger_functional_output_current_tolerance_edit_edit' in locals() else None
                    
                    # Test Time (int, >= 1000)
                    def _to_int_or_none_charger_functional_test_time_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    test_time = _to_int_or_none_charger_functional_test_time_edit(charger_functional_test_time_edit_edit) if 'charger_functional_test_time_edit_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'Charger Functional Test',
                        'command_signal_source': cmd_msg_id,
                        'test_trigger_signal': trigger_signal,
                        'test_trigger_signal_value': trigger_value,
                        'set_output_current_trim_signal': trim_signal,
                        'fallback_output_current_trim_value': fallback_trim,
                        'set_output_current_setpoint_signal': setpoint_signal,
                        'output_test_current': output_current,
                        'feedback_signal_source': feedback_msg_id,
                        'dut_test_state_signal': dut_state_signal,
                        'enable_relay_signal': enable_relay_signal,
                        'enable_pfc_signal': enable_pfc_signal,
                        'pfc_power_good_signal': pfc_power_good_signal,
                        'pcmc_signal': pcmc_signal,
                        'output_current_signal': output_current_signal,
                        'psfb_fault_signal': psfb_fault_signal,
                        'output_current_tolerance': output_current_tolerance,
                        'test_time_ms': test_time,
                    }
            else:
                if data['type'] == 'Digital Logic Test':
                    try:
                        can_id = int(dig_can.text().strip(),0) if dig_can.text().strip() else None
                    except Exception:
                        can_id = None
                    try:
                        dig_dwell = int(dig_dwell_ms.text().strip()) if hasattr(dig_dwell_ms, 'text') and dig_dwell_ms.text().strip() else None
                    except Exception:
                        dig_dwell = None
                    data['actuation'] = {'type':'Digital Logic Test','can_id':can_id,'signal':dig_signal.text().strip(),'value_low':dig_value_low.text().strip(),'value_high':dig_value_high.text().strip(),'dwell_ms':dig_dwell}
                elif data['type'] == 'Analog Sweep Test':
                    # Non-DBC analog test: read all fields
                    try:
                        mux_channel_val = int(mux_chan.text().strip(), 0) if mux_chan.text().strip() else None
                    except Exception:
                        mux_channel_val = None
                    try:
                        dac_id = int(dac_can.text().strip(), 0) if dac_can.text().strip() else None
                    except Exception:
                        dac_id = None
                    dac_cmd_sig = dac_cmd.text().strip()
                    
                    # Read numeric DAC parameters using the assigned variables
                    def _to_int_or_none(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dac_min = _to_int_or_none(dac_min_mv)
                    dac_max = _to_int_or_none(dac_max_mv)
                    dac_step = _to_int_or_none(dac_step_mv)
                    dac_dwell = _to_int_or_none(dac_dwell_ms)
                    # Read expected gain (optional float)
                    expected_gain_val = None
                    try:
                        if 'expected_gain_edit' in locals():
                            expected_gain_text = expected_gain_edit.text().strip() if hasattr(expected_gain_edit, 'text') else ''
                            if expected_gain_text:
                                expected_gain_val = float(expected_gain_text)
                    except (ValueError, TypeError):
                        pass
                    # Read gain tolerance (optional float)
                    gain_tolerance_val = None
                    try:
                        if 'gain_tolerance_edit' in locals():
                            gain_tolerance_text = gain_tolerance_edit.text().strip() if hasattr(gain_tolerance_edit, 'text') else ''
                            if gain_tolerance_text:
                                gain_tolerance_val = float(gain_tolerance_text)
                                if gain_tolerance_val < 0:
                                    raise ValueError("Gain tolerance cannot be negative")
                    except (ValueError, TypeError):
                        pass
                    
                    data['actuation'] = {
                        'type': 'Analog Sweep Test',
                        'dac_can_id': dac_id,
                        'dac_command_signal': dac_cmd_sig,
                        'mux_channel_value': mux_channel_val,
                        'dac_min_mv': dac_min,
                        'dac_max_mv': dac_max,
                        'dac_step_mv': dac_step,
                        'dac_dwell_ms': dac_dwell,
                    }
                    if expected_gain_val is not None:
                        data['actuation']['expected_gain'] = expected_gain_val
                elif data['type'] == 'Phase Current Test':
                    # Phase Current Calibration (no DBC): read from text fields
                    try:
                        cmd_msg_id = int(phase_current_cmd_msg_edit.text().strip(), 0) if 'phase_current_cmd_msg_edit' in locals() and phase_current_cmd_msg_edit.text().strip() else None
                    except Exception:
                        cmd_msg_id = None
                    trigger_test_sig = phase_current_trigger_signal_edit.text().strip() if 'phase_current_trigger_signal_edit' in locals() else ''
                    iq_ref_sig = phase_current_iq_ref_signal_edit.text().strip() if 'phase_current_iq_ref_signal_edit' in locals() else ''
                    id_ref_sig = phase_current_id_ref_signal_edit.text().strip() if 'phase_current_id_ref_signal_edit' in locals() else ''
                    
                    try:
                        phase_current_can_id = int(phase_current_msg_edit.text().strip(), 0) if 'phase_current_msg_edit' in locals() and phase_current_msg_edit.text().strip() else None
                    except Exception:
                        phase_current_can_id = None
                    phase_current_v_sig = phase_current_v_signal_edit.text().strip() if 'phase_current_v_signal_edit' in locals() else ''
                    phase_current_w_sig = phase_current_w_signal_edit.text().strip() if 'phase_current_w_signal_edit' in locals() else ''
                    
                    def _to_float_or_none(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    min_iq = _to_float_or_none(min_iq_edit) if 'min_iq_edit' in locals() else None
                    max_iq = _to_float_or_none(max_iq_edit) if 'max_iq_edit' in locals() else None
                    step_iq = _to_float_or_none(step_iq_edit) if 'step_iq_edit' in locals() else None
                    
                    def _to_int_or_none_duration(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    ipc_test_duration = _to_int_or_none_duration(ipc_test_duration_edit) if 'ipc_test_duration_edit' in locals() else None
                    
                    osc_phase_v_ch = osc_phase_v_ch_combo.currentText().strip() if 'osc_phase_v_ch_combo' in locals() and osc_phase_v_ch_combo.count() else ''
                    osc_phase_w_ch = osc_phase_w_ch_combo.currentText().strip() if 'osc_phase_w_ch_combo' in locals() and osc_phase_w_ch_combo.count() else ''
                    
                    data['actuation'] = {
                        'type': 'Phase Current Test',
                        'command_message': cmd_msg_id,
                        'trigger_test_signal': trigger_test_sig,
                        'iq_ref_signal': iq_ref_sig,
                        'id_ref_signal': id_ref_sig,
                        'phase_current_signal_source': phase_current_can_id,
                        'phase_current_v_signal': phase_current_v_sig,
                        'phase_current_w_signal': phase_current_w_sig,
                        'min_iq': min_iq,
                        'max_iq': max_iq,
                        'step_iq': step_iq,
                        'ipc_test_duration_ms': ipc_test_duration,
                        'oscilloscope_phase_v_ch': osc_phase_v_ch,
                        'oscilloscope_phase_w_ch': osc_phase_w_ch,
                    }
                elif data['type'] == 'Analog Static Test':
                    # Analog Static Test (no DBC): read from text fields
                    try:
                        fb_msg_id = int(analog_static_fb_msg_edit_edit.text().strip(), 0) if 'analog_static_fb_msg_edit_edit' in locals() and analog_static_fb_msg_edit_edit.text().strip() else None
                    except Exception:
                        fb_msg_id = None
                    fb_signal = analog_static_fb_signal_edit_edit.text().strip() if 'analog_static_fb_signal_edit_edit' in locals() else ''
                    
                    try:
                        eol_msg_id = int(analog_static_eol_msg_edit_edit.text().strip(), 0) if 'analog_static_eol_msg_edit_edit' in locals() and analog_static_eol_msg_edit_edit.text().strip() else None
                    except Exception:
                        eol_msg_id = None
                    eol_signal = analog_static_eol_signal_edit_edit.text().strip() if 'analog_static_eol_signal_edit_edit' in locals() else ''
                    
                    # Tolerance (float)
                    def _to_float_or_none_tolerance_fallback_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_val = _to_float_or_none_tolerance_fallback_edit(tolerance_edit_fallback_edit) if 'tolerance_edit_fallback_edit' in locals() else None
                    
                    # Pre-dwell and dwell times (int)
                    def _to_int_or_none_time_fallback_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    pre_dwell_val = _to_int_or_none_time_fallback_edit(pre_dwell_time_edit_fallback_edit) if 'pre_dwell_time_edit_fallback_edit' in locals() else None
                    dwell_time_val = _to_int_or_none_time_fallback_edit(dwell_time_edit_fallback_edit) if 'dwell_time_edit_fallback_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'Analog Static Test',
                        'feedback_signal_source': fb_msg_id,
                        'feedback_signal': fb_signal,
                        'eol_signal_source': eol_msg_id,
                        'eol_signal': eol_signal,
                        'tolerance_mv': tolerance_val,
                        'pre_dwell_time_ms': pre_dwell_val,
                        'dwell_time_ms': dwell_time_val,
                    }
                elif data['type'] == 'Temperature Validation Test':
                    # Temperature Validation Test (no DBC): read from text fields
                    try:
                        fb_msg_id = int(temp_val_fb_msg_edit_edit.text().strip(), 0) if 'temp_val_fb_msg_edit_edit' in locals() and temp_val_fb_msg_edit_edit.text().strip() else None
                    except Exception:
                        fb_msg_id = None
                    fb_signal = temp_val_fb_signal_edit_edit.text().strip() if 'temp_val_fb_signal_edit_edit' in locals() else ''
                    
                    # Reference temperature (float)
                    def _to_float_or_none_reference_fallback_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    reference_temp_val = _to_float_or_none_reference_fallback_edit(temp_val_reference_edit_fallback_edit) if 'temp_val_reference_edit_fallback_edit' in locals() else None
                    
                    # Tolerance (float)
                    def _to_float_or_none_temp_tolerance_fallback_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    tolerance_c_val = _to_float_or_none_temp_tolerance_fallback_edit(temp_val_tolerance_edit_fallback_edit) if 'temp_val_tolerance_edit_fallback_edit' in locals() else None
                    
                    # Dwell time (int)
                    def _to_int_or_none_dwell_fallback_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dwell_time_val = _to_int_or_none_dwell_fallback_edit(temp_val_dwell_time_edit_fallback_edit) if 'temp_val_dwell_time_edit_fallback_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'Temperature Validation Test',
                        'feedback_signal_source': fb_msg_id,
                        'feedback_signal': fb_signal,
                        'reference_temperature_c': reference_temp_val,
                        'tolerance_c': tolerance_c_val,
                        'dwell_time_ms': dwell_time_val,
                    }
                elif data['type'] == 'Analog PWM Sensor':
                    # Analog PWM Sensor Test (no DBC): read from text fields
                    try:
                        fb_msg_id = int(analog_pwm_fb_msg_edit_edit.text().strip(), 0) if 'analog_pwm_fb_msg_edit_edit' in locals() and analog_pwm_fb_msg_edit_edit.text().strip() else None
                    except Exception:
                        fb_msg_id = None
                    pwm_frequency_signal = analog_pwm_frequency_signal_edit_edit.text().strip() if 'analog_pwm_frequency_signal_edit_edit' in locals() else ''
                    duty_signal = analog_pwm_duty_signal_edit_edit.text().strip() if 'analog_pwm_duty_signal_edit_edit' in locals() else ''
                    
                    # Reference PWM frequency (float)
                    def _to_float_or_none_pwm_freq_reference_fallback_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    reference_pwm_freq_val = _to_float_or_none_pwm_freq_reference_fallback_edit(analog_pwm_reference_frequency_edit_fallback_edit) if 'analog_pwm_reference_frequency_edit_fallback_edit' in locals() else None
                    
                    # Reference duty (float)
                    def _to_float_or_none_duty_reference_fallback_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    reference_duty_val = _to_float_or_none_duty_reference_fallback_edit(analog_pwm_reference_duty_edit_fallback_edit) if 'analog_pwm_reference_duty_edit_fallback_edit' in locals() else None
                    
                    # PWM frequency tolerance (float)
                    def _to_float_or_none_pwm_freq_tolerance_fallback_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    pwm_freq_tolerance_val = _to_float_or_none_pwm_freq_tolerance_fallback_edit(analog_pwm_frequency_tolerance_edit_fallback_edit) if 'analog_pwm_frequency_tolerance_edit_fallback_edit' in locals() else None
                    
                    # Duty tolerance (float)
                    def _to_float_or_none_duty_tolerance_fallback_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return float(txt) if txt else None
                        except Exception:
                            return None
                    
                    duty_tolerance_val = _to_float_or_none_duty_tolerance_fallback_edit(analog_pwm_duty_tolerance_edit_fallback_edit) if 'analog_pwm_duty_tolerance_edit_fallback_edit' in locals() else None
                    
                    # Acquisition time (int)
                    def _to_int_or_none_acquisition_fallback_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    acquisition_time_val = _to_int_or_none_acquisition_fallback_edit(analog_pwm_acquisition_time_edit_fallback_edit) if 'analog_pwm_acquisition_time_edit_fallback_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'Analog PWM Sensor',
                        'feedback_signal_source': fb_msg_id,
                        'feedback_pwm_frequency_signal': pwm_frequency_signal,
                        'feedback_duty_signal': duty_signal,
                        'reference_pwm_frequency': reference_pwm_freq_val,
                        'reference_duty': reference_duty_val,
                        'pwm_frequency_tolerance': pwm_freq_tolerance_val,
                        'duty_tolerance': duty_tolerance_val,
                        'acquisition_time_ms': acquisition_time_val,
                    }
                elif data['type'] == 'Fan Control Test':
                    # Fan Control Test (no DBC): read from text fields
                    try:
                        trigger_msg_id = int(fan_control_trigger_msg_edit_edit.text().strip(), 0) if 'fan_control_trigger_msg_edit_edit' in locals() and fan_control_trigger_msg_edit_edit.text().strip() else None
                    except Exception:
                        trigger_msg_id = None
                    trigger_signal = fan_control_trigger_signal_edit_edit.text().strip() if 'fan_control_trigger_signal_edit_edit' in locals() else ''
                    
                    try:
                        feedback_msg_id = int(fan_control_feedback_msg_edit_edit.text().strip(), 0) if 'fan_control_feedback_msg_edit_edit' in locals() and fan_control_feedback_msg_edit_edit.text().strip() else None
                    except Exception:
                        feedback_msg_id = None
                    fan_enabled_signal = fan_control_enabled_signal_edit_edit.text().strip() if 'fan_control_enabled_signal_edit_edit' in locals() else ''
                    fan_tach_signal = fan_control_tach_signal_edit_edit.text().strip() if 'fan_control_tach_signal_edit_edit' in locals() else ''
                    fan_fault_signal = fan_control_fault_signal_edit_edit.text().strip() if 'fan_control_fault_signal_edit_edit' in locals() else ''
                    
                    # Dwell time (int)
                    def _to_int_or_none_fan_dwell_fallback_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    dwell_time_val = _to_int_or_none_fan_dwell_fallback_edit(fan_control_dwell_time_edit_fallback_edit) if 'fan_control_dwell_time_edit_fallback_edit' in locals() else None
                    
                    # Test timeout (int)
                    def _to_int_or_none_fan_timeout_fallback_edit(txt_widget):
                        try:
                            txt = txt_widget.text().strip() if hasattr(txt_widget, 'text') else ''
                            return int(txt) if txt else None
                        except Exception:
                            return None
                    
                    timeout_val = _to_int_or_none_fan_timeout_fallback_edit(fan_control_timeout_edit_fallback_edit) if 'fan_control_timeout_edit_fallback_edit' in locals() else None
                    
                    data['actuation'] = {
                        'type': 'Fan Control Test',
                        'fan_test_trigger_source': trigger_msg_id,
                        'fan_test_trigger_signal': trigger_signal,
                        'fan_control_feedback_source': feedback_msg_id,
                        'fan_enabled_signal': fan_enabled_signal,
                        'fan_tach_feedback_signal': fan_tach_signal,
                        'fan_fault_feedback_signal': fan_fault_signal,
                        'dwell_time_ms': dwell_time_val,
                        'test_timeout_ms': timeout_val,
                    }

            # Validate test before saving
            is_valid, error_msg = self._validate_test(data)
            if not is_valid:
                QtWidgets.QMessageBox.warning(dlg, 'Invalid Test Configuration', f'Cannot save test: {error_msg}')
                return
            
            old_test_name = self._tests[idx].get('name', '')
            self._tests[idx] = data
            self.test_list.currentItem().setText(data['name'])
            # If test name changed, update execution data key
            new_test_name = data.get('name', '')
            if old_test_name != new_test_name and old_test_name in self._test_execution_data:
                self._test_execution_data[new_test_name] = self._test_execution_data.pop(old_test_name)
            # refresh JSON preview for current selection
            try:
                self._on_select_test(None, None)
            except Exception:
                pass
            # Sync Test Plan
            try:
                self._populate_test_plan()
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
                            self._update_signal_with_status('feedback_signal', v)
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
            # Retrieve plot data that was captured at the end of run_single_test
            plot_data = None
            test_name = t.get('name', '<unnamed>')
            test_type = t.get('type', '')
            
            if test_type == 'Analog Sweep Test':
                # First try to get from temporary storage (captured in run_single_test)
                if hasattr(self, '_test_plot_data_temp') and test_name in self._test_plot_data_temp:
                    plot_data = self._test_plot_data_temp.pop(test_name)  # Remove after retrieval
                    logger.debug(f"Retrieved stored plot data for {test_name} (single test)")
                # Fallback: try to read from global arrays (for backwards compatibility)
                elif hasattr(self, 'plot_dac_voltages') and hasattr(self, 'plot_feedback_values'):
                    if self.plot_dac_voltages and self.plot_feedback_values:
                        plot_data = {
                            'dac_voltages': list(self.plot_dac_voltages),
                            'feedback_values': list(self.plot_feedback_values)
                        }
                        logger.debug(f"Used global plot data for {test_name} (single test, fallback)")
            elif test_type == 'Phase Current Test':
                # Retrieve plot data for phase current calibration tests
                if hasattr(self, '_test_plot_data_temp') and test_name in self._test_plot_data_temp:
                    plot_data = self._test_plot_data_temp.pop(test_name)  # Remove after retrieval
                    logger.debug(f"Retrieved stored plot data for {test_name} (phase current test)")
            
            self._update_test_plan_row(t, result, exec_time, info, plot_data)
        except Exception as e:
            end_time = time.time()
            exec_time = f"{end_time - start_time:.2f}s"
            self.status_label.setText('Test error')
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.test_log.appendPlainText(f'[{timestamp}] Error: {e}')
            # Retrieve plot data that was captured at the end of run_single_test (even if failed, may have partial data)
            plot_data = None
            test_name = t.get('name', '<unnamed>')
            test_type = t.get('type', '')
            
            if test_type == 'Analog Sweep Test':
                # First try to get from temporary storage (captured in run_single_test)
                if hasattr(self, '_test_plot_data_temp') and test_name in self._test_plot_data_temp:
                    plot_data = self._test_plot_data_temp.pop(test_name)  # Remove after retrieval
                    logger.debug(f"Retrieved stored plot data for {test_name} (exception case)")
                # Fallback: try to read from global arrays (for backwards compatibility)
                elif hasattr(self, 'plot_dac_voltages') and hasattr(self, 'plot_feedback_values'):
                    if self.plot_dac_voltages and self.plot_feedback_values:
                        plot_data = {
                            'dac_voltages': list(self.plot_dac_voltages),
                            'feedback_values': list(self.plot_feedback_values)
                        }
                        logger.debug(f"Used global plot data for {test_name} (exception case, fallback)")
            elif test_type == 'Phase Current Test':
                # Retrieve plot data for phase current calibration tests
                if hasattr(self, '_test_plot_data_temp') and test_name in self._test_plot_data_temp:
                    plot_data = self._test_plot_data_temp.pop(test_name)  # Remove after retrieval
                    logger.debug(f"Retrieved stored plot data for {test_name} (exception case, phase current)")
            
            self._update_test_plan_row(t, 'ERROR', exec_time, str(e), plot_data)
        finally:
            # clear current feedback monitor
            try:
                self._current_feedback = None
            except Exception:
                pass

    def _on_clear_results(self) -> None:
        """Clear all test results, logs, and plots from the Test Status tab.
        
        Resets test statuses to "Not Run", clears execution log, and clears the feedback
        vs DAC voltage plot. Useful for starting a fresh test session.
        Execution data is preserved but statuses are reset.
        """
        # Clear execution data statuses (preserve execution history, just reset status)
        for test_name in self._test_execution_data:
            self._test_execution_data[test_name]['status'] = 'Not Run'
            # Remove DUT UID from execution data to ensure clean state
            if 'dut_uid' in self._test_execution_data[test_name]:
                del self._test_execution_data[test_name]['dut_uid']
        
        # Clear execution log
        self.test_log.clear()
        self.status_label.setText('Results cleared')
        
        # Clear DUT UID input and state (user must enter it again for next test sequence)
        if hasattr(self, 'dut_uid_input'):
            self.dut_uid_input.clear()
            self.dut_uid_input.setStyleSheet("")  # Reset visual feedback
            self.dut_uid_input.setEnabled(True)   # Ensure enabled
        self.current_dut_uid = None
        self._invalidate_dut_uid_cache()
        
        # Repopulate Test Plan with "Not Run" statuses
        try:
            self._populate_test_plan()
        except Exception:
            pass
        
        # Also clear the plot
        try:
            self._clear_plot()
        except Exception:
            pass

    def _on_repeat_test(self):
        """Repeat the currently selected test.
        
        Note: DUT UID is not required for single test execution,
        only for test sequences via Run Sequence button.
        """
        self._on_run_selected()
    
    @QtCore.Slot()
    def _show_charged_hv_bus_safety_dialog(self) -> None:
        """Show pre-test safety dialog for Charged HV Bus Test.
        
        This method must be called from the main GUI thread.
        It can be invoked from a background thread using QMetaObject.invokeMethod
        with Qt.BlockingQueuedConnection.
        
        The result is stored in self._charged_hv_bus_dialog_result for retrieval.
        """
        from PySide6.QtWidgets import QMessageBox
        try:
            # Ensure we're in the main thread
            from PySide6 import QtCore
            if QtCore.QThread.currentThread() != QtCore.QCoreApplication.instance().thread():
                logger.error("_show_charged_hv_bus_safety_dialog called from non-main thread!")
                self._charged_hv_bus_dialog_result = QMessageBox.No
                return
            
            # Create dialog with proper parent to ensure it's modal
            msg_box = QMessageBox(self)
            msg_box.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            msg_box.setWindowTitle("Pre-Test Safety Check - Charged HV Bus Test")
            msg_box.setText("Hardware Connection Requirements:")
            msg_box.setInformativeText(
                "1. Ensure that AC Input is connected to a switchable AC Input\n"
                "2. Ensure that DC Output is connected to a Battery/Load Back\n\n"
                "Proceed to Run Test?"
            )
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.Yes)
            
            # Show dialog and store result
            # exec() will block until user clicks a button
            result = msg_box.exec()
            self._charged_hv_bus_dialog_result = result
        except Exception as e:
            logger.error(f"Error in _show_charged_hv_bus_safety_dialog: {e}", exc_info=True)
            # Return No on error to be safe
            self._charged_hv_bus_dialog_result = QMessageBox.No
    
    @QtCore.Slot()
    def _show_charger_functional_safety_dialog(self) -> None:
        """Show pre-test safety dialog for Charger Functional Test.
        
        This method must be called from the main GUI thread.
        It can be invoked from a background thread using QMetaObject.invokeMethod
        with Qt.BlockingQueuedConnection.
        
        The result is stored in self._charger_functional_dialog_result for retrieval.
        """
        from PySide6.QtWidgets import QMessageBox
        try:
            # Ensure we're in the main thread
            from PySide6 import QtCore
            if QtCore.QThread.currentThread() != QtCore.QCoreApplication.instance().thread():
                logger.error("_show_charger_functional_safety_dialog called from non-main thread!")
                self._charger_functional_dialog_result = QMessageBox.No
                return
            
            # Create dialog with proper parent to ensure it's modal
            msg_box = QMessageBox(self)
            msg_box.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            msg_box.setWindowTitle("Pre-Test Safety Check - Charger Functional Test")
            msg_box.setText("Hardware Connection Requirements:")
            msg_box.setInformativeText(
                "1. Ensure that AC Input is connected to a switchable AC Input\n"
                "2. Ensure that DC Output is connected to a Battery/Load Bank\n\n"
                "Proceed to Run Test?"
            )
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.Yes)
            
            # Show dialog and store result
            # exec() will block until user clicks a button
            result = msg_box.exec()
            self._charger_functional_dialog_result = result
        except Exception as e:
            logger.error(f"Error in _show_charger_functional_safety_dialog: {e}", exc_info=True)
            # Return No on error to be safe
            self._charger_functional_dialog_result = QMessageBox.No
    
    @QtCore.Slot()
    def _show_output_current_calibration_safety_dialog(self) -> None:
        """Show pre-test safety dialog for Output Current Calibration Test.
        
        This method must be called from the main GUI thread.
        It can be invoked from a background thread using QMetaObject.invokeMethod
        with Qt.BlockingQueuedConnection.
        
        The result is stored in self._output_current_calibration_dialog_result for retrieval.
        """
        from PySide6.QtWidgets import QMessageBox
        try:
            # Ensure we're in the main thread
            from PySide6 import QtCore
            if QtCore.QThread.currentThread() != QtCore.QCoreApplication.instance().thread():
                logger.error("_show_output_current_calibration_safety_dialog called from non-main thread!")
                self._output_current_calibration_dialog_result = QMessageBox.No
                return
            
            # Create dialog with proper parent to ensure it's modal
            msg_box = QMessageBox(self)
            msg_box.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            msg_box.setWindowTitle("Pre-Test Safety Check - Output Current Calibration Test")
            msg_box.setText("Hardware Connection Requirements:")
            msg_box.setInformativeText(
                "1. Ensure that AC Input is connected to a Regulated Power Supply with Maximum 60V and current limited.\n"
                "2. Ensure that DC Output is connected to a appropriate Low resistive load for current calibration.\n\n"
                "Proceed to Run Test?"
            )
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.Yes)
            
            # Show dialog and store result
            # exec() will block until user clicks a button
            result = msg_box.exec()
            self._output_current_calibration_dialog_result = result
        except Exception as e:
            logger.error(f"Error in _show_output_current_calibration_safety_dialog: {e}", exc_info=True)
            # Return No on error to be safe
            self._output_current_calibration_dialog_result = QMessageBox.No
    
    @QtCore.Slot()
    def _request_test_sequence_pause(self) -> None:
        """Safely request pause on test execution thread from main thread.
        
        This method must be called from the main GUI thread.
        It can be invoked from a background thread using QMetaObject.invokeMethod
        with Qt.QueuedConnection.
        """
        try:
            if self.test_execution_thread is not None and self.test_execution_thread.isRunning():
                self.test_execution_thread.pause()
                logger.info("Test sequence pause requested via safe method")
        except Exception as e:
            logger.error(f"Error requesting pause: {e}", exc_info=True)

    def _on_run_sequence(self) -> None:
        """Execute all configured tests in sequence using background thread.
        
        Phase 2: Uses TestExecutionThread to run tests asynchronously,
        preventing UI blocking. Progress is updated via Qt signals.
        """
        # Phase 2: Use async thread for test execution
        if self.TestExecutionThread is None:
            QtWidgets.QMessageBox.critical(self, 'Error', 'TestExecutionThread not available - this should not happen')
            logger.error("TestExecutionThread not available in _on_run_sequence")
            return
        
        # Check if already running
        if self.test_execution_thread is not None and self.test_execution_thread.isRunning():
            logger.warning("Test sequence already running, ignoring request")
            return
        
        if not self._tests:
            logger.warning("Run Sequence called but _tests is empty")
            self.status_label.setText('No tests to run - Load tests first')
            self.tabs_main.setCurrentIndex(self.status_tab_index)
            QtWidgets.QMessageBox.warning(self, 'No Tests', 'No tests loaded. Please load a test profile from Test Configurator tab first.')
            return
        
        # Check if DUT UID is populated and valid
        dut_uid, error_msg = self._get_validated_dut_uid()
        if dut_uid is None:
            # Determine error type for better messaging
            text = self.dut_uid_input.text().strip()
            if not text:
                error_type = 'empty'
                details = ""
            else:
                try:
                    val = int(text)
                    if val <= 0:
                        error_type = 'invalid_range'
                        details = str(val)
                    else:
                        error_type = 'invalid_format'
                        details = text
                except ValueError:
                    error_type = 'invalid_format'
                    details = text
            
            logger.warning(f"Run Sequence called but DUT UID is invalid: {error_type} - {details}")
            self._show_dut_uid_error(error_type, details)
            return
        
        # Check if CAN adapter is connected
        can_connected = False
        if self.can_service is not None:
            try:
                can_connected = self.can_service.is_connected()
            except Exception:
                pass
        
        if not can_connected:
            logger.warning("Run Sequence called but CAN adapter not connected")
            self.status_label.setText('CAN adapter not connected')
            self.tabs_main.setCurrentIndex(self.status_tab_index)
            QtWidgets.QMessageBox.warning(self, 'Adapter Not Connected', 'CAN adapter must be connected before running tests.\n\nPlease go to CAN Data View tab and click "Connect".')
            return
        
        # Switch to Test Status tab
        self.tabs_main.setCurrentIndex(self.status_tab_index)
        
        # Store DUT UID for this test sequence (will be included in reports)
        # Explicitly ensure integer type
        self.current_dut_uid = int(dut_uid)
        
        # Disable DUT UID input during sequence execution to prevent changes
        self.dut_uid_input.setEnabled(False)
        self.dut_uid_input.setToolTip('DUT UID is locked during test sequence execution')
        
        # Create and configure TestExecutionThread
        runner = TestRunner(self)
        
        # Phase 3: Get services from container if available
        # Use getattr for defensive access in case service_container doesn't exist
        service_container = getattr(self, 'service_container', None)
        can_svc = service_container.get_can_service() if service_container else getattr(self, 'can_service', None)
        dbc_svc = service_container.get_dbc_service() if service_container else getattr(self, 'dbc_service', None)
        signal_svc = service_container.get_signal_service() if service_container else getattr(self, 'signal_service', None)
        
        self.test_execution_thread = self.TestExecutionThread(
            tests=list(self._tests),
            test_runner=runner,
            can_service=can_svc,
            dbc_service=dbc_svc,
            signal_service=signal_svc,
            timeout=1.0
        )
        
        # Connect signals
        self.test_execution_thread.test_started.connect(self._on_test_started)
        self.test_execution_thread.test_finished.connect(self._on_test_finished)
        self.test_execution_thread.test_failed.connect(self._on_test_failed)
        self.test_execution_thread.sequence_started.connect(self._on_sequence_started)
        self.test_execution_thread.sequence_progress.connect(self._on_sequence_progress)
        self.test_execution_thread.sequence_finished.connect(self._on_sequence_finished)
        self.test_execution_thread.sequence_cancelled.connect(self._on_sequence_cancelled)
        self.test_execution_thread.sequence_paused.connect(self._on_sequence_paused)
        self.test_execution_thread.sequence_resumed.connect(self._on_sequence_resumed)
        self.test_execution_thread.test_mode_mismatch.connect(self._on_test_mode_mismatch)
        
        # Initialize UI
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(self._tests))
        self.progress_bar.setValue(0)
        self.status_label.setText('Starting test sequence...')
        
        # Update run button to cancel button
        try:
            if hasattr(self, 'run_seq_btn'):
                self.run_seq_btn.setText('Cancel Sequence')
                self.run_seq_btn.clicked.disconnect()
                self.run_seq_btn.clicked.connect(self._on_cancel_sequence)
        except Exception:
            pass
        
        # Start thread
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.test_log.appendPlainText(f'[{timestamp}] Starting test sequence ({len(self._tests)} tests)')
        try:
            self.test_execution_thread.start()
            logger.info(f"Started test sequence thread with {len(self._tests)} tests")
        except Exception as e:
            logger.error(f"Failed to start test execution thread: {e}", exc_info=True)
            self.status_label.setText(f'Error starting tests: {e}')
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to start test sequence:\n{e}')
            # Clean up on failure
            try:
                self.run_seq_btn.setText('Run Sequence')
                self.run_seq_btn.clicked.disconnect()
                self.run_seq_btn.clicked.connect(self._on_run_sequence)
            except Exception:
                pass
    
    # Legacy _on_run_sequence_legacy method removed - TestExecutionThread should always be available
    
    def _on_cancel_sequence(self) -> None:
        """Cancel the currently running test sequence."""
        if self.test_execution_thread is not None and self.test_execution_thread.isRunning():
            logger.info("Cancelling test sequence")
            self.test_execution_thread.stop()
            self.status_label.setText('Cancelling test sequence...')
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.test_log.appendPlainText(f'[{timestamp}] Test sequence cancellation requested')
        else:
            logger.debug("No test sequence running to cancel")
    
    def _on_sequence_started(self, total_tests: int) -> None:
        """Handle sequence started signal from TestExecutionThread."""
        self.progress_bar.setRange(0, total_tests)
        self.progress_bar.setValue(0)
        self.status_label.setText(f'Running test sequence ({total_tests} tests)...')
        logger.debug(f"Sequence started: {total_tests} tests")
        
        # Enable pause button for all test sequences (including single test)
        self.pause_test_btn.setEnabled(True)
        self.resume_test_btn.setEnabled(False)
    
    def _on_sequence_progress(self, current: int, total: int) -> None:
        """Handle sequence progress signal from TestExecutionThread."""
        self.progress_bar.setValue(current)
        self.status_label.setText(f'Running test {current}/{total}...')
        
        # Keep pause button enabled for all tests (including last test)
        # User can pause even on the last test to review results before sequence ends
        self.pause_test_btn.setEnabled(True)
    
    def _on_test_started(self, test_index: int, test_name: str) -> None:
        """Handle test started signal from TestExecutionThread."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.test_log.appendPlainText(f'[{timestamp}] Running test: {test_name}')
        
        # Store current test index for plot detection
        self._current_test_index = test_index
        
        # Update Test Plan status to "Running..."
        try:
            if test_index < len(self._tests):
                t = self._tests[test_index]
                self._update_test_plan_row(t, 'Running...', 'N/A', 'Test execution in progress...')
                self._current_feedback = (t.get('feedback_message_id'), t.get('feedback_signal'))
                if self._current_feedback and self._current_feedback[1]:
                    ts, v = self.get_latest_signal(self._current_feedback[0], self._current_feedback[1])
                    if v is not None:
                        try:
                            self._update_signal_with_status('feedback_signal', v)
                        except Exception:
                            pass
        except Exception:
            self._current_feedback = None

    def _on_test_finished(self, test_index: int, success: bool, info: str, exec_time: float) -> None:
        """Handle test finished signal from TestExecutionThread."""
        result = 'PASS' if success else 'FAIL'
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.test_log.appendPlainText(f'[{timestamp}] Result: {result}\n{info}')
        
        # Update Test Plan row
        try:
            if test_index < len(self._tests):
                t = self._tests[test_index]
                # Retrieve plot data that was captured at the end of run_single_test
                # This data was stored before the next test could clear the plot arrays
                plot_data = None
                test_name = t.get('name', '<unnamed>')
                test_type = t.get('type', '')
                
                if test_type == 'Analog Sweep Test':
                    # First try to get from temporary storage (captured in run_single_test)
                    if hasattr(self, '_test_plot_data_temp') and test_name in self._test_plot_data_temp:
                        plot_data = self._test_plot_data_temp.pop(test_name)  # Remove after retrieval
                        logger.debug(f"Retrieved stored plot data for {test_name}")
                    # Fallback: try to read from global arrays (for backwards compatibility)
                    elif hasattr(self, 'plot_dac_voltages') and hasattr(self, 'plot_feedback_values'):
                        if self.plot_dac_voltages and self.plot_feedback_values:
                            plot_data = {
                                'dac_voltages': list(self.plot_dac_voltages),
                                'feedback_values': list(self.plot_feedback_values)
                            }
                            logger.debug(f"Used global plot data for {test_name} (fallback)")
                elif test_type == 'Phase Current Test':
                    # Retrieve plot data for phase current calibration tests
                    if hasattr(self, '_test_plot_data_temp') and test_name in self._test_plot_data_temp:
                        plot_data = self._test_plot_data_temp.pop(test_name)  # Remove after retrieval
                        logger.debug(f"Retrieved stored plot data for {test_name} (phase current test)")
                elif test_type == 'Output Current Calibration':
                    # Retrieve plot data for Output Current Calibration tests
                    if hasattr(self, '_test_plot_data_temp') and test_name in self._test_plot_data_temp:
                        plot_data = self._test_plot_data_temp.pop(test_name)  # Remove after retrieval
                        logger.debug(f"Retrieved stored plot data for {test_name} (Output Current Calibration test)")
                    # Also retrieve result data for statistics
                    # CRITICAL: Check if statistics already exist (they may have been set immediately in test_runner.py)
                    # Only update if they don't exist or are None/invalid
                    if not hasattr(self, '_test_execution_data'):
                        self._test_execution_data = {}
                    if test_name not in self._test_execution_data:
                        self._test_execution_data[test_name] = {}
                    
                    existing_stats = self._test_execution_data[test_name].get('statistics')
                    stats_already_valid = (existing_stats is not None and 
                                          isinstance(existing_stats, dict) and 
                                          existing_stats.get('adjustment_factor') is not None)
                    
                    if stats_already_valid:
                        logger.debug(f"_on_test_finished: Statistics already exist for '{test_name}' with adjustment_factor={existing_stats.get('adjustment_factor')}, preserving them")
                    elif hasattr(self, '_test_result_data_temp') and test_name in self._test_result_data_temp:
                        result_data = self._test_result_data_temp.pop(test_name)
                        logger.debug(f"_on_test_finished: Processing result_data for '{test_name}' from temp storage")
                        
                        # Store statistics - use second sweep values for pass/fail (as per test logic)
                        second_sweep_gain_error = result_data.get('second_sweep_gain_error')
                        tolerance_percent = result_data.get('tolerance_percent', 0)
                        # Pass/fail is based on second sweep gain error (from linear regression)
                        passed = False
                        if second_sweep_gain_error is not None and tolerance_percent is not None:
                            passed = abs(second_sweep_gain_error) <= tolerance_percent
                        
                        self._test_execution_data[test_name]['statistics'] = {
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
                            'passed': passed
                        }
                        logger.info(f"_on_test_finished: Stored statistics for '{test_name}' (adjustment_factor={result_data.get('adjustment_factor')}, passed={passed})")
                    else:
                        logger.warning(f"_on_test_finished: No result_data found in temp storage for '{test_name}' and no existing valid statistics. Statistics may be missing.")
                elif test_type == 'Analog Static Test':
                    # Retrieve result data for analog_static tests
                    if hasattr(self, '_test_result_data_temp') and test_name in self._test_result_data_temp:
                        result_data = self._test_result_data_temp.pop(test_name)
                        # Store statistics in exec_data for display
                        if not hasattr(self, '_test_execution_data'):
                            self._test_execution_data = {}
                        if test_name not in self._test_execution_data:
                            self._test_execution_data[test_name] = {}
                        self._test_execution_data[test_name]['statistics'] = {
                            'feedback_avg': result_data.get('feedback_avg'),
                            'eol_avg': result_data.get('eol_avg'),
                            'difference': result_data.get('difference'),
                            'tolerance': result_data.get('tolerance'),
                            'feedback_samples': result_data.get('feedback_samples'),
                            'eol_samples': result_data.get('eol_samples'),
                            'passed': result_data.get('difference', float('inf')) <= result_data.get('tolerance', 0)
                        }
                        # Store raw data for potential plotting
                        plot_data = {
                            'feedback_values': result_data.get('feedback_values', []),
                            'eol_values': result_data.get('eol_values', [])
                        }
                        logger.debug(f"Retrieved stored result data for {test_name} (analog static test)")
                    else:
                        plot_data = None
                elif test_type == 'Temperature Validation Test':
                    # Retrieve result data for temperature validation tests
                    if hasattr(self, '_test_result_data_temp') and test_name in self._test_result_data_temp:
                        result_data = self._test_result_data_temp.pop(test_name)
                        # Store statistics in exec_data for display
                        if not hasattr(self, '_test_execution_data'):
                            self._test_execution_data = {}
                        if test_name not in self._test_execution_data:
                            self._test_execution_data[test_name] = {}
                        self._test_execution_data[test_name]['statistics'] = {
                            'reference_temperature_c': result_data.get('reference_temperature_c'),
                            'measured_avg_c': result_data.get('measured_avg_c'),
                            'difference_c': result_data.get('difference_c'),
                            'tolerance_c': result_data.get('tolerance_c'),
                            'samples': result_data.get('samples'),
                            'passed': result_data.get('difference_c', float('inf')) <= result_data.get('tolerance_c', 0)
                        }
                        # Store raw data for potential plotting
                        plot_data = {
                            'temperature_values': result_data.get('temperature_values', [])
                        }
                        logger.debug(f"Retrieved stored result data for {test_name} (temperature validation test)")
                    else:
                        plot_data = None
                elif test_type == 'Fan Control Test':
                    # Retrieve result data for fan control tests
                    if hasattr(self, '_test_result_data_temp') and test_name in self._test_result_data_temp:
                        result_data = self._test_result_data_temp.pop(test_name)
                        # Store statistics in exec_data for display
                        if not hasattr(self, '_test_execution_data'):
                            self._test_execution_data = {}
                        if test_name not in self._test_execution_data:
                            self._test_execution_data[test_name] = {}
                        self._test_execution_data[test_name]['statistics'] = {
                            'fan_tach_latest': result_data.get('fan_tach_latest'),
                            'fan_fault_latest': result_data.get('fan_fault_latest'),
                            'fan_tach_samples': result_data.get('fan_tach_samples'),
                            'fan_fault_samples': result_data.get('fan_fault_samples'),
                            'passed': result_data.get('passed', False)
                        }
                        logger.debug(f"Retrieved stored result data for {test_name} (fan control test)")
                elif test_type == 'Charged HV Bus Test':
                    # Retrieve result data for Charged HV Bus Test
                    if hasattr(self, '_test_result_data_temp') and test_name in self._test_result_data_temp:
                        result_data = self._test_result_data_temp.pop(test_name)
                        # Store statistics in exec_data for display
                        if not hasattr(self, '_test_execution_data'):
                            self._test_execution_data = {}
                        if test_name not in self._test_execution_data:
                            self._test_execution_data[test_name] = {}
                        self._test_execution_data[test_name]['statistics'] = {
                            'pfc_regulation_success': result_data.get('pfc_regulation_success'),
                            'pcmc_success': result_data.get('pcmc_success'),
                            'fault_detected': result_data.get('fault_detected'),
                            'final_dut_state': result_data.get('final_dut_state'),
                            'trigger_value': result_data.get('trigger_value'),
                            'trim_value_used': result_data.get('trim_value_used'),
                            'total_data_points': len(result_data.get('logged_data', [])),
                            'passed': result_data.get('passed')
                        }
                        logger.debug(f"Retrieved stored result data for {test_name} (Charged HV Bus Test)")
                    else:
                        plot_data = None
                elif test_type == 'Charger Functional Test':
                    # Retrieve result data for Charger Functional Test
                    if hasattr(self, '_test_result_data_temp') and test_name in self._test_result_data_temp:
                        result_data = self._test_result_data_temp.pop(test_name)
                        # Store statistics in exec_data for display
                        if not hasattr(self, '_test_execution_data'):
                            self._test_execution_data = {}
                        if test_name not in self._test_execution_data:
                            self._test_execution_data[test_name] = {}
                        self._test_execution_data[test_name]['statistics'] = {
                            'pfc_regulation_success': result_data.get('pfc_regulation_success'),
                            'pcmc_success': result_data.get('pcmc_success'),
                            'current_regulation_success': result_data.get('current_regulation_success'),
                            'avg_output_current': result_data.get('avg_output_current'),
                            'output_current_error': result_data.get('output_current_error'),
                            'fault_detected': result_data.get('fault_detected'),
                            'final_dut_state': result_data.get('final_dut_state'),
                            'trigger_value': result_data.get('trigger_value'),
                            'trim_value_used': result_data.get('trim_value_used'),
                            'total_data_points': len(result_data.get('logged_data', [])),
                            'passed': result_data.get('passed')
                        }
                        logger.debug(f"Retrieved stored result data for {test_name} (Charger Functional Test)")
                    else:
                        plot_data = None
                
                self._update_test_plan_row(t, result, f"{exec_time:.2f}s", info, plot_data)
        except Exception:
            pass
        
        # Clear current feedback
        try:
            self._current_feedback = None
        except Exception:
            pass
    
    def _on_test_failed(self, test_index: int, error: str, exec_time: float) -> None:
        """Handle test failed signal from TestExecutionThread."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.test_log.appendPlainText(f'[{timestamp}] Error: {error}')
        
        # Update Test Plan row
        try:
            if test_index < len(self._tests):
                t = self._tests[test_index]
                # Retrieve plot data that was captured at the end of run_single_test (even if failed, may have partial data)
                plot_data = None
                test_name = t.get('name', '<unnamed>')
                test_type = t.get('type', '')
                
                if test_type == 'Analog Sweep Test':
                    # First try to get from temporary storage (captured in run_single_test)
                    if hasattr(self, '_test_plot_data_temp') and test_name in self._test_plot_data_temp:
                        plot_data = self._test_plot_data_temp.pop(test_name)  # Remove after retrieval
                        logger.debug(f"Retrieved stored plot data for {test_name} (error case)")
                    # Fallback: try to read from global arrays (for backwards compatibility)
                    elif hasattr(self, 'plot_dac_voltages') and hasattr(self, 'plot_feedback_values'):
                        if self.plot_dac_voltages and self.plot_feedback_values:
                            plot_data = {
                                'dac_voltages': list(self.plot_dac_voltages),
                                'feedback_values': list(self.plot_feedback_values)
                            }
                            logger.debug(f"Used global plot data for {test_name} (error case, fallback)")
                elif test_type == 'Phase Current Test':
                    # Retrieve plot data for phase current calibration tests
                    if hasattr(self, '_test_plot_data_temp') and test_name in self._test_plot_data_temp:
                        plot_data = self._test_plot_data_temp.pop(test_name)  # Remove after retrieval
                        logger.debug(f"Retrieved stored plot data for {test_name} (error case, phase current)")
                elif test_type == 'Output Current Calibration':
                    # Retrieve plot data for Output Current Calibration tests
                    if hasattr(self, '_test_plot_data_temp') and test_name in self._test_plot_data_temp:
                        plot_data = self._test_plot_data_temp.pop(test_name)  # Remove after retrieval
                        logger.debug(f"Retrieved stored plot data for {test_name} (error case, Output Current Calibration)")
                self._update_test_plan_row(t, 'ERROR', f"{exec_time:.2f}s", error, plot_data)
        except Exception:
            pass
        
        # Clear current feedback
        try:
            self._current_feedback = None
        except Exception:
            pass
    
    def _on_sequence_finished(self, results: list, summary: str) -> None:
        """Handle sequence finished signal from TestExecutionThread."""
        self.progress_bar.setVisible(False)
        
        # Parse results for UI update
        pass_count = sum(1 for _, success, _ in results if success)
        total = len(results)
        self.status_label.setText(f'Sequence completed: {pass_count}/{total} passed')
        
        # Log summary
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.test_log.appendPlainText(f'[{timestamp}] Sequence summary:\n{summary}')
        
        # Re-enable DUT UID input
        if hasattr(self, 'dut_uid_input'):
            self.dut_uid_input.setEnabled(True)
            self.dut_uid_input.setToolTip('Enter IPC UID number for the next test sequence')
        
        # Restore run button
        try:
            if hasattr(self, 'run_seq_btn'):
                self.run_seq_btn.setText('Run Sequence')
                self.run_seq_btn.clicked.disconnect()
                self.run_seq_btn.clicked.connect(self._on_run_sequence)
        except Exception:
            pass
        
        # Clean up thread
        if self.test_execution_thread is not None:
            self.test_execution_thread.wait(1000)  # Wait up to 1 second for thread to finish
            self.test_execution_thread = None
        
        # Disable pause/resume buttons
        self.pause_test_btn.setEnabled(False)
        self.resume_test_btn.setEnabled(False)
        
        logger.info(f"Test sequence finished: {pass_count}/{total} passed")
    
    def _on_sequence_cancelled(self) -> None:
        """Handle sequence cancelled signal from TestExecutionThread."""
        self.progress_bar.setVisible(False)
        self.status_label.setText('Test sequence cancelled')
        
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.test_log.appendPlainText(f'[{timestamp}] Test sequence was cancelled by user')
        
        # Re-enable DUT UID input
        if hasattr(self, 'dut_uid_input'):
            self.dut_uid_input.setEnabled(True)
            self.dut_uid_input.setToolTip('Enter IPC UID number for the next test sequence')
        
        # Restore run button
        try:
            if hasattr(self, 'run_seq_btn'):
                self.run_seq_btn.setText('Run Sequence')
                self.run_seq_btn.clicked.disconnect()
                self.run_seq_btn.clicked.connect(self._on_run_sequence)
        except Exception:
            pass
        
        # Clean up thread
        if self.test_execution_thread is not None:
            self.test_execution_thread.wait(1000)  # Wait up to 1 second for thread to finish
            self.test_execution_thread = None
        
        # Disable pause/resume buttons
        self.pause_test_btn.setEnabled(False)
        self.resume_test_btn.setEnabled(False)
        
        logger.info("Test sequence cancelled")
    
    def _on_pause_test(self) -> None:
        """Handle pause test button click.
        
        Requests the test sequence to pause after the current test completes.
        Works when a sequence is running (including single test sequences).
        """
        if self.test_execution_thread is not None and self.test_execution_thread.isRunning():
            self.test_execution_thread.pause()
            logger.info("Pause test requested")
        else:
            logger.debug("Pause ignored - no test sequence running")
    
    def _on_resume_test(self) -> None:
        """Handle resume test button click.
        
        Resumes the paused test sequence. Only works when sequence is paused.
        """
        if self.test_execution_thread is not None:
            if self.test_execution_thread.is_paused():
                self.test_execution_thread.resume()
                logger.info("Resume test requested")
            else:
                logger.debug("Resume ignored - test sequence not paused")
        else:
            logger.debug("Resume ignored - no test sequence running")
    
    def _on_sequence_paused(self) -> None:
        """Handle sequence paused signal from TestExecutionThread."""
        self.status_label.setText('Paused - waiting to resume...')
        self.pause_test_btn.setEnabled(False)
        self.resume_test_btn.setEnabled(True)
        
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.test_log.appendPlainText(f'[{timestamp}] Test sequence paused')
        logger.info("Test sequence paused")
    
    def _on_sequence_resumed(self) -> None:
        """Handle sequence resumed signal from TestExecutionThread."""
        # Get current test index to update status
        if self.test_execution_thread is not None:
            current = getattr(self.test_execution_thread, '_current_test_index', -1) + 1
            total = len(self._tests)
            if current > 0 and current <= total:
                self.status_label.setText(f'Running test {current}/{total}...')
            else:
                self.status_label.setText('Resuming test sequence...')
        
        self.pause_test_btn.setEnabled(True)
        self.resume_test_btn.setEnabled(False)
        
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.test_log.appendPlainText(f'[{timestamp}] Test sequence resumed')
        logger.info("Test sequence resumed")
    
    @QtCore.Slot(str, str)
    def _on_test_mode_mismatch(self, test_name: str, message: str) -> None:
        """Handle test mode mismatch signal from TestExecutionThread.
        
        Shows a warning dialog when DUT is not in the correct test mode.
        User can click OK to close the dialog, then press Resume to retry.
        
        Args:
            test_name: Name of the test that failed the mode check
            message: Error message describing the mismatch
        """
        logger.warning(f"Test mode mismatch for {test_name}: {message}")
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.test_log.appendPlainText(f'[{timestamp}] Test mode mismatch for {test_name}: {message}')
        QtWidgets.QMessageBox.warning(
            self,
            'Test Mode Mismatch',
            f'Test: {test_name}\n\n{message}\n\n'
            'Please ensure DUT is in the correct test mode and click Resume to retry.'
        )
    
    def closeEvent(self, event) -> None:
        """Handle window close event - cleanup services and resources.
        
        Phase 3: Cleanup service container and all registered services
        when the application is closed.
        
        Args:
            event: QCloseEvent from Qt
        """
        logger.info("BaseGUI closing, cleaning up resources...")
        
        # Stop test execution thread if running
        if self.test_execution_thread is not None and self.test_execution_thread.isRunning():
            logger.info("Stopping test execution thread...")
            self.test_execution_thread.stop()
            self.test_execution_thread.wait(2000)  # Wait up to 2 seconds
            self.test_execution_thread = None
        
        # Phase 3: Cleanup service container
        if self.service_container is not None:
            try:
                self.service_container.clear()
                logger.info("ServiceContainer cleaned up")
            except Exception as e:
                logger.warning(f"Error cleaning up ServiceContainer: {e}", exc_info=True)
        
        # Disconnect adapter if connected
        if self.can_service is not None:
            try:
                if hasattr(self.can_service, 'is_connected') and self.can_service.is_connected():
                    self.can_service.disconnect()
                    logger.info("CanService disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting CanService: {e}", exc_info=True)
        
        # Disconnect oscilloscope if connected
        if self.oscilloscope_service is not None:
            try:
                if self.oscilloscope_service.is_connected():
                    self.oscilloscope_service.disconnect()
                    logger.info("OscilloscopeService disconnected")
                self.oscilloscope_service.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up OscilloscopeService: {e}", exc_info=True)
        
        # Stop polling timer
        try:
            if hasattr(self, 'poll_timer') and self.poll_timer.isActive():
                self.poll_timer.stop()
        except Exception:
            pass
        
        # Phase 4: Save window geometry and configuration
        if self.config_manager:
            try:
                self.config_manager.save_window_geometry(self.saveGeometry())
            except Exception as e:
                logger.debug(f"Failed to save window geometry: {e}")
        
        logger.info("BaseGUI cleanup complete")
        event.accept()  # Accept the close event
    
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
        device_combo = getattr(self, 'device_combo', None)
        if device_combo is None:
            QtWidgets.QMessageBox.warning(self, 'Connection', 'Please open EOL -> Connect EOL to configure connection settings.')
            return
        try:
            selected = device_combo.currentText()
        except Exception:
            selected = getattr(self, 'adapter_combo', QtWidgets.QComboBox()).currentText()
        
        logger.info(f"toggle_adapter called (service); connected={self.can_service.is_connected()}; selected={selected}")
        
        if self.can_service.is_connected():
            # Disconnect
            self.can_service.disconnect()
            self.poll_timer.stop()
            if self.start_btn is not None:
                self.start_btn.setText('Connect')
            self.conn_indicator.setText('Adapter: stopped')
            logger.info('Adapter disconnected via service')
            return
        
        # Connect
        try:
            channel_combo = getattr(self, 'can_channel_combo', None)
            if channel_combo is not None:
                channel_value = channel_combo.currentText().strip()
                if channel_value:
                    self.can_service.channel = channel_value
            bitrate_combo = getattr(self, 'can_bitrate_combo', None)
            if bitrate_combo is not None:
                try:
                    bitrate_value = bitrate_combo.currentText().strip()
                    if bitrate_value:
                        self.can_service.bitrate = int(bitrate_value.split()[0])
                except Exception:
                    pass
            success = self.can_service.connect(selected)
            if not success:
                QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to connect to {selected}')
                return
        except (ValueError, RuntimeError) as e:
            logger.error(f"Adapter connection failed: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to connect: {e}')
            return
        
        # Adapter connected via service
        
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
                logger.debug('[host_gui] injecting deterministic test frame into frame_queue')
                if self.can_service is not None:
                    self.can_service.frame_queue.put(test_frame)
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
        # Use CanService (should always be available)
        if self.can_service is None:
            QtWidgets.QMessageBox.critical(self, 'Error', 'CanService not available - this should not happen')
            logger.error("CanService not available in toggle_adapter")
            return
        
        return self._toggle_adapter_with_service()


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
        into frame_queue. It processes frames in batches to prevent UI blocking
        while ensuring all frames are eventually processed.
        
        Rate limiting is applied to prevent processing too many frames in a single
        poll interval, which could cause UI freezing.
        """
        try:
            if self.can_service is None:
                return
            
            frames_processed = 0
            queue_size_before = self.can_service.frame_queue.qsize()
            # Limit frames processed per poll to prevent UI blocking
            # Higher limit for better throughput while maintaining responsiveness
            MAX_FRAMES_PER_POLL = 100
            
            # Process frames in batch, but limit to prevent UI freeze
            while not self.can_service.frame_queue.empty() and frames_processed < MAX_FRAMES_PER_POLL:
                try:
                    f = self.can_service.frame_queue.get_nowait()
                    self._add_frame_row(f)  # Process each frame - CRITICAL: must be inside loop
                    frames_processed += 1
                except Exception as frame_error:
                    logger.debug(f"Error processing frame in poll: {frame_error}")
                    # Continue with next frame even if one fails
                    continue
            
            # Log if we hit the rate limit (indicates high traffic)
            if frames_processed >= MAX_FRAMES_PER_POLL:
                remaining = self.can_service.frame_queue.qsize()
                if remaining > 0:
                    logger.debug(f"Frame rate limit reached: processed {frames_processed}, {remaining} remaining in queue")
            
            # Log queue size periodically for monitoring
            if queue_size_before > 50 or frames_processed > 10:
                logger.debug(f"Poll processed {frames_processed} frames (queue had {queue_size_before}, now {self.can_service.frame_queue.qsize()})")
                
        except Exception as e:
            logger.error(f"Error polling frames: {e}", exc_info=True)

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
            logger.error(f"Error decoding signals from frame: {e}", exc_info=True)

    def _decode_and_add_signals(self, frame):
        """Decode a received CAN frame using loaded DBC and append each signal to Signal View.
        
        This method decodes the frame's data bytes using the DBC database to extract
        individual signal values. Each decoded signal is added to the signal table
        and cached in _signal_values for quick lookup during test execution.
        
        Args:
            frame: CAN frame object with can_id and data attributes
        """
        # Phase 1: Use SignalService if available and DBC is loaded
        # Check if services exist (may not be initialized yet)
        signal_service = getattr(self, 'signal_service', None)
        dbc_service = getattr(self, 'dbc_service', None)
        
        if signal_service is not None and dbc_service is not None:
            # Check if DBC is loaded (either via service or legacy)
            dbc_loaded = False
            try:
                if hasattr(dbc_service, 'is_loaded'):
                    dbc_loaded = dbc_service.is_loaded()
            except Exception:
                pass
            
            # Also check legacy _dbc_db
            if not dbc_loaded:
                dbc_loaded = getattr(self, '_dbc_db', None) is not None
            
            if dbc_loaded:
                # Extract can_id early for use in error handling
                can_id = getattr(frame, 'can_id', 0)
                
                try:
                    # Convert frame to SignalService format
                    from backend.adapters.interface import Frame as AdapterFrame
                    if not isinstance(frame, AdapterFrame):
                        # Convert from legacy format
                        adapter_frame = AdapterFrame(
                            can_id=can_id,
                            data=getattr(frame, 'data', b''),
                            timestamp=getattr(frame, 'timestamp', None)
                        )
                    else:
                        adapter_frame = frame
                    
                    # Decode signals
                    try:
                        signal_values = signal_service.decode_frame(adapter_frame)
                    except Exception as e:
                        # Handle decode errors gracefully (log and continue without decoded signals)
                        if SignalDecodeError and isinstance(e, SignalDecodeError):
                            logger.warning(f"Signal decode error for frame 0x{can_id:X}: {e}")
                        else:
                            logger.warning(f"Error during signal decode for frame 0x{can_id:X}: {e}")
                        signal_values = []  # Continue without decoded signals
                    
                    # Only proceed if we got signal values
                    if signal_values:
                        # Update UI table (legacy table handling)
                        for sig_val in signal_values:
                            key = sig_val.key
                            fid = sig_val.message_id
                            sig_name = sig_val.signal_name
                            val = sig_val.value  # SignalService already applies gain factors (e.g., ADC_A3_GAIN_FACTOR)
                            ts = sig_val.timestamp or time.time()
                            
                            if key in self._signal_rows:
                                row = self._signal_rows[key]
                                try:
                                    self.signal_table.setItem(row, 0, QtWidgets.QTableWidgetItem(datetime.fromtimestamp(ts).isoformat()))
                                except Exception:
                                    self.signal_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(ts)))
                                self.signal_table.setItem(row, 4, QtWidgets.QTableWidgetItem(str(val)))
                                # Signal values stored in signal_service (legacy cache removed)
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
                                # Signal values stored in signal_service
                            
                            # Update feedback label if this is the current monitored signal
                            try:
                                cur = getattr(self, '_current_feedback', None)
                                if cur and cur[1] and str(cur[1]) == str(sig_name):
                                    try:
                                        cur_id = int(cur[0]) if cur[0] is not None else None
                                        this_id = int(fid)
                                        if cur_id is not None and this_id is not None and cur_id == this_id:
                                            try:
                                                # Use the gain-adjusted value for feedback label
                                                self._update_signal_with_status('feedback_signal', val)
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        return  # Successfully decoded via service
                except Exception as e:
                    logger.debug(f"SignalService decode failed: {e}", exc_info=True)
        
        # Legacy implementation removed - SignalService should handle all decoding
        # If we reach here, SignalService decode failed and we can't decode
        logger.debug("No signal decoding possible - SignalService failed and legacy removed")

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
        # Use SignalService if available
        # Note: SignalService now handles signal processing (e.g., ADC_A3_GAIN_FACTOR) internally
        if self.signal_service is not None:
            ts, val = self.signal_service.get_latest_signal(can_id, signal_name)
            return (ts, val)
        
        # No fallback - signal_service should always be available
        # If signal_service is None, it means services weren't initialized properly
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


