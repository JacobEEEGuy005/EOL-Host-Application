# EOL-Host-Application

Cross Platform Host GUI for End of Line Testing of Integrated Power Converter (IPC).

## Overview

The EOL Host Application is a comprehensive testing framework for End of Line (EOL) testing of Integrated Power Converters. It provides a PySide6-based GUI interface for configuring and executing test sequences, monitoring CAN bus communication, and analyzing test results.

## Features

- **CAN Bus Integration**: Support for multiple CAN adapters (PCAN, SocketCAN, PythonCAN, Canalystii, SimAdapter)
- **DBC File Management**: Load and manage DBC (Database CAN) files for signal decoding
- **Test Configuration**: Create and manage test profiles with visual configuration interface
- **Test Execution**: Execute test sequences with real-time monitoring and progress tracking
- **Dynamic Real-Time Monitoring**: Test-specific signal display that automatically adapts to show relevant signals for each test type
- **Oscilloscope Integration**: Support for USBTMC oscilloscopes (Siglent SDS1104X-U and compatible)
- **Live Data Visualization**: Real-time CAN frame monitoring and signal visualization
- **Test Results**: Comprehensive test reports with pass/fail status and detailed information
- **Report Export**: Export test reports to HTML and PDF formats with embedded plots and calibration data
- **Async Execution**: Non-blocking test execution with pause/resume capabilities

## Architecture

The application uses a **service-based architecture** that separates business logic from the GUI layer:

### Service Layer

- **CanService**: CAN adapter management and frame transmission
- **DbcService**: DBC file loading, parsing, and message/signal operations
- **SignalService**: Signal decoding, caching, and value retrieval
- **OscilloscopeService**: Oscilloscope connection and configuration via USBTMC
- **TestExecutionService**: Decoupled test execution (headless support)
- **TestExecutionThread**: Async test execution in background thread
- **ServiceContainer**: Dependency injection container for service management

### Module Structure

```
EOL-Host-Application/
├── host_gui/              # GUI application
│   ├── main.py            # Application entry point
│   ├── base_gui.py        # Main GUI window
│   ├── test_runner.py     # Test execution logic
│   ├── config.py          # Configuration management
│   ├── exceptions.py      # Custom exception classes
│   ├── constants.py       # Application constants
│   ├── services/          # Service layer
│   │   ├── can_service.py
│   │   ├── dbc_service.py
│   │   ├── signal_service.py
│   │   ├── oscilloscope_service.py
│   │   ├── phase_current_service.py
│   │   ├── test_execution_service.py
│   │   ├── test_execution_thread.py
│   │   └── service_container.py
│   ├── models/            # Data models
│   ├── utils/             # Utility functions
│   └── widgets/           # UI widgets
├── backend/               # Backend services
│   ├── adapters/          # CAN adapter implementations
│   ├── data/              # Data files (DBCs, configs, tests)
│   └── tests/             # Backend tests
├── docs/                  # Documentation
└── scripts/               # Utility scripts
```

For detailed architecture documentation, see [Service Architecture](docs/SERVICE_ARCHITECTURE.md).

## Test Types

The application supports 12 test types:

1. **Digital Logic Test** - Tests digital relay states (LOW→HIGH→LOW sequence)
2. **Analog Sweep Test** - Sweeps DAC voltages and monitors feedback signals
3. **Phase Current Test** - Phase current calibration with oscilloscope integration
4. **Analog Static Test** - Static analog measurement comparison
5. **Analog PWM Sensor** - PWM sensor frequency and duty cycle validation
6. **Temperature Validation Test** - Temperature measurement validation
7. **Fan Control Test** - Fan control system testing
8. **External 5V Test** - External 5V power supply testing
9. **DC Bus Sensing** - DC bus voltage sensing with oscilloscope
10. **Output Current Calibration** - Output current sensor calibration with oscilloscope
11. **Charged HV Bus Test** - Charged high voltage bus testing
12. **Charger Functional Test** - Charger functional testing with current validation

For detailed test type documentation, see:
- [Test Type System Overview](docs/TEST_TYPE_SYSTEM_OVERVIEW.md)
- [Adding New Test Types](docs/ADDING_NEW_TEST_TYPES.md)
- [Test Type Quick Reference](docs/TEST_TYPE_QUICK_REFERENCE.md)

## Installation

### Prerequisites

- Python 3.8 or higher
- PySide6 (Qt for Python)
- cantools (for DBC file parsing)
- Optional: PyVISA (for oscilloscope support)
- Optional: python-can (for PythonCAN adapter)
- Optional: PCAN drivers (for PCAN adapter)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd EOL-Host-Application
```

2. Create a virtual environment (recommended):
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
cd host_gui
python main.py
```

## Configuration

The application supports multiple configuration sources (in priority order):

1. JSON config file (`~/.eol_host/config.json` or `backend/parameters.json`)
2. Environment variables (backwards compatibility)
3. Default values

For detailed configuration documentation, see [Configuration Management](docs/CONFIGURATION.md).

## Usage

### Starting the Application

```bash
cd host_gui
python main.py
```

### Basic Workflow

1. **Connect CAN Adapter**: Select adapter type and connect
2. **Load DBC File**: Load a DBC file for signal decoding (optional)
3. **Configure Tests**: Create and configure test profiles in Test Configurator tab
4. **Execute Tests**: Run test sequences in Test Status tab
5. **View Results**: Review test results and reports

### Headless Mode

The application supports headless startup testing:

```bash
python main.py --headless-test
```

## Documentation

- [Service Architecture](docs/SERVICE_ARCHITECTURE.md) - Service layer architecture
- [Configuration Management](docs/CONFIGURATION.md) - Configuration system
- [Async Test Execution](docs/ASYNC_TEST_EXECUTION.md) - Background test execution
- [Oscilloscope Integration](docs/OSCILLOSCOPE_INTEGRATION.md) - Oscilloscope support
- [Exception Handling](docs/EXCEPTION_HANDLING.md) - Error handling
- [Test Type System Overview](docs/TEST_TYPE_SYSTEM_OVERVIEW.md) - Test type architecture
- [Adding New Test Types](docs/ADDING_NEW_TEST_TYPES.md) - Guide for adding test types
- [Test Type Quick Reference](docs/TEST_TYPE_QUICK_REFERENCE.md) - Quick reference guide
- [Real-Time Monitoring](docs/REAL_TIME_MONITORING.md) - Dynamic test-specific monitoring system

## Development

### Project Structure

- `host_gui/` - Main GUI application
- `backend/` - Backend services and adapters
- `docs/` - Documentation
- `scripts/` - Utility scripts

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

### Testing

Run tests:
```bash
# Backend tests
pytest backend/tests/

# GUI tests
pytest host_gui/tests/
```

## License

[Add license information here]

## Support

[Add support information here]
