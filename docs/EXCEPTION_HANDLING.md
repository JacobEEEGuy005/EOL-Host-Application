# Exception Handling

## Overview

The EOL Host Application uses a custom exception hierarchy to provide better error handling and more meaningful error messages. All custom exceptions inherit from `EolHostException`, allowing for both specific and general exception handling.

## Exception Hierarchy

```
EolHostException (base class)
├── CanAdapterError
├── DbcError
├── TestExecutionError
├── ConfigurationError
└── SignalDecodeError
```

## Exception Classes

### EolHostException

Base exception for all EOL Host application errors.

**Usage**: Catch all application-specific errors:

```python
try:
    # Application code
except EolHostException as e:
    # Handle any application error
    logger.error(f"Application error: {e}")
```

### CanAdapterError

Exception raised for CAN adapter connection or operation failures.

**Attributes**:
- `adapter_type` (str, optional): Type of adapter that failed (e.g., 'PCAN', 'SimAdapter')
- `operation` (str, optional): Operation that failed (e.g., 'connect', 'send_frame')
- `original_error` (Exception, optional): The underlying exception that caused this error

**Usage**:

```python
from host_gui.exceptions import CanAdapterError

try:
    can_service.connect('PCAN')
except CanAdapterError as e:
    logger.error(f"CAN adapter error: {e}")
    logger.error(f"Adapter: {e.adapter_type}, Operation: {e.operation}")
    if e.original_error:
        logger.error(f"Original error: {e.original_error}")
```

**When to Use**:
- CAN adapter connection failures
- Frame transmission failures
- Adapter initialization errors

**Example**:

```python
from host_gui.exceptions import CanAdapterError

def connect_adapter(adapter_type: str):
    try:
        if adapter_type == 'PCAN':
            adapter = PcanAdapter(channel='0', bitrate=500)
            adapter.connect()
        else:
            raise ValueError(f"Unsupported adapter type: {adapter_type}")
    except Exception as e:
        raise CanAdapterError(
            f"Failed to connect to {adapter_type} adapter: {e}",
            adapter_type=adapter_type,
            operation='connect',
            original_error=e
        )
```

### DbcError

Exception raised for DBC file loading or parsing failures.

**Attributes**:
- `dbc_path` (str, optional): Path to the DBC file that failed
- `operation` (str, optional): Operation that failed (e.g., 'load', 'parse', 'find_message')
- `original_error` (Exception, optional): The underlying exception that caused this error

**Usage**:

```python
from host_gui.exceptions import DbcError

try:
    dbc_service.load_dbc_file('/path/to/file.dbc')
except DbcError as e:
    logger.error(f"DBC error: {e}")
    logger.error(f"File: {e.dbc_path}, Operation: {e.operation}")
    if e.original_error:
        logger.error(f"Original error: {e.original_error}")
```

**When to Use**:
- DBC file loading failures
- DBC parsing errors
- Message/signal lookup failures

**Example**:

```python
from host_gui.exceptions import DbcError

def load_dbc_file(filepath: str):
    try:
        database = cantools.database.load_file(filepath)
    except Exception as e:
        raise DbcError(
            f"Failed to load DBC file: {e}",
            dbc_path=filepath,
            operation='load',
            original_error=e
        )
```

### TestExecutionError

Exception raised during test execution failures.

**Attributes**:
- `test_name` (str, optional): Name of the test that failed
- `test_type` (str, optional): Type of test ('digital', 'analog', 'phase_current', etc.)
- `stage` (str, optional): Stage of execution that failed (e.g., 'actuation', 'feedback_check')
- `original_error` (Exception, optional): The underlying exception that caused this error

**Usage**:

```python
from host_gui.exceptions import TestExecutionError

try:
    success, info = test_runner.run_test(test)
except TestExecutionError as e:
    logger.error(f"Test execution error: {e}")
    logger.error(f"Test: {e.test_name}, Type: {e.test_type}, Stage: {e.stage}")
    if e.original_error:
        logger.error(f"Original error: {e.original_error}")
```

**When to Use**:
- Test execution failures
- Test validation errors
- Test timeout errors

**Example**:

```python
from host_gui.exceptions import TestExecutionError

def execute_digital_test(test: dict):
    try:
        # Send actuation command
        send_command(test)
        
        # Wait for feedback
        feedback = read_feedback(test)
        
        # Validate feedback
        if not validate_feedback(feedback, test):
            raise TestExecutionError(
                f"Feedback validation failed for test {test['name']}",
                test_name=test['name'],
                test_type='digital',
                stage='feedback_check'
            )
    except TestExecutionError:
        raise
    except Exception as e:
        raise TestExecutionError(
            f"Test execution failed: {e}",
            test_name=test.get('name'),
            test_type='digital',
            stage='execution',
            original_error=e
        )
```

### ConfigurationError

Exception raised for invalid configuration values.

**Attributes**:
- `setting_name` (str, optional): Name of the setting that is invalid
- `setting_value` (Any, optional): The invalid value
- `expected` (str, optional): Description of expected value

**Usage**:

```python
from host_gui.exceptions import ConfigurationError

try:
    config.validate()
except ConfigurationError as e:
    logger.error(f"Configuration error: {e}")
    logger.error(f"Setting: {e.setting_name}, Value: {e.setting_value}, Expected: {e.expected}")
```

**When to Use**:
- Configuration validation failures
- Invalid configuration values
- Missing required configuration

**Example**:

```python
from host_gui.exceptions import ConfigurationError

def validate_can_settings(settings: dict):
    bitrate = settings.get('bitrate')
    if not isinstance(bitrate, int) or bitrate <= 0:
        raise ConfigurationError(
            f"Invalid CAN bitrate: {bitrate}",
            setting_name='bitrate',
            setting_value=bitrate,
            expected='positive integer'
        )
```

### SignalDecodeError

Exception raised for signal decoding failures.

**Attributes**:
- `can_id` (int, optional): CAN message ID that failed to decode
- `signal_name` (str, optional): Name of signal that failed (if applicable)
- `data` (bytes, optional): Raw data bytes that failed to decode
- `original_error` (Exception, optional): The underlying exception that caused this error

**Usage**:

```python
from host_gui.exceptions import SignalDecodeError

try:
    signal_values = signal_service.decode_frame(frame)
except SignalDecodeError as e:
    logger.error(f"Signal decode error: {e}")
    logger.error(f"CAN ID: 0x{e.can_id:X}, Signal: {e.signal_name}")
    if e.original_error:
        logger.error(f"Original error: {e.original_error}")
```

**When to Use**:
- Signal decoding failures
- Message decoding errors
- Invalid signal values

**Example**:

```python
from host_gui.exceptions import SignalDecodeError

def decode_signal(frame: Frame, signal_name: str):
    try:
        message = dbc_service.find_message_by_id(frame.can_id)
        if not message:
            raise SignalDecodeError(
                f"Message not found for CAN ID 0x{frame.can_id:X}",
                can_id=frame.can_id,
                data=frame.data
            )
        
        decoded = dbc_service.decode_message(message, frame.data)
        if signal_name not in decoded:
            raise SignalDecodeError(
                f"Signal '{signal_name}' not found in message",
                can_id=frame.can_id,
                signal_name=signal_name,
                data=frame.data
            )
        
        return decoded[signal_name]
    except SignalDecodeError:
        raise
    except Exception as e:
        raise SignalDecodeError(
            f"Failed to decode signal: {e}",
            can_id=frame.can_id,
            signal_name=signal_name,
            data=frame.data,
            original_error=e
        )
```

## Best Practices

### 1. Use Specific Exceptions

Use the most specific exception type for the error:

```python
# Good
raise CanAdapterError("Connection failed", adapter_type='PCAN', operation='connect')

# Less specific (but acceptable)
raise EolHostException("Connection failed")
```

### 2. Include Context

Always include relevant context in exception attributes:

```python
raise TestExecutionError(
    "Feedback validation failed",
    test_name=test['name'],
    test_type='digital',
    stage='feedback_check'
)
```

### 3. Preserve Original Errors

Capture and preserve original exceptions:

```python
try:
    # Operation that may fail
except Exception as e:
    raise CanAdapterError(
        f"Operation failed: {e}",
        adapter_type='PCAN',
        operation='send_frame',
        original_error=e
    )
```

### 4. Provide Meaningful Messages

Exception messages should be clear and actionable:

```python
# Good
raise ConfigurationError(
    "CAN bitrate must be a positive integer",
    setting_name='bitrate',
    setting_value=bitrate,
    expected='positive integer'
)

# Less helpful
raise ConfigurationError("Invalid bitrate")
```

### 5. Handle Exceptions Appropriately

Catch specific exceptions when possible:

```python
# Good - specific handling
try:
    can_service.connect('PCAN')
except CanAdapterError as e:
    # Handle CAN adapter errors specifically
    show_error_dialog(f"CAN adapter error: {e}")
except Exception as e:
    # Handle other errors
    show_error_dialog(f"Unexpected error: {e}")

# Less specific (but acceptable for general error handling)
try:
    can_service.connect('PCAN')
except EolHostException as e:
    # Handle any application error
    show_error_dialog(f"Error: {e}")
```

### 6. Log Exceptions

Always log exceptions with appropriate level:

```python
try:
    # Operation
except CanAdapterError as e:
    logger.error(f"CAN adapter error: {e}", exc_info=True)
    # Handle error
except Exception as e:
    logger.exception("Unexpected error")
    # Handle error
```

## Error Handling Patterns

### Pattern 1: Service Method Error Handling

```python
def send_frame(self, frame: Frame) -> bool:
    """Send a CAN frame."""
    if not self.is_connected():
        raise CanAdapterError(
            "Cannot send frame: adapter not connected",
            adapter_type=self.adapter_name,
            operation='send_frame'
        )
    
    try:
        self.adapter.send(frame)
        return True
    except Exception as e:
        raise CanAdapterError(
            f"Failed to send frame: {e}",
            adapter_type=self.adapter_name,
            operation='send_frame',
            original_error=e
        )
```

### Pattern 2: Test Execution Error Handling

```python
def run_test(self, test: dict) -> Tuple[bool, str]:
    """Execute a test."""
    test_name = test.get('name', '<unnamed>')
    test_type = test.get('actuation', {}).get('type', 'unknown')
    
    try:
        # Execute test
        return self._execute_test_logic(test)
    except TestExecutionError:
        raise  # Re-raise test execution errors
    except Exception as e:
        raise TestExecutionError(
            f"Test execution failed: {e}",
            test_name=test_name,
            test_type=test_type,
            stage='execution',
            original_error=e
        )
```

### Pattern 3: Configuration Validation

```python
def validate(self) -> List[str]:
    """Validate configuration."""
    errors = []
    
    # Validate CAN settings
    if not isinstance(self.can_settings.bitrate, int) or self.can_settings.bitrate <= 0:
        errors.append(
            ConfigurationError(
                "CAN bitrate must be a positive integer",
                setting_name='bitrate',
                setting_value=self.can_settings.bitrate,
                expected='positive integer'
            )
        )
    
    return errors
```

## Related Documentation

- [Service Architecture](SERVICE_ARCHITECTURE.md) - Services that raise exceptions
- [Configuration Management](CONFIGURATION.md) - ConfigurationError usage

