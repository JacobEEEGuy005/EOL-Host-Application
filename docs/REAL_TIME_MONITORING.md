# Real-Time Monitoring System

## Overview

The Real-Time Monitoring system provides a dynamic, test-specific display of signal values during test execution. The monitoring section automatically configures itself based on the active test type, displaying only the relevant signals for that test.

## Features

- **Dynamic Configuration**: Monitoring labels change based on the active test type
- **Fixed 3x2 Grid Layout**: Compact display with 3 rows and 2 columns (6 total slots)
- **Sent Command Tracking**: Tracks and displays the latest sent command values for certain test types
- **Static Reference Values**: Displays constant reference values from test configuration
- **Automatic Updates**: Signals are updated in real-time via periodic polling (100ms) and event-driven updates
- **Empty Slot Handling**: Unused slots remain empty (cleared) when not needed

## Layout

The Real-Time Monitoring section uses a fixed 3x2 grid layout:
- **3 rows × 2 columns = 6 total slots**
- Fixed height: 90px
- Compact label format: `<label name> : <signal value> <signal unit>`
- Labels are styled with minimal padding and borders for compact display

## Test-Specific Signal Configuration

### Digital Logic Test
- **Applied Input**: Displays the last sent command value (HIGH=1 or LOW=0)
  - Tracks `value_high` and `value_low` from test configuration
  - Updates when HIGH or LOW commands are sent
- **Digital Input**: Displays feedback signal value from DUT

### Analog Sweep Test
- **Current Signal**: Displays DAC voltage command (in Volts)
- **Feedback Signal**: Displays feedback signal value from DUT

### Phase Current Test
- **Set Id**: Displays latest `id_ref_signal` value sent (tracked from command messages)
- **Set Iq**: Displays latest `iq_ref_signal` value sent (tracked from command messages)
- **DUT Phase V Current**: Displays `phase_v_signal` from data collection
- **DUT Phase W Current**: Displays `phase_w_signal` from data collection

### Analog Static Test
- **EOL Measured Signal**: Displays EOL measurement signal value
- **DUT Feedback Signal**: Displays DUT feedback signal value

### Analog PWM Sensor Test
- **Reference PWM Frequency**: Static value from test configuration (does not change)
- **DUT PWM Frequency**: Displays feedback PWM frequency signal
- **Reference Duty**: Static value from test configuration (does not change)
- **DUT Duty**: Displays feedback duty cycle signal

### Temperature Validation Test
- **Reference Temperature**: Static value from test configuration (does not change)
- **DUT Temperature**: Displays feedback temperature signal

### Fan Control Test
- **Fan Enabled**: Displays fan enabled status signal
- **Fan Tach Signal**: Displays fan tachometer signal
- **Fan Fault**: Displays fan fault status signal

### External 5V Test
- **EOL Measurement**: Displays EOL measurement signal value
- **DUT Measurement**: Displays DUT measurement signal value

### DC Bus Sensing
- **DUT DC Bus Voltage**: Displays DC bus voltage signal

### Output Current Calibration
- **Output Current Reference**: Displays latest `current_setpoint_signal` value sent (tracked from command messages)
- **DUT Output Current**: Displays feedback output current signal

### Charged HV Bus Test
- **Enable Relay**: Displays enable relay status signal
- **Enable PFC**: Displays enable PFC status signal
- **PFC Power Good**: Displays PFC power good status signal

### Charger Functional Test
- **Enable Relay**: Displays enable relay status signal
- **Enable PFC**: Displays enable PFC status signal
- **PFC Power Good**: Displays PFC power good status signal
- **Output Current**: Displays output current signal

## Signal Value Formatting

Signal values are automatically formatted with appropriate units based on signal type:

- **Voltage**: `X.XX V` (e.g., "12.50 V")
- **Current**: `X.XX A` (e.g., "5.25 A")
- **Temperature**: `X.XX °C` (e.g., "25.30 °C")
- **Frequency**: `X.XX Hz` (e.g., "1000.00 Hz")
- **Duty Cycle**: `X.XX %` (e.g., "50.00 %")
- **Digital**: `0` or `1` (e.g., "1")
- **Generic**: `X.XX` (e.g., "123.45")

## Update Mechanisms

### 1. Periodic Polling
- A timer runs every 100ms to update monitored signals from CAN cache
- Reads signal values using `get_latest_signal(message_id, signal_name)`
- Updates all configured monitoring labels

### 2. Event-Driven Updates
- **Analog Sweep Test**: Updates via `_update_plot()` callback when new data points are collected
- **Phase Current Test**: Updates via `phase_current_service` during signal collection
- **Digital Logic Test**: Updates when HIGH/LOW commands are sent
- **Output Current Calibration**: Updates when setpoint commands are sent

### 3. Command Tracking
For tests that send commands, the system tracks the latest sent value:
- **Digital Logic Test**: Tracks HIGH/LOW commands via `track_sent_command_value('applied_input', value)`
- **Phase Current Test**: Tracks id_ref and iq_ref via `track_sent_command_value('set_id', value)` and `track_sent_command_value('set_iq', value)`
- **Output Current Calibration**: Tracks setpoint via `track_sent_command_value('output_current_reference', value)`

## Static Reference Values

Some tests display static reference values that are set once from test configuration and remain constant:
- **Reference PWM Frequency**: From `reference_pwm_frequency` in test config
- **Reference Duty**: From `reference_duty` in test config
- **Reference Temperature**: From `reference_temperature_c` in test config

These values are displayed immediately when the test starts and do not change during test execution.

## Implementation Details

### Configuration Method
The `_configure_monitor_signals_for_test(test)` method:
1. Clears all existing monitoring labels
2. Determines test type from `test['actuation']['type']`
3. Sets up appropriate signals for that test type
4. Stores signal names and message IDs for periodic polling
5. Initializes static reference values if applicable
6. Starts the periodic update timer

### Reset Behavior
When a new test starts:
1. All monitoring labels are cleared
2. Configuration is reset for the new test type
3. Sent value tracking is cleared
4. Static values are re-initialized from test config
5. Periodic update timer is restarted

### Signal Name Mapping
The system stores signal names and message IDs in `_monitor_sent_values` dictionary:
- Format: `{signal_key}_signal_name` and `{signal_key}_msg_id`
- Example: `dut_temperature_signal_name` and `temp_msg_id`

This allows the periodic polling mechanism to automatically read and update signals from CAN cache.

## Color Coding

Signal values are color-coded based on thresholds (if applicable):
- **Green**: Value within good range
- **Orange**: Value within warning range
- **Red**: Value outside acceptable range
- **Gray**: Value is N/A (not available)

## Backward Compatibility

The system maintains backward compatibility with existing code:
- Old signal keys (`current_signal`, `feedback_signal`, etc.) are still supported
- Backward compatibility references are updated dynamically based on active test configuration
- Legacy update methods continue to work but are mapped to new signal names

## Adding Monitoring for New Test Types

To add monitoring support for a new test type:

1. **Add configuration in `_configure_monitor_signals_for_test()`**:
   ```python
   elif test_type == 'Your New Test Type':
       _setup_signal('signal_key', 'Display Name', initial_value)
       # Store signal name and message ID for polling
       self._monitor_sent_values['signal_key_signal_name'] = actuation.get('signal_name')
       self._monitor_sent_values['signal_key_msg_id'] = actuation.get('message_id')
   ```

2. **Add update calls in test execution** (if needed):
   ```python
   if self.gui is not None and hasattr(self.gui, 'update_monitor_signal_by_name'):
       self.gui.update_monitor_signal_by_name('signal_key', value)
   ```

3. **Add command tracking** (if test sends commands):
   ```python
   if self.gui is not None and hasattr(self.gui, 'track_sent_command_value'):
       self.gui.track_sent_command_value('signal_key', sent_value)
   ```

4. **Update periodic polling** (if needed):
   Add special handling in `_update_monitored_signals_from_can()` if the signal requires special processing.

## Related Files

- **Main Implementation**: `host_gui/base_gui.py`
  - `_configure_monitor_signals_for_test()`: Configuration method
  - `reset_monitor_signals()`: Reset and configuration entry point
  - `_update_monitored_signals_from_can()`: Periodic polling method
  - `track_sent_command_value()`: Command tracking method
  - `update_monitor_signal_by_name()`: Signal update wrapper
  - `_update_signal_with_status()`: Core update method with formatting

- **Test Execution**: `host_gui/test_runner.py`
  - Command tracking calls for Digital Logic Test and Output Current Calibration

- **Phase Current Service**: `host_gui/services/phase_current_service.py`
  - Command tracking and signal updates for Phase Current Test

## Summary

The Real-Time Monitoring system provides a flexible, test-specific display that automatically adapts to show only relevant signals for each test type. The system uses a combination of periodic polling and event-driven updates to ensure real-time accuracy, while maintaining a compact, fixed-size layout that doesn't interfere with other GUI elements.

