# Test Type Addition - Quick Reference Guide

## Files to Modify (In Order)

1. **`backend/data/tests/schema.json`**
   - Add to `type.enum` array
   - Add `oneOf` entry with properties and required fields

2. **`host_gui/models/test_profile.py`**
   - Update `ActuationConfig` docstring
   - Add new fields if needed (most reuse existing)

3. **`host_gui/base_gui.py`**
   - `_on_create_test()`: Add to combo box, create widget, register in stacked widget, build actuation dict
   - `_on_edit_test()`: Same as create, but pre-populate fields
   - `_validate_test()`: Add to allowed types, add type-specific validation

4. **`host_gui/test_runner.py`**
   - `run_test()`: Add `elif` branch with execution logic

5. **`host_gui/services/test_execution_service.py`** (Optional)
   - `run_single_test()`: Add branch
   - Implement `_run_your_test()` method

6. **`host_gui/base_gui.py`** (Reports)
   - `_refresh_test_report()`: Add to type filter
   - `_build_test_report()`: Add display logic if needed

## Test Type Name Consistency

**CRITICAL:** The test type name must match exactly in all files:
- Schema enum
- ComboBox items
- Validation checks
- Execution branches
- Report filters

Example: `"Temperature Validation Test"` (not `"temperature validation test"` or `"TemperatureValidationTest"`)

## Required Components Checklist

- [ ] Schema enum entry
- [ ] Schema oneOf actuation definition
- [ ] Create dialog combo box entry
- [ ] Create dialog widget with fields
- [ ] Create dialog stacked widget registration
- [ ] Create dialog actuation dict building
- [ ] Edit dialog combo box entry
- [ ] Edit dialog widget with fields
- [ ] Edit dialog stacked widget registration
- [ ] Edit dialog actuation dict building
- [ ] Validation: type check
- [ ] Validation: type-specific field validation
- [ ] Execution: test runner branch
- [ ] Execution: service layer (optional)
- [ ] Reports: type filter
- [ ] Reports: display logic (if special)

## Common Field Types

### CAN Message/Signal Selection (DBC Mode)
```python
msg_combo = QtWidgets.QComboBox()
for m, label in msg_display:
    fid = getattr(m, 'frame_id', getattr(m, 'arbitration_id', None))
    msg_combo.addItem(label, fid)

signal_combo = QtWidgets.QComboBox()
def _update_signals(idx=0):
    signal_combo.clear()
    m = messages[idx]
    sigs = [s.name for s in getattr(m, 'signals', [])]
    signal_combo.addItems(sigs)
msg_combo.currentIndexChanged.connect(_update_signals)
```

### Numeric Input with Validator
```python
validator = QtGui.QIntValidator(0, 10000, self)
field_edit = QtWidgets.QLineEdit()
field_edit.setValidator(validator)
```

### Float Input with Validator
```python
validator = QtGui.QDoubleValidator(0.0, 1000.0, 2, self)
validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
field_edit = QtWidgets.QLineEdit()
field_edit.setValidator(validator)
```

## Execution Pattern Template

```python
elif act.get('type') == 'Your New Test Type':
    # 1. Extract parameters
    param1 = act.get('field_1')
    param2 = act.get('field_2')
    
    # 2. Validate parameters
    if not all([param1, param2]):
        return False, "Missing required parameters"
    
    # 3. Implement test logic
    try:
        # Send commands if needed
        # Wait for stabilization
        # Collect data
        # Process data
        # Determine pass/fail
        
        success = True  # or False
        info = "Test details"
        return success, info
    except Exception as e:
        logger.error(f"Test execution failed: {e}", exc_info=True)
        return False, f"Test execution error: {e}"
```

## Validation Pattern Template

```python
elif test_type == 'Your New Test Type':
    # Check required fields
    if actuation.get('required_field') is None:
        return False, "Your New Test Type requires required_field"
    
    # Check field constraints
    if actuation.get('field', 0) < 0:
        return False, "field must be non-negative"
    
    if actuation.get('field', 0) <= 0:
        return False, "field must be positive"
```

## Actuation Dictionary Pattern

```python
act = {
    'type': 'Your New Test Type',
    'field_1': value1,
    'field_2': value2,
    # ... all required and optional fields
}
```

## Helper Functions Available in TestRunner

- `_nb_sleep(sec: float)` - Non-blocking sleep
- `self.signal_service.get_latest_signal(msg_id, signal_name)` - Get signal value
- `self.can_service.send_frame(frame)` - Send CAN frame
- `self.dbc_service.encode_message(msg, signal_values)` - Encode CAN message
- `self.plot_update_callback(x, y, label)` - Update plot
- `self.label_update_callback(text)` - Update label

## Common Mistakes to Avoid

1. ❌ Inconsistent test type name casing/spelling
2. ❌ Missing validation for required fields
3. ❌ Using `time.sleep()` instead of `_nb_sleep()`
4. ❌ Not handling both DBC and non-DBC modes
5. ❌ Missing error handling in execution
6. ❌ Not updating all required files
7. ❌ Forgetting to add to report filters
8. ❌ Not testing with invalid configurations

## Testing Checklist

- [ ] Create test with valid configuration
- [ ] Create test with invalid configuration (should fail validation)
- [ ] Edit existing test
- [ ] Execute test (should run without errors)
- [ ] Verify pass/fail logic works correctly
- [ ] Check results appear in results table
- [ ] Check results appear in test report
- [ ] Test with DBC loaded
- [ ] Test without DBC loaded (if applicable)
- [ ] Verify JSON schema validation works

## Current Test Types

1. Digital Logic Test
2. Analog Sweep Test
3. Phase Current Test
4. Analog Static Test
5. Temperature Validation Test
6. Fan Control Test
7. External 5V Test
8. DC Bus Sensing

## Related Documentation

- Full guide: `docs/ADDING_NEW_TEST_TYPES.md`
- Schema reference: `backend/data/tests/schema.json`
- Test execution: `host_gui/test_runner.py`

