# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `Analog Sweep Test`
- **Short Description**: `Sweeps DAC voltages from minimum to maximum in steps and monitors feedback signals`
- **Detailed Description**: 
  ```
  This test validates analog signal response by sweeping DAC (Digital-to-Analog Converter) voltages
  across a range and monitoring the corresponding feedback signals.
  
  How it works:
  - The test controls a MUX (multiplexer) to route the DAC output to the appropriate channel
  - Disables MUX, sets MUX channel, sets DAC to minimum voltage
  - Enables MUX to connect DAC output
  - Holds DAC at minimum voltage for dwell time while collecting feedback data
  - Incrementally increases DAC voltage by step size up to maximum voltage
  - At each voltage step, holds for dwell time and collects feedback data
  - Updates real-time plot (DAC voltage vs Feedback value) during data collection
  - Finally, sets DAC to 0mV and disables MUX for cleanup
  
  Hardware Requirements:
  - Device Under Test (DUT)
  - EOL Hardware with DAC and MUX
  - CAN Hardware (Canalystii or compatible)
  
  Special Considerations:
  - Test uses MUX control for signal routing
  - DAC commands are sent periodically (every 50ms) during dwell time to ensure reception
  - Data collection happens after a settling period to allow DAC to stabilize
  - Real-time plot updates during sweep (DAC voltage vs Feedback value)
  - Supports both DBC and non-DBC modes
  - Test clears signal cache before starting to ensure fresh timestamps
  ```

## Test Configuration Fields

### Required Fields
List all fields that must be provided for this test type:

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `dac_can_id` | `integer` | `CAN message ID for DAC command message` | `Range: 0-0x1FFFFFFF, Required` | `0x200` |
| `dac_command_signal` | `string` | `CAN signal name for DAC command` | `Non-empty, Required` | `"DAC_Command"` |
| `dac_min_mv` | `integer` | `Minimum DAC voltage in millivolts` | `Range: 0-5000, Required` | `0` |
| `dac_max_mv` | `integer` | `Maximum DAC voltage in millivolts` | `Range: 0-5000, Required, >= dac_min_mv` | `5000` |
| `dac_step_mv` | `integer` | `DAC voltage step size in millivolts` | `Minimum: 1, Required` | `500` |
| `dac_dwell_ms` | `integer` | `Dwell time per DAC voltage step in milliseconds` | `Minimum: 0, Default: 1000` | `1000` |

### Optional Fields

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `mux_enable_signal` | `string` | `Signal name for MUX enable` | `Optional` | `"MUX_Enable"` |
| `mux_channel_signal` | `string` | `Signal name for MUX channel selection` | `Optional` | `"MUX_Channel"` |
| `mux_channel_value` | `integer` | `MUX channel value to select` | `Optional` | `1` |
| `feedback_signal` | `string` | `Signal name for feedback (from test config, not actuation)` | `Optional` | `"Feedback_Voltage"` |
| `feedback_message_id` | `integer` | `CAN message ID for feedback signal (from test config, not actuation)` | `Optional` | `0x201` |

### CAN Message/Signal Fields
If the test uses CAN communication, specify:

- **Command Message** (sending commands to DUT/EOL):
  - Message ID: `dac_can_id` (configurable, e.g., 0x200)
  - Signals used: 
    - `dac_command_signal` - DAC voltage command (in millivolts)
    - `mux_enable_signal` - MUX enable (0 = disabled, 1 = enabled, optional)
    - `mux_channel_signal` - MUX channel selection (optional)
    - `DeviceID` - Device ID (if message is multiplexed, default: 0)
    - `MessageType` - Message type (if signal is multiplexed, typically MSG_TYPE_DAC_COMMAND)
  - Purpose: `Send DAC voltage commands and MUX control signals`

- **Feedback Messages** (reading measurements from DUT):
  - Message ID: `feedback_message_id` (from test config, optional)
  - Signals used: 
    - `feedback_signal` - Feedback signal from DUT (from test config, optional)
  - Purpose: `Read feedback signal from DUT for plotting against DAC voltage`

- **DBC Support**: `Yes` - Test works with DBC file loaded (dropdowns for messages/signals)
- **Non-DBC Support**: `Yes` - Test works without DBC file (free-text inputs for CAN IDs and values)

## Test Execution Logic

### Execution Flow
Describe the step-by-step execution flow:

```
1. Initialize Test
   - Action: 
     - Validate CAN ID, DAC parameters, and signals
     - Clear plot window
     - Clear signal cache to ensure fresh timestamps
   - Duration: As fast as possible
   - Expected result: Test ready, plot cleared, cache cleared

2. Disable MUX
   - Action: 
     - Send mux_enable_signal = 0 to disable MUX
     - Wait SLEEP_INTERVAL_SHORT (typically 50ms)
   - Duration: ~50ms
   - Expected result: MUX disabled (or already disabled)

3. Set MUX Channel
   - Action: 
     - Send mux_channel_signal = mux_channel_value to set channel
     - Wait SLEEP_INTERVAL_SHORT (typically 50ms)
   - Duration: ~50ms
   - Expected result: MUX channel set (if MUX channel signal provided)

4. Set DAC to Minimum
   - Action: 
     - Send dac_command_signal = dac_min_mv
     - Wait SLEEP_INTERVAL_SHORT (typically 50ms)
   - Duration: ~50ms
   - Expected result: DAC set to minimum voltage

5. Enable MUX
   - Action: 
     - Send mux_enable_signal = 1 (and mux_channel_signal if provided)
     - Wait SLEEP_INTERVAL_SHORT (typically 50ms)
   - Duration: ~50ms
   - Expected result: MUX enabled, DAC output connected

6. Hold at Minimum and Collect Data
   - Action: 
     - Continuously send DAC command (every 50ms) to maintain voltage
     - Wait for DAC_SETTLING_TIME_MS (typically 100ms) for DAC to stabilize
     - Collect feedback data during DATA_COLLECTION_PERIOD_MS (typically 200ms)
     - Update plot with (DAC voltage, feedback value) points
     - Continue holding DAC voltage for remaining dwell time
   - Duration: dac_dwell_ms milliseconds
   - Expected result: Multiple feedback data points collected at minimum voltage

7. Sweep DAC Voltage (Loop)
   - For each voltage step from (dac_min + dac_step) to dac_max:
     a. Set DAC to Current Voltage
        - Action: Send dac_command_signal = current_voltage
        - Duration: ~50ms
        - Expected result: DAC voltage updated
     
     b. Hold and Collect Data
        - Action: 
          - Continuously send DAC command (every 50ms) to maintain voltage
          - Wait for DAC_SETTLING_TIME_MS for DAC to stabilize
          - Collect feedback data during DATA_COLLECTION_PERIOD_MS
          - Update plot with (DAC voltage, feedback value) points
          - Continue holding DAC voltage for remaining dwell time
        - Duration: dac_dwell_ms milliseconds
        - Expected result: Multiple feedback data points collected at current voltage
   
   - Duration: (number_of_steps × dac_dwell_ms)
   - Expected result: Feedback data collected for all voltage steps

8. Cleanup
   - Action: 
     - Send dac_command_signal = 0 to set DAC to 0mV
     - Send mux_enable_signal = 0 to disable MUX
     - Wait SLEEP_INTERVAL_SHORT
   - Duration: ~100ms
   - Expected result: DAC set to 0, MUX disabled (system in safe state)

9. Store Plot Data
   - Action: 
     - Capture plot data (DAC voltages and feedback values) for test report
   - Duration: As fast as possible
   - Expected result: Plot data stored for later display
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `Test completes successfully (all DAC commands sent, data collected, cleanup performed)`
- **Fail Condition**: `Test fails if any critical step fails (DAC command fails, MUX control fails, etc.)`
- **Calculation Method**: 
  ```
  Note: Analog Sweep Test is primarily a data collection test. Pass/fail determination
  is typically done by analyzing the collected data (plot) after test completion.
  The test itself passes if:
  1. All DAC commands are sent successfully
  2. Data is collected at each voltage step
  3. Cleanup is performed successfully
  
  Data Analysis (post-test):
  - Plot shows DAC voltage vs Feedback value relationship
  - User or automated analysis can determine if relationship is linear, within expected range, etc.
  - No automatic pass/fail based on tolerance (unlike other test types)
  ```

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: 
  - `feedback_signal` from CAN (DUT feedback measurement, optional)
  - Measured DAC voltage from EOL hardware (if configured, optional)
  
- **Collection Duration**: `DATA_COLLECTION_PERIOD_MS` (typically 200ms) per voltage step, after `DAC_SETTLING_TIME_MS` (typically 100ms) settling period
  
- **Sampling Rate**: 
  - Polled during data collection period with optimized loop interval (25ms)
  - DAC command resent every 50ms to ensure reception
  - Plot updates batched every 50ms for improved performance
  
- **Data Processing**: 
  ```
  1. During Each Voltage Step:
     - Wait for DAC_SETTLING_TIME_MS after voltage change
     - Collect feedback data during DATA_COLLECTION_PERIOD_MS
     - Only use feedback values with timestamps after DAC command timestamp
     - Update plot with (measured_DAC_voltage, feedback_value) points
  
  2. Timestamp Validation:
     - Feedback values must have timestamps >= DAC command timestamp
     - Prevents using stale cached values from previous voltage steps
  
  3. Plot Updates:
     - Real-time plot updates during data collection
     - X-axis: DAC voltage (measured or commanded)
     - Y-axis: Feedback value
  ```

### Timing Requirements
Specify any timing requirements:

- **DAC Settling Time**: `DAC_SETTLING_TIME_MS` (typically 100ms) - Time for DAC to stabilize after voltage change
- **Data Collection Period**: `DATA_COLLECTION_PERIOD_MS` (typically 200ms) - Time to collect feedback data per step
- **DAC Command Periodicity**: `50ms` - Interval between DAC command resends during dwell time
- **Dwell Time**: `dac_dwell_ms` (default: 1000ms) - Total time to hold at each voltage step
- **Total Duration**: 
  ```
  Estimated total test duration:
  = initialization_time (≈0.1s)
  + MUX_setup_time (≈0.2s)
  + DAC_min_setup_time (≈0.1s)
  + (dac_dwell_ms × (1 + number_of_steps))
  + cleanup_time (≈0.1s)
  
  Example with dac_min_mv = 0, dac_max_mv = 5000, dac_step_mv = 500, dac_dwell_ms = 1000ms:
  number_of_steps = (5000 - 0) / 500 = 10 steps
  ≈ 0.1s + 0.2s + 0.1s + (1.0s × 11) + 0.1s
  ≈ 11.5 seconds
  ```

## GUI Requirements

### Create/Edit Dialog Fields
Specify the UI fields needed:

#### Field 1: DAC CAN ID
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x200)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 2: DAC Command Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 3: MUX Enable Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal (optional)` / `Enter signal name (optional)`
- **Validator**: `Non-empty string (if provided)`
- **DBC Mode**: `Dropdown (populated based on selected message, optional)`
- **Required**: `No`

#### Field 4: MUX Channel Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal (optional)` / `Enter signal name (optional)`
- **Validator**: `Non-empty string (if provided)`
- **DBC Mode**: `Dropdown (populated based on selected message, optional)`
- **Required**: `No`

#### Field 5: MUX Channel Value
- **Type**: `QSpinBox` or `QLineEdit` with QIntValidator
- **Placeholder**: `Enter channel value (optional)`
- **Validator**: `Integer (if provided)`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `No`

#### Field 6: DAC Minimum
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter minimum voltage in mV (e.g., 0)`
- **Validator**: `Integer 0-5000, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 7: DAC Maximum
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter maximum voltage in mV (e.g., 5000)`
- **Validator**: `Integer 0-5000, >= dac_min_mv, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 8: DAC Step
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter step size in mV (e.g., 500)`
- **Validator**: `Integer >= 1, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 9: Dwell Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter dwell time in milliseconds (e.g., 1000)`
- **Validator**: `Integer >= 0, Default: 1000`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `No (defaults to 1000ms)`

### Feedback Fields Visibility
- **Show Feedback Fields**: `Yes` - Test can use feedback signal for plotting (optional)
- **Custom Feedback Fields**: `No` - Uses standard feedback_signal and feedback_message_id from test config

### Plot Requirements
- **Needs Plot**: `Yes`
- **Plot Type**: `Scatter plot (X-Y plot)`
- **Plot Title**: `DUT Calculated Voltage vs DAC Voltage Plot`
- **X-Axis**: `DAC Voltage (mV)` - Commanded or measured DAC voltage
- **X-Axis Title**: `DAC Voltage`
- **Y-Axis**: `Feedback Value` - Feedback signal value from DUT
- **Y-Axis Title**: `DUT Calculated Voltage`
- **Update Frequency**: `During data collection period at each voltage step (real-time)`
- **Plot Features**: 
  - Real-time plot updates during test execution
  - Each point represents one data sample (DAC voltage, feedback value)
  - Plot shows relationship between DAC voltage and feedback response
  - Ideal calibration line (Y = X) displayed before test starts
  - Linear regression line displayed after test completion

### Real-Time Monitoring
The Real-Time Monitoring section displays the following signals during test execution:

- **Current Signal**: Displays the DAC voltage command value (in Volts, converted from millivolts)
  - Updates in real-time as DAC commands are sent
  - Format: `Current Signal : X.XX V`
  
- **Feedback Signal**: Displays the feedback signal value from DUT
  - Updates in real-time during data collection
  - Format: `Feedback Signal : X.XX <unit>` (unit depends on signal type)

The monitoring section automatically configures these labels when the test starts and clears them when the test completes. See [Real-Time Monitoring](../REAL_TIME_MONITORING.md) for detailed documentation.

## Validation Rules

### Schema Validation
Specify JSON schema requirements:

```json
{
  "properties": {
    "type": {"const": "Analog Sweep Test"},
    "mux_channel": {"type": ["integer", "null"]},
    "dac_can_id": {"type": "integer"},
    "dac_command": {"type": "string"}
  },
  "required": ["dac_can_id"]
}
```

### Application Validation
List validation checks to perform in `_validate_test()`:

- [x] Test type is in allowed list
- [x] Actuation type matches test type
- [x] `dac_can_id` is present and in valid range (0-0x1FFFFFFF)
- [x] `dac_command_signal` is present and non-empty
- [x] `dac_min_mv` is present and in valid range (0-5000)
- [x] `dac_max_mv` is present and in valid range (0-5000) and >= dac_min_mv
- [x] `dac_step_mv` is present and positive (>= 1)
- [x] `dac_dwell_ms` is non-negative (defaults to 1000 if not specified)

## Error Handling

### Expected Error Scenarios
List potential errors and how to handle them:

1. **Missing Required Field**
   - Error: `"Analog test requires dac_command_signal but none provided"`
   - Handling: Return `False, "Analog test failed: dac_command_signal is required but missing"`

2. **Invalid DAC CAN ID**
   - Error: `"Invalid DAC CAN ID"`
   - Handling: Return `False, "Invalid DAC CAN ID: {can_id}"`

3. **Invalid DAC Voltage Range**
   - Error: `"DAC max {dac_max} < min {dac_min}"`
   - Handling: Swap values and continue with warning, or return error

4. **DAC Command Failure**
   - Error: `"Failed to set DAC to minimum"`
   - Handling: Return `False, "Failed to send DAC command: {error}"`

5. **MUX Control Failure**
   - Error: `"Failed to disable MUX"`
   - Handling: Log warning and continue (MUX may already be disabled)

6. **No Feedback Data Collected**
   - Error: `"No feedback data collected"`
   - Handling: Test continues but plot may be empty (log warning)

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "Analog Sweep Test - Basic",
  "type": "Analog Sweep Test",
  "feedback_signal": "Feedback_Voltage",
  "feedback_message_id": 256,
  "actuation": {
    "type": "Analog Sweep Test",
    "dac_can_id": 256,
    "dac_command_signal": "DAC_Command",
    "mux_enable_signal": "MUX_Enable",
    "mux_channel_signal": "MUX_Channel",
    "mux_channel_value": 1,
    "dac_min_mv": 0,
    "dac_max_mv": 5000,
    "dac_step_mv": 500,
    "dac_dwell_ms": 1000
  }
}
```

### Example 2: Fine Step Sweep
```json
{
  "name": "Analog Sweep Test - Fine Steps",
  "type": "Analog Sweep Test",
  "feedback_signal": "Feedback_Voltage",
  "feedback_message_id": 256,
  "actuation": {
    "type": "Analog Sweep Test",
    "dac_can_id": 256,
    "dac_command_signal": "DAC_Command",
    "dac_min_mv": 0,
    "dac_max_mv": 5000,
    "dac_step_mv": 100,
    "dac_dwell_ms": 500
  }
}
```

## Implementation Notes

### Special Considerations
- **MUX Control**: Test controls MUX to route DAC output (optional but recommended)
- **Periodic DAC Commands**: DAC commands are resent every 50ms during dwell time to ensure reception
- **Settling Time**: Test waits for DAC to stabilize before collecting data
- **Timestamp Validation**: Only uses feedback values with timestamps after DAC command to avoid stale data
- **Signal Cache Clearing**: Test clears signal cache before starting to ensure fresh timestamps
- **Real-Time Plotting**: Plot updates in real-time during data collection
- **Plot Data Storage**: Plot data is captured and stored for test report

## Report Export

### HTML Export
Test results are automatically included in HTML report exports:
- Test details (name, type, status, execution time, parameters, notes)
- Calibration parameters table (if available):
  - Gain (Slope)
  - Offset
  - R² (Linearity)
  - Mean/Max Error
  - MSE
  - Data Points
  - Expected Gain (if available)
  - Gain Error (if available)
  - Tolerance Check (if available)
  - Gain Adjustment Factor (if available)
- Plot image: "Plot: Feedback vs DAC Output" with embedded PNG image

### PDF Export
Test results are automatically included in PDF report exports:
- Test details table with all test information
- Calibration parameters table (same as HTML export)
- Plot image embedded in PDF:
  - Title: "Plot: Feedback vs DAC Output"
  - Image size: 5x3 inches
  - **Plot title and image are kept together on the same page** using ReportLab's `KeepTogether` flowable to prevent page breaks between title and plot
- Professional formatting with consistent styling and spacing
- **DBC Support**: Test supports both DBC and non-DBC modes

### Dependencies
- **can_service**: Required for sending CAN commands and receiving feedback
- **dbc_service**: Optional but recommended for proper signal encoding/decoding
- **signal_service**: Required for reading feedback signals with timestamps
- **eol_hw_config**: Optional but recommended for measured DAC voltage (if available)

### Similar Test Types
- **Digital Logic Test**: Similar command/feedback pattern but for digital signals
- **Output Current Calibration**: Similar sweep pattern but for current setpoints
- **Phase Current Test**: Similar multi-step pattern but for phase current

### Testing Requirements
- Test with hardware connected (DUT, EOL hardware with DAC/MUX, CAN hardware)
- Test with valid DBC file loaded
- Test without DBC file (non-DBC mode)
- Test with various DAC voltage ranges and step sizes
- Test with different dwell times
- Test error cases (DAC command failure, MUX control failure, etc.)
- Verify real-time plot updates correctly
- Verify plot data is stored for test report
- Test with and without MUX control signals

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Output Current Calibration` (for sweep pattern)
- **Why Similar**: 
  - Both sweep through a range of values
  - Both collect data at each step
  - Both update plots in real-time
- **Key Differences**: 
  - Analog Sweep Test sweeps DAC voltages (not current setpoints)
  - Analog Sweep Test uses MUX control
  - Analog Sweep Test doesn't use oscilloscope
  - Analog Sweep Test doesn't calculate linear regression

### Code Patterns to Use
- **Sweep Pattern**: Loop through voltage range with step increments
- **MUX Control Pattern**: Disable → Set Channel → Enable sequence
- **Periodic Command Pattern**: Resend commands periodically during dwell time
- **Settling + Collection Pattern**: Wait for settling, then collect data
- **Timestamp Validation Pattern**: Only use feedback values with fresh timestamps
- **Real-Time Plot Pattern**: Update plot during data collection
- **Cleanup Pattern**: Set DAC to 0 and disable MUX at end

## Acceptance Criteria

### Functional Requirements
- [ ] Test type appears in create test dialog dropdown
- [ ] Test type appears in edit test dialog dropdown
- [ ] All configuration fields are displayed correctly
- [ ] Test can be created and saved successfully
- [ ] Test can be edited and saved successfully
- [ ] Validation works correctly (rejects invalid configurations)
- [ ] Test execution runs without errors
- [ ] Test execution returns success/failure results
- [ ] Test results appear in results table
- [ ] Test results appear in test report
- [ ] Plot data appears in test report
- [ ] JSON schema validation works

### Technical Requirements
- [ ] All files updated according to documentation
- [ ] Code follows existing patterns and style
- [ ] Error handling implemented
- [ ] Logging added for debugging
- [ ] Non-blocking sleep used (no `time.sleep()`)
- [ ] DBC mode supported
- [ ] Non-DBC mode supported
- [ ] MUX control implemented correctly
- [ ] Periodic DAC command resend implemented
- [ ] Timestamp validation implemented
- [ ] Signal cache clearing implemented
- [ ] Real-time plot updates implemented
- [ ] Plot data storage implemented

### Testing Requirements
- [ ] Test with valid configuration
- [ ] Test with invalid configuration (should fail validation)
- [ ] Test with DBC loaded
- [ ] Test without DBC loaded
- [ ] Test execution produces correct results
- [ ] Error cases handled gracefully (DAC command failure, MUX control failure, etc.)
- [ ] Test with various DAC voltage ranges and step sizes
- [ ] Test with different dwell times
- [ ] Verify real-time plot updates correctly
- [ ] Verify plot data is stored for test report
- [ ] Test with and without MUX control signals

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
- Use exact test type name consistently across all files: `"Analog Sweep Test"`
- Support both DBC and non-DBC modes
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style
- Implement MUX control sequence (disable → set channel → enable)
- Resend DAC commands periodically (every 50ms) during dwell time
- Wait for DAC settling time before collecting data
- Validate feedback timestamps to avoid stale data
- Clear signal cache before starting test
- Update plot in real-time during data collection (batched for performance)
- Store plot data for test report

## Performance Optimizations

The Analog Sweep Test implementation includes several performance optimizations to reduce execution time while maintaining data quality:

### 1. Optimized Loop Interval
- **Previous**: Data collection loop iterated every 5ms (SLEEP_INTERVAL_SHORT)
- **Optimized**: Data collection loop iterates every 25ms
- **Impact**: Reduces loop iteration overhead by ~80% (from ~100 iterations to ~20 iterations per 500ms collection period)
- **Data Quality**: Minimal impact - still collects sufficient data points for accurate analysis

### 2. Batched Plot Updates
- **Previous**: Plot updated for every data point collected (immediate updates)
- **Optimized**: Data points are batched and plot is updated every 50ms
- **Impact**: Reduces Qt thread-safe callback overhead by ~80% (from ~100 callbacks to ~10 callbacks per 500ms)
- **Data Quality**: No impact - all data points are still collected and displayed, just batched for efficiency

### 3. Encoded Frame Caching
- **Previous**: DAC commands were fully encoded on every send (every 50ms)
- **Optimized**: Encoded frames are cached when DAC voltage hasn't changed
- **Impact**: Eliminates redundant encoding operations for repeated DAC commands
- **Memory**: Cache limited to last 10 entries to prevent memory growth

### Performance Metrics

For a typical test configuration:
- **Voltage Range**: 0-5000mV
- **Step Size**: 100mV
- **Steps**: 50
- **Dwell Time**: 500ms per step

**Before Optimization**:
- Loop iterations: ~5,000 (50 steps × 100 iterations)
- Plot updates: ~5,000 (one per iteration)
- Encoding operations: ~2,500 (50ms command period)

**After Optimization**:
- Loop iterations: ~1,000 (50 steps × 20 iterations) - **80% reduction**
- Plot updates: ~500 (batched every 50ms) - **90% reduction**
- Encoding operations: ~50 (cached for repeated commands) - **98% reduction**

**Estimated Performance Improvement**: 30-40% faster test execution while maintaining equivalent data quality.

