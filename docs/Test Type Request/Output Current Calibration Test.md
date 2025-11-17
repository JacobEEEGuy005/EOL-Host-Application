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
  - The test performs two sweeps to calibrate the output current sensor:
  
  First Sweep (Initial Calibration):
  - The test starts by verifying oscilloscope settings (timebase, channel enable, probe attenuation)
  - The output current trim value is initialized in the DUT using the initial_trim_value
  - The first current setpoint (from the test setpoints array) is sent to the DUT
  - A test trigger signal is sent to the DUT via CAN to initiate the calibration test mode
  - The EOL system sends remaining current setpoints from minimum to maximum values in steps
  - For each setpoint (including the first one that was sent before test trigger):
    * Wait for pre-acquisition time to allow current to stabilize
    * Start CAN data logging and oscilloscope acquisition
    * Collect data for the specified acquisition time
    * Stop data collection and calculate averages from both sources
    * Update live scatter plot (DUT measurement vs Oscilloscope measurement) for first sweep
  - After all setpoints are tested, perform linear regression on all (oscilloscope_avg, can_avg) pairs
  - Calculate slope and intercept from linear regression (same method as Analog Sweep Test)
  - Calculate the Gain Adjustment Factor from regression slope: gain_adjustment_factor = 1.0 / slope
  - Convert Gain Adjustment Factor to trim value: calculated_trim_value = 100 * gain_adjustment_factor
  
  Second Sweep (Verification):
  - Disable test mode at DUT
  - Initialize DUT with the calculated trim value (calculated_trim_value)
  - Send the first current setpoint again
  - Re-enable test mode at DUT
  - Repeat the same sweep pattern through all current setpoints
  - For each setpoint, collect data and update a second scatter plot (DUT measurement vs Oscilloscope measurement) for second sweep
  - After all setpoints are tested in second sweep, perform linear regression on all (oscilloscope_avg, can_avg) pairs
  - Calculate slope from linear regression and gain error: gain_error = (slope - 1.0) * 100.0
  - Test passes if gain error from the second sweep linear regression is within specified tolerance
  
  Results Display:
  - Both plots (first sweep and second sweep) are displayed in Test Detail window and in the report
  - Each plot is labeled with the trim value used (initial_trim_value for first sweep, calculated_trim_value for second sweep)
  - Test report includes: first sweep gain error (from regression), first sweep adjustment factor, calculated trim value, second sweep gain error (from regression), slope and intercept for both sweeps, and both plots
  
  Hardware Requirements:
  - Device Under Test (DUT)
    - EOL Hardware
    - CAN Hardware (Canalystii)
  - Oscilloscope - Siglent SDS1104X-u (or compatible)
  - Current probe connected to oscilloscope channel

  Special Considerations:
  - **Pre-Test Safety Dialog**: Before starting the test, the test sequence must pause and display a safety confirmation dialog. The dialog lists hardware connection requirements and asks the user to confirm before proceeding. If the user clicks "No", the test sequence pauses and the same dialog will appear again when the user resumes the sequence.
  - Requires oscilloscope to be connected and configured before test execution
  - Test iterates through multiple current setpoints (sweep pattern)
  - Real-time scatter plot updates during test execution
  - Calculates calibration parameters (slope, intercept, gain error, adjustment factor) for sensor trim using linear regression method (same as Analog Sweep Test)
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
| `output_current_trim_signal` | `string` | `CAN signal name for output current trim value (initialization)` | `Non-empty, Required` | `"Output_Current_Trim"` |
| `initial_trim_value` | `number` | `Initial trim value in percent to initialize DUT before test` | `Range: 0.0000-200.0000, Required, Default: 100.0000` | `100.0000` |
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
    - `output_current_trim_signal` - Set output current trim value in percent (value: `initial_trim_value`, range: 0.0000-200.0000%)
    - `test_trigger_signal` - Enable/disable output current test mode (value: `test_trigger_signal_value`, typically 1 to enable, 0 to disable)
    - `current_setpoint_signal` - Set output current setpoint value in Amperes
  - Purpose: `Send trim initialization, test trigger, and current setpoint commands to DUT`

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
0. Pre-Test Safety Dialog
   - Action: 
     1. Pause test sequence execution
     2. Display modal dialog with title "Pre-Test Safety Check - Output Current Calibration Test"
     3. Dialog content:
        - Requirements list:
          * "1. Ensure that AC Input is connected to a Regulated Power Supply with Maximum 60V and current limited."
          * "2. Ensure that DC Output is connected to a appropriate Low resistive load for current calibration."
        - Text: "Proceed to Run Test"
        - Buttons: "Yes" and "No"
     4. Wait for user response:
        - If user clicks "Yes": Continue to step 1
        - If user clicks "No": 
          * Pause test sequence (do not proceed)
          * User can resume test sequence later
          * When user resumes, return to step 0 (show dialog again)
   - Duration: User-dependent (until user responds)
   - Expected result: User confirms hardware connections are ready, or test sequence paused

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

2. Prepare Test Current Setpoints Array (First Sweep)
   - Action: 
     - Generate array of current setpoints from minimum_test_current to maximum_test_current 
       with step_current increments (e.g., [5.0, 10.0, 15.0, 20.0] A)
     - Clear plot window and initialize first scatter plot
     - Set X-axis label: "Oscilloscope Measurement (A)"
     - Set Y-axis label: "DUT Measurement (A)"
     - Initialize lists for storing CAN averages and oscilloscope averages for first sweep
   - Duration: As fast as possible
   - Expected result: Array of current setpoints ready, first plot initialized with correct labels

3. Initialize Trim Value at DUT (First Sweep)
    - Action: 
     - Encode and send CAN message with output_current_trim_signal = initial_trim_value (in percent, range: 0.0000-200.0000%)
       to initialize the output current trim value in the DUT before enabling test mode for first sweep
     - This sets the initial calibration trim value that will be used during the first sweep
   - Duration: As fast as possible
   - Expected result: Trim value initialization command sent successfully, DUT trim value initialized for first sweep

4. Send Initial Current Setpoint (First Sweep)
    - Action: 
     - Encode and send CAN message with current_setpoint_signal = first value from Test Current Setpoints Array
       to set the initial output current setpoint before enabling test mode for first sweep
     - This ensures the DUT starts at the first test setpoint value (e.g., minimum_test_current)
   - Duration: As fast as possible
   - Expected result: Initial current setpoint command sent successfully, DUT configured with first setpoint for first sweep

5. Trigger Test at DUT (First Sweep)
    - Action: 
     - Encode and send CAN message with test_trigger_signal = test_trigger_signal_value (typically 1)
       to enable output current test mode at DUT for first sweep
     - DUT will use the previously set trim value and initial current setpoint
   - Duration: As fast as possible
   - Expected result: Test trigger command sent successfully, DUT enters test mode for first sweep

6. Collect Data for First Setpoint (First Sweep)
   - Action: 
     - Wait for pre_acquisition_time_ms to allow current to stabilize at the first setpoint
     - Start CAN data logging and oscilloscope acquisition
     - Collect data during acquisition_time_ms
     - Stop data collection and calculate averages
     - Update first scatter plot with first data point
   - Duration: pre_acquisition_time_ms + acquisition_time_ms + analysis time
   - Expected result: Data collected for first setpoint in first sweep, first plot updated with first data point

7. For each remaining current setpoint in the array (first sweep, starting from the second setpoint, since first was already sent):
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
        - Update first scatter plot with point (oscilloscope_avg, can_avg)
    - Duration: As fast as possible
      - Expected result: Averages calculated and stored, first plot updated with new data point

8. First Sweep Post-Analysis
    - Action: 
     - Send test trigger signal with value 0 to disable test mode at DUT
     - Perform linear regression on first sweep data:
       * X-axis: oscilloscope_averages (reference measurements)
       * Y-axis: can_averages (DUT measurements)
       * Fit linear regression: can_avg = slope * osc_avg + intercept
       * Calculate slope and intercept using least squares method
     - Calculate gain error from regression slope:
       * first_sweep_gain_error = (slope - 1.0) * 100.0
     - Calculate adjustment factor from regression slope:
       * first_sweep_gain_adjustment_factor = 1.0 / slope (if slope != 0)
     - Calculate trim value: calculated_trim_value = 100 * first_sweep_gain_adjustment_factor
     - Store first sweep plot data with label indicating initial_trim_value, including slope and intercept
   - Duration: As fast as possible
   - Expected result: Test mode disabled, first sweep linear regression completed, trim value calculated

9. Initialize Second Sweep with Calculated Trim Value
    - Action: 
     - Encode and send CAN message with output_current_trim_signal = calculated_trim_value (in percent, range: 0.0000-200.0000%)
       to initialize the output current trim value in the DUT for the second sweep
     - **Clear plot window** (remove all data points from first sweep plot) before initializing second scatter plot
     - Initialize second scatter plot (fresh plot for second sweep)
     - Set X-axis label: "Oscilloscope Measurement (A)"
     - Set Y-axis label: "DUT Measurement (A)"
     - Initialize lists for storing CAN averages and oscilloscope averages for second sweep
   - Duration: As fast as possible
   - Expected result: Calculated trim value sent successfully, plot cleared, second plot initialized

10. Send Initial Current Setpoint for Second Sweep
    - Action: 
     - Encode and send CAN message with current_setpoint_signal = first value from Test Current Setpoints Array
       to set the initial output current setpoint before enabling test mode for second sweep
   - Duration: As fast as possible
   - Expected result: Initial current setpoint command sent successfully for second sweep

11. Trigger Test at DUT for Second Sweep
    - Action: 
     - Encode and send CAN message with test_trigger_signal = test_trigger_signal_value (typically 1)
       to enable output current test mode at DUT for second sweep
     - DUT will use the calculated trim value and initial current setpoint
   - Duration: As fast as possible
   - Expected result: Test trigger command sent successfully, DUT enters test mode for second sweep

12. Collect Data for First Setpoint (Second Sweep)
   - Action: 
     - Wait for pre_acquisition_time_ms to allow current to stabilize at the first setpoint
     - Start CAN data logging and oscilloscope acquisition
     - Collect data during acquisition_time_ms
     - Stop data collection and calculate averages
     - Update second scatter plot with first data point
   - Duration: pre_acquisition_time_ms + acquisition_time_ms + analysis time
   - Expected result: Data collected for first setpoint in second sweep, second plot updated with first data point

13. For each remaining current setpoint in the array (second sweep, starting from the second setpoint):
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
        - Update second scatter plot with point (oscilloscope_avg, can_avg)
    - Duration: As fast as possible
      - Expected result: Averages calculated and stored, second plot updated with new data point

14. Second Sweep Post-Test Analysis
    - Action: 
     - Send test trigger signal with value 0 to disable test mode at DUT
     - Perform linear regression on second sweep data:
       * X-axis: oscilloscope_averages (reference measurements)
       * Y-axis: can_averages (DUT measurements with calculated trim value applied)
       * Fit linear regression: can_avg = slope * osc_avg + intercept
       * Calculate slope and intercept using least squares method
     - Calculate gain error from regression slope:
       * second_sweep_gain_error = (slope - 1.0) * 100.0
     - Store second sweep plot data with label indicating calculated_trim_value, including slope and intercept
     - Determine pass/fail: pass if |second_sweep_gain_error| <= tolerance_percent
   - Duration: As fast as possible
   - Expected result: Test mode disabled, second sweep linear regression completed, pass/fail determined based on second sweep
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `Gain error percentage from second sweep linear regression is within tolerance_percent (second_sweep_gain_error <= tolerance_percent)`
- **Fail Condition**: `Gain error percentage from second sweep linear regression exceeds tolerance_percent (second_sweep_gain_error > tolerance_percent)`
- **Calculation Method**: 
  ```
  First Sweep Analysis:
  1. Collect data points: For each current setpoint in first sweep, collect:
     - CAN average: average of all CAN feedback_signal readings during acquisition_time_ms
     - Oscilloscope average: result from "C{ch_num}:PAVA? MEAN" command
  
  2. Perform linear regression on first sweep data:
     - X-axis: oscilloscope_averages (reference measurements)
     - Y-axis: can_averages (DUT measurements)
     - Fit linear regression: can_avg = slope * osc_avg + intercept
     - Calculate slope using least squares method:
       * slope = (n*Σ(osc_avg * can_avg) - Σ(osc_avg) * Σ(can_avg)) / (n*Σ(osc_avg²) - (Σ(osc_avg))²)
     - Calculate intercept:
       * intercept = (Σ(can_avg) - slope * Σ(osc_avg)) / n
     - Ideal slope = 1.0 (perfect calibration)
  
  3. Calculate gain error and adjustment factor from first sweep:
     - Gain error: first_sweep_gain_error = ((slope - 1.0) / 1.0) * 100.0 = (slope - 1.0) * 100.0
     - Adjustment factor: first_sweep_gain_adjustment_factor = 1.0 / slope (if slope != 0)
     - This adjustment factor corrects the DUT measurement to match oscilloscope reference
  
  4. Calculate trim value for second sweep:
     - calculated_trim_value = 100 * first_sweep_gain_adjustment_factor
     - This converts the adjustment factor to a percentage trim value
  
  Second Sweep Analysis:
  5. Collect data points: For each current setpoint in second sweep, collect:
     - CAN average: average of all CAN feedback_signal readings during acquisition_time_ms
     - Oscilloscope average: result from "C{ch_num}:PAVA? MEAN" command
  
  6. Perform linear regression on second sweep data:
     - X-axis: oscilloscope_averages (reference measurements)
     - Y-axis: can_averages (DUT measurements with calculated trim value applied)
     - Fit linear regression: can_avg = slope * osc_avg + intercept
     - Calculate slope using least squares method:
       * slope = (n*Σ(osc_avg * can_avg) - Σ(osc_avg) * Σ(can_avg)) / (n*Σ(osc_avg²) - (Σ(osc_avg))²)
     - Calculate intercept:
       * intercept = (Σ(can_avg) - slope * Σ(osc_avg)) / n
  
  7. Calculate gain error from second sweep:
     - Gain error: second_sweep_gain_error = ((slope - 1.0) / 1.0) * 100.0 = (slope - 1.0) * 100.0
     - This measures how well the calibrated DUT matches the reference after applying trim value
  
  8. Determine pass/fail (based on second sweep only):
     - PASS if |second_sweep_gain_error| <= tolerance_percent
     - FAIL if |second_sweep_gain_error| > tolerance_percent
  
  Note: This method uses linear regression (same as Analog Sweep Test) to fit a line through
  all data points and calculate a single slope value. The gain error is calculated from the
  deviation of the slope from the ideal value of 1.0. The pass/fail determination is based
  solely on the second sweep gain error after applying the calculated trim value.
  ```

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: 
  - `feedback_signal` from CAN (DUT current measurement)
  - Oscilloscope channel average (reference current measurement)
  
- **Collection Duration**: `acquisition_time_ms` milliseconds per setpoint (applies to both sweeps)
  
- **Sampling Rate**: 
  - CAN data: Logged continuously during acquisition_time_ms (typically every 50-100ms via signal_service)
  - Oscilloscope: Continuous acquisition during acquisition_time_ms, average computed after stop
  
- **Data Processing**: 
  ```
  First Sweep Data Processing:
  1. CAN Data:
     - Collect all feedback_signal readings during acquisition_time_ms for each setpoint
     - Calculate arithmetic mean (average) of all collected values
     - Store average for this setpoint
  
  2. Oscilloscope Data:
     - Start acquisition with "TRMD AUTO"
     - Let oscilloscope acquire data for acquisition_time_ms
     - Stop acquisition with "STOP"
     - Query average using "C{ch_num}:PAVA? MEAN" command
     - Parse and store average value for this setpoint
  
  3. First Sweep Linear Regression Analysis:
     - Collect all (oscilloscope_avg, can_avg) pairs from first sweep
     - Perform linear regression: can_avg = slope * osc_avg + intercept
     - Calculate slope using least squares:
       * n = number of data points
       * slope = (n*Σ(osc_avg * can_avg) - Σ(osc_avg) * Σ(can_avg)) / (n*Σ(osc_avg²) - (Σ(osc_avg))²)
     - Calculate intercept:
       * intercept = (Σ(can_avg) - slope * Σ(osc_avg)) / n
     - Calculate gain error: first_sweep_gain_error = (slope - 1.0) * 100.0
     - Calculate adjustment factor: first_sweep_gain_adjustment_factor = 1.0 / slope (if slope != 0)
     - Calculate trim value: calculated_trim_value = 100 * first_sweep_gain_adjustment_factor
     - Store first sweep plot data with label indicating initial_trim_value, including slope and intercept
  
  Second Sweep Data Processing:
  4. CAN Data (Second Sweep):
     - Collect all feedback_signal readings during acquisition_time_ms for each setpoint
     - Calculate arithmetic mean (average) of all collected values
     - Store average for this setpoint
  
  5. Oscilloscope Data (Second Sweep):
     - Start acquisition with "TRMD AUTO"
     - Let oscilloscope acquire data for acquisition_time_ms
     - Stop acquisition with "STOP"
     - Query average using "C{ch_num}:PAVA? MEAN" command
     - Parse and store average value for this setpoint
  
  6. Second Sweep Linear Regression Analysis:
     - Collect all (oscilloscope_avg, can_avg) pairs from second sweep
     - Perform linear regression: can_avg = slope * osc_avg + intercept
     - Calculate slope using least squares:
       * n = number of data points
       * slope = (n*Σ(osc_avg * can_avg) - Σ(osc_avg) * Σ(can_avg)) / (n*Σ(osc_avg²) - (Σ(osc_avg))²)
     - Calculate intercept:
       * intercept = (Σ(can_avg) - slope * Σ(osc_avg)) / n
     - Calculate gain error: second_sweep_gain_error = (slope - 1.0) * 100.0
     - Store second sweep plot data with label indicating calculated_trim_value, including slope and intercept
     - Use |second_sweep_gain_error| for pass/fail determination
  ```

### Timing Requirements
Specify any timing requirements:

- **Pre-Acquisition Time**: `pre_acquisition_time_ms` (default: 1000ms) - Wait time after setting current setpoint before starting data collection (applies to both sweeps)
- **Acquisition Time**: `acquisition_time_ms` (default: 3000ms) - Time to collect data from both CAN and oscilloscope per setpoint (applies to both sweeps)
- **Post-Acquisition Time**: Not required - Analysis happens immediately after data collection
- **Total Duration**: 
  ```
  Estimated total test duration (includes both sweeps):
  = oscilloscope_setup_time (≈1s)
  + first_sweep_trim_initialization_time (≈0.1s)
  + first_sweep_first_setpoint_send_time (≈0.1s)
  + first_sweep_trigger_time (≈0.1s)
  + first_sweep_first_setpoint_data_collection (pre_acquisition_time_ms + acquisition_time_ms + analysis_time)
  + first_sweep_remaining_setpoints (number_of_setpoints - 1) × (setpoint_send_time + pre_acquisition_time_ms + acquisition_time_ms + analysis_time)
  + first_sweep_post_analysis_time (≈0.5s)
  + second_sweep_trim_initialization_time (≈0.1s)
  + second_sweep_first_setpoint_send_time (≈0.1s)
  + second_sweep_trigger_time (≈0.1s)
  + second_sweep_first_setpoint_data_collection (pre_acquisition_time_ms + acquisition_time_ms + analysis_time)
  + second_sweep_remaining_setpoints (number_of_setpoints - 1) × (setpoint_send_time + pre_acquisition_time_ms + acquisition_time_ms + analysis_time)
  + second_sweep_post_analysis_time (≈0.5s)
  
  Example with 4 setpoints (5A, 10A, 15A, 20A), 1000ms pre-acq, 3000ms acq:
  First Sweep:
  ≈ 1s + 0.1s + 0.1s + 0.1s + (1s + 3s + 0.2s) + 3 × (0.1s + 1s + 3s + 0.2s) + 0.5s
  ≈ 1.3s + 4.2s + 3 × 4.3s + 0.5s
  ≈ 1.3s + 4.2s + 12.9s + 0.5s
  ≈ 18.9 seconds
  
  Second Sweep:
  ≈ 0.1s + 0.1s + 0.1s + (1s + 3s + 0.2s) + 3 × (0.1s + 1s + 3s + 0.2s) + 0.5s
  ≈ 0.3s + 4.2s + 12.9s + 0.5s
  ≈ 17.9 seconds
  
  Total: ≈ 18.9s + 17.9s ≈ 36.8 seconds
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

#### Field 5: Output Current Trim Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on test trigger source message)`
- **Required**: `Yes`

#### Field 6: Initial Trim Value
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter initial trim value in percent (e.g., 100.0000)`
- **Validator**: `Double 0.0000-200.0000, Default: 100.0000`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 7: Feedback Signal Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x201)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 8: Feedback Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 9: Oscilloscope Channel
- **Type**: `QComboBox`
- **Placeholder**: `Select oscilloscope channel`
- **Validator**: `Must be from enabled channels in loaded profile`
- **DBC Mode**: `Dropdown (populated from oscilloscope profile)`
- **Required**: `Yes`

#### Field 10: Oscilloscope Timebase
- **Type**: `QComboBox`
- **Placeholder**: `Select timebase`
- **Validator**: `One of: '10MS', '20MS', '100MS', '500MS'`
- **DBC Mode**: `Dropdown (same for both modes)`
- **Required**: `Yes`

#### Field 11: Minimum Test Current
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter minimum current in Amperes (e.g., 5.0)`
- **Validator**: `Double >= 0.0, Default: 5.0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 12: Maximum Test Current
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter maximum current in Amperes (e.g., 20.0)`
- **Validator**: `Double >= minimum_test_current, Default: 20.0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 13: Step Current
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter step size in Amperes (e.g., 5.0)`
- **Validator**: `Double >= 0.1, Default: 5.0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 14: Pre-Acquisition Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter pre-acquisition time in milliseconds (e.g., 1000)`
- **Validator**: `Integer >= 0, Default: 1000`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 15: Acquisition Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter acquisition time in milliseconds (e.g., 3000)`
- **Validator**: `Integer >= 1, Default: 3000`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 16: Tolerance
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter tolerance in percent (e.g., 1.0)`
- **Validator**: `Double >= 0.0, Default: 1.0`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

### Feedback Fields Visibility
- **Show Feedback Fields**: `No` - This test type has its own feedback fields (feedback_signal_source and feedback_signal)
- **Custom Feedback Fields**: `Yes` - Uses feedback_signal_source and feedback_signal for DUT current measurement

### Pre-Test Safety Dialog Requirements
- **Show Pre-Test Dialog**: `Yes` - Dialog must appear before test execution starts
- **Dialog Type**: `QMessageBox` or custom `QDialog` with modal blocking
- **Dialog Title**: `"Pre-Test Safety Check - Output Current Calibration Test"`
- **Dialog Content**: 
  - Requirements list (bulleted):
    1. "Ensure that AC Input is connected to a Regulated Power Supply with Maximum 60V and current limited."
    2. "Ensure that DC Output is connected to a appropriate Low resistive load for current calibration."
  - Confirmation text: "Proceed to Run Test"
- **Dialog Buttons**: 
  - "Yes" button (default/accept) - Proceeds with test execution
  - "No" button (reject) - Pauses test sequence
- **Dialog Behavior**:
  - Modal dialog (blocks test execution until user responds)
  - If "Yes": Dialog closes, test proceeds to step 1
  - If "No": Dialog closes, test sequence pauses, user can resume later
  - On resume: Dialog appears again (same content and behavior)
- **Implementation Notes**:
  - Dialog should be shown before any test initialization or CAN communication
  - Dialog must be shown in the main GUI thread (not in background test thread)
  - Test sequence pause/resume mechanism should be used for "No" response
  - Dialog should be non-dismissible (user must click Yes or No)

### Plot Requirements
- **Needs Plot**: `Yes` - Two plots required (one for each sweep)
- **Plot Type**: `Scatter plot (X-Y plot)` - Two separate scatter plots
- **X-Axis**: `Oscilloscope Measurement (A)` - Reference measurement from oscilloscope
- **Y-Axis**: `DUT Measurement (A)` - DUT measurement from CAN feedback signal
- **Update Frequency**: `After each setpoint completes (after calculating averages from CAN and oscilloscope)`
- **Plot Features**: 
  - **First Sweep Plot**:
    - Real-time scatter plot updates during first sweep execution
    - Each point represents one current setpoint from first sweep
    - Plot title/label should indicate: "First Sweep (Trim Value: {initial_trim_value}%)"
    - Ideal calibration line (Y = X) can be displayed for reference
    - Regression line (from linear regression) should be displayed showing slope and intercept
    - Plot shows data points, ideal line, and regression line
  
  - **Second Sweep Plot**:
    - **Plot must be cleared before second sweep starts** (clear plot window after first sweep completes)
    - Real-time scatter plot updates during second sweep execution
    - Each point represents one current setpoint from second sweep
    - Plot title/label should indicate: "Second Sweep (Trim Value: {calculated_trim_value}%)"
    - Ideal calibration line (Y = X) can be displayed for reference
    - Regression line (from linear regression) should be displayed showing slope and intercept
    - Plot shows data points, ideal line, and regression line
  
  - **Display Requirements**:
    - Both plots must be displayed in the Test Detail window during and after test execution
    - Both plots must be included in the test report
    - Each plot must be clearly labeled with the trim value used for that sweep

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
    "output_current_trim_signal": {"type": "string"},
    "initial_trim_value": {"type": "number", "minimum": 0.0, "maximum": 200.0},
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
    "output_current_trim_signal",
    "initial_trim_value",
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
- [x] `output_current_trim_signal` is present and non-empty
- [x] `initial_trim_value` is present and in range (0.0000-200.0000)
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
     - `initial_trim_value` must be 0.0000-200.0000
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
   - Error: `"Insufficient data points for linear regression"`
   - Handling: Return `False, "Insufficient data points collected. Need at least 2 setpoints for linear regression, got {count}. Check CAN connection and signal configuration."`
  
9. **Linear Regression Failure (First Sweep)**
   - Error: `"Failed to perform linear regression on first sweep data"`
   - Handling: Return `False, "Failed to perform linear regression on first sweep data. Check data quality and ensure oscilloscope and CAN measurements are valid. Need at least 2 valid data points."`
   - Examples:
     - Denominator too small (data may be constant)
     - All data points are invalid (NaN or infinity)
     - Slope calculation results in invalid value

10. **Invalid Calculated Trim Value**
    - Error: `"Calculated trim value out of range"`
    - Handling: Return `False, "Calculated trim value ({calculated_trim_value}%) is out of valid range (0.0000-200.0000%). Check first sweep data quality."`

11. **No CAN Data Collected (Second Sweep)**
    - Error: `"No CAN data collected at setpoint {setpoint} in second sweep"`
    - Handling: Return `False, "No CAN data collected at setpoint {setpoint}A in second sweep. Check CAN connection and signal configuration."`

12. **Oscilloscope Data Acquisition Failure (Second Sweep)**
    - Error: `"Failed to acquire oscilloscope data in second sweep"`
    - Handling: Return `False, "Failed to acquire oscilloscope data at setpoint {setpoint}A in second sweep: {error}"`

13. **Insufficient Data Points (Second Sweep)**
    - Error: `"Insufficient data points for analysis in second sweep"`
    - Handling: Return `False, "Insufficient data points collected in second sweep. Need at least 2 setpoints, got {count}. Check CAN connection and signal configuration."`
  
14. **Linear Regression Failure (Second Sweep)**
    - Error: `"Failed to perform linear regression on second sweep data"`
    - Handling: Return `False, "Failed to perform linear regression on second sweep data. Check data quality and ensure oscilloscope and CAN measurements are valid. Need at least 2 valid data points."`
    - Examples:
      - Denominator too small (data may be constant)
      - All data points are invalid (NaN or infinity)
      - Slope calculation results in invalid value

15. **DBC Service Not Available**
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
    "output_current_trim_signal": "Output_Current_Trim",
    "initial_trim_value": 100.0000,
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
    "output_current_trim_signal": "Output_Current_Trim",
    "initial_trim_value": 100.0000,
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
- **Pre-Test Safety Dialog**: Before test execution begins, a modal safety confirmation dialog must be displayed. The dialog lists two hardware connection requirements and asks the user to confirm readiness. If the user clicks "No", the test sequence pauses and the dialog will reappear when the user resumes the sequence. This ensures proper hardware connections before starting the test, which is critical for safety and test validity. The dialog must be shown in the main GUI thread before any test initialization occurs.
- **Requires oscilloscope integration**: Test must verify oscilloscope connection and configuration before execution
- **Two-sweep calibration pattern**: Test performs two complete sweeps - first sweep calculates trim value, second sweep verifies calibration
- **Multi-step test pattern**: Each sweep iterates through multiple current setpoints (similar to Analog Sweep Test)
- **Real-time plotting**: Two scatter plots must update after each setpoint completes (one for each sweep)
- **Linear regression calculation**: Final analysis uses linear regression to fit a line through all data points and calculate slope/intercept (same method as Analog Sweep Test)
- **Calibration parameter calculation**: 
  - First sweep: Performs linear regression on (oscilloscope_avg, can_avg) pairs to calculate slope
  - Calculates gain error from slope: first_sweep_gain_error = (slope - 1.0) * 100.0
  - Calculates adjustment factor from slope: first_sweep_gain_adjustment_factor = 1.0 / slope
  - Converts adjustment factor to trim value: calculated_trim_value = 100 * gain_adjustment_factor
  - Second sweep: Performs linear regression on second sweep data to calculate slope and gain error
- **Pass/fail based on second sweep**: Test pass/fail determination uses only the second sweep gain error from linear regression
- **Dual plot display**: Both plots (first sweep and second sweep) must be displayed in Test Detail window and included in test report, each labeled with its trim value
- **Regression line display**: Plots should optionally display the regression line (slope and intercept) for visualization
- **Test results reporting**: Report must include first sweep gain error (from regression), first sweep adjustment factor, calculated trim value, second sweep gain error (from regression), and both plots
- **DBC required**: Test requires DBC file to be loaded for proper CAN message encoding/decoding
- **State management**: Test maintains state across multiple setpoints and two sweeps (oscilloscope setup, data collection, analysis, plot management)

### Dependencies
- **oscilloscope_service**: Required for oscilloscope communication (TDIV, TRA, TRMD, STOP, PAVA commands)
- **can_service**: Required for sending CAN commands and receiving feedback
- **dbc_service**: Required for encoding/decoding CAN messages (test requires DBC file)
- **signal_service**: Required for reading CAN feedback signal during data collection
- **numpy** (optional): Recommended for linear regression calculation, but can be implemented with simple arithmetic operations (least squares method)

### Similar Test Types
- **Analog Sweep Test**: Similar linear regression calculation method, multi-step sweep pattern, iterates through values and collects feedback
- **DC Bus Sensing**: Similar oscilloscope + CAN comparison pattern, uses PAVA? MEAN command
- **Phase Current Test**: Similar oscilloscope integration pattern, multi-step current testing, real-time plotting (but uses point-by-point calculation, not linear regression)
- **Temperature Validation Test**: Similar reference comparison pattern (though simpler, single measurement)

### Testing Requirements
- Test with hardware connected (DUT, oscilloscope, CAN hardware)
- Test with valid DBC file loaded (test requires DBC for signal encoding)
- Test with oscilloscope connected and configured
- Test with various current setpoint ranges and step sizes
- Test with different tolerance values
- Test error cases (oscilloscope not connected, channel not found, no data collected)
- Test error cases for second sweep (invalid calculated trim value, no data in second sweep)
- Test with different oscilloscope timebase settings
- Verify linear regression calculation accuracy for both sweeps (slope, intercept)
- Verify gain error calculation from regression slope for both sweeps
- Verify trim value calculation (calculated_trim_value = 100 * gain_adjustment_factor)
- Verify both plots update correctly during execution (first sweep and second sweep)
- Verify both plots are displayed in Test Detail window with correct labels
- Verify both plots are included in test report with correct labels
- Verify test results include: first sweep gain error (from regression), first sweep adjustment factor, calculated trim value, second sweep gain error (from regression), slope and intercept for both sweeps
- Verify pass/fail determination uses only second sweep gain error from linear regression

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Analog Sweep Test` and `DC Bus Sensing`
- **Why Similar**: 
  - Analog Sweep Test: Similar pattern of linear regression calculation, multi-step sweep pattern, and real-time plotting
  - DC Bus Sensing: Similar pattern of comparing oscilloscope measurements with CAN feedback, using PAVA? MEAN command, and scatter plot visualization
- **Key Differences**: 
  - Output Current Calibration focuses on output current (not DAC voltage)
  - Uses linear regression calculation method (same as Analog Sweep Test)
  - Calculates calibration parameters (slope, intercept, gain error, adjustment factor) for sensor trim
  - Iterates through current setpoints sent via CAN (not DAC voltage steps)
  - Uses oscilloscope for reference measurement (not EOL hardware)
  - Performs two sweeps (first calculates trim, second verifies)

### Code Patterns to Use
- **Pre-Test Dialog Pattern**: Show modal dialog before test execution, pause sequence if user declines, re-show dialog on resume. Dialog should be shown in main GUI thread using QMessageBox or QDialog with proper signal/slot connection to test execution thread.
- **Oscilloscope setup pattern**: Follow DC Bus Sensing pattern for oscilloscope verification (TDIV, TRA commands)
- **Multi-step iteration pattern**: Follow Analog Sweep Test pattern for iterating through setpoints
- **CAN command + feedback pattern**: Send current setpoint via CAN, then read feedback signal
- **Data collection pattern**: Follow DC Bus Sensing pattern for collecting CAN data and oscilloscope averages
- **Linear regression pattern**: Use Analog Sweep Test pattern for linear regression calculation (slope, intercept, gain error)
- **Plot update pattern**: Update scatter plot after each setpoint (similar to Phase Current Test)
- **State management**: Consider using state machine pattern (like Phase Current Test) if test becomes complex
- **Test Sequence Pause/Resume Pattern**: Use test execution thread pause/resume mechanism when user clicks "No" in pre-test dialog

## Acceptance Criteria

### Functional Requirements
- [ ] Test type appears in create test dialog dropdown
- [ ] Test type appears in edit test dialog dropdown
- [ ] All configuration fields are displayed correctly
- [ ] Test can be created and saved successfully
- [ ] Test can be edited and saved successfully
- [ ] Validation works correctly (rejects invalid configurations)
- [ ] Pre-test safety dialog appears before test execution starts
- [ ] Pre-test dialog shows correct requirements (AC Input and DC Output connections)
- [ ] Pre-test dialog "Yes" button proceeds with test execution
- [ ] Pre-test dialog "No" button pauses test sequence
- [ ] Pre-test dialog reappears when test sequence is resumed after "No" response
- [ ] Test execution runs without errors
- [ ] Test execution returns correct pass/fail results
- [ ] Test results appear in results table
- [ ] Test results appear in test report
- [ ] JSON schema validation works

### Technical Requirements
- [ ] All files updated according to documentation
- [ ] Code follows existing patterns and style
- [ ] Error handling implemented (including second sweep error cases)
- [ ] Logging added for debugging
- [ ] Non-blocking sleep used (no `time.sleep()`)
- [ ] DBC mode supported (required - test requires DBC file)
- [ ] Pre-test safety dialog implemented correctly (modal, blocks execution, pause/resume integration)
- [ ] Oscilloscope integration implemented correctly
- [ ] Linear regression calculation implemented (same as Analog Sweep Test) for both sweeps
- [ ] Two-sweep execution pattern implemented correctly
- [ ] Trim value calculation implemented: calculated_trim_value = 100 * gain_adjustment_factor
- [ ] Real-time plot updates during execution (both sweeps)
- [ ] Dual plot display implemented (first sweep and second sweep plots)
- [ ] Plot labels include trim values (initial_trim_value for first sweep, calculated_trim_value for second sweep)
- [ ] Regression line optionally displayed on plots (slope and intercept)
- [ ] Test results include: first sweep gain error (from regression), first sweep adjustment factor, calculated trim value, second sweep gain error (from regression), slope and intercept for both sweeps
- [ ] Pass/fail determination uses only second sweep gain error from linear regression

### Testing Requirements
- [ ] Test with valid configuration
- [ ] Test with invalid configuration (should fail validation)
- [ ] Test with DBC loaded (required)
- [ ] Pre-test dialog appears before test execution
- [ ] Pre-test dialog "Yes" button proceeds correctly
- [ ] Pre-test dialog "No" button pauses sequence correctly
- [ ] Pre-test dialog reappears on resume after "No" response
- [ ] Test execution produces correct results (both sweeps complete)
- [ ] Error cases handled gracefully (oscilloscope not connected, channel not found, no data collected)
- [ ] Error cases for second sweep handled gracefully (invalid calculated trim value, no data in second sweep)
- [ ] Test with various current setpoint ranges and step sizes
- [ ] Test with different tolerance values
- [ ] Verify linear regression calculation accuracy for both sweeps (slope, intercept)
- [ ] Verify gain error calculation from regression slope for both sweeps
- [ ] Verify trim value calculation accuracy
- [ ] Verify both plots update correctly during execution (first sweep and second sweep)
- [ ] Verify both plots are displayed in Test Detail window with correct labels
- [ ] Verify both plots are included in test report with correct labels
- [ ] Verify test results include all required values (first sweep gain error from regression, adjustment factor, calculated trim value, second sweep gain error from regression, slope and intercept for both sweeps)
- [ ] Verify pass/fail determination uses only second sweep gain error from linear regression

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
5. Implement pre-test safety dialog (modal dialog with Yes/No, pause sequence on No, re-show on resume)
6. Implement execution logic
7. Test thoroughly with both valid and invalid configurations
7. Ensure all acceptance criteria are met

### Key Reminders
- Use exact test type name consistently across all files: `"Output Current Calibration"`
- DBC mode is required (test does not support non-DBC mode)
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style
- **Implement pre-test safety dialog before test execution starts** - Show modal dialog with hardware connection requirements, pause sequence if user clicks "No", re-show dialog when user resumes
- Verify oscilloscope connection before test execution
- Implement two-sweep execution pattern:
  - First sweep: Use initial_trim_value, perform linear regression, calculate gain adjustment factor from slope, convert to trim value (calculated_trim_value = 100 * gain_adjustment_factor)
  - Second sweep: Use calculated_trim_value, perform linear regression, calculate gain error from slope for pass/fail determination
- Implement linear regression calculation (same method as Analog Sweep Test) for both sweeps:
  - X-axis: oscilloscope_averages (reference)
  - Y-axis: can_averages (DUT measurements)
  - Calculate slope and intercept using least squares method
  - Calculate gain error: gain_error = (slope - 1.0) * 100.0
  - Calculate adjustment factor: adjustment_factor = 1.0 / slope
- Update scatter plots after each setpoint completes (both first sweep and second sweep plots)
- Display both plots in Test Detail window and include in test report, each labeled with its trim value
- Optionally display regression line on plots (slope and intercept)
- Test results must include: first sweep gain error (from regression), first sweep adjustment factor, calculated trim value, second sweep gain error (from regression), slope and intercept for both sweeps
- Pass/fail determination uses only second sweep gain error from linear regression

