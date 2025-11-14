# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `Charged HV Bus Test`
- **Short Description**: `Verifies PFC Regulation and PSFB Operation at Rated Bus Voltage of 400V`
- **Detailed Description**: 
  ```
  This test verifies that the Power Factor Correction (PFC) circuit properly regulates the DC bus voltage 
  to 400V and that the Phase-Shifted Full-Bridge (PSFB) converter operates correctly without faults.
  
  How it works:
  - The test starts by configuring output current trim value (from previous Output Current Calibration 
    test result or fallback value) and output current setpoint
  - A test trigger signal is sent to the DUT via CAN to initiate the test
  - The DUT receives the trigger and initializes for the test
  - When AC voltage is detected by the DUT, it turns on the AC Input relay and enables PFC
  - The test monitors PFC feedback signals to confirm PFC regulation (bus voltage reaches 400V)
  - After AC is turned off, the DUT enables PSFB operation with the configured current setpoint
  - The test monitors fault signals throughout the test duration
  - After test timeout, the test analyzes logged CAN data to verify:
    1. PFC Regulation: PFC Power Good signal transitions from 0→1 after Enable PFC becomes 1
    2. PCMC Success: PCMC signal value is 1 (Peak Current Mode Control successful)
  - Test passes if both PFC Regulation and PCMC are successful, and no faults occurred
  
  Hardware Requirements:
  - Device Under Test (DUT) - Integrated Power Converter (IPC)
  - EOL Hardware
  - CAN Hardware (Canalystii or compatible)
  - AC Power Source (for AC input to DUT)
  
  Special Considerations:
  - Test requires Output Current Calibration test to be performed prior (for trim value)
  - If Output Current Calibration was not performed, uses fallback trim value from user input
  - Test monitors multiple feedback signals simultaneously during execution
  - Test performs post-execution analysis of logged CAN data
  - Test duration is user-configurable (test_time_ms)
  - DUT Test State = 7 indicates a fault condition (test fails immediately)
  - DUT Test State matching Test Trigger Signal Value indicates no fault occurred
  ```

## Test Configuration Fields

### Required Fields
List all fields that must be provided for this test type:

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `command_signal_source` | `integer` | `CAN message ID for command messages` | `Range: 0-0x1FFFFFFF, Required` | `0x110` |
| `test_trigger_signal` | `string` | `CAN signal name for test trigger command` | `Non-empty, Required` | `"Test_Request"` |
| `test_trigger_signal_value` | `integer` | `Value to send for test trigger signal (user configurable)` | `Range: 0-255, Required` | `1` |
| `set_output_current_trim_signal` | `string` | `CAN signal name for setting output current trim value` | `Non-empty, Required` | `"Set_ChargerIout_TrimValue"` |
| `fallback_output_current_trim_value` | `number` | `Fallback trim value (0-200%) if Output Current Calibration not performed` | `Range: 0-200, Required` | `100.0` |
| `set_output_current_setpoint_signal` | `string` | `CAN signal name for setting output current setpoint` | `Non-empty, Required` | `"ChargerIout_SetPoint"` |
| `output_test_current` | `number` | `Output current setpoint in Amperes` | `Range: 0-40, Required` | `10.0` |
| `feedback_signal_source` | `integer` | `CAN message ID for feedback messages` | `Range: 0-0x1FFFFFFF, Required` | `0x107` |
| `dut_test_state_signal` | `string` | `CAN signal name for DUT test state feedback` | `Non-empty, Required` | `"ChargerTestState"` |
| `enable_relay_signal` | `string` | `CAN signal name for AC relay enable feedback` | `Non-empty, Required` | `"Enable_Relay"` |
| `enable_pfc_signal` | `string` | `CAN signal name for PFC enable feedback` | `Non-empty, Required` | `"Enable_PFC"` |
| `pfc_power_good_signal` | `string` | `CAN signal name for PFC power good feedback` | `Non-empty, Required` | `"PFC_PGood"` |
| `pcmc_signal` | `string` | `CAN signal name for Peak Current Mode Control feedback` | `Non-empty, Required` | `"PCMC_Flag"` |
| `psfb_fault_signal` | `string` | `CAN signal name for PSFB fault feedback (for future use)` | `Non-empty, Required` | `"PSFB_Fault"` |
| `test_time_ms` | `integer` | `Test duration in milliseconds from test trigger` | `Minimum: 1000, Required` | `30000` |

### Optional Fields

None - All fields are required for this test type.

### CAN Message/Signal Fields
If the test uses CAN communication, specify:

- **Command Message** (sending commands to DUT):
  - Message ID: `command_signal_source` (configurable, e.g., 0x110)
  - Signals used: 
    - `test_trigger_signal` - Test trigger command (value: `test_trigger_signal_value`, user configurable)
    - `set_output_current_trim_signal` - Output current trim value (percentage, 0-200%)
    - `set_output_current_setpoint_signal` - Output current setpoint (Amperes, 0-40A)
  - Purpose: `Send test trigger, current trim, and current setpoint commands to DUT`

- **Feedback Messages** (reading feedback from DUT):
  - Message ID: `feedback_signal_source` (configurable, e.g., 0x107)
  - Signals used: 
    - `dut_test_state_signal` - DUT test state (value 7 = fault, matching trigger value = no fault)
    - `enable_relay_signal` - AC relay enable state
    - `enable_pfc_signal` - PFC enable state
    - `pfc_power_good_signal` - PFC power good status (0→1 transition indicates regulation)
    - `pcmc_signal` - Peak Current Mode Control flag (1 = successful)
    - `psfb_fault_signal` - PSFB fault status (for future implementation)
  - Purpose: `Read DUT state and feedback signals for test verification`

- **DBC Support**: `Yes` - Test works with DBC file loaded (dropdowns for messages/signals)
- **Non-DBC Support**: `No` - Test requires DBC file for proper signal encoding/decoding

## Test Execution Logic

### Execution Flow
Describe the step-by-step execution flow:

```
1. Initialize and Get Output Current Trim Value
   - Action: 
     1. Check if Output Current Calibration test was performed previously in test sequence
     2. If found, retrieve adjustment_factor from test results
     3. Calculate trim value: trim_value = adjustment_factor * 100 (percentage)
     4. If not found, use fallback_output_current_trim_value from configuration
   - Duration: As fast as possible
   - Expected result: Trim value determined (from calibration or fallback)

2. Send Output Current Trim Value
   - Action: 
     1. Encode trim value to CAN message using DBC
     2. Send CAN message with set_output_current_trim_signal = trim_value
     3. Wait SLEEP_INTERVAL_MEDIUM (typically 50ms)
   - Duration: ~50ms
   - Expected result: Trim value command sent to DUT

3. Send Output Current Setpoint
   - Action: 
     1. Encode output_test_current value to CAN message using DBC
     2. Send CAN message with set_output_current_setpoint_signal = output_test_current
     3. Wait SLEEP_INTERVAL_MEDIUM (typically 50ms)
   - Duration: ~50ms
   - Expected result: Current setpoint command sent to DUT

4. Start CAN Data Logging
   - Action: 
     1. Initialize CAN data logging for all feedback signals:
        - dut_test_state_signal
        - enable_relay_signal
        - enable_pfc_signal
        - pfc_power_good_signal
        - pcmc_signal
        - psfb_fault_signal
     2. Start timestamped logging
   - Duration: As fast as possible
   - Expected result: CAN logging started, ready to collect data

5. Send Test Trigger
   - Action: 
     1. Encode test_trigger_signal_value to CAN message using DBC
     2. Send CAN message with test_trigger_signal = test_trigger_signal_value
     3. Record trigger timestamp (t0 = test start time)
   - Duration: As fast as possible
   - Expected result: Test trigger sent, DUT receives command and initializes

6. Monitor Test Execution (until test_time_ms elapsed)
   - Action: 
     1. Continuously poll all feedback signals from CAN
     2. Log all signal values with timestamps
     3. Check dut_test_state_signal value:
        - If value = 7: DUT has fault → Test FAIL immediately, stop logging, send trigger = 0
        - If value = test_trigger_signal_value: No fault (normal operation)
     4. Continue monitoring until (current_time - t0) >= test_time_ms
   - Duration: test_time_ms milliseconds
   - Expected result: All feedback signals logged throughout test duration, no fault detected

7. Stop Test and Logging
   - Action: 
     1. Stop CAN data logging
     2. Send test_trigger_signal = 0 to stop test on DUT
     3. Wait SLEEP_INTERVAL_MEDIUM (typically 50ms)
   - Duration: ~50ms
   - Expected result: Test stopped, logging stopped, DUT returns to normal state

8. Analyze Logged CAN Data - PFC Regulation
   - Action: 
     1. Find all timestamps where enable_pfc_signal = 1
     2. For each timestamp where enable_pfc_signal = 1:
        - Check pfc_power_good_signal value at that timestamp
        - Check pfc_power_good_signal value at later timestamps
        - Verify if pfc_power_good_signal transitions from 0→1 after enable_pfc_signal = 1
     3. If transition 0→1 found: PFC Regulation = SUCCESS
     4. If no transition found or pfc_power_good_signal never becomes 1: PFC Regulation = FAIL
   - Duration: As fast as possible (data analysis)
   - Expected result: PFC Regulation status determined

9. Analyze Logged CAN Data - PCMC Success
   - Action: 
     1. Check latest pcmc_signal value from logged data
     2. If pcmc_signal = 1: PCMC Success = TRUE
     3. If pcmc_signal = 0 or not found: PCMC Success = FALSE
   - Duration: As fast as possible (data analysis)
   - Expected result: PCMC Success status determined

10. Determine Pass/Fail
   - Action: 
     1. Check if fault occurred (dut_test_state_signal = 7): If yes → FAIL
     2. Check PFC Regulation: If not successful → FAIL
     3. Check PCMC Success: If not successful → FAIL
     4. If all checks pass: Test PASS
   - Duration: As fast as possible
   - Expected result: Pass/fail determined, result returned
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `PFC Regulation is successful (PFC Power Good transitions 0→1 after Enable PFC = 1) AND PCMC Success (PCMC signal = 1) AND No fault occurred (DUT Test State never = 7, and equals Test Trigger Signal Value at end)`
- **Fail Condition**: `DUT Test State = 7 (fault) OR PFC Regulation failed (PFC Power Good never transitions 0→1) OR PCMC Success failed (PCMC signal ≠ 1)`
- **Calculation Method**: 
  ```
  1. Fault Check:
     - If any logged dut_test_state_signal value = 7 → FAIL immediately
     - If latest dut_test_state_signal value ≠ test_trigger_signal_value → FAIL
  
  2. PFC Regulation Check:
     - Find timestamps where enable_pfc_signal = 1
     - Check if pfc_power_good_signal transitions from 0→1 after enable_pfc_signal = 1
     - If transition found → PFC Regulation = SUCCESS
     - If no transition → PFC Regulation = FAIL
  
  3. PCMC Success Check:
     - Check latest pcmc_signal value from logged data
     - If pcmc_signal = 1 → PCMC Success = TRUE
     - If pcmc_signal ≠ 1 → PCMC Success = FALSE
  
  4. Final Result:
     - PASS if: (No fault) AND (PFC Regulation = SUCCESS) AND (PCMC Success = TRUE)
     - FAIL if: (Fault occurred) OR (PFC Regulation = FAIL) OR (PCMC Success = FALSE)
  ```

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: 
  - `dut_test_state_signal` - DUT test state (for fault detection)
  - `enable_relay_signal` - AC relay enable state
  - `enable_pfc_signal` - PFC enable state
  - `pfc_power_good_signal` - PFC power good status (for regulation verification)
  - `pcmc_signal` - Peak Current Mode Control flag (for success verification)
  - `psfb_fault_signal` - PSFB fault status (for future use)
  
- **Collection Duration**: `test_time_ms` milliseconds (from test trigger to timeout)
  
- **Sampling Rate**: 
  - Polled continuously during test execution (typically every SLEEP_INTERVAL_SHORT, ~50-100ms)
  - All signal values logged with timestamps
  
- **Data Processing**: 
  ```
  1. During Test Execution:
     - Continuously poll and log all feedback signals with timestamps
     - Check dut_test_state_signal for fault condition (value = 7)
     - If fault detected, stop immediately and fail test
  
  2. Post-Execution Analysis:
     - Analyze logged data for PFC Regulation:
       * Find enable_pfc_signal = 1 timestamps
       * Check pfc_power_good_signal transition from 0→1
     - Analyze logged data for PCMC Success:
       * Check latest pcmc_signal value
     - Check final dut_test_state_signal value (should equal test_trigger_signal_value)
  ```

### Timing Requirements
Specify any timing requirements:

- **Pre-Trigger Time**: `~100ms` - Time to send trim value and setpoint commands before trigger
- **Test Duration**: `test_time_ms` (user configurable, typically 30000ms = 30 seconds)
- **Post-Trigger Time**: `~50ms` - Time to stop test and send trigger = 0
- **Data Analysis Time**: `As fast as possible` - Analysis of logged CAN data
- **Total Duration**: 
  ```
  Estimated total test duration:
  = pre_trigger_time (≈0.1s)
  + test_time_ms (user configurable, e.g., 30000ms = 30s)
  + post_trigger_time (≈0.05s)
  + data_analysis_time (≈0.1s)
  
  Example with test_time_ms = 30000ms:
  ≈ 0.1s + 30.0s + 0.05s + 0.1s
  ≈ 30.25 seconds
  ```

## GUI Requirements

### Create/Edit Dialog Fields
Specify the UI fields needed:

#### Field 1: Command Signal Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x110)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 2: Test Trigger Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string (if DBC loaded)`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes (if DBC loaded), Optional (if no DBC)`

#### Field 3: Test Trigger Signal Value
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter trigger value (e.g., 1)`
- **Validator**: `Integer 0-255`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 4: Set Output Current Trim Value Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string (if DBC loaded)`
- **DBC Mode**: `Dropdown (populated based on Command Signal Source)`
- **Required**: `Yes (if DBC loaded), Optional (if no DBC)`

#### Field 5: Fallback Output Current Trim Value
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter fallback trim value (0-200%)`
- **Validator**: `Float 0.0-200.0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 6: Set Output Current Setpoint Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string (if DBC loaded)`
- **DBC Mode**: `Dropdown (populated based on Command Signal Source)`
- **Required**: `Yes (if DBC loaded), Optional (if no DBC)`

#### Field 7: Output Test Current
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter output current (0-40A)`
- **Validator**: `Float 0.0-40.0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 8: Feedback Signal Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x107)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 9: DUT Test State Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string (if DBC loaded)`
- **DBC Mode**: `Dropdown (populated based on Feedback Signal Source)`
- **Required**: `Yes (if DBC loaded), Optional (if no DBC)`

#### Field 10: Enable Relay Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string (if DBC loaded)`
- **DBC Mode**: `Dropdown (populated based on Feedback Signal Source)`
- **Required**: `Yes (if DBC loaded), Optional (if no DBC)`

#### Field 11: Enable PFC Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string (if DBC loaded)`
- **DBC Mode**: `Dropdown (populated based on Feedback Signal Source)`
- **Required**: `Yes (if DBC loaded), Optional (if no DBC)`

#### Field 12: PFC Power Good Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string (if DBC loaded)`
- **DBC Mode**: `Dropdown (populated based on Feedback Signal Source)`
- **Required**: `Yes (if DBC loaded), Optional (if no DBC)`

#### Field 13: PCMC Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string (if DBC loaded)`
- **DBC Mode**: `Dropdown (populated based on Feedback Signal Source)`
- **Required**: `Yes (if DBC loaded), Optional (if no DBC)`

#### Field 14: PSFB Fault Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string (if DBC loaded)`
- **DBC Mode**: `Dropdown (populated based on Feedback Signal Source)`
- **Required**: `Yes (if DBC loaded), Optional (if no DBC)`

#### Field 15: Test Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter test time in milliseconds (e.g., 30000)`
- **Validator**: `Integer >= 1000`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

### Feedback Fields Visibility
- **Show Feedback Fields**: `No` - Test uses custom feedback fields (Feedback Signal Source and all feedback signals)
- **Custom Feedback Fields**: `Yes` - Test has its own feedback signal configuration

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
    "type": {"const": "Charged HV Bus Test"},
    "command_signal_source": {"type": "integer", "minimum": 0, "maximum": 536870911},
    "test_trigger_signal": {"type": "string"},
    "test_trigger_signal_value": {"type": "integer", "minimum": 0, "maximum": 255},
    "set_output_current_trim_signal": {"type": "string"},
    "fallback_output_current_trim_value": {"type": "number", "minimum": 0, "maximum": 200},
    "set_output_current_setpoint_signal": {"type": "string"},
    "output_test_current": {"type": "number", "minimum": 0, "maximum": 40},
    "feedback_signal_source": {"type": "integer", "minimum": 0, "maximum": 536870911},
    "dut_test_state_signal": {"type": "string"},
    "enable_relay_signal": {"type": "string"},
    "enable_pfc_signal": {"type": "string"},
    "pfc_power_good_signal": {"type": "string"},
    "pcmc_signal": {"type": "string"},
    "psfb_fault_signal": {"type": "string"},
    "test_time_ms": {"type": "integer", "minimum": 1000}
  },
  "required": [
    "command_signal_source",
    "test_trigger_signal",
    "test_trigger_signal_value",
    "set_output_current_trim_signal",
    "fallback_output_current_trim_value",
    "set_output_current_setpoint_signal",
    "output_test_current",
    "feedback_signal_source",
    "dut_test_state_signal",
    "enable_relay_signal",
    "enable_pfc_signal",
    "pfc_power_good_signal",
    "pcmc_signal",
    "psfb_fault_signal",
    "test_time_ms"
  ]
}
```

### Application Validation
List validation checks to perform in `_validate_test()`:

- [ ] Test type is in allowed list
- [ ] Actuation type matches test type
- [ ] `command_signal_source` is present and in valid range (0-0x1FFFFFFF)
- [ ] `test_trigger_signal` is present and non-empty (if DBC loaded)
- [ ] `test_trigger_signal_value` is present and in valid range (0-255)
- [ ] `set_output_current_trim_signal` is present and non-empty (if DBC loaded)
- [ ] `fallback_output_current_trim_value` is present and in valid range (0-200)
- [ ] `set_output_current_setpoint_signal` is present and non-empty (if DBC loaded)
- [ ] `output_test_current` is present and in valid range (0-40)
- [ ] `feedback_signal_source` is present and in valid range (0-0x1FFFFFFF)
- [ ] `dut_test_state_signal` is present and non-empty (if DBC loaded)
- [ ] `enable_relay_signal` is present and non-empty (if DBC loaded)
- [ ] `enable_pfc_signal` is present and non-empty (if DBC loaded)
- [ ] `pfc_power_good_signal` is present and non-empty (if DBC loaded)
- [ ] `pcmc_signal` is present and non-empty (if DBC loaded)
- [ ] `psfb_fault_signal` is present and non-empty (if DBC loaded)
- [ ] `test_time_ms` is present and >= 1000

## Error Handling

### Expected Error Scenarios
List potential errors and how to handle them:

1. **Missing Required Field**
   - Error: `"Missing required field: field_name"`
   - Handling: Return `False, "Charged HV Bus Test requires field_name"`

2. **Invalid Field Value**
   - Error: `"Field value out of range"`
   - Handling: Return `False, "Field value out of range: expected range, got {value}"`

3. **Output Current Calibration Not Found**
   - Error: `"Output Current Calibration test not found in sequence"`
   - Handling: Use fallback_output_current_trim_value, log warning message

4. **DUT Fault Detected**
   - Error: `"DUT Test State = 7 (fault detected)"`
   - Handling: Stop test immediately, return `False, "Test failed: DUT fault detected (Test State = 7)"`

5. **Signal Not Found During Execution**
   - Error: `"Signal not found in CAN messages"`
   - Handling: Return `False, "No data collected: signal {signal_name} not found"`

6. **PFC Regulation Failed**
   - Error: `"PFC Power Good signal never transitioned from 0→1"`
   - Handling: Return `False, "PFC Regulation failed: PFC Power Good never became 1"`

7. **PCMC Success Failed**
   - Error: `"PCMC signal is not 1"`
   - Handling: Return `False, "PCMC Success failed: PCMC signal = {value} (expected 1)"`

8. **DBC Encoding Failure**
   - Error: `"Failed to encode message"`
   - Handling: Return `False, "Failed to encode CAN message: {error}"`

9. **CAN Communication Failure**
   - Error: `"No CAN frames received"`
   - Handling: Return `False, "CAN communication failure: No frames received"`

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "Charged HV Bus Test - 400V",
  "type": "Charged HV Bus Test",
  "actuation": {
    "type": "Charged HV Bus Test",
    "command_signal_source": 272,
    "test_trigger_signal": "Test_Request",
    "test_trigger_signal_value": 1,
    "set_output_current_trim_signal": "Set_ChargerIout_TrimValue",
    "fallback_output_current_trim_value": 100.0,
    "set_output_current_setpoint_signal": "ChargerIout_SetPoint",
    "output_test_current": 10.0,
    "feedback_signal_source": 250,
    "dut_test_state_signal": "ChargerTestState",
    "enable_relay_signal": "Enable_Relay",
    "enable_pfc_signal": "Enable_PFC",
    "pfc_power_good_signal": "PFC_PGood",
    "pcmc_signal": "PCMC_Flag",
    "psfb_fault_signal": "PSFB_Fault",
    "test_time_ms": 30000
  }
}
```

### Example 2: Full Configuration with Different Values
```json
{
  "name": "Charged HV Bus Test - 400V - 20A",
  "type": "Charged HV Bus Test",
  "actuation": {
    "type": "Charged HV Bus Test",
    "command_signal_source": 272,
    "test_trigger_signal": "Test_Request",
    "test_trigger_signal_value": 2,
    "set_output_current_trim_signal": "Set_ChargerIout_TrimValue",
    "fallback_output_current_trim_value": 95.5,
    "set_output_current_setpoint_signal": "ChargerIout_SetPoint",
    "output_test_current": 20.0,
    "feedback_signal_source": 250,
    "dut_test_state_signal": "ChargerTestState",
    "enable_relay_signal": "Enable_Relay",
    "enable_pfc_signal": "Enable_PFC",
    "pfc_power_good_signal": "PFC_PGood",
    "pcmc_signal": "PCMC_Flag",
    "psfb_fault_signal": "PSFB_Fault",
    "test_time_ms": 60000
  }
}
```

## Implementation Notes

### Special Considerations
- **Output Current Calibration Dependency**: Test attempts to retrieve adjustment_factor from previous "Output Current Calibration" test in the test sequence. If not found, uses fallback value. Implementation should search test results/execution history for previous test.
- **Multi-Signal Monitoring**: Test monitors 6 feedback signals simultaneously during execution. All signals must be logged with timestamps for post-execution analysis.
- **Post-Execution Analysis**: Test performs analysis of logged CAN data after test execution completes. This requires storing all logged data with timestamps.
- **Fault Detection**: Test must immediately fail if DUT Test State = 7 is detected at any point during execution.
- **State Machine Pattern**: Test uses a simple state machine: Initialize → Send Commands → Monitor → Analyze → Determine Result
- **PSFB Fault Signal**: Currently logged but not used for pass/fail determination (reserved for future implementation)

### Dependencies
- **can_service**: Required for sending CAN commands and receiving CAN frames
- **dbc_service**: Required for proper signal encoding/decoding (test requires DBC)
- **signal_service**: Required for reading feedback signals
- **Test Result Access**: Requires ability to access results from previous tests in test sequence (for Output Current Calibration adjustment_factor)

### Similar Test Types
- **Output Current Calibration**: Similar CAN command/feedback pattern, but this test focuses on PFC/PSFB operation rather than calibration
- **Fan Control Test**: Similar state monitoring pattern, but this test is more complex with multiple signals and post-execution analysis

### Testing Requirements
- Test with hardware connected (DUT, CAN hardware, AC power source)
- Test with valid DBC file loaded (required)
- Test with Output Current Calibration performed prior (to verify trim value retrieval)
- Test without Output Current Calibration (to verify fallback value usage)
- Test with various test_time_ms values
- Test with different output_test_current values
- Test error cases (fault detection, signal not found, etc.)

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Fan Control Test` (for state monitoring pattern)
- **Why Similar**: 
  - Both monitor multiple feedback signals during execution
  - Both check signal values for pass/fail determination
  - Both use CAN communication for commands and feedback
- **Key Differences**: 
  - Charged HV Bus Test requires post-execution analysis of logged data
  - Charged HV Bus Test monitors 6 signals vs 2 signals in Fan Control Test
  - Charged HV Bus Test has dependency on previous test results
  - Charged HV Bus Test has longer duration (user configurable)

### Code Patterns to Use
- **Multi-Signal Monitoring Pattern**: Poll and log multiple signals simultaneously with timestamps
- **Post-Execution Analysis Pattern**: Store logged data and analyze after test execution completes
- **Previous Test Result Access Pattern**: Search test execution history/results for previous test data
- **Fault Detection Pattern**: Check for fault condition during monitoring and fail immediately
- **State Transition Pattern**: Use state machine for test flow (Initialize → Send → Monitor → Analyze → Result)
- **DBC Encoding Pattern**: Use DBC service for encoding command messages

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
- [ ] Output Current Calibration result retrieval works (if test performed prior)
- [ ] Fallback trim value used correctly (if Output Current Calibration not performed)

### Technical Requirements
- [ ] All files updated according to documentation
- [ ] Code follows existing patterns and style
- [ ] Error handling implemented
- [ ] Logging added for debugging
- [ ] Non-blocking sleep used (no `time.sleep()`)
- [ ] DBC mode supported (required)
- [ ] Multi-signal monitoring implemented correctly
- [ ] Post-execution data analysis implemented correctly
- [ ] Previous test result access implemented (for Output Current Calibration)
- [ ] Fault detection works correctly (immediate fail on DUT Test State = 7)

### Testing Requirements
- [ ] Test with valid configuration
- [ ] Test with invalid configuration (should fail validation)
- [ ] Test with DBC loaded (required)
- [ ] Test execution produces correct results
- [ ] Error cases handled gracefully (fault detection, signal not found, etc.)
- [ ] Test with Output Current Calibration performed prior
- [ ] Test without Output Current Calibration (fallback value)
- [ ] Test with various test_time_ms values
- [ ] Test with different output_test_current values
- [ ] Post-execution analysis produces correct results
- [ ] PFC Regulation analysis works correctly
- [ ] PCMC Success analysis works correctly

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
5. Implement execution logic with multi-signal monitoring
6. Implement post-execution data analysis
7. Implement previous test result access (for Output Current Calibration)
8. Test thoroughly with both valid and invalid configurations
9. Ensure all acceptance criteria are met

### Key Reminders
- Use exact test type name consistently across all files: `"Charged HV Bus Test"`
- Support DBC mode only (test requires DBC file)
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style
- Implement multi-signal monitoring with timestamped logging
- Implement post-execution analysis for PFC Regulation and PCMC Success
- Access previous test results for Output Current Calibration adjustment_factor
- Fail immediately if DUT Test State = 7 detected
- Use fallback trim value if Output Current Calibration not found

