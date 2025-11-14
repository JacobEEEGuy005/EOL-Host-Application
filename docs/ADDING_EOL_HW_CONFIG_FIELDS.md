# Adding Fields to EOL H/W Configuration

## Overview

This document provides a guide for adding new fields to the EOL (End of Line) Hardware Configuration system. The EOL H/W Configuration allows users to configure how the application interfaces with EOL test hardware, including mapping DBC messages and signals to hardware feedback channels.

## Current Configuration Structure

### Existing Fields

The current EOL H/W Configuration JSON structure includes the following fields:

| Field Name | Type | Description | Required | Example |
|------------|------|-------------|----------|---------|
| `name` | `string` | Unique name for the configuration | Yes | `"EOL_HW_V1.0"` |
| `feedback_message_id` | `integer` | CAN message ID for EOL hardware feedback (hex format) | Yes | `256` (0x100) |
| `feedback_message_name` | `string` | DBC message name for feedback | Yes | `"Status_Data"` |
| `measured_dac_signal` | `string` | DBC signal name for measured DAC voltage | Yes | `"ADC_A1_mV"` |
| `created_at` | `string` | ISO 8601 timestamp of creation | Auto | `"2025-11-03T14:14:48.368097Z"` |
| `updated_at` | `string` | ISO 8601 timestamp of last update | Auto | `"2025-11-03T14:14:58.917704Z"` |

### Current Configuration Example

```json
{
  "name": "EOL_HW_V1.0",
  "feedback_message_id": 256,
  "feedback_message_name": "Status_Data",
  "measured_dac_signal": "ADC_A1_mV",
  "created_at": "2025-11-03T14:14:48.368097Z",
  "updated_at": "2025-11-03T14:14:58.917704Z"
}
```

## Available Signals in Status_Data Message

Based on the DBC file (`eol_firmware.dbc`), the `Status_Data` message (ID: 0x100) contains the following signals that could potentially be added as configuration fields:

| Signal Name | Description | Units | Range |
|-------------|-------------|-------|-------|
| `ADC_A0_mV` | ADC channel A0 reading | mV | 0-65535 |
| `ADC_A1_mV` | ADC channel A1 reading | mV | 0-65535 |
| `ADC_A2_mV` | ADC channel A2 reading | mV | 0-65535 |
| `ADC_A3_mV` | ADC channel A3 reading | mV | 0-65535 |
| `DAC_Voltage_mV` | Current DAC output voltage | mV | 0-5000 |
| `Relay_State` | Relay state bitmap | - | 0-15 |
| `MUX_Channel` | Currently selected MUX channel | - | 0-7 |
| `MUX_Enabled` | MUX enable state | - | 0-1 |
| `I2C_DeviceCount` | Number of I2C devices found | - | 0-16 |
| `I2C_Addr1-5` | I2C device addresses | - | 0-255 |
| `HardwareStatus` | Hardware status flags | - | 0-255 |
| `Heartbeat_Counter` | Heartbeat counter | - | 0-65535 |

## Adding New Fields - Step by Step

### Step 1: Define the New Field

First, determine what field you want to add. Consider:

- **Field Purpose**: What hardware signal or configuration does this field represent?
- **Field Type**: String, integer, float, boolean, or object?
- **Field Source**: Is it from DBC (message/signal), or a manual configuration value?
- **Field Validation**: What are the valid ranges or formats?
- **Field Required**: Is this field required or optional?

### Step 2: Update the Configuration Dictionary Structure

**File**: `host_gui/base_gui.py`

**Location**: `_build_eol_hw_configurator()` method (around line 473)

Update the default configuration dictionary to include your new field:

```python
# Store current configuration
self._eol_hw_config = {
    'name': None,
    'feedback_message_id': None,
    'feedback_message_name': None,
    'measured_dac_signal': None,
    'new_field_name': None,  # Add your new field here
    'created_at': None,
    'updated_at': None
}
```

**Also update**: The initialization in `__init__` method (around line 738) if it exists.

### Step 3: Update the Create Dialog

**File**: `host_gui/base_gui.py`

**Location**: `_on_create_eol_config()` method (around line 4589)

Add UI elements for your new field in the create dialog. The pattern depends on field type:

#### For DBC Signal Selection (Dropdown):

```python
# Add after existing signal selection
new_sig_label = QtWidgets.QLabel('<b>New Signal Name:</b>')
layout.addWidget(new_sig_label)
new_sig_combo = QtWidgets.QComboBox()
new_sig_combo.setEnabled(False)
layout.addWidget(new_sig_combo)

# Update the on_message_changed function to populate this combo
def on_message_changed(index):
    # ... existing code ...
    
    # Populate new signal combo
    new_sig_combo.clear()
    new_sig_combo.addItem('-- Select Signal --', None)
    for sig in signals:
        sig_name = getattr(sig, 'name', '')
        new_sig_combo.addItem(sig_name, sig)
```

#### For Text Input:

```python
# Add after existing fields
new_field_layout = QtWidgets.QHBoxLayout()
new_field_layout.addWidget(QtWidgets.QLabel('New Field Label:'))
new_field_edit = QtWidgets.QLineEdit()
new_field_edit.setPlaceholderText('Enter value...')
new_field_layout.addWidget(new_field_edit)
layout.addLayout(new_field_layout)
```

#### For Integer/Number Input:

```python
# Add after existing fields
new_field_layout = QtWidgets.QHBoxLayout()
new_field_layout.addWidget(QtWidgets.QLabel('New Field Label:'))
new_field_spin = QtWidgets.QSpinBox()  # or QDoubleSpinBox for floats
new_field_spin.setRange(0, 65535)  # Set appropriate range
new_field_spin.setValue(0)  # Set default value
new_field_layout.addWidget(new_field_spin)
layout.addLayout(new_field_layout)
```

#### Update the Save Handler:

In the `on_save()` function within `_on_create_eol_config()`, add your field to the configuration dictionary:

```python
def on_save():
    # ... existing validation ...
    
    # Save configuration
    self._eol_hw_config = {
        'name': config_name,
        'feedback_message_id': getattr(msg, 'frame_id', 0),
        'feedback_message_name': getattr(msg, 'name', ''),
        'measured_dac_signal': getattr(sig, 'name', ''),
        'new_field_name': new_field_value,  # Add your field here
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'updated_at': datetime.utcnow().isoformat() + 'Z'
    }
    
    # ... rest of save logic ...
```

### Step 4: Update the Edit Dialog

**File**: `host_gui/base_gui.py`

**Location**: `_on_edit_eol_config()` method (around line 4751)

Add the same UI elements as in Step 3, but pre-populate them with existing values:

```python
# For text input
new_field_edit.setText(self._eol_hw_config.get('new_field_name', ''))

# For combo box - set current selection based on existing value
current_new_field_value = self._eol_hw_config.get('new_field_name')
# ... find matching index and set it ...

# For spin box
new_field_spin.setValue(self._eol_hw_config.get('new_field_name', 0))
```

Update the save handler in `_on_edit_eol_config()`:

```python
self._eol_hw_config.update({
    'name': config_name,
    'feedback_message_id': getattr(msg, 'frame_id', 0),
    'feedback_message_name': getattr(msg, 'name', ''),
    'measured_dac_signal': getattr(sig, 'name', ''),
    'new_field_name': new_field_value,  # Add your field here
    'updated_at': datetime.utcnow().isoformat() + 'Z'
})
```

### Step 5: Update the Display

**File**: `host_gui/base_gui.py`

**Location**: `_update_eol_config_display()` method (around line 5056)

Add a label to display your new field in the configuration display area:

```python
def _update_eol_config_display(self):
    """Update the display labels for current EOL configuration."""
    if not hasattr(self, 'eol_config_name_label'):
        return
    
    config = self._eol_hw_config
    
    # ... existing display code ...
    
    # Add display for new field
    new_field_value = config.get('new_field_name')
    if new_field_value:
        self.eol_new_field_label.setText(str(new_field_value))
        self.eol_new_field_label.setStyleSheet('')
    else:
        self.eol_new_field_label.setText('Not configured')
        self.eol_new_field_label.setStyleSheet('color: gray; font-style: italic;')
```

**Also update**: `_build_eol_hw_configurator()` method to add the label widget:

```python
# In the config_group section (around line 444)
self.eol_new_field_label = QtWidgets.QLabel('Not configured')
self.eol_new_field_label.setStyleSheet('color: gray; font-style: italic;')

config_layout.addRow('New Field Label:', self.eol_new_field_label)
```

### Step 6: Update Configuration Usage

If your new field is used by test execution or other parts of the application, update those locations:

**Files to check**:
- `host_gui/test_runner.py` - Test execution logic
- `host_gui/services/test_execution_service.py` - Test execution service
- Any test type implementations that use EOL configuration

**Example**: If adding a new ADC channel signal:

```python
# In test_runner.py or test_execution_service.py
if self.eol_hw_config and self.eol_hw_config.get('feedback_message_id'):
    eol_msg_id = self.eol_hw_config['feedback_message_id']
    new_signal_name = self.eol_hw_config.get('new_field_name')
    if new_signal_name:
        # Use the new signal
        new_signal_value = self._read_signal(eol_msg_id, new_signal_name)
```

### Step 7: Update JSON Schema (Optional but Recommended)

**File**: Create or update schema file (e.g., `backend/data/eol_configs/schema.json`)

If you want to validate EOL configuration JSON files, create or update a JSON schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "Configuration name"
    },
    "feedback_message_id": {
      "type": "integer",
      "minimum": 0,
      "maximum": 2147483647
    },
    "feedback_message_name": {
      "type": "string"
    },
    "measured_dac_signal": {
      "type": "string"
    },
    "new_field_name": {
      "type": "string",
      "description": "Description of new field"
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time"
    }
  },
  "required": ["name", "feedback_message_id", "feedback_message_name", "measured_dac_signal"]
}
```

### Step 8: Update Documentation

Update this document and any other relevant documentation to reflect the new field.

## Example: Adding an Additional ADC Channel Field

Let's walk through a complete example of adding a new field `additional_adc_signal` that allows users to configure a second ADC channel for monitoring.

### Step 1: Define the Field

- **Field Name**: `additional_adc_signal`
- **Type**: `string` (DBC signal name)
- **Purpose**: Configure an additional ADC channel signal for monitoring
- **Source**: DBC signal selection
- **Required**: No (optional field)

### Step 2: Update Configuration Dictionary

```python
# In _build_eol_hw_configurator()
self._eol_hw_config = {
    'name': None,
    'feedback_message_id': None,
    'feedback_message_name': None,
    'measured_dac_signal': None,
    'additional_adc_signal': None,  # New field
    'created_at': None,
    'updated_at': None
}
```

### Step 3: Update Create Dialog

```python
# In _on_create_eol_config(), after measured_dac_signal selection

# Additional ADC Signal selection
additional_adc_label = QtWidgets.QLabel('<b>Additional ADC Signal (Optional):</b>')
layout.addWidget(additional_adc_label)
additional_adc_combo = QtWidgets.QComboBox()
additional_adc_combo.setEnabled(False)
layout.addWidget(additional_adc_combo)

# Update on_message_changed to populate additional ADC combo
def on_message_changed(index):
    # ... existing code for measured_dac_signal ...
    
    # Populate additional ADC signal combo
    additional_adc_combo.clear()
    additional_adc_combo.addItem('-- None (Optional) --', None)
    for sig in signals:
        sig_name = getattr(sig, 'name', '')
        if 'ADC' in sig_name:  # Filter to ADC signals only
            additional_adc_combo.addItem(sig_name, sig)

# Update on_save()
def on_save():
    # ... existing validation ...
    
    additional_adc_sig = additional_adc_combo.currentData()
    
    self._eol_hw_config = {
        'name': config_name,
        'feedback_message_id': getattr(msg, 'frame_id', 0),
        'feedback_message_name': getattr(msg, 'name', ''),
        'measured_dac_signal': getattr(sig, 'name', ''),
        'additional_adc_signal': getattr(additional_adc_sig, 'name', '') if additional_adc_sig else None,
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'updated_at': datetime.utcnow().isoformat() + 'Z'
    }
```

### Step 4: Update Edit Dialog

Similar changes to `_on_edit_eol_config()`, with pre-population:

```python
# Pre-populate the combo
current_additional_adc = self._eol_hw_config.get('additional_adc_signal')
# ... find and set matching index ...
```

### Step 5: Update Display

```python
# In _build_eol_hw_configurator()
self.eol_additional_adc_label = QtWidgets.QLabel('Not configured')
self.eol_additional_adc_label.setStyleSheet('color: gray; font-style: italic;')
config_layout.addRow('Additional ADC Signal:', self.eol_additional_adc_label)

# In _update_eol_config_display()
additional_adc = config.get('additional_adc_signal')
if additional_adc:
    self.eol_additional_adc_label.setText(additional_adc)
    self.eol_additional_adc_label.setStyleSheet('')
else:
    self.eol_additional_adc_label.setText('Not configured')
    self.eol_additional_adc_label.setStyleSheet('color: gray; font-style: italic;')
```

### Step 6: Use in Test Execution (if needed)

```python
# In test_runner.py
if self.eol_hw_config and self.eol_hw_config.get('feedback_message_id'):
    eol_msg_id = self.eol_hw_config['feedback_message_id']
    additional_adc_signal = self.eol_hw_config.get('additional_adc_signal')
    if additional_adc_signal:
        additional_adc_value = self._read_signal(eol_msg_id, additional_adc_signal)
        logger.debug(f"Additional ADC reading: {additional_adc_value}")
```

## Validation Rules

When adding new fields, consider implementing validation:

### For DBC Signal Fields:
- Signal must exist in the selected message
- Signal must be readable (not write-only)

### For Integer Fields:
- Range validation (min/max)
- Type checking

### For String Fields:
- Non-empty validation (if required)
- Format validation (if applicable)

### Example Validation:

```python
def _validate_eol_config(self, config: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate EOL hardware configuration."""
    # Existing validations...
    
    # Validate new field
    new_field_value = config.get('new_field_name')
    if new_field_value is not None:
        if not isinstance(new_field_value, str):
            return False, "new_field_name must be a string"
        if len(new_field_value.strip()) == 0:
            return False, "new_field_name cannot be empty"
    
    return True, ""
```

## Testing Checklist

After adding a new field, test the following:

- [ ] Create new configuration with the field populated
- [ ] Create new configuration with the field empty/None (if optional)
- [ ] Edit existing configuration and update the field
- [ ] Edit existing configuration and clear the field (if optional)
- [ ] Load existing configuration file (backward compatibility)
- [ ] Save configuration and verify JSON structure
- [ ] Display shows the field correctly
- [ ] Field is used correctly in test execution (if applicable)
- [ ] Validation works for invalid values
- [ ] Error handling for missing DBC (if field depends on DBC)

## Backward Compatibility

When adding new fields:

1. **Make new fields optional** when possible to maintain backward compatibility
2. **Provide default values** in code when field is missing
3. **Handle None/empty values** gracefully
4. **Update existing configs** only when user edits them (don't auto-update)

Example of backward-compatible code:

```python
# Always check if field exists before using
new_field_value = self.eol_hw_config.get('new_field_name')
if new_field_value:
    # Use the field
    pass
else:
    # Use default or skip
    pass
```

## File Summary

Files that typically need updates when adding EOL H/W Configuration fields:

| File | Purpose | Update Required |
|------|---------|----------------|
| `host_gui/base_gui.py` | GUI implementation | Yes - Multiple methods |
| `host_gui/test_runner.py` | Test execution | Maybe - If field is used in tests |
| `host_gui/services/test_execution_service.py` | Test service | Maybe - If field is used in tests |
| `backend/data/eol_configs/*.json` | Example configs | Optional - Add example |
| `backend/data/eol_configs/schema.json` | JSON schema | Optional - For validation |
| `docs/ADDING_EOL_HW_CONFIG_FIELDS.md` | This document | Yes - Update examples |

## Common Patterns

### Pattern 1: DBC Signal Selection Field

Use when the field represents a DBC signal from a message.

**UI**: QComboBox populated from DBC signals
**Storage**: String (signal name)
**Validation**: Signal must exist in selected message

### Pattern 2: Manual Configuration Field

Use when the field is a user-entered value (not from DBC).

**UI**: QLineEdit, QSpinBox, QDoubleSpinBox, or QCheckBox
**Storage**: String, int, float, or bool
**Validation**: Type and range validation

### Pattern 3: Optional Field with Default

Use when the field is optional but has a sensible default.

**UI**: Include "None" or "Default" option
**Storage**: Value or None
**Usage**: Check for None and use default in code

## Troubleshooting

### Issue: Field not saving

**Check**:
- Field is added to `self._eol_hw_config` dictionary in save handler
- Field value is correctly extracted from UI widget
- No validation errors preventing save

### Issue: Field not displaying

**Check**:
- Label widget created in `_build_eol_hw_configurator()`
- Display update logic in `_update_eol_config_display()`
- Field exists in loaded configuration

### Issue: Field not loading from file

**Check**:
- JSON file contains the field
- Field name matches exactly (case-sensitive)
- No JSON parsing errors

### Issue: Backward compatibility broken

**Check**:
- Code handles missing field gracefully (uses `.get()` with default)
- No required validation on optional fields
- Default values provided when field is None

## Additional Resources

- **DBC File**: `docs/can_specs/eol_firmware.dbc` - Reference for available signals
- **Example Config**: `backend/data/eol_configs/EOL_HW_V1.0.json` - Example configuration
- **GUI Code**: `host_gui/base_gui.py` - Main GUI implementation
- **Test Execution**: `host_gui/test_runner.py` - How EOL config is used in tests

## Questions or Issues?

If you encounter issues or need clarification when adding fields:

1. Review existing field implementations in `base_gui.py`
2. Check the DBC file for available signals
3. Review test execution code to understand how fields are used
4. Test with both DBC loaded and unloaded scenarios
5. Verify backward compatibility with existing configuration files

