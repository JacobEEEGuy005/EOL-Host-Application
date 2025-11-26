# Async Test Execution

## Overview

The EOL Host Application uses `TestExecutionThread` to execute test sequences asynchronously in a background thread. This prevents the GUI from freezing during long-running test sequences and provides a responsive user experience.

## TestExecutionThread

`TestExecutionThread` is a `QThread`-based class that executes test sequences in a background thread, emitting Qt signals for progress updates and results.

### Key Features

- **Non-blocking Execution**: Tests run in background thread, GUI remains responsive
- **Progress Reporting**: Emits signals for test progress and completion
- **Pause/Resume**: Supports pausing and resuming test sequences
- **Cancellation**: Supports cancelling test sequences
- **Error Handling**: Handles exceptions and reports errors via signals

## Signals

`TestExecutionThread` emits the following Qt signals:

### Test-Level Signals

- `test_started(int, str)`: Emitted when a test starts
  - Parameters: `test_index`, `test_name`
- `test_progress(float)`: Emitted during test execution
  - Parameters: `progress` (0.0-1.0)
- `test_finished(int, bool, str, float)`: Emitted when a test completes
  - Parameters: `test_index`, `success`, `info`, `execution_time`
- `test_failed(int, str, float)`: Emitted when a test fails with exception
  - Parameters: `test_index`, `error_message`, `execution_time`

### Sequence-Level Signals

- `sequence_started(int)`: Emitted when sequence starts
  - Parameters: `total_tests`
- `sequence_progress(int, int)`: Emitted for overall sequence progress
  - Parameters: `current_test`, `total_tests`
- `sequence_finished(list, str)`: Emitted when sequence completes
  - Parameters: `results_list`, `summary_text`
- `sequence_cancelled()`: Emitted when sequence is cancelled
- `sequence_paused()`: Emitted when sequence is paused
- `sequence_resumed()`: Emitted when sequence is resumed

## Usage in BaseGUI

### Initialization

```python
from host_gui.services.test_execution_thread import TestExecutionThread

class BaseGUI(QtWidgets.QMainWindow):
    def __init__(self):
        # ...
        self.test_execution_thread = None
        self.TestExecutionThread = TestExecutionThread
```

### Creating and Starting Thread

```python
def _on_run_sequence(self):
    # Get test list
    tests = self._get_selected_tests()
    
    # Create TestRunner
    test_runner = TestRunner(
        gui=self,
        can_service=self.can_service,
        dbc_service=self.dbc_service,
        signal_service=self.signal_service,
        oscilloscope_service=self.oscilloscope_service
    )
    
    # Create and configure TestExecutionThread
    self.test_execution_thread = self.TestExecutionThread(
        tests=tests,
        test_runner=test_runner,
        can_service=self.can_service,
        dbc_service=self.dbc_service,
        signal_service=self.signal_service,
        timeout=1.0
    )
    
    # Connect signals
    self.test_execution_thread.test_started.connect(self._on_test_started)
    self.test_execution_thread.test_finished.connect(self._on_test_finished)
    self.test_execution_thread.test_failed.connect(self._on_test_failed)
    self.test_execution_thread.sequence_started.connect(self._on_sequence_started)
    self.test_execution_thread.sequence_finished.connect(self._on_sequence_finished)
    self.test_execution_thread.sequence_cancelled.connect(self._on_sequence_cancelled)
    self.test_execution_thread.sequence_paused.connect(self._on_sequence_paused)
    self.test_execution_thread.sequence_resumed.connect(self._on_sequence_resumed)
    
    # Start thread
    self.test_execution_thread.start()
```

### Signal Handlers

```python
def _on_test_started(self, test_index: int, test_name: str):
    """Handle test started signal."""
    logger.info(f"Test {test_index + 1} started: {test_name}")
    # Update UI to show current test

def _on_test_finished(self, test_index: int, success: bool, info: str, exec_time: float):
    """Handle test finished signal."""
    logger.info(f"Test {test_index + 1} finished: {'PASS' if success else 'FAIL'}")
    # Update results table
    # Update progress bar

def _on_test_failed(self, test_index: int, error: str, exec_time: float):
    """Handle test failed signal."""
    logger.error(f"Test {test_index + 1} failed: {error}")
    # Show error in UI

def _on_sequence_started(self, total_tests: int):
    """Handle sequence started signal."""
    logger.info(f"Test sequence started: {total_tests} tests")
    # Initialize progress bar
    # Disable run button

def _on_sequence_finished(self, results: list, summary: str):
    """Handle sequence finished signal."""
    logger.info(f"Test sequence finished: {summary}")
    # Update results table
    # Enable run button
    # Show summary dialog

def _on_sequence_cancelled(self):
    """Handle sequence cancelled signal."""
    logger.info("Test sequence cancelled")
    # Update UI
    # Enable run button

def _on_sequence_paused(self):
    """Handle sequence paused signal."""
    logger.info("Test sequence paused")
    # Update UI to show paused state

def _on_sequence_resumed(self):
    """Handle sequence resumed signal."""
    logger.info("Test sequence resumed")
    # Update UI to show running state
```

### Pause/Resume

```python
def _on_pause_sequence(self):
    """Pause the test sequence."""
    if self.test_execution_thread and self.test_execution_thread.is_running():
        self.test_execution_thread.pause()

def _on_resume_sequence(self):
    """Resume the paused test sequence."""
    if self.test_execution_thread and self.test_execution_thread.is_paused():
        self.test_execution_thread.resume()
```

### Cancellation

```python
def _on_cancel_sequence(self):
    """Cancel the test sequence."""
    if self.test_execution_thread and self.test_execution_thread.is_running():
        self.test_execution_thread.stop()
        # Wait for thread to finish (optional)
        self.test_execution_thread.wait()
```

### Cleanup

```python
def closeEvent(self, event):
    """Handle window close event."""
    # Stop test execution thread if running
    if self.test_execution_thread and self.test_execution_thread.is_running():
        self.test_execution_thread.stop()
        self.test_execution_thread.wait(5000)  # Wait up to 5 seconds
    event.accept()
```

## Pause/Resume Behavior

### Pause Request

When `pause()` is called:
1. The current test completes normally
2. The sequence pauses before starting the next test
3. `sequence_paused` signal is emitted
4. Thread waits in paused state

### Resume

When `resume()` is called:
1. `sequence_resumed` signal is emitted
2. Thread continues from the next test in sequence
3. If a test requested pause (e.g., user declined safety check), the same test is retried

### Test-Requested Pause

Tests can request a pause by returning `(False, "Test sequence paused: reason")`. This is useful for:
- User confirmation dialogs
- Safety checks
- Manual intervention required

When a test requests pause:
- The test is not recorded as a failure
- The sequence pauses
- On resume, the same test is retried

## Thread Safety

### Qt Signal/Slot Thread Safety

Qt signals and slots are thread-safe:
- Signals can be emitted from any thread
- Slots are executed in the receiver's thread (main thread for GUI)
- No manual synchronization needed for signal/slot connections

### Service Thread Safety

Services handle thread safety internally:
- `CanService` uses `AdapterWorker` thread for frame reception
- `SignalService` uses thread-safe caching
- `OscilloscopeService` operations are thread-safe

### GUI Updates

All GUI updates should be done in the main thread:
- Use Qt signals to communicate from background thread to GUI
- Do not access GUI widgets directly from background thread
- Use `QMetaObject.invokeMethod()` or signals for thread-safe GUI updates

## Error Handling

### Test Execution Errors

Test execution errors are caught and reported via `test_failed` signal:

```python
try:
    success, info = self.test_runner.run_single_test(test, self.timeout)
except Exception as e:
    error_msg = str(e)
    self.test_failed.emit(test_index, error_msg, exec_time)
```

### Thread Errors

Thread-level errors are caught and logged:

```python
try:
    # Execute tests
except Exception as e:
    logger.error(f"Test sequence execution failed: {e}", exc_info=True)
    self.sequence_finished.emit(results, f"Sequence failed: {e}")
```

## Best Practices

1. **Always Connect Signals**: Connect all relevant signals before starting thread
2. **Handle All Signals**: Implement handlers for all signals you connect
3. **Cleanup on Close**: Stop and wait for thread in `closeEvent()`
4. **Progress Updates**: Use `test_progress` and `sequence_progress` for UI updates
5. **Error Handling**: Handle `test_failed` signal for error reporting
6. **Pause/Resume**: Provide UI controls for pause/resume functionality
7. **Cancellation**: Allow users to cancel long-running sequences
8. **Thread Safety**: Never access GUI widgets directly from background thread

## Example: Complete Integration

```python
class BaseGUI(QtWidgets.QMainWindow):
    def __init__(self):
        # ... initialization ...
        self.test_execution_thread = None
    
    def _on_run_sequence(self):
        tests = self._get_selected_tests()
        if not tests:
            return
        
        # Create test runner
        test_runner = TestRunner(
            gui=self,
            can_service=self.can_service,
            dbc_service=self.dbc_service,
            signal_service=self.signal_service,
            oscilloscope_service=self.oscilloscope_service
        )
        
        # Create thread
        self.test_execution_thread = TestExecutionThread(
            tests=tests,
            test_runner=test_runner,
            can_service=self.can_service,
            dbc_service=self.dbc_service,
            signal_service=self.signal_service,
            timeout=1.0
        )
        
        # Connect signals
        self.test_execution_thread.test_started.connect(self._on_test_started)
        self.test_execution_thread.test_finished.connect(self._on_test_finished)
        self.test_execution_thread.test_failed.connect(self._on_test_failed)
        self.test_execution_thread.sequence_started.connect(self._on_sequence_started)
        self.test_execution_thread.sequence_finished.connect(self._on_sequence_finished)
        self.test_execution_thread.sequence_cancelled.connect(self._on_sequence_cancelled)
        self.test_execution_thread.sequence_paused.connect(self._on_sequence_paused)
        self.test_execution_thread.sequence_resumed.connect(self._on_sequence_resumed)
        
        # Start thread
        self.test_execution_thread.start()
        
        # Update UI
        self.run_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
    
    def _on_pause_sequence(self):
        if self.test_execution_thread and self.test_execution_thread.is_running():
            self.test_execution_thread.pause()
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(True)
    
    def _on_resume_sequence(self):
        if self.test_execution_thread and self.test_execution_thread.is_paused():
            self.test_execution_thread.resume()
            self.pause_button.setEnabled(True)
            self.resume_button.setEnabled(False)
    
    def _on_cancel_sequence(self):
        if self.test_execution_thread and self.test_execution_thread.is_running():
            self.test_execution_thread.stop()
            self.run_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
    
    def closeEvent(self, event):
        if self.test_execution_thread and self.test_execution_thread.is_running():
            self.test_execution_thread.stop()
            self.test_execution_thread.wait(5000)
        event.accept()
```

## Related Documentation

- [Service Architecture](SERVICE_ARCHITECTURE.md) - Service layer used by TestExecutionThread
- [Test Type System Overview](TEST_TYPE_SYSTEM_OVERVIEW.md) - Test execution overview

