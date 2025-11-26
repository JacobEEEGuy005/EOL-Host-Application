# Host GUI - EOL Host Application

PySide6-based GUI application for End of Line (EOL) testing of Integrated Power Converters.

## Overview

The Host GUI provides a comprehensive interface for:
- Connecting to CAN bus adapters (PCAN, SocketCAN, PythonCAN, Canalystii, SimAdapter)
- Loading and managing DBC (Database CAN) files for signal decoding
- Configuring and executing test sequences (12 test types)
- Real-time monitoring of CAN frames and decoded signals
- **Dynamic Real-Time Monitoring**: Test-specific signal display that adapts to each test type
- Visualizing test results with live plots
- Managing oscilloscope connections for advanced tests

## Architecture

The GUI uses a **service-based architecture** that separates business logic from the UI layer:

### Service Layer (`host_gui/services/`)

The application has been refactored to use a service layer for better modularity and testability:

- **CanService** (`can_service.py`): CAN adapter management and frame transmission
  - Manages adapter connections (SimAdapter, PCAN, PythonCAN, SocketCAN, Canalystii)
  - Handles frame sending and receiving via background worker thread (`AdapterWorker`)
  - Provides connection retry logic and error handling

- **DbcService** (`dbc_service.py`): DBC file loading, parsing, and message/signal operations
  - Loads and parses DBC files using cantools
  - Finds messages by CAN ID and signals by name
  - Encodes/decodes messages and signals
  - Manages DBC file index and persistence

- **SignalService** (`signal_service.py`): Signal decoding, caching, and value retrieval
  - Decodes CAN frames into signal values using DBC
  - Caches latest signal values for quick lookup
  - Provides signal value retrieval by message ID and signal name

- **OscilloscopeService** (`oscilloscope_service.py`): Oscilloscope connection and configuration via USB (USBTMC) and LAN (TCPIP)
  - Scans for available oscilloscopes (LAN preferred, USB fallback)
  - Connects/disconnects oscilloscopes via USB or LAN
  - Configures channels, timebase, probe attenuation
  - Sends SCPI commands and queries
  - Retrieves waveform data

- **PhaseCurrentService** (`phase_current_service.py`): Phase Current Calibration test state machine
  - Executes phase current calibration test sequence
  - Coordinates oscilloscope and CAN data collection
  - Manages test phases and generates results

- **TestExecutionService** (`test_execution_service.py`): Decoupled test execution (no GUI dependencies)
  - Executes tests without requiring GUI components
  - Supports headless/automated test execution
  - Uses dependency injection for services

- **TestExecutionThread** (`test_execution_thread.py`): Background thread for async test execution
  - Executes test sequences in background thread (non-blocking UI)
  - Emits Qt signals for progress and results
  - Supports pause/resume and cancellation

- **ServiceContainer** (`service_container.py`): Dependency injection container
  - Centralized service instance management
  - Lazy initialization of services
  - Service lifecycle management

### Module Structure

```
host_gui/
├── main.py                    # Application entry point
├── base_gui.py                # Main GUI window (BaseGUI class)
├── test_runner.py             # Test execution logic (TestRunner class)
├── config.py                  # Configuration management (ConfigManager)
├── exceptions.py              # Custom exception classes
├── constants.py               # Application constants
├── services/                  # Service layer
│   ├── __init__.py
│   ├── can_service.py         # CAN adapter management
│   ├── dbc_service.py         # DBC file operations
│   ├── signal_service.py      # Signal decoding and caching
│   ├── oscilloscope_service.py # Oscilloscope management
│   ├── phase_current_service.py # Phase current test state machine
│   ├── test_execution_service.py # Decoupled test execution
│   ├── test_execution_thread.py  # Async test execution thread
│   └── service_container.py      # Dependency injection container
├── models/                    # Data models
│   ├── test_profile.py        # Test configuration data structures
│   ├── can_frame.py           # CAN frame model
│   └── signal_value.py        # Signal value model
├── utils/                     # Utility functions
│   ├── signal_analysis.py     # Signal analysis utilities
│   ├── signal_processing.py   # Signal processing (filtering, etc.)
│   └── waveform_decoder.py    # Oscilloscope waveform decoding
└── widgets/                   # UI widgets (placeholder for future extraction)
    └── __init__.py
```

### Key Classes

- **BaseGUI** (`base_gui.py`): Main application window
  - Manages all GUI tabs (Home, CAN Data View, Test Configurator, Test Status)
  - Initializes and manages services
  - Handles user interactions and test execution
  - Provides real-time data visualization

- **TestRunner** (`test_runner.py`): Test execution engine
  - Executes individual test cases
  - Supports all 12 test types
  - Can work with services directly (decoupled mode) or via GUI (legacy mode)

- **ConfigManager** (`config.py`): Configuration management
  - Loads configuration from JSON files, environment variables, or defaults
  - Manages CAN settings, UI settings, and app settings
  - Handles user preferences via Qt QSettings

## Running the Application

### Basic Usage

```bash
cd host_gui
python main.py
```

### Headless Mode (Testing)

Test GUI startup without displaying window:

```bash
python main.py --headless-test
```

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python main.py
```

## Service Initialization

Services are initialized in `BaseGUI.__init__()`:

```python
# Initialize core services
self.can_service = CanService(channel=channel, bitrate=bitrate)
self.dbc_service = DbcService()
self.signal_service = SignalService(self.dbc_service)
self.oscilloscope_service = OscilloscopeService()

# Optional: Use ServiceContainer for dependency injection
self.service_container = ServiceContainer()
self.service_container.initialize_services({
    'can_channel': channel,
    'can_bitrate': bitrate
})
```

## Migration from Legacy Code

The codebase has been refactored to use services. Legacy code may still reference:

- `self.sim` (deprecated) → Use `self.can_service` instead
- `self.worker` (deprecated) → Managed by `CanService`
- `self._dbc_db` (deprecated) → Use `self.dbc_service` instead
- `self._signal_values` (deprecated) → Use `self.signal_service` instead

## Async Test Execution

The application uses `TestExecutionThread` for non-blocking test execution:

- Tests run in background thread
- GUI remains responsive during test execution
- Progress updates via Qt signals
- Supports pause/resume and cancellation

See [Async Test Execution](../docs/ASYNC_TEST_EXECUTION.md) for details.

## Configuration

Configuration is managed via `ConfigManager`:

- JSON config files (`~/.eol_host/config.json` or `backend/parameters.json`)
- Environment variables (backwards compatibility)
- Default values

See [Configuration Management](../docs/CONFIGURATION.md) for details.

## Error Handling

The application uses custom exception classes:

- `CanAdapterError`: CAN adapter failures
- `DbcError`: DBC file operations
- `SignalDecodeError`: Signal decoding failures
- `TestExecutionError`: Test execution failures
- `ConfigurationError`: Invalid configuration

See [Exception Handling](../docs/EXCEPTION_HANDLING.md) for details.

## Documentation

- [Service Architecture](../docs/SERVICE_ARCHITECTURE.md) - Detailed service layer documentation
- [Configuration Management](../docs/CONFIGURATION.md) - Configuration system
- [Async Test Execution](../docs/ASYNC_TEST_EXECUTION.md) - Background test execution
- [Oscilloscope Integration](../docs/OSCILLOSCOPE_INTEGRATION.md) - Oscilloscope support
- [Exception Handling](../docs/EXCEPTION_HANDLING.md) - Error handling
- [Test Type System Overview](../docs/TEST_TYPE_SYSTEM_OVERVIEW.md) - Test type architecture
- [Adding New Test Types](../docs/ADDING_NEW_TEST_TYPES.md) - Guide for adding test types
- [Real-Time Monitoring](../docs/REAL_TIME_MONITORING.md) - Dynamic test-specific monitoring system

## Testing

Run GUI tests:

```bash
pytest host_gui/tests/
```

## Development Notes

- Services are designed to be testable without GUI dependencies
- Use dependency injection via `ServiceContainer` for new code
- Prefer services over direct adapter access
- Handle exceptions using custom exception classes
- Services handle thread safety internally
