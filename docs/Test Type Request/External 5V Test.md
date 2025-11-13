# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `External 5V Test`
- **Short Description**: `Tests external 5V power supply by comparing DUT feedback with EOL measurement in disabled and enabled states`
- **Detailed Description**: 
  ```
  This test validates the external 5V power supply functionality by testing both disabled and enabled states
  and comparing measurements from two sources:
  1. DUT feedback signal (from DUT via CAN)
  2. EOL external 5V measurement signal (from EOL hardware via CAN)
  
  How it works:
  - Phase 1 (Disabled State):
    * Send external 5V test trigger signal = 0 to disable external 5V
    * Wait for pre-dwell time for system stabilization
    * Collect feedback and EOL signals during dwell time
    * Calculate averages for disabled phase
  - Phase 2 (Enabled State):
    * Send external 5V test trigger signal = 1 to enable external 5V
    * Wait for pre-dwell time for system stabilization
    * Collect feedback and EOL signals during dwell time
    * Calculate averages for enabled phase
  - Cleanup:
    * Send external 5V test trigger signal = 0 to disable external 5V
  - Evaluation:
    * Compare feedback vs EOL for both phases
    * Test passes if both phases are within tolerance
  
  Hardware Requirements:
  - Device Under Test (DUT) with external 5V power supply
  - EOL Hardware (for EOL external 5V measurement)
  - CAN Hardware (Canalystii or compatible)
  
  Special Considerations:
  - Multi-phase test (disabled and enabled states)
  - Both phases must pass for overall test to pass
  - Real-time display of both signals during data collection
  - Supports both DBC and non-DBC modes
  ```

## Test Configuration Fields

### Required Fields
List all fields that must be provided for this test type:

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `ext_5v_test_trigger_source` | `integer` | `CAN message ID for External 5V test trigger command` | `Range: 0-0x1FFFFFFF, Required` | `0x200` |
| `ext_5v_test_trigger_signal` | `string` | `CAN signal name for External 5V test trigger` | `Non-empty, Required` | `"Ext_5V_Test_Enable"` |
| `eol_ext_5v_measurement_source` | `integer` | `CAN message ID containing EOL Ext 5V measurement signal` | `Range: 0-0x1FFFFFFF, Required` | `0x201` |
| `eol_ext_5v_measurement_signal` | `string` | `CAN signal name for EOL Ext 5V measurement` | `Non-empty, Required` | `"EOL_Ext_5V"` |
| `feedback_signal_source` | `integer` | `CAN message ID containing feedback signal` | `Range: 0-0x1FFFFFFF, Required` | `0x202` |
| `feedback_signal` | `string` | `CAN signal name for feedback signal` | `Non-empty, Required` | `"Feedback_5V"` |
| `tolerance_mv` | `number` | `Tolerance in millivolts for pass/fail determination` | `Minimum: 0, Required` | `50.0` |
| `pre_dwell_time_ms` | `integer` | `Pre-dwell time in milliseconds (system stabilization)` | `Minimum: 0, Required` | `1000` |
| `dwell_time_ms` | `integer` | `Dwell time in milliseconds (data collection period)` | `Minimum: 1, Required` | `3000` |

### CAN Message/Signal Fields
If the test uses CAN communication, specify:

- **Command Message** (sending commands to DUT):
  - Message ID: `ext_5v_test_trigger_source` (configurable, e.g., 0x200)
  - Signals used: 
    - `ext_5v_test_trigger_signal` - Enable/disable external 5V test (value: 1 to enable, 0 to disable)
    - `DeviceID` - Device ID (if message is multiplexed, default: 0)
    - `MessageType` - Message type (if signal is multiplexed)
  - Purpose: `Send external 5V test trigger command to enable/disable external 5V`

- **Feedback Messages** (reading measurements from DUT):
  - Message ID: `feedback_signal_source` (configurable, e.g., 0x202)
  - Signals used: 
    - `feedback_signal` - Feedback signal from DUT (in millivolts)
  - Purpose: `Read feedback signal from DUT for comparison with EOL measurement`

- **EOL Messages** (reading measurements from EOL hardware):
  - Message ID: `eol_ext_5v_measurement_source` (configurable, e.g., 0x201)
  - Signals used: 
    - `eol_ext_5v_measurement_signal` - EOL external 5V measurement signal (in millivolts)
  - Purpose: `Read EOL external 5V measurement for comparison with DUT feedback`

- **DBC Support**: `Yes` - Test works with DBC file loaded (dropdowns for messages/signals)
- **Non-DBC Support**: `Yes` - Test works without DBC file (free-text inputs for CAN IDs and signal names)

## Test Execution Logic

### Execution Flow
Describe the step-by-step execution flow:

```
1. Phase 1: Disabled State
   a. Send Disable Trigger
      - Action: Encode and send CAN message with ext_5v_test_trigger_signal = 0
      - Duration: As fast as possible
      - Expected result: External 5V disabled command sent successfully
   
   b. Wait for Pre-Dwell Time
      - Action: Wait for pre_dwell_time_ms to allow system to stabilize
      - Duration: pre_dwell_time_ms milliseconds
      - Expected result: System stabilized in disabled state
   
   c. Collect Data (Disabled Phase)
      - Action: 
        - Continuously read feedback_signal from CAN
        - Continuously read eol_ext_5v_measurement_signal from CAN
        - Store all readings in lists
        - Update real-time display with latest values
      - Duration: dwell_time_ms milliseconds
      - Expected result: Multiple samples of both signals collected for disabled phase

2. Phase 2: Enabled State
   a. Send Enable Trigger
      - Action: Encode and send CAN message with ext_5v_test_trigger_signal = 1
      - Duration: As fast as possible
      - Expected result: External 5V enabled command sent successfully
   
   b. Wait for Pre-Dwell Time
      - Action: Wait for pre_dwell_time_ms to allow system to stabilize
      - Duration: pre_dwell_time_ms milliseconds
      - Expected result: System stabilized in enabled state
   
   c. Collect Data (Enabled Phase)
      - Action: 
        - Clear plot (if using plots)
        - Continuously read feedback_signal from CAN
        - Continuously read eol_ext_5v_measurement_signal from CAN
        - Store all readings in lists
        - Update real-time display with latest values
      - Duration: dwell_time_ms milliseconds
      - Expected result: Multiple samples of both signals collected for enabled phase

3. Cleanup
   - Action: Send ext_5v_test_trigger_signal = 0 to disable external 5V
   - Duration: As fast as possible
   - Expected result: External 5V disabled (system returned to safe state)

4. Calculate Averages
   - Action: 
     - Calculate feedback_avg_disabled and eol_avg_disabled from Phase 1 data
     - Calculate feedback_avg_enabled and eol_avg_enabled from Phase 2 data
   - Duration: As fast as possible
   - Expected result: Averages calculated for both phases

5. Compare and Determine Pass/Fail
   - Action: 
     - Calculate difference_disabled = |feedback_avg_disabled - eol_avg_disabled|
     - Calculate difference_enabled = |feedback_avg_enabled - eol_avg_enabled|
     - passed_disabled = (difference_disabled <= tolerance_mv)
     - passed_enabled = (difference_enabled <= tolerance_mv)
     - passed = (passed_disabled AND passed_enabled)
   - Duration: As fast as possible
   - Expected result: Test result determined and returned
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `Both disabled and enabled phases are within tolerance (difference_disabled <= tolerance_mv AND difference_enabled <= tolerance_mv)`
- **Fail Condition**: `Either disabled or enabled phase exceeds tolerance (difference_disabled > tolerance_mv OR difference_enabled > tolerance_mv)`
- **Calculation Method**: 
  ```
  1. Phase 1 (Disabled State):
     - Collect feedback and EOL signals during dwell time
     - Calculate averages:
       * feedback_avg_disabled = sum(feedback_values_disabled) / len(feedback_values_disabled)
       * eol_avg_disabled = sum(eol_values_disabled) / len(eol_values_disabled)
     - Calculate difference:
       * difference_disabled = abs(feedback_avg_disabled - eol_avg_disabled)
     - Check: passed_disabled = (difference_disabled <= tolerance_mv)
  
  2. Phase 2 (Enabled State):
     - Collect feedback and EOL signals during dwell time
     - Calculate averages:
       * feedback_avg_enabled = sum(feedback_values_enabled) / len(feedback_values_enabled)
       * eol_avg_enabled = sum(eol_values_enabled) / len(eol_values_enabled)
     - Calculate difference:
       * difference_enabled = abs(feedback_avg_enabled - eol_avg_enabled)
     - Check: passed_enabled = (difference_enabled <= tolerance_mv)
  
  3. Final Result:
     - PASS if (passed_disabled AND passed_enabled)
     - FAIL if (NOT passed_disabled OR NOT passed_enabled)
  ```

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: 
  - `feedback_signal` from CAN (DUT feedback measurement)
  - `eol_ext_5v_measurement_signal` from CAN (EOL external 5V measurement)
  
- **Collection Duration**: `dwell_time_ms` milliseconds per phase (disabled and enabled)
  
- **Sampling Rate**: 
  - Polled every SLEEP_INTERVAL_SHORT (typically 50-100ms) during dwell time
  
- **Data Processing**: 
  ```
  1. Phase 1 (Disabled):
     - Collect feedback_signal and eol_ext_5v_measurement_signal during dwell_time_ms
     - Store in feedback_values_disabled and eol_values_disabled lists
  
  2. Phase 2 (Enabled):
     - Collect feedback_signal and eol_ext_5v_measurement_signal during dwell_time_ms
     - Store in feedback_values_enabled and eol_values_enabled lists
  
  3. Analysis:
     - Calculate averages for each phase
     - Compare averages and check tolerance for each phase
  ```

### Timing Requirements
Specify any timing requirements:

- **Pre-Dwell Time**: `pre_dwell_time_ms` (default: 1000ms) - Wait time for system stabilization per phase
- **Dwell Time**: `dwell_time_ms` (default: 3000ms) - Time to collect data per phase
- **Polling Interval**: `SLEEP_INTERVAL_SHORT` (typically 50-100ms) - Interval between signal readings
- **Total Duration**: 
  ```
  Estimated total test duration:
  = disable_trigger_time (≈0.1s)
  + pre_dwell_time_ms (Phase 1)
  + dwell_time_ms (Phase 1)
  + enable_trigger_time (≈0.1s)
  + pre_dwell_time_ms (Phase 2)
  + dwell_time_ms (Phase 2)
  + cleanup_time (≈0.1s)
  
  Example with pre_dwell_time_ms = 1000ms, dwell_time_ms = 3000ms:
  ≈ 0.1s + 1.0s + 3.0s + 0.1s + 1.0s + 3.0s + 0.1s
  ≈ 8.3 seconds
  ```

## GUI Requirements

### Create/Edit Dialog Fields
Specify the UI fields needed:

#### Field 1: External 5V Test Trigger Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x200)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 2: External 5V Test Trigger Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 3: EOL Ext 5V Measurement Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x201)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 4: EOL Ext 5V Measurement Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 5: Feedback Signal Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x202)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 6: Feedback Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 7: Tolerance
- **Type**: `QLineEdit` with QDoubleValidator
- **Placeholder**: `Enter tolerance in millivolts (e.g., 50.0)`
- **Validator**: `Double >= 0.0, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 8: Pre-Dwell Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter pre-dwell time in milliseconds (e.g., 1000)`
- **Validator**: `Integer >= 0, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 9: Dwell Time
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
    "type": {"const": "External 5V Test"},
    "ext_5v_test_trigger_source": {"type": "integer"},
    "ext_5v_test_trigger_signal": {"type": "string"},
    "eol_ext_5v_measurement_source": {"type": "integer"},
    "eol_ext_5v_measurement_signal": {"type": "string"},
    "feedback_signal_source": {"type": "integer"},
    "feedback_signal": {"type": "string"},
    "tolerance_mv": {"type": "number", "minimum": 0},
    "pre_dwell_time_ms": {"type": "integer", "minimum": 0},
    "dwell_time_ms": {"type": "integer", "minimum": 1}
  },
  "required": [
    "ext_5v_test_trigger_source",
    "ext_5v_test_trigger_signal",
    "eol_ext_5v_measurement_source",
    "eol_ext_5v_measurement_signal",
    "feedback_signal_source",
    "feedback_signal",
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
- [x] `ext_5v_test_trigger_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `ext_5v_test_trigger_signal` is present and non-empty
- [x] `eol_ext_5v_measurement_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `eol_ext_5v_measurement_signal` is present and non-empty
- [x] `feedback_signal_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `feedback_signal` is present and non-empty
- [x] `tolerance_mv` is present and non-negative
- [x] `pre_dwell_time_ms` is present and non-negative
- [x] `dwell_time_ms` is present and positive (>= 1)

## Error Handling

### Expected Error Scenarios
List potential errors and how to handle them:

1. **Missing Required Field**
   - Error: `"Missing required External 5V Test parameters"`
   - Handling: Return `False, "External 5V Test requires {field_name}"`

2. **Invalid Field Value**
   - Error: `"Tolerance must be non-negative"`
   - Handling: Return `False, "Tolerance must be non-negative"`

3. **No Data Collected in Disabled Phase**
   - Error: `"No data collected during disabled phase"`
   - Handling: Return `False, "No data collected during disabled phase (EOL samples: {len(eol_values_disabled)}, Feedback samples: {len(feedback_values_disabled)})"`

4. **No Data Collected in Enabled Phase**
   - Error: `"No data collected during enabled phase"`
   - Handling: Return `False, "No data collected during enabled phase (EOL samples: {len(eol_values_enabled)}, Feedback samples: {len(feedback_values_enabled)})"`

5. **DBC Encoding Failure**
   - Error: `"Failed to encode trigger message"`
   - Handling: Return `False, "Failed to encode trigger message"`

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "External 5V Test - Basic",
  "type": "External 5V Test",
  "actuation": {
    "type": "External 5V Test",
    "ext_5v_test_trigger_source": 512,
    "ext_5v_test_trigger_signal": "Ext_5V_Test_Enable",
    "eol_ext_5v_measurement_source": 513,
    "eol_ext_5v_measurement_signal": "EOL_Ext_5V",
    "feedback_signal_source": 514,
    "feedback_signal": "Feedback_5V",
    "tolerance_mv": 50.0,
    "pre_dwell_time_ms": 1000,
    "dwell_time_ms": 3000
  }
}
```

### Example 2: Extended Dwell Time
```json
{
  "name": "External 5V Test - Extended",
  "type": "External 5V Test",
  "actuation": {
    "type": "External 5V Test",
    "ext_5v_test_trigger_source": 512,
    "ext_5v_test_trigger_signal": "Ext_5V_Test_Enable",
    "eol_ext_5v_measurement_source": 513,
    "eol_ext_5v_measurement_signal": "EOL_Ext_5V",
    "feedback_signal_source": 514,
    "feedback_signal": "Feedback_5V",
    "tolerance_mv": 30.0,
    "pre_dwell_time_ms": 2000,
    "dwell_time_ms": 5000
  }
}
```

## Implementation Notes

### Special Considerations
- **Multi-Phase Test**: Test executes two phases (disabled and enabled) and both must pass
- **State Management**: Test manages external 5V state (disabled → enabled → disabled)
- **Dual Signal Collection**: Collects from two CAN signals simultaneously in each phase
- **Real-Time Display**: Both signals displayed in real-time during data collection
- **Cleanup**: Test disables external 5V at the end (returns to safe state)
- **DBC Support**: Test supports both DBC and non-DBC modes

### Dependencies
- **can_service**: Required for sending CAN commands and receiving feedback
- **dbc_service**: Optional but recommended for proper signal encoding/decoding
- **signal_service**: Required for reading feedback and EOL signals

### Similar Test Types
- **Analog Static Test**: Similar dual-signal comparison pattern but single-phase
- **Fan Control Test**: Similar command/feedback pattern but different signals
- **DC Bus Sensing**: Similar comparison pattern but uses oscilloscope as reference

### Testing Requirements
- Test with hardware connected (DUT, EOL hardware, CAN hardware)
- Test with valid DBC file loaded
- Test without DBC file (non-DBC mode)
- Test with various tolerance values
- Test with different pre-dwell and dwell times
- Test error cases (no data collected, invalid values, etc.)
- Verify real-time display of both signals works correctly
- Verify external 5V is disabled after test (cleanup)
- Verify both phases are evaluated correctly

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Analog Static Test` (for dual-signal comparison pattern)
- **Why Similar**: 
  - Both compare two CAN signals
  - Both use pre-dwell + dwell pattern
  - Both calculate averages and compare difference
- **Key Differences**: 
  - External 5V Test has two phases (disabled and enabled)
  - External 5V Test sends trigger commands to change state
  - External 5V Test requires both phases to pass

### Code Patterns to Use
- **Multi-Phase Pattern**: Execute multiple phases and evaluate each
- **State Management Pattern**: Send commands to change state, verify state
- **Dual Signal Collection Pattern**: Collect from two signals simultaneously
- **Pre-Dwell Pattern**: Wait for system stabilization before data collection
- **Cleanup Pattern**: Return system to safe state at end of test
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
- [ ] Multi-phase pattern implemented correctly
- [ ] Cleanup (external 5V disable) implemented

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
- [ ] Verify external 5V is disabled after test
- [ ] Verify both phases are evaluated correctly

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
- Use exact test type name consistently across all files: `"External 5V Test"`
- Support both DBC and non-DBC modes
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style
- Implement multi-phase pattern (disabled and enabled)
- Both phases must pass for overall test to pass
- Disable external 5V at end of test (cleanup)

