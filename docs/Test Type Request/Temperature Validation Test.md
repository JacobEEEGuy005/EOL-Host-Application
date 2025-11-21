# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `Temperature Validation Test`
- **Short Description**: `Validates temperature measurement by comparing DUT temperature reading with a reference value`
- **Detailed Description**: 
  ```
  This test validates the temperature sensor accuracy by comparing the DUT's temperature measurement
  with a known reference temperature value.
  
  How it works:
  - The test continuously reads the temperature feedback signal from the DUT via CAN during the dwell time
  - Calculates the average temperature from all collected readings
  - Compares the average temperature with the reference temperature
  - Test passes if the difference is within the specified tolerance
  
  Hardware Requirements:
  - Device Under Test (DUT) with temperature sensor
  - EOL Hardware
  - CAN Hardware (Canalystii or compatible)
  - Reference temperature source (e.g., temperature chamber, calibrated sensor)
  
  Special Considerations:
  - Simple single-phase test (no state changes required)
  - Real-time temperature display during data collection
  - Temperature values displayed in degrees Celsius (°C)
  - Supports both DBC and non-DBC modes
  ```

## Test Configuration Fields

### Required Fields
List all fields that must be provided for this test type:

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `feedback_signal_source` | `integer` | `CAN message ID containing temperature signal` | `Range: 0-0x1FFFFFFF, Required` | `0x201` |
| `feedback_signal` | `string` | `CAN signal name for temperature measurement` | `Non-empty, Required` | `"Temperature_Sensor"` |
| `reference_temperature_c` | `number` | `Reference temperature in degrees Celsius` | `Required` | `25.0` |
| `tolerance_c` | `number` | `Tolerance in degrees Celsius for pass/fail determination` | `Minimum: 0, Required` | `2.0` |
| `dwell_time_ms` | `integer` | `Time to collect temperature data in milliseconds` | `Minimum: 1, Required` | `3000` |

### CAN Message/Signal Fields
If the test uses CAN communication, specify:

- **Feedback Messages** (reading temperature from DUT):
  - Message ID: `feedback_signal_source` (configurable, e.g., 0x201)
  - Signals used: 
    - `feedback_signal` - Temperature measurement from DUT (in degrees Celsius)
  - Purpose: `Read temperature measurement from DUT for comparison with reference`

- **DBC Support**: `Yes` - Test works with DBC file loaded (dropdowns for messages/signals)
- **Non-DBC Support**: `Yes` - Test works without DBC file (free-text inputs for CAN IDs and signal names)

## Test Execution Logic

### Execution Flow
Describe the step-by-step execution flow:

```
1. Collect Temperature Data
   - Action: 
     - Continuously read feedback_signal from CAN during dwell_time_ms
     - Store all temperature readings in a list
     - Update real-time display with latest temperature value (in °C)
   - Duration: dwell_time_ms milliseconds
   - Expected result: Multiple temperature samples collected

2. Check Data Collection
   - Action: 
     - Verify that at least one temperature reading was collected
   - Duration: As fast as possible
   - Expected result: Temperature data available for analysis

3. Calculate Average
   - Action: 
     - Calculate arithmetic mean (average) of all collected temperature values
   - Duration: As fast as possible
   - Expected result: Average temperature calculated

4. Compare with Reference
   - Action: 
     - Calculate absolute difference: |average - reference_temperature_c|
     - Compare difference with tolerance_c
   - Duration: As fast as possible
   - Expected result: Pass/fail determined

5. Determine Pass/Fail
   - Action: 
     - PASS if difference <= tolerance_c
     - FAIL if difference > tolerance_c
   - Duration: As fast as possible
   - Expected result: Test result returned
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `Absolute difference between average temperature and reference temperature is within tolerance (|average - reference_temperature_c| <= tolerance_c)`
- **Fail Condition**: `Absolute difference exceeds tolerance (|average - reference_temperature_c| > tolerance_c)`
- **Calculation Method**: 
  ```
  1. Collect Data:
     - Read feedback_signal continuously during dwell_time_ms
     - Store all temperature readings in temperature_values list
  
  2. Calculate Average:
     - temperature_avg = sum(temperature_values) / len(temperature_values)
  
  3. Calculate Difference:
     - difference = abs(temperature_avg - reference_temperature_c)
  
  4. Determine Pass/Fail:
     - PASS if difference <= tolerance_c
     - FAIL if difference > tolerance_c
  ```

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: 
  - `feedback_signal` from CAN (temperature measurement)
  
- **Collection Duration**: `dwell_time_ms` milliseconds
  
- **Sampling Rate**: 
  - Polled every SLEEP_INTERVAL_SHORT (typically 50-100ms) during dwell time
  
- **Data Processing**: 
  ```
  1. During Dwell Time:
     - Continuously poll feedback_signal
     - Convert value to float (temperature in °C)
     - Append to temperature_values list
     - Update real-time display with latest value
  
  2. After Dwell Time:
     - Calculate arithmetic mean of all collected values
     - Compare with reference temperature
  ```

### Timing Requirements
Specify any timing requirements:

- **Dwell Time**: `dwell_time_ms` (default: 3000ms) - Time to collect temperature data
- **Polling Interval**: `SLEEP_INTERVAL_SHORT` (typically 50-100ms) - Interval between temperature readings
- **Total Duration**: 
  ```
  Estimated total test duration:
  = dwell_time_ms
  
  Example with dwell_time_ms = 3000ms:
  ≈ 3.0 seconds
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

#### Field 3: Reference Temperature
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter reference temperature in °C (e.g., 25.0)`
- **Validator**: `Double, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 4: Tolerance
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter tolerance in °C (e.g., 2.0)`
- **Validator**: `Double >= 0.0, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 5: Dwell Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter dwell time in milliseconds (e.g., 3000)`
- **Validator**: `Integer >= 1, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

### Feedback Fields Visibility
- **Show Feedback Fields**: `Yes` - Test uses feedback_signal_source and feedback_signal for temperature measurement
- **Custom Feedback Fields**: `No` - Uses standard feedback fields from test config

### Plot Requirements
- **Needs Plot**: `No`
- **Plot Type**: `N/A`
- **Plot Title**: `Nil`
- **X-Axis Title**: `Nil`
- **Y-Axis Title**: `Nil`
- **Plot**: `Empty`
- **Update Frequency**: `N/A`

### Real-Time Monitoring
The Real-Time Monitoring section displays the following signals during test execution:

- **Reference Temperature**: Displays the static reference temperature value from test configuration
  - Set once from `reference_temperature_c` in test config, remains constant during test
  - Format: `Reference Temperature : X.XX °C`
  
- **DUT Temperature**: Displays the feedback temperature signal from DUT
  - Updates in real-time via periodic polling (100ms) and during data collection
  - Format: `DUT Temperature : X.XX °C`

The monitoring section automatically configures these labels when the test starts and clears them when the test completes. See [Real-Time Monitoring](../REAL_TIME_MONITORING.md) for detailed documentation.

## Validation Rules

### Schema Validation
Specify JSON schema requirements:

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

### Application Validation
List validation checks to perform in `_validate_test()`:

- [x] Test type is in allowed list
- [x] Actuation type matches test type
- [x] `feedback_signal_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `feedback_signal` is present and non-empty
- [x] `reference_temperature_c` is present
- [x] `tolerance_c` is present and non-negative
- [x] `dwell_time_ms` is present and positive (>= 1)

## Error Handling

### Expected Error Scenarios
List potential errors and how to handle them:

1. **Missing Required Field**
   - Error: `"Missing required Temperature Validation Test parameters"`
   - Handling: Return `False, "Temperature Validation Test requires {field_name}"`

2. **Invalid Field Value**
   - Error: `"Tolerance must be non-negative"`
   - Handling: Return `False, "Tolerance must be non-negative"`

3. **No Temperature Data Collected**
   - Error: `"No temperature data received during dwell time"`
   - Handling: Return `False, "No temperature data received during dwell time ({dwell_time_ms}ms). Check CAN connection and signal configuration."`

4. **Invalid Temperature Value**
   - Error: `"Invalid temperature value"`
   - Handling: Skip invalid values and continue collection (log warning)

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "Temperature Validation - Room Temperature",
  "type": "Temperature Validation Test",
  "actuation": {
    "type": "Temperature Validation Test",
    "feedback_signal_source": 256,
    "feedback_signal": "Temperature_Sensor",
    "reference_temperature_c": 25.0,
    "tolerance_c": 2.0,
    "dwell_time_ms": 3000
  }
}
```

### Example 2: High Temperature Test
```json
{
  "name": "Temperature Validation - High Temp",
  "type": "Temperature Validation Test",
  "actuation": {
    "type": "Temperature Validation Test",
    "feedback_signal_source": 256,
    "feedback_signal": "Temperature_Sensor",
    "reference_temperature_c": 85.0,
    "tolerance_c": 3.0,
    "dwell_time_ms": 5000
  }
}
```

## Implementation Notes

### Special Considerations
- **Simple Test Pattern**: Single-phase test with no state changes
- **Real-Time Display**: Temperature values displayed in real-time during collection
- **Temperature Units**: All values in degrees Celsius (°C)
- **DBC Support**: Test supports both DBC and non-DBC modes

### Dependencies
- **can_service**: Required for CAN communication
- **dbc_service**: Optional but recommended for proper signal decoding
- **signal_service**: Required for reading temperature signal

### Similar Test Types
- **Analog Static Test**: Similar pattern of reading signal and comparing to reference
- **DC Bus Sensing**: Similar pattern but uses oscilloscope as reference

### Testing Requirements
- Test with hardware connected (DUT, CAN hardware)
- Test with valid DBC file loaded
- Test without DBC file (non-DBC mode)
- Test with various reference temperatures
- Test with different tolerance values
- Test with different dwell times
- Verify real-time temperature display
- Test error cases (no data collected, invalid values, etc.)

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Analog Static Test`
- **Why Similar**: 
  - Both read signals and compare to reference
  - Both use simple single-phase pattern
  - Both calculate averages from collected data
- **Key Differences**: 
  - Temperature Validation Test compares to reference temperature
  - Temperature Validation Test displays values in °C
  - Temperature Validation Test is simpler (no EOL signal comparison)

### Code Patterns to Use
- **Signal Reading Pattern**: Continuously read signal during dwell time
- **Average Calculation Pattern**: Calculate arithmetic mean of collected values
- **Reference Comparison Pattern**: Compare average with reference and check tolerance
- **Real-Time Display Pattern**: Update UI label with latest value during collection

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
- [ ] Real-time temperature display implemented

### Testing Requirements
- [ ] Test with valid configuration
- [ ] Test with invalid configuration (should fail validation)
- [ ] Test with DBC loaded
- [ ] Test without DBC loaded
- [ ] Test execution produces correct results
- [ ] Error cases handled gracefully (no data collected, invalid values, etc.)
- [ ] Test with various reference temperatures
- [ ] Test with different tolerance values
- [ ] Verify real-time temperature display works correctly

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
- Use exact test type name consistently across all files: `"Temperature Validation Test"`
- Support both DBC and non-DBC modes
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style
- Display temperature values in degrees Celsius (°C)
- Update real-time display during data collection

