# Adding New Test Types to EOL Host Application

## Overview

This document provides a comprehensive guide for AI agents on how to add new test types to the EOL Host Application codebase. The system currently supports 13 test types:

1. **Digital Logic Test** - Tests digital relay states
2. **Analog Sweep Test** - Sweeps DAC voltages and monitors feedback
3. **Phase Current Test** - Phase current calibration with oscilloscope integration
4. **Analog Static Test** - Static analog measurement comparison
5. **Analog PWM Sensor** - PWM sensor frequency and duty cycle validation
6. **Temperature Validation Test** - Temperature measurement validation
7. **Fan Control Test** - Fan control system testing
8. **External 5V Test** - External 5V power supply testing
9. **DC Bus Sensing** - DC bus voltage sensing with oscilloscope
10. **Output Current Calibration** - Output current sensor calibration with oscilloscope integration
11. **Charged HV Bus Test** - Charged high voltage bus testing
12. **Charger Functional Test** - Charger functional testing with current validation
13. **Phase Offset Calibration Test** - Phase offset calibration: send Test Request (Drive Mode), poll for CAL_DONE, read Phase V/W ADC offsets

## Architecture Overview

The test type system is distributed across multiple components:

1. **Schema Definition** (`backend/data/tests/schema.json`) - JSON schema validation
2. **GUI Components** (`host_gui/base_gui.py`) - User interface for creating/editing tests
3. **Validation Logic** (`host_gui/base_gui.py::_validate_test()`) - Test configuration validation
4. **Execution Logic** (`host_gui/test_runner.py`) - Test execution implementation
5. **Service Layer** (`host_gui/services/`) - Business logic services
   - `test_execution_service.py` - Decoupled test execution
   - `can_service.py` - CAN adapter management
   - `dbc_service.py` - DBC file operations
   - `signal_service.py` - Signal decoding
   - `oscilloscope_service.py` - Oscilloscope management
6. **Data Models** (`host_gui/models/test_profile.py`) - Test configuration data structures

For detailed service architecture documentation, see [Service Architecture](SERVICE_ARCHITECTURE.md).

## Step-by-Step Guide to Adding a New Test Type

### Step 1: Update JSON Schema

**File:** `backend/data/tests/schema.json`

Add the new test type to the schema's enum list and create a corresponding `oneOf` entry.

#### 1.1 Add to Type Enum

Locate the `type` property in the schema (around line 13 in `schema.json`) and add your test type name to the enum array:

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

In the `actuation.oneOf` array (starting around line 18 in `schema.json`), add a new object defining the required and optional properties for your test type's actuation configuration:

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

Add documentation for your test type's fields in the `ActuationConfig` class docstring in `host_gui/models/test_profile.py`. Document all fields that your test type will use.

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

In `_on_create_test()` method (around line 8579 in `base_gui.py`), add your test type to the combo box:

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

Create a widget and layout for your test type's configuration fields (after adding to combo box in `_on_create_test()`):

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

Register your widget in the test type to index mapping (in `_on_create_test()` method):

```python
test_type_to_index['Your New Test Type'] = act_stacked.addWidget(your_test_widget)
```

#### 3.4 Handle Feedback Fields Visibility

In the `_on_type_change()` function (within `_on_create_test()` method), add logic to show/hide feedback fields if needed:

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

In the `on_accept()` function (within `_on_create_test()` method), add a branch to build the actuation dictionary for your test type:

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

In `_on_edit_test()` method (around line 12376 in `base_gui.py`), add your test type to the combo box (same as create dialog).

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

Add to the edit dialog's stacked widget mapping (in `_on_edit_test()` method):

```python
test_type_to_index_edit['Your New Test Type'] = act_stacked_edit.addWidget(your_test_widget_edit)
```

#### 4.4 Handle Edit Dialog Type Changes

Update `_on_type_change_edit()` function (within `_on_edit_test()` method) to handle your test type.

#### 4.5 Update Actuation in Edit Dialog

In the edit dialog's `on_accept()` function (within `_on_edit_test()` method), add a branch to update the actuation dictionary for your test type (similar to create dialog).

### Step 5: Update Validation Logic

**File:** `host_gui/base_gui.py`

#### 5.1 Add to Type Validation

In `_validate_test()` method (around line 11640 in `base_gui.py`), add your test type to the allowed types:

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

Add validation logic for your test type's required fields (within `_validate_test()` method):

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

In the `run_test()` method in `test_runner.py`, add a branch to handle your test type:

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

If you want to support your test type in the decoupled service layer (for headless execution):

**Note**: `TestExecutionService` uses the same service pattern as `TestRunner`. Services are passed to the constructor and accessed as attributes.

#### 7.1 Add Execution Branch

In `run_single_test()` method (around line 599 in `test_runner.py`), add a branch:

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

In `_refresh_test_report()` method (around line 4203 in `base_gui.py`), add your test type to the filter dropdown:

```python
self.report_type_filter.addItems([
    'All', 
    'Digital Logic Test', 
    'Analog Sweep Test', 
    # ... existing types ...
    'Your New Test Type'  # <-- Add here
])
```

#### 8.2 Add Report Tree Display Logic

In `_refresh_test_report()` method (around line 4203 in `base_gui.py`), add a section to display your test type's results in the report tree:

```python
# For your new test type, add results and plot sections
is_your_test = (test_type == 'Your New Test Type' or 
                (test_config and test_config.get('type') == 'Your New Test Type'))
if is_your_test and test_config:
    exec_data_full = self._test_execution_data.get(test_name, exec_data)
    plot_data = exec_data_full.get('plot_data')
    
    if plot_data:
        # Add calibration/results data section
        if some_result_data:
            results_item = QtWidgets.QTreeWidgetItem(['Results', '', '', ''])
            results_item.setExpanded(False)
            # Add child items with results
            results_item.addChild(QtWidgets.QTreeWidgetItem(['Parameter 1', f"{value1:.4f}", '', '']))
            test_item.addChild(results_item)
        
        # Add plot widget if plot data is available
        if matplotlib_available:
            plot_item = QtWidgets.QTreeWidgetItem(['Plot: Your Plot Title', '', '', ''])
            plot_item.setExpanded(False)
            
            x_values = plot_data.get('x_values', [])
            y_values = plot_data.get('y_values', [])
            
            if x_values and y_values:
                try:
                    # Create plot widget
                    plot_widget = QtWidgets.QWidget()
                    plot_layout = QtWidgets.QVBoxLayout(plot_widget)
                    plot_layout.setContentsMargins(0, 0, 0, 0)
                    
                    plot_figure = Figure(figsize=(8, 6))
                    plot_canvas = FigureCanvasQTAgg(plot_figure)
                    plot_axes = plot_figure.add_subplot(111)
                    
                    # Filter out NaN values
                    x_clean = []
                    y_clean = []
                    min_len = min(len(x_values), len(y_values))
                    for i in range(min_len):
                        x_val = x_values[i]
                        y_val = y_values[i]
                        if (isinstance(x_val, (int, float)) and isinstance(y_val, (int, float)) and
                            not (isinstance(x_val, float) and x_val != x_val) and
                            not (isinstance(y_val, float) and y_val != y_val)):
                            x_clean.append(x_val)
                            y_clean.append(y_val)
                    
                    if x_clean and y_clean:
                        plot_axes.plot(x_clean, y_clean, 'bo', markersize=6, label='Data Points')
                        plot_axes.set_xlabel('X-Axis Label')
                        plot_axes.set_ylabel('Y-Axis Label')
                        plot_axes.set_title(f'Your Plot Title: {test_name}')
                        plot_axes.grid(True, alpha=0.3)
                        plot_axes.legend()
                        plot_axes.relim()
                        plot_axes.autoscale()
                    
                    plot_figure.tight_layout()
                    plot_layout.addWidget(plot_canvas)
                    
                    # Set widget as item widget
                    self.report_tree.setItemWidget(plot_item, 1, plot_widget)
                except Exception as e:
                    logger.error(f"Error creating plot in report: {e}", exc_info=True)
                    plot_item.setText(1, f"Plot error: {e}")
            
            test_item.addChild(plot_item)
```

**Reference Implementation:** Search for `Output Current Calibration` in `_refresh_test_report()` method for a complete example.

#### 8.3 Add to Test Details Popup

In `_show_test_details_popup()` method (around line 2168 in `base_gui.py`), add a section to display your test type's plot and results in the popup dialog:

```python
# For your new test type
elif test_type == 'Your New Test Type':
    plot_data = exec_data.get('plot_data')
    if plot_data:
        # Create plot section
        plot_label = QtWidgets.QLabel('Plot:')
        plot_label.setStyleSheet('font-weight: bold;')
        layout.addWidget(plot_label)
        
        # Create matplotlib plot
        if matplotlib_available:
            try:
                plot_figure = Figure(figsize=(6, 4))
                plot_canvas = FigureCanvasQTAgg(plot_figure)
                plot_axes = plot_figure.add_subplot(111)
                
                x_values = plot_data.get('x_values', [])
                y_values = plot_data.get('y_values', [])
                # ... plot data ...
                
                plot_figure.tight_layout()
                layout.addWidget(plot_canvas)
            except Exception as e:
                logger.error(f"Error creating plot in popup: {e}", exc_info=True)
        
        # Add results text
        results_text = QtWidgets.QTextEdit()
        results_text.setReadOnly(True)
        results_text.setMaximumHeight(100)
        # ... populate results text ...
        layout.addWidget(results_text)
```

**Reference Implementation:** See `Output Current Calibration` section in `_show_test_details_popup()` for a complete example.

### Step 9: Update Results Display and Storage

**File:** `host_gui/base_gui.py`

#### 9.1 Store Plot Data for Reports

In `_on_test_finished()` method (around line 15979 in `base_gui.py`) or `_on_test_failed()` method, ensure plot data is stored for your test type:

```python
# Store plot data for your test type
if test_type == 'Your New Test Type':
    plot_data = self._test_plot_data_temp.get(test_name, {})
    if plot_data:
        exec_data['plot_data'] = {
            'x_values': list(plot_data.get('x_values', [])),
            'y_values': list(plot_data.get('y_values', [])),
            # ... other plot data fields ...
        }
```

#### 9.2 Store Result Statistics

Also store any calculated statistics or results:

```python
# Store result data
result_data = self._test_result_data_temp.get(test_name, {})
if result_data:
    exec_data['result_data'] = {
        'statistic1': result_data.get('statistic1'),
        'statistic2': result_data.get('statistic2'),
        # ... other result fields ...
    }
```

**Reference Implementation:** Search for `Output Current Calibration` in `_on_test_finished()` method for a complete example.

### Step 10: Add Plot Initialization (If Using Live Plots)

**File:** `host_gui/base_gui.py`

If your test type uses live plots that update during execution, you need to initialize the plot before the test starts:

#### 10.1 Create Plot Initialization Method

Add a method to initialize your test type's plot:

```python
def _initialize_your_test_plot(self, test_name: Optional[str] = None) -> None:
    """Initialize the plot for Your New Test Type with proper labels and title.
    
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
        self.plot_axes.set_xlabel('Your X-Axis Label')
        self.plot_axes.set_ylabel('Your Y-Axis Label')
        self.plot_axes.set_title(f'Your Plot Title{(": " + test_name) if test_name else ""}')
        self.plot_axes.grid(True, alpha=PLOT_GRID_ALPHA)
        # Add reference lines if needed
        # self.plot_axes.axline((0, 0), slope=1, color='gray', linestyle='--', alpha=0.5, label='Ideal (y=x)')
        # Create plot line
        self.plot_line, = self.plot_axes.plot([], [], 'bo', markersize=6, label='Data Points')
        self.plot_axes.legend()
        self.plot_figure.tight_layout()
        self.plot_canvas.draw_idle()
        self._your_test_plot_initialized = True
        logger.debug(f"Initialized plot for Your New Test Type: {test_name}")
    except Exception as e:
        logger.error(f"Failed to initialize Your New Test Type plot: {e}", exc_info=True)
```

#### 10.2 Call Plot Initialization in Test Runner

**File:** `host_gui/test_runner.py`

In your test execution code, call the plot initialization right after clearing the plot:

```python
# Initialize plot
if self.plot_clear_callback is not None:
    self.plot_clear_callback()

# Initialize plot labels and title for your test type
test_name = test.get('name', '')
if self.gui is not None and hasattr(self.gui, '_initialize_your_test_plot'):
    try:
        self.gui._initialize_your_test_plot(test_name)
    except Exception as e:
        logger.debug(f"Failed to initialize Your New Test Type plot: {e}")
```

**Reference Implementation:** Search for `Output Current Calibration` in `test_runner.py` for a complete example.

#### 10.3 Update Plot Update Method

In `_update_plot()` method (around line 3940 in `base_gui.py`), add handling for your test type:

```python
# Detect your test type
is_your_test = False
if hasattr(self, '_current_test_index') and self._current_test_index is not None:
    if self._current_test_index < len(self._tests):
        current_test = self._tests[self._current_test_index]
        is_your_test = current_test.get('type') == 'Your New Test Type'

# Add new data point
if x_value is not None and y_value is not None:
    if is_your_test:
        # Initialize plot if not already done (fallback)
        if not hasattr(self, '_your_test_plot_initialized') or not self._your_test_plot_initialized:
            self._initialize_your_test_plot(test_name)
        
        # Store data points
        if not hasattr(self, 'plot_x_values'):
            self.plot_x_values = []
        if not hasattr(self, 'plot_y_values'):
            self.plot_y_values = []
        
        self.plot_x_values.append(x_value)
        self.plot_y_values.append(y_value)
        
        # Update plot
        self.plot_line.set_data(self.plot_x_values, self.plot_y_values)
        self.plot_axes.relim()
        self.plot_axes.autoscale()
        self.plot_canvas.draw_idle()
```

**Reference Implementation:** Search for `Output Current Calibration` in `_update_plot()` method for a complete example.

### Step 11: Add HTML/PDF Export Support (If Using Plots)

**File:** `host_gui/base_gui.py`

#### 11.1 Create Plot Image Generation Functions

Add functions to generate plot images for export:

```python
def _generate_your_test_plot_image(self, test_name: str, x_values: list, 
                                   y_values: list, output_format: str = 'png') -> Optional[bytes]:
    """Generate a plot image for export.
    
    Args:
        test_name: Name of the test
        x_values: List of X-axis values
        y_values: List of Y-axis values
        output_format: Image format ('png', 'svg', etc.)
        
    Returns:
        Image bytes if successful, None otherwise
    """
    if not matplotlib_available:
        return None
    
    # Filter out NaN values
    x_clean = []
    y_clean = []
    if x_values and y_values:
        min_len = min(len(x_values), len(y_values))
        for i in range(min_len):
            x_val = x_values[i]
            y_val = y_values[i]
            if (isinstance(x_val, (int, float)) and isinstance(y_val, (int, float)) and
                not (isinstance(x_val, float) and x_val != x_val) and
                not (isinstance(y_val, float) and y_val != y_val)):
                x_clean.append(x_val)
                y_clean.append(y_val)
    
    if not (x_clean and y_clean):
        return None
    
    try:
        import io
        from matplotlib.figure import Figure
        
        fig = Figure(figsize=(8, 6))
        ax = fig.add_subplot(111)
        
        ax.plot(x_clean, y_clean, 'bo', markersize=6, label='Data Points')
        ax.set_xlabel('X-Axis Label')
        ax.set_ylabel('Y-Axis Label')
        ax.set_title(f'Your Plot Title: {test_name}')
        ax.grid(True, alpha=0.3)
        ax.legend()
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
        logger.error(f"Error generating plot image: {e}", exc_info=True)
        return None

def _generate_your_test_plot_base64(self, test_name: str, x_values: list,
                                    y_values: list) -> Optional[str]:
    """Generate a base64-encoded plot image for HTML embedding.
    
    Args:
        test_name: Name of the test
        x_values: List of X-axis values
        y_values: List of Y-axis values
        
    Returns:
        Base64-encoded image string if successful, None otherwise
    """
    image_bytes = self._generate_your_test_plot_image(test_name, x_values, y_values, 'png')
    if image_bytes:
        return base64.b64encode(image_bytes).decode('utf-8')
    return None
```

#### 11.2 Add to HTML Export

In `_export_report_html()` method (around line 5341 in `base_gui.py`), add a section for your test type:

```python
# Your New Test Type test results
elif test_type == 'Your New Test Type' or (test_config and test_config.get('type') == 'Your New Test Type'):
    plot_data = exec_data.get('plot_data')
    if plot_data:
        # Add results table
        result1 = plot_data.get('result1')
        result2 = plot_data.get('result2')
        if result1 is not None or result2 is not None:
            html_parts.append('<h3>Results</h3>')
            html_parts.append('<table class="calibration-table">')
            html_parts.append('<tr><th>Parameter</th><th>Value</th></tr>')
            if result1 is not None:
                html_parts.append(f'<tr><td>Result 1</td><td>{result1:.6f}</td></tr>')
            if result2 is not None:
                html_parts.append(f'<tr><td>Result 2</td><td>{result2:.6f}</td></tr>')
            html_parts.append('</table>')
        
        # Add plot image
        x_values = plot_data.get('x_values', [])
        y_values = plot_data.get('y_values', [])
        if x_values and y_values:
            plot_base64 = self._generate_your_test_plot_base64(test_name, x_values, y_values)
            if plot_base64:
                html_parts.append('<h3>Plot: Your Plot Title</h3>')
                html_parts.append(f'<img src="data:image/png;base64,{plot_base64}" alt="Plot for {test_name}" class="plot-image">')
```

**Reference Implementation:** Search for `Output Current Calibration` in `_export_report_html()` method for a complete example.

#### 11.3 Add to PDF Export (Optional)

In `_export_report_pdf()` method (around line 5773), add similar logic for PDF export if needed. **Important:** When adding plots to PDF, wrap the plot title, spacer, and image in a `KeepTogether` flowable to prevent page breaks between the title and plot.

Example implementation:

```python
# Your New Test Type test results
elif test_type == 'Your New Test Type' or (test_config and test_config.get('type') == 'Your New Test Type'):
    plot_data = exec_data.get('plot_data')
    if plot_data:
        x_values = plot_data.get('x_values', [])
        y_values = plot_data.get('y_values', [])
        
        if x_values and y_values:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                tmp_path = tmp_file.name
            
            plot_bytes = self._generate_your_test_plot_image(test_name, x_values, y_values, 'png')
            if plot_bytes:
                with open(tmp_path, 'wb') as f:
                    f.write(plot_bytes)
                
                # IMPORTANT: Use KeepTogether to keep title and plot on same page
                from reportlab.platypus import KeepTogether
                plot_block = [
                    Spacer(1, 0.1*inch),
                    Paragraph('<b>Plot: Your Plot Title</b>', styles['Heading3']),
                    Image(tmp_path, width=5*inch, height=3*inch)
                ]
                story.append(KeepTogether(plot_block))
                
                # Track temp file for cleanup after PDF is built
                temp_files.append(tmp_path)
```

**Reference Implementation:** Search for `Analog Tests`, `Phase Current Test`, or `Output Current Calibration` in `_export_report_pdf()` method for complete examples with `KeepTogether` usage.

### Step 12: Handle Multiplexed Signals (If Needed)

**File:** `host_gui/test_runner.py`

If your test type uses CAN messages with multiplexed signals (signals that require a `MessageType` multiplexor), you need to handle this in your test execution:

#### 12.1 Finding Multiplexor Values

When encoding CAN messages, check if signals are multiplexed and extract the multiplexor value:

```python
# Find message
msg = self.dbc_service.find_message_by_id(message_id)
if msg is None:
    return False, f"Message (ID: 0x{message_id:X}) not found in DBC"

# Build signal values dict - include required signals (DeviceID, MessageType) if they exist
signal_values = {}

# Check for DeviceID signal (common requirement)
for sig in msg.signals:
    if sig.name == 'DeviceID':
        signal_values['DeviceID'] = 0  # Default value, adjust as needed
        break

# Check for MessageType signal (multiplexor)
message_type_value = None
for sig in msg.signals:
    if sig.name == 'MessageType':
        # Check if your target signal is multiplexed
        target_signal = None
        for s in msg.signals:
            if s.name == your_signal_name:
                target_signal = s
                break
        
        if target_signal and hasattr(target_signal, 'multiplexer_ids') and target_signal.multiplexer_ids:
            # Signal is multiplexed, use the multiplexor ID
            message_type_value = target_signal.multiplexer_ids[0]
        else:
            # Signal is not multiplexed, but MessageType exists - use default 0
            message_type_value = 0
        
        signal_values['MessageType'] = message_type_value
        break

# Add your signal value
signal_values[your_signal_name] = your_signal_value

# Encode and send
frame_data = self.dbc_service.encode_message(msg, signal_values)
frame = AdapterFrame(can_id=message_id, data=frame_data)
self.can_service.send_frame(frame)
```

**Reference Implementation:** Search for `Output Current Calibration` and `MessageType` in `test_runner.py` for complete multiplexor handling.

#### 12.2 Common Pattern for Multiple Messages

If you need to send multiple messages with the same multiplexor logic:

```python
def _get_message_type_for_signal(msg, signal_name):
    """Helper to get MessageType value for a signal."""
    for sig in msg.signals:
        if sig.name == signal_name:
            if hasattr(sig, 'multiplexer_ids') and sig.multiplexer_ids:
                return sig.multiplexer_ids[0]
    return None

# Use for different messages
trigger_msg = self.dbc_service.find_message_by_id(trigger_msg_id)
trigger_msg_type = _get_message_type_for_signal(trigger_msg, test_trigger_signal)

setpoint_msg = self.dbc_service.find_message_by_id(setpoint_msg_id)
setpoint_msg_type = _get_message_type_for_signal(setpoint_msg, current_setpoint_signal)
```

### Step 13: Oscilloscope Integration (If Needed)

**File:** `host_gui/test_runner.py`

If your test type requires oscilloscope integration, follow this pattern:

#### 13.1 Verify Oscilloscope Setup

```python
# Check oscilloscope service availability
if self.oscilloscope_service is None or not self.oscilloscope_service.is_connected():
    return False, "Oscilloscope not connected. Please connect oscilloscope before running test."

# Get oscilloscope configuration
osc_config = None
if self.gui is not None and hasattr(self.gui, '_oscilloscope_config'):
    osc_config = self.gui._oscilloscope_config
else:
    return False, "Oscilloscope configuration not available. Please configure oscilloscope first."

# Get channel number from channel name
channel_num = self.oscilloscope_service.get_channel_number_from_name(channel_name, osc_config)
if channel_num is None:
    return False, f"Channel '{channel_name}' not found in oscilloscope configuration or not enabled"
```

#### 13.2 Configure Oscilloscope

```python
# Set timebase
self.oscilloscope_service.send_command(f"TDIV {timebase}")
time.sleep(0.2)

# Verify timebase
tdiv_response = self.oscilloscope_service.send_command("TDIV?")
if tdiv_response is None:
    return False, "Failed to verify oscilloscope timebase"

# Enable channel
tra_response = self.oscilloscope_service.send_command(f"C{channel_num}:TRA?")
tra_str = tra_response.strip().upper()
is_on = 'ON' in tra_str or tra_str == '1' or 'TRUE' in tra_str

if not is_on:
    self.oscilloscope_service.send_command(f"C{channel_num}:TRA ON")
    time.sleep(0.2)
    # Verify it's now ON
    tra_response = self.oscilloscope_service.send_command(f"C{channel_num}:TRA?")
    # ... verify ...
```

#### 13.3 Acquire Data from Oscilloscope

```python
# Start acquisition
self.oscilloscope_service.send_command("TRMD AUTO")
time.sleep(0.1)

# Collect data during acquisition time
# ... collect CAN data in parallel ...

# Stop acquisition
self.oscilloscope_service.send_command("STOP")

# Query oscilloscope for average
osc_response = self.oscilloscope_service.send_command(f"C{channel_num}:PAVA? MEAN")
if osc_response:
    try:
        # Parse response (format may vary)
        osc_value = float(osc_response.strip())
    except ValueError:
        logger.warning(f"Could not parse oscilloscope response: {osc_response}")
        osc_value = None
else:
    osc_value = None
```

**Reference Implementation:** Search for `Output Current Calibration` and oscilloscope usage in `test_runner.py` for complete oscilloscope integration.

### Step 14: Data Analysis and Calculations (If Needed)

**File:** `host_gui/test_runner.py`

If your test type requires data analysis (e.g., linear regression, statistics), implement it in your test execution:

#### 14.1 Linear Regression Example

```python
# Collect data points
x_values = []  # e.g., oscilloscope measurements
y_values = []  # e.g., CAN measurements

# ... collect data during test execution ...

# Perform linear regression
try:
    import numpy as np
    # Fit polynomial of degree 1 (linear)
    coeffs = np.polyfit(x_values, y_values, 1)
    slope = coeffs[0]
    intercept = coeffs[1]
except ImportError:
    # Fallback: manual calculation if numpy not available
    n = len(x_values)
    if n > 0:
        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values))
        sum_x2 = sum(x * x for x in x_values)
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x) if (n * sum_x2 - sum_x * sum_x) != 0 else 0
        intercept = (sum_y - slope * sum_x) / n if n > 0 else 0

# Calculate gain error
expected_slope = 1.0  # Ideal slope
gain_error = ((slope - expected_slope) / expected_slope) * 100.0  # Percentage

# Calculate adjustment factor
adjustment_factor = expected_slope / slope if abs(slope) > 1e-10 else 0.0

# Determine pass/fail
passed = abs(gain_error) <= tolerance_percent
```

**Reference Implementation:** Search for `Output Current Calibration` and linear regression in `test_runner.py` for complete linear regression implementation.

#### 14.2 Store Analysis Results

Store calculated results for report generation:

```python
# Store plot data
if self.gui is not None:
    if not hasattr(self.gui, '_test_plot_data_temp'):
        self.gui._test_plot_data_temp = {}
    self.gui._test_plot_data_temp[test_name] = {
        'x_values': x_values,
        'y_values': y_values,
        'slope': slope,
        'intercept': intercept,
        'gain_error': gain_error,
        'adjustment_factor': adjustment_factor,
        'tolerance_percent': tolerance_percent
    }
    
    # Store result data
    if not hasattr(self.gui, '_test_result_data_temp'):
        self.gui._test_result_data_temp = {}
    self.gui._test_result_data_temp[test_name] = {
        'slope': slope,
        'intercept': intercept,
        'gain_error': gain_error,
        'adjustment_factor': adjustment_factor
    }
```

### Step 15: Testing Checklist

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
- [ ] Plot initialization works (if using live plots)
- [ ] Plot updates correctly during test execution (if using live plots)
- [ ] Plot appears in test report tree view (if using plots)
- [ ] Plot appears in test details popup (if using plots)
- [ ] Plot appears in HTML export (if using plots)
- [ ] Plot appears in PDF export (if using plots)
- [ ] Multiplexed signals handled correctly (if applicable)
- [ ] Oscilloscope integration works (if applicable)
- [ ] Data analysis calculations are correct (if applicable)

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

### Pattern 4: Oscilloscope + CAN Data Collection Test

For tests that collect data from both oscilloscope and CAN (like Output Current Calibration):

```python
# 1. Verify oscilloscope setup
if not self.oscilloscope_service.is_connected():
    return False, "Oscilloscope not connected"

# Get channel number
channel_num = self.oscilloscope_service.get_channel_number_from_name(channel_name, osc_config)

# Set timebase and enable channel
self.oscilloscope_service.send_command(f"TDIV {timebase}")
self.oscilloscope_service.send_command(f"C{channel_num}:TRA ON")

# 2. Send test trigger
# ... send CAN message to enable test mode ...

# 3. Loop through setpoints
for setpoint in setpoints:
    # Send setpoint via CAN
    # ... send CAN message with setpoint value ...
    
    # Wait for stabilization
    _nb_sleep(pre_acquisition_time_ms / 1000.0)
    
    # Start data collection
    self.oscilloscope_service.send_command("TRMD AUTO")
    
    # Collect CAN data
    can_values = []
    end_time = time.time() + (acquisition_time_ms / 1000.0)
    while time.time() < end_time:
        if self.signal_service is not None:
            _, val = self.signal_service.get_latest_signal(feedback_msg_id, feedback_signal)
            if val is not None:
                can_values.append(float(val))
        _nb_sleep(SLEEP_INTERVAL_SHORT)
    
    # Stop oscilloscope
    self.oscilloscope_service.send_command("STOP")
    
    # Get oscilloscope average
    osc_response = self.oscilloscope_service.send_command(f"C{channel_num}:PAVA? MEAN")
    osc_value = float(osc_response.strip()) if osc_response else None
    
    # Calculate averages
    can_avg = sum(can_values) / len(can_values) if can_values else None
    
    # Store for later analysis
    osc_averages.append(osc_value)
    can_averages.append(can_avg)
    
    # Update live plot
    if self.plot_update_callback is not None:
        self.plot_update_callback(osc_value, can_avg, test_name)

# 4. Disable test mode
# ... send CAN message to disable test mode ...

# 5. Perform analysis (e.g., linear regression)
# ... calculate slope, intercept, gain error, etc. ...

# 6. Store results for reports
if self.gui is not None:
    self.gui._test_plot_data_temp[test_name] = {
        'osc_averages': osc_averages,
        'can_averages': can_averages,
        'slope': slope,
        'intercept': intercept,
        'gain_error': gain_error,
        'adjustment_factor': adjustment_factor
    }
```

**Reference Implementation:** Search for `Output Current Calibration` in `test_runner.py` for complete implementation.

### Pattern 5: Test with Multiplexed CAN Signals

For tests that use multiplexed signals (signals requiring MessageType):

```python
# Find message
msg = self.dbc_service.find_message_by_id(message_id)

# Build signal values - include DeviceID and MessageType if they exist
signal_values = {}

# Add DeviceID if present
for sig in msg.signals:
    if sig.name == 'DeviceID':
        signal_values['DeviceID'] = 0  # or appropriate value
        break

# Add MessageType if signal is multiplexed
target_signal = None
for sig in msg.signals:
    if sig.name == your_signal_name:
        target_signal = sig
        break

if target_signal and hasattr(target_signal, 'multiplexer_ids') and target_signal.multiplexer_ids:
    # Signal is multiplexed - use multiplexor ID
    message_type_value = target_signal.multiplexer_ids[0]
    signal_values['MessageType'] = message_type_value
elif any(s.name == 'MessageType' for s in msg.signals):
    # MessageType exists but signal not multiplexed - use default 0
    signal_values['MessageType'] = 0

# Add your signal value
signal_values[your_signal_name] = your_signal_value

# Encode and send
frame_data = self.dbc_service.encode_message(msg, signal_values)
frame = AdapterFrame(can_id=message_id, data=frame_data)
self.can_service.send_frame(frame)
```

**Reference Implementation:** Search for `Output Current Calibration` and `MessageType` in `test_runner.py` for complete multiplexor handling.

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

8. **Result Storage**: Store detailed results in `self.gui._test_result_data_temp[test_name]` and plot data in `self.gui._test_plot_data_temp[test_name]` for later retrieval in report generation.

9. **Multiplexed Signals**: When encoding CAN messages, always check if signals are multiplexed and include `MessageType` and `DeviceID` if they exist in the message. See Pattern 5 for details.

10. **Oscilloscope Integration**: When using oscilloscope, always verify connection and configuration before starting. Use proper SCPI commands and handle response parsing errors gracefully.

11. **Plot Initialization**: For tests with live plots, initialize plot labels and title before test starts using a dedicated initialization method. This ensures the plot is ready before data collection begins.

12. **Data Analysis**: If your test performs calculations (regression, statistics), store both raw data and calculated results for report generation.

## File Locations Summary

| Component | File | Key Methods/Functions |
|-----------|------|---------------------|
| Schema | `backend/data/tests/schema.json` | `type.enum`, `actuation.oneOf` |
| Data Model | `host_gui/models/test_profile.py` | `ActuationConfig` class |
| Create Dialog | `host_gui/base_gui.py` | `_on_create_test()` |
| Edit Dialog | `host_gui/base_gui.py` | `_on_edit_test()` |
| Validation | `host_gui/base_gui.py` | `_validate_test()` |
| Execution | `host_gui/test_runner.py` | `run_single_test()` |
| Service Execution | `host_gui/services/test_execution_service.py` | `run_single_test()` |
| Plot Initialization | `host_gui/base_gui.py` | `_initialize_<test_type>_plot()` |
| Plot Updates | `host_gui/base_gui.py` | `_update_plot()` |
| Reports (Tree) | `host_gui/base_gui.py` | `_refresh_test_report()` |
| Reports (Popup) | `host_gui/base_gui.py` | `_show_test_details_popup()` |
| HTML Export | `host_gui/base_gui.py` | `_export_report_html()`, `_generate_<test_type>_plot_base64()` |
| PDF Export | `host_gui/base_gui.py` | `_export_report_pdf()` |

## Conclusion

Adding a new test type requires coordinated changes across multiple files. Follow this guide systematically, and ensure all components are updated consistently. Test thoroughly with both DBC-loaded and non-DBC scenarios to ensure robustness.

