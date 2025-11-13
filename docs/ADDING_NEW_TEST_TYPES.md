# Adding New Test Types to EOL Host Application

## Overview

This document provides a comprehensive guide for AI agents on how to add new test types to the EOL Host Application codebase. The system currently supports 8 test types:

1. **Digital Logic Test** - Tests digital relay states
2. **Analog Sweep Test** - Sweeps DAC voltages and monitors feedback
3. **Phase Current Test** - Phase current calibration with oscilloscope integration
4. **Analog Static Test** - Static analog measurement comparison
5. **Temperature Validation Test** - Temperature measurement validation
6. **Fan Control Test** - Fan control system testing
7. **External 5V Test** - External 5V power supply testing
8. **DC Bus Sensing** - DC bus voltage sensing with oscilloscope

## Architecture Overview

The test type system is distributed across multiple components:

1. **Schema Definition** (`backend/data/tests/schema.json`) - JSON schema validation
2. **GUI Components** (`host_gui/base_gui.py`) - User interface for creating/editing tests
3. **Validation Logic** (`host_gui/base_gui.py::_validate_test()`) - Test configuration validation
4. **Execution Logic** (`host_gui/test_runner.py`) - Test execution implementation
5. **Service Layer** (`host_gui/services/test_execution_service.py`) - Decoupled test execution
6. **Data Models** (`host_gui/models/test_profile.py`) - Test configuration data structures

## Step-by-Step Guide to Adding a New Test Type

### Step 1: Update JSON Schema

**File:** `backend/data/tests/schema.json`

Add the new test type to the schema's enum list and create a corresponding `oneOf` entry.

#### 1.1 Add to Type Enum

Locate the `type` property in the schema (around line 13) and add your test type name to the enum array:

```json
"type": {
  "type": "string",
  "enum": [
    "Digital Logic Test",
    "Analog Sweep Test",
    "Phase Current Test",
    "Analog Static Test",
    "Temperature Validation Test",
    "Fan Control Test",
    "External 5V Test",
    "DC Bus Sensing",
    "Your New Test Type"  // <-- Add here
  ]
}
```

#### 1.2 Add Actuation Schema

In the `actuation.oneOf` array (starting around line 17), add a new object defining the required and optional properties for your test type's actuation configuration:

```json
{
  "properties": {
    "type": {"const": "Your New Test Type"},
    "required_field_1": {"type": "integer"},
    "required_field_2": {"type": "string"},
    "optional_field_1": {"type": "number", "minimum": 0},
    "optional_field_2": {"type": "integer", "minimum": 1}
  },
  "required": [
    "required_field_1",
    "required_field_2"
  ]
}
```

**Example from Temperature Validation Test:**
```json
{
  "properties": {
    "type": {"const": "Temperature Validation Test"},
    "feedback_signal_source": {"type": "integer"},
    "feedback_signal": {"type": "string"},
    "reference_temperature_c": {"type": "number"},
    "tolerance_c": {"type": "number", "minimum": 0},
    "dwell_time_ms": {"type": "integer", "minimum": 1}
  },
  "required": [
    "feedback_signal_source",
    "feedback_signal",
    "reference_temperature_c",
    "tolerance_c",
    "dwell_time_ms"
  ]
}
```

### Step 2: Update Data Model

**File:** `host_gui/models/test_profile.py`

#### 2.1 Update ActuationConfig Docstring

Add documentation for your test type's fields in the `ActuationConfig` class docstring (around line 10). Document all fields that your test type will use.

#### 2.2 Add Fields to ActuationConfig

If your test type requires new fields not already in `ActuationConfig`, add them as optional fields:

```python
# Your New Test Type fields
your_new_field_1: Optional[int] = None
your_new_field_2: Optional[str] = None
```

**Note:** Most test types reuse existing fields. Check the existing fields before adding new ones.

### Step 3: Update GUI - Create Test Dialog

**File:** `host_gui/base_gui.py`

#### 3.1 Add to Test Type ComboBox

In `_on_create_test()` method (around line 5357), add your test type to the combo box:

```python
type_combo.addItems([
    'Digital Logic Test',
    'Analog Sweep Test',
    'Phase Current Test',
    'Analog Static Test',
    'Temperature Validation Test',
    'Fan Control Test',
    'External 5V Test',
    'DC Bus Sensing',
    'Your New Test Type'  # <-- Add here
])
```

#### 3.2 Create Widget for Test Type Configuration

Create a widget and layout for your test type's configuration fields (around line 5360-5376):

```python
your_test_widget = QtWidgets.QWidget()
your_test_layout = QtWidgets.QFormLayout(your_test_widget)

# Create input fields
your_field_1_edit = QtWidgets.QLineEdit()
your_field_2_combo = QtWidgets.QComboBox()
# ... add more fields as needed

# Add fields to layout
your_test_layout.addRow('Field 1 Label:', your_field_1_edit)
your_test_layout.addRow('Field 2 Label:', your_field_2_combo)
```

**For DBC-driven fields (CAN messages/signals):**

If your test type needs CAN message/signal selection, follow the pattern used by other test types:

```python
# Message combo
your_msg_combo = QtWidgets.QComboBox()
for m, label in msg_display:
    fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
    your_msg_combo.addItem(label, fid)

# Signal combo (populated based on selected message)
your_signal_combo = QtWidgets.QComboBox()

def _update_your_signals(idx=0):
    your_signal_combo.clear()
    try:
        m = messages[idx]
        sigs = [s.name for s in getattr(m, 'signals', [])]
        your_signal_combo.addItems(sigs)
    except Exception:
        pass

if msg_display:
    _update_your_signals(0)
your_msg_combo.currentIndexChanged.connect(_update_your_signals)
```

#### 3.3 Add Widget to Stacked Widget

Register your widget in the test type to index mapping (around line 6322-6330):

```python
test_type_to_index['Your New Test Type'] = act_stacked.addWidget(your_test_widget)
```

#### 3.4 Handle Feedback Fields Visibility

In the `_on_type_change()` function (around line 6335), add logic to show/hide feedback fields if needed:

```python
def _on_type_change(txt: str):
    # ... existing code ...
    elif txt == 'Your New Test Type':
        # Hide feedback fields if your test type has its own
        if fb_msg_label is not None:
            fb_msg_label.hide()
            fb_msg_combo.hide()
            # ... or show them if needed
```

#### 3.5 Build Actuation Dictionary

In the `on_accept()` function (around line 6370), add a branch to build the actuation dictionary for your test type:

```python
elif t == 'Your New Test Type':
    # Read all fields from your widget
    try:
        field_1_val = your_field_1_edit.text().strip()
    except Exception:
        field_1_val = None
    
    # For DBC mode
    if self.dbc_service is not None and self.dbc_service.is_loaded():
        try:
            msg_id = your_msg_combo.currentData()
        except Exception:
            msg_id = None
        signal = your_signal_combo.currentText().strip()
        
        act = {
            'type': 'Your New Test Type',
            'field_1': field_1_val,
            'message_id': msg_id,
            'signal': signal,
            # ... add all required fields
        }
    else:
        # Non-DBC mode (free-text inputs)
        act = {
            'type': 'Your New Test Type',
            'field_1': field_1_val,
            # ... add all required fields
        }
```

### Step 4: Update GUI - Edit Test Dialog

**File:** `host_gui/base_gui.py`

#### 4.1 Add to Edit Dialog ComboBox

In `_on_edit_test()` method (around line 8500+), add your test type to the combo box (same as create dialog).

#### 4.2 Create Edit Widget

Create a widget for editing your test type, similar to the create dialog but pre-populated with existing values:

```python
your_test_widget_edit = QtWidgets.QWidget()
your_test_layout_edit = QtWidgets.QFormLayout(your_test_widget_edit)

# Pre-populate fields from existing test data
act = data.get('actuation', {})
your_field_1_edit_edit = QtWidgets.QLineEdit(str(act.get('field_1', '')))
# ... create and populate all fields
```

#### 4.3 Register Edit Widget

Add to the edit dialog's stacked widget mapping (around line 8841):

```python
test_type_to_index_edit['Your New Test Type'] = act_stacked_edit.addWidget(your_test_widget_edit)
```

#### 4.4 Handle Edit Dialog Type Changes

Update `_on_type_change_edit()` function (around line 8854) to handle your test type.

#### 4.5 Update Actuation in Edit Dialog

In the edit dialog's `on_accept()` function (around line 8890), add a branch to update the actuation dictionary for your test type (similar to create dialog).

### Step 5: Update Validation Logic

**File:** `host_gui/base_gui.py`

#### 5.1 Add to Type Validation

In `_validate_test()` method (around line 7229), add your test type to the allowed types:

```python
if test_type not in (
    'Digital Logic Test',
    'Analog Sweep Test',
    'Phase Current Test',
    'Analog Static Test',
    'Temperature Validation Test',
    'Fan Control Test',
    'External 5V Test',
    'DC Bus Sensing',
    'Your New Test Type'  # <-- Add here
):
    return False, f"Invalid test type: {test_type}..."
```

#### 5.2 Add Type-Specific Validation

Add validation logic for your test type's required fields (around line 7243):

```python
elif test_type == 'Your New Test Type':
    # Validate required fields
    if actuation.get('required_field_1') is None:
        return False, "Your New Test Type requires required_field_1"
    if not actuation.get('required_field_2'):
        return False, "Your New Test Type requires required_field_2"
    # Validate field ranges/constraints
    if actuation.get('optional_field_1', 0) < 0:
        return False, "optional_field_1 must be non-negative"
    if actuation.get('optional_field_2', 0) <= 0:
        return False, "optional_field_2 must be positive"
```

### Step 6: Implement Test Execution

**File:** `host_gui/test_runner.py`

#### 6.1 Add Execution Branch

In the `run_test()` method (around line 200), add a branch to handle your test type:

```python
elif act.get('type') == 'Your New Test Type':
    # Extract parameters
    param1 = act.get('field_1')
    param2 = act.get('field_2')
    
    # Validate parameters
    if not all([param1, param2]):
        return False, "Missing required parameters"
    
    # Implement test execution logic
    try:
        # Your test execution code here
        # - Send CAN messages if needed
        # - Read signals
        # - Perform measurements
        # - Determine pass/fail
        
        success = True  # or False based on results
        info = "Test execution details"
        return success, info
    except Exception as e:
        logger.error(f"Your New Test Type execution failed: {e}", exc_info=True)
        return False, f"Test execution error: {e}"
```

#### 6.2 Implementation Pattern

Follow the pattern used by existing test types:

1. **Extract parameters** from the actuation dictionary
2. **Validate parameters** (required fields, ranges, etc.)
3. **Implement test logic**:
   - Send actuation commands (CAN messages)
   - Wait for stabilization (pre-dwell time if applicable)
   - Collect data during dwell time
   - Process data (calculate averages, compare values, etc.)
   - Determine pass/fail based on criteria
4. **Return results** as `(success: bool, info: str)`

**Helper Functions Available:**
- `_nb_sleep(sec: float)` - Non-blocking sleep that processes Qt events
- `_encode_and_send(signal_dict)` - Encode and send CAN message (if DBC available)
- `self.signal_service.get_latest_signal(msg_id, signal_name)` - Get latest signal value
- `self.can_service.send_frame(frame)` - Send CAN frame

**Example from Analog Static Test:**
```python
elif act.get('type') == 'Analog Static Test':
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
    
    # Wait for pre-dwell time
    _nb_sleep(pre_dwell_ms / 1000.0)
    
    # Collect data during dwell time
    feedback_values = []
    eol_values = []
    end_time = time.time() + (dwell_ms / 1000.0)
    
    while time.time() < end_time:
        # Read signals
        if self.signal_service is not None:
            _, fb_val = self.signal_service.get_latest_signal(feedback_msg_id, feedback_signal)
            _, eol_val = self.signal_service.get_latest_signal(eol_msg_id, eol_signal)
        # ... collect values ...
        time.sleep(SLEEP_INTERVAL_SHORT)
    
    # Calculate averages and determine pass/fail
    feedback_avg = sum(feedback_values) / len(feedback_values)
    eol_avg = sum(eol_values) / len(eol_values)
    difference = abs(feedback_avg - eol_avg)
    passed = difference <= tolerance_mv
    
    return passed, f"Feedback Avg: {feedback_avg:.2f} mV, EOL Avg: {eol_avg:.2f} mV..."
```

### Step 7: Update Test Execution Service (Optional)

**File:** `host_gui/services/test_execution_service.py`

If you want to support your test type in the decoupled service layer:

#### 7.1 Add Execution Branch

In `run_single_test()` method (around line 147), add a branch:

```python
elif act.get('type') == 'Your New Test Type':
    return self._run_your_new_test(test, timeout)
```

#### 7.2 Implement Execution Method

Add a private method to implement the test execution:

```python
def _run_your_new_test(self, test: Dict[str, Any], timeout: float) -> Tuple[bool, str]:
    """Execute Your New Test Type.
    
    Args:
        test: Test configuration dictionary
        timeout: Timeout in seconds
        
    Returns:
        Tuple of (success, info_message)
    """
    act = test.get('actuation', {})
    # Implement test execution similar to test_runner.py
    # ...
    return success, info
```

### Step 8: Update Report Generation

**File:** `host_gui/base_gui.py`

#### 8.1 Add to Report Type Filter

In `_refresh_test_report()` method (around line 2166), add your test type to the filter:

```python
if type_filter != 'All':
    # ... existing filters ...
    elif type_filter == 'Your New Test Type' and test_type != 'Your New Test Type':
        continue
```

#### 8.2 Add Report Display Logic

In `_build_test_report()` method (around line 2012), add logic to display your test type's results appropriately. Check how other test types are displayed and follow the same pattern.

### Step 9: Update Results Display

**File:** `host_gui/base_gui.py`

#### 9.1 Add to Results Table

In methods that display test results (around line 1179), ensure your test type is handled correctly. Most test types use the same display logic, but check if special handling is needed.

### Step 10: Testing Checklist

After implementing your new test type, verify:

- [ ] Test type appears in create test dialog dropdown
- [ ] Test type appears in edit test dialog dropdown
- [ ] Configuration fields are displayed correctly for your test type
- [ ] Test can be created and saved
- [ ] Test can be edited and saved
- [ ] Test validation works correctly (required fields, ranges, etc.)
- [ ] Test execution runs without errors
- [ ] Test execution returns correct pass/fail results
- [ ] Test results appear in results table
- [ ] Test results appear in test report
- [ ] JSON schema validation works (test with invalid configuration)
- [ ] Test works with DBC loaded
- [ ] Test works without DBC loaded (if applicable)

## Common Patterns and Examples

### Pattern 1: Simple Signal Reading Test

For tests that just read a signal and compare to a reference:

```python
# Extract parameters
signal_source = act.get('signal_source')
signal_name = act.get('signal_name')
reference_value = float(act.get('reference_value'))
tolerance = float(act.get('tolerance'))
dwell_ms = int(act.get('dwell_time_ms'))

# Collect data
values = []
end_time = time.time() + (dwell_ms / 1000.0)
while time.time() < end_time:
    if self.signal_service is not None:
        _, val = self.signal_service.get_latest_signal(signal_source, signal_name)
        if val is not None:
            values.append(float(val))
    time.sleep(SLEEP_INTERVAL_SHORT)

# Compare
avg = sum(values) / len(values)
difference = abs(avg - reference_value)
passed = difference <= tolerance
return passed, f"Reference: {reference_value}, Measured: {avg:.2f}, Diff: {difference:.2f}"
```

### Pattern 2: CAN Command + Feedback Test

For tests that send a command and verify feedback:

```python
# Extract parameters
cmd_msg_id = act.get('command_message_id')
cmd_signal = act.get('command_signal')
cmd_value = act.get('command_value')
feedback_msg_id = act.get('feedback_signal_source')
feedback_signal = act.get('feedback_signal')
expected_value = act.get('expected_value')
dwell_ms = int(act.get('dwell_time_ms'))

# Send command
if self.dbc_service is not None and self.dbc_service.is_loaded():
    msg = self.dbc_service.find_message_by_id(cmd_msg_id)
    if msg is not None:
        signal_values = {cmd_signal: cmd_value}
        frame_data = self.dbc_service.encode_message(msg, signal_values)
        frame = AdapterFrame(can_id=cmd_msg_id, data=frame_data)
        self.can_service.send_frame(frame)

# Wait and verify
# ... collect feedback values during dwell time ...
# ... compare to expected value ...
```

### Pattern 3: Multi-Phase Test

For tests with multiple phases (like External 5V Test):

```python
# Phase 1: Disabled state
_send_trigger(0)  # Disable
_nb_sleep(pre_dwell_ms / 1000.0)
phase1_values = _collect_data_phase("Disabled")

# Phase 2: Enabled state
_send_trigger(1)  # Enable
_nb_sleep(pre_dwell_ms / 1000.0)
phase2_values = _collect_data_phase("Enabled")

# Phase 3: Cleanup
_send_trigger(0)  # Disable

# Evaluate both phases
phase1_passed = _evaluate_phase(phase1_values)
phase2_passed = _evaluate_phase(phase2_values)
passed = phase1_passed and phase2_passed
```

## Important Notes

1. **Test Type Names**: Must match exactly across all files. Use consistent capitalization and spelling.

2. **DBC vs Non-DBC**: Most test types support both DBC-loaded and non-DBC modes. In DBC mode, use dropdowns for messages/signals. In non-DBC mode, use free-text inputs.

3. **Error Handling**: Always validate parameters and handle exceptions gracefully. Return meaningful error messages.

4. **Logging**: Use the logger for debugging and error tracking:
   ```python
   logger.info(f"Your New Test Type: Starting execution...")
   logger.error(f"Your New Test Type failed: {e}", exc_info=True)
   ```

5. **Non-Blocking Sleep**: Always use `_nb_sleep()` instead of `time.sleep()` to keep the UI responsive during test execution.

6. **Signal Service**: Prefer `self.signal_service.get_latest_signal()` over direct GUI access for better decoupling.

7. **Plot Updates**: If your test type produces plot data, use `self.plot_update_callback()` to update plots in real-time.

8. **Result Storage**: Store detailed results in `self.gui._test_result_data_temp[test_name]` for later retrieval in report generation.

## File Locations Summary

| Component | File | Key Methods/Functions |
|-----------|------|---------------------|
| Schema | `backend/data/tests/schema.json` | `type.enum`, `actuation.oneOf` |
| Data Model | `host_gui/models/test_profile.py` | `ActuationConfig` class |
| Create Dialog | `host_gui/base_gui.py` | `_on_create_test()` |
| Edit Dialog | `host_gui/base_gui.py` | `_on_edit_test()` |
| Validation | `host_gui/base_gui.py` | `_validate_test()` |
| Execution | `host_gui/test_runner.py` | `run_test()` |
| Service Execution | `host_gui/services/test_execution_service.py` | `run_single_test()` |
| Reports | `host_gui/base_gui.py` | `_build_test_report()`, `_refresh_test_report()` |

## Conclusion

Adding a new test type requires coordinated changes across multiple files. Follow this guide systematically, and ensure all components are updated consistently. Test thoroughly with both DBC-loaded and non-DBC scenarios to ensure robustness.

