# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `DC Bus Sensing`
- **Short Description**: `Validates DC bus voltage sensing by comparing DUT measurement with oscilloscope measurement`
- **Detailed Description**: 
  ```
  This test validates the DC bus voltage sensing accuracy by comparing measurements from two sources:
  1. DUT measurement via CAN bus (feedback signal)
  2. Oscilloscope measurement (reference measurement)
  
  How it works:
  - The test checks if the oscilloscope channel is enabled, and enables it if needed
  - Starts oscilloscope acquisition (TRMD AUTO) and CAN data logging simultaneously
  - Collects data from both sources during the dwell time
  - Stops oscilloscope acquisition and CAN logging
  - Queries oscilloscope for average value using "C{ch_num}:PAVA? MEAN" command
  - Calculates average from CAN feedback signal
  - Compares both averages: |osc_avg - can_avg| <= tolerance → PASS
  
  Hardware Requirements:
  - Device Under Test (DUT)
  - EOL Hardware
  - CAN Hardware (Canalystii)
  - Oscilloscope - Siglent SDS1104X-u (or compatible)
  - Voltage probe connected to oscilloscope channel
  
  Special Considerations:
  - Requires oscilloscope to be connected and configured before test execution
  - Test uses oscilloscope's PAVA? MEAN command for average calculation
  - Real-time display of CAN feedback signal during data collection
  - Supports both DBC and non-DBC modes
  ```

## Test Configuration Fields

### Required Fields
List all fields that must be provided for this test type:

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `oscilloscope_channel` | `string` | `Oscilloscope channel name (from loaded profile) for voltage measurement` | `Non-empty, Required, Must be enabled in profile` | `"DC Bus Voltage"` |
| `feedback_signal_source` | `integer` | `CAN message ID for feedback signal (DUT voltage measurement)` | `Range: 0-0x1FFFFFFF, Required` | `0x201` |
| `feedback_signal` | `string` | `CAN signal name for DC bus voltage feedback from DUT` | `Non-empty, Required` | `"DC_Bus_Voltage"` |
| `dwell_time_ms` | `integer` | `Time to collect data from both CAN and oscilloscope` | `Minimum: 1, Required` | `3000` |
| `tolerance_v` | `number` | `Tolerance in volts for pass/fail determination` | `Minimum: 0, Required` | `1.0` |

### CAN Message/Signal Fields
If the test uses CAN communication, specify:

- **Feedback Messages** (reading measurements from DUT):
  - Message ID: `feedback_signal_source` (configurable, e.g., 0x201)
  - Signals used: 
    - `feedback_signal` - DC bus voltage measured by DUT (in volts)
  - Purpose: `Read DC bus voltage measurement from DUT for comparison with oscilloscope`

- **DBC Support**: `Yes` - Test works with DBC file loaded (dropdowns for messages/signals)
- **Non-DBC Support**: `Yes` - Test works without DBC file (free-text inputs for CAN IDs and signal names)

## Test Execution Logic

### Execution Flow
Describe the step-by-step execution flow:

```
1. Verify Oscilloscope Channel
   - Action: 
     - Check if oscilloscope service is connected
     - Get oscilloscope configuration
     - Get channel number from oscilloscope_channel name
     - Query channel trace status using "C{ch_num}:TRA?" command
     - If channel is OFF, send "C{ch_num}:TRA ON" command
     - Verify channel is now ON
   - Duration: As fast as possible (typically < 1 second)
   - Expected result: Oscilloscope channel is enabled and ready

2. Start Data Acquisition
   - Action: 
     - Send "TRMD AUTO" command to oscilloscope to start acquisition
     - Start logging CAN feedback signal
     - Initialize data collection lists
   - Duration: As fast as possible
   - Expected result: Oscilloscope acquisition started, CAN logging started

3. Collect Data During Dwell Time
   - Action: 
     - Continuously read feedback_signal from CAN during dwell_time_ms
     - Store all CAN readings in list
     - Update real-time display with latest CAN value
     - Oscilloscope continues acquiring data
   - Duration: dwell_time_ms milliseconds
   - Expected result: Multiple CAN samples collected, oscilloscope data acquired

4. Stop Data Acquisition
   - Action: 
     - Stop logging CAN feedback signal
     - Send "STOP" command to oscilloscope to stop acquisition
   - Duration: As fast as possible
   - Expected result: CAN logging stopped, oscilloscope acquisition stopped

5. Query Oscilloscope Average
   - Action: 
     - Send "C{ch_num}:PAVA? MEAN" command to oscilloscope
     - Parse response to extract average voltage value
   - Duration: As fast as possible
   - Expected result: Oscilloscope average value obtained

6. Calculate CAN Average
   - Action: 
     - Calculate arithmetic mean of all collected CAN feedback values
   - Duration: As fast as possible
   - Expected result: CAN average calculated

7. Compare and Determine Pass/Fail
   - Action: 
     - Calculate absolute difference: |osc_avg - can_avg|
     - Compare difference with tolerance_v
     - PASS if difference <= tolerance_v
     - FAIL if difference > tolerance_v
   - Duration: As fast as possible
   - Expected result: Test result determined and returned
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `Absolute difference between oscilloscope average and CAN average is within tolerance (|osc_avg - can_avg| <= tolerance_v)`
- **Fail Condition**: `Absolute difference exceeds tolerance (|osc_avg - can_avg| > tolerance_v)`
- **Calculation Method**: 
  ```
  1. Collect Data:
     - Read feedback_signal continuously during dwell_time_ms
     - Store all CAN readings in feedback_values list
     - Oscilloscope acquires data during same period
  
  2. Calculate Averages:
     - CAN average: can_avg = sum(feedback_values) / len(feedback_values)
     - Oscilloscope average: osc_avg = result from "C{ch_num}:PAVA? MEAN" command
  
  3. Calculate Difference:
     - difference = abs(osc_avg - can_avg)
  
  4. Determine Pass/Fail:
     - PASS if difference <= tolerance_v
     - FAIL if difference > tolerance_v
  ```

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: 
  - `feedback_signal` from CAN (DUT voltage measurement)
  - Oscilloscope channel average (reference voltage measurement)
  
- **Collection Duration**: `dwell_time_ms` milliseconds
  
- **Sampling Rate**: 
  - CAN data: Logged continuously during dwell_time_ms (typically every 50-100ms via signal_service)
  - Oscilloscope: Continuous acquisition during dwell_time_ms, average computed after stop
  
- **Data Processing**: 
  ```
  1. CAN Data:
     - Collect all feedback_signal readings during dwell_time_ms
     - Calculate arithmetic mean (average) of all collected values
     - Store average for comparison
  
  2. Oscilloscope Data:
     - Start acquisition with "TRMD AUTO"
     - Let oscilloscope acquire data for dwell_time_ms
     - Stop acquisition with "STOP"
     - Query average using "C{ch_num}:PAVA? MEAN" command
     - Parse and store average value
  
  3. Comparison:
     - Calculate absolute difference between averages
     - Compare with tolerance
  ```

### Timing Requirements
Specify any timing requirements:

- **Channel Verification Time**: `~0.2-1.0 seconds` - Time to check and enable oscilloscope channel
- **Dwell Time**: `dwell_time_ms` (default: 3000ms) - Time to collect data from both CAN and oscilloscope
- **Polling Interval**: `SLEEP_INTERVAL_SHORT` (typically 50-100ms) - Interval between CAN signal readings
- **Total Duration**: 
  ```
  Estimated total test duration:
  = channel_verification_time (≈0.5s)
  + start_acquisition_time (≈0.2s)
  + dwell_time_ms
  + stop_acquisition_time (≈0.2s)
  + query_oscilloscope_time (≈0.1s)
  + analysis_time (≈0.1s)
  
  Example with dwell_time_ms = 3000ms:
  ≈ 0.5s + 0.2s + 3.0s + 0.2s + 0.1s + 0.1s
  ≈ 4.1 seconds
  ```

## GUI Requirements

### Create/Edit Dialog Fields
Specify the UI fields needed:

#### Field 1: Oscilloscope Channel
- **Type**: `QComboBox`
- **Placeholder**: `Select oscilloscope channel`
- **Validator**: `Must be from enabled channels in loaded profile`
- **DBC Mode**: `Dropdown (populated from oscilloscope profile)`
- **Required**: `Yes`

#### Field 2: Feedback Signal Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x201)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 3: Feedback Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 4: Dwell Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter dwell time in milliseconds (e.g., 3000)`
- **Validator**: `Integer >= 1, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 5: Tolerance
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter tolerance in volts (e.g., 1.0)`
- **Validator**: `Double >= 0.0, Required`
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
    "type": {"const": "DC Bus Sensing"},
    "oscilloscope_channel": {"type": "string"},
    "feedback_signal_source": {"type": "integer"},
    "feedback_signal": {"type": "string"},
    "dwell_time_ms": {"type": "integer", "minimum": 1},
    "tolerance_v": {"type": "number", "minimum": 0}
  },
  "required": [
    "oscilloscope_channel",
    "feedback_signal_source",
    "feedback_signal",
    "dwell_time_ms",
    "tolerance_v"
  ]
}
```

### Application Validation
List validation checks to perform in `_validate_test()`:

- [x] Test type is in allowed list
- [x] Actuation type matches test type
- [x] `oscilloscope_channel` is present and non-empty
- [x] `feedback_signal_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `feedback_signal` is present and non-empty
- [x] `dwell_time_ms` is present and positive (>= 1)
- [x] `tolerance_v` is present and non-negative
- [x] Oscilloscope service is available and connected
- [x] Oscilloscope channel exists in loaded profile

## Error Handling

### Expected Error Scenarios
List potential errors and how to handle them:

1. **Missing Required Field**
   - Error: `"Missing required DC Bus Sensing Test parameters"`
   - Handling: Return `False, "DC Bus Sensing Test requires {field_name}"`

2. **Invalid Field Value**
   - Error: `"Tolerance must be non-negative"`
   - Handling: Return `False, "Tolerance must be non-negative"`

3. **Oscilloscope Not Connected**
   - Error: `"Oscilloscope not connected"`
   - Handling: Return `False, "Oscilloscope not connected. Please connect oscilloscope before running DC Bus Sensing test."`

4. **Oscilloscope Channel Not Found**
   - Error: `"Channel not found in oscilloscope configuration"`
   - Handling: Return `False, "Channel '{oscilloscope_channel}' not found in oscilloscope configuration or not enabled"`

5. **Channel Enable Failure**
   - Error: `"Failed to enable channel"`
   - Handling: Return `False, "Failed to enable channel {channel_num} trace"`

6. **No CAN Data Collected**
   - Error: `"No CAN data collected"`
   - Handling: Return `False, "No CAN data collected during dwell time ({dwell_time_ms}ms). Check CAN connection and signal configuration."`

7. **Oscilloscope Query Failure**
   - Error: `"Failed to query oscilloscope average"`
   - Handling: Return `False, "Failed to query oscilloscope average: {error}"`

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "DC Bus Sensing - Basic",
  "type": "DC Bus Sensing",
  "actuation": {
    "type": "DC Bus Sensing",
    "oscilloscope_channel": "DC Bus Voltage",
    "feedback_signal_source": 256,
    "feedback_signal": "DC_Bus_Voltage",
    "dwell_time_ms": 3000,
    "tolerance_v": 1.0
  }
}
```

### Example 2: Extended Dwell Time
```json
{
  "name": "DC Bus Sensing - Extended",
  "type": "DC Bus Sensing",
  "actuation": {
    "type": "DC Bus Sensing",
    "oscilloscope_channel": "DC Bus Voltage",
    "feedback_signal_source": 256,
    "feedback_signal": "DC_Bus_Voltage",
    "dwell_time_ms": 5000,
    "tolerance_v": 0.5
  }
}
```

## Implementation Notes

### Special Considerations
- **Requires oscilloscope integration**: Test must verify oscilloscope connection and channel before execution
- **Oscilloscope PAVA Command**: Test uses "C{ch_num}:PAVA? MEAN" command to get average voltage
- **Channel Management**: Test automatically enables oscilloscope channel if it's OFF
- **Real-Time Display**: CAN feedback signal displayed in real-time during data collection
- **DBC Support**: Test supports both DBC and non-DBC modes

### Dependencies
- **oscilloscope_service**: Required for oscilloscope communication (TRA, TRMD, STOP, PAVA commands)
- **can_service**: Required for sending CAN commands and receiving feedback
- **dbc_service**: Optional but recommended for proper signal decoding
- **signal_service**: Required for reading CAN feedback signal during data collection

### Similar Test Types
- **Output Current Calibration**: Similar oscilloscope + CAN comparison pattern, uses PAVA? MEAN command
- **Analog Static Test**: Similar dual-signal comparison pattern but uses two CAN signals (no oscilloscope)
- **Temperature Validation Test**: Similar simple signal reading pattern but compares to reference value

### Testing Requirements
- Test with hardware connected (DUT, oscilloscope, CAN hardware)
- Test with valid DBC file loaded
- Test without DBC file (non-DBC mode)
- Test with oscilloscope connected and configured
- Test with various tolerance values
- Test with different dwell times
- Test error cases (oscilloscope not connected, channel not found, no data collected, etc.)
- Verify real-time CAN feedback display works correctly

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Output Current Calibration`
- **Why Similar**: 
  - Both compare oscilloscope measurements with CAN feedback
  - Both use PAVA? MEAN command for oscilloscope average
  - Both require oscilloscope channel verification
  - Both use TRMD AUTO and STOP commands
- **Key Differences**: 
  - DC Bus Sensing is simpler (single measurement, no setpoint loop)
  - DC Bus Sensing compares voltage (not current)
  - DC Bus Sensing doesn't require timebase configuration
  - DC Bus Sensing doesn't calculate linear regression

### Code Patterns to Use
- **Oscilloscope Setup Pattern**: Check and enable channel using TRA commands
- **Oscilloscope Acquisition Pattern**: Start with TRMD AUTO, stop with STOP, query with PAVA? MEAN
- **Dual Source Collection Pattern**: Collect from oscilloscope and CAN simultaneously
- **Average Calculation Pattern**: Calculate arithmetic mean of CAN values, query oscilloscope average
- **Reference Comparison Pattern**: Compare averages and check tolerance

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
- [ ] Oscilloscope integration implemented correctly

### Testing Requirements
- [ ] Test with valid configuration
- [ ] Test with invalid configuration (should fail validation)
- [ ] Test with DBC loaded
- [ ] Test without DBC loaded
- [ ] Test execution produces correct results
- [ ] Error cases handled gracefully (oscilloscope not connected, channel not found, no data collected, etc.)
- [ ] Test with various tolerance values
- [ ] Test with different dwell times
- [ ] Verify real-time CAN feedback display works correctly

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
- Use exact test type name consistently across all files: `"DC Bus Sensing"`
- Support both DBC and non-DBC modes
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style
- Verify oscilloscope connection before test execution
- Use PAVA? MEAN command for oscilloscope average
- Enable oscilloscope channel if it's OFF

