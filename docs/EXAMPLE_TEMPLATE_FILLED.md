# New Test Type Implementation Request - Example

> **Note**: This is a filled-in example of the template. Replace all content with your actual test type details.

## Test Type Information

### Basic Details
- **Test Type Name**: `Voltage Regulation Test`
- **Short Description**: `Tests voltage regulation by applying load and measuring output voltage stability`
- **Detailed Description**: 
  ```
  This test validates that a voltage regulator maintains stable output voltage under varying load conditions.
  The test applies a series of load steps and measures the output voltage at each step. The test passes
  if the voltage remains within specified tolerance at all load points.
  
  Hardware Requirements:
  - Programmable load
  - Voltage measurement equipment
  - CAN communication to device under test
  
  The test sends load commands via CAN and reads voltage feedback signals to verify regulation.
  ```

## Test Configuration Fields

### Required Fields

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `load_command_source` | `integer` | `CAN message ID for load command` | `Range: 0-0x1FFFFFFF, Required` | `0x200` |
| `load_command_signal` | `string` | `Signal name for load command` | `Non-empty, Required` | `"Load_Command"` |
| `voltage_feedback_source` | `integer` | `CAN message ID for voltage feedback` | `Range: 0-0x1FFFFFFF, Required` | `0x201` |
| `voltage_feedback_signal` | `string` | `Signal name for voltage feedback` | `Non-empty, Required` | `"Output_Voltage"` |
| `reference_voltage_v` | `number` | `Expected output voltage in volts` | `Range: 0-50, Required` | `12.0` |
| `tolerance_v` | `number` | `Voltage tolerance in volts` | `Minimum: 0, Required` | `0.1` |
| `load_steps` | `array` | `Array of load values to test` | `Min items: 1, Required` | `[0, 25, 50, 75, 100]` |
| `dwell_time_ms` | `integer` | `Time to wait at each load step` | `Minimum: 1, Required` | `1000` |

### Optional Fields

| Field Name | Type | Description | Validation Rules | Default Value |
|------------|------|-------------|------------------|---------------|
| `pre_dwell_time_ms` | `integer` | `Time to wait before starting test` | `Minimum: 0` | `500` |
| `settling_time_ms` | `integer` | `Time to wait after load change before measurement` | `Minimum: 0` | `200` |

### CAN Message/Signal Fields

- **Command Message** (sending load commands):
  - Message ID: `0x200` (configurable via `load_command_source`)
  - Signals used: `Load_Command` (value: load percentage 0-100)
  - Purpose: `Send load commands to programmable load`

- **Feedback Messages** (reading voltage):
  - Message ID: `0x201` (configurable via `voltage_feedback_source`)
  - Signals used: `Output_Voltage` (value: voltage in volts)
  - Purpose: `Read output voltage from device under test`

- **DBC Support**: `Yes` - Test works with DBC file loaded (dropdowns for messages/signals)
- **Non-DBC Support**: `Yes` - Test works without DBC file (free-text inputs)

## Test Execution Logic

### Execution Flow

```
1. Initialization
   - Action: Wait for pre_dwell_time_ms to allow system stabilization
   - Duration: pre_dwell_time_ms milliseconds
   - Expected result: System is stable and ready

2. For each load step in load_steps:
   a. Apply Load
      - Action: Send CAN message with load_command_signal = load_step value
      - Duration: Immediate
      - Expected result: Load command sent successfully
   
   b. Wait for Settling
      - Action: Wait for settling_time_ms to allow voltage to stabilize
      - Duration: settling_time_ms milliseconds
      - Expected result: Voltage has settled to new value
   
   c. Collect Voltage Data
      - Action: Read voltage_feedback_signal repeatedly during dwell_time_ms
      - Duration: dwell_time_ms milliseconds
      - Expected result: Multiple voltage samples collected
   
   d. Evaluate Step
      - Action: Calculate average voltage, compare to reference_voltage_v ± tolerance_v
      - Duration: Immediate
      - Expected result: Pass/fail determination for this step

3. Final Evaluation
   - Action: All steps must pass for overall test to pass
   - Duration: Immediate
   - Expected result: Overall pass/fail result
```

### Pass/Fail Criteria

- **Pass Condition**: `All load steps have average voltage within reference_voltage_v ± tolerance_v`
- **Fail Condition**: `Any load step has average voltage outside reference_voltage_v ± tolerance_v`
- **Calculation Method**: 
  ```
  For each load step:
    1. Calculate average of collected voltage samples
    2. Calculate difference: |average - reference_voltage_v|
    3. If difference <= tolerance_v: step passes
    4. If difference > tolerance_v: step fails
  
  Overall result: PASS if all steps pass, FAIL if any step fails
  ```

### Data Collection

- **Signals to Monitor**: `Output_Voltage` (from voltage_feedback_source)
- **Collection Duration**: `dwell_time_ms milliseconds per load step`
- **Sampling Rate**: `Approximately every 50ms (SLEEP_INTERVAL_SHORT)`
- **Data Processing**: 
  ```
  1. Collect voltage samples during dwell_time_ms
  2. Calculate average voltage for each load step
  3. Store results for each step (average, min, max, samples count)
  4. Compare each step's average to reference ± tolerance
  ```

### Timing Requirements

- **Pre-Dwell Time**: `pre_dwell_time_ms` (default: 500ms) - System stabilization
- **Settling Time**: `settling_time_ms` (default: 200ms) - Voltage settling after load change
- **Dwell Time**: `dwell_time_ms` (required) - Data collection period per step
- **Total Duration**: `pre_dwell_time_ms + (settling_time_ms + dwell_time_ms) × number_of_load_steps`

## GUI Requirements

### Create/Edit Dialog Fields

#### Field 1: Load Command Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x200)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 2: Load Command Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 3: Voltage Feedback Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x201)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 4: Voltage Feedback Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 5: Reference Voltage
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter reference voltage in volts (e.g., 12.0)`
- **Validator**: `Double 0.0-50.0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 6: Tolerance
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter tolerance in volts (e.g., 0.1)`
- **Validator**: `Double >= 0.0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 7: Load Steps
- **Type**: `QTextEdit` or `QLineEdit` (comma-separated)
- **Placeholder**: `Enter load steps as comma-separated values (e.g., 0,25,50,75,100)`
- **Validator**: `Comma-separated integers 0-100`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 8: Dwell Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter dwell time in milliseconds (e.g., 1000)`
- **Validator**: `Integer >= 1`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 9: Pre-Dwell Time (Optional)
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter pre-dwell time in milliseconds (e.g., 500)`
- **Validator**: `Integer >= 0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `No`

#### Field 10: Settling Time (Optional)
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter settling time in milliseconds (e.g., 200)`
- **Validator**: `Integer >= 0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `No`

### Feedback Fields Visibility
- **Show Feedback Fields**: `No` - This test type has its own feedback fields
- **Custom Feedback Fields**: `Yes` - Uses voltage_feedback_source and voltage_feedback_signal

### Plot Requirements
- **Needs Plot**: `Yes`
- **Plot Type**: `X-Y plot`
- **X-Axis**: `Load step value (0-100%)`
- **Y-Axis**: `Voltage (volts)`
- **Update Frequency**: `After each load step completes`

## Validation Rules

### Schema Validation

```json
{
  "properties": {
    "type": {"const": "Voltage Regulation Test"},
    "load_command_source": {"type": "integer"},
    "load_command_signal": {"type": "string"},
    "voltage_feedback_source": {"type": "integer"},
    "voltage_feedback_signal": {"type": "string"},
    "reference_voltage_v": {"type": "number", "minimum": 0, "maximum": 50},
    "tolerance_v": {"type": "number", "minimum": 0},
    "load_steps": {
      "type": "array",
      "items": {"type": "integer", "minimum": 0, "maximum": 100},
      "minItems": 1
    },
    "dwell_time_ms": {"type": "integer", "minimum": 1},
    "pre_dwell_time_ms": {"type": "integer", "minimum": 0},
    "settling_time_ms": {"type": "integer", "minimum": 0}
  },
  "required": [
    "load_command_source",
    "load_command_signal",
    "voltage_feedback_source",
    "voltage_feedback_signal",
    "reference_voltage_v",
    "tolerance_v",
    "load_steps",
    "dwell_time_ms"
  ]
}
```

### Application Validation

- [x] Test type is in allowed list
- [x] Actuation type matches test type
- [x] `load_command_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `load_command_signal` is present and non-empty
- [x] `voltage_feedback_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `voltage_feedback_signal` is present and non-empty
- [x] `reference_voltage_v` is present and in range (0-50)
- [x] `tolerance_v` is present and non-negative
- [x] `load_steps` is present, is array, has at least 1 item, all values 0-100
- [x] `dwell_time_ms` is present and positive
- [x] `pre_dwell_time_ms` is non-negative (if provided)
- [x] `settling_time_ms` is non-negative (if provided)

## Error Handling

### Expected Error Scenarios

1. **Missing Required Field**
   - Error: `"Missing required field: load_command_source"`
   - Handling: Return `False, "Voltage Regulation Test requires load_command_source (CAN ID)"`

2. **Invalid Load Steps**
   - Error: `"Invalid load_steps: must be array of integers 0-100"`
   - Handling: Return `False, "Load steps must be array of integers between 0 and 100"`

3. **No Voltage Data Collected**
   - Error: `"No voltage data collected at load step X"`
   - Handling: Return `False, "No voltage data collected at load step {step}. Check CAN connection and signal configuration."`

4. **Voltage Out of Tolerance**
   - Error: `"Voltage {voltage}V outside tolerance at load step {step}"`
   - Handling: Return `False, "FAIL: Voltage {voltage:.2f}V at load step {step}% is outside tolerance {reference}±{tolerance}V"`

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "Voltage Regulation Test - Basic",
  "type": "Voltage Regulation Test",
  "actuation": {
    "type": "Voltage Regulation Test",
    "load_command_source": 512,
    "load_command_signal": "Load_Command",
    "voltage_feedback_source": 513,
    "voltage_feedback_signal": "Output_Voltage",
    "reference_voltage_v": 12.0,
    "tolerance_v": 0.1,
    "load_steps": [0, 50, 100],
    "dwell_time_ms": 1000
  }
}
```

### Example 2: Full Configuration
```json
{
  "name": "Voltage Regulation Test - Full",
  "type": "Voltage Regulation Test",
  "actuation": {
    "type": "Voltage Regulation Test",
    "load_command_source": 512,
    "load_command_signal": "Load_Command",
    "voltage_feedback_source": 513,
    "voltage_feedback_signal": "Output_Voltage",
    "reference_voltage_v": 12.0,
    "tolerance_v": 0.1,
    "load_steps": [0, 25, 50, 75, 100],
    "dwell_time_ms": 2000,
    "pre_dwell_time_ms": 500,
    "settling_time_ms": 200
  }
}
```

## Implementation Notes

### Special Considerations
- This test requires iterating through multiple load steps
- Each load step must be evaluated independently
- All steps must pass for overall test to pass
- Plot should show voltage vs load step
- Results should show pass/fail for each load step

### Dependencies
- Requires `can_service` for sending load commands
- Requires `signal_service` for reading voltage feedback
- Requires `dbc_service` for message encoding (if DBC mode)

### Similar Test Types
- Similar to `Analog Sweep Test` (iterates through values)
- Similar to `Temperature Validation Test` (compares to reference with tolerance)
- Uses multi-step pattern like `External 5V Test`

### Testing Requirements
- Test with hardware connected (programmable load and voltage measurement)
- Test with valid DBC file loaded
- Test without DBC file (non-DBC mode)
- Test with various load step configurations
- Test with voltage within and outside tolerance

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Analog Sweep Test`
- **Why Similar**: `Both iterate through a series of values and collect feedback at each step`
- **Key Differences**: 
  - Analog Sweep Test sweeps DAC voltages
  - Voltage Regulation Test applies load steps and measures voltage
  - Voltage Regulation Test compares to reference ± tolerance
  - Analog Sweep Test may calculate gain/linearity

### Code Patterns to Use
- Use multi-step iteration pattern (like Analog Sweep Test)
- Use signal reading pattern (like Temperature Validation Test)
- Use reference comparison pattern (like Temperature Validation Test)
- Use plot update pattern (update after each step)

## Acceptance Criteria

### Functional Requirements
- [x] Test type appears in create test dialog dropdown
- [x] Test type appears in edit test dialog dropdown
- [x] All configuration fields are displayed correctly
- [x] Test can be created and saved successfully
- [x] Test can be edited and saved successfully
- [x] Validation works correctly (rejects invalid configurations)
- [x] Test execution runs without errors
- [x] Test execution returns correct pass/fail results
- [x] Test results appear in results table
- [x] Test results appear in test report
- [x] JSON schema validation works

### Technical Requirements
- [x] All files updated according to documentation
- [x] Code follows existing patterns and style
- [x] Error handling implemented
- [x] Logging added for debugging
- [x] Non-blocking sleep used (no `time.sleep()`)
- [x] DBC mode supported
- [x] Non-DBC mode supported

### Testing Requirements
- [x] Test with valid configuration
- [x] Test with invalid configuration (should fail validation)
- [x] Test with DBC loaded
- [x] Test without DBC loaded
- [x] Test execution produces correct results
- [x] Error cases handled gracefully

---

## Instructions for AI Agent

Please implement this new test type following the documentation in:
- `docs/ADDING_NEW_TEST_TYPES.md` - Full implementation guide
- `docs/TEST_TYPE_QUICK_REFERENCE.md` - Quick reference
- `docs/TEST_TYPE_SYSTEM_OVERVIEW.md` - System overview

### Implementation Steps
1. Review the test type requirements above
2. Follow the step-by-step guide in `ADDING_NEW_TEST_TYPES.md`
3. Update all required files:
   - `backend/data/tests/schema.json`
   - `host_gui/models/test_profile.py`
   - `host_gui/base_gui.py` (multiple methods)
   - `host_gui/test_runner.py`
   - `host_gui/services/test_execution_service.py` (optional)
4. Implement validation logic
5. Implement execution logic
6. Test thoroughly with both valid and invalid configurations
7. Ensure all acceptance criteria are met

### Key Reminders
- Use exact test type name consistently across all files: `"Voltage Regulation Test"`
- Support both DBC and non-DBC modes
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style

