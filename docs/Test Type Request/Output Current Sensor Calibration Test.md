# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `Output Current Calibration`
- **Short Description**: `Calibrates the output current sensor by comparing DUT measurements with oscilloscope measurements across multiple current setpoints`
- **Detailed Description**: 
  ```
  This test calibrates the Output Current sensor trim value to ensure the measurement error is below 
  the specified tolerance. The test compares output current measurements from two sources:
  1. DUT measurement via CAN bus (feedback signal)
  2. Oscilloscope measurement (reference measurement)
  
  How it works:
  - The test starts by verifying oscilloscope settings (timebase, channel enable, probe attenuation)
  - A test trigger signal is sent to the DUT via CAN to initiate the calibration test mode
  - The DUT outputs current at an initial setpoint (typically 5A)
  - The EOL system sends current setpoints from minimum to maximum values in steps
  - For each setpoint:
    * Wait for pre-acquisition time to allow current to stabilize
    * Start CAN data logging and oscilloscope acquisition
    * Collect data for the specified acquisition time
    * Stop data collection and calculate averages from both sources
    * Update live scatter plot (DUT measurement vs Oscilloscope measurement)
  - After all setpoints are tested, calculate gain error (%) and gain adjustment factor
  - Test passes if gain error is within specified tolerance
  
  Hardware Requirements:
  - Device Under Test (DUT)
    - EOL Hardware
    - CAN Hardware (Canalystii)
  - Oscilloscope - Siglent SDS1104X-u (or compatible)
  - Current probe connected to oscilloscope channel

  Special Considerations:
  - Requires oscilloscope to be connected and configured before test execution
  - Test iterates through multiple current setpoints (sweep pattern)
  - Real-time scatter plot updates during test execution
  - Calculates calibration parameters (gain error, adjustment factor) for sensor trim
  ```

## Test Configuration Fields

### Required Fields
List all fields that must be provided for this test type:

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `test_trigger_source` | `integer` | `CAN message ID for test trigger command` | `Range: 0-0x1FFFFFFF, Required` | `0x200` |
| `test_trigger_signal` | `string` | `CAN signal name for test trigger (enable/disable test mode)` | `Non-empty, Required` | `"Output_Current_Test_Enable"` |
| `test_trigger_signal_value` | `integer` | `Value to send for test trigger signal (typically 1 to enable, 0 to disable)` | `Range: 0-255, Required` | `1` |
| `current_setpoint_signal` | `string` | `CAN signal name for setting output current setpoint` | `Non-empty, Required` | `"Output_Current_Setpoint"` |
| `feedback_signal_source` | `integer` | `CAN message ID for feedback signal (DUT current measurement)` | `Range: 0-0x1FFFFFFF, Required` | `0x201` |
| `feedback_signal` | `string` | `CAN signal name for output current feedback from DUT` | `Non-empty, Required` | `"Output_Current_Measured"` |
| `oscilloscope_channel` | `string` | `Oscilloscope channel name (from loaded profile) for current measurement` | `Non-empty, Required, Must be enabled in profile` | `"Channel 3"` |
| `oscilloscope_timebase` | `string` | `Oscilloscope timebase setting` | `One of: '10MS', '20MS', '100MS', '500MS', Required` | `"100MS"` |
| `minimum_test_current` | `number` | `Minimum current setpoint in Amperes` | `Minimum: 0, Required, Default: 5.0` | `5.0` |
| `maximum_test_current` | `number` | `Maximum current setpoint in Amperes` | `Minimum: minimum_test_current, Required, Default: 20.0` | `20.0` |
| `step_current` | `number` | `Current step size in Amperes for sweep` | `Minimum: 0.1, Required, Default: 5.0` | `5.0` |
| `pre_acquisition_time_ms` | `integer` | `Time to wait before starting data acquisition (stabilization time)` | `Minimum: 0, Required, Default: 1000` | `1000` |
| `acquisition_time_ms` | `integer` | `Time to collect data from both CAN and oscilloscope` | `Minimum: 1, Required, Default: 3000` | `3000` |
| `tolerance_percent` | `number` | `Maximum allowed gain error percentage` | `Minimum: 0, Required, Default: 1.0` | `1.0` |

### CAN Message/Signal Fields
If the test uses CAN communication, specify:

- **Command Message** (sending commands to DUT):
  - Message ID: `test_trigger_source` (configurable, e.g., 0x200)
  - Signals used: 
    - `test_trigger_signal` - Enable/disable output current test mode (value: `test_trigger_signal_value`, typically 1 to enable, 0 to disable)
    - `current_setpoint_signal` - Set output current setpoint value in Amperes
  - Purpose: `Send test trigger and current setpoint commands to DUT`

- **Feedback Messages** (reading measurements from DUT):
  - Message ID: `feedback_signal_source` (configurable, e.g., 0x201)
  - Signals used: 
    - `feedback_signal` - Output current measured by DUT (in Amperes)
  - Purpose: `Read output current measurement from DUT for comparison with oscilloscope`

- **DBC Support**: `Yes` - Test works with DBC file loaded (dropdowns for messages/signals)
- **Non-DBC Support**: `No` - Test requires DBC file for proper signal encoding/decoding

## Test Execution Logic

### Execution Flow
Describe the step-by-step execution flow:

```
1. Verify Oscilloscope Setup
    - Action: 
     1. Check oscilloscope connection status
     2. Send TDIV command with oscilloscope_timebase value (e.g., "TDIV 100MS")
     3. Verify timebase is set correctly using "TDIV?" query command
     4. Get channel number from oscilloscope_channel name
     5. Send "C{ch_num}:TRA ON" command to enable channel trace
     6. Verify channel is enabled using "C{ch_num}:TRA?" query
     7. Verify probe attenuation matches oscilloscope configuration for selected channel
   - Duration: As fast as possible (typically < 1 second)
   - Expected result: Oscilloscope is configured correctly with proper timebase, channel enabled, and probe attenuation verified

2. Prepare Test Current Setpoints Array
   - Action: 
     - Generate array of current setpoints from minimum_test_current to maximum_test_current 
       with step_current increments (e.g., [5.0, 10.0, 15.0, 20.0] A)
     - Clear plot window and initialize scatter plot
     - Set X-axis label: "Oscilloscope Measurement (A)"
     - Set Y-axis label: "DUT Measurement (A)"
     - Initialize lists for storing CAN averages and oscilloscope averages
   - Duration: As fast as possible
   - Expected result: Array of current setpoints ready, plot initialized with correct labels

3. Trigger Test at DUT
    - Action: 
     - Encode and send CAN message with test_trigger_signal = test_trigger_signal_value (typically 1)
       to enable output current test mode at DUT
     - DUT should initialize and output current at default setpoint (typically 5A)
   - Duration: As fast as possible
   - Expected result: Test trigger command sent successfully, DUT enters test mode

4. For each current setpoint in the array:
   a. Send Current Setpoint
      - Action: Encode and send CAN message with current_setpoint_signal = setpoint value (in Amperes)
    - Duration: As fast as possible
      - Expected result: Current setpoint command sent successfully
   
   b. Wait for Pre-Acquisition Time
      - Action: Wait for pre_acquisition_time_ms to allow current to stabilize at new setpoint
      - Duration: pre_acquisition_time_ms milliseconds
      - Expected result: Current has stabilized at setpoint value
   
   c. Start Data Acquisition
      - Action: 
        - Start logging CAN feedback signal (feedback_signal from feedback_signal_source)
        - Send "TRMD AUTO" command to oscilloscope to start acquisition
        - Initialize data collection lists for this setpoint
    - Duration: As fast as possible
      - Expected result: CAN logging started, oscilloscope acquisition started
   
   d. Collect Data During Acquisition Time
      - Action: 
        - Continuously read feedback_signal from CAN during acquisition_time_ms
        - Store all CAN readings in list
        - Oscilloscope continues acquiring data
      - Duration: acquisition_time_ms milliseconds
      - Expected result: Multiple CAN samples collected, oscilloscope data acquired
   
   e. Stop Data Acquisition
      - Action: 
        - Stop logging CAN feedback signal
        - Send "STOP" command to oscilloscope to stop acquisition
    - Duration: As fast as possible
      - Expected result: CAN logging stopped, oscilloscope acquisition stopped
   
   f. Analyze Data and Update Plot
      - Action: 
        - Calculate average from collected CAN feedback values
        - Query oscilloscope for average value using "C{ch_num}:PAVA? MEAN" command
        - Store both averages in lists for final analysis
        - Update scatter plot with point (oscilloscope_avg, can_avg)
    - Duration: As fast as possible
      - Expected result: Averages calculated and stored, plot updated with new data point

5. Post-Test Analysis
    - Action: 
     - Send test trigger signal with value 0 to disable test mode at DUT
     - Perform linear regression on collected data points (CAN vs Oscilloscope)
     - Calculate gain error: gain_error = |(slope - 1.0)| * 100%
     - Calculate gain adjustment factor: adjustment_factor = 1.0 / slope
     - Determine pass/fail: pass if gain_error <= tolerance_percent
   - Duration: As fast as possible
   - Expected result: Test mode disabled, calibration parameters calculated, pass/fail determined
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `Gain error percentage is within tolerance_percent (gain_error <= tolerance_percent)`
- **Fail Condition**: `Gain error percentage exceeds tolerance_percent (gain_error > tolerance_percent)`
- **Calculation Method**: 
  ```
  1. Collect data points: For each current setpoint, collect:
     - CAN average: average of all CAN feedback_signal readings during acquisition_time_ms
     - Oscilloscope average: result from "C{ch_num}:PAVA? MEAN" command
  
  2. Perform linear regression on data points:
     - X values: Oscilloscope averages (reference measurements)
     - Y values: CAN averages (DUT measurements)
     - Calculate slope and intercept: Y = slope * X + intercept
  
  3. Calculate gain error:
     - Ideal slope = 1.0 (perfect calibration)
     - gain_error = |(slope - 1.0)| * 100%
  
  4. Calculate gain adjustment factor:
     - adjustment_factor = 1.0 / slope
     - This factor can be used to adjust the sensor trim value
  
  5. Determine pass/fail:
     - PASS if gain_error <= tolerance_percent
     - FAIL if gain_error > tolerance_percent
  ```

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: 
  - `feedback_signal` from CAN (DUT current measurement)
  - Oscilloscope channel average (reference current measurement)
  
- **Collection Duration**: `acquisition_time_ms` milliseconds per setpoint
  
- **Sampling Rate**: 
  - CAN data: Logged continuously during acquisition_time_ms (typically every 50-100ms via signal_service)
  - Oscilloscope: Continuous acquisition during acquisition_time_ms, average computed after stop
  
- **Data Processing**: 
  ```
  1. CAN Data:
     - Collect all feedback_signal readings during acquisition_time_ms
     - Calculate arithmetic mean (average) of all collected values
     - Store average for this setpoint
  
  2. Oscilloscope Data:
     - Start acquisition with "TRMD AUTO"
     - Let oscilloscope acquire data for acquisition_time_ms
     - Stop acquisition with "STOP"
     - Query average using "C{ch_num}:PAVA? MEAN" command
     - Parse and store average value for this setpoint
  
  3. Final Analysis:
     - Perform linear regression on all (oscilloscope_avg, can_avg) pairs
     - Calculate gain error and adjustment factor
  ```

### Timing Requirements
Specify any timing requirements:

- **Pre-Acquisition Time**: `pre_acquisition_time_ms` (default: 1000ms) - Wait time after setting current setpoint before starting data collection
- **Acquisition Time**: `acquisition_time_ms` (default: 3000ms) - Time to collect data from both CAN and oscilloscope per setpoint
- **Post-Acquisition Time**: Not required - Analysis happens immediately after data collection
- **Total Duration**: 
  ```
  Estimated total test duration:
  = oscilloscope_setup_time (≈1s)
  + trigger_time (≈0.1s)
  + (number_of_setpoints × (setpoint_send_time + pre_acquisition_time_ms + acquisition_time_ms + analysis_time))
  + post_test_analysis_time (≈0.5s)
  
  Example with 4 setpoints (5A, 10A, 15A, 20A), 1000ms pre-acq, 3000ms acq:
  ≈ 1s + 0.1s + 4 × (0.1s + 1s + 3s + 0.2s) + 0.5s
  ≈ 1.6s + 4 × 4.3s + 0.5s
  ≈ 19.3 seconds
  ```

## GUI Requirements

### Create/Edit Dialog Fields
Specify the UI fields needed:

#### Field 1: Test Trigger Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x200)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 2: Test Trigger Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 3: Test Trigger Signal Value
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter trigger value (typically 1 to enable, 0 to disable)`
- **Validator**: `Integer 0-255`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 4: Current Setpoint Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on test trigger source message)`
- **Required**: `Yes`

#### Field 5: Feedback Signal Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x201)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 6: Feedback Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 7: Oscilloscope Channel
- **Type**: `QComboBox`
- **Placeholder**: `Select oscilloscope channel`
- **Validator**: `Must be from enabled channels in loaded profile`
- **DBC Mode**: `Dropdown (populated from oscilloscope profile)`
- **Required**: `Yes`

#### Field 8: Oscilloscope Timebase
- **Type**: `QComboBox`
- **Placeholder**: `Select timebase`
- **Validator**: `One of: '10MS', '20MS', '100MS', '500MS'`
- **DBC Mode**: `Dropdown (same for both modes)`
- **Required**: `Yes`

#### Field 9: Minimum Test Current
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter minimum current in Amperes (e.g., 5.0)`
- **Validator**: `Double >= 0.0, Default: 5.0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 10: Maximum Test Current
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter maximum current in Amperes (e.g., 20.0)`
- **Validator**: `Double >= minimum_test_current, Default: 20.0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 11: Step Current
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter step size in Amperes (e.g., 5.0)`
- **Validator**: `Double >= 0.1, Default: 5.0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 12: Pre-Acquisition Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter pre-acquisition time in milliseconds (e.g., 1000)`
- **Validator**: `Integer >= 0, Default: 1000`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 13: Acquisition Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter acquisition time in milliseconds (e.g., 3000)`
- **Validator**: `Integer >= 1, Default: 3000`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 14: Tolerance
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter tolerance in percent (e.g., 1.0)`
- **Validator**: `Double >= 0.0, Default: 1.0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

### Feedback Fields Visibility
- **Show Feedback Fields**: `No` - This test type has its own feedback fields (feedback_signal_source and feedback_signal)
- **Custom Feedback Fields**: `Yes` - Uses feedback_signal_source and feedback_signal for DUT current measurement

### Plot Requirements
- **Needs Plot**: `Yes`
- **Plot Type**: `Scatter plot (X-Y plot)`
- **X-Axis**: `Oscilloscope Measurement (A)` - Reference measurement from oscilloscope
- **Y-Axis**: `DUT Measurement (A)` - DUT measurement from CAN feedback signal
- **Update Frequency**: `After each setpoint completes (after calculating averages from CAN and oscilloscope)`
- **Plot Features**: 
  - Real-time scatter plot updates during test execution
  - Each point represents one current setpoint
  - Ideal calibration line (Y = X) can be displayed for reference
  - Final linear regression line can be displayed after test completion

## Validation Rules

### Schema Validation
Specify JSON schema requirements:

```json
{
  "properties": {
    "type": {"const": "Output Current Calibration"},
    "test_trigger_source": {"type": "integer", "minimum": 0, "maximum": 536870911},
    "test_trigger_signal": {"type": "string"},
    "test_trigger_signal_value": {"type": "integer", "minimum": 0, "maximum": 255},
    "current_setpoint_signal": {"type": "string"},
    "feedback_signal_source": {"type": "integer", "minimum": 0, "maximum": 536870911},
    "feedback_signal": {"type": "string"},
    "oscilloscope_channel": {"type": "string"},
    "oscilloscope_timebase": {"type": "string", "enum": ["10MS", "20MS", "100MS", "500MS"]},
    "minimum_test_current": {"type": "number", "minimum": 0},
    "maximum_test_current": {"type": "number", "minimum": 0},
    "step_current": {"type": "number", "minimum": 0.1},
    "pre_acquisition_time_ms": {"type": "integer", "minimum": 0},
    "acquisition_time_ms": {"type": "integer", "minimum": 1},
    "tolerance_percent": {"type": "number", "minimum": 0}
  },
  "required": [
    "test_trigger_source",
    "test_trigger_signal",
    "test_trigger_signal_value",
    "current_setpoint_signal",
    "feedback_signal_source",
    "feedback_signal",
    "oscilloscope_channel",
    "oscilloscope_timebase",
    "minimum_test_current",
    "maximum_test_current",
    "step_current",
    "pre_acquisition_time_ms",
    "acquisition_time_ms",
    "tolerance_percent"
  ]
}
```

### Application Validation
List validation checks to perform in `_validate_test()`:

- [x] Test type is in allowed list
- [x] Actuation type matches test type
- [x] `test_trigger_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `test_trigger_signal` is present and non-empty
- [x] `test_trigger_signal_value` is present and in range (0-255)
- [x] `current_setpoint_signal` is present and non-empty
- [x] `feedback_signal_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `feedback_signal` is present and non-empty
- [x] `oscilloscope_channel` is present and non-empty
- [x] `oscilloscope_timebase` is present and one of: '10MS', '20MS', '100MS', '500MS'
- [x] `minimum_test_current` is present and non-negative
- [x] `maximum_test_current` is present and >= minimum_test_current
- [x] `step_current` is present and >= 0.1
- [x] `pre_acquisition_time_ms` is present and non-negative
- [x] `acquisition_time_ms` is present and positive (>= 1)
- [x] `tolerance_percent` is present and non-negative
- [x] Oscilloscope service is available and connected
- [x] Oscilloscope channel exists in loaded profile

## Error Handling

### Expected Error Scenarios
List potential errors and how to handle them:

1. **Missing Required Field**
   - Error: `"Missing required field: {field_name}"`
   - Handling: Return `False, "Output Current Calibration requires {field_name}"`

2. **Invalid Field Value**
   - Error: `"Field value out of range"`
   - Handling: Return `False, "Field value out of range: {field_name} expected {range}, got {value}"`
   - Examples:
     - `test_trigger_signal_value` must be 0-255
     - `maximum_test_current` must be >= `minimum_test_current`
     - `step_current` must be >= 0.1

3. **Oscilloscope Not Connected**
   - Error: `"Oscilloscope not connected"`
   - Handling: Return `False, "Oscilloscope not connected. Please connect oscilloscope before running Output Current Calibration test."`

4. **Oscilloscope Channel Not Found**
   - Error: `"Channel not found in oscilloscope configuration"`
   - Handling: Return `False, "Channel '{oscilloscope_channel}' not found in oscilloscope configuration or not enabled"`

5. **Oscilloscope Setup Failure**
   - Error: `"Failed to configure oscilloscope"`
   - Handling: Return `False, "Failed to configure oscilloscope: {specific_error}"`
   - Examples:
     - Timebase verification failed
     - Channel enable failed
     - Probe attenuation mismatch

6. **No CAN Data Collected**
   - Error: `"No CAN data collected at setpoint {setpoint}"`
   - Handling: Return `False, "No CAN data collected at setpoint {setpoint}A. Check CAN connection and signal configuration."`

7. **Oscilloscope Data Acquisition Failure**
   - Error: `"Failed to acquire oscilloscope data"`
   - Handling: Return `False, "Failed to acquire oscilloscope data at setpoint {setpoint}A: {error}"`

8. **Insufficient Data Points**
   - Error: `"Insufficient data points for analysis"`
   - Handling: Return `False, "Insufficient data points collected. Need at least 2 setpoints for linear regression."`

9. **Linear Regression Failure**
   - Error: `"Failed to calculate calibration parameters"`
   - Handling: Return `False, "Failed to calculate calibration parameters: {error}. Check data quality."`

10. **DBC Service Not Available**
    - Error: `"DBC service not available"`
    - Handling: Return `False, "Output Current Calibration requires DBC file to be loaded"`

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "Output Current Calibration - Basic",
  "type": "Output Current Calibration",
  "actuation": {
    "type": "Output Current Calibration",
    "test_trigger_source": 512,
    "test_trigger_signal": "Output_Current_Test_Enable",
    "test_trigger_signal_value": 1,
    "current_setpoint_signal": "Output_Current_Setpoint",
    "feedback_signal_source": 513,
    "feedback_signal": "Output_Current_Measured",
    "oscilloscope_channel": "Channel 3",
    "oscilloscope_timebase": "100MS",
    "minimum_test_current": 5.0,
    "maximum_test_current": 20.0,
    "step_current": 5.0,
    "pre_acquisition_time_ms": 1000,
    "acquisition_time_ms": 3000,
    "tolerance_percent": 1.0
  }
}
```

### Example 2: Full Configuration with Fine Steps
```json
{
  "name": "Output Current Calibration - Fine Steps",
  "type": "Output Current Calibration",
  "actuation": {
    "type": "Output Current Calibration",
    "test_trigger_source": 512,
    "test_trigger_signal": "Output_Current_Test_Enable",
    "test_trigger_signal_value": 1,
    "current_setpoint_signal": "Output_Current_Setpoint",
    "feedback_signal_source": 513,
    "feedback_signal": "Output_Current_Measured",
    "oscilloscope_channel": "Channel 3",
    "oscilloscope_timebase": "100MS",
    "minimum_test_current": 5.0,
    "maximum_test_current": 25.0,
    "step_current": 2.5,
    "pre_acquisition_time_ms": 1500,
    "acquisition_time_ms": 5000,
    "tolerance_percent": 0.5
  }
}
```

## Implementation Notes

### Special Considerations
- **Requires oscilloscope integration**: Test must verify oscilloscope connection and configuration before execution
- **Multi-step test pattern**: Test iterates through multiple current setpoints (similar to Analog Sweep Test)
- **Real-time plotting**: Scatter plot must update after each setpoint completes
- **Linear regression analysis**: Final analysis requires linear regression on collected data points
- **Calibration parameter calculation**: Test calculates gain error and adjustment factor for sensor trim
- **DBC required**: Test requires DBC file to be loaded for proper CAN message encoding/decoding
- **State management**: Test maintains state across multiple setpoints (oscilloscope setup, data collection, analysis)

### Dependencies
- **oscilloscope_service**: Required for oscilloscope communication (TDIV, TRA, TRMD, STOP, PAVA commands)
- **can_service**: Required for sending CAN commands and receiving feedback
- **dbc_service**: Required for encoding/decoding CAN messages (test requires DBC file)
- **signal_service**: Required for reading CAN feedback signal during data collection
- **numpy** (optional but recommended): For linear regression calculation (can use built-in methods if numpy unavailable)

### Similar Test Types
- **Phase Current Test**: Similar oscilloscope integration pattern, multi-step current testing, real-time plotting
- **DC Bus Sensing**: Similar oscilloscope + CAN comparison pattern, uses PAVA? MEAN command
- **Analog Sweep Test**: Similar multi-step sweep pattern, iterates through values and collects feedback
- **Temperature Validation Test**: Similar reference comparison pattern (though simpler, single measurement)

### Testing Requirements
- Test with hardware connected (DUT, oscilloscope, CAN hardware)
- Test with valid DBC file loaded (test requires DBC for signal encoding)
- Test with oscilloscope connected and configured
- Test with various current setpoint ranges and step sizes
- Test with different tolerance values
- Test error cases (oscilloscope not connected, channel not found, no data collected)
- Test with different oscilloscope timebase settings
- Verify linear regression calculation accuracy
- Verify plot updates correctly during execution

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Phase Current Test` and `DC Bus Sensing`
- **Why Similar**: 
  - Phase Current Test: Similar pattern of oscilloscope integration, multi-step current testing, real-time plotting, and state machine approach
  - DC Bus Sensing: Similar pattern of comparing oscilloscope measurements with CAN feedback, using PAVA? MEAN command, and scatter plot visualization
- **Key Differences**: 
  - Output Current Calibration focuses on output current (not phase current)
  - Uses linear regression for gain error calculation (not just simple difference)
  - Calculates calibration parameters (gain error, adjustment factor) for sensor trim
  - Iterates through current setpoints sent via CAN (not fixed Iq_ref values)
  - Uses different CAN signals (output current specific)

### Code Patterns to Use
- **Oscilloscope setup pattern**: Follow DC Bus Sensing pattern for oscilloscope verification (TDIV, TRA commands)
- **Multi-step iteration pattern**: Follow Phase Current Test or Analog Sweep Test pattern for iterating through setpoints
- **CAN command + feedback pattern**: Send current setpoint via CAN, then read feedback signal
- **Data collection pattern**: Follow DC Bus Sensing pattern for collecting CAN data and oscilloscope averages
- **Linear regression pattern**: Use numpy.polyfit or scipy.stats.linregress for calculating slope and intercept
- **Plot update pattern**: Update scatter plot after each setpoint (similar to Phase Current Test)
- **State management**: Consider using state machine pattern (like Phase Current Test) if test becomes complex

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
- [ ] DBC mode supported (required - test requires DBC file)
- [ ] Oscilloscope integration implemented correctly
- [ ] Linear regression calculation implemented
- [ ] Real-time plot updates during execution

### Testing Requirements
- [ ] Test with valid configuration
- [ ] Test with invalid configuration (should fail validation)
- [ ] Test with DBC loaded (required)
- [ ] Test execution produces correct results
- [ ] Error cases handled gracefully (oscilloscope not connected, channel not found, no data collected)
- [ ] Test with various current setpoint ranges and step sizes
- [ ] Test with different tolerance values
- [ ] Verify linear regression calculation accuracy
- [ ] Verify plot updates correctly during execution

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
- Use exact test type name consistently across all files: `"Output Current Calibration"`
- DBC mode is required (test does not support non-DBC mode)
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style
- Verify oscilloscope connection before test execution
- Implement linear regression for gain error calculation
- Update scatter plot after each setpoint completes

