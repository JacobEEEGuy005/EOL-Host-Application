# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `Analog Static Test`
- **Short Description**: `Compares static analog measurements between DUT feedback signal and EOL measurement signal`
- **Detailed Description**: 
  ```
  This test validates analog signal accuracy by comparing measurements from two sources:
  1. DUT feedback signal (from DUT via CAN)
  2. EOL measurement signal (from EOL hardware via CAN)
  
  How it works:
  - The test waits for a pre-dwell time to allow the system to stabilize
  - During the dwell time, continuously collects both feedback and EOL signal values
  - Calculates averages from both signal sources
  - Compares the averages: |feedback_avg - eol_avg| <= tolerance → PASS
  - Test passes if the difference is within the specified tolerance (in millivolts)
  
  Hardware Requirements:
  - Device Under Test (DUT)
  - EOL Hardware (for EOL measurement signal)
  - CAN Hardware (Canalystii or compatible)
  
  Special Considerations:
  - Two-phase data collection (pre-dwell for stabilization, then data collection)
  - Compares two CAN signals (no oscilloscope required)
  - Real-time display of both signals during data collection
  - Supports both DBC and non-DBC modes
  ```

## Test Configuration Fields

### Required Fields
List all fields that must be provided for this test type:

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `feedback_signal_source` | `integer` | `CAN message ID containing feedback signal` | `Range: 0-0x1FFFFFFF, Required` | `0x201` |
| `feedback_signal` | `string` | `CAN signal name for feedback signal` | `Non-empty, Required` | `"Feedback_Voltage"` |
| `eol_signal_source` | `integer` | `CAN message ID containing EOL signal` | `Range: 0-0x1FFFFFFF, Required` | `0x202` |
| `eol_signal` | `string` | `CAN signal name for EOL measurement signal` | `Non-empty, Required` | `"EOL_Voltage"` |
| `tolerance_mv` | `number` | `Tolerance in millivolts for pass/fail determination` | `Minimum: 0, Required` | `10.0` |
| `pre_dwell_time_ms` | `integer` | `Pre-dwell time in milliseconds (system stabilization)` | `Minimum: 0, Required` | `1000` |
| `dwell_time_ms` | `integer` | `Dwell time in milliseconds (data collection period)` | `Minimum: 1, Required` | `3000` |

### CAN Message/Signal Fields
If the test uses CAN communication, specify:

- **Feedback Messages** (reading measurements from DUT):
  - Message ID: `feedback_signal_source` (configurable, e.g., 0x201)
  - Signals used: 
    - `feedback_signal` - Feedback signal from DUT (in millivolts)
  - Purpose: `Read feedback signal from DUT for comparison with EOL measurement`

- **EOL Messages** (reading measurements from EOL hardware):
  - Message ID: `eol_signal_source` (configurable, e.g., 0x202)
  - Signals used: 
    - `eol_signal` - EOL measurement signal (in millivolts)
  - Purpose: `Read EOL measurement signal for comparison with DUT feedback`

- **DBC Support**: `Yes` - Test works with DBC file loaded (dropdowns for messages/signals)
- **Non-DBC Support**: `Yes` - Test works without DBC file (free-text inputs for CAN IDs and signal names)

## Test Execution Logic

### Execution Flow
Describe the step-by-step execution flow:

```
1. Wait for Pre-Dwell Time
   - Action: 
     - Wait for pre_dwell_time_ms to allow system to stabilize
     - No data collection during this period
   - Duration: pre_dwell_time_ms milliseconds
   - Expected result: System stabilized, ready for data collection

2. Collect Data During Dwell Time
   - Action: 
     - Continuously read feedback_signal from CAN
     - Continuously read eol_signal from CAN
     - Store all readings in separate lists
     - Update real-time display with latest values from both signals
   - Duration: dwell_time_ms milliseconds
   - Expected result: Multiple samples of both signals collected

3. Check Data Collection
   - Action: 
     - Verify that at least one reading was collected for both signals
   - Duration: As fast as possible
   - Expected result: Data available for both signals

4. Calculate Averages
   - Action: 
     - Calculate arithmetic mean of feedback_values → feedback_avg
     - Calculate arithmetic mean of eol_values → eol_avg
   - Duration: As fast as possible
   - Expected result: Averages calculated for both signals

5. Compare Averages
   - Action: 
     - Calculate absolute difference: |feedback_avg - eol_avg|
     - Compare difference with tolerance_mv
   - Duration: As fast as possible
   - Expected result: Difference calculated

6. Determine Pass/Fail
   - Action: 
     - PASS if difference <= tolerance_mv
     - FAIL if difference > tolerance_mv
   - Duration: As fast as possible
   - Expected result: Test result determined and returned
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `Absolute difference between feedback average and EOL average is within tolerance (|feedback_avg - eol_avg| <= tolerance_mv)`
- **Fail Condition**: `Absolute difference exceeds tolerance (|feedback_avg - eol_avg| > tolerance_mv)`
- **Calculation Method**: 
  ```
  1. Collect Data:
     - Read feedback_signal continuously during dwell_time_ms
     - Read eol_signal continuously during dwell_time_ms
     - Store all readings in feedback_values and eol_values lists
  
  2. Calculate Averages:
     - feedback_avg = sum(feedback_values) / len(feedback_values)
     - eol_avg = sum(eol_values) / len(eol_values)
  
  3. Calculate Difference:
     - difference = abs(feedback_avg - eol_avg)
  
  4. Determine Pass/Fail:
     - PASS if difference <= tolerance_mv
     - FAIL if difference > tolerance_mv
  ```

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: 
  - `feedback_signal` from CAN (DUT feedback measurement)
  - `eol_signal` from CAN (EOL measurement)
  
- **Collection Duration**: `dwell_time_ms` milliseconds
  
- **Sampling Rate**: 
  - Polled every SLEEP_INTERVAL_SHORT (typically 50-100ms) during dwell time
  
- **Data Processing**: 
  ```
  1. During Pre-Dwell Time:
     - No data collection (system stabilization only)
  
  2. During Dwell Time:
     - Continuously poll both feedback_signal and eol_signal
     - Convert values to float (millivolts)
     - Append to respective lists
     - Update real-time display with latest values
  
  3. After Dwell Time:
     - Calculate arithmetic means of both signal lists
     - Compare averages
  ```

### Timing Requirements
Specify any timing requirements:

- **Pre-Dwell Time**: `pre_dwell_time_ms` (default: 1000ms) - Wait time for system stabilization
- **Dwell Time**: `dwell_time_ms` (default: 3000ms) - Time to collect data from both signals
- **Polling Interval**: `SLEEP_INTERVAL_SHORT` (typically 50-100ms) - Interval between signal readings
- **Total Duration**: 
  ```
  Estimated total test duration:
  = pre_dwell_time_ms + dwell_time_ms
  
  Example with pre_dwell_time_ms = 1000ms, dwell_time_ms = 3000ms:
  ≈ 1.0s + 3.0s
  ≈ 4.0 seconds
  ```

## GUI Requirements

### Create/Edit Dialog Fields
Specify the UI fields needed:

#### Field 1: Feedback Signal Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x201)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 2: Feedback Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 3: EOL Signal Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x202)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 4: EOL Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 5: Tolerance
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter tolerance in millivolts (e.g., 10.0)`
- **Validator**: `Double >= 0.0, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 6: Pre-Dwell Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter pre-dwell time in milliseconds (e.g., 1000)`
- **Validator**: `Integer >= 0, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 7: Dwell Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter dwell time in milliseconds (e.g., 3000)`
- **Validator**: `Integer >= 1, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

### Feedback Fields Visibility
- **Show Feedback Fields**: `No` - This test type has its own feedback fields (feedback_signal_source and feedback_signal)
- **Custom Feedback Fields**: `Yes` - Uses feedback_signal_source and feedback_signal for DUT measurement

### Plot Requirements
- **Needs Plot**: `No`
- **Plot Type**: `N/A`
- **X-Axis**: `N/A`
- **Y-Axis**: `N/A`
- **Update Frequency**: `N/A`

## Validation Rules

### Schema Validation
Specify JSON schema requirements:

```json
{
  "properties": {
    "type": {"const": "Analog Static Test"},
    "feedback_signal_source": {"type": "integer"},
    "feedback_signal": {"type": "string"},
    "eol_signal_source": {"type": "integer"},
    "eol_signal": {"type": "string"},
    "tolerance_mv": {"type": "number", "minimum": 0},
    "pre_dwell_time_ms": {"type": "integer", "minimum": 0},
    "dwell_time_ms": {"type": "integer", "minimum": 1}
  },
  "required": [
    "feedback_signal_source",
    "feedback_signal",
    "eol_signal_source",
    "eol_signal",
    "tolerance_mv",
    "pre_dwell_time_ms",
    "dwell_time_ms"
  ]
}
```

### Application Validation
List validation checks to perform in `_validate_test()`:

- [x] Test type is in allowed list
- [x] Actuation type matches test type
- [x] `feedback_signal_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `feedback_signal` is present and non-empty
- [x] `eol_signal_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `eol_signal` is present and non-empty
- [x] `tolerance_mv` is present and non-negative
- [x] `pre_dwell_time_ms` is present and non-negative
- [x] `dwell_time_ms` is present and positive (>= 1)

## Error Handling

### Expected Error Scenarios
List potential errors and how to handle them:

1. **Missing Required Field**
   - Error: `"Missing required Analog Static Test parameters"`
   - Handling: Return `False, "Analog Static Test requires {field_name}"`

2. **Invalid Field Value**
   - Error: `"Tolerance must be non-negative"`
   - Handling: Return `False, "Tolerance must be non-negative"`

3. **No Data Collected**
   - Error: `"No data collected during dwell time"`
   - Handling: Return `False, "No data collected during dwell time (Feedback samples: {len(feedback_values)}, EOL samples: {len(eol_values)})"`

4. **Invalid Signal Value**
   - Error: `"Invalid signal value"`
   - Handling: Skip invalid values and continue collection (log warning)

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "Analog Static Test - Basic",
  "type": "Analog Static Test",
  "actuation": {
    "type": "Analog Static Test",
    "feedback_signal_source": 256,
    "feedback_signal": "Feedback_Voltage",
    "eol_signal_source": 257,
    "eol_signal": "EOL_Voltage",
    "tolerance_mv": 10.0,
    "pre_dwell_time_ms": 1000,
    "dwell_time_ms": 3000
  }
}
```

### Example 2: Tight Tolerance
```json
{
  "name": "Analog Static Test - Tight Tolerance",
  "type": "Analog Static Test",
  "actuation": {
    "type": "Analog Static Test",
    "feedback_signal_source": 256,
    "feedback_signal": "Feedback_Voltage",
    "eol_signal_source": 257,
    "eol_signal": "EOL_Voltage",
    "tolerance_mv": 5.0,
    "pre_dwell_time_ms": 2000,
    "dwell_time_ms": 5000
  }
}
```

## Implementation Notes

### Special Considerations
- **Two-Phase Pattern**: Pre-dwell for stabilization, then data collection
- **Dual Signal Collection**: Collects from two different CAN signals simultaneously
- **Real-Time Display**: Both signals displayed in real-time during collection
- **No Oscilloscope Required**: Test uses only CAN signals (no oscilloscope)
- **DBC Support**: Test supports both DBC and non-DBC modes

### Dependencies
- **can_service**: Required for CAN communication
- **dbc_service**: Optional but recommended for proper signal decoding
- **signal_service**: Required for reading both feedback and EOL signals

### Similar Test Types
- **Temperature Validation Test**: Similar pattern but compares to reference value (not another signal)
- **External 5V Test**: Similar dual-signal comparison but with multi-phase pattern
- **DC Bus Sensing**: Similar comparison pattern but uses oscilloscope as reference

### Testing Requirements
- Test with hardware connected (DUT, EOL hardware, CAN hardware)
- Test with valid DBC file loaded
- Test without DBC file (non-DBC mode)
- Test with various tolerance values
- Test with different pre-dwell and dwell times
- Test error cases (no data collected, invalid values, etc.)
- Verify real-time display of both signals works correctly

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Temperature Validation Test` (for simple signal reading pattern)
- **Why Similar**: 
  - Both read signals and compare values
  - Both use pre-dwell + dwell pattern
  - Both calculate averages from collected data
- **Key Differences**: 
  - Analog Static Test compares two CAN signals (not reference value)
  - Analog Static Test collects from two sources simultaneously
  - Analog Static Test displays both signals in real-time

### Code Patterns to Use
- **Dual Signal Collection Pattern**: Collect from two signals simultaneously during dwell time
- **Pre-Dwell Pattern**: Wait for system stabilization before data collection
- **Average Calculation Pattern**: Calculate arithmetic mean of collected values
- **Difference Comparison Pattern**: Compare averages and check tolerance
- **Real-Time Display Pattern**: Update UI labels with latest values from both signals

## Acceptance Criteria

### Functional Requirements
- [ ] Test type appears in create test dialog dropdown
- [ ] Test type appears in edit test dialog dropdown
- [ ] All configuration fields are displayed correctly
- [ ] Test can be created and saved successfully
- [ ] Test can be edited and saved successfully
- [ ] Validation works correctly (rejects invalid configurations)
- [ ] Test execution runs without errors
- [ ] Test execution returns correct pass/fail results
- [ ] Test results appear in results table
- [ ] Test results appear in test report
- [ ] JSON schema validation works

### Technical Requirements
- [ ] All files updated according to documentation
- [ ] Code follows existing patterns and style
- [ ] Error handling implemented
- [ ] Logging added for debugging
- [ ] Non-blocking sleep used (no `time.sleep()`)
- [ ] DBC mode supported
- [ ] Non-DBC mode supported
- [ ] Real-time display of both signals implemented

### Testing Requirements
- [ ] Test with valid configuration
- [ ] Test with invalid configuration (should fail validation)
- [ ] Test with DBC loaded
- [ ] Test without DBC loaded
- [ ] Test execution produces correct results
- [ ] Error cases handled gracefully (no data collected, invalid values, etc.)
- [ ] Test with various tolerance values
- [ ] Test with different pre-dwell and dwell times
- [ ] Verify real-time display of both signals works correctly

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
- Use exact test type name consistently across all files: `"Analog Static Test"`
- Support both DBC and non-DBC modes
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style
- Collect from both signals simultaneously during dwell time
- Display both signals in real-time during collection
- Calculate averages and compare difference with tolerance

