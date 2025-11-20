# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `Phase Current Test`
- **Short Description**: `Calibrates phase current sensors by comparing DUT measurements with oscilloscope measurements across multiple test points`
- **Detailed Description**: 
  ```
  This test calibrates phase current sensors by comparing DUT measurements (via CAN) with oscilloscope
  measurements (reference) across multiple test points defined by Id_ref and Iq_ref current values.
  
  How it works:
  - The test uses a state machine pattern to manage the complex test sequence
  - Validates oscilloscope settings (timebase, channels, probe attenuation)
  - Prepares an array of Iq_ref values to test
  - For each Iq_ref value:
    * Configures oscilloscope vertical scale based on expected current
    * Starts oscilloscope acquisition and CAN data logging
    * Sends trigger message to DUT with Id_ref and Iq_ref values
    * Waits for test duration while collecting CAN phase current signals
    * Stops oscilloscope acquisition and CAN logging
    * Analyzes steady-state data from both oscilloscope and CAN
    * Updates live plot with calibration data
  - Disables test mode at DUT
  - Calculates calibration parameters (gain error, offset, etc.)
  
  Hardware Requirements:
  - Device Under Test (DUT) with phase current sensors
  - EOL Hardware
  - CAN Hardware (Canalystii)
  - Oscilloscope - Siglent SDS1104X-u (or compatible)
  - Current probes connected to oscilloscope channels (typically 2 channels for phase V and W)
  
  Special Considerations:
  - Most complex test type with state machine pattern
  - Requires oscilloscope to be connected and configured before test execution
  - Test iterates through multiple Iq_ref values (sweep pattern)
  - Real-time plot updates during test execution
  - Analyzes steady-state data using advanced algorithms
  - Calculates calibration parameters for sensor trim
  - Uses state machine for complex sequence management
  ```

## Test Configuration Fields

### Required Fields
List all fields that must be provided for this test type:

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `can_id` | `integer` | `CAN message ID for phase current test command` | `Range: 0-0x1FFFFFFF, Required` | `272` |
| `message_type` | `integer` | `CAN message type for phase current test command` | `Required` | `18` |
| `device_id` | `integer` | `Target device ID (IPC_Hardware = 0x03)` | `Required` | `3` |
| `enable_signal` | `string` | `Signal name for enabling phase current test` | `Non-empty, Required` | `"Mctrl_Phase_I_Test_Enable"` |
| `id_ref_signal` | `string` | `Signal name for Id reference current` | `Non-empty, Required` | `"Mctrl_Set_Id_Ref"` |
| `iq_ref_signal` | `string` | `Signal name for Iq reference current` | `Non-empty, Required` | `"Mctrl_Set_Iq_Ref"` |
| `test_points` | `array` | `List of test points, each with id_ref and iq_ref` | `Minimum: 1 item, Required` | `[{"id_ref": 0.0, "iq_ref": 5.0}, ...]` |
| `oscilloscope` | `object` | `Oscilloscope configuration (model, connection, channels, trigger)` | `Required` | See oscilloscope config |
| `timing` | `object` | `Timing configuration (pre_trigger_wait_ms, test_duration_ms, extended_collection_ms)` | `Required` | See timing config |
| `data_collection` | `object` | `Data collection configuration (can_message_id, can_message_type, phase signals, sampling_rate_hz)` | `Required` | See data collection config |

### Optional Fields

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `steady_state_detection` | `object` | `Steady-state detection configuration (derivative_window_ms, ramp_threshold, stability_duration_ms, etc.)` | `Optional` | See steady-state config |

### Oscilloscope Configuration Object

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `model` | `string` | `Oscilloscope model name` | `Required` | `"SDS1104X-U"` |
| `connection` | `object` | `Connection configuration (type, address)` | `Required` | `{"type": "ethernet", "address": "192.168.1.100"}` |
| `channels` | `object` | `Channel configuration (channel_1, channel_2 with name, unit, probe_attenuation, scale)` | `Required` | See channels config |
| `trigger` | `object` | `Trigger configuration (mode, source, level_percent)` | `Required` | `{"mode": "auto"}` |

### Timing Configuration Object

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `pre_trigger_wait_ms` | `integer` | `Time to wait before sending trigger message` | `Minimum: 0, Required` | `100` |
| `test_duration_ms` | `integer` | `Test duration in milliseconds` | `Minimum: 1000, Required` | `2000` |
| `extended_collection_ms` | `integer` | `Extended collection time after test duration` | `Minimum: 3000, Required` | `3000` |

### Data Collection Configuration Object

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `can_message_id` | `integer` | `CAN message ID for phase current feedback` | `Required` | `250` |
| `can_message_type` | `integer` | `CAN message type for phase current feedback` | `Required` | `0` |
| `phase_v_signal` | `string` | `Signal name for phase V current` | `Non-empty, Required` | `"Phase_V_Current"` |
| `phase_w_signal` | `string` | `Signal name for phase W current` | `Non-empty, Required` | `"Phase_W_Current"` |
| `sampling_rate_hz` | `integer` | `CAN sampling rate in Hz` | `Optional` | `10` |

### CAN Message/Signal Fields
If the test uses CAN communication, specify:

- **Command Message** (sending commands to DUT):
  - Message ID: `can_id` (configurable, e.g., 272)
  - Message Type: `message_type` (configurable, e.g., 18)
  - Device ID: `device_id` (configurable, e.g., 3)
  - Signals used: 
    - `enable_signal` - Enable phase current test (value: 1 to enable, 0 to disable)
    - `id_ref_signal` - Id reference current value (in Amperes)
    - `iq_ref_signal` - Iq reference current value (in Amperes)
  - Purpose: `Send phase current test trigger and reference current values to DUT`

- **Feedback Messages** (reading measurements from DUT):
  - Message ID: `data_collection.can_message_id` (configurable, e.g., 250)
  - Message Type: `data_collection.can_message_type` (configurable, e.g., 0)
  - Signals used: 
    - `phase_v_signal` - Phase V current measured by DUT (in Amperes)
    - `phase_w_signal` - Phase W current measured by DUT (in Amperes)
  - Purpose: `Read phase current measurements from DUT for comparison with oscilloscope`

- **DBC Support**: `Yes` - Test works with DBC file loaded (dropdowns for messages/signals)
- **Non-DBC Support**: `No` - Test requires DBC file for proper signal encoding/decoding

## Test Execution Logic

### Execution Flow
Describe the step-by-step execution flow:

```
1. Initialize State Machine
   - Action: 
     - Validate test configuration
     - Extract oscilloscope, timing, and data collection parameters
     - Initialize state machine
   - Duration: As fast as possible
   - Expected result: State machine ready

2. Validate Oscilloscope Settings
   - Action: 
     - Check oscilloscope connection
     - Verify timebase, channels, probe attenuation match configuration
     - Validate trigger settings
   - Duration: As fast as possible (typically < 1 second)
   - Expected result: Oscilloscope settings validated

3. Prepare Iq_ref Array
   - Action: 
     - Extract test_points from configuration
     - Build array of unique Iq_ref values to test
     - Clear plot window
   - Duration: As fast as possible
   - Expected result: Array of Iq_ref values ready

4. For each Iq_ref value in array:
   a. Set Vertical Division
      - Action: 
        - Calculate expected current based on Iq_ref
        - Configure oscilloscope vertical scale (VDIV) for appropriate range
      - Duration: As fast as possible
      - Expected result: Oscilloscope vertical scale configured
   
   b. Start Acquisition and Logging
      - Action: 
        - Start oscilloscope acquisition (TRMD AUTO or similar)
        - Start CAN data logging for phase current signals
        - Initialize data collection lists
      - Duration: As fast as possible
      - Expected result: Data acquisition started
   
   c. Send Trigger Message
      - Action: 
        - Wait for pre_trigger_wait_ms
        - Encode and send CAN message with:
          * enable_signal = 1
          * id_ref_signal = id_ref (from test point)
          * iq_ref_signal = iq_ref (current value in loop)
        - Include DeviceID and MessageType
      - Duration: As fast as possible
      - Expected result: Trigger message sent, DUT starts phase current test
   
   d. Wait for Test Duration
      - Action: 
        - Continuously collect phase_v_signal and phase_w_signal from CAN
        - Store all readings with timestamps
        - Continue for test_duration_ms
      - Duration: test_duration_ms milliseconds
      - Expected result: CAN data collected during test duration
   
   e. Extended Collection
      - Action: 
        - Continue collecting CAN data for extended_collection_ms
        - Oscilloscope continues acquiring data
      - Duration: extended_collection_ms milliseconds
      - Expected result: Extended data collected
   
   f. Stop Acquisition and Logging
      - Action: 
        - Stop oscilloscope acquisition (STOP command)
        - Stop CAN data logging
      - Duration: As fast as possible
      - Expected result: Data acquisition stopped
   
   g. Analyze Steady State
      - Action: 
        - Decode oscilloscope waveform data
        - Analyze steady-state periods from oscilloscope data
        - Analyze steady-state periods from CAN data
        - Extract average values for comparison
        - Update live plot with calibration data
      - Duration: As fast as possible (may take several seconds for analysis)
      - Expected result: Steady-state data analyzed, plot updated

5. Disable Test Mode
   - Action: 
     - Send CAN message with enable_signal = 0 to disable phase current test
   - Duration: As fast as possible
   - Expected result: Test mode disabled at DUT

6. Calculate Calibration Parameters
   - Action: 
     - Perform linear regression on collected data points
     - Calculate gain error, offset, adjustment factors
     - Determine pass/fail based on calibration criteria
   - Duration: As fast as possible
   - Expected result: Calibration parameters calculated, pass/fail determined
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `Calibration parameters (gain error, offset, etc.) are within specified tolerances`
- **Fail Condition**: `Calibration parameters exceed tolerances OR steady-state analysis fails`
- **Calculation Method**: 
  ```
  1. For Each Test Point:
     - Collect oscilloscope waveform data
     - Collect CAN phase current signals
     - Analyze steady-state periods from both sources
     - Extract average values for comparison
  
  2. Steady-State Analysis:
     - Detect steady-state periods using derivative analysis
     - Apply low-pass filtering if needed
     - Extract stable average values
  
  3. Calibration Calculation:
     - Perform linear regression on (oscilloscope_avg, can_avg) pairs
     - Calculate slope, intercept, gain error, offset
     - Compare with tolerance criteria
  
  4. Pass/Fail Determination:
     - PASS if all calibration parameters within tolerance
     - FAIL if any parameter exceeds tolerance OR analysis fails
  ```

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: 
  - `phase_v_signal` from CAN (DUT phase V current measurement)
  - `phase_w_signal` from CAN (DUT phase W current measurement)
  - Oscilloscope waveform data from channels (reference measurements)
  
- **Collection Duration**: 
  - Test duration: `test_duration_ms` milliseconds
  - Extended collection: `extended_collection_ms` milliseconds
  - Total: `test_duration_ms + extended_collection_ms` per test point
  
- **Sampling Rate**: 
  - CAN data: Polled at `sampling_rate_hz` (typically 10 Hz)
  - Oscilloscope: Continuous acquisition, decoded after stop
  
- **Data Processing**: 
  ```
  1. During Test Duration:
     - Collect phase_v_signal and phase_w_signal from CAN
     - Store with timestamps
     - Oscilloscope acquires waveform data
  
  2. During Extended Collection:
     - Continue collecting CAN data
     - Oscilloscope continues acquiring
  
  3. After Acquisition:
     - Decode oscilloscope waveform data
     - Analyze steady-state periods
     - Extract average values
     - Update plot
  ```

### Timing Requirements
Specify any timing requirements:

- **Pre-Trigger Wait**: `pre_trigger_wait_ms` (default: 100ms) - Wait time before sending trigger
- **Test Duration**: `test_duration_ms` (default: 2000ms) - Time for DUT to reach steady state
- **Extended Collection**: `extended_collection_ms` (default: 3000ms) - Additional data collection time
- **Total Duration**: 
  ```
  Estimated total test duration:
  = oscilloscope_validation_time (≈1s)
  + (number_of_iq_ref_values × (
      vertical_scale_time (≈0.2s)
      + start_acquisition_time (≈0.2s)
      + pre_trigger_wait_ms
      + test_duration_ms
      + extended_collection_ms
      + stop_acquisition_time (≈0.2s)
      + analysis_time (≈2-5s)
    ))
  + disable_test_time (≈0.1s)
  + calibration_calculation_time (≈0.5s)
  
  Example with 5 Iq_ref values, test_duration_ms = 2000ms, extended_collection_ms = 3000ms:
  ≈ 1s + 5 × (0.2s + 0.2s + 0.1s + 2.0s + 3.0s + 0.2s + 3.0s) + 0.1s + 0.5s
  ≈ 1s + 5 × 8.7s + 0.6s
  ≈ 45.1 seconds
  ```

## GUI Requirements

### Create/Edit Dialog Fields
Specify the UI fields needed:

#### Oscilloscope Configuration Section
- **Model**: `QComboBox` or `QLineEdit` - Oscilloscope model selection
- **Connection Type**: `QComboBox` - Connection type (usb, ethernet, serial)
- **Connection Address**: `QLineEdit` - Connection address
- **Channel 1/2 Configuration**: Multiple fields for name, unit, probe_attenuation, scale
- **Trigger Configuration**: Fields for mode, source, level_percent

#### Timing Configuration Section
- **Pre-Trigger Wait**: `QLineEdit` with QIntValidator - Pre-trigger wait time in ms
- **Test Duration**: `QLineEdit` with QIntValidator - Test duration in ms
- **Extended Collection**: `QLineEdit` with QIntValidator - Extended collection time in ms

#### Data Collection Configuration Section
- **CAN Message ID**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode) - CAN ID for feedback
- **CAN Message Type**: `QLineEdit` with QIntValidator - Message type
- **Phase V Signal**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode) - Phase V signal name
- **Phase W Signal**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode) - Phase W signal name
- **Sampling Rate**: `QLineEdit` with QIntValidator - Sampling rate in Hz

#### Test Points Configuration Section
- **Test Points Table**: `QTableWidget` - Table for entering id_ref and iq_ref values
- **Add/Remove Buttons**: Buttons to add/remove test points

#### Command Configuration Section
- **CAN ID**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode) - CAN ID for commands
- **Message Type**: `QLineEdit` with QIntValidator - Message type
- **Device ID**: `QLineEdit` with QIntValidator - Device ID
- **Enable Signal**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode) - Enable signal name
- **Id Ref Signal**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode) - Id ref signal name
- **Iq Ref Signal**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode) - Iq ref signal name

### Feedback Fields Visibility
- **Show Feedback Fields**: `No` - This test type has its own feedback configuration in data_collection
- **Custom Feedback Fields**: `Yes` - Uses data_collection configuration for phase current signals

### Plot Requirements
- **Needs Plot**: `Yes`
- **Plot Type**: `Scatter plot or line plot (X-Y plot)`
- **X-Axis**: `Oscilloscope Measurement (A)` - Reference measurement from oscilloscope
- **Y-Axis**: `DUT Measurement (A)` - DUT measurement from CAN feedback signals
- **Update Frequency**: `After each test point completes (after steady-state analysis)`
- **Plot Features**: 
  - Real-time plot updates during test execution
  - Each point represents one test point (Iq_ref value)
  - Ideal calibration line (Y = X) can be displayed for reference
  - Linear regression line can be displayed after test completion

### Real-Time Monitoring
The Real-Time Monitoring section displays the following signals during test execution:

- **Set Id**: Displays the latest `id_ref_signal` value sent (tracked from command messages)
  - Updates when trigger messages are sent with Id_ref values
  - Format: `Set Id : X.XX A`
  
- **Set Iq**: Displays the latest `iq_ref_signal` value sent (tracked from command messages)
  - Updates when trigger messages are sent with Iq_ref values
  - Format: `Set Iq : X.XX A`
  
- **DUT Phase V Current**: Displays `phase_v_signal` from data collection
  - Updates in real-time during signal collection via phase_current_service
  - Format: `DUT Phase V Current : X.XX A`
  
- **DUT Phase W Current**: Displays `phase_w_signal` from data collection
  - Updates in real-time during signal collection via phase_current_service
  - Format: `DUT Phase W Current : X.XX A`

The monitoring section automatically configures these labels when the test starts and clears them when the test completes. See [Real-Time Monitoring](../REAL_TIME_MONITORING.md) for detailed documentation.

## Validation Rules

### Schema Validation
Specify JSON schema requirements:

```json
{
  "properties": {
    "type": {"const": "Phase Current Test"},
    "can_id": {"type": "integer"},
    "message_type": {"type": "integer"},
    "device_id": {"type": "integer"},
    "enable_signal": {"type": "string"},
    "id_ref_signal": {"type": "string"},
    "iq_ref_signal": {"type": "string"},
    "test_points": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id_ref": {"type": "number"},
          "iq_ref": {"type": "number"}
        },
        "required": ["id_ref", "iq_ref"]
      },
      "minItems": 1
    },
    "oscilloscope": {
      "type": "object",
      "properties": {
        "model": {"type": "string"},
        "connection": {
          "type": "object",
          "properties": {
            "type": {"type": "string", "enum": ["usb", "ethernet", "serial"]},
            "address": {"type": "string"}
          },
          "required": ["type", "address"]
        },
        "channels": {
          "type": "object",
          "properties": {
            "channel_1": {
              "type": "object",
              "properties": {
                "name": {"type": "string"},
                "unit": {"type": "string"},
                "probe_attenuation": {"type": "number"},
                "scale": {"type": "number"}
              },
              "required": ["name", "unit", "probe_attenuation", "scale"]
            },
            "channel_2": {
              "type": "object",
              "properties": {
                "name": {"type": "string"},
                "unit": {"type": "string"},
                "probe_attenuation": {"type": "number"},
                "scale": {"type": "number"}
              },
              "required": ["name", "unit", "probe_attenuation", "scale"]
            }
          },
          "required": ["channel_1", "channel_2"]
        },
        "trigger": {
          "type": "object",
          "properties": {
            "mode": {"type": "string", "enum": ["single", "normal", "auto"]},
            "source": {"type": "string"},
            "level_percent": {"type": "number", "minimum": 0, "maximum": 100}
          },
          "required": ["mode"]
        }
      },
      "required": ["model", "connection", "channels", "trigger"]
    },
    "timing": {
      "type": "object",
      "properties": {
        "pre_trigger_wait_ms": {"type": "integer", "minimum": 0},
        "test_duration_ms": {"type": "integer", "minimum": 1000},
        "extended_collection_ms": {"type": "integer", "minimum": 3000}
      },
      "required": ["pre_trigger_wait_ms", "test_duration_ms", "extended_collection_ms"]
    },
    "data_collection": {
      "type": "object",
      "properties": {
        "can_message_id": {"type": "integer"},
        "can_message_type": {"type": "integer"},
        "phase_v_signal": {"type": "string"},
        "phase_w_signal": {"type": "string"},
        "sampling_rate_hz": {"type": "integer"}
      },
      "required": ["can_message_id", "can_message_type", "phase_v_signal", "phase_w_signal"]
    },
    "steady_state_detection": {
      "type": "object",
      "properties": {
        "derivative_window_ms": {"type": "integer"},
        "ramp_threshold_a_per_sec": {"type": "number"},
        "stability_duration_ms": {"type": "integer"},
        "drop_threshold_percent": {"type": "number"},
        "minimum_steady_state_duration_ms": {"type": "integer"},
        "minimum_samples": {"type": "integer"},
        "max_std_threshold_percent": {"type": "number"},
        "time_sync_tolerance_ms": {"type": "integer"}
      }
    }
  },
  "required": [
    "can_id",
    "message_type",
    "device_id",
    "test_points",
    "oscilloscope",
    "timing",
    "data_collection"
  ]
}
```

### Application Validation
List validation checks to perform in `_validate_test()`:

- [x] Test type is in allowed list
- [x] Actuation type matches test type
- [x] `can_id` is present and in valid range (0-0x1FFFFFFF)
- [x] `message_type` is present
- [x] `device_id` is present
- [x] `enable_signal`, `id_ref_signal`, `iq_ref_signal` are present and non-empty
- [x] `test_points` is present and has at least 1 item
- [x] Each test point has `id_ref` and `iq_ref`
- [x] `oscilloscope` configuration is present and valid
- [x] `timing` configuration is present and valid
- [x] `data_collection` configuration is present and valid
- [x] Oscilloscope service is available and connected
- [x] DBC service is available (test requires DBC)

## Error Handling

### Expected Error Scenarios
List potential errors and how to handle them:

1. **Missing Required Field**
   - Error: `"Missing required Phase Current Test parameters"`
   - Handling: Return `False, "Phase Current Test requires {field_name}"`

2. **Invalid Test Points**
   - Error: `"No test points specified"`
   - Handling: Return `False, "Phase Current Test requires at least one test point"`

3. **Oscilloscope Not Connected**
   - Error: `"Oscilloscope not connected"`
   - Handling: Return `False, "Oscilloscope not connected. Please connect oscilloscope before running Phase Current Test."`

4. **Oscilloscope Configuration Mismatch**
   - Error: `"Oscilloscope configuration mismatch"`
   - Handling: Return `False, "Oscilloscope configuration does not match test configuration: {specific_error}"`

5. **Steady-State Analysis Failure**
   - Error: `"Failed to detect steady state"`
   - Handling: Log warning and continue to next test point, or fail test if critical

6. **DBC Service Not Available**
   - Error: `"DBC service not available"`
   - Handling: Return `False, "Phase Current Test requires DBC file to be loaded"`

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "Phase Current Test - Basic",
  "type": "Phase Current Test",
  "actuation": {
    "type": "Phase Current Test",
    "can_id": 272,
    "message_type": 18,
    "device_id": 3,
    "enable_signal": "Mctrl_Phase_I_Test_Enable",
    "id_ref_signal": "Mctrl_Set_Id_Ref",
    "iq_ref_signal": "Mctrl_Set_Iq_Ref",
    "test_points": [
      {"id_ref": 0.0, "iq_ref": 5.0},
      {"id_ref": 0.0, "iq_ref": 10.0},
      {"id_ref": 0.0, "iq_ref": 15.0}
    ],
    "oscilloscope": {
      "model": "SDS1104X-U",
      "connection": {
        "type": "ethernet",
        "address": "192.168.1.100"
      },
      "channels": {
        "channel_1": {
          "name": "Phase V",
          "unit": "A",
          "probe_attenuation": 1.0,
          "scale": 1.0
        },
        "channel_2": {
          "name": "Phase W",
          "unit": "A",
          "probe_attenuation": 1.0,
          "scale": 1.0
        }
      },
      "trigger": {
        "mode": "auto"
      }
    },
    "timing": {
      "pre_trigger_wait_ms": 100,
      "test_duration_ms": 2000,
      "extended_collection_ms": 3000
    },
    "data_collection": {
      "can_message_id": 250,
      "can_message_type": 0,
      "phase_v_signal": "Phase_V_Current",
      "phase_w_signal": "Phase_W_Current",
      "sampling_rate_hz": 10
    }
  }
}
```

## Implementation Notes

### Special Considerations
- **State Machine Pattern**: Test uses PhaseCurrentTestStateMachine class for complex sequence management
- **Oscilloscope Integration**: Extensive oscilloscope configuration and control
- **Steady-State Analysis**: Advanced algorithms for detecting and analyzing steady-state periods
- **Multi-Point Testing**: Iterates through multiple test points (Iq_ref values)
- **Real-Time Plotting**: Plot updates after each test point completes
- **Calibration Calculation**: Performs linear regression and calculates calibration parameters
- **DBC Required**: Test requires DBC file for proper signal encoding/decoding

### Dependencies
- **oscilloscope_service**: Required for oscilloscope communication
- **can_service**: Required for sending CAN commands and receiving feedback
- **dbc_service**: Required for encoding/decoding CAN messages
- **signal_service**: Required for reading CAN phase current signals
- **numpy** (optional but recommended): For linear regression and data analysis
- **matplotlib** (optional but recommended): For plotting

### Similar Test Types
- **Output Current Calibration**: Similar oscilloscope + CAN comparison pattern, uses linear regression
- **DC Bus Sensing**: Similar oscilloscope integration but simpler (single measurement)
- **Analog Sweep Test**: Similar multi-step pattern but for DAC voltages (no oscilloscope)

### Testing Requirements
- Test with hardware connected (DUT, oscilloscope, CAN hardware)
- Test with valid DBC file loaded (required)
- Test with oscilloscope connected and configured
- Test with various test point configurations
- Test error cases (oscilloscope not connected, steady-state analysis failure, etc.)
- Verify real-time plot updates correctly
- Verify calibration parameters are calculated correctly

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Output Current Calibration`
- **Why Similar**: 
  - Both compare oscilloscope measurements with CAN feedback
  - Both iterate through multiple test points
  - Both use linear regression for calibration
  - Both update plots in real-time
- **Key Differences**: 
  - Phase Current Test is more complex (state machine, steady-state analysis)
  - Phase Current Test uses multiple channels (phase V and W)
  - Phase Current Test has more configuration options
  - Phase Current Test analyzes steady-state periods

### Code Patterns to Use
- **State Machine Pattern**: Use PhaseCurrentTestStateMachine for sequence management
- **Oscilloscope Setup Pattern**: Validate and configure oscilloscope settings
- **Multi-Point Iteration Pattern**: Loop through test points and collect data
- **Steady-State Analysis Pattern**: Detect and analyze steady-state periods
- **Linear Regression Pattern**: Calculate calibration parameters
- **Real-Time Plot Pattern**: Update plot after each test point

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
- [ ] Plot data appears in test report
- [ ] JSON schema validation works

### Technical Requirements
- [ ] All files updated according to documentation
- [ ] Code follows existing patterns and style
- [ ] Error handling implemented
- [ ] Logging added for debugging
- [ ] Non-blocking sleep used (no `time.sleep()`)
- [ ] DBC mode supported (required)
- [ ] Oscilloscope integration implemented correctly
- [ ] State machine pattern implemented
- [ ] Steady-state analysis implemented
- [ ] Linear regression calculation implemented
- [ ] Real-time plot updates implemented

### Testing Requirements
- [ ] Test with valid configuration
- [ ] Test with invalid configuration (should fail validation)
- [ ] Test with DBC loaded (required)
- [ ] Test execution produces correct results
- [ ] Error cases handled gracefully (oscilloscope not connected, steady-state analysis failure, etc.)
- [ ] Test with various test point configurations
- [ ] Verify real-time plot updates correctly
- [ ] Verify calibration parameters are calculated correctly

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
   - `host_gui/services/phase_current_service.py` (state machine)
   - `host_gui/services/test_execution_service.py` (optional)
4. Implement validation logic
5. Implement execution logic (state machine)
6. Test thoroughly with both valid and invalid configurations
7. Ensure all acceptance criteria are met

### Key Reminders
- Use exact test type name consistently across all files: `"Phase Current Test"`
- DBC mode is required (test does not support non-DBC mode)
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style
- Use state machine pattern for complex sequence management
- Verify oscilloscope connection before test execution
- Implement steady-state analysis algorithms
- Calculate calibration parameters using linear regression
- Update plot after each test point completes

