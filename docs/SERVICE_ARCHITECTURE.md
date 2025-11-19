# Service Architecture

## Overview

The EOL Host Application uses a service-based architecture that separates business logic from the GUI layer. This design improves testability, reusability, and maintainability by decoupling components and enabling dependency injection.

## Architecture Principles

1. **Separation of Concerns**: Business logic is separated from UI code
2. **Dependency Injection**: Services are injected rather than tightly coupled
3. **Single Responsibility**: Each service has a focused, well-defined purpose
4. **Testability**: Services can be tested independently without GUI dependencies
5. **Reusability**: Services can be used in GUI, headless execution, or automated testing

## Service Layer Components

### Core Services

#### CanService (`host_gui/services/can_service.py`)

**Purpose**: Manages CAN bus adapters and frame transmission/reception.

**Responsibilities**:
- Connecting/disconnecting CAN adapters (SimAdapter, PCAN, PythonCAN, SocketCAN, Canalystii)
- Sending CAN frames
- Receiving frames via background worker thread (`AdapterWorker`)
- Managing adapter-specific configuration (channel, bitrate)
- Handling connection retries and error recovery

**Key Methods**:
- `connect(adapter_type, max_retries=3, retry_delay=0.5) -> bool`: Connect to adapter
- `disconnect() -> None`: Disconnect adapter and stop worker thread
- `send_frame(frame: Frame) -> bool`: Send a CAN frame
- `is_connected() -> bool`: Check connection status
- `get_available_adapters() -> List[str]`: List available adapter types

**Dependencies**: 
- Backend adapters (`backend.adapters.*`)
- `AdapterWorker` thread for frame reception

**Usage Example**:
```python
from host_gui.services.can_service import CanService

can_service = CanService(channel='0', bitrate=500)
if can_service.connect('PCAN'):
    frame = Frame(can_id=0x100, data=b'\x01\x02\x03\x04')
    can_service.send_frame(frame)
```

---

#### DbcService (`host_gui/services/dbc_service.py`)

**Purpose**: Manages DBC (Database CAN) files and message/signal operations.

**Responsibilities**:
- Loading and parsing DBC files using cantools
- Finding messages by CAN ID
- Finding signals within messages
- Encoding/decoding messages and signals
- Managing DBC file index/persistence
- Caching message and signal lookups

**Key Methods**:
- `load_dbc_file(filepath: str) -> bool`: Load a DBC file
- `is_loaded() -> bool`: Check if DBC is loaded
- `find_message_by_id(can_id: int) -> Optional[Message]`: Find message by CAN ID
- `find_signal_by_name(message, signal_name: str) -> Optional[Signal]`: Find signal in message
- `encode_message(message, signal_values: Dict) -> bytes`: Encode message with signal values
- `decode_message(message, data: bytes) -> Dict[str, Any]`: Decode message data

**Dependencies**:
- `cantools` library for DBC parsing
- File system for DBC file storage

**Usage Example**:
```python
from host_gui.services.dbc_service import DbcService

dbc_service = DbcService()
if dbc_service.load_dbc_file('/path/to/file.dbc'):
    message = dbc_service.find_message_by_id(0x100)
    signal_values = {'Signal1': 10.5, 'Signal2': 20}
    frame_data = dbc_service.encode_message(message, signal_values)
```

---

#### SignalService (`host_gui/services/signal_service.py`)

**Purpose**: Decodes CAN signals and manages signal value cache.

**Responsibilities**:
- Decoding frames into signal values using DBC
- Caching latest signal values for quick lookup
- Retrieving latest signal values by message ID and signal name
- Handling signal value formatting (numeric vs string)
- Managing signal value timestamps

**Key Methods**:
- `decode_frame(frame: Frame) -> List[SignalValue]`: Decode frame into signals
- `get_latest_signal(can_id: int, signal_name: str) -> Tuple[Optional[float], Optional[float]]`: Get latest signal value and timestamp
- `clear_cache() -> None`: Clear signal value cache
- `get_all_signals() -> Dict[str, Tuple[float, Any]]`: Get all cached signals

**Dependencies**:
- `DbcService` for DBC operations
- `SignalValue` model for signal representation

**Usage Example**:
```python
from host_gui.services.signal_service import SignalService

signal_service = SignalService(dbc_service)
signal_values = signal_service.decode_frame(frame)
timestamp, value = signal_service.get_latest_signal(0x100, 'Temperature')
```

---

#### OscilloscopeService (`host_gui/services/oscilloscope_service.py`)

**Purpose**: Manages oscilloscope connections via USBTMC.

**Responsibilities**:
- Scanning for available USBTMC oscilloscopes
- Connecting/disconnecting oscilloscopes
- Managing oscilloscope-specific configuration (channels, timebase, probe attenuation)
- Sending SCPI commands and queries
- Retrieving waveform data
- Parsing oscilloscope responses (PAVA, VDIV, OFST, etc.)

**Key Methods**:
- `scan_for_devices() -> List[str]`: Scan for available USBTMC devices
- `connect(resource: str) -> bool`: Connect to oscilloscope
- `disconnect() -> None`: Disconnect from oscilloscope
- `send_command(command: str) -> Optional[str]`: Send SCPI command
- `configure_channel(channel: int, enabled: bool, probe_attenuation: float, unit: str) -> bool`: Configure channel
- `apply_configuration(config: Dict) -> Tuple[bool, List[str]]`: Apply full configuration
- `query_pava_mean(channel: int, retries: int = 3) -> Optional[float]`: Query PAVA MEAN value
- `get_channel_names(config: Dict) -> List[str]`: Get enabled channel names

**Dependencies**:
- `pyvisa` library for USBTMC communication
- Optional: `pyusb` for USB device detection

**Supported Oscilloscopes**:
- Siglent SDS1104X-U (primary)
- Other USBTMC-compatible oscilloscopes

**Usage Example**:
```python
from host_gui.services.oscilloscope_service import OscilloscopeService

osc_service = OscilloscopeService()
devices = osc_service.scan_for_devices()
if devices and osc_service.connect(devices[0]):
    mean_value = osc_service.query_pava_mean(channel=1)
    osc_service.disconnect()
```

---

### Specialized Services

#### PhaseCurrentService (`host_gui/services/phase_current_service.py`)

**Purpose**: State machine for Phase Current Calibration testing.

**Responsibilities**:
- Executing phase current calibration test sequence
- Managing oscilloscope and CAN data collection
- Coordinating test phases (validation, sweep, analysis)
- Generating test results and gain error calculations
- Live plot updates for Phase V and Phase W currents

**Key Class**: `PhaseCurrentTestStateMachine`

**Dependencies**:
- `OscilloscopeService` for oscilloscope operations
- `CanService` for CAN communication
- `DbcService` for message encoding
- `SignalService` for signal decoding
- `WaveformDecoder` utility for waveform analysis

**Usage**: Typically instantiated by `TestRunner` or `TestExecutionService` for Phase Current Test execution.

---

#### TestExecutionService (`host_gui/services/test_execution_service.py`)

**Purpose**: Decoupled test execution without GUI dependencies.

**Responsibilities**:
- Executing tests without requiring GUI components
- Supporting headless/automated test execution
- Using dependency injection for services
- Providing callbacks for UI updates (plot, label updates)
- Handling all test types (digital, analog, phase current, etc.)

**Key Methods**:
- `run_single_test(test: Dict, timeout: float = 1.0) -> Tuple[bool, str]`: Execute a single test
- `_run_digital_test(test, timeout) -> Tuple[bool, str]`: Execute digital test
- `_run_analog_test(test, timeout) -> Tuple[bool, str]`: Execute analog test
- `_run_phase_current_test(test, timeout) -> Tuple[bool, str]`: Execute phase current test

**Dependencies**:
- `CanService`, `DbcService`, `SignalService`, `OscilloscopeService`
- Callbacks for UI updates (optional)

**Usage**: Used by `TestExecutionThread` for background test execution, or directly for headless execution.

---

#### TestExecutionThread (`host_gui/services/test_execution_thread.py`)

**Purpose**: Background thread for async test execution.

**Responsibilities**:
- Executing test sequences in background thread (non-blocking UI)
- Emitting Qt signals for progress and results
- Supporting pause/resume functionality
- Supporting cancellation
- Managing test sequence lifecycle

**Key Signals**:
- `test_started(int, str)`: Test index and name
- `test_finished(int, bool, str, float)`: Test index, success, info, execution time
- `test_failed(int, str, float)`: Test index, error, execution time
- `sequence_started(int)`: Total number of tests
- `sequence_progress(int, int)`: Current and total tests
- `sequence_finished(list, str)`: Results and summary
- `sequence_cancelled()`: Cancellation signal
- `sequence_paused()`: Pause signal
- `sequence_resumed()`: Resume signal

**Dependencies**:
- `TestRunner` for test execution
- Services (CanService, DbcService, SignalService) passed to TestRunner

**Usage**: Instantiated by `BaseGUI` for async test execution. Connected to GUI via Qt signals.

---

### Service Container

#### ServiceContainer (`host_gui/services/service_container.py`)

**Purpose**: Dependency injection container for managing service instances.

**Responsibilities**:
- Centralized service instance management
- Lazy initialization of services
- Service lifecycle management
- Providing single source of truth for services

**Key Methods**:
- `register(name: str, service: Any, lazy: bool = False) -> None`: Register a service
- `get(name: str) -> Optional[Any]`: Get a service by name
- `initialize_services(config: Dict) -> None`: Initialize core services with config
- `get_can_service() -> Optional[CanService]`: Get CanService
- `get_dbc_service() -> Optional[DbcService]`: Get DbcService
- `get_signal_service() -> Optional[SignalService]`: Get SignalService
- `clear() -> None`: Clear all services

**Usage Example**:
```python
from host_gui.services.service_container import ServiceContainer

container = ServiceContainer()
container.initialize_services({
    'can_channel': '0',
    'can_bitrate': 500
})

can_service = container.get_can_service()
dbc_service = container.get_dbc_service()
```

---

## Service Dependencies

```
┌─────────────────┐
│   BaseGUI       │
│   (GUI Layer)   │
└────────┬────────┘
         │
         ├─────────────────┐
         │                 │
         ▼                 ▼
┌─────────────────┐  ┌──────────────────┐
│ ServiceContainer│  │ Direct Service    │
│  (Optional DI)   │  │  Access           │
└────────┬────────┘  └─────────┬─────────┘
         │                     │
         │                     │
    ┌────┴────┬────────────────┴─────┬──────────────┐
    │         │                      │              │
    ▼         ▼                      ▼              ▼
┌─────────┐ ┌─────────┐      ┌──────────────┐ ┌──────────────┐
│CanService│ │DbcService│      │SignalService │ │Oscilloscope  │
│         │ │         │      │             │ │Service       │
└────┬────┘ └────┬────┘      └──────┬──────┘ └──────────────┘
     │          │                   │
     │          └───────────┬───────┘
     │                      │
     │                      ▼
     │              ┌─────────────────┐
     │              │ SignalService   │
     │              │ (depends on    │
     │              │  DbcService)    │
     └──────────────┼─────────────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │  TestRunner         │
         │  TestExecutionService│
         │  TestExecutionThread│
         └──────────────────────┘
```

## Service Initialization

### In BaseGUI

Services are typically initialized in `BaseGUI.__init__()`:

```python
# Initialize services
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

### Service Lifecycle

1. **Initialization**: Services are created during GUI startup
2. **Configuration**: Services are configured based on user settings or config files
3. **Connection**: Services connect to hardware (CAN adapters, oscilloscopes) when needed
4. **Operation**: Services are used throughout application lifetime
5. **Cleanup**: Services disconnect and clean up resources on shutdown

## Best Practices

1. **Use Services, Not Direct Adapters**: Always use services rather than accessing adapters directly
2. **Dependency Injection**: Prefer passing services as parameters rather than accessing global instances
3. **Error Handling**: Services raise custom exceptions (`CanAdapterError`, `DbcError`, `SignalDecodeError`) for better error handling
4. **Thread Safety**: Services handle thread safety internally (e.g., `AdapterWorker` for CAN frames)
5. **Resource Management**: Always disconnect services and clean up resources when done
6. **Service Container**: Use `ServiceContainer` for dependency injection in new code
7. **Testing**: Services can be tested independently without GUI dependencies

## Migration from Legacy Code

The codebase has been refactored to use services. Legacy code may still access:
- `self.sim` (deprecated) → Use `self.can_service` instead
- `self.worker` (deprecated) → Managed by `CanService`
- `self._dbc_db` (deprecated) → Use `self.dbc_service` instead
- `self._signal_values` (deprecated) → Use `self.signal_service` instead

## Related Documentation

- [Configuration Management](CONFIGURATION.md) - Service configuration
- [Async Test Execution](ASYNC_TEST_EXECUTION.md) - TestExecutionThread usage
- [Oscilloscope Integration](OSCILLOSCOPE_INTEGRATION.md) - OscilloscopeService details
- [Exception Handling](EXCEPTION_HANDLING.md) - Service exception types

