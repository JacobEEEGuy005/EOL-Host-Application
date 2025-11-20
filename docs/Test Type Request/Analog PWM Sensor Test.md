# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `Analog PWM Sensor`
- **Short Description**: `Verifies PWM frequency and duty cycle percentage at zero input to the sensor`
- **Detailed Description**: 
  ```
  This test validates the PWM sensor behavior at zero input by comparing measured PWM frequency
  and duty cycle values from the DUT with reference values.
  
  How it works:
  - The test continuously reads PWM frequency and duty cycle signals from the DUT via CAN during
    the acquisition time period
  - Calculates average values for both PWM frequency and duty cycle from all collected readings
  - Compares the average PWM frequency with the reference PWM frequency
  - Compares the average duty cycle with the reference duty cycle
  - Test passes if both values are within their respective tolerances
  - Test fails if either value exceeds its tolerance
  
  Hardware Requirements:
  - Device Under Test (DUT) with PWM sensor
  - EOL Hardware
  - CAN Hardware (Canalystii or compatible)
  - Sensor at zero input condition
  
  Special Considerations:
  - Test verifies two independent parameters (frequency and duty cycle)
  - Both parameters must pass for overall test to pass
  - Real-time display of PWM frequency and duty cycle values during data collection
  - Supports both DBC and non-DBC modes
  - Test assumes sensor is at zero input condition (no external input applied)
  ```

## Test Configuration Fields

### Required Fields
List all fields that must be provided for this test type:

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `feedback_signal_source` | `integer` | `CAN message ID containing PWM frequency and duty signals` | `Range: 0-0x1FFFFFFF, Required` | `0x201` |
| `feedback_pwm_frequency_signal` | `string` | `CAN signal name for PWM frequency measurement` | `Non-empty, Required` | `"PWM_Frequency"` |
| `feedback_duty_signal` | `string` | `CAN signal name for PWM duty cycle measurement` | `Non-empty, Required` | `"PWM_Duty"` |
| `reference_pwm_frequency` | `number` | `Reference PWM frequency in Hz` | `Required` | `1000.0` |
| `reference_duty` | `number` | `Reference duty cycle in percentage (%)` | `Required` | `50.0` |
| `pwm_frequency_tolerance` | `number` | `Tolerance for PWM frequency in Hz` | `Minimum: 0, Required` | `10.0` |
| `duty_tolerance` | `number` | `Tolerance for duty cycle in percentage (%)` | `Minimum: 0, Required` | `1.0` |
| `acquisition_time_ms` | `integer` | `Time to collect PWM data in milliseconds` | `Minimum: 1, Required` | `3000` |

### CAN Message/Signal Fields
If the test uses CAN communication, specify:

- **Feedback Messages** (reading measurements from DUT):
  - Message ID: `feedback_signal_source` (configurable, e.g., 0x201)
  - Signals used: 
    - `feedback_pwm_frequency_signal` - PWM frequency measured by DUT (in Hz)
    - `feedback_duty_signal` - PWM duty cycle measured by DUT (in percentage %)
  - Purpose: `Read PWM frequency and duty cycle measurements from DUT for comparison with reference values`

- **DBC Support**: `Yes` - Test works with DBC file loaded (dropdowns for messages/signals)
- **Non-DBC Support**: `No, Test will not work without DBC file (free-text inputs for CAN IDs and signal names)

## Test Execution Logic

### Execution Flow
Describe the step-by-step execution flow:

```
1. Collect PWM Data During Acquisition Time
   - Action: 
     - Continuously read feedback_pwm_frequency_signal from CAN during acquisition_time_ms
     - Continuously read feedback_duty_signal from CAN during acquisition_time_ms
     - Store all PWM frequency readings in a list
     - Store all duty cycle readings in a list
     - Update real-time display with latest PWM frequency and duty cycle values
   - Duration: acquisition_time_ms milliseconds
   - Expected result: Multiple samples of both PWM frequency and duty cycle collected

2. Check Data Collection
   - Action: 
     - Verify that at least one reading was collected for both signals
   - Duration: As fast as possible
   - Expected result: Data available for both PWM frequency and duty cycle

3. Calculate Averages
   - Action: 
     - Calculate arithmetic mean of all PWM frequency values → pwm_frequency_avg
     - Calculate arithmetic mean of all duty cycle values → duty_avg
   - Duration: As fast as possible
   - Expected result: Averages calculated for both parameters

4. Compare with Reference Values
   - Action: 
     - Calculate absolute difference for PWM frequency: |pwm_frequency_avg - reference_pwm_frequency|
     - Calculate absolute difference for duty cycle: |duty_avg - reference_duty|
     - Compare frequency difference with pwm_frequency_tolerance
     - Compare duty difference with duty_tolerance
   - Duration: As fast as possible
   - Expected result: Differences calculated and compared with tolerances

5. Determine Pass/Fail
   - Action: 
     - frequency_ok = (frequency_difference <= pwm_frequency_tolerance)
     - duty_ok = (duty_difference <= duty_tolerance)
     - PASS if (frequency_ok AND duty_ok)
     - FAIL if (NOT frequency_ok OR NOT duty_ok)
   - Duration: As fast as possible
   - Expected result: Test result determined and returned
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `Both PWM frequency and duty cycle averages are within their respective tolerances (frequency_difference <= pwm_frequency_tolerance AND duty_difference <= duty_tolerance)`
- **Fail Condition**: `Either PWM frequency or duty cycle average exceeds its tolerance (frequency_difference > pwm_frequency_tolerance OR duty_difference > duty_tolerance)`
- **Calculation Method**: 
  ```
  1. Collect Data:
     - Read feedback_pwm_frequency_signal continuously during acquisition_time_ms
     - Read feedback_duty_signal continuously during acquisition_time_ms
     - Store all readings in pwm_frequency_values and duty_values lists
  
  2. Calculate Averages:
     - pwm_frequency_avg = sum(pwm_frequency_values) / len(pwm_frequency_values)
     - duty_avg = sum(duty_values) / len(duty_values)
  
  3. Calculate Differences:
     - frequency_difference = abs(pwm_frequency_avg - reference_pwm_frequency)
     - duty_difference = abs(duty_avg - reference_duty)
  
  4. Determine Pass/Fail:
     - frequency_ok = (frequency_difference <= pwm_frequency_tolerance)
     - duty_ok = (duty_difference <= duty_tolerance)
     - PASS if (frequency_ok AND duty_ok)
     - FAIL if (NOT frequency_ok OR NOT duty_ok)
  ```

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: 
  - `feedback_pwm_frequency_signal` from CAN (PWM frequency measurement in Hz)
  - `feedback_duty_signal` from CAN (PWM duty cycle measurement in percentage %)
  
- **Collection Duration**: `acquisition_time_ms` milliseconds
  
- **Sampling Rate**: 
  - Polled every SLEEP_INTERVAL_SHORT (typically 50-100ms) during acquisition time
  
- **Data Processing**: 
  ```
  1. During Acquisition Time:
     - Continuously poll both feedback_pwm_frequency_signal and feedback_duty_signal
     - Convert values to float (frequency in Hz, duty in %)
     - Append to respective lists
     - Update real-time display with latest values
  
  2. After Acquisition Time:
     - Calculate arithmetic means of both signal lists
     - Compare with reference values
  ```

### Timing Requirements
Specify any timing requirements:

- **Acquisition Time**: `acquisition_time_ms` (default: 3000ms) - Time to collect PWM frequency and duty cycle data
- **Polling Interval**: `SLEEP_INTERVAL_SHORT` (typically 50-100ms) - Interval between signal readings
- **Total Duration**: 
  ```
  Estimated total test duration:
  = acquisition_time_ms
  
  Example with acquisition_time_ms = 3000ms:
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

#### Field 2: Feedback PWM Frequency Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 3: Feedback Duty Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 4: Reference PWM Frequency
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter reference PWM frequency in Hz (e.g., 1000.0)`
- **Validator**: `Double, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 5: Reference Duty
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter reference duty cycle in % (e.g., 50.0)`
- **Validator**: `Double, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 6: PWM Frequency Tolerance
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter PWM frequency tolerance in Hz (e.g., 10.0)`
- **Validator**: `Double >= 0.0, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 7: Duty Tolerance
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter duty cycle tolerance in % (e.g., 1.0)`
- **Validator**: `Double >= 0.0, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 8: Acquisition Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter acquisition time in milliseconds (e.g., 3000)`
- **Validator**: `Integer >= 1, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

### Feedback Fields Visibility
- **Show Feedback Fields**: `No` - This test type has its own feedback fields (feedback_signal_source and feedback signals)
- **Custom Feedback Fields**: `Yes` - Uses feedback_signal_source, feedback_pwm_frequency_signal, and feedback_duty_signal

### Plot Requirements
- **Needs Plot**: `No`
- **Plot Type**: `N/A`
- **X-Axis**: `N/A`
- **Y-Axis**: `N/A`
- **Update Frequency**: `N/A`

### Real-Time Monitoring
The Real-Time Monitoring section displays the following signals during test execution:

- **Reference PWM Frequency**: Displays the static reference PWM frequency value from test configuration
  - Set once from `reference_pwm_frequency` in test config, remains constant during test
  - Format: `Reference PWM Frequency : X.XX Hz`
  
- **DUT PWM Frequency**: Displays the feedback PWM frequency signal from DUT
  - Updates in real-time via periodic polling (100ms)
  - Format: `DUT PWM Frequency : X.XX Hz`
  
- **Reference Duty**: Displays the static reference duty cycle value from test configuration
  - Set once from `reference_duty` in test config, remains constant during test
  - Format: `Reference Duty : X.XX %`
  
- **DUT Duty**: Displays the feedback duty cycle signal from DUT
  - Updates in real-time via periodic polling (100ms)
  - Format: `DUT Duty : X.XX %`

The monitoring section automatically configures these labels when the test starts and clears them when the test completes. See [Real-Time Monitoring](../REAL_TIME_MONITORING.md) for detailed documentation.

## Validation Rules

### Schema Validation
Specify JSON schema requirements:

```json
{
  "properties": {
    "type": {"const": "Analog PWM Sensor"},
    "feedback_signal_source": {"type": "integer"},
    "feedback_pwm_frequency_signal": {"type": "string"},
    "feedback_duty_signal": {"type": "string"},
    "reference_pwm_frequency": {"type": "number"},
    "reference_duty": {"type": "number"},
    "pwm_frequency_tolerance": {"type": "number", "minimum": 0},
    "duty_tolerance": {"type": "number", "minimum": 0},
    "acquisition_time_ms": {"type": "integer", "minimum": 1}
  },
  "required": [
    "feedback_signal_source",
    "feedback_pwm_frequency_signal",
    "feedback_duty_signal",
    "reference_pwm_frequency",
    "reference_duty",
    "pwm_frequency_tolerance",
    "duty_tolerance",
    "acquisition_time_ms"
  ]
}
```

### Application Validation
List validation checks to perform in `_validate_test()`:

- [ ] Test type is in allowed list
- [ ] Actuation type matches test type
- [ ] `feedback_signal_source` is present and in valid range (0-0x1FFFFFFF)
- [ ] `feedback_pwm_frequency_signal` is present and non-empty
- [ ] `feedback_duty_signal` is present and non-empty
- [ ] `reference_pwm_frequency` is present
- [ ] `reference_duty` is present
- [ ] `pwm_frequency_tolerance` is present and non-negative
- [ ] `duty_tolerance` is present and non-negative
- [ ] `acquisition_time_ms` is present and positive (>= 1)

## Error Handling

### Expected Error Scenarios
List potential errors and how to handle them:

1. **Missing Required Field**
   - Error: `"Missing required Analog PWM Sensor Test parameters"`
   - Handling: Return `False, "Analog PWM Sensor Test requires {field_name}"`

2. **Invalid Field Value**
   - Error: `"Tolerance must be non-negative"`
   - Handling: Return `False, "Tolerance must be non-negative"`

3. **No PWM Frequency Data Collected**
   - Error: `"No PWM frequency data received during acquisition time"`
   - Handling: Return `False, "No PWM frequency data received during acquisition time ({acquisition_time_ms}ms). Check CAN connection and signal configuration."`

4. **No Duty Data Collected**
   - Error: `"No duty cycle data received during acquisition time"`
   - Handling: Return `False, "No duty cycle data received during acquisition time ({acquisition_time_ms}ms). Check CAN connection and signal configuration."`

5. **Invalid Signal Value**
   - Error: `"Invalid signal value"`
   - Handling: Skip invalid values and continue collection (log warning)

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "Analog PWM Sensor - Basic",
  "type": "Analog PWM Sensor",
  "actuation": {
    "type": "Analog PWM Sensor",
    "feedback_signal_source": 256,
    "feedback_pwm_frequency_signal": "PWM_Frequency",
    "feedback_duty_signal": "PWM_Duty",
    "reference_pwm_frequency": 1000.0,
    "reference_duty": 50.0,
    "pwm_frequency_tolerance": 10.0,
    "duty_tolerance": 1.0,
    "acquisition_time_ms": 3000
  }
}
```

### Example 2: Tight Tolerance
```json
{
  "name": "Analog PWM Sensor - Tight Tolerance",
  "type": "Analog PWM Sensor",
  "actuation": {
    "type": "Analog PWM Sensor",
    "feedback_signal_source": 256,
    "feedback_pwm_frequency_signal": "PWM_Frequency",
    "feedback_duty_signal": "PWM_Duty",
    "reference_pwm_frequency": 1000.0,
    "reference_duty": 50.0,
    "pwm_frequency_tolerance": 5.0,
    "duty_tolerance": 0.5,
    "acquisition_time_ms": 5000
  }
}
```

## Implementation Notes

### Special Considerations
- **Dual Parameter Verification**: Test verifies two independent parameters (frequency and duty cycle) from the same CAN message
- **Both Must Pass**: Both parameters must be within tolerance for overall test to pass
- **Real-Time Display**: Both PWM frequency and duty cycle values displayed in real-time during data collection
- **Zero Input Condition**: Test assumes sensor is at zero input condition (no external input applied to sensor)
- **DBC Support**: Test supports both DBC and non-DBC modes

### Dependencies
- **can_service**: Required for CAN communication
- **dbc_service**: Optional but recommended for proper signal decoding
- **signal_service**: Required for reading PWM frequency and duty cycle signals

### Similar Test Types
- **Temperature Validation Test**: Similar pattern of reading signal and comparing to reference value
- **Analog Static Test**: Similar dual-signal reading pattern but compares two different sources (DUT vs EOL)
- **Fan Control Test**: Similar pattern of reading multiple signals from same message

### Testing Requirements
- Test with hardware connected (DUT, CAN hardware)
- Test with sensor at zero input condition
- Test with valid DBC file loaded
- Test without DBC file (non-DBC mode)
- Test with various reference values
- Test with different tolerance values
- Test with different acquisition times
- Test error cases (no data collected, invalid values, etc.)
- Verify real-time display of both signals works correctly

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Temperature Validation Test`
- **Why Similar**: 
  - Both read signals and compare to reference values
  - Both use simple single-phase pattern
  - Both calculate averages from collected data
  - Both use tolerance-based pass/fail determination
- **Key Differences**: 
  - Analog PWM Sensor Test reads two signals (frequency and duty) instead of one
  - Analog PWM Sensor Test compares both signals independently
  - Analog PWM Sensor Test requires both parameters to pass for overall pass
  - Analog PWM Sensor Test uses acquisition_time_ms instead of dwell_time_ms

### Code Patterns to Use
- **Dual Signal Collection Pattern**: Collect from two signals simultaneously during acquisition time
- **Average Calculation Pattern**: Calculate arithmetic mean of collected values for both signals
- **Dual Reference Comparison Pattern**: Compare both averages with their respective reference values and check tolerances
- **Real-Time Display Pattern**: Update UI labels with latest values from both signals during collection
- **Combined Pass/Fail Pattern**: Both parameters must pass for overall test to pass

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
- [ ] Test with various reference values
- [ ] Test with different tolerance values
- [ ] Test with different acquisition times
- [ ] Verify real-time display of both signals works correctly
- [ ] Verify both parameters are evaluated correctly (both must pass)

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
- Use exact test type name consistently across all files: `"Analog PWM Sensor"`
- Support both DBC and non-DBC modes
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style
- Collect from both signals simultaneously during acquisition time
- Display both signals in real-time during collection
- Calculate averages and compare both with their respective reference values
- Both parameters must pass for overall test to pass
- Use acquisition_time_ms for data collection duration

