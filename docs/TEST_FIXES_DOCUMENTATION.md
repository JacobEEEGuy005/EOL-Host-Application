# Test Runner Fixes Documentation

This document describes all fixes applied to the test runner codebase to address thread safety, validation, error handling, and cleanup issues across all test types.

## Table of Contents

1. [Digital Logic Test Fixes](#1-digital-logic-test-fixes)
2. [Analog Static Test Fixes](#2-analog-static-test-fixes)
3. [Temperature Validation Test Fixes](#3-temperature-validation-test-fixes)
4. [Analog PWM Sensor Test Fixes](#4-analog-pwm-sensor-test-fixes)
5. [External 5V Test Fixes](#5-external-5v-test-fixes)
6. [Cross-Cutting Improvements](#cross-cutting-improvements)

---

## 1. Digital Logic Test Fixes

### Issue 1.1: Thread Safety for GUI Updates
**Location**: Lines 722-726, 732-736, 749-753

**Problem**: Direct GUI method calls (`track_sent_command_value`) from background threads without thread-safe mechanisms could cause GUI crashes or memory corruption.

**Fix**: Created `_track_sent_command_value_thread_safe()` helper function that:
- Checks if current thread is the main GUI thread
- If in main thread: calls directly
- If in background thread: uses `QMetaObject.invokeMethod` with `QueuedConnection` to safely update GUI from background thread

**New Behavior**: 
- GUI updates are now thread-safe and will not cause crashes
- Updates are queued and processed in the main thread when called from background threads
- If update fails, it's logged as debug message instead of crashing

### Issue 1.2: Improved Error Handling for CAN Frame Sending
**Location**: Lines 590-606

**Problem**: `send_frame` exceptions were caught but not logged with sufficient context (CAN ID, signal name).

**Fix**: Enhanced `_send_bytes()` function to:
- Check if `send_frame` returns `False` and log warning with CAN ID and signal name
- Log error with full context (CAN ID, signal) when exceptions occur
- Use `exc_info=True` for better error traceback

**New Behavior**:
- All CAN send failures are now logged with full context
- Warnings are issued when `send_frame` returns `False` (previously silent)
- Better debugging information for CAN communication issues

### Issue 1.3: Feedback Signal Validation
**Location**: Lines 632-705

**Problem**: `_wait_for_value` function didn't validate that feedback signal was configured before attempting to wait for values.

**Fix**: Added validation at the start of `_wait_for_value`:
- Checks if `fb` (feedback signal) is configured
- Returns early with error message if feedback signal is missing
- Prevents infinite waiting when feedback signal is not configured

**New Behavior**:
- Test fails immediately with clear error message if feedback signal is not configured
- No more silent failures or infinite waits when feedback is missing

### Issue 1.4: State Machine Loop Protection
**Location**: Lines 710-767

**Problem**: `while True` loop in state machine had no explicit timeout, could hang indefinitely if state transitions break.

**Fix**: Added safety mechanisms:
- `max_state_transitions` counter (set to 10) to prevent infinite loops
- `state_transition_count` tracks number of state transitions
- Loop breaks if maximum transitions exceeded
- Error message logged and added to info if loop exceeds limit

**New Behavior**:
- State machine will not hang indefinitely
- Maximum of 10 state transitions allowed (should be more than enough for LOW→HIGH→LOW sequence)
- Clear error message if state machine gets stuck

---

## 2. Analog Static Test Fixes

### Issue 2.1: Thread Safety for Result Storage
**Location**: Lines 1751-1754

**Problem**: Direct assignment to `self.gui._test_result_data_temp` from background thread without thread safety checks.

**Fix**: Added thread safety checks:
- Checks if current thread is main thread
- Logs debug message if storing from background thread
- Uses Python's GIL protection (dictionary assignment is atomic)
- Added exception handling for storage failures

**New Behavior**:
- Result data storage is now thread-safe
- Debug logging helps identify when storage happens from background thread
- Failures in storage are logged but don't crash the test

### Issue 2.2: Pre-Dwell Time Validation
**Location**: Lines 1629-1643

**Problem**: Pre-dwell time validated to be non-negative but not checked if reasonable (could be configuration error).

**Fix**: Added validation:
- Warns if pre-dwell time > 60 seconds (likely configuration error)
- Warns if dwell time < 100ms (may not collect sufficient data)

**New Behavior**:
- Warnings issued for suspicious timing values
- Helps identify configuration errors early
- Test still proceeds but user is alerted to potential issues

### Issue 2.3: Data Quality Validation
**Location**: Lines 1751-1756

**Problem**: Test only checked if data was collected, but didn't validate data quality (all zeros, all same value, outliers).

**Fix**: Added comprehensive data quality checks:
- Validates minimum sample count (at least 5 samples or 1 per 200ms)
- Checks for data variation (warns if all values are the same)
- Detects outliers (values > 3 standard deviations from mean)
- Warnings logged but test continues

**New Behavior**:
- Test detects and warns about poor data quality
- Helps identify sensor issues or configuration problems
- Test still completes but results may be questionable if warnings present

---

## 3. Temperature Validation Test Fixes

### Issue 3.1: Simplified Thread Safety Logic
**Location**: Lines 1902-1970

**Problem**: Complex nested thread checking logic with multiple fallback paths increased complexity and potential for bugs.

**Fix**: Simplified to use `update_monitor_signal()` method which already handles thread safety:
- Removed complex nested thread checking
- Uses existing `update_monitor_signal()` method (already thread-safe)
- Cleaner, more maintainable code

**New Behavior**:
- Simpler code that's easier to maintain
- Consistent thread safety approach across all tests
- Reduced code complexity and potential bugs

### Issue 3.2: Reference Temperature Range Validation
**Location**: Lines 1857-1861

**Problem**: Reference temperature not validated against reasonable range.

**Fix**: Added validation:
- Warns if reference temperature outside typical range (-40°C to 150°C)
- Test still proceeds but user is alerted

**New Behavior**:
- Warnings for suspicious temperature values
- Helps catch configuration errors

### Issue 3.3: Data Quality Validation
**Location**: Lines 1883-1890

**Problem**: No validation of temperature data quality or reasonableness.

**Fix**: Added validation:
- Validates minimum sample count
- Checks for data variation
- Validates temperature values are in reasonable range (-40°C to 200°C)
- Warnings logged for suspicious data

**New Behavior**:
- Better detection of sensor issues or configuration problems
- Warnings help identify data quality issues early

### Issue 3.4: Thread Safety for Result Storage
**Location**: Lines 1915-1922

**Problem**: Direct assignment to `_test_result_data_temp` without thread safety.

**Fix**: Same as Analog Static Test - added thread safety checks and exception handling.

**New Behavior**:
- Thread-safe result storage
- Better error handling

---

## 4. Analog PWM Sensor Test Fixes

### Issue 4.1: Thread Safety for GUI Updates
**Location**: Lines 2075-2090

**Problem**: Direct `setText` calls on `feedback_signal_label` without thread safety.

**Fix**: Removed direct GUI updates:
- PWM test doesn't have dedicated monitor signal
- Real-time updates removed (final results displayed after completion)
- Eliminates thread safety issues

**New Behavior**:
- No thread safety issues from GUI updates
- Cleaner code
- Results still displayed after test completion

### Issue 4.2: PWM Frequency Range Validation
**Location**: Lines 2011-2015

**Problem**: Reference PWM frequency not validated against reasonable range.

**Fix**: Added validation:
- Warns if reference frequency outside typical range (0-100kHz)
- Validates duty cycle is 0-100%

**New Behavior**:
- Catches configuration errors early
- Warnings for suspicious values

### Issue 4.3: Duty Cycle Range Validation
**Location**: Lines 2070-2073

**Problem**: Duty cycle values not validated to be in 0-100% range.

**Fix**: Added validation:
- Warns if duty cycle value outside 0-100% range
- Validates calculated averages are in reasonable range

**New Behavior**:
- Better data validation
- Catches sensor issues or configuration problems

### Issue 4.4: Data Quality Validation
**Location**: Lines 2044-2058

**Problem**: No validation of minimum sample count or data quality.

**Fix**: Added validation:
- Validates minimum sample count
- Validates calculated averages are in reasonable range
- Warnings for suspicious data

**New Behavior**:
- Better data quality checks
- Helps identify issues early

---

## 5. External 5V Test Fixes

### Issue 5.1: Trigger Signal Encoding Validation
**Location**: Lines 2127-2174

**Problem**: `_send_trigger` function didn't validate that trigger signal was successfully encoded before sending.

**Fix**: Enhanced `_send_trigger()` function:
- Validates `encode_message` returns non-empty data
- Checks if `send_frame` returns `False` and logs warning
- Better error messages with context
- Returns `False` if encoding fails

**New Behavior**:
- Test fails immediately if encoding fails
- Better error messages for debugging
- No silent failures

### Issue 5.2: Cleanup on Early Return
**Location**: Lines 2334-2356

**Problem**: If test fails during Phase 1, Phase 2 cleanup (disabling External 5V) may not execute.

**Fix**: Added `try-finally` block:
- `finally` block always executes cleanup
- Disables External 5V even if test fails
- Exception handling in cleanup to prevent cleanup failures from masking original error

**New Behavior**:
- External 5V always disabled after test (even on failure)
- Prevents hardware from being left in enabled state
- Better resource cleanup

### Issue 5.3: Phase Validation
**Location**: Lines 2342-2352

**Problem**: Test doesn't validate that Phase 1 (disabled) data was collected before proceeding to Phase 2.

**Fix**: Added validation:
- Checks if Phase 1 data was collected
- Logs warning if data incomplete but continues to Phase 2
- Helps identify data collection issues

**New Behavior**:
- Better visibility into data collection issues
- Test continues but user is alerted to potential problems

---

## Cross-Cutting Improvements

### Thread Safety Pattern
All tests now use consistent thread safety patterns:
- Check if in main thread before direct GUI access
- Use `QMetaObject.invokeMethod` with `QueuedConnection` for background thread updates
- Dictionary assignments are safe due to Python GIL but we still check threads for clarity

### Error Handling
Improved error handling across all tests:
- All exceptions logged with `exc_info=True` for better debugging
- Context information (CAN IDs, signal names) included in error messages
- Warnings for suspicious values instead of silent failures

### Data Quality Validation
All data collection tests now include:
- Minimum sample count validation
- Data variation checks
- Outlier detection
- Range validation for calculated values

### Resource Cleanup
Tests with hardware control now include:
- `try-finally` blocks for cleanup
- Cleanup executes even on test failure
- Exception handling in cleanup to prevent masking original errors

---

## 6. Fan Control Test Fixes

### Issue 6.1: Thread Safety for Monitor Updates
**Location**: Lines 2672-2716

**Problem**: Complex nested thread checking logic similar to Temperature Validation Test, and direct GUI label updates without thread safety.

**Fix**: Simplified to use `update_monitor_signal()` method:
- Removed complex nested thread checking
- Uses existing `update_monitor_signal()` method (already thread-safe)
- Cleaner, more maintainable code

**New Behavior**:
- Simpler code that's easier to maintain
- Consistent thread safety approach
- Reduced code complexity

### Issue 6.2: Fan Tach Signal Range Validation
**Location**: Lines 2667-2670

**Problem**: Fan tach signal expected to be 0 or 1, but no validation that received values are in this range.

**Fix**: Added validation:
- Warns if fan tach signal value outside expected range (0-1)
- Helps identify sensor issues or configuration problems

**New Behavior**:
- Warnings for suspicious values
- Better data validation

### Issue 6.3: Cleanup on Failure
**Location**: Lines 2647-2777

**Problem**: If test fails during fan enabled verification, fan may remain enabled.

**Fix**: Added `try-finally` block:
- `finally` block always executes cleanup
- Disables fan even if test fails
- Exception handling in cleanup to prevent cleanup failures from masking original error

**New Behavior**:
- Fan always disabled after test (even on failure)
- Prevents hardware from being left in enabled state
- Better resource cleanup

### Issue 6.4: Timeout Handling for Fan Enabled
**Location**: Lines 2617-2648

**Problem**: Timeout loop doesn't handle case where fan enabled signal is received but immediately goes back to 0.

**Fix**: Added stability checking:
- Checks if fan enabled signal is stable (same value for multiple readings)
- Requires at least 2 consecutive readings of value 1 before considering verified
- Prevents false positives from transient signals

**New Behavior**:
- More robust fan enabled verification
- Prevents false positives from transient signals
- Better handling of unstable signals

### Issue 6.5: Thread Safety for Result Storage
**Location**: Lines 2809-2816

**Problem**: Direct assignment to `_test_result_data_temp` without thread safety.

**Fix**: Same as other tests - added thread safety checks and exception handling.

**New Behavior**:
- Thread-safe result storage
- Better error handling

---

## Remaining Work

## 7. Analog Sweep Test Fixes

### Issue 7.1: MUX Channel Value Validation
**Location**: Lines 835-848

**Problem**: MUX channel value was not validated, which could lead to invalid configurations being used.

**Fix**: Added validation for MUX channel value:
- Validates that MUX channel value is an integer
- Warns if value is negative or unusually large (>31)
- Defaults to 0 if invalid value is provided

**New Behavior**: 
- Invalid MUX channel values are caught and logged with warnings
- Test continues with default value (0) if invalid value provided
- Prevents potential DBC encoding errors from invalid MUX channel values

### Issue 7.2: Dwell Time Validation
**Location**: Lines 878-896

**Problem**: Dwell time was not validated against data collection period, which could result in insufficient data collection.

**Fix**: Added validation that dwell time is sufficient for data collection:
- Warns if dwell time is less than data collection period
- Ensures test has enough time to collect meaningful data

**New Behavior**:
- Warnings are issued if dwell time is too short
- Helps identify configuration issues early

### Issue 7.3: Linear Regression Data Validation
**Location**: Lines 1596-1644

**Problem**: Linear regression calculation didn't properly validate minimum data points before attempting calculation.

**Fix**: Improved validation:
- Explicitly checks for minimum 2 valid data points before regression
- Better error messages when insufficient data is available
- Validates variance in DAC values before regression

**New Behavior**:
- Clear warnings when insufficient data for regression
- Regression only attempted when sufficient valid data is available
- Better error messages guide troubleshooting

### Issue 7.4: Thread Safety for Plot Data Storage
**Location**: Lines 1656-1668

**Problem**: Plot data storage accessed GUI attributes from background thread without thread safety checks.

**Fix**: Added thread safety checks:
- Checks current thread vs main thread
- Logs when storing from background thread
- Dictionary operations are thread-safe (GIL protects them)

**New Behavior**:
- Plot data storage is thread-safe
- Better logging for debugging thread-related issues

---

## 8. Phase Current Test Fixes

### Issue 8.1: Oscilloscope Service Validation
**Location**: Lines 479-511

**Problem**: Test could proceed without oscilloscope connection, leading to failures later in execution.

**Fix**: Added early validation:
- Checks oscilloscope service is available and connected before proceeding
- Returns early with clear error message if oscilloscope not available

**New Behavior**:
- Test fails early with clear message if oscilloscope not connected
- Prevents wasted time running test that will fail

### Issue 8.2: State Machine Cleanup
**Location**: Lines 502-511

**Problem**: State machine reference cleanup could fail silently, leaving references in GUI.

**Fix**: Enhanced cleanup:
- Added nested try-finally blocks for proper cleanup
- Additional cleanup in outer finally block as safety net
- Validates state machine completed successfully (not None)

**New Behavior**:
- State machine references are always cleaned up
- Test validates state machine returned success status
- Better error messages when state machine fails

---

## 9. DC Bus Sensing Test Fixes

### Issue 9.1: Unit Conversion Logic
**Location**: Lines 2962-2971

**Problem**: Hardcoded unit conversion logic (mV to V) was not well documented and could fail for edge cases.

**Fix**: Improved unit conversion:
- Added clear comments explaining conversion logic
- Added validation that converted values are in reasonable range (0-1000V)
- Warns if values are outside typical DC bus range

**New Behavior**:
- Unit conversion is more robust with validation
- Warnings help identify configuration or measurement issues
- Better documentation of conversion logic

### Issue 9.2: Oscilloscope Data Validation
**Location**: Lines 2997-3007

**Problem**: Oscilloscope average values were not validated before use.

**Fix**: Added validation:
- Validates oscilloscope response is numeric
- Checks value is in reasonable range (0-1000V)
- Returns error if invalid value received

**New Behavior**:
- Invalid oscilloscope data is caught early
- Clear error messages when oscilloscope returns invalid data
- Prevents test from proceeding with bad data

### Issue 9.3: CAN Data Sample Count Validation
**Location**: Lines 3002-3015

**Problem**: Minimum sample count was not validated, which could lead to unreliable averages.

**Fix**: Added validation:
- Calculates minimum expected samples based on dwell time
- Warns if insufficient samples collected
- Validates calculated average is in reasonable range

**New Behavior**:
- Warnings when insufficient data collected
- Helps identify CAN communication issues
- Validates data quality before analysis

### Issue 9.4: Thread Safety for Result Storage
**Location**: Lines 3034-3042

**Problem**: Test result data storage accessed GUI attributes from background thread.

**Fix**: Added thread safety checks:
- Checks current thread vs main thread
- Logs when storing from background thread
- Dictionary operations are thread-safe

**New Behavior**:
- Result storage is thread-safe
- Better logging for debugging

### Issue 9.5: Oscilloscope Channel Verification
**Location**: Lines 2929-2934

**Problem**: Channel was enabled but not verified to be actually measuring.

**Fix**: Added verification:
- Queries channel scale as verification that channel is active
- Helps catch cases where channel is enabled but probe is disconnected

**New Behavior**:
- Better verification that oscilloscope channel is properly configured
- Helps identify hardware connection issues early

---

## 10. Charged HV Bus Test Fixes

### Issue 10.1: Trim Value Range Validation
**Location**: Lines 3407-3420

**Problem**: Trim value was not validated for reasonable range before use.

**Fix**: Added validation:
- Validates trim value is in range 0-200%
- Clamps to valid range if outside
- Warns when clamping occurs

**New Behavior**:
- Invalid trim values are caught and corrected
- Warnings help identify configuration issues
- Prevents invalid values from being sent to DUT

### Issue 10.2: Cleanup on Fault Detection
**Location**: Lines 3607-3711

**Problem**: When fault was detected, test would break out of loop but cleanup (stopping test) might not execute if exception occurred.

**Fix**: Wrapped monitoring loop in try-finally:
- Ensures test stop signal is always sent, even if fault detected or exception occurs
- Improved error handling for send_frame failures
- Better logging of cleanup actions

**New Behavior**:
- Test is always stopped, even on fault or exception
- Better cleanup ensures DUT is left in safe state
- Improved error messages for debugging

---

## 11. Charger Functional Test Fixes

### Issue 11.1: Trim Value Range Validation
**Location**: Lines 4060-4075

**Problem**: Same as Charged HV Bus Test - trim value not validated.

**Fix**: Added same validation as Charged HV Bus Test:
- Validates trim value is in range 0-200%
- Clamps to valid range if outside
- Warns when clamping occurs

**New Behavior**:
- Same improvements as Charged HV Bus Test

### Issue 11.2: Cleanup on Fault Detection
**Location**: Lines 4201-4311

**Problem**: Same as Charged HV Bus Test - cleanup might not execute on fault.

**Fix**: Wrapped monitoring loop in try-finally:
- Ensures test stop signal is always sent
- Improved error handling

**New Behavior**:
- Same improvements as Charged HV Bus Test

### Issue 11.3: Output Current Regulation Validation
**Location**: Lines 4348-4378

**Problem**: Test duration and tolerance were not validated, which could lead to unreliable regulation analysis.

**Fix**: Added validation:
- Validates tolerance is not too large compared to setpoint
- Validates test duration is sufficient (warns if < 2 seconds)
- Validates minimum sample count for regulation analysis
- Handles cases where test is shorter than 1 second

**New Behavior**:
- Warnings when test configuration may lead to unreliable results
- Better handling of edge cases (short test duration)
- Validates data quality before regulation analysis

---

## 12. Output Current Calibration Test Fixes

### Issue 12.1: Setpoint Array Validation
**Location**: Lines 4753-4776

**Problem**: Setpoint array was not validated for size or range.

**Fix**: Added validation:
- Validates minimum 2 setpoints for calibration
- Warns if too many setpoints (may take long time)
- Validates setpoint range is reasonable (0-50A typical)
- Better error messages

**New Behavior**:
- Invalid setpoint configurations are caught early
- Warnings help identify configuration issues
- Prevents test from running with invalid configuration

### Issue 12.2: Thread Safety for Plot Initialization
**Location**: Lines 4762-4776

**Problem**: Plot initialization accessed GUI from background thread without thread safety.

**Fix**: Added thread safety:
- Checks current thread vs main thread
- Uses QMetaObject.invokeMethod for background thread calls
- QueuedConnection ensures safe execution

**New Behavior**:
- Plot initialization is thread-safe
- No crashes from GUI access from background thread

### Issue 12.3: Oscilloscope Data Quality Validation
**Location**: Lines 5003-5017, 5114-5128, 5508-5520

**Problem**: Oscilloscope data was not validated before use in calculations.

**Fix**: Added validation for all oscilloscope queries:
- Validates response is numeric
- Checks value is in reasonable range (0-60A)
- Skips invalid data points with warnings
- Applied to first setpoint, first sweep, and second sweep

**New Behavior**:
- Invalid oscilloscope data is caught and skipped
- Warnings help identify measurement issues
- Prevents bad data from affecting calibration results

### Issue 12.4: CAN Data Quality Validation
**Location**: Lines 5014-5017, 5125-5128, 5544-5547

**Problem**: CAN data was not validated before use.

**Fix**: Added validation:
- Validates CAN average is in reasonable range (0-60A)
- Warns if outside typical range
- Applied consistently across all data collection points

**New Behavior**:
- Invalid CAN data is identified with warnings
- Helps identify CAN communication or signal issues

### Issue 12.5: Adjustment Factor Validation
**Location**: Lines 5208-5215

**Problem**: Adjustment factor was not validated for reasonableness.

**Fix**: Added validation:
- Validates adjustment factor is in typical range (0.5-2.0)
- Warns if outside typical range (may indicate data quality issues)
- Validates calculated trim value is in valid range (0-200%)

**New Behavior**:
- Unusual adjustment factors are flagged with warnings
- Helps identify data quality issues
- Prevents invalid trim values from being calculated

### Issue 12.6: Test Mode Cleanup
**Location**: Lines 4860-4879, 5191-5193, 5576-5578, 5760-5762

**Problem**: Test mode might not be disabled if test fails early or exception occurs.

**Fix**: Created `_disable_test_mode()` helper function and:
- Used helper in all disable test mode locations (Step 8, Step 15)
- Added final cleanup before return to ensure test mode is always disabled
- Improved error handling and logging

**New Behavior**:
- Test mode is always disabled, even on early failure
- Consistent cleanup logic across all disable points
- Better error messages for cleanup failures

### Issue 12.7: Thread Safety for Command Value Tracking
**Location**: Lines 4899-4910, 5055-5067

**Problem**: `track_sent_command_value` called directly from background thread.

**Fix**: Added thread safety:
- Checks current thread vs main thread
- Uses QMetaObject.invokeMethod for background thread calls
- QueuedConnection ensures safe execution

**New Behavior**:
- Command value tracking is thread-safe
- No crashes from GUI access from background thread

---

## Testing Recommendations

After applying these fixes, test the following scenarios:
1. Run tests from background threads to verify thread safety
2. Test with missing/invalid configuration to verify validation
3. Test with poor data quality to verify warnings
4. Test with early failures to verify cleanup executes
5. Test CAN communication failures to verify error handling

---

## Summary of All Fixes

### Tests Fixed (12 out of 12):
1. ✅ **Digital Logic Test** - Thread safety, error handling, validation, loop protection
2. ✅ **Analog Static Test** - Thread safety, data quality validation, pre-dwell validation
3. ✅ **Temperature Validation Test** - Thread safety simplification, validation, data quality
4. ✅ **Analog PWM Sensor Test** - Thread safety, range validation, data quality
5. ✅ **External 5V Test** - Trigger encoding validation, cleanup, phase validation
6. ✅ **Fan Control Test** - Thread safety, cleanup, timeout handling, signal validation
7. ✅ **Analog Sweep Test** - MUX validation, dwell time validation, linear regression validation, thread safety
8. ✅ **Phase Current Test** - Oscilloscope validation, state machine cleanup, error handling
9. ✅ **DC Bus Sensing Test** - Unit conversion validation, oscilloscope validation, sample count validation, thread safety
10. ✅ **Charged HV Bus Test** - Trim value validation, cleanup on fault detection, improved error handling
11. ✅ **Charger Functional Test** - Trim value validation, cleanup on fault detection, regulation validation
12. ✅ **Output Current Calibration Test** - Setpoint validation, thread safety, data quality validation, cleanup

### Key Improvements Applied:
- **Thread Safety**: All GUI updates now use thread-safe mechanisms
- **Error Handling**: Improved error logging with context
- **Data Quality**: Validation for minimum samples, variation, outliers
- **Resource Cleanup**: `try-finally` blocks ensure cleanup even on failure
- **Validation**: Range checks, reasonableness checks, configuration validation
- **Code Quality**: Simplified complex logic, reduced code duplication

## Version History

- **2024-01-XX**: Initial fixes for Digital Logic, Analog Static, Temperature Validation, Analog PWM Sensor, External 5V, and Fan Control tests
- **2024-01-XX**: Completed fixes for Analog Sweep, Phase Current, DC Bus Sensing, Charged HV Bus, Charger Functional, and Output Current Calibration tests

