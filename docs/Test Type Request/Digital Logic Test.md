# New Test Type Implementation Request

## Test Type Information

### Basic Details
- **Test Type Name**: `Digital Logic Test`
- **Short Description**: `Tests digital relay states by sending LOW→HIGH→LOW sequence and verifying feedback`
- **Detailed Description**: 
  ```
  This test verifies digital relay functionality by sending a sequence of commands to the DUT
  and monitoring the feedback signal to ensure the relay responds correctly.
  
  How it works:
  - The test sends a LOW value command to the DUT via CAN
  - Waits for the feedback signal to match the LOW value and remain stable during dwell time
  - Sends a HIGH value command to the DUT via CAN
  - Waits for the feedback signal to match the HIGH value and remain stable during dwell time
  - Sends a LOW value command again to return to initial state
  - Waits for the feedback signal to match the LOW value and remain stable during dwell time
  - Test passes if both HIGH and LOW states are correctly observed and sustained
  
  Hardware Requirements:
  - Device Under Test (DUT)
  - EOL Hardware
  - CAN Hardware (Canalystii or compatible)
  
  Special Considerations:
  - Test uses a state machine pattern (ENSURE_LOW → ACTUATE_HIGH → ENSURE_LOW_AFTER_HIGH → WAIT_LOW_DWELL)
  - Feedback signal must remain stable during dwell time (not just transient)
  - Supports both DBC and non-DBC modes
  - Can test individual relay signals (CMD_Relay_1, CMD_Relay_2, CMD_Relay_3, CMD_Relay_4)
  ```

## Test Configuration Fields

### Required Fields
List all fields that must be provided for this test type:

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `can_id` | `integer` | `CAN message ID for relay command` | `Range: 0-0x1FFFFFFF, Required` | `0x100` |
| `signal` | `string` | `CAN signal name for relay command (optional in non-DBC mode)` | `Non-empty if DBC loaded, Optional otherwise` | `"CMD_Relay_1"` |
| `value_low` | `string` or `integer` | `Low value to send (typically 0)` | `Required` | `"0"` or `0` |
| `value_high` | `string` or `integer` | `High value to send (typically 1)` | `Required` | `"1"` or `1` |
| `dwell_ms` | `integer` | `Dwell time in milliseconds for each state verification` | `Minimum: 0, Default: 1000` | `1000` |

### Optional Fields

| Field Name | Type | Description | Validation Rules | Example Value |
|------------|------|-------------|------------------|---------------|
| `device_id` | `integer` | `Device ID for multiplexed messages (default: 0)` | `Range: 0-255, Optional` | `0` |
| `feedback_signal` | `string` | `Signal name for feedback verification (from test config, not actuation)` | `Optional` | `"Relay_Feedback"` |
| `feedback_message_id` | `integer` | `CAN message ID for feedback signal (from test config, not actuation)` | `Range: 0-0x1FFFFFFF, Optional` | `0x101` |

### CAN Message/Signal Fields
If the test uses CAN communication, specify:

- **Command Message** (sending commands to DUT):
  - Message ID: `can_id` (configurable, e.g., 0x100)
  - Signals used: 
    - `signal` - Relay command signal (e.g., CMD_Relay_1, CMD_Relay_2, CMD_Relay_3, CMD_Relay_4)
    - `DeviceID` - Device ID (if message is multiplexed, default: 0)
    - `MessageType` - Message type (if message is multiplexed, typically MSG_TYPE_SET_RELAY)
  - Purpose: `Send relay state commands (LOW/HIGH) to DUT`

- **Feedback Messages** (reading relay state from DUT):
  - Message ID: `feedback_message_id` (from test config, optional)
  - Signals used: 
    - `feedback_signal` - Relay feedback signal (from test config, optional)
  - Purpose: `Read relay state from DUT for verification`

- **DBC Support**: `Yes` - Test works with DBC file loaded (dropdowns for messages/signals)
- **Non-DBC Support**: `Yes` - Test works without DBC file (free-text inputs for CAN IDs and values)

## Test Execution Logic

### Execution Flow
Describe the step-by-step execution flow:

```
1. Initialize State Machine
   - Action: 
     - Validate CAN ID, signal, and values
     - Encode LOW and HIGH values to bytes (using DBC if available)
     - Initialize state machine to 'ENSURE_LOW' state
   - Duration: As fast as possible
   - Expected result: State machine ready, values encoded

2. ENSURE_LOW State
   - Action: 
     - Send LOW value command via CAN
     - Wait for SLEEP_INTERVAL_MEDIUM (typically 50ms)
   - Duration: ~50ms
   - Expected result: LOW command sent, transition to ACTUATE_HIGH state

3. ACTUATE_HIGH State
   - Action: 
     - Send HIGH value command via CAN
     - Wait for feedback signal to match HIGH value
     - Verify feedback signal remains HIGH for entire dwell time
   - Duration: dwell_ms milliseconds (or until feedback matches and remains stable)
   - Expected result: Feedback signal matches HIGH value and remains stable → high_ok = True

4. ENSURE_LOW_AFTER_HIGH State
   - Action: 
     - Send LOW value command via CAN
     - Wait for SLEEP_INTERVAL_MEDIUM (typically 50ms)
   - Duration: ~50ms
   - Expected result: LOW command sent, transition to WAIT_LOW_DWELL state

5. WAIT_LOW_DWELL State
   - Action: 
     - Wait for feedback signal to match LOW value
     - Verify feedback signal remains LOW for entire dwell time
   - Duration: dwell_ms milliseconds (or until feedback matches and remains stable)
   - Expected result: Feedback signal matches LOW value and remains stable → low_ok = True

6. Cleanup
   - Action: 
     - Send LOW value command one final time to ensure safe state
     - Wait 50ms
   - Duration: ~50ms
   - Expected result: DUT returned to LOW state

7. Determine Pass/Fail
   - Action: 
     - Test passes if both high_ok and low_ok are True
     - Test fails if either high_ok or low_ok is False
   - Duration: As fast as possible
   - Expected result: Pass/fail determined, result returned
```

### Pass/Fail Criteria
Define how the test determines pass or fail:

- **Pass Condition**: `Both HIGH and LOW states are correctly observed and sustained during their respective dwell times (high_ok = True AND low_ok = True)`
- **Fail Condition**: `Either HIGH or LOW state is not observed or not sustained during dwell time (high_ok = False OR low_ok = False)`
- **Calculation Method**: 
  ```
  1. HIGH State Verification:
     - Send HIGH command
     - Monitor feedback signal during dwell time
     - Feedback must match HIGH value and remain stable (no transient values)
     - If feedback matches and remains stable → high_ok = True
     - If feedback never matches or changes during dwell → high_ok = False
  
  2. LOW State Verification:
     - Send LOW command
     - Monitor feedback signal during dwell time
     - Feedback must match LOW value and remain stable (no transient values)
     - If feedback matches and remains stable → low_ok = True
     - If feedback never matches or changes during dwell → low_ok = False
  
  3. Final Result:
     - PASS if (high_ok = True AND low_ok = True)
     - FAIL if (high_ok = False OR low_ok = False)
  ```

### Data Collection
Specify what data needs to be collected:

- **Signals to Monitor**: 
  - `feedback_signal` from CAN (relay state feedback, optional)
  
- **Collection Duration**: `dwell_ms` milliseconds per state (HIGH and LOW)
  
- **Sampling Rate**: 
  - Polled every SLEEP_INTERVAL_SHORT (typically 50-100ms) during dwell time
  
- **Data Processing**: 
  ```
  1. During Dwell Time:
     - Continuously poll feedback signal
     - Check if feedback matches expected value (HIGH or LOW)
     - Track when first match occurs (matched_start timestamp)
     - If feedback changes after match → fail immediately
     - If feedback remains stable until end of dwell → pass for that state
  
  2. State Verification:
     - HIGH state: Verify feedback = HIGH value and remains stable
     - LOW state: Verify feedback = LOW value and remains stable
  ```

### Timing Requirements
Specify any timing requirements:

- **State Transition Time**: `SLEEP_INTERVAL_MEDIUM` (typically 50ms) - Wait time after sending command before checking feedback
- **Dwell Time**: `dwell_ms` (default: 1000ms) - Time to verify feedback signal remains stable in each state
- **Polling Interval**: `SLEEP_INTERVAL_SHORT` (typically 50-100ms) - Interval between feedback signal checks
- **Total Duration**: 
  ```
  Estimated total test duration:
  = initialization_time (≈0.1s)
  + ENSURE_LOW_time (≈0.05s)
  + ACTUATE_HIGH_dwell (dwell_ms)
  + ENSURE_LOW_AFTER_HIGH_time (≈0.05s)
  + WAIT_LOW_DWELL (dwell_ms)
  + cleanup_time (≈0.05s)
  
  Example with dwell_ms = 1000ms:
  ≈ 0.1s + 0.05s + 1.0s + 0.05s + 1.0s + 0.05s
  ≈ 2.25 seconds
  ```

## GUI Requirements

### Create/Edit Dialog Fields
Specify the UI fields needed:

#### Field 1: CAN Message ID
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select CAN message` / `Enter CAN ID (e.g., 0x100)`
- **Validator**: `Integer 0-0x1FFFFFFF`
- **DBC Mode**: `Dropdown`
- **Required**: `Yes`

#### Field 2: Signal
- **Type**: `QComboBox` (DBC mode) / `QLineEdit` (non-DBC mode)
- **Placeholder**: `Select signal` / `Enter signal name`
- **Validator**: `Non-empty string (if DBC loaded)`
- **DBC Mode**: `Dropdown (populated based on selected message)`
- **Required**: `Yes (if DBC loaded), Optional (if no DBC)`

#### Field 3: Low Value
- **Type**: `QLineEdit`
- **Placeholder**: `Enter low value (typically 0)`
- **Validator**: `String or integer (0, "0", "0x0")`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 4: High Value
- **Type**: `QLineEdit`
- **Placeholder**: `Enter high value (typically 1)`
- **Validator**: `String or integer (1, "1", "0x1")`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `Yes`

#### Field 5: Dwell Time
- **Type**: `QLineEdit` with QIntValidator
- **Placeholder**: `Enter dwell time in milliseconds (e.g., 1000)`
- **Validator**: `Integer >= 0, Default: 1000`
- **DBC Mode**: `Free-text (same for both modes)`
- **Required**: `No (defaults to 1000ms)`

### Feedback Fields Visibility
- **Show Feedback Fields**: `Yes` - Test can use feedback signal for verification (optional)
- **Custom Feedback Fields**: `No` - Uses standard feedback_signal and feedback_message_id from test config

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

- **Applied Input**: Displays the last sent command value (HIGH=1 or LOW=0)
  - Tracks `value_high` and `value_low` from test configuration
  - Updates when HIGH or LOW commands are sent during state machine transitions
  - Format: `Applied Input : 1` or `Applied Input : 0`
  
- **Digital Input**: Displays the feedback signal value from DUT
  - Updates in real-time via periodic polling (100ms)
  - Format: `Digital Input : 0` or `Digital Input : 1`

The monitoring section automatically configures these labels when the test starts and clears them when the test completes. See [Real-Time Monitoring](../REAL_TIME_MONITORING.md) for detailed documentation.

## Validation Rules

### Schema Validation
Specify JSON schema requirements:

```json
{
  "properties": {
    "type": {"const": "Digital Logic Test"},
    "can_id": {"type": "integer"},
    "signal": {"type": "string"},
    "value": {"type": ["string", "integer"]}
  },
  "required": ["can_id"]
}
```

### Application Validation
List validation checks to perform in `_validate_test()`:

- [x] Test type is in allowed list
- [x] Actuation type matches test type
- [x] `can_id` is present and in valid range (0-0x1FFFFFFF)
- [x] `signal` is present if DBC is loaded (optional if no DBC)
- [x] `value_low` is present (or `value` as fallback)
- [x] `value_high` is present
- [x] `dwell_ms` is non-negative (defaults to 1000 if not specified)

## Error Handling

### Expected Error Scenarios
List potential errors and how to handle them:

1. **Missing Required Field**
   - Error: `"Missing required field: can_id"`
   - Handling: Return `False, "Digital Logic Test requires can_id"`

2. **Invalid CAN ID**
   - Error: `"Invalid CAN ID: {can_id}"`
   - Handling: Return `False, "Invalid CAN ID: {can_id}"`

3. **No Feedback Signal Configured**
   - Error: `"No feedback signal configured"`
   - Handling: Test continues but cannot verify states (may always pass or fail depending on implementation)

4. **Feedback Never Matches Expected Value**
   - Error: `"Did not observe expected value {value} during dwell"`
   - Handling: Return `False, "Did not observe expected value {value} during dwell"`

5. **Feedback Changes During Dwell**
   - Error: `"Value changed during dwell (last={value})"`
   - Handling: Return `False, "Value changed during dwell (last={value})"`

6. **DBC Encoding Failure**
   - Error: `"Failed to encode message"`
   - Handling: Fall back to raw byte encoding if DBC encoding fails

## Test Examples

### Example 1: Basic Configuration
```json
{
  "name": "Digital Logic Test - Relay 1",
  "type": "Digital Logic Test",
  "feedback_signal": "Relay_1_Feedback",
  "feedback_message_id": 256,
  "actuation": {
    "type": "Digital Logic Test",
    "can_id": 256,
    "signal": "CMD_Relay_1",
    "value_low": "0",
    "value_high": "1",
    "dwell_ms": 1000
  }
}
```

### Example 2: Non-DBC Mode
```json
{
  "name": "Digital Logic Test - Raw",
  "type": "Digital Logic Test",
  "actuation": {
    "type": "Digital Logic Test",
    "can_id": 256,
    "value_low": "0x00",
    "value_high": "0x01",
    "dwell_ms": 500
  }
}
```

## Implementation Notes

### Special Considerations
- **State Machine Pattern**: Test uses a state machine to manage the LOW→HIGH→LOW sequence
- **Feedback Stability**: Feedback signal must remain stable during dwell time, not just transient
- **DBC Support**: Test supports both DBC and non-DBC modes
- **Multiplexed Signals**: Test handles multiplexed signals (DeviceID, MessageType) when DBC is loaded
- **Relay Selection**: Can test individual relays (CMD_Relay_1, CMD_Relay_2, CMD_Relay_3, CMD_Relay_4)

### Dependencies
- **can_service**: Required for sending CAN commands
- **dbc_service**: Optional but recommended for proper signal encoding
- **signal_service**: Optional but recommended for reading feedback signals

### Similar Test Types
- **Analog Sweep Test**: Similar command/feedback pattern but for analog signals
- **Fan Control Test**: Similar state verification pattern but for fan control

### Testing Requirements
- Test with hardware connected (DUT, CAN hardware)
- Test with valid DBC file loaded
- Test without DBC file (non-DBC mode)
- Test with various dwell times
- Test with different relay signals
- Test error cases (no feedback, feedback mismatch, etc.)

## Report Export

### HTML Export
Test results are automatically included in HTML report exports:
- Test details (name, type, status, execution time, parameters, notes)
- No plot data (test does not generate plots)

### PDF Export
Test results are automatically included in PDF report exports:
- Test details table with all test information
- No plot data (test does not generate plots)
- Professional formatting with consistent styling and spacing

## Reference Implementation

### Similar Test Type to Follow
- **Test Type**: `Analog Sweep Test` (for command/feedback pattern)
- **Why Similar**: 
  - Both send commands and verify feedback
  - Both use dwell time for verification
- **Key Differences**: 
  - Digital Logic Test uses discrete states (LOW/HIGH)
  - Digital Logic Test uses state machine pattern
  - Digital Logic Test verifies state stability during dwell

### Code Patterns to Use
- **State Machine Pattern**: Use state machine for LOW→HIGH→LOW sequence
- **Feedback Verification Pattern**: Poll feedback signal and verify stability
- **DBC Encoding Pattern**: Use DBC service for encoding if available, fallback to raw bytes
- **Non-Blocking Sleep**: Use `_nb_sleep()` for state transitions

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
- [ ] State machine pattern implemented correctly

### Testing Requirements
- [ ] Test with valid configuration
- [ ] Test with invalid configuration (should fail validation)
- [ ] Test with DBC loaded
- [ ] Test without DBC loaded
- [ ] Test execution produces correct results
- [ ] Error cases handled gracefully (no feedback, feedback mismatch, etc.)
- [ ] Test with various dwell times
- [ ] Test with different relay signals

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
- Use exact test type name consistently across all files: `"Digital Logic Test"`
- Support both DBC and non-DBC modes
- Use `_nb_sleep()` instead of `time.sleep()`
- Provide meaningful error messages
- Add appropriate logging
- Follow existing code patterns and style
- Implement state machine pattern for LOW→HIGH→LOW sequence
- Verify feedback signal stability during dwell time

