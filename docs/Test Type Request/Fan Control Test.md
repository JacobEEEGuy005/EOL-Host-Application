# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `Fan Control Test`
- **Short Description**: `Tests fan control system by enabling fan and verifying tach feedback and fault status`
- **Detailed Description**: 
  ```
  This test validates the fan control system functionality by enabling the fan and monitoring
  the fan's response signals (enabled status, tach feedback, and fault status).
  
  How it works:
  - The test sends a fan test trigger signal (value = 1) to enable the fan
  - Waits up to test_timeout_ms for the fan enabled signal to become 1
  - If fan enabled signal doesn't reach 1 within timeout → test fails
  - After fan enabled is verified, collects fan tach feedback and fan fault feedback signals
    during the dwell time
  - Displays fan tach signal value in real-time monitoring
  - After dwell time, checks latest values:
    * Fan Tach Feedback Signal should be 1 (fan is running)
    * Fan Fault Feedback Signal should be 0 (no fault)
  - Test passes if both conditions are met
  - Finally, sends fan test trigger signal (value = 0) to disable the fan
  
  Hardware Requirements:
  - Device Under Test (DUT) with fan control system
  - EOL Hardware
  - CAN Hardware (Canalystii or compatible)
  - Fan connected to DUT
  
  Special Considerations:
  - Test has timeout mechanism for fan enabled verification
  - Real-time display of fan tach signal during data collection
  - Test disables fan at the end (cleanup)
  - Supports both DBC and non-DBC modes
  ```

## Test Configuration Fields

### Required Fields
List all fields that must be provided for this test type:

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `fan_test_trigger_source` | `integer` | `CAN message ID for fan test trigger command` | `Range: 0-0x1FFFFFFF, Required` | `0x200` |
| `fan_test_trigger_signal` | `string` | `CAN signal name for fan test trigger` | `Non-empty, Required` | `"Fan_Test_Enable"` |
| `fan_control_feedback_source` | `integer` | `CAN message ID containing fan feedback signals` | `Range: 0-0x1FFFFFFF, Required` | `0x201` |
| `fan_enabled_signal` | `string` | `CAN signal name for fan enabled status` | `Non-empty, Required` | `"Fan_Enabled"` |
| `fan_tach_feedback_signal` | `string` | `CAN signal name for fan tach feedback` | `Non-empty, Required` | `"Fan_Tach"` |
| `fan_fault_feedback_signal` | `string` | `CAN signal name for fan fault feedback` | `Non-empty, Required` | `"Fan_Fault"` |
| `dwell_time_ms` | `integer` | `Time to collect fan feedback data in milliseconds` | `Minimum: 1, Required` | `3000` |
| `test_timeout_ms` | `integer` | `Timeout for fan enabled verification in milliseconds` | `Minimum: 1, Required` | `5000` |

### CAN Message/Signal Fields
If the test uses CAN communication, specify:

- **Command Message** (sending commands to DUT):
  - Message ID: `fan_test_trigger_source` (configurable, e.g., 0x200)
  - Signals used: 
    - `fan_test_trigger_signal` - Enable/disable fan test (value: 1 to enable, 0 to disable)
    - `DeviceID` - Device ID (if message is multiplexed, default: 0)
    - `MessageType` - Message type (if signal is multiplexed)
  - Purpose: `Send fan test trigger command to enable/disable fan`

- **Feedback Messages** (reading fan status from DUT):
  - Message ID: `fan_control_feedback_source` (configurable, e.g., 0x201)
  - Signals used: 
    - `fan_enabled_signal` - Fan enabled status (1 = enabled, 0 = disabled)
    - `fan_tach_feedback_signal` - Fan tachometer feedback (1 = running, 0 = stopped)
    - `fan_fault_feedback_signal` - Fan fault status (0 = no fault, 1 = fault)
  - Purpose: `Read fan status signals from DUT for verification`

- **DBC Support**: `Yes` - Test works with DBC file loaded (dropdowns for messages/signals)
- **Non-DBC Support**: `Yes` - Test works without DBC file (free-text inputs for CAN IDs and signal names)

## Test Execution Logic

### Execution Flow
Describe the step-by-step execution flow:

```
1. Send Fan Test Trigger (Enable)
   - Action: 
     - Encode and send CAN message with fan_test_trigger_signal = 1
     - Include DeviceID and MessageType if message is multiplexed
   - Duration: As fast as possible
   - Expected result: Fan enable command sent successfully

2. Wait for Fan Enabled Signal
   - Action: 
     - Continuously poll fan_enabled_signal from CAN
     - Check if signal value equals 1
     - Continue polling until timeout or signal becomes 1
   - Duration: Up to test_timeout_ms milliseconds
   - Expected result: Fan enabled signal reaches 1 within timeout → fan_enabled_verified = True

3. Verify Fan Enabled
   - Action: 
     - Check if fan_enabled_verified is True
     - If False → return FAIL (fan did not enable within timeout)
   - Duration: As fast as possible
   - Expected result: Fan enabled verification passed

4. Collect Fan Feedback Data
   - Action: 
     - Continuously read fan_tach_feedback_signal and fan_fault_feedback_signal from CAN
     - Store all readings in lists
     - Update real-time display with latest fan tach value
     - Continue for dwell_time_ms
   - Duration: dwell_time_ms milliseconds
   - Expected result: Multiple samples of tach and fault signals collected

5. Disable Fan (Cleanup)
   - Action: 
     - Encode and send CAN message with fan_test_trigger_signal = 0
   - Duration: As fast as possible
   - Expected result: Fan disable command sent (test continues even if this fails)

6. Check Data Collection
   - Action: 
     - Verify that at least one tach and fault reading was collected
   - Duration: As fast as possible
   - Expected result: Fan feedback data available for analysis

7. Determine Pass/Fail
   - Action: 
     - Get latest values: latest_tach = last value in fan_tach_values
     - Get latest values: latest_fault = last value in fan_fault_values
     - Check: tach_ok = (latest_tach == 1)
     - Check: fault_ok = (latest_fault == 0)
     - PASS if (tach_ok AND fault_ok)
     - FAIL if (NOT tach_ok OR NOT fault_ok)
   - Duration: As fast as possible
   - Expected result: Test result determined and returned
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `Fan enabled signal reaches 1 within timeout AND latest fan tach signal = 1 AND latest fan fault signal = 0`
- **Fail Condition**: `Fan enabled signal does not reach 1 within timeout OR latest fan tach signal ≠ 1 OR latest fan fault signal ≠ 0`
- **Calculation Method**: 
  ```
  1. Fan Enabled Verification:
     - Send fan test trigger = 1
     - Poll fan_enabled_signal during test_timeout_ms
     - If signal reaches 1 → fan_enabled_verified = True
     - If timeout expires without signal = 1 → fan_enabled_verified = False → FAIL
  
  2. Fan Feedback Collection:
     - Collect fan_tach_feedback_signal and fan_fault_feedback_signal during dwell_time_ms
     - Store all readings in lists
  
  3. Pass/Fail Determination:
     - latest_tach = last value in fan_tach_values
     - latest_fault = last value in fan_fault_values
     - tach_ok = (int(float(latest_tach)) == 1)
     - fault_ok = (int(float(latest_fault)) == 0)
     - PASS if (fan_enabled_verified AND tach_ok AND fault_ok)
     - FAIL if (NOT fan_enabled_verified OR NOT tach_ok OR NOT fault_ok)
  ```

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: 
  - `fan_enabled_signal` from CAN (during timeout period)
  - `fan_tach_feedback_signal` from CAN (during dwell time)
  - `fan_fault_feedback_signal` from CAN (during dwell time)
  
- **Collection Duration**: 
  - Fan enabled verification: Up to `test_timeout_ms` milliseconds
  - Fan feedback collection: `dwell_time_ms` milliseconds
  
- **Sampling Rate**: 
  - Polled every SLEEP_INTERVAL_SHORT (typically 50-100ms) during both timeout and dwell periods
  
- **Data Processing**: 
  ```
  1. Fan Enabled Verification:
     - Poll fan_enabled_signal continuously
     - Check if value equals 1
     - Stop polling when signal = 1 or timeout expires
  
  2. Fan Feedback Collection:
     - Continuously poll fan_tach_feedback_signal and fan_fault_feedback_signal
     - Store all readings in lists
     - Update real-time display with latest tach value
  
  3. Pass/Fail Determination:
     - Use latest values (last in list) for tach and fault signals
     - Check if tach = 1 and fault = 0
  ```

### Timing Requirements
Specify any timing requirements:

- **Test Timeout**: `test_timeout_ms` (default: 5000ms) - Maximum time to wait for fan enabled signal
- **Dwell Time**: `dwell_time_ms` (default: 3000ms) - Time to collect fan feedback data after fan is enabled
- **Polling Interval**: `SLEEP_INTERVAL_SHORT` (typically 50-100ms) - Interval between signal checks
- **Total Duration**: 
  ```
  Estimated total test duration:
  = fan_enable_time (≈0.1s)
  + fan_enabled_verification (up to test_timeout_ms, typically < 1s)
  + dwell_time_ms
  + fan_disable_time (≈0.1s)
  
  Example with test_timeout_ms = 5000ms, dwell_time_ms = 3000ms:
  ≈ 0.1s + 1.0s + 3.0s + 0.1s
  ≈ 4.2 seconds (if fan enables quickly)
  ≈ 5.1+ seconds (if fan takes full timeout)
  ```

## GUI Requirements

### Create/Edit Dialog Fields
Specify the UI fields needed:

#### Field 1: Fan Test Trigger Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x200)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 2: Fan Test Trigger Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 3: Fan Control Feedback Source
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x201)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 4: Fan Enabled Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 5: Fan Tach Feedback Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 6: Fan Fault Feedback Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes`

#### Field 7: Dwell Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter dwell time in milliseconds (e.g., 3000)`
- **Validator**: `Integer >= 1, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 8: Test Timeout
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter timeout in milliseconds (e.g., 5000)`
- **Validator**: `Integer >= 1, Required`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

### Feedback Fields Visibility
- **Show Feedback Fields**: `No` - This test type has its own feedback fields (fan_control_feedback_source and fan signals)
- **Custom Feedback Fields**: `Yes` - Uses fan_control_feedback_source and multiple fan signals

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
    "type": {"const": "Fan Control Test"},
    "fan_test_trigger_source": {"type": "integer"},
    "fan_test_trigger_signal": {"type": "string"},
    "fan_control_feedback_source": {"type": "integer"},
    "fan_enabled_signal": {"type": "string"},
    "fan_tach_feedback_signal": {"type": "string"},
    "fan_fault_feedback_signal": {"type": "string"},
    "dwell_time_ms": {"type": "integer", "minimum": 1},
    "test_timeout_ms": {"type": "integer", "minimum": 1}
  },
  "required": [
    "fan_test_trigger_source",
    "fan_test_trigger_signal",
    "fan_control_feedback_source",
    "fan_enabled_signal",
    "fan_tach_feedback_signal",
    "fan_fault_feedback_signal",
    "dwell_time_ms",
    "test_timeout_ms"
  ]
}
```

### Application Validation
List validation checks to perform in `_validate_test()`:

- [x] Test type is in allowed list
- [x] Actuation type matches test type
- [x] `fan_test_trigger_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `fan_test_trigger_signal` is present and non-empty
- [x] `fan_control_feedback_source` is present and in valid range (0-0x1FFFFFFF)
- [x] `fan_enabled_signal` is present and non-empty
- [x] `fan_tach_feedback_signal` is present and non-empty
- [x] `fan_fault_feedback_signal` is present and non-empty
- [x] `dwell_time_ms` is present and positive (>= 1)
- [x] `test_timeout_ms` is present and positive (>= 1)

## Error Handling

### Expected Error Scenarios
List potential errors and how to handle them:

1. **Missing Required Field**
   - Error: `"Missing required Fan Control Test parameters"`
   - Handling: Return `False, "Fan Control Test requires {field_name}"`

2. **Invalid Field Value**
   - Error: `"Dwell time must be positive"`
   - Handling: Return `False, "Dwell time must be positive"`

3. **Fan Enabled Timeout**
   - Error: `"Fan enabled signal did not reach 1 within timeout"`
   - Handling: Return `False, "Fan enabled signal did not reach 1 within timeout ({test_timeout_ms}ms). Check fan control configuration."`

4. **No Tach Data Collected**
   - Error: `"No fan tach data received during dwell time"`
   - Handling: Return `False, "No fan tach data received during dwell time ({dwell_time_ms}ms). Check CAN connection and signal configuration."`

5. **No Fault Data Collected**
   - Error: `"No fan fault data received during dwell time"`
   - Handling: Return `False, "No fan fault data received during dwell time ({dwell_time_ms}ms). Check CAN connection and signal configuration."`

6. **DBC Encoding Failure**
   - Error: `"Failed to encode fan trigger message"`
   - Handling: Return `False, "Failed to encode fan trigger message"`

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "Fan Control Test - Basic",
  "type": "Fan Control Test",
  "actuation": {
    "type": "Fan Control Test",
    "fan_test_trigger_source": 512,
    "fan_test_trigger_signal": "Fan_Test_Enable",
    "fan_control_feedback_source": 513,
    "fan_enabled_signal": "Fan_Enabled",
    "fan_tach_feedback_signal": "Fan_Tach",
    "fan_fault_feedback_signal": "Fan_Fault",
    "dwell_time_ms": 3000,
    "test_timeout_ms": 5000
  }
}
```

### Example 2: Extended Timeout
```json
{
  "name": "Fan Control Test - Extended Timeout",
  "type": "Fan Control Test",
  "actuation": {
    "type": "Fan Control Test",
    "fan_test_trigger_source": 512,
    "fan_test_trigger_signal": "Fan_Test_Enable",
    "fan_control_feedback_source": 513,
    "fan_enabled_signal": "Fan_Enabled",
    "fan_tach_feedback_signal": "Fan_Tach",
    "fan_fault_feedback_signal": "Fan_Fault",
    "dwell_time_ms": 5000,
    "test_timeout_ms": 10000
  }
}
```

## Implementation Notes

### Special Considerations
- **Timeout Mechanism**: Test has a timeout for fan enabled verification (different from dwell time)
- **Real-Time Display**: Fan tach signal value displayed in real-time during data collection
- **Cleanup**: Test disables fan at the end (sends trigger = 0)
- **Multiple Signals**: Test monitors three different feedback signals (enabled, tach, fault)
- **Latest Value Check**: Pass/fail uses latest values (not averages) for tach and fault signals
- **DBC Support**: Test supports both DBC and non-DBC modes

### Dependencies
- **can_service**: Required for sending CAN commands and receiving feedback
- **dbc_service**: Optional but recommended for proper signal encoding/decoding
- **signal_service**: Required for reading fan feedback signals

### Similar Test Types
- **Digital Logic Test**: Similar command/feedback pattern but for digital relays
- **External 5V Test**: Similar multi-phase pattern but for power supply testing

### Testing Requirements
- Test with hardware connected (DUT, CAN hardware, fan)
- Test with valid DBC file loaded
- Test without DBC file (non-DBC mode)
- Test with various timeout values
- Test with different dwell times
- Test error cases (fan doesn't enable, no data collected, etc.)
- Verify real-time tach display works correctly
- Verify fan is disabled after test (cleanup)

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Digital Logic Test` (for command/feedback pattern)
- **Why Similar**: 
  - Both send commands and verify feedback
  - Both use timeout/verification mechanisms
- **Key Differences**: 
  - Fan Control Test has timeout for enabled verification
  - Fan Control Test monitors multiple feedback signals
  - Fan Control Test uses latest values (not state stability)

### Code Patterns to Use
- **Command + Feedback Pattern**: Send command, wait for feedback, verify
- **Timeout Pattern**: Poll signal with timeout mechanism
- **Multi-Signal Collection Pattern**: Collect multiple signals simultaneously
- **Cleanup Pattern**: Disable/cleanup at end of test
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
- [ ] Timeout mechanism implemented correctly
- [ ] Cleanup (fan disable) implemented

### Testing Requirements
- [ ] Test with valid configuration
- [ ] Test with invalid configuration (should fail validation)
- [ ] Test with DBC loaded
- [ ] Test without DBC loaded
- [ ] Test execution produces correct results
- [ ] Error cases handled gracefully (fan doesn't enable, no data collected, etc.)
- [ ] Test with various timeout values
- [ ] Test with different dwell times
- [ ] Verify real-time tach display works correctly
- [ ] Verify fan is disabled after test

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
- Use exact test type name consistently across all files: `"Fan Control Test"`
- Support both DBC and non-DBC modes
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style
- Implement timeout mechanism for fan enabled verification
- Use latest values (not averages) for tach and fault signals
- Disable fan at end of test (cleanup)

